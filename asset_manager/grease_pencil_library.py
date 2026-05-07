# grease_pencil_library.py
"""
Módulo de Biblioteca Grease Pencil para Asset Manager Pro
VERSÃO COMPLETA - Blender 5.0 (Grease Pencil v3)
Suporte a múltiplos frames, thumbnails e portabilidade entre projetos
"""

import bpy
import json
import uuid
import shutil
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import bpy.utils.previews as previews

# ===========================================================================
# PREVIEW COLLECTIONS (gerenciamento de thumbnails)
# ===========================================================================
_preview_collections = {}

def get_preview_collection():
    """Retorna a coleção de previews"""
    pcoll = _preview_collections.get("gp_library")
    if pcoll is None:
        pcoll = previews.new()
        _preview_collections["gp_library"] = pcoll
    return pcoll

def invalidate_library_previews():
    """Limpa o cache de previews"""
    pcoll = _preview_collections.get("gp_library")
    if pcoll:
        previews.remove(pcoll)
        _preview_collections.pop("gp_library", None)

def clear_preview_collections():
    """Limpa todas as coleções de preview"""
    for pcoll in _preview_collections.values():
        previews.remove(pcoll)
    _preview_collections.clear()

# ===========================================================================
# CONFIGURAÇÕES
# ===========================================================================
GP_LIBRARY_CONFIG = {
    'libraries_folder': 'grease_pencil/libraries',
    'thumbnails_folder': 'grease_pencil/thumbnails',
    'index_filename': 'gp_library_index.json',
    'thumbnail_size': (256, 256),
}


# ===========================================================================
# ESTRUTURA DE DADOS
# ===========================================================================
class GPPose:
    """Representa uma pose individual dentro de uma biblioteca"""
    def __init__(self):
        self.id = ""                    # UUID único
        self.name = ""                  # Nome da pose
        self.library_name = ""          # Nome do arquivo .blend
        self.library_path = ""          # Caminho relativo ao projeto
        self.frame_number = 0           # Frame onde a pose está
        self.category = "custom"        # Categoria
        self.tags = []                  # Tags para busca
        self.thumbnail_path = ""        # Caminho do thumbnail
        self.description = ""           # Descrição
        self.created = ""               # Data de criação
        
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'library_name': self.library_name,
            'library_path': self.library_path,
            'frame_number': self.frame_number,
            'category': self.category,
            'tags': self.tags,
            'thumbnail_path': self.thumbnail_path,
            'description': self.description,
            'created': self.created,
        }
    
    def from_dict(self, data):
        for k, v in data.items():
            if hasattr(self, k):
                setattr(self, k, v)
        return self


# ===========================================================================
# CLASSE PRINCIPAL DA BIBLIOTECA
# ===========================================================================
class GPLibrary:
    """Gerenciador principal da biblioteca de poses"""
    
    def __init__(self):
        self.project_path = self._find_project_path()
        self.libraries_path = None
        self.thumbnails_path = None
        self.index_path = None
        self.poses = {}  # id -> GPPose
        self.libraries = {}  # library_name -> library_info
        
        if self.project_path:
            self._setup_paths()
            self._load_index()
    
    def _find_project_path(self) -> Optional[Path]:
        """Encontra o caminho do projeto atual"""
        if not bpy.data.filepath:
            return None
        current = Path(bpy.data.filepath).parent.resolve()
        for parent in [current] + list(current.parents):
            if (parent / "project_config.json").exists():
                return parent
        return None
    
    def _setup_paths(self):
        """Configura os caminhos da biblioteca"""
        assets_dir = self.project_path / "assets"
        self.libraries_path = assets_dir / GP_LIBRARY_CONFIG['libraries_folder']
        self.thumbnails_path = assets_dir / GP_LIBRARY_CONFIG['thumbnails_folder']
        self.index_path = assets_dir / GP_LIBRARY_CONFIG['index_filename']
        
        # Criar pastas necessárias
        self.libraries_path.mkdir(parents=True, exist_ok=True)
        self.thumbnails_path.mkdir(parents=True, exist_ok=True)
    
    def _load_index(self):
        """Carrega o índice de bibliotecas e poses"""
        self.poses.clear()
        self.libraries.clear()
        
        if not self.index_path or not self.index_path.exists():
            return
        
        try:
            with open(self.index_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Carregar bibliotecas
            for lib_name, lib_info in data.get('libraries', {}).items():
                self.libraries[lib_name] = lib_info
            
            # Carregar poses
            for pose_id, pose_data in data.get('poses', {}).items():
                pose = GPPose().from_dict(pose_data)
                self.poses[pose_id] = pose
                
        except Exception as e:
            print(f"Erro ao carregar índice: {e}")
    
    def _save_index(self):
        """Salva o índice de bibliotecas e poses"""
        if not self.index_path:
            return
        
        data = {
            'version': '2.0',
            'project': self.project_path.name if self.project_path else '',
            'updated': datetime.now().isoformat(),
            'libraries': self.libraries,
            'poses': {pid: p.to_dict() for pid, p in self.poses.items()}
        }
        
        try:
            with open(self.index_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Erro ao salvar índice: {e}")
    
    # ======================== GERENCIAMENTO DE THUMBNAILS ========================
    def _generate_thumbnail(self, pose, output_path: Path) -> bool:
        """
        Gera thumbnail para uma pose específica
        """
        if not bpy.context.scene.camera:
            print(f"  ❌ Nenhuma câmera encontrada no projeto")
            return False
        
        # Salvar estado atual
        original_filepath = bpy.data.filepath
        library_path = self.project_path / pose.library_path
        
        if not library_path.exists():
            print(f"  ❌ Biblioteca não encontrada: {library_path}")
            return False
        
        temp_load = False
        
        try:
            # Se não estamos no arquivo da biblioteca, carregar temporariamente
            if str(library_path.resolve()) != original_filepath:
                print(f"  📂 Carregando biblioteca temporariamente...")
                bpy.ops.wm.open_mainfile(filepath=str(library_path))
                temp_load = True
            
            scene = bpy.context.scene
            
            # Verificar câmera novamente após carregar
            if not scene.camera:
                print(f"  ❌ Biblioteca não tem câmera")
                return False
            
            # Salvar frame atual
            original_frame = scene.frame_current
            
            # Ir para o frame da pose
            scene.frame_set(pose.frame_number)
            bpy.context.view_layer.update()
            
            # Configurar render
            old_format = scene.render.image_settings.file_format
            old_filepath = scene.render.filepath
            old_res_x = scene.render.resolution_x
            old_res_y = scene.render.resolution_y
            old_transparent = scene.render.film_transparent
            
            # Configurar para PNG quadrado
            scene.render.image_settings.file_format = 'PNG'
            scene.render.image_settings.color_mode = 'RGBA'
            scene.render.resolution_x = 256
            scene.render.resolution_y = 256
            scene.render.film_transparent = True
            scene.render.filepath = str(output_path)
            
            # Criar diretório
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Renderizar
            bpy.ops.render.render(write_still=True)
            
            # Restaurar configurações
            scene.render.image_settings.file_format = old_format
            scene.render.filepath = old_filepath
            scene.render.resolution_x = old_res_x
            scene.render.resolution_y = old_res_y
            scene.render.film_transparent = old_transparent
            
            # Restaurar frame
            scene.frame_set(original_frame)
            
            return True
            
        except Exception as e:
            print(f"  ❌ Erro ao gerar thumbnail: {e}")
            import traceback
            traceback.print_exc()
            return False
            
        finally:
            # Restaurar arquivo original se carregamos temporariamente
            if temp_load and original_filepath:
                print(f"  📂 Restaurando projeto original...")
                try:
                    bpy.ops.wm.open_mainfile(filepath=original_filepath)
                except:
                    print(f"  ⚠️ Erro ao restaurar projeto original")

    def get_thumbnail_icon(self, pose_id: str, library_name: str, frame_number: int) -> str:
        """
        Retorna a chave do ícone para usar na UI
        """
        if not self.thumbnails_path:
            return None
            
        thumb_path = self.thumbnails_path / f"{pose_id}.png"
        
        if not thumb_path.exists():
            return None
        
        pcoll = get_preview_collection()
        key = f"{library_name}_{pose_id}"
        
        if key not in pcoll:
            try:
                pcoll.load(key, str(thumb_path), 'IMAGE')
            except Exception as e:
                print(f"❌ Erro ao carregar ícone: {e}")
                return None
        
        return key
    
    # ======================== SALVAR BIBLIOTECA ========================
    def save_library(self, library_name: str, description: str = "", 
                    frames: List[int] = None, overwrite: bool = False) -> Tuple[bool, str]:
        """
        Salva o objeto Grease Pencil selecionado como uma biblioteca
        Gera thumbnails usando a câmera atual do projeto
        """
        # Verificar objeto selecionado
        obj = bpy.context.active_object
        if not obj or obj.type != 'GREASEPENCIL':
            return False, "Selecione um objeto Grease Pencil"
        
        # Verificar se existe câmera
        if not bpy.context.scene.camera:
            return False, "Nenhuma câmera encontrada no projeto. Adicione uma câmera primeiro."
        
        obj_name = obj.name
        library_filename = f"{library_name}.blend"
        library_path = self.libraries_path / library_filename
        
        if library_path.exists() and not overwrite:
            return False, f"Biblioteca '{library_name}' já existe"
        
        # Determinar quais frames salvar
        if frames is None:
            frames_set = set()
            for layer in obj.data.layers:
                for frame in layer.frames:
                    frames_set.add(frame.frame_number)
            frames = sorted(list(frames_set))
        
        if not frames:
            return False, "Nenhum frame encontrado no objeto Grease Pencil"
        
        print(f"📊 Salvando biblioteca '{library_name}' com frames: {frames}")
        
        # ===== PRIMEIRO: GERAR THUMBNAILS (usando câmera atual) =====
        print(f"📸 Gerando thumbnails usando câmera atual...")
        
        thumbnails_path = self.thumbnails_path / library_name
        thumbnails_path.mkdir(parents=True, exist_ok=True)
        
        thumb_paths = {}
        for frame_number in frames:
            thumb_filename = f"{library_name}_frame_{frame_number:03d}.png"
            thumb_path = thumbnails_path / thumb_filename
            self._generate_thumbnail(frame_number, thumb_path)
            thumb_paths[frame_number] = thumb_path
        
        # ===== SEGUNDO: SALVAR O ARQUIVO .BLEND =====
        try:
            # Salvar arquivo temporário
            current_filepath = bpy.data.filepath
            temp_dir = self.libraries_path / "temp"
            temp_dir.mkdir(exist_ok=True)
            temp_blend = temp_dir / f"{library_name}_temp.blend"
            
            bpy.ops.wm.save_as_mainfile(filepath=str(temp_blend), copy=True)
            bpy.ops.wm.open_mainfile(filepath=str(temp_blend))
            
            # Encontrar objeto
            temp_obj = None
            for o in bpy.data.objects:
                if o.type == 'GREASEPENCIL' and o.name == obj_name:
                    temp_obj = o
                    break
            
            if temp_obj:
                # Remover outros objetos
                for o in list(bpy.data.objects):
                    if o != temp_obj:
                        bpy.data.objects.remove(o, do_unlink=True)
                
                # Remover cenas extras
                for scene in list(bpy.data.scenes):
                    if scene.name != 'Scene':
                        bpy.data.scenes.remove(scene)
                
                # Garantir que está na cena
                if temp_obj.name not in bpy.context.scene.collection.objects:
                    bpy.context.scene.collection.objects.link(temp_obj)
                
                # Salvar
                bpy.ops.wm.save_as_mainfile(filepath=str(library_path))
                print(f"✅ Biblioteca salva")
            else:
                return False, "Erro ao processar objeto"
            
            # Voltar ao original
            if current_filepath:
                bpy.ops.wm.open_mainfile(filepath=current_filepath)
            
            # Limpar temporário
            if temp_blend.exists():
                temp_blend.unlink()
            try:
                temp_dir.rmdir()
            except:
                pass
            
            if not library_path.exists():
                return False, "Erro ao criar arquivo da biblioteca"
            
            # ===== REGISTRAR NO ÍNDICE =====
            self.libraries[library_name] = {
                'filename': library_filename,
                'path': str(library_path.relative_to(self.project_path)),
                'description': description,
                'frames': frames,
                'created': datetime.now().isoformat(),
                'modified': datetime.now().isoformat(),
                'object_name': obj_name
            }
            
            # Criar poses com os thumbnails gerados
            for frame_number in frames:
                pose_id = str(uuid.uuid4())
                pose = GPPose()
                pose.id = pose_id
                pose.name = f"{library_name}_frame_{frame_number:03d}"
                pose.library_name = library_name
                pose.library_path = str(library_path.relative_to(self.project_path))
                pose.frame_number = frame_number
                pose.category = "library"
                pose.created = datetime.now().isoformat()
                
                # Associar thumbnail
                thumb_path = thumb_paths.get(frame_number)
                if thumb_path and thumb_path.exists():
                    # Copiar thumbnail para o local correto
                    final_thumb_path = self.thumbnails_path / f"{pose_id}.png"
                    import shutil
                    shutil.copy2(thumb_path, final_thumb_path)
                    pose.thumbnail_path = str(final_thumb_path.relative_to(self.project_path))
                else:
                    pose.thumbnail_path = ""
                
                self.poses[pose_id] = pose
            
            self._save_index()
            
            return True, f"✅ Biblioteca '{library_name}' salva com {len(frames)} poses!"
            
        except Exception as e:
            print(f"❌ Erro ao salvar biblioteca: {e}")
            import traceback
            traceback.print_exc()
            
            try:
                if current_filepath:
                    bpy.ops.wm.open_mainfile(filepath=current_filepath)
            except:
                pass
            
            return False, f"Erro ao salvar biblioteca: {str(e)}"

    # ======================== APLICAR POSE ========================
    def _extract_pose_from_frame(self, source_obj, source_frame: int,
                                  target_obj, target_frame: int) -> bool:
        """
        Extrai a pose de um frame específico usando operadores nativos
        """
        try:
            # Garantir que os objetos estão na view layer
            if source_obj.name not in bpy.context.view_layer.objects:
                bpy.context.scene.collection.objects.link(source_obj)
                bpy.context.view_layer.update()
            
            if target_obj.name not in bpy.context.view_layer.objects:
                bpy.context.scene.collection.objects.link(target_obj)
                bpy.context.view_layer.update()
            
            # Guardar estado
            original_active = bpy.context.view_layer.objects.active
            original_selected = [obj for obj in bpy.context.selected_objects if obj]
            original_frame = bpy.context.scene.frame_current
            original_mode = bpy.context.mode
            
            # Sair do modo EDIT
            if bpy.context.mode == 'EDIT':
                bpy.ops.object.mode_set(mode='OBJECT')
            
            # ==================== COPIAR ====================
            # Selecionar fonte
            bpy.ops.object.select_all(action='DESELECT')
            source_obj.select_set(True)
            bpy.context.view_layer.objects.active = source_obj
            
            # Ir para o frame
            bpy.context.scene.frame_set(source_frame)
            
            # Entrar em modo EDIT
            bpy.ops.object.mode_set(mode='EDIT')
            
            # Selecionar e copiar
            if bpy.app.version >= (4, 3, 0):
                bpy.ops.grease_pencil.select_all(action='SELECT')
                bpy.ops.grease_pencil.copy()
            else:
                bpy.ops.gpencil.select_all(action='SELECT')
                bpy.ops.gpencil.copy()
            
            # ==================== COLAR ====================
            bpy.ops.object.mode_set(mode='OBJECT')
            
            bpy.ops.object.select_all(action='DESELECT')
            target_obj.select_set(True)
            bpy.context.view_layer.objects.active = target_obj
            
            bpy.context.scene.frame_set(target_frame)
            bpy.ops.object.mode_set(mode='EDIT')
            
            # Limpar e colar
            if bpy.app.version >= (4, 3, 0):
                bpy.ops.grease_pencil.select_all(action='SELECT')
                bpy.ops.grease_pencil.delete()
                bpy.ops.grease_pencil.paste()
            else:
                bpy.ops.gpencil.select_all(action='SELECT')
                bpy.ops.gpencil.delete(type='STROKES')
                bpy.ops.gpencil.paste()
            
            # ==================== RESTAURAR ====================
            bpy.ops.object.mode_set(mode='OBJECT')
            
            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selected:
                if obj and obj.name in bpy.data.objects:
                    try:
                        obj.select_set(True)
                    except:
                        pass
            
            if original_active and original_active.name in bpy.data.objects:
                try:
                    bpy.context.view_layer.objects.active = original_active
                except:
                    pass
            
            bpy.context.scene.frame_set(original_frame)
            
            if original_mode == 'EDIT':
                try:
                    bpy.ops.object.mode_set(mode='EDIT')
                except:
                    pass
            
            return True
            
        except Exception as e:
            print(f"Erro ao extrair pose: {e}")
            import traceback
            traceback.print_exc()
            
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except:
                pass
            
            return False
    
    def apply_pose_from_library(self, target_object, pose_id: str) -> Tuple[bool, str]:
        """Aplica uma pose específica da biblioteca ao objeto alvo"""
        if not target_object or target_object.type != 'GREASEPENCIL':
            return False, "Objeto alvo deve ser Grease Pencil"
        
        pose = self.poses.get(pose_id)
        if not pose:
            return False, "Pose não encontrada"
        
        library_path = self.project_path / pose.library_path
        if not library_path.exists():
            return False, f"Arquivo da biblioteca não encontrado: {library_path}"
        
        try:
            # Carregar biblioteca
            with bpy.data.libraries.load(str(library_path), link=False, relative=False) as (data_from, data_to):
                data_to.objects = data_from.objects[:]
            
            # Encontrar objeto carregado
            loaded_obj = next((obj for obj in bpy.data.objects if obj.name in data_from.objects), None)
            if not loaded_obj:
                return False, "Não foi possível carregar a biblioteca"
            
            # Garantir que está na view layer
            if loaded_obj.name not in bpy.context.view_layer.objects:
                bpy.context.scene.collection.objects.link(loaded_obj)
                bpy.context.view_layer.update()
            
            current_frame = bpy.context.scene.frame_current
            
            # Aplicar pose
            success = self._extract_pose_from_frame(
                loaded_obj, pose.frame_number, target_object, current_frame
            )
            
            # Limpar objeto temporário
            bpy.data.objects.remove(loaded_obj, do_unlink=True)
            
            if success:
                return True, f"✅ Pose '{pose.name}' (frame {pose.frame_number}) aplicada no frame {current_frame}"
            else:
                return False, f"Erro ao aplicar pose do frame {pose.frame_number}"
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"Erro ao aplicar pose: {str(e)}"
    
    # ======================== IMPORTAR BIBLIOTECA ========================
    def import_library(self, external_blend_path: str, library_name: str = None) -> Tuple[bool, str]:
        """Importa biblioteca completa com todos os thumbnails"""
        
        # Verificações iniciais
        if not self.project_path or not self.libraries_path:
            return False, "Nenhum projeto ativo. Use 'Iniciar Projeto' primeiro."
        
        source_path = Path(external_blend_path)
        if not source_path.exists():
            return False, "Arquivo não encontrado"
        
        if source_path.suffix.lower() != '.blend':
            return False, "O arquivo deve ser .blend"
        
        if not library_name:
            library_name = source_path.stem
        
        dest_path = self.libraries_path / f"{library_name}.blend"
        if dest_path.exists():
            return False, f"Biblioteca '{library_name}' já existe no projeto"
        
        try:
            # ===== 1. COPIAR O ARQUIVO .BLEND =====
            print(f"📄 Copiando biblioteca: {source_path.name}")
            shutil.copy2(source_path, dest_path)
            
            # ===== 2. LOCALIZAR PASTA DE THUMBNAILS DA ORIGEM =====
            # Assumindo estrutura: [projeto_origem]/assets/grease_pencil/thumbnails/
            source_thumb_dir = source_path.parent.parent / "thumbnails"
            
            # Se não encontrar, tentar outros locais comuns
            if not source_thumb_dir.exists():
                source_thumb_dir = source_path.parent / "thumbnails"
            if not source_thumb_dir.exists():
                source_thumb_dir = source_path.parent.parent.parent / "thumbnails"
            
            # ===== 3. COPIAR THUMBNAILS =====
            thumbnails_copied = 0
            dest_thumb_dir = self.thumbnails_path
            dest_thumb_dir.mkdir(parents=True, exist_ok=True)
            
            if source_thumb_dir.exists():
                print(f"📸 Copiando thumbnails de: {source_thumb_dir}")
                
                # Copiar TODOS os arquivos .png que podem ser thumbnails
                for thumb_file in source_thumb_dir.glob("*.png"):
                    # Verificar se o thumbnail pertence a esta biblioteca
                    # Por nome do arquivo ou pelo conteúdo
                    should_copy = False
                    
                    # Método 1: Nome contém o nome da biblioteca
                    if library_name in thumb_file.stem:
                        should_copy = True
                    
                    # Método 2: Nome segue padrão de pose_id (UUID)
                    elif len(thumb_file.stem) == 36 and '-' in thumb_file.stem:
                        should_copy = True  # Parece um UUID
                    
                    if should_copy:
                        dest_thumb = dest_thumb_dir / thumb_file.name
                        shutil.copy2(thumb_file, dest_thumb)
                        thumbnails_copied += 1
                        print(f"  ✅ Copiado: {thumb_file.name}")
            else:
                print(f"⚠️ Pasta de thumbnails não encontrada na origem")
            
            print(f"📸 {thumbnails_copied} thumbnails copiados")
            
            # ===== 4. ANALISAR O .BLEND E REGISTRAR =====
            frames_info = self._analyze_library_frames(dest_path)
            
            # Registrar a biblioteca
            self.libraries[library_name] = {
                'filename': f"{library_name}.blend",
                'path': str(dest_path.relative_to(self.project_path)),
                'description': f"Importado de {source_path.parent.name}",
                'frames': frames_info['frames'],
                'created': datetime.now().isoformat(),
                'modified': datetime.now().isoformat(),
                'object_name': frames_info.get('object_name', 'Unknown'),
                'source_project': str(source_path.parent.parent.parent) if source_thumb_dir.exists() else ""
            }
            
            # ===== 5. CRIAR POSES E VINCULAR THUMBNAILS =====
            poses_created = 0
            for frame_number in frames_info['frames']:
                pose_id = str(uuid.uuid4())
                pose = GPPose()
                pose.id = pose_id
                pose.name = f"{library_name}_frame_{frame_number:03d}"
                pose.library_name = library_name
                pose.library_path = str(dest_path.relative_to(self.project_path))
                pose.frame_number = frame_number
                pose.category = "imported"
                pose.description = f"Importado com {thumbnails_copied} thumbnails"
                pose.created = datetime.now().isoformat()
                
                # Tentar encontrar um thumbnail para este frame
                thumbnail_found = False
                
                # Procurar por padrões de nome comuns
                possible_patterns = [
                    f"{pose_id}.png",                           # UUID
                    f"{library_name}_frame_{frame_number:03d}.png",  # library_frame_001
                    f"{library_name}_{frame_number}.png",       # library_1
                    f"frame_{frame_number:03d}.png",           # frame_001
                    f"thumb_{frame_number}.png",               # thumb_1
                    f"{library_name}_pose_{frame_number}.png", # library_pose_1
                ]
                
                for pattern in possible_patterns:
                    thumb_path = dest_thumb_dir / pattern
                    if thumb_path.exists():
                        pose.thumbnail_path = str(thumb_path.relative_to(self.project_path))
                        thumbnail_found = True
                        print(f"  ✅ Pose frame {frame_number} vinculada ao thumbnail: {pattern}")
                        break
                
                if not thumbnail_found:
                    # Tentar qualquer thumbnail que contenha o frame number
                    for thumb_file in dest_thumb_dir.glob(f"*_{frame_number:03d}*.png"):
                        pose.thumbnail_path = str(thumb_file.relative_to(self.project_path))
                        thumbnail_found = True
                        print(f"  ✅ Pose frame {frame_number} vinculada ao thumbnail: {thumb_file.name}")
                        break
                
                if not thumbnail_found:
                    print(f"  ⚠️ Pose frame {frame_number} sem thumbnail")
                    pose.thumbnail_path = ""
                
                self.poses[pose_id] = pose
                poses_created += 1
            
            # ===== 6. SALVAR ÍNDICE =====
            self._save_index()
            
            print(f"\n🔄 Ressincronizando thumbnails no projeto atual...")
            self.resync_thumbnails(library_name)
            
            return True, f"✅ Biblioteca '{library_name}' importada e sincronizada! ({poses_created} poses, {thumbnails_copied} thumbnails)"

            # ===== 7. ATUALIZAR UI =====
            from .grease_pencil_ui import invalidate_library_previews
            invalidate_library_previews()
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"Erro ao importar biblioteca: {str(e)}"

    def _find_source_project(self, blend_path: Path) -> Optional[Path]:
        """Encontra o projeto de origem baseado no caminho do arquivo .blend"""
        
        # Procurar pela estrutura padronizada: .../assets/grease_pencil/libraries/arquivo.blend
        current = blend_path.parent
        
        # Subir até encontrar a pasta 'assets'
        for _ in range(5):  # Máximo 5 níveis
            if current.name == "assets":
                project_path = current.parent
                # Verificar se tem project_config.json
                if (project_path / "project_config.json").exists():
                    return project_path
                break
            current = current.parent
        
        # Se não encontrou pela estrutura, procurar o arquivo project_config.json
        current = blend_path.parent
        for parent in [current] + list(current.parents):
            if (parent / "project_config.json").exists():
                return parent
        
        return None

    def _merge_library_from_index(self, index_path: Path, library_name: str, 
                                dest_blend_path: Path, dest_thumb_dir: Path):
        """Mescla informações da biblioteca a partir do índice de origem"""
        
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                source_index = json.load(f)
            
            # Encontrar biblioteca no índice
            lib_info = source_index.get('libraries', {}).get(library_name)
            
            if not lib_info:
                print(f"  ⚠️ Biblioteca '{library_name}' não encontrada no índice")
                self._import_library_by_analysis(dest_blend_path, library_name, dest_thumb_dir, 0)
                return
            
            # Registrar biblioteca
            self.libraries[library_name] = {
                'filename': f"{library_name}.blend",
                'path': str(dest_blend_path.relative_to(self.project_path)),
                'description': lib_info.get('description', f'Importado de {index_path.parent.parent.name}'),
                'frames': lib_info.get('frames', []),
                'created': datetime.now().isoformat(),
                'modified': datetime.now().isoformat(),
                'imported_from': str(index_path),
                'original_project': str(index_path.parent.parent.parent),
                'object_name': lib_info.get('object_name', 'Unknown')
            }
            
            # Importar poses
            poses_imported = 0
            for pose_id, pose_data in source_index.get('poses', {}).items():
                if pose_data.get('library_name') == library_name:
                    # Criar nova pose com novo UUID
                    new_pose_id = str(uuid.uuid4())
                    new_pose = GPPose()
                    new_pose.id = new_pose_id
                    new_pose.name = pose_data.get('name', f"{library_name}_pose")
                    new_pose.library_name = library_name
                    new_pose.library_path = str(dest_blend_path.relative_to(self.project_path))
                    new_pose.frame_number = pose_data.get('frame_number', 1)
                    new_pose.category = pose_data.get('category', 'imported')
                    new_pose.tags = pose_data.get('tags', [])
                    new_pose.description = pose_data.get('description', f'Importado de projeto original')
                    new_pose.created = datetime.now().isoformat()
                    
                    # Verificar se o thumbnail foi copiado
                    old_thumb_name = Path(pose_data.get('thumbnail_path', '')).name
                    if old_thumb_name and (dest_thumb_dir / old_thumb_name).exists():
                        new_pose.thumbnail_path = str((dest_thumb_dir / old_thumb_name).relative_to(self.project_path))
                        print(f"  ✅ Pose {new_pose.name} - thumbnail encontrado")
                    else:
                        # Procurar por thumbnail alternativo
                        possible_thumbs = list(dest_thumb_dir.glob(f"*_{new_pose.frame_number:03d}.png"))
                        if possible_thumbs:
                            new_pose.thumbnail_path = str(possible_thumbs[0].relative_to(self.project_path))
                            print(f"  ✅ Pose {new_pose.name} - thumbnail alternativo encontrado")
                        else:
                            new_pose.thumbnail_path = ""
                            print(f"  ⚠️ Pose {new_pose.name} - sem thumbnail")
                    
                    self.poses[new_pose_id] = new_pose
                    poses_imported += 1
            
            print(f"  ✅ {poses_imported} poses importadas do índice")
            
        except Exception as e:
            print(f"  ❌ Erro ao processar índice: {e}")
            self._import_library_by_analysis(dest_blend_path, library_name, dest_thumb_dir, 0)

    def _import_library_by_analysis(self, dest_blend_path: Path, library_name: str, 
                                    dest_thumb_dir: Path, existing_thumbs: int):
        """Fallback: analisar o .blend diretamente se não houver índice"""
        
        print(f"  🔍 Analisando arquivo .blend diretamente...")
        
        frames_info = self._analyze_library_frames(dest_blend_path)
        
        # Registrar biblioteca
        self.libraries[library_name] = {
            'filename': f"{library_name}.blend",
            'path': str(dest_blend_path.relative_to(self.project_path)),
            'description': f'Importado por análise direta',
            'frames': frames_info['frames'],
            'created': datetime.now().isoformat(),
            'modified': datetime.now().isoformat(),
            'object_name': frames_info.get('object_name', 'Unknown')
        }
        
        # Criar poses
        for frame_number in frames_info['frames']:
            pose_id = str(uuid.uuid4())
            pose = GPPose()
            pose.id = pose_id
            pose.name = f"{library_name}_frame_{frame_number:03d}"
            pose.library_name = library_name
            pose.library_path = str(dest_blend_path.relative_to(self.project_path))
            pose.frame_number = frame_number
            pose.category = "imported"
            pose.description = "Importado por análise direta"
            pose.created = datetime.now().isoformat()
            
            # Procurar thumbnail existente
            possible_thumbs = list(dest_thumb_dir.glob(f"*_{frame_number:03d}.png"))
            if possible_thumbs:
                pose.thumbnail_path = str(possible_thumbs[0].relative_to(self.project_path))
            else:
                pose.thumbnail_path = ""
            
            self.poses[pose_id] = pose
        
        print(f"  ✅ {len(frames_info['frames'])} poses criadas por análise")

    def _import_library_only_blend(self, source_path: Path, library_name: str, dest_path: Path) -> Tuple[bool, str]:
        """Importa apenas o .blend quando não encontra o projeto de origem"""
        
        print(f"  ⚠️ Importando apenas .blend (sem thumbnails)")
        
        # Copiar apenas o .blend
        shutil.copy2(source_path, dest_path)
        
        # Analisar e criar poses sem thumbnails
        frames_info = self._analyze_library_frames(dest_path)
        
        self.libraries[library_name] = {
            'filename': f"{library_name}.blend",
            'path': str(dest_path.relative_to(self.project_path)),
            'description': f'Importado de {source_path.name} (sem thumbnails)',
            'frames': frames_info['frames'],
            'created': datetime.now().isoformat(),
            'modified': datetime.now().isoformat(),
            'object_name': frames_info.get('object_name', 'Unknown')
        }
        
        for frame_number in frames_info['frames']:
            pose_id = str(uuid.uuid4())
            pose = GPPose()
            pose.id = pose_id
            pose.name = f"{library_name}_frame_{frame_number:03d}"
            pose.library_name = library_name
            pose.library_path = str(dest_path.relative_to(self.project_path))
            pose.frame_number = frame_number
            pose.category = "imported"
            pose.description = "Importado sem thumbnails"
            pose.created = datetime.now().isoformat()
            pose.thumbnail_path = ""
            
            self.poses[pose_id] = pose
        
        self._save_index()
        
        return True, f"⚠️ Biblioteca '{library_name}' importada sem thumbnails ({len(frames_info['frames'])} poses)"

    def resync_thumbnails(self, library_name: str = None) -> Tuple[bool, str]:
        """
        Ressincroniza thumbnails no projeto atual
        - Verifica quais thumbnails existem
        - Associa cada thumbnail à pose correta
        - Gera thumbnails faltantes se necessário
        """
        if not self.project_path:
            return False, "Nenhum projeto ativo"
        
        # Filtrar poses por biblioteca
        poses_to_sync = []
        if library_name:
            poses_to_sync = [p for p in self.poses.values() if p.library_name == library_name]
        else:
            poses_to_sync = list(self.poses.values())
        
        if not poses_to_sync:
            return False, "Nenhuma pose encontrada para sincronizar"
        
        print(f"\n🔄 Ressincronizando {len(poses_to_sync)} poses...")
        
        thumbnails_found = 0
        thumbnails_missing = 0
        thumbnails_repaired = 0
        
        for pose in poses_to_sync:
            # Caminho onde o thumbnail DEVERIA estar
            expected_thumb_path = self.thumbnails_path / f"{pose.id}.png"
            
            # Verificar se o thumbnail existe
            if expected_thumb_path.exists():
                # Thumbnail já existe no local correto
                pose.thumbnail_path = str(expected_thumb_path.relative_to(self.project_path))
                thumbnails_found += 1
                print(f"  ✅ {pose.name} - thumbnail OK")
                
            else:
                # Tentar encontrar o thumbnail em outros lugares
                thumbnail_found = False
                
                # Procurar por padrões alternativos
                library_name_clean = pose.library_name.replace(" ", "_")
                patterns = [
                    f"{pose.id}.png",                                    # UUID
                    f"{library_name_clean}_frame_{pose.frame_number:03d}.png",
                    f"{library_name_clean}_{pose.frame_number}.png",
                    f"{pose.name}.png",
                    f"frame_{pose.frame_number:03d}.png",
                    f"thumb_{pose.frame_number}.png",
                    f"pose_{pose.frame_number}.png",
                    f"*_{pose.frame_number:03d}.png",                    # Qualquer nome com o frame
                    f"*{pose.frame_number}*.png",                       # Qualquer nome com o número
                ]
                
                for pattern in patterns:
                    if '*' in pattern:
                        # Busca com wildcard
                        matches = list(self.thumbnails_path.glob(pattern))
                        if matches:
                            thumb_path = matches[0]
                            # Renomear para o padrão UUID
                            new_path = self.thumbnails_path / f"{pose.id}.png"
                            shutil.move(str(thumb_path), str(new_path))
                            pose.thumbnail_path = str(new_path.relative_to(self.project_path))
                            thumbnail_found = True
                            thumbnails_repaired += 1
                            print(f"  🔧 {pose.name} - thumbnail renomeado: {thumb_path.name} -> {pose.id}.png")
                            break
                    else:
                        # Busca exata
                        thumb_path = self.thumbnails_path / pattern
                        if thumb_path.exists():
                            # Renomear para o padrão UUID
                            new_path = self.thumbnails_path / f"{pose.id}.png"
                            shutil.move(str(thumb_path), str(new_path))
                            pose.thumbnail_path = str(new_path.relative_to(self.project_path))
                            thumbnail_found = True
                            thumbnails_repaired += 1
                            print(f"  🔧 {pose.name} - thumbnail renomeado: {pattern} -> {pose.id}.png")
                            break
                
                if not thumbnail_found:
                    thumbnails_missing += 1
                    pose.thumbnail_path = ""
                    print(f"  ⚠️ {pose.name} - thumbnail NÃO encontrado (frame {pose.frame_number})")
        
        # Salvar índice atualizado
        self._save_index()
        
        # Atualizar UI
        from .grease_pencil_ui import invalidate_library_previews
        invalidate_library_previews()
        
        message = f"✅ Sincronização concluída! Encontrados: {thumbnails_found}, Reparados: {thumbnails_repaired}, Faltando: {thumbnails_missing}"
        print(f"\n{message}")
        
        return True, message

    def _analyze_library_frames(self, library_path: Path) -> Dict:
        """Analisa um arquivo .blend para extrair frames"""
        frames_info = {'frames': [], 'object_name': None}
        
        current_filepath = bpy.data.filepath
        
        try:
            bpy.ops.wm.open_mainfile(filepath=str(library_path))
            
            for obj in bpy.data.objects:
                if obj.type == 'GREASEPENCIL':
                    frames_info['object_name'] = obj.name
                    frames_set = set()
                    for layer in obj.data.layers:
                        for frame in layer.frames:
                            frames_set.add(frame.frame_number)
                    frames_info['frames'] = sorted(list(frames_set))
                    break
            
            if not frames_info['frames']:
                frames_info['frames'] = [1]
                
        except Exception as e:
            print(f"Erro ao analisar biblioteca: {e}")
            frames_info['frames'] = [1]
        
        finally:
            if current_filepath:
                try:
                    bpy.ops.wm.open_mainfile(filepath=current_filepath)
                except:
                    pass
        
        return frames_info
    
    # ======================== GERENCIAMENTO ========================
    def get_libraries(self) -> Dict:
        """Retorna todas as bibliotecas disponíveis"""
        return self.libraries
    
    def get_poses(self, library_name: str = None, category: str = None) -> List[GPPose]:
        """Retorna poses filtradas"""
        poses = list(self.poses.values())
        
        if library_name:
            poses = [p for p in poses if p.library_name == library_name]
        
        if category:
            poses = [p for p in poses if p.category == category]
        
        return poses
    
    def delete_library(self, library_name: str) -> Tuple[bool, str]:
        """Remove uma biblioteca completa"""
        if library_name not in self.libraries:
            return False, "Biblioteca não encontrada"
        
        library_info = self.libraries[library_name]
        
        try:
            # Remover arquivo .blend
            library_path = self.project_path / library_info['path']
            if library_path.exists():
                library_path.unlink()
            
            # Remover poses associadas
            poses_to_delete = [pid for pid, pose in self.poses.items() 
                              if pose.library_name == library_name]
            for pid in poses_to_delete:
                pose = self.poses[pid]
                if pose.thumbnail_path:
                    thumb_path = self.project_path / pose.thumbnail_path
                    thumb_path.unlink(missing_ok=True)
                del self.poses[pid]
            
            # Remover do índice
            del self.libraries[library_name]
            
            self._save_index()
            
            return True, f"✅ Biblioteca '{library_name}' removida"
            
        except Exception as e:
            return False, f"Erro ao remover biblioteca: {str(e)}"
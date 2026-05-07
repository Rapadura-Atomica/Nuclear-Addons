# grease_pencil_library.py
# Apenas as funções corrigidas - substitua as existentes

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
# CONFIGURAÇÕES
# ===========================================================================
GP_LIBRARY_CONFIG = {
    'libraries_folder': 'grease_pencil/libraries',
    'thumbnails_folder': 'grease_pencil/thumbnails',
    'index_filename': 'gp_library_index.json',
    'thumbnail_size': (256, 256),
}

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
# ESTRUTURA DE DADOS (mantém igual)
# ===========================================================================
class GPPose:
    """Representa uma pose individual dentro de uma biblioteca"""
    def __init__(self):
        self.id = ""
        self.name = ""
        self.library_name = ""
        self.library_path = ""
        self.frame_number = 0
        self.category = "custom"
        self.tags = []
        self.thumbnail_path = ""
        self.description = ""
        self.created = ""
        
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
# CLASSE PRINCIPAL DA BIBLIOTECA (COM FUNÇÕES CORRIGIDAS)
# ===========================================================================
class GPLibrary:
    """Gerenciador principal da biblioteca de poses"""
    
    def __init__(self):
        self.project_path = self._find_project_path()
        self.libraries_path = None
        self.thumbnails_path = None
        self.index_path = None
        self.poses = {}
        self.libraries = {}
        
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
    
    # ======================== GERAR THUMBNAIL (APENAS UMA VEZ) ========================
    def generate_thumbnail_for_frame(self, frame_number: int, output_path: Path, gp_object_name: str = None) -> bool:
        """
        Gera thumbnail para um frame específico (chamado apenas UMA VEZ no projeto fonte)
        Não requer câmera - usa viewport screenshot
        """
        try:
            scene = bpy.context.scene
            view_layer = bpy.context.view_layer
            
            # Salvar estado atual
            original_frame = scene.frame_current
            original_selected = bpy.context.selected_objects.copy()
            original_active = view_layer.objects.active
            
            # Encontrar objeto Grease Pencil
            gp_obj = None
            if gp_object_name:
                gp_obj = bpy.data.objects.get(gp_object_name)
            
            if not gp_obj:
                for obj in bpy.data.objects:
                    if obj.type == 'GREASEPENCIL':
                        gp_obj = obj
                        break
            
            if not gp_obj:
                print(f"  ❌ Nenhum objeto Grease Pencil encontrado")
                return False
            
            # Ir para o frame
            scene.frame_set(frame_number)
            
            # Isolar o objeto GP para screenshot
            bpy.ops.object.select_all(action='DESELECT')
            gp_obj.select_set(True)
            view_layer.objects.active = gp_obj
            
            # Configurar viewport para screenshot
            original_show_overlays = bpy.context.space_data.overlay.show_overlays if bpy.context.space_data else True
            
            # Tentar usar viewport render
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Método alternativo: usar view3d screenshot
            success = self._take_viewport_screenshot(gp_obj, output_path, frame_number)
            
            # Restaurar
            scene.frame_set(original_frame)
            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selected:
                if obj and obj.name in bpy.data.objects:
                    obj.select_set(True)
            if original_active and original_active.name in bpy.data.objects:
                view_layer.objects.active = original_active
            
            if success:
                print(f"  ✅ Thumbnail gerado para frame {frame_number}")
                return True
            else:
                print(f"  ⚠️ Não foi possível gerar thumbnail para frame {frame_number}")
                return False
                
        except Exception as e:
            print(f"  ❌ Erro ao gerar thumbnail: {e}")
            return False
    
    def _take_viewport_screenshot(self, obj, output_path: Path, frame_number: int) -> bool:
        """
        Tira screenshot da viewport 3D focando no objeto Grease Pencil
        """
        try:
            # Encontrar uma área 3D
            for area in bpy.context.screen.areas:
                if area.type == 'VIEW_3D':
                    # Salvar estado da região
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            # Usar contexto override
                            with bpy.context.temp_override(area=area, region=region):
                                # Configurar viewport
                                space = area.spaces.active
                                if space:
                                    # Salvar configurações
                                    old_shading = space.shading.type
                                    old_overlays = space.overlay.show_overlays
                                    
                                    # Configurar para visualização limpa
                                    space.shading.type = 'SOLID'
                                    space.shading.light = 'STUDIO'
                                    space.overlay.show_overlays = False
                                    
                                    # Tentar focar no objeto
                                    bpy.ops.view3d.view_selected()
                                    
                                    # Salvar screenshot
                                    bpy.ops.screen.screenshot(filepath=str(output_path))
                                    
                                    # Restaurar
                                    space.shading.type = old_shading
                                    space.overlay.show_overlays = old_overlays
                                    
                                    return output_path.exists()
            return False
        except Exception as e:
            print(f"    Erro no screenshot: {e}")
            return False
    
    # ======================== SALVAR BIBLIOTECA (CRIA THUMBS UMA VEZ) ========================
    def save_library(self, library_name: str, description: str = "", 
                    frames: List[int] = None, overwrite: bool = False) -> Tuple[bool, str]:
        """
        Salva o objeto Grease Pencil selecionado como uma biblioteca
        Gera thumbnails APENAS UMA VEZ e salva na pasta de thumbnails
        """
        # Verificar objeto selecionado
        obj = bpy.context.active_object
        if not obj or obj.type != 'GREASEPENCIL':
            return False, "Selecione um objeto Grease Pencil"
        
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
        
        # ===== GERAR THUMBNAILS (APENAS UMA VEZ) =====
        print(f"📸 Gerando thumbnails...")
        thumb_paths = {}
        
        for frame_number in frames:
            thumb_filename = f"{library_name}_frame_{frame_number:03d}.png"
            thumb_path = self.thumbnails_path / thumb_filename
            
            # Só gera se não existir
            if not thumb_path.exists():
                success = self.generate_thumbnail_for_frame(frame_number, thumb_path, obj_name)
                if success:
                    thumb_paths[frame_number] = thumb_path
                else:
                    print(f"  ⚠️ Falha ao gerar thumbnail para frame {frame_number}")
                    thumb_paths[frame_number] = None
            else:
                print(f"  ✅ Thumb já existe: {thumb_filename}")
                thumb_paths[frame_number] = thumb_path
        
        # ===== SALVAR O ARQUIVO .BLEND =====
        try:
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
                print(f"✅ Biblioteca salva em: {library_path}")
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
                'object_name': obj_name,
                'thumbnail_base': library_name  # Para referência das thumbs
            }
            
            # Criar poses e associar thumbs existentes
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
                
                # Associar thumbnail (já existe do passo anterior)
                expected_thumb = self.thumbnails_path / f"{library_name}_frame_{frame_number:03d}.png"
                if expected_thumb.exists():
                    pose.thumbnail_path = str(expected_thumb.relative_to(self.project_path))
                    print(f"  ✅ Pose {frame_number} associada à thumb")
                else:
                    pose.thumbnail_path = ""
                    print(f"  ⚠️ Pose {frame_number} sem thumb")
                
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

    # ======================== IMPORTAR BIBLIOTECA (REUTILIZA THUMBS) ========================
    def import_library(self, external_blend_path: str, library_name: str = None) -> Tuple[bool, str]:
        """
        Importa uma biblioteca externa para o projeto atual
        REUTILIZA as thumbs existentes - NÃO gera novas
        """
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
            # 1. Copiar arquivo .blend
            print(f"📁 Copiando biblioteca: {source_path} -> {dest_path}")
            shutil.copy2(source_path, dest_path)
            
            # 2. PROCURAR E COPIAR THUMBS DO PROJETO FONTE
            thumbs_copied = 0
            source_dir = source_path.parent
            source_thumb_dir = None
            
            # Procurar pasta de thumbnails em várias localizações possíveis
            possible_thumb_dirs = [
                source_dir / "thumbnails",                        # Junto ao .blend
                source_dir.parent / "thumbnails",                 # Pasta pai
                source_dir / "assets" / "grease_pencil" / "thumbnails",  # Estrutura Asset Manager
                source_dir.parent / "assets" / "grease_pencil" / "thumbnails",
                Path(bpy.data.filepath).parent / "assets" / "grease_pencil" / "thumbnails" if bpy.data.filepath else None,
            ]
            
            for thumb_dir in possible_thumb_dirs:
                if thumb_dir and thumb_dir.exists():
                    source_thumb_dir = thumb_dir
                    print(f"📸 Encontrada pasta de thumbs: {source_thumb_dir}")
                    break
            
            # Copiar thumbs do mesmo nome da biblioteca
            if source_thumb_dir:
                thumb_pattern = f"{library_name}_frame_*.png"
                for thumb_file in source_thumb_dir.glob(thumb_pattern):
                    dest_thumb = self.thumbnails_path / thumb_file.name
                    shutil.copy2(thumb_file, dest_thumb)
                    thumbs_copied += 1
                    print(f"  ✅ Copiada thumb: {thumb_file.name}")
            
            print(f"📸 Total de thumbs copiadas: {thumbs_copied}")
            
            # 3. Analisar frames do .blend
            frames_info = self._analyze_library_frames(dest_path)
            print(f"📊 Frames encontrados: {frames_info['frames']}")
            
            # 4. Registrar no índice
            self.libraries[library_name] = {
                'filename': f"{library_name}.blend",
                'path': str(dest_path.relative_to(self.project_path)),
                'description': f"Importado de {source_path.name}",
                'frames': frames_info['frames'],
                'created': datetime.now().isoformat(),
                'modified': datetime.now().isoformat(),
                'imported_from': str(source_path),
                'object_name': frames_info.get('object_name', 'Unknown')
            }
            
            # 5. Criar poses e VINCULAR thumbs existentes (sem gerar novas)
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
                pose.description = f"Importado de {source_path.name}"
                pose.created = datetime.now().isoformat()
                
                # Verificar se a thumb foi copiada
                expected_thumb = self.thumbnails_path / f"{library_name}_frame_{frame_number:03d}.png"
                if expected_thumb.exists():
                    pose.thumbnail_path = str(expected_thumb.relative_to(self.project_path))
                    print(f"  ✅ Pose {frame_number} vinculada à thumb existente")
                else:
                    pose.thumbnail_path = ""
                    print(f"  ⚠️ Pose {frame_number} sem thumb (não foi encontrada no projeto fonte)")
                
                self.poses[pose_id] = pose
                poses_created += 1
            
            self._save_index()
            
            # Forçar atualização dos previews na UI
            invalidate_library_previews()
            
            return True, f"✅ Biblioteca '{library_name}' importada com {poses_created} poses! ({thumbs_copied} thumbs copiadas)"
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"Erro ao importar biblioteca: {str(e)}"
    
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
    
    # ======================== APLICAR POSE ========================
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
    
    def _extract_pose_from_frame(self, source_obj, source_frame: int,
                                  target_obj, target_frame: int) -> bool:
        """Extrai a pose de um frame específico usando operadores nativos"""
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
    
    # ======================== THUMBNAIL PARA UI ========================
    def get_thumbnail_icon(self, pose_id: str, library_name: str, frame_number: int) -> str:
        """Retorna a chave do ícone para usar na UI"""
        if not self.thumbnails_path:
            return None
        
        pose = self.poses.get(pose_id)
        if not pose or not pose.thumbnail_path:
            return None
        
        thumb_path = self.project_path / pose.thumbnail_path
        
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
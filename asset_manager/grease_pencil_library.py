"""
Módulo de Biblioteca Grease Pencil - Versão com Bibliotecas Portáveis
Suporte a múltiplas poses por arquivo .blend
"""

import bpy
import json
import uuid
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import os

# ===========================================================================
# CONFIGURAÇÕES
# ===========================================================================
GP_LIBRARY_CONFIG = {
    'libraries_folder': 'grease_pencil/libraries',
    'thumbnails_folder': 'grease_pencil/thumbnails',
    'index_filename': 'gp_library_index.json',
    'thumbnail_size': (256, 256),
}

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


class GPLibrary:
    """Gerenciador principal da biblioteca de poses"""
    
    def __init__(self):
        self.project_path = self._find_project_path()
        self.libraries_path = None
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
    
    # ======================== SALVAR BIBLIOTECA ========================
    def save_library(self, library_name: str, description: str = "", 
                     frames: List[int] = None, overwrite: bool = False) -> Tuple[bool, str]:
        """
        Salva o objeto Grease Pencil selecionado como uma biblioteca
        Pode salvar múltiplos frames como poses separadas
        
        Args:
            library_name: Nome da biblioteca (ex: "mao_animations")
            description: Descrição da biblioteca
            frames: Lista de frames para salvar (None = todos os frames do objeto)
            overwrite: Sobrescrever biblioteca existente?
        """
        # Verificar objeto selecionado
        if not bpy.context.active_object or bpy.context.active_object.type != 'GREASEPENCIL':
            return False, "Selecione um objeto Grease Pencil"
        
        gp_object = bpy.context.active_object
        library_filename = f"{library_name}.blend"
        library_path = self.libraries_path / library_filename
        
        # Verificar se já existe
        if library_path.exists() and not overwrite:
            return False, f"Biblioteca '{library_name}' já existe. Use overwrite=True para substituir."
        
        # Determinar quais frames salvar
        if frames is None:
                frames_set = set()
                for layer in gp_object.data.layers:
                    for frame in layer.frames:
                        frames_set.add(frame.frame_number)
                frames = sorted(list(frames_set))
        
        print(f"📊 Frames encontrados: {frames}")

        if not frames:
            return False, "Nenhum frame encontrado no objeto Grease Pencil"
        
        try:
            # Salvar o objeto inteiro como biblioteca .blend
            success = self._save_blend_library(library_path, gp_object, frames)
            if not success:
                return False, "Erro ao salvar arquivo da biblioteca"
            
            # Registrar biblioteca no índice
            self.libraries[library_name] = {
                'filename': library_filename,
                'path': str(library_path.relative_to(self.project_path)),
                'description': description,
                'frames': frames,
                'created': datetime.now().isoformat(),
                'modified': datetime.now().isoformat(),
                'object_name': gp_object.name
            }
            
            # Criar poses para cada frame
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
                
                # Gerar thumbnail para este frame
                thumbnail_filename = f"{pose_id}.png"
                thumbnail_path = self.thumbnails_path / thumbnail_filename
                self._generate_thumbnail_from_library(library_path, frame_number, thumbnail_path)
                pose.thumbnail_path = str(thumbnail_path.relative_to(self.project_path)) if thumbnail_path.exists() else ""
                
                self.poses[pose_id] = pose
            
            # Salvar índice
            self._save_index()
            
            return True, f"✅ Biblioteca '{library_name}' salva com {len(frames)} poses!"
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"Erro ao salvar biblioteca: {str(e)}"

    def _save_blend_library(self, library_path: Path, gp_object, frames: List[int]) -> bool:
        """Salva o objeto Grease Pencil como biblioteca .blend - VERSÃO CORRIGIDA"""
        try:
            # IMPORTANTE: Salvar usando bpy.ops.wm.save_as_mainfile para biblioteca temporária
            # Este método garante que todos os dados do Grease Pencil sejam salvos
            
            # Guardar estado atual
            current_filepath = bpy.data.filepath
            current_scene = bpy.context.scene.name
            
            # Criar um arquivo .blend temporário apenas com o objeto Grease Pencil
            temp_blend = library_path.parent / f"temp_{library_path.name}"
            
            # Criar uma cena temporária com apenas o objeto necessário
            temp_scene = bpy.data.scenes.new("temp_save_scene")
            
            # Guardar referência original
            original_collection = gp_object.users_collection[0] if gp_object.users_collection else None
            
            # Mover objeto para cena temporária
            if original_collection:
                original_collection.objects.unlink(gp_object)
            temp_scene.collection.objects.link(gp_object)
            
            # Tornar a cena temporária ativa
            bpy.context.window.scene = temp_scene
            
            # Salvar o arquivo .blend com apenas a cena temporária
            try:
                # Método 1: Usar save_as_mainfile para garantir que tudo seja salvo
                bpy.ops.wm.save_as_mainfile(
                    filepath=str(temp_blend),
                    copy=True,  # Copiar, não mover
                    relative_remap=False
                )
                
                # Verificar se o arquivo foi criado
                if temp_blend.exists():
                    # Copiar para o destino final
                    import shutil
                    shutil.copy2(temp_blend, library_path)
                    print(f"✅ Biblioteca salva via save_as_mainfile: {library_path}")
                    success = True
                else:
                    success = False
                    
            except Exception as e:
                print(f"⚠️ Erro no save_as_mainfile: {e}")
                success = False
            
            # Restaurar estado
            if original_collection:
                temp_scene.collection.objects.unlink(gp_object)
                original_collection.objects.link(gp_object)
            
            # Remover cena temporária
            bpy.data.scenes.remove(temp_scene)
            
            # Restaurar cena original
            if current_filepath:
                bpy.ops.wm.open_mainfile(filepath=current_filepath)
            
            if success:
                return True
            
            # MÉTODO 2: Fallback - Salvar usando libraries.write com todos os data blocks
            print("Tentando método alternativo de salvamento...")
            
            # Coletar TODOS os data blocks relacionados
            data_blocks = set()
            
            # Objeto e seus dados
            data_blocks.add(gp_object)
            data_blocks.add(gp_object.data)
            
            # Materiais e texturas
            for slot in gp_object.material_slots:
                if slot.material:
                    data_blocks.add(slot.material)
                    if hasattr(slot.material, 'node_tree') and slot.material.node_tree:
                        data_blocks.add(slot.material.node_tree)
            
            # Paletas de cores
            if hasattr(gp_object.data, 'palettes'):
                for palette in gp_object.data.palettes:
                    data_blocks.add(palette)
            
            # Brushes (se houver referência)
            for brush in bpy.data.brushes:
                if brush.grease_pencil:
                    data_blocks.add(brush)
            
            # Materiais do Grease Pencil (v3)
            if hasattr(gp_object.data, 'materials'):
                for material in gp_object.data.materials:
                    if material:
                        data_blocks.add(material)
            
            # Camadas de pintura (se houver)
            if hasattr(gp_object.data, 'layers'):
                for layer in gp_object.data.layers:
                    # Adicionar informações da layer (algumas podem ser data blocks)
                    if hasattr(layer, 'mask_layer') and layer.mask_layer:
                        data_blocks.add(layer.mask_layer)
            
            # Salvar usando libraries.write
            bpy.data.libraries.write(str(library_path), data_blocks, 
                                    fake_user=True, compress=True, 
                                    relative_remap=False)
            
            # Verificar se o arquivo foi criado e tem tamanho > 0
            if library_path.exists() and library_path.stat().st_size > 1000:  # > 1KB
                print(f"✅ Biblioteca salva via libraries.write: {library_path}")
                return True
            else:
                print(f"❌ Arquivo salvo está vazio ou muito pequeno")
                return False
            
        except Exception as e:
            print(f"❌ Erro ao salvar biblioteca: {e}")
            import traceback
            traceback.print_exc()
            return False

    # ======================== APLICAR POSE DA BIBLIOTECA ========================
    def apply_pose_from_library(self, target_object, pose_id: str) -> Tuple[bool, str]:
        """
        Aplica uma pose específica da biblioteca ao objeto alvo
        Mantém as outras layers/frames intactos
        """
        if not target_object or target_object.type != 'GREASEPENCIL':
            return False, "Objeto alvo deve ser Grease Pencil"
        
        pose = self.poses.get(pose_id)
        if not pose:
            return False, "Pose não encontrada"
        
        library_path = self.project_path / pose.library_path
        if not library_path.exists():
            return False, f"Arquivo da biblioteca não encontrado: {library_path}"
        
        try:
            # Carregar biblioteca temporariamente
            with bpy.data.libraries.load(str(library_path), link=False, relative=False) as (data_from, data_to):
                data_to.objects = data_from.objects[:]
            
            # Encontrar objeto carregado
            loaded_obj = next((obj for obj in bpy.data.objects if obj.name in data_from.objects), None)
            if not loaded_obj:
                return False, "Não foi possível carregar a biblioteca"
            
            current_frame = bpy.context.scene.frame_current
            
            # Extrair a pose do frame específico
            success = self._extract_pose_from_frame(loaded_obj, pose.frame_number, target_object, current_frame)
            
            # Limpar objeto temporário
            bpy.data.objects.remove(loaded_obj, do_unlink=True)
            
            if success:
                return True, f"✅ Pose '{pose.name}' aplicada no frame {current_frame}"
            else:
                return False, "Erro ao extrair pose da biblioteca"
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"Erro ao aplicar pose: {str(e)}"

    def _extract_pose_from_frame(self, source_obj, source_frame: int,
                                target_obj, target_frame: int) -> bool:
        """
        Extrai a pose de um frame específico - Versão corrigida para Blender 5.0
        """
        try:
            # 🔥 DEBUG: Mostrar qual frame estamos tentando extrair
            print(f"🎯 Extraindo pose do frame {source_frame} para o frame {target_frame}")
            
            # Garantir que os objetos estão na view layer
            def ensure_in_view_layer(obj):
                if obj is None:
                    return False
                if obj.name not in bpy.context.view_layer.objects:
                    bpy.context.scene.collection.objects.link(obj)
                    bpy.context.view_layer.update()
                return obj.name in bpy.context.view_layer.objects
            
            ensure_in_view_layer(source_obj)
            ensure_in_view_layer(target_obj)
            
            # Guardar estado original
            original_active = bpy.context.view_layer.objects.active
            original_selected = [obj for obj in bpy.context.selected_objects if obj]
            original_frame = bpy.context.scene.frame_current
            original_mode = bpy.context.mode
            
            # ==================== VERIFICAR SE O FRAME EXISTE ====================
            frame_exists = False
            for layer in source_obj.data.layers:
                for frame in layer.frames:
                    if frame.frame_number == source_frame:
                        frame_exists = True
                        print(f"  ✅ Frame {source_frame} encontrado na layer {layer.name}")
                        break
                if frame_exists:
                    break
            
            if not frame_exists:
                print(f"  ❌ Frame {source_frame} NÃO encontrado no objeto fonte!")
                available_frames = set()
                for layer in source_obj.data.layers:
                    for frame in layer.frames:
                        available_frames.add(frame.frame_number)
                print(f"  📊 Frames disponíveis: {sorted(available_frames)}")
                return False
            
            # ==================== COPIAR DA FONTE ====================
            # Sair do modo EDIT se necessário
            if bpy.context.mode == 'EDIT':
                bpy.ops.object.mode_set(mode='OBJECT')
            
            # Deselecionar tudo
            bpy.ops.object.select_all(action='DESELECT')
            
            # Selecionar fonte
            source_obj.select_set(True)
            bpy.context.view_layer.objects.active = source_obj
            
            # Ir para o frame da fonte
            bpy.context.scene.frame_set(source_frame)
            
            # Entrar em modo EDIT
            bpy.ops.object.mode_set(mode='EDIT')
            
            # Selecionar todos os strokes e copiar
            if bpy.app.version >= (4, 3, 0):
                bpy.ops.grease_pencil.select_all(action='SELECT')
                bpy.ops.grease_pencil.copy()
            else:
                bpy.ops.gpencil.select_all(action='SELECT')
                bpy.ops.gpencil.copy()
            
            # ==================== COLAR NO ALVO ====================
            # Voltar para OBJECT
            bpy.ops.object.mode_set(mode='OBJECT')
            
            # Deselecionar tudo
            bpy.ops.object.select_all(action='DESELECT')
            
            # Selecionar alvo
            target_obj.select_set(True)
            bpy.context.view_layer.objects.active = target_obj
            
            # Ir para o frame alvo
            bpy.context.scene.frame_set(target_frame)
            
            # Entrar em modo EDIT
            bpy.ops.object.mode_set(mode='EDIT')
            
            # Limpar frame atual
            if bpy.app.version >= (4, 3, 0):
                bpy.ops.grease_pencil.select_all(action='SELECT')
                bpy.ops.grease_pencil.delete()
            else:
                bpy.ops.gpencil.select_all(action='SELECT')
                bpy.ops.gpencil.delete(type='STROKES')
            
            # Colar
            if bpy.app.version >= (4, 3, 0):
                bpy.ops.grease_pencil.paste()
            else:
                bpy.ops.gpencil.paste()
            
            # ==================== RESTAURAR ESTADO ====================
            bpy.ops.object.mode_set(mode='OBJECT')
            
            # Restaurar seleção
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
            
            # Restaurar modo
            if original_mode == 'EDIT':
                try:
                    bpy.ops.object.mode_set(mode='EDIT')
                except:
                    pass
            
            print(f"  ✅ Pose do frame {source_frame} aplicada com sucesso!")
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

    # ======================== IMPORTAR BIBLIOTECA EXTERNA ========================
    def import_library(self, external_blend_path: str, library_name: str = None) -> Tuple[bool, str]:
        """
        Importa uma biblioteca externa (.blend) para o projeto atual
        Permite reutilizar bibliotecas entre projetos
        
        Args:
            external_blend_path: Caminho do arquivo .blend externo
            library_name: Nome para a biblioteca (se None, usa nome do arquivo)
        """
        source_path = Path(external_blend_path)
        if not source_path.exists():
            return False, "Arquivo não encontrado"
        
        if source_path.suffix.lower() != '.blend':
            return False, "O arquivo deve ser .blend"
        
        # Gerar nome da biblioteca
        if not library_name:
            library_name = source_path.stem
        
        # Verificar se já existe
        dest_path = self.libraries_path / f"{library_name}.blend"
        if dest_path.exists():
            return False, f"Biblioteca '{library_name}' já existe no projeto"
        
        try:
            # Copiar arquivo
            shutil.copy2(source_path, dest_path)
            
            # Analisar biblioteca para extrair informações das poses
            frames_info = self._analyze_library_frames(dest_path)
            
            # Registrar no índice
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
            
            # Criar poses para cada frame
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
                
                # Gerar thumbnail
                thumbnail_filename = f"{pose_id}.png"
                thumbnail_path = self.thumbnails_path / thumbnail_filename
                self._generate_thumbnail_from_library(dest_path, frame_number, thumbnail_path)
                pose.thumbnail_path = str(thumbnail_path.relative_to(self.project_path)) if thumbnail_path.exists() else ""
                
                self.poses[pose_id] = pose
            
            # Salvar índice
            self._save_index()
            
            return True, f"✅ Biblioteca '{library_name}' importada com {len(frames_info['frames'])} poses!"
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"Erro ao importar biblioteca: {str(e)}"
    
    def _analyze_library_frames(self, library_path: Path) -> Dict:
        """Analisa um arquivo .blend para extrair frames - Versão melhorada"""
        frames_info = {'frames': [], 'object_name': None}
        
        # Salvar estado atual
        current_filepath = bpy.data.filepath
        
        try:
            # Abrir a biblioteca temporariamente
            bpy.ops.wm.open_mainfile(filepath=str(library_path))
            
            # Encontrar objeto Grease Pencil
            for obj in bpy.data.objects:
                if obj.type == 'GREASEPENCIL':
                    frames_info['object_name'] = obj.name
                    
                    # 🔥 COLETAR TODOS OS FRAMES
                    frames_set = set()
                    for layer in obj.data.layers:
                        for frame in layer.frames:
                            frames_set.add(frame.frame_number)
                    
                    frames_info['frames'] = sorted(list(frames_set))
                    print(f"📊 Biblioteca '{library_path.stem}': frames encontrados = {frames_info['frames']}")
                    break
            
            # Se não encontrou frames, usar frame 1 como fallback
            if not frames_info['frames']:
                print(f"⚠️ Nenhum frame encontrado, usando frame 1 como fallback")
                frames_info['frames'] = [1]
                
        except Exception as e:
            print(f"Erro ao analisar biblioteca: {e}")
            frames_info['frames'] = [1]
        
        finally:
            # Voltar ao arquivo original
            if current_filepath:
                try:
                    bpy.ops.wm.open_mainfile(filepath=current_filepath)
                except:
                    pass
        
        return frames_info

    def _generate_thumbnail_from_library(self, library_path: Path, frame_number: int, output_path: Path):
        """Gera thumbnail de um frame específico da biblioteca"""
        try:
            # Carregar biblioteca temporariamente
            with bpy.data.libraries.load(str(library_path), link=False) as (data_from, data_to):
                if data_from.objects:
                    data_to.objects = data_from.objects[:1]
            
            if not data_to.objects:
                return
            
            temp_obj = data_to.objects[0]
            if not temp_obj or temp_obj.type != 'GREASEPENCIL':
                return
            
            # Criar cena temporária para renderizar
            temp_scene = bpy.data.scenes.new("temp_thumb")
            temp_scene.render.engine = 'BLENDER_EEVEE'
            temp_scene.render.resolution_x = GP_LIBRARY_CONFIG['thumbnail_size'][0]
            temp_scene.render.resolution_y = GP_LIBRARY_CONFIG['thumbnail_size'][1]
            temp_scene.render.image_settings.file_format = 'PNG'
            temp_scene.render.film_transparent = True
            
            # Configurar câmera
            bpy.ops.object.camera_add(location=(0, -5, 0))
            temp_cam = bpy.context.active_object
            temp_cam.rotation_euler = (3.14159/2, 0, 0)
            temp_scene.camera = temp_cam
            
            # Adicionar objeto à cena
            temp_scene.collection.objects.link(temp_obj)
            
            # Definir frame atual
            temp_scene.frame_set(frame_number)
            
            # Renderizar
            temp_scene.render.filepath = str(output_path)
            bpy.ops.render.render(write_still=True, scene=temp_scene.name)
            
            # Limpar
            bpy.data.scenes.remove(temp_scene)
            bpy.data.objects.remove(temp_cam, do_unlink=True)
            bpy.data.objects.remove(temp_obj, do_unlink=True)
            
        except Exception as e:
            print(f"⚠️ Erro ao gerar thumbnail: {e}")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.touch()
    
    # ======================== UTILITÁRIOS ========================
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
                # Remover thumbnail
                pose = self.poses[pid]
                if pose.thumbnail_path:
                    thumb_path = self.project_path / pose.thumbnail_path
                    thumb_path.unlink(missing_ok=True)
                del self.poses[pid]
            
            # Remover do índice
            del self.libraries[library_name]
            
            # Salvar índice
            self._save_index()
            
            return True, f"✅ Biblioteca '{library_name}' removida"
            
        except Exception as e:
            return False, f"Erro ao remover biblioteca: {str(e)}"
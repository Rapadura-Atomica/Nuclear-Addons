# grease_pencil_library.py
"""
Módulo de Biblioteca Grease Pencil para Asset Manager Pro
Implementa o sistema de drawing substitution para animadores
"""

import bpy
import os
import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import math
import shutil
import tempfile

# ===========================================================================
# CONFIGURAÇÕES GREASE PENCIL
# ===========================================================================
GP_LIBRARY_CONFIG = {
    'library_filename': 'gp_library.json',
    'drawings_folder': 'grease_pencil/drawings',
    'previews_folder': 'grease_pencil/previews',
    'thumbnail_size': (256, 256),
    'thumbnail_quality': 90
}

GP_POSE_CATEGORIES = [
    'hands', 'mouths', 'eyes', 'eyebrows', 'head', 'body',
    'props', 'expressions', 'custom'
]


# ===========================================================================
# ESTRUTURA DE DADOS
# ===========================================================================
class GPPoseData:
    """Representa uma pose/desenho na biblioteca"""
    def __init__(self):
        self.id = ""
        self.name = ""
        self.category = "custom"
        self.tags = []
        self.blend_path = ""
        self.data_block_name = ""
        self.thumbnail_path = ""
        self.vertex_groups = []
        self.layers = []
        self.created = ""
        self.modified = ""
        self.description = ""
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'category': self.category,
            'tags': self.tags,
            'blend_path': self.blend_path,
            'data_block_name': self.data_block_name,
            'thumbnail_path': self.thumbnail_path,
            'vertex_groups': self.vertex_groups,
            'layers': self.layers,
            'created': self.created,
            'modified': self.modified,
            'description': self.description
        }
    
    def from_dict(self, data):
        self.id = data.get('id', '')
        self.name = data.get('name', '')
        self.category = data.get('category', 'custom')
        self.tags = data.get('tags', [])
        self.blend_path = data.get('blend_path', '')
        self.data_block_name = data.get('data_block_name', '')
        self.thumbnail_path = data.get('thumbnail_path', '')
        self.vertex_groups = data.get('vertex_groups', [])
        self.layers = data.get('layers', [])
        self.created = data.get('created', '')
        self.modified = data.get('modified', '')
        self.description = data.get('description', '')
        return self


class GPLibrary:
    """Gerencia a biblioteca de poses Grease Pencil"""
    
    def __init__(self):
        self.project_path = self._find_project_path()
        self.library_path = None
        self.master_json_path = None
        self.poses = {}  # id -> GPPoseData (sempre objeto!)
        
        if self.project_path:
            self._setup_paths()
            self._load_master_json()
    
    def _find_project_path(self) -> Optional[Path]:
        if not bpy.data.filepath:
            return None
        current = Path(bpy.data.filepath).parent.resolve()
        for parent in [current] + list(current.parents):
            if (parent / "project_config.json").exists():
                return parent
        return None
    
    def _setup_paths(self):
        assets_dir = self.project_path / "assets"
        self.library_path = assets_dir / "grease_pencil"
        self.master_json_path = self.library_path / GP_LIBRARY_CONFIG['library_filename']
        
        self.library_path.mkdir(parents=True, exist_ok=True)
        (self.library_path / "drawings").mkdir(exist_ok=True)
        (self.library_path / "previews").mkdir(exist_ok=True)
    
    def _load_master_json(self):
        self.poses.clear()
        if not self.master_json_path or not self.master_json_path.exists():
            return
        
        try:
            with open(self.master_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for pose_id, pose_data in data.get('poses', {}).items():
                pose = GPPoseData().from_dict(pose_data)
                self.poses[pose_id] = pose
        except Exception as e:
            print(f"Erro ao carregar GP Library JSON: {e}")
    
    def _save_master_json(self):
        if not self.master_json_path:
            return
        
        data = {
            'version': '1.0',
            'project': self.project_path.name if self.project_path else '',
            'updated': datetime.now().isoformat(),
            'poses': {pose_id: pose.to_dict() for pose_id, pose in self.poses.items()}
        }
        
        try:
            with open(self.master_json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Erro ao salvar GP Library JSON: {e}")
    
    def add_pose_from_current(self, name: str, category: str = 'custom', 
                            tags: List[str] = None, description: str = ""):
        """Salva o Grease Pencil selecionado como uma nova pose"""
        
        if not bpy.context.active_object or bpy.context.active_object.type != 'GREASEPENCIL':
            return False, "Selecione um objeto Grease Pencil", None
        
        gp_object = bpy.context.active_object
        gp_data = gp_object.data
        
        pose_id = str(uuid.uuid4())
        
        # Coletar informações
        vertex_groups = [vg.name for vg in gp_object.vertex_groups]
        layers = [layer.name for layer in gp_data.layers]
        
        # Salvar arquivo .blend da pose
        blend_filename = f"{pose_id}.blend"
        blend_path = self.library_path / "drawings" / blend_filename
        
        success = self._save_pose_blend(blend_path, gp_object)
        if not success:
            return False, "Erro ao salvar arquivo da pose", None
        
        # Gerar thumbnail
        thumbnail_filename = f"{pose_id}.png"
        thumbnail_path = self.library_path / "previews" / thumbnail_filename
        self._generate_thumbnail(gp_object, thumbnail_path)
        
        # Criar objeto GPPoseData (sempre objeto, nunca dict!)
        pose = GPPoseData()
        pose.id = pose_id
        pose.name = name
        pose.category = category
        pose.tags = tags or []
        pose.blend_path = str(blend_path.relative_to(self.project_path))
        pose.data_block_name = gp_data.name
        pose.thumbnail_path = str(thumbnail_path.relative_to(self.project_path)) if thumbnail_path.exists() else ""
        pose.vertex_groups = vertex_groups
        pose.layers = layers
        pose.created = datetime.now().isoformat()
        pose.modified = datetime.now().isoformat()
        pose.description = description
        
        self.poses[pose_id] = pose
        self._save_master_json()
        
        return True, f"Pose '{name}' adicionada à biblioteca", pose_id

    def _save_pose_blend(self, blend_path: Path, gp_object):
        """Salva APENAS o Grease Pencil selecionado em um .blend separado"""
        try:
            if gp_object.type != 'GREASEPENCIL':
                print(f"Erro: Objeto {gp_object.name} não é Grease Pencil")
                return False
            
            data_blocks = set()
            data_blocks.add(gp_object)           # objeto
            data_blocks.add(gp_object.data)      # grease pencil data
            
            # Materiais
            for slot in gp_object.material_slots:
                if slot.material:
                    data_blocks.add(slot.material)
            
            # Paletas e brushes
            for palette in bpy.data.palettes:
                data_blocks.add(palette)
            for brush in bpy.data.brushes:
                if brush.grease_pencil:
                    data_blocks.add(brush)
            
            bpy.data.libraries.write(str(blend_path), data_blocks)
            
            print(f"✅ Pose salva: {blend_path}")
            return True
            
        except Exception as e:
            print(f"❌ Erro ao salvar pose blend: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _generate_thumbnail(self, gp_object, thumbnail_path: Path):
        """Gera thumbnail de forma mais robusta (sem depender do PIL)"""
        try:
            # Código simplificado e seguro
            temp_scene = bpy.data.scenes.new("temp_thumb")
            temp_scene.render.engine = 'BLENDER_EEVEE'
            temp_scene.render.resolution_x = GP_LIBRARY_CONFIG['thumbnail_size'][0]
            temp_scene.render.resolution_y = GP_LIBRARY_CONFIG['thumbnail_size'][1]
            temp_scene.render.image_settings.file_format = 'PNG'
            temp_scene.render.film_transparent = True
            
            # Copiar objeto
            temp_gp = gp_object.copy()
            temp_gp.data = gp_object.data.copy()
            temp_scene.collection.objects.link(temp_gp)
            
            # Câmera simples
            bpy.ops.object.camera_add(location=(0, -5, 0))
            temp_cam = bpy.context.active_object
            temp_cam.rotation_euler = (math.radians(90), 0, 0)
            temp_scene.camera = temp_cam
            
            temp_scene.render.filepath = str(thumbnail_path)
            bpy.ops.render.render(write_still=True, scene=temp_scene.name)
            
            # Limpeza
            bpy.data.scenes.remove(temp_scene)
            bpy.data.objects.remove(temp_gp)
            bpy.data.objects.remove(temp_cam)
            
            print(f"✅ Thumbnail gerado: {thumbnail_path.name}")
            
        except Exception as e:
            print(f"⚠️ Não foi possível gerar thumbnail: {e}")
            # Cria um arquivo vazio só para não quebrar
            thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
            thumbnail_path.touch()

    # ======================== MÉTODOS JÁ EXISTENTES ========================
    def get_poses_by_category(self, category: str = None):
        if not category:
            return list(self.poses.values())
        return [pose for pose in self.poses.values() if pose.category == category]
    
    def get_categories_with_poses(self) -> Dict[str, int]:
        categories = {}
        for pose in self.poses.values():
            categories[pose.category] = categories.get(pose.category, 0) + 1
        return categories
    
    def swap_pose(self, target_object, pose_id: str):
        # TODO (futuro): implementar substituição real da pose
        return True, f"Pose aplicada (em breve)"
    
    def delete_pose(self, pose_id: str):
        if pose_id not in self.poses:
            return False, "Pose não encontrada"
        
        pose = self.poses[pose_id]
        try:
            (self.project_path / pose.blend_path).unlink(missing_ok=True)
            (self.project_path / pose.thumbnail_path).unlink(missing_ok=True)
        except Exception as e:
            print(f"Erro ao remover arquivos: {e}")
        
        del self.poses[pose_id]
        self._save_master_json()
        return True, f"Pose '{pose.name}' removida"
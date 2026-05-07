# __init__.py
bl_info = {
    "name": "Asset Manager Pro",
    "author": "Rapadura Atômica LTDA",
    "version": (2, 1, 4),
    "blender": (5, 0, 0),
    "location": "View3D > N-Panel > Asset Pro | File > Import",
    "description": "Gerenciador de assets com pastas + integração Asset Browser + catálogos inteligentes",
    "category": "System",
}

import bpy
import os
import shutil
import time
from pathlib import Path
import json
import uuid
from mathutils import Vector
import math
from bpy.props import StringProperty, BoolProperty
from bpy_extras.io_utils import ImportHelper
from bpy.app.handlers import persistent
from .grease_pencil_ui import register_properties, unregister_properties

from .grease_pencil_operators import (
    GP_OT_save_library,
    GP_OT_import_library,
    GP_OT_refresh_library,
    GP_OT_apply_pose,
    GP_OT_delete_library,
    GP_OT_generate_all_thumbs,
    GP_OT_clear_thumbnails,
    GP_OT_generate_thumbnail, 
)
from .grease_pencil_ui import (
    GP_PT_library_panel,
    GP_PT_library_settings
)

# ===========================================================================
# CONFIGURAÇÕES
# ===========================================================================
ASSET_CATEGORIES = {
    'textures': ['.jpg', '.jpeg', '.png', '.tga', '.tiff', '.bmp', '.exr', '.hdr'],
    'images': ['.jpg', '.jpeg', '.png', '.tga', '.tiff', '.bmp'],
    'hdris': ['.hdr', '.exr'],
    'videos': ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv'],
    'audio': ['.wav', '.mp3', '.ogg', '.flac', '.aac'],
    'models': ['.fbx', '.obj', '.stl', '.gltf', '.glb', '.dae', '.3ds', '.blend'],
    'scripts': ['.py', '.json', '.xml', '.txt'],
    'fonts': ['.ttf', '.otf', '.woff', '.woff2'],
    'misc': []
}
CATALOG_MAP = {cat: cat.capitalize() for cat in ASSET_CATEGORIES}

# ===========================================================================
# FUNÇÕES AUXILIARES
# ===========================================================================
def find_project_path(context=None):
    if context is None:
        context = bpy.context
    if not context.scene or not bpy.data.filepath:
        return None
    current = Path(bpy.data.filepath).parent.resolve()
    for parent in [current] + list(current.parents):
        config_path = parent / "project_config.json"
        if config_path.exists():
            return parent
    return None

def register_asset_library(context=None):
    if context is None:
        context = bpy.context
    project_path = find_project_path(context)
    if not project_path:
        return
    assets_dir = project_path / "assets"
    if not assets_dir.exists():
        return
    lib_name = f"{project_path.name} Assets"
    prefs = context.preferences.filepaths
    libs = prefs.asset_libraries
    for lib in libs:
        if lib.name == lib_name and str(lib.path) == str(assets_dir):
            return
    try:
        new_lib = libs.new(name=lib_name, directory=str(assets_dir))
        # CORREÇÃO: Usar 'APPEND' em vez de 'APPEND_REUSE' no Blender 5.0
        new_lib.import_method = 'APPEND'  # Mudado de 'APPEND_REUSE'
        print(f"Asset Library registrada: {lib_name} → {assets_dir}")
    except Exception as e:
        print(f"Erro ao registrar library: {e}") 

def create_catalog_definition(project_path):
    assets_dir = project_path / "assets"
    cdf_path = assets_dir / "blender_assets.cdf"
    if cdf_path.exists():
        with open(cdf_path, 'r') as f:
            lines = f.readlines()
    else:
        lines = ["VERSION 1\n"]
    existing_catalogs = {line.split(':')[1].strip() for line in lines if ':' in line}
    for cat_name in CATALOG_MAP.values():
        if cat_name not in existing_catalogs:
            catalog_uuid = str(uuid.uuid4())
            lines.append(f"{catalog_uuid}:{cat_name}:{cat_name}\n")
    with open(cdf_path, 'w') as f:
        f.writelines(lines)
    print(f"Catálogos atualizados em: {cdf_path}")

@persistent
def load_handler(dummy):
    project = find_project_path()
    if project:
        create_catalog_definition(project)
    register_asset_library()

def add_image_as_empty(context, abs_path: str, name_prefix="Ref_"):
    scene = context.scene
    
    # Garantir contexto VIEW_3D (essencial para empty_image_add)
    override = None
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            for region in area.regions:
                if region.type == 'WINDOW':
                    override = context.temp_override(area=area, region=region)
                    break
            if override:
                break
    
    with override or context.temp_override():
        bpy.ops.object.empty_image_add(filepath=abs_path, location=(0, 0, 0))
    
    empty = context.active_object
    
    # Verificação de segurança
    if not empty or empty.type != 'EMPTY' or empty.empty_display_type != 'IMAGE':
        print(f"ERRO: Não foi possível criar Empty Image válido para {abs_path}")
        print("Verifique se o arquivo existe e se o formato é suportado (png, jpg, etc.)")
        return None
    
    empty.name = f"{name_prefix}{Path(abs_path).stem}"
    empty.empty_display_type = 'IMAGE'
    empty.empty_image_side = 'FRONT'
        
    if scene.camera:
        cam = scene.camera
        cam_matrix = cam.matrix_world
        cam_forward = (cam_matrix @ Vector((0, 0, -1))) - cam.location
        cam_forward.normalize()
        
        # Posiciona o Empty na frente da câmera
        empty.location = cam.location + (cam_forward * 5.0)
        
        # Direction do Empty para a câmera (oposto do forward da câmera)
        direction = cam.location - empty.location
        direction.normalize()
        
        empty.rotation_euler = (math.radians(90), 0, 0)
        
    else:
        # Sem câmera: posiciona olhando para -Y global (frente padrão)
        empty.location = (0, -5, 0)  # um pouco à frente no -Y
        empty.rotation_euler = (math.radians(90), 0, 0)  # plano XY, olhando -Y
    
    print(f"Imagem de referência adicionada como Empty: {empty.name} (voltada para -Y)")
    return empty

# ===========================================================================
# OPERADORES
# ===========================================================================
class ASSETMANAGER_OT_first_save(bpy.types.Operator, ImportHelper):
    bl_idname = "assetmanager.first_save"
    bl_label = "Primeiro Salvamento"
    bl_options = {'REGISTER', 'UNDO'}
    directory: StringProperty(subtype='DIR_PATH') #type: ignore
    project_name: StringProperty(default="MeuProjeto") #type: ignore

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        base_path = Path(self.directory) / self.project_name
        base_path.mkdir(parents=True, exist_ok=True)
        folders = [
            base_path / "assets" / cat for cat in ASSET_CATEGORIES
        ] + [
            base_path / "blend_files",
            base_path / "renders" / "frames",
            base_path / "renders" / "composited",
            base_path / "exports" / "fbx",
            base_path / "exports" / "obj",
            base_path / "exports" / "gltf",
            base_path / "references",
            base_path / "docs"
        ]
        for f in folders:
            f.mkdir(parents=True, exist_ok=True)
        config = {
            "project_name": self.project_name,
            "project_path": str(base_path),
            "created": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        with open(base_path / "project_config.json", 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        blend_file = base_path / "blend_files" / f"{self.project_name}.blend"
        if bpy.data.filepath:
            bpy.ops.wm.save_as_mainfile(filepath=str(blend_file))
        else:
            bpy.ops.wm.save_mainfile(filepath=str(blend_file))
        context.scene.render.filepath = "//renders/frames/"
        create_catalog_definition(base_path)
        register_asset_library(context)
        self.report({'INFO'}, f"Projeto criado: {base_path}")
        return {'FINISHED'}

class ASSETMANAGER_OT_import_asset(bpy.types.Operator, ImportHelper):
    bl_idname = "assetmanager.import_asset"
    bl_label = "Importar Asset Organizado"
    filter_glob: StringProperty(default="*.*", options={'HIDDEN'}) #type: ignore
    auto_organize: BoolProperty(name="Organizar Automaticamente", default=True) #type: ignore 
    pack_images: BoolProperty(name="Pack Imagens Após Importar", default=True) #type: ignore

    def execute(self, context):
        source = Path(self.filepath)
        if not source.exists():
            self.report({'ERROR'}, "Arquivo não encontrado")
            return {'CANCELLED'}
        project = find_project_path(context)
        if not project:
            self.report({'WARNING'}, "Execute 'Primeiro Salvamento' antes")
            return {'CANCELLED'}
        create_catalog_definition(project)
        category = 'videos'
        dest_folder = project / "assets" / category
        dest_folder.mkdir(parents=True, exist_ok=True)
        dest = self.unique_path(dest_folder, source.name)
        shutil.copy2(source, dest)
        rel_path = dest.relative_to(project)
        abs_path = str(dest.resolve())
        
        # Empty com imagem (para preview 3D)
        bpy.ops.object.empty_image_add(filepath=abs_path, location=(0, 0, 0))
        empty = context.active_object
        if empty:
            empty.name = f"Animatic_{source.stem}"
            empty.rotation_euler = (math.radians(90), 0, 0)
            if context.scene.camera:
                cam = context.scene.camera
                cam_matrix = cam.matrix_world
                cam_forward = (cam_matrix @ Vector((0, 0, -1))) - cam.location
                cam_forward.normalize()
                empty.location = cam.location + (cam_forward * 3.0)
            else:
                empty.location = (0, -5, 0)
        
        # Import no VSE
        if not context.scene.sequence_editor:
            context.scene.sequence_editor_create()
        strip = context.scene.sequence_editor.sequences.new(
            name=source.stem,
            type='MOVIE',
            filepath=abs_path,
            channel=2,
            frame_start=1
        )
        
        # Ajustar duração da cena
        if strip.frame_final_duration > context.scene.frame_end:
            context.scene.frame_end = strip.frame_final_duration + 50
            self.report({'INFO'}, f"Frame end ajustado para {context.scene.frame_end} frames")
        
        self.report({'INFO'}, f"Animatic importado: //{rel_path}")
        register_asset_library()
        return {'FINISHED'}

    def get_category(self, path):
        ext = path.suffix.lower()
        for cat, exts in ASSET_CATEGORIES.items():
            if ext in exts:
                return cat
        return 'misc'

    def unique_path(self, folder, name):
        path = folder / name
        if not path.exists():
            return path
        stem, ext = path.stem, path.suffix
        i = 1
        while (folder / f"{stem}_{i:03d}{ext}").exists():
            i += 1
        return folder / f"{stem}_{i:03d}{ext}"

    def load_to_blender(self, abs_path: Path, rel_path: Path, context, category: str):
        ext = abs_path.suffix.lower()
        str_abs = str(abs_path)
        catalog_name = CATALOG_MAP.get(category, 'Misc')
        try:
            if ext in ASSET_CATEGORIES['textures'] + ASSET_CATEGORIES['images'] + ASSET_CATEGORIES['hdris']:
                img = bpy.data.images.load(str_abs, check_existing=True)
                img.filepath = bpy.path.relpath(str_abs)
                img.name = abs_path.stem
            elif ext in ASSET_CATEGORIES['videos']:
                if not context.scene.sequence_editor:
                    context.scene.sequence_editor_create()
                
                bpy.ops.sequencer.movie_strip_add(
                    filepath=str_abs,
                    frame_start=1,
                    channel=2
                )
                
                strip = context.scene.sequence_editor.active_strip
                if strip and strip.frame_final_duration > context.scene.frame_end:
                    context.scene.frame_end = strip.frame_final_duration + 50
                    print(f"Frame end ajustado para {context.scene.frame_end}")
            elif ext in ASSET_CATEGORIES['audio']:
                if not context.scene.sequence_editor:
                    context.scene.sequence_editor_create()
                
                bpy.ops.sequencer.sound_strip_add(
                    filepath=str_abs,
                    frame_start=1,
                    channel=1
                )
            elif ext == '.blend':
                with bpy.data.libraries.load(str_abs, link=False) as (data_from, data_to):
                    data_to.objects = data_from.objects
                    data_to.materials = data_from.materials
                    data_to.collections = data_from.collections
                for datatype in [bpy.data.objects, bpy.data.materials, bpy.data.collections]:
                    for item in datatype:
                        if item.library and item.asset_data:
                            item.asset_mark()
                            item.asset_data.catalog_id = self.get_catalog_uuid(catalog_name)
            else:
                self.report({'WARNING'}, f"Tipo não suportado para importação automática: {ext}")
        except Exception as e:
            self.report({'ERROR'}, f"Erro ao carregar {ext.upper()}: {str(e)}")

    def get_catalog_uuid(self, catalog_name: str):
        project = find_project_path()
        if not project:
            return ""
        cdf_path = project / "assets" / "blender_assets.cdf"
        if not cdf_path.exists():
            return ""
        with open(cdf_path, 'r') as f:
            for line in f:
                if ':' in line and line.split(':')[1].strip() == catalog_name:
                    return line.split(':')[0].strip()
        return ""

class ASSETMANAGER_OT_import_animatic(bpy.types.Operator, ImportHelper):
    bl_idname = "assetmanager.import_animatic"
    bl_label = "Importar Animatic"
    bl_options = {'REGISTER', 'UNDO'}
    filename_ext = ".mp4"
    filter_glob: StringProperty(default="*.mp4;*.avi;*.mov;*.mkv;*.webm") #type: ignore

    def execute(self, context):
        source = Path(self.filepath)
        if not source.exists():
            self.report({'ERROR'}, "Arquivo não encontrado")
            return {'CANCELLED'}
        project = find_project_path(context)
        if not project:
            self.report({'WARNING'}, "Execute 'Primeiro Salvamento' antes")
            return {'CANCELLED'}
        create_catalog_definition(project)
        category = 'videos'
        dest_folder = project / "assets" / category
        dest_folder.mkdir(parents=True, exist_ok=True)
        dest = self.unique_path(dest_folder, source.name)
        shutil.copy2(source, dest)
        rel_path = dest.relative_to(project)
        abs_path = str(dest.resolve())
        
        # Empty com imagem (para preview 3D)
        bpy.ops.object.empty_image_add(filepath=abs_path, location=(0, 0, 0))
        empty = context.active_object
        if empty:
            empty.name = f"Animatic_{source.stem}"
            empty.rotation_euler = (math.radians(90), 0, 0)
            if context.scene.camera:
                cam = context.scene.camera
                cam_matrix = cam.matrix_world
                cam_forward = (cam_matrix @ Vector((0, 0, -1))) - cam.location
                cam_forward.normalize()
                empty.location = cam.location + (cam_forward * 3.0)
        
            #Import no VSE
            if not context.scene.sequence_editor:
                context.scene.sequence_editor_create()
            
            # Procura a área do Sequencer para fazer o override
            for window in context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'SEQUENCE_EDITOR':
                        # --- NOVO JEITO ---
                        with context.temp_override(window=window, area=area, screen=window.screen):
                            bpy.ops.sequencer.movie_strip_add(
                                filepath=abs_path,
                                frame_start=1,
                                channel=1,
                                sound=True
                            )
                        break
                else:
                    continue
                break
        
        self.report({'INFO'}, f"Animatic importado: //{rel_path}")
        register_asset_library()
        return {'FINISHED'}

    def unique_path(self, folder, name):
        path = folder / name
        if not path.exists():
            return path
        stem, ext = path.stem, path.suffix
        i = 1
        while (folder / f"{stem}_{i:03d}{ext}").exists():
            i += 1
        return folder / f"{stem}_{i:03d}{ext}"

class ASSETMANAGER_OT_duplicate_project(bpy.types.Operator, ImportHelper):
    bl_idname = "assetmanager.duplicate_project"
    bl_label = "Duplicar Projeto (Save As Novo)"
    bl_options = {'REGISTER'}
    directory: StringProperty(subtype='DIR_PATH') #type: ignore 
    new_project_name: StringProperty(default="Projeto_Copia") #type: ignore 

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        if not bpy.data.filepath:
            self.report({'ERROR'}, "Salve o arquivo atual primeiro!")
            return {'CANCELLED'}
        current_blend = Path(bpy.data.filepath)
        project_path = find_project_path(context)
        if not project_path:
            self.report({'ERROR'}, "Projeto não detectado (project_config.json)")
            return {'CANCELLED'}
        new_base = Path(self.directory) / self.new_project_name
        new_base.mkdir(parents=True, exist_ok=True)
        if project_path != new_base:
            shutil.copytree(project_path, new_base, dirs_exist_ok=True)
        new_blend = new_base / "blend_files" / f"{self.new_project_name}.blend"
        new_blend.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(new_blend))
        config_path = new_base / "project_config.json"
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = json.load(f)
            config["project_name"] = self.new_project_name
            config["project_path"] = str(new_base)
            config["created"] = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
        register_asset_library(context)
        self.report({'INFO'}, f"Projeto duplicado em: {new_base}\nNovo arquivo: {new_blend}")
        return {'FINISHED'}

# ===========================================================================
# UI PANEL
# ===========================================================================
class ASSETMANAGER_PT_main(bpy.types.Panel):
    bl_label = "Asset Manager Pro"
    bl_idname = "ASSETMANAGER_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Asset Pro"

    def draw(self, context):
        layout = self.layout
        project = find_project_path(context)
        if project:
            layout.label(text=f"Projeto: {project.name}", icon='CHECKMARK')
            layout.operator("assetmanager.import_asset", icon='IMPORT', text="Importar Asset Geral")
            layout.operator("assetmanager.import_animatic", icon='FILE_MOVIE', text="Importar Animatic")
            row = layout.row()
            row.operator("assetmanager.duplicate_project", text="Duplicar Projeto", icon='DUPLICATE')
        else:
            layout.operator("assetmanager.first_save", text="Iniciar Projeto", icon='FILE_NEW')

def menu_import(self, context):
    self.layout.separator()
    self.layout.operator("assetmanager.import_asset")

# ===========================================================================
# REGISTER / UNREGISTER
# ===========================================================================
classes = (
    ASSETMANAGER_OT_first_save,
    ASSETMANAGER_OT_import_asset,
    ASSETMANAGER_OT_import_animatic,
    ASSETMANAGER_OT_duplicate_project,
    ASSETMANAGER_PT_main,
    GP_OT_save_library,
    GP_OT_apply_pose,
    GP_OT_import_library,
    GP_OT_refresh_library,
    GP_OT_delete_library,
    GP_OT_generate_all_thumbs,
    GP_OT_clear_thumbnails,
    GP_OT_generate_thumbnail,      # ← ADICIONAR
    GP_PT_library_panel,
    GP_PT_library_settings,
)

# Adicionar propriedades para a UI
def register_properties():
    bpy.types.Scene.gp_current_library = bpy.props.StringProperty(
        name="Current Library",
        description="Currently selected library",
        default=""
    )
    
    bpy.types.Scene.gp_thumb_size = bpy.props.IntProperty(
        name="Thumbnail Size",
        description="Size of thumbnails in gallery",
        default=64,
        min=32,
        max=256,
        step=8
    )
    
    bpy.types.Scene.gp_grid_columns = bpy.props.IntProperty(
        name="Grid Columns",
        description="Number of columns in gallery grid",
        default=4,
        min=2,
        max=8,
        step=1
    )

def unregister_properties():
    del bpy.types.Scene.gp_current_library
    del bpy.types.Scene.gp_thumb_size
    del bpy.types.Scene.gp_grid_columns

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(menu_import)
    bpy.app.handlers.load_post.append(load_handler)
    register_properties()

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    bpy.types.TOPBAR_MT_file_import.remove(menu_import)
    bpy.app.handlers.load_post.remove(load_handler)
    unregister_properties()

if __name__ == "__main__":
    register()
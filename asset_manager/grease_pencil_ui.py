# grease_pencil_ui.py
"""
UI para a biblioteca Grease Pencil - Versão com suporte a thumbnails
"""

import bpy
from .grease_pencil_library import GPLibrary, get_preview_collection, invalidate_library_previews


class GP_PT_library_panel(bpy.types.Panel):
    """Painel principal da biblioteca Grease Pencil - Modo Galeria"""
    bl_label = "GPose Gallery"
    bl_idname = "GP_PT_library_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Asset Pro"
    bl_parent_id = "ASSETMANAGER_PT_main"
    
    def draw(self, context):
        layout = self.layout
        library = GPLibrary()
        
        # ==================== BARRA SUPERIOR ====================
        row = layout.row(align=True)
        
        # Botão Salvar
        op = row.operator("gp.save_library", text="", icon='FILE_BLEND')
        if context.active_object and context.active_object.type == 'GREASEPENCIL':
            op.library_name = context.active_object.name
        
        # Botão Importar
        row.operator("gp.import_library", text="", icon='IMPORT')
        
        # Botão Atualizar
        row.operator("gp.refresh_library", text="", icon='FILE_REFRESH')
        
        # Contador de poses
        row.label(text=f"{len(library.poses)}", icon='GREASEPENCIL')
        
        # Verificar projeto ativo
        if not library.project_path:
            box = layout.box()
            box.label(text="⚠️ No active project", icon='ERROR')
            box.operator("assetmanager.first_save", text="Start Project", icon='FILE_NEW')
            return
        
        # ==================== SELETOR DE BIBLIOTECA ====================
        libraries = library.get_libraries()
        if libraries:
            row = layout.row(align=True)
            row.label(text="Library:", icon='FILE_FOLDER')
            
            lib_names = list(libraries.keys())
            current_lib = getattr(context.scene, 'gp_current_library', lib_names[0] if lib_names else "")
            
            if lib_names:
                row.prop(context.scene, 'gp_current_library', text="")
                
                if current_lib in libraries:
                    lib_info = libraries[current_lib]
                    row = layout.row()
                    row.label(text=f"📚 {current_lib}")
                    frames_count = len(lib_info.get('frames', []))
                    row.label(text=f"Frames: {frames_count}", icon='TIME')
        
        # ==================== GALERIA DE THUMBS ====================
        poses = library.get_poses(library_name=getattr(context.scene, 'gp_current_library', None))
        
        if not poses:
            layout.label(text="No poses in library", icon='INFO')
            layout.label(text="Select a Grease Pencil object and click +")
            return
        
        self.draw_gallery(layout, context, poses)
    
    def draw_gallery(self, layout, context, poses):
        """Desenha a galeria de thumbnails"""
        columns = getattr(context.scene, 'gp_grid_columns', 4)
        
        flow = layout.grid_flow(
            row_major=True, 
            columns=columns, 
            even_columns=True,
            even_rows=False
        )
        
        for pose in poses:
            self.draw_thumbnail(flow, context, pose)
    
    def draw_thumbnail(self, layout, context, pose):
        """Desenha um thumbnail individual"""
        
        box = layout.box()
        library = GPLibrary()
        
        # ===== THUMBNAIL IMAGEM =====
        icon_key = library.get_thumbnail_icon(pose.id, pose.library_name, pose.frame_number)
        
        if icon_key:
            pcoll = get_preview_collection()
            if icon_key in pcoll:
                # Mostrar thumbnail real
                box.template_icon(icon_value=pcoll[icon_key].icon_id, scale=5.0)
            else:
                # Placeholder com botão para gerar
                row = box.row(align=True)
                row.label(text=f"Frame {pose.frame_number:03d}", icon='IMAGE')
                op = row.operator("gp.generate_thumbnail", text="", icon='RENDER_STILL')
                op.pose_id = pose.id
        else:
            # Placeholder com botão para gerar
            row = box.row(align=True)
            row.label(text=f"Frame {pose.frame_number:03d}", icon='IMAGE')
            op = row.operator("gp.generate_thumbnail", text="", icon='RENDER_STILL')
            op.pose_id = pose.id
        
        # ===== INFO E BOTÃO DE APLICAR =====
        row = box.row(align=True)
        row.label(text=f"{pose.frame_number:03d}", icon='TIME')
        
        # Botão de aplicar
        op = row.operator("gp.apply_pose", text="Apply", icon='CHECKMARK')
        op.pose_id = pose.id


class GP_PT_library_settings(bpy.types.Panel):
    """Painel de configurações da biblioteca"""
    bl_label = "Library Settings"
    bl_idname = "GP_PT_library_settings"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Asset Pro"
    bl_parent_id = "ASSETMANAGER_PT_main"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        library = GPLibrary()
        
        # ===== CONFIGURAÇÕES DE EXIBIÇÃO =====
        layout.label(text="Display Settings:", icon='VIEWZOOM')
        
        # Número de colunas
        row = layout.row(align=True)
        row.label(text="Grid Columns:")
        row.prop(context.scene, 'gp_grid_columns', text="")
        
        layout.separator()
        
        # ===== AÇÕES =====
        layout.label(text="Thumbnail Actions:", icon='RENDER_STILL')
        
        # Botão para gerar todos os thumbnails
        row = layout.row(align=True)
        row.operator("gp.generate_all_thumbs", text="Generate All Thumbnails", icon='RENDER_STILL')
        
        # Botão para limpar thumbnails
        row = layout.row(align=True)
        row.operator("gp.clear_thumbnails", text="Clear Thumbnails", icon='X')
        
        layout.separator()
        
        # ===== INFORMAÇÕES =====
        layout.label(text="Library Info:", icon='INFO')
        
        # Número de bibliotecas
        libraries_count = len(library.get_libraries())
        row = layout.row()
        row.label(text=f"Libraries: {libraries_count}")
        
        # Número de poses
        poses_count = len(library.poses)
        row = layout.row()
        row.label(text=f"Total Poses: {poses_count}")
        
        # Caminho do projeto
        if library.project_path:
            row = layout.row()
            row.label(text="Project:", icon='FILE_FOLDER')
            row.label(text=str(library.project_path.name))
        
        layout.separator()
        
        # ===== AVISO =====
        box = layout.box()
        box.label(text="💡 Tips:", icon='INFO')
        box.label(text="• Click 'Apply' to use a pose")
        box.label(text="• Click 📸 to generate thumbnail for a pose")
        box.label(text="• Use 'Generate All' to create all thumbnails")
        box.label(text="• Thumbnails are generated one by one to avoid crashes")


# ===========================================================================
# PROPRIEDADES DA CENA
# ===========================================================================
def register_properties():
    """Registra propriedades para a cena"""
    bpy.types.Scene.gp_current_library = bpy.props.StringProperty(
        name="Current Library",
        description="Currently selected library",
        default=""
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
    """Remove propriedades da cena"""
    if hasattr(bpy.types.Scene, 'gp_current_library'):
        del bpy.types.Scene.gp_current_library
    if hasattr(bpy.types.Scene, 'gp_grid_columns'):
        del bpy.types.Scene.gp_grid_columns
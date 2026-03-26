# grease_pencil_ui.py
"""
UI para a biblioteca Grease Pencil
"""

import bpy
from .grease_pencil_library import GPLibrary


class GP_PT_library_panel(bpy.types.Panel):
    """Painel principal da biblioteca Grease Pencil"""
    bl_label = "GPose Library"
    bl_idname = "GP_PT_library_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Asset Pro"
    bl_parent_id = "ASSETMANAGER_PT_main"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        library = GPLibrary()
        
        # Header com ações
        row = layout.row(align=True)
        row.operator("gp.add_current_to_library", icon='ADD', text="Add Current")
        row.operator("gp.refresh_library", icon='FILE_REFRESH', text="")
        
        if not library.project_path:
            layout.label(text="No active project", icon='ERROR')
            layout.label(text="Use 'Iniciar Projeto' first")
            return
        
        # Estatísticas
        poses_count = len(library.poses)
        if poses_count == 0:
            layout.label(text="No poses in library", icon='INFO')
            layout.label(text="Select a Grease Pencil and click 'Add Current'")
            return
        
        # Filtro por categoria
        categories = library.get_categories_with_poses()
        
        row = layout.row()
        row.label(text=f"Total: {poses_count} poses", icon='GREASEPENCIL')
        
        # Layout em grid para as poses
        flow = layout.grid_flow(row_major=True, columns=0, even_columns=True, 
                                even_rows=False, align=True)
        
        # Agrupar por categoria
        for category, count in categories.items():
            col = flow.column(align=True)
            col.label(text=f"{category.capitalize()} ({count})", icon='FILE_FOLDER')
            
            poses = library.get_poses_by_category(category)
            for pose in poses:
                self.draw_pose_button(col, context, pose)
    
    def draw_pose_button(self, layout, context, pose):
        """Desenha um botão para uma pose específica"""
        row = layout.row(align=True)
        
        # Botão principal da pose
        op = row.operator("gp.apply_pose", text=pose.name)
        op.pose_id = pose.id
        
        # Botão de deletar
        op_del = row.operator("gp.delete_pose", text="", icon='X')
        op_del.pose_id = pose.id


class GP_PT_library_settings(bpy.types.Panel):
    """Painel de configurações"""
    bl_label = "Library Settings"
    bl_idname = "GP_PT_library_settings"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Asset Pro"
    bl_parent_id = "ASSETMANAGER_PT_main"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        layout.label(text="Coming soon:", icon='SETTINGS')
        layout.label(text="- Thumbnail previews")
        layout.label(text="- Auto-refresh on file changes")
        layout.label(text="- Multi-object substitution")
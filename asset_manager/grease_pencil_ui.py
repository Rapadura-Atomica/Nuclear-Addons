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
    
    def draw(self, context):
        layout = self.layout
        library = GPLibrary()
        
        # Ações principais
        row = layout.row(align=True)
        row.operator("gp.save_library", icon='FILE_BLEND', text="Save as Library")
        row.operator("gp.import_library", icon='IMPORT', text="Import")
        row.operator("gp.refresh_library", icon='FILE_REFRESH', text="")
        
        if not library.project_path:
            layout.label(text="No active project", icon='ERROR')
            layout.label(text="Use 'Iniciar Projeto' first")
            return
        
        # Bibliotecas disponíveis
        libraries = library.get_libraries()
        if not libraries:
            layout.label(text="No libraries", icon='INFO')
            layout.label(text="Select a Grease Pencil and click 'Save as Library'")
            return
        
        # Listar bibliotecas
        for lib_name, lib_info in libraries.items():
            self.draw_library(layout, context, library, lib_name, lib_info)
    
    def draw_library(self, layout, context, library, lib_name, lib_info):
        """Desenha uma biblioteca e suas poses"""
        box = layout.box()
        
        # Header da biblioteca
        row = box.row(align=True)
        row.label(text=f"📚 {lib_name}", icon='FILE_BLEND')
        
        # Botões de ação da biblioteca
        row = box.row(align=True)
        row.label(text=f"Poses: {len([p for p in library.poses.values() if p.library_name == lib_name])}")
        
        op_del = row.operator("gp.delete_library", text="", icon='X')
        op_del.library_name = lib_name
        
        # Poses da biblioteca
        poses = library.get_poses(library_name=lib_name)
        flow = box.grid_flow(row_major=True, columns=3, even_columns=True, even_rows=False)
        
        for pose in poses:
            self.draw_pose_button(flow, context, pose)
    
    def draw_pose_button(self, layout, context, pose):
        """Desenha um botão para uma pose específica"""
        row = layout.row(align=True)

        if not pose or not pose.id:
            row.label(text="Invalid pose")
            return
        
        # Nome da pose
        op = row.operator("gp.apply_pose", text=f"🎨 Frame {pose.frame_number}: {pose.name}")
        op.pose_id = pose.id


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
        library = GPLibrary()
        
        layout.label(text="Libraries Location:", icon='FILE_FOLDER')
        if library.libraries_path:
            layout.label(text=str(library.libraries_path))
        
        layout.separator()
        layout.label(text="Tips:", icon='INFO')
        layout.label(text="• Save a GP object as library")
        layout.label(text="• Each frame becomes a pose")
        layout.label(text="• Import libraries between projects")
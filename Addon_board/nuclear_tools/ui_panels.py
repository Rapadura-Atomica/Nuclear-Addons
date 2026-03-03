import bpy
from .api_router import *

# Painel de configuração global (mantido para o fitting)
class NIJIGP_PT_global_setting(bpy.types.Panel):
    bl_idname = 'NIJIGP_PT_global_setting'
    bl_label = "Fitting Settings"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Nuclear_Tools"
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        row = layout.row()
        row.label(text="Working Plane:")
        row.prop(scene, "nijigp_working_plane", text='')
        if scene.nijigp_working_plane == 'VIEW' or scene.nijigp_working_plane == 'AUTO':
            row = layout.row()
            row.prop(scene, "nijigp_working_plane_layer_transform", text='Use Transform of Active Layer')

# Painel de fitting no Edit Mode
class NIJIGP_PT_edit_panel_line(bpy.types.Panel):
    bl_idname = 'NIJIGP_PT_edit_panel_line'
    bl_label = "Line Fitting"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Nuclear_Tools"
    bl_context = get_bl_context_str('edit')
    bl_order = 1

    def draw(self, context):
        layout = self.layout
        layout.label(text="Line Cleanup by Fitting:")
        row = layout.row()
        row.operator("gpencil.nijigp_fit_selected", text="Single-Line", icon="MOD_SMOOTH")
        row.operator("gpencil.nijigp_cluster_and_fit", text="Multi-Line", icon="CURVES")
        layout.label(text="Line Utilities:")
        row = layout.row()
        row.operator("gpencil.nijigp_cluster_select", text="Cluster Select", icon="SELECT_SET")
        row = layout.row()
        row.operator("gpencil.nijigp_pinch", text="Pinch", icon="HANDLE_VECTOR")
        row.operator("gpencil.nijigp_taper_selected", text="Taper", icon="GP_ONLY_SELECTED")
     
# Painel de fitting no Draw Mode  
class NIJIGP_PT_draw_panel_line(bpy.types.Panel):
    bl_idname = 'NIJIGP_PT_draw_panel_line'
    bl_label = "Line Fitting"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Nuclear_Tools"
    bl_context = get_bl_context_str('paint')
    bl_order = 1

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.operator("gpencil.nijigp_fit_last", icon='MOD_SMOOTH')
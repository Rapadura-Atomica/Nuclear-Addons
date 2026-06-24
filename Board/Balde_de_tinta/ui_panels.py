import bpy
from .api_router import *

class NIJIGP_PT_draw_panel_line(bpy.types.Panel):
    bl_idname = 'NIJIGP_PT_draw_panel_line'
    bl_label = "Balde de tinta"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Balde de tinta"
    bl_context = get_bl_context_str('paint')
    bl_order = 1

    def draw(self, context):
        layout = self.layout

        row = layout.row()
        row.operator("gpencil.nijigp_fit_last", icon='MOD_SMOOTH')
        row = layout.row()
        row.operator("gpencil.nijigp_smart_fill", icon='SHADING_SOLID')

import bpy
from .api_router import *


class AutoMattePanelBase:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Auto Matte"
    bl_order = 1

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.label(text="Working Plane:")
        col.prop(context.scene, "nijigp_working_plane", text="")
        col.separator()
        col.operator("gpencil.generate_auto_matte", icon='SHADING_SOLID')
        col.separator()
        col.label(text="Line Cleanup:")
        col.operator("gpencil.automatte_cleanup_lines", icon='MOD_SMOOTH')


class AUTOMATTE_PT_panel_paint(AutoMattePanelBase, bpy.types.Panel):
    bl_idname = "AUTOMATTE_PT_panel_paint"
    bl_label = "Generate Auto Matte"
    bl_context = get_bl_context_str('paint')


class AUTOMATTE_PT_panel_edit(AutoMattePanelBase, bpy.types.Panel):
    bl_idname = "AUTOMATTE_PT_panel_edit"
    bl_label = "Generate Auto Matte"
    bl_context = get_bl_context_str('edit')

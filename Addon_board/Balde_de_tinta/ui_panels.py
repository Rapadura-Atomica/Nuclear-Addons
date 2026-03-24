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
        prefs = context.preferences.addons[__package__].preferences

        # Bucket Fill Tool
        box = layout.box()
        box.label(text="Bucket Fill", icon='SHADING_SOLID')
        
        # Operator button
        row = box.row()
        row.operator("gpencil.nijigp_simple_bucket_fill", text="Fill", icon='SHADING_SOLID')
        
        # Tolerance slider
        row = box.row()
        row.prop(prefs, "bucket_fill_tolerance", text="Tolerance (px)")
        
        # Fill layer option
        row = box.row()
        row.prop(prefs, "bucket_fill_use_fill_layer", text="Use Fill Layer")
        
        if prefs.bucket_fill_use_fill_layer:
            row = box.row()
            row.prop(prefs, "bucket_fill_layer_name", text="Fill Layer")
        
        # Separator
        layout.separator()
        
        # Original operators
        row = layout.row()
        row.operator("gpencil.nijigp_fit_last", icon='MOD_SMOOTH')
        row = layout.row()
        row.operator("gpencil.nijigp_smart_fill", icon='SHADING_SOLID')
import bpy
from .api_router import *

ADDON_NAME = "Balde_de_tinta"


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
        
        try:
            prefs = context.preferences.addons[ADDON_NAME].preferences
        except KeyError:
            prefs = None

        # Bucket Fill Tool
        box = layout.box()
        box.label(text="Bucket Fill", icon='SHADING_SOLID')
        
        row = box.row()
        row.operator("gpencil.nijigp_simple_bucket_fill", text="Fill", icon='SHADING_SOLID')
        
        if prefs:
            row = box.row()
            row.prop(prefs, "bucket_fill_tolerance", text="Tolerance (px)")
            row = box.row()
            row.prop(prefs, "bucket_fill_auto_close_gap", text="Auto-Close Gap (px)")
            
            # Performance options
            row = box.row()
            row.prop(prefs, "bucket_fill_use_simplification", text="Simplify Complex Strokes")
            if prefs.bucket_fill_use_simplification:
                row = box.row()
                row.prop(prefs, "bucket_fill_max_points", text="Max Points per Stroke")
            
            # Fill layer options
            row = box.row()
            row.prop(prefs, "bucket_fill_use_fill_layer", text="Use Fill Layer")
            if prefs.bucket_fill_use_fill_layer:
                row = box.row()
                row.prop(prefs, "bucket_fill_layer_name", text="Fill Layer")
        
        layout.separator()
        
        # Original operators
        row = layout.row()
        row.operator("gpencil.nijigp_fit_last", icon='MOD_SMOOTH')
        row = layout.row()
        row.operator("gpencil.nijigp_smart_fill", icon='SHADING_SOLID')
import bpy

class GPENCIL_WST_SelectTool(bpy.types.WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'PAINT_GREASE_PENCIL'
    bl_idname = "gpencil.wst_select_tool"
    bl_label = "GP Select Tool"
    bl_description = "Ferramenta de seleção (Box/Lasso)"
    bl_icon = "ops.generic.select_box"
    bl_widget = None
    bl_keymap = (
        ("gpencil.draw_mode_box_select", {"type": 'LEFTMOUSE', "value": 'PRESS'}, {}),
        ("gpencil.draw_mode_lasso_select", {"type": 'LEFTMOUSE', "value": 'PRESS', "ctrl": True}, {}),
    )

class GPENCIL_WST_LassoTool(bpy.types.WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'PAINT_GREASE_PENCIL'
    bl_idname = "gpencil.wst_lasso_tool"
    bl_label = "GP Lasso Tool"
    bl_description = "Ferramenta de seleção por lasso"
    bl_icon = "ops.generic.select_lasso" 
    bl_widget = None
    bl_keymap = (
        ("gpencil.draw_mode_lasso_select", {"type": 'LEFTMOUSE', "value": 'PRESS'}, {}),
    )
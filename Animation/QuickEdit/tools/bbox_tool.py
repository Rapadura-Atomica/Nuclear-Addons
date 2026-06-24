import bpy

class GPENCIL_WST_BBoxTool(bpy.types.WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'PAINT_GREASE_PENCIL'
    bl_idname = "gpencil.wst_bbox_tool"
    bl_label = "GP BBox Tool"
    bl_description = "Ferramenta de transformação com bounding box"
    bl_icon = "ops.transform.resize"
    bl_widget = None
    bl_keymap = (
        ("gpencil.bbox_transform", {"type": 'LEFTMOUSE', "value": 'PRESS'}, {}),
    )
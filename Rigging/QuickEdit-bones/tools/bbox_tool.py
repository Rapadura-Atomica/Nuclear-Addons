# SPDX-License-Identifier: GPL-3.0-or-later
"""
Ferramenta de Bounding Box para bones em modo Pose
"""

import bpy


class POSE_WST_BBoxTool(bpy.types.WorkSpaceTool):
    """Ferramenta de transformação com bounding box para bones"""
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'POSE'
    bl_idname = "pose.wst_bbox_tool"
    bl_label = "Pose BBox Tool"
    bl_description = "Ferramenta de transformação com bounding box"
    bl_icon = "ops.transform.resize"
    bl_widget = None
    bl_keymap = (
        ("pose.bbox_transform_bones", {"type": 'LEFTMOUSE', "value": 'PRESS'}, {}),
    )
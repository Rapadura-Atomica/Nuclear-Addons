# SPDX-License-Identifier: GPL-3.0-or-later
"""
Ferramentas de seleção para modo Pose
"""

import bpy


class POSE_WST_SelectTool(bpy.types.WorkSpaceTool):
    """Ferramenta de seleção por caixa"""
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'POSE'
    bl_idname = "pose.wst_select_tool"
    bl_label = "Pose Select Tool"
    bl_description = "Ferramenta de seleção por caixa (Box Select)"
    bl_icon = "ops.generic.select_box"
    bl_widget = None
    bl_keymap = (
        ("pose.box_select_bones", {"type": 'LEFTMOUSE', "value": 'PRESS'}, {}),
    )


class POSE_WST_LassoTool(bpy.types.WorkSpaceTool):
    """Ferramenta de seleção por lasso"""
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'POSE'
    bl_idname = "pose.wst_lasso_tool"
    bl_label = "Pose Lasso Tool"
    bl_description = "Ferramenta de seleção por lasso"
    bl_icon = "ops.generic.select_lasso"
    bl_widget = None
    bl_keymap = (
        ("pose.lasso_select_bones", {"type": 'LEFTMOUSE', "value": 'PRESS'}, {}),
    )
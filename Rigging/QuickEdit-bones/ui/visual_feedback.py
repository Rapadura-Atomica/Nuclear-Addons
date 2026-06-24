# SPDX-License-Identifier: GPL-3.0-or-later
"""
Sistema de highlight visual para bones selecionados - Compatível com Blender 5.0+
"""

import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from bpy_extras.view3d_utils import location_3d_to_region_2d

from ..core.bone_manager import BoneManager


class BoneHighlighter:
    """Sistema de highlight visual para bones selecionados"""
    
    _draw_handler = None
    _enabled = False
    
    @classmethod
    def enable(cls):
        if cls._draw_handler is not None:
            return
        cls._draw_handler = bpy.types.SpaceView3D.draw_handler_add(
            cls.draw_callback, (), 'WINDOW', 'POST_PIXEL'
        )
        cls._enabled = True
    
    @classmethod
    def disable(cls):
        if cls._draw_handler is not None:
            bpy.types.SpaceView3D.draw_handler_remove(cls._draw_handler, 'WINDOW')
            cls._draw_handler = None
            cls._enabled = False
    
    @classmethod
    def toggle(cls):
        if cls._enabled:
            cls.disable()
        else:
            cls.enable()
    
    @classmethod
    def draw_callback(cls):
        context = bpy.context
        obj = BoneManager.get_active_armature(context)
        if not obj:
            return

        region = context.region
        rv3d = BoneManager.get_region_3d(context)
        if not rv3d:
            return

        SELECTED_COLOR = (1.0, 0.6, 0.0, 1.0)
        LINE_WIDTH = 3.0

        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('NONE')

        armature_matrix = obj.matrix_world

        for pose_bone in obj.pose.bones:
            # CORREÇÃO: usar pose_bone.select diretamente (Blender 5.0+)
            if not pose_bone.select:
                continue

            head_world = armature_matrix @ pose_bone.head
            tail_world = armature_matrix @ pose_bone.tail
            
            head_screen = location_3d_to_region_2d(region, rv3d, head_world)
            tail_screen = location_3d_to_region_2d(region, rv3d, tail_world)
            
            if head_screen and tail_screen:
                gpu.state.line_width_set(LINE_WIDTH)
                batch = batch_for_shader(shader, 'LINES', {"pos": [head_screen, tail_screen]})
                shader.bind()
                shader.uniform_float("color", SELECTED_COLOR)
                batch.draw(shader)

        gpu.state.blend_set('NONE')
        gpu.state.line_width_set(1.0)


class AutoBoneHighlighter:
    """Ativa/desativa automaticamente o highlight baseado no contexto"""
    
    @staticmethod
    def update_highlight_state(context):
        if (context.object and 
            context.object.type == 'ARMATURE' and 
            context.object.mode == 'POSE'):
            BoneHighlighter.enable()
        else:
            BoneHighlighter.disable()
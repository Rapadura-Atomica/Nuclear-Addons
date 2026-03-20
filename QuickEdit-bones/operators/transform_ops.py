# SPDX-License-Identifier: GPL-3.0-or-later
"""
Operador de transformação com Bounding Box para bones em modo Pose
Compatível com Blender 5.0+
"""

import bpy
import gpu
import blf
from gpu_extras.batch import batch_for_shader
from mathutils import Vector, Matrix, Euler
from math import atan2, pi, cos, sin
from bpy_extras.view3d_utils import region_2d_to_location_3d, location_3d_to_region_2d

from ..core import constants
from ..core.bone_manager import BoneManager
from ..core.event_handler import BBoxEventHandler
from ..core.utilities import (
    calculate_screen_bbox, get_bbox_corners, get_bbox_center,
    get_handle_under_mouse
)
from ..ui.visual_feedback import BoneHighlighter


def draw_bbox(bbox, handle_hover, handle_active, is_proportional=False):
    """Desenha a bounding box, handles e gizmo pivot"""
    if not bbox:
        return

    corners = get_bbox_corners(bbox)
    center = get_bbox_center(bbox)
    pivot_pos = constants._pivot_pos
    if pivot_pos is None:
        pivot_pos = center

    shader = gpu.shader.from_builtin('UNIFORM_COLOR')

    # 1. Desenhar bounding box (LINHAS)
    vertices = [corners[0], corners[1], corners[1], corners[2],
                corners[2], corners[3], corners[3], corners[0]]
    batch = batch_for_shader(shader, 'LINES', {"pos": vertices})
    shader.bind()
    if is_proportional:
        shader.uniform_float("color", (0.2, 0.8, 0.8, 0.8))
    else:
        shader.uniform_float("color", constants.COLOR_BBOX)
    gpu.state.line_width_set(constants.LINE_WIDTH)
    batch.draw(shader)
    gpu.state.line_width_set(1)

    # 2. Texto indicador proporcional
    if is_proportional:
        font_id = 0
        blf.position(font_id, center.x - 20, center.y - 15, 0)
        blf.size(font_id, 16)
        blf.color(font_id, 0.2, 0.8, 0.8, 1.0)
        blf.draw(font_id, "Proportional")

    # 3. Desenhar handles normais
    shear_offset = 25
    handle_positions = [
        (constants.HandleType.BOTTOM_LEFT, corners[0]),
        (constants.HandleType.BOTTOM_RIGHT, corners[1]),
        (constants.HandleType.TOP_RIGHT, corners[2]),
        (constants.HandleType.TOP_LEFT, corners[3]),
        (constants.HandleType.TOP, (corners[2] + corners[3]) / 2),
        (constants.HandleType.BOTTOM, (corners[0] + corners[1]) / 2),
        (constants.HandleType.LEFT, (corners[0] + corners[3]) / 2),
        (constants.HandleType.RIGHT, (corners[1] + corners[2]) / 2),
        (constants.HandleType.CENTER, center),
        (constants.HandleType.SHEAR_TOP, (corners[2] + corners[3]) / 2 + Vector((0, shear_offset))),
        (constants.HandleType.SHEAR_BOTTOM, (corners[0] + corners[1]) / 2 + Vector((0, -shear_offset))),
        (constants.HandleType.SHEAR_LEFT, (corners[0] + corners[3]) / 2 + Vector((-shear_offset, 0))),
        (constants.HandleType.SHEAR_RIGHT, (corners[1] + corners[2]) / 2 + Vector((shear_offset, 0))),
    ]

    for handle_type, pos in handle_positions:
        if handle_type == handle_active:
            color = constants.COLOR_HANDLE_ACTIVE
            size = constants.HANDLE_SIZE * 1.2
        elif handle_type == handle_hover:
            color = constants.COLOR_HANDLE_HOVER
            size = constants.HANDLE_SIZE * 1.1
        else:
            if handle_type == constants.HandleType.CENTER:
                color = constants.COLOR_CENTER
                size = constants.CENTER_HANDLE_SIZE
            elif handle_type in [constants.HandleType.SHEAR_TOP, constants.HandleType.SHEAR_BOTTOM,
                                 constants.HandleType.SHEAR_LEFT, constants.HandleType.SHEAR_RIGHT]:
                color = constants.COLOR_SHEAR
                size = constants.HANDLE_SIZE * 0.8
            else:
                color = (0.2, 0.8, 0.8, 1.0) if is_proportional else constants.COLOR_HANDLE
                size = constants.HANDLE_SIZE

        if handle_type in [constants.HandleType.BOTTOM_LEFT, constants.HandleType.BOTTOM_RIGHT,
                           constants.HandleType.TOP_LEFT, constants.HandleType.TOP_RIGHT,
                           constants.HandleType.TOP, constants.HandleType.BOTTOM,
                           constants.HandleType.LEFT, constants.HandleType.RIGHT]:
            handle_size = size / 2
            handle_verts = [
                pos + Vector((-handle_size, -handle_size)),
                pos + Vector((handle_size, -handle_size)),
                pos + Vector((handle_size, handle_size)),
                pos + Vector((-handle_size, handle_size))
            ]
            handle_indices = [(0, 1), (1, 2), (2, 3), (3, 0)]
            batch_handle = batch_for_shader(shader, 'LINES', {"pos": handle_verts}, indices=handle_indices)
            shader.uniform_float("color", color)
            batch_handle.draw(shader)

    # 4. Roda de rotação
    if handle_active == constants.HandleType.ROTATION or handle_hover == constants.HandleType.ROTATION:
        shader.uniform_float("color", constants.COLOR_ROTATION)
        gpu.state.line_width_set(1)
        rotation_handle_pos = center + Vector((0, constants.ROTATION_HANDLE_DISTANCE))
        batch_line = batch_for_shader(shader, 'LINES', {"pos": [center, rotation_handle_pos]})
        batch_line.draw(shader)

    # 5. Desenhar o gizmo pivot
    segments = 16
    circle_verts = []
    radius = constants.PIVOT_RADIUS
    for j in range(segments + 1):
        angle = 2 * pi * j / segments
        dx = radius * cos(angle)
        dy = radius * sin(angle)
        circle_verts.append((pivot_pos.x + dx, pivot_pos.y + dy))

    if circle_verts:
        batch = batch_for_shader(shader, 'LINE_LOOP', {"pos": circle_verts})
        if handle_active == constants.HandleType.PIVOT:
            color = constants.COLOR_PIVOT_ACTIVE
        elif handle_hover == constants.HandleType.PIVOT:
            color = constants.COLOR_PIVOT_HOVER
        else:
            color = constants.COLOR_PIVOT
        shader.bind()
        shader.uniform_float("color", color)
        gpu.state.line_width_set(2.0)
        batch.draw(shader)
    gpu.state.line_width_set(1.0)


class POSE_OT_bbox_transform_bones(bpy.types.Operator):
    """Transformação interativa com bounding box para bones"""
    bl_idname = "pose.bbox_transform_bones"
    bl_label = "Pose BBox Transform"
    bl_options = {'REGISTER', 'UNDO'}

    def modal(self, context, event):
        from ..core.event_handler import BBoxEventHandler
        
        # 1. Checa se o evento deve passar para outros operadores
        if BBoxEventHandler.handle_event(context, event, self):
            if event.type == 'MOUSEMOVE':
                context.area.tag_redraw()
            return {'PASS_THROUGH'}

        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            self.update_bbox(context)
            return {'PASS_THROUGH'}
        
        # 2. Fallback manual para clipboard
        if event.ctrl and event.value == 'PRESS':
            if event.type == 'C':
                bpy.ops.pose.copy_bones()
                return {'PASS_THROUGH'}
            elif event.type == 'V':
                bpy.ops.pose.paste_bones()
                return {'PASS_THROUGH'}
            elif event.type == 'X':
                bpy.ops.pose.cut_bones()
                return {'PASS_THROUGH'}
        
        # 3. Atualiza estado proporcional
        self.is_proportional = event.shift
        
        # 4. Se não há mais BBox, finaliza
        if not constants._bbox_data:
            self.finish(context)
            return {'CANCELLED'}
        
        mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))
        
        # 5. Recalcula BBox se a view mudou
        current_view_matrix = context.region_data.view_matrix.copy() if context.region_data else None
        if not hasattr(self, '_last_view_matrix'):
            self._last_view_matrix = current_view_matrix
        
        if current_view_matrix and self._last_view_matrix != current_view_matrix:
            self.update_bbox(context)
            self._last_view_matrix = current_view_matrix
        
        # 6. Hover nos handles
        if event.type == 'MOUSEMOVE' and self.handle_active == constants.HandleType.NONE:
            handle_under_mouse = get_handle_under_mouse(constants._bbox_data, mouse_pos)
            
            if handle_under_mouse in [constants.HandleType.SHEAR_TOP, constants.HandleType.SHEAR_BOTTOM,
                                    constants.HandleType.SHEAR_LEFT, constants.HandleType.SHEAR_RIGHT]:
                context.window.cursor_modal_set('HAND')
            elif handle_under_mouse in [constants.HandleType.ROTATE_TOP_LEFT, constants.HandleType.ROTATE_TOP_RIGHT,
                                        constants.HandleType.ROTATE_BOTTOM_LEFT, constants.HandleType.ROTATE_BOTTOM_RIGHT]:
                context.window.cursor_modal_set('SCROLL_XY')
            elif handle_under_mouse == constants.HandleType.PIVOT:
                context.window.cursor_modal_set('CROSSHAIR')
            else:
                context.window.cursor_modal_set('DEFAULT')
            
            self.handle_hover = handle_under_mouse if handle_under_mouse != constants.HandleType.NONE else self.handle_hover
            context.area.tag_redraw()
        
        # 7. Arrasto de handles
        if event.type == 'MOUSEMOVE' and self.handle_active != constants.HandleType.NONE:
            delta = mouse_pos - self.mouse_start
            
            # Pivot move
            if self.handle_active == constants.HandleType.PIVOT:
                xmin, xmax, ymin, ymax = constants._bbox_data
                margin = 10
                new_x = max(xmin + margin, min(event.mouse_region_x, xmax - margin))
                new_y = max(ymin + margin, min(event.mouse_region_y, ymax - margin))
                constants._pivot_pos = Vector((new_x, new_y))
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            
            # Rotação
            if self.handle_active in [constants.HandleType.ROTATE_TOP_LEFT, constants.HandleType.ROTATE_TOP_RIGHT,
                                    constants.HandleType.ROTATE_BOTTOM_LEFT, constants.HandleType.ROTATE_BOTTOM_RIGHT]:
                pivot_pos = constants._pivot_pos if constants._pivot_pos else get_bbox_center(self.bbox_start)
                vec_current = mouse_pos - pivot_pos
                current_angle = atan2(vec_current.y, vec_current.x)
                if not hasattr(self, '_start_angle'):
                    self._start_angle = current_angle
                total_angle = current_angle - self._start_angle
                self.apply_rotation_to_bones(context, total_angle)
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            
            # Translação
            elif self.handle_active == constants.HandleType.CENTER:
                total_delta = mouse_pos - self.mouse_start
                self.apply_translation_to_bones(context, total_delta)
                new_bbox = (
                    self.bbox_start[0] + total_delta.x,
                    self.bbox_start[1] + total_delta.x,
                    self.bbox_start[2] + total_delta.y,
                    self.bbox_start[3] + total_delta.y
                )
                constants._bbox_data = new_bbox
                if constants._pivot_pos:
                    constants._pivot_pos = get_bbox_center(new_bbox)
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            
            # Shear
            elif self.handle_active in [constants.HandleType.SHEAR_TOP, constants.HandleType.SHEAR_BOTTOM,
                                        constants.HandleType.SHEAR_LEFT, constants.HandleType.SHEAR_RIGHT]:
                pivot_pos = constants._pivot_pos if constants._pivot_pos else get_bbox_center(self.bbox_start)
                
                if self.handle_active in [constants.HandleType.SHEAR_LEFT, constants.HandleType.SHEAR_RIGHT]:
                    shear_amount = delta.x / 100.0
                else:
                    shear_amount = delta.y / 100.0
                
                self.apply_shear_to_bones(context, shear_amount, self.handle_active, pivot_pos)
                self.update_bbox(context)
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            
            # Escala
            else:
                pivot_pos = constants._pivot_pos if constants._pivot_pos else get_bbox_center(self.bbox_start)
                xmin, xmax, ymin, ymax = self.bbox_start
                
                delta_x_left = delta.x if self.handle_active in [constants.HandleType.LEFT, constants.HandleType.TOP_LEFT, constants.HandleType.BOTTOM_LEFT] else 0
                delta_x_right = delta.x if self.handle_active in [constants.HandleType.RIGHT, constants.HandleType.TOP_RIGHT, constants.HandleType.BOTTOM_RIGHT] else 0
                delta_y_top = delta.y if self.handle_active in [constants.HandleType.TOP, constants.HandleType.TOP_LEFT, constants.HandleType.TOP_RIGHT] else 0
                delta_y_bottom = delta.y if self.handle_active in [constants.HandleType.BOTTOM, constants.HandleType.BOTTOM_LEFT, constants.HandleType.BOTTOM_RIGHT] else 0
                
                new_xmin = xmin + delta_x_left
                new_xmax = xmax + delta_x_right
                new_ymin = ymin + delta_y_bottom
                new_ymax = ymax + delta_y_top
                
                original_width = xmax - xmin
                original_height = ymax - ymin
                
                scale_x = (new_xmax - new_xmin) / original_width if original_width != 0 else 1.0
                scale_y = (new_ymax - new_ymin) / original_height if original_height != 0 else 1.0
                
                if self.is_proportional and self.handle_active in [
                    constants.HandleType.TOP_LEFT, constants.HandleType.TOP_RIGHT,
                    constants.HandleType.BOTTOM_LEFT, constants.HandleType.BOTTOM_RIGHT,
                    constants.HandleType.TOP, constants.HandleType.BOTTOM,
                    constants.HandleType.LEFT, constants.HandleType.RIGHT
                ]:
                    uniform_scale = min(scale_x, scale_y) if scale_x > 0 and scale_y > 0 else max(scale_x, scale_y)
                    scale_x = uniform_scale
                    scale_y = uniform_scale
                
                self.apply_scale_to_bones(context, scale_x, scale_y, pivot_pos)
                self.update_bbox(context)
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}
        
        # Início do arrasto
        elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            handle_under_mouse = get_handle_under_mouse(constants._bbox_data, mouse_pos)
            if handle_under_mouse == constants.HandleType.NONE:
                self.finish(context)
                return {'CANCELLED'}
            
            self.handle_active = handle_under_mouse
            self.mouse_start = mouse_pos
            self.bbox_start = constants._bbox_data
            self.is_proportional = event.shift
            
            if hasattr(self, '_start_angle'):
                del self._start_angle
            
            # Salvar estado original dos bones (usando pose_bone)
            obj = BoneManager.get_active_armature(context)
            if obj:
                constants._original_bones = {}
                for pose_bone in obj.pose.bones:
                    if pose_bone.select:
                        constants._original_bones[pose_bone.name] = {
                            'pose_bone': pose_bone,
                            'head': pose_bone.head.copy(),
                            'tail': pose_bone.tail.copy(),
                            'matrix': pose_bone.matrix.copy(),
                            'location': pose_bone.location.copy(),
                            'rotation': pose_bone.rotation_euler.copy() if pose_bone.rotation_mode == 'XYZ' else pose_bone.rotation_quaternion.copy(),
                            'scale': pose_bone.scale.copy()
                        }
            
            context.area.tag_redraw()
        
        # Fim do arrasto
        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            self.handle_active = constants.HandleType.NONE
            if hasattr(self, '_start_angle'):
                del self._start_angle
            context.window.cursor_modal_restore()
            context.area.tag_redraw()
        
        # Cancelamento
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            self.finish(context)
            return {'CANCELLED'}
        
        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        selected_bones, world_points, screen_points, _ = BoneManager.get_selected_bones(context)
        
        if not selected_bones:
            self.report({'ERROR'}, "Selecione alguns bones primeiro")
            return {'CANCELLED'}
        
        constants._bbox_data = calculate_screen_bbox(context, screen_points)
        if not constants._bbox_data:
            self.report({'ERROR'}, "Não foi possível calcular a bounding box")
            return {'CANCELLED'}
        
        constants._pivot_pos = get_bbox_center(constants._bbox_data)
        
        bpy.ops.ed.undo_push(message="Before BBox Transform")

        self.handle_hover = constants.HandleType.NONE
        self.handle_active = constants.HandleType.NONE
        self.mouse_start = Vector((0, 0))
        self.bbox_start = constants._bbox_data
        self.is_proportional = False
        
        # Salvar estado original dos bones
        obj = BoneManager.get_active_armature(context)
        constants._original_bones = {}
        for pose_bone in selected_bones:
            constants._original_bones[pose_bone.name] = {
                'pose_bone': pose_bone,
                'head': pose_bone.head.copy(),
                'tail': pose_bone.tail.copy(),
                'matrix': pose_bone.matrix.copy(),
                'location': pose_bone.location.copy(),
                'rotation': pose_bone.rotation_euler.copy() if pose_bone.rotation_mode == 'XYZ' else pose_bone.rotation_quaternion.copy(),
                'scale': pose_bone.scale.copy()
            }
        
        if constants._bbox_handle is None:
            constants._bbox_handle = bpy.types.SpaceView3D.draw_handler_add(
                self.draw_callback, (context,), 'WINDOW', 'POST_PIXEL'
            )
        
        BoneHighlighter.enable()

        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def apply_translation_to_bones(self, context, delta):
        """Aplica translação aos bones selecionados usando location"""
        obj = BoneManager.get_active_armature(context)
        if not obj or not constants._original_bones:
            return
        
        region = context.region
        rv3d = BoneManager.get_region_3d(context)
        if not rv3d:
            return
        
        armature_matrix = obj.matrix_world
        
        for bone_name, original in constants._original_bones.items():
            pose_bone = original['pose_bone']
            if not pose_bone:
                continue
            
            # Calcular nova posição do bone no espaço da armature
            head_world = armature_matrix @ original['head']
            tail_world = armature_matrix @ original['tail']
            
            head_screen = location_3d_to_region_2d(region, rv3d, head_world)
            tail_screen = location_3d_to_region_2d(region, rv3d, tail_world)
            
            if head_screen:
                new_head_screen = Vector((head_screen.x + delta.x, head_screen.y + delta.y))
                new_head_world = region_2d_to_location_3d(region, rv3d, new_head_screen, head_world)
                new_head_local = armature_matrix.inverted() @ new_head_world
                
                # Calcular o offset da translação
                offset = new_head_local - original['head']
                
                # Aplicar translação ao bone
                pose_bone.location = original['location'] + offset

    def apply_scale_to_bones(self, context, scale_x, scale_y, pivot_pos):
        """Aplica escala aos bones selecionados"""
        obj = BoneManager.get_active_armature(context)
        if not obj or not constants._original_bones:
            return
        
        region = context.region
        rv3d = BoneManager.get_region_3d(context)
        if not rv3d:
            return
        
        armature_matrix = obj.matrix_world
        
        for bone_name, original in constants._original_bones.items():
            pose_bone = original['pose_bone']
            if not pose_bone:
                continue
            
            head_world = armature_matrix @ original['head']
            tail_world = armature_matrix @ original['tail']
            
            head_screen = location_3d_to_region_2d(region, rv3d, head_world)
            tail_screen = location_3d_to_region_2d(region, rv3d, tail_world)
            
            if head_screen:
                rel_to_pivot = head_screen - pivot_pos
                scaled_rel = Vector((rel_to_pivot.x * scale_x, rel_to_pivot.y * scale_y))
                new_head_screen = pivot_pos + scaled_rel
                new_head_world = region_2d_to_location_3d(region, rv3d, new_head_screen, head_world)
                new_head_local = armature_matrix.inverted() @ new_head_world
                
                # Calcular escala relativa ao bone original
                if original['head'].length > 0:
                    scale_factor = new_head_local.length / original['head'].length
                    # Aplicar escala uniforme baseada no fator
                    pose_bone.scale = original['scale'] * scale_factor

    def apply_rotation_to_bones(self, context, angle):
        """Aplica rotação aos bones selecionados"""
        obj = BoneManager.get_active_armature(context)
        if not obj or not constants._original_bones:
            return
        
        pivot_pos = constants._pivot_pos if constants._pivot_pos else get_bbox_center(self.bbox_start)
        cos_a = cos(angle)
        sin_a = sin(angle)
        
        region = context.region
        rv3d = BoneManager.get_region_3d(context)
        if not rv3d:
            return
        
        armature_matrix = obj.matrix_world
        
        for bone_name, original in constants._original_bones.items():
            pose_bone = original['pose_bone']
            if not pose_bone:
                continue
            
            head_world = armature_matrix @ original['head']
            tail_world = armature_matrix @ original['tail']
            
            head_screen = location_3d_to_region_2d(region, rv3d, head_world)
            tail_screen = location_3d_to_region_2d(region, rv3d, tail_world)
            
            if head_screen:
                rel_to_pivot = head_screen - pivot_pos
                rotated_rel = Vector((
                    rel_to_pivot.x * cos_a - rel_to_pivot.y * sin_a,
                    rel_to_pivot.x * sin_a + rel_to_pivot.y * cos_a
                ))
                new_head_screen = pivot_pos + rotated_rel
                new_head_world = region_2d_to_location_3d(region, rv3d, new_head_screen, head_world)
                new_head_local = armature_matrix.inverted() @ new_head_world
                
                # Calcular vetor original e novo para obter rotação
                original_vec = original['head']
                new_vec = new_head_local
                
                if original_vec.length > 0 and new_vec.length > 0:
                    # Calcular ângulo de rotação no plano local
                    original_vec_2d = Vector((original_vec.x, original_vec.y))
                    new_vec_2d = Vector((new_vec.x, new_vec.y))
                    
                    if original_vec_2d.length > 0:
                        rot_angle = original_vec_2d.angle_signed(new_vec_2d)
                        # Aplicar rotação ao bone
                        current_euler = pose_bone.rotation_euler
                        pose_bone.rotation_euler = Euler((
                            current_euler.x,
                            current_euler.y,
                            current_euler.z + rot_angle
                        ))

    def apply_shear_to_bones(self, context, shear_amount, handle_type, pivot_pos):
        """Aplica shear aos bones selecionados"""
        obj = BoneManager.get_active_armature(context)
        if not obj or not constants._original_bones:
            return
        
        region = context.region
        rv3d = BoneManager.get_region_3d(context)
        if not rv3d:
            return
        
        armature_matrix = obj.matrix_world
        is_horizontal = handle_type in [constants.HandleType.SHEAR_LEFT, constants.HandleType.SHEAR_RIGHT]
        
        for bone_name, original in constants._original_bones.items():
            pose_bone = original['pose_bone']
            if not pose_bone:
                continue
            
            head_world = armature_matrix @ original['head']
            tail_world = armature_matrix @ original['tail']
            
            head_screen = location_3d_to_region_2d(region, rv3d, head_world)
            tail_screen = location_3d_to_region_2d(region, rv3d, tail_world)
            
            if head_screen:
                rel_to_pivot = head_screen - pivot_pos
                if is_horizontal:
                    new_rel = Vector((rel_to_pivot.x + shear_amount * rel_to_pivot.y, rel_to_pivot.y))
                else:
                    new_rel = Vector((rel_to_pivot.x, rel_to_pivot.y + shear_amount * rel_to_pivot.x))
                new_head_screen = pivot_pos + new_rel
                new_head_world = region_2d_to_location_3d(region, rv3d, new_head_screen, head_world)
                new_head_local = armature_matrix.inverted() @ new_head_world
                
                # Para shear, movemos a posição do bone
                offset = new_head_local - original['head']
                pose_bone.location = original['location'] + offset

    def update_bbox(self, context):
        """Atualiza a bounding box baseada na seleção atual"""
        _, world_points, screen_points, _ = BoneManager.get_selected_bones(context)
        if screen_points:
            constants._bbox_data = calculate_screen_bbox(context, screen_points)
            if constants._pivot_pos is None:
                constants._pivot_pos = get_bbox_center(constants._bbox_data)
            context.area.tag_redraw()

    def draw_callback(self, context):
        draw_bbox(constants._bbox_data, self.handle_hover, self.handle_active, self.is_proportional)

    def finish(self, context):
        context.window.cursor_modal_restore()
        
        if constants._bbox_handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(constants._bbox_handle, 'WINDOW')
            constants._bbox_handle = None
        
        constants._bbox_data = None
        constants._pivot_pos = None
        constants._original_bones.clear()
        
        BoneHighlighter.disable()
        context.area.tag_redraw()


class POSE_OT_activate_bbox_tool(bpy.types.Operator):
    """Ativa a ferramenta de bounding box"""
    bl_idname = "pose.activate_bbox_tool"
    bl_label = "Ativar BBox Tool"
    bl_description = "Ativa a ferramenta de bounding box"
    bl_options = {'REGISTER'}

    def execute(self, context):
        BoneManager.activate_tool("pose.wst_bbox_tool")
        return {'FINISHED'}
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Operador de Bounding Box para bones em Pose Mode
Focado em escala como S + X / S + Y (esticar direcionado)
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
    """Desenha a bounding box sem shear"""
    if not bbox:
        return
    corners = get_bbox_corners(bbox)
    center = get_bbox_center(bbox)
    pivot_pos = constants._pivot_pos if constants._pivot_pos else center

    shader = gpu.shader.from_builtin('UNIFORM_COLOR')

    # Bounding box
    vertices = [corners[0], corners[1], corners[1], corners[2],
                corners[2], corners[3], corners[3], corners[0]]
    batch = batch_for_shader(shader, 'LINES', {"pos": vertices})
    shader.bind()
    color = (0.2, 0.8, 0.8, 0.8) if is_proportional else constants.COLOR_BBOX
    shader.uniform_float("color", color)
    gpu.state.line_width_set(constants.LINE_WIDTH)
    batch.draw(shader)
    gpu.state.line_width_set(1)

    # Texto Proportional
    if is_proportional:
        font_id = 0
        blf.position(font_id, center.x - 25, center.y - 15, 0)
        blf.size(font_id, 16)
        blf.color(font_id, 0.2, 0.8, 0.8, 1.0)
        blf.draw(font_id, "Proportional")

    # Handles (sem shear)
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
            else:
                color = (0.2, 0.8, 0.8, 1.0) if is_proportional else constants.COLOR_HANDLE
                size = constants.HANDLE_SIZE

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

    # Roda de rotação
    if handle_active == constants.HandleType.ROTATION or handle_hover == constants.HandleType.ROTATION:
        shader.uniform_float("color", constants.COLOR_ROTATION)
        gpu.state.line_width_set(1)
        rotation_handle_pos = center + Vector((0, constants.ROTATION_HANDLE_DISTANCE))
        batch_line = batch_for_shader(shader, 'LINES', {"pos": [center, rotation_handle_pos]})
        batch_line.draw(shader)

    # Gizmo pivot
    segments = 16
    radius = constants.PIVOT_RADIUS
    circle_verts = []
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
        shader.uniform_float("color", color)
        gpu.state.line_width_set(2.0)
        batch.draw(shader)
    gpu.state.line_width_set(1.0)


class POSE_OT_bbox_transform_bones(bpy.types.Operator):
    """Bounding Box Transform - Escala como S + X / S + Y"""
    bl_idname = "pose.bbox_transform_bones"
    bl_label = "Pose BBox Transform (Scale like S+X/Y)"
    bl_options = {'REGISTER', 'UNDO'}

    def modal(self, context, event):
        from ..core.event_handler import BBoxEventHandler

        if BBoxEventHandler.handle_event(context, event, self):
            if event.type == 'MOUSEMOVE':
                context.area.tag_redraw()
            return {'PASS_THROUGH'}

        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            self.update_bbox(context)
            return {'PASS_THROUGH'}

        self.is_proportional = event.shift

        if not constants._bbox_data:
            self.finish(context)
            return {'CANCELLED'}

        mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))

        # Recalcula se view mudou
        current_vm = context.region_data.view_matrix.copy() if context.region_data else None
        if not hasattr(self, '_last_vm'):
            self._last_vm = current_vm
        if current_vm and self._last_vm != current_vm:
            self.update_bbox(context)
            self._last_vm = current_vm

        # Hover
        if event.type == 'MOUSEMOVE' and self.handle_active == constants.HandleType.NONE:
            handle = get_handle_under_mouse(constants._bbox_data, mouse_pos)
            self.handle_hover = handle if handle != constants.HandleType.NONE else self.handle_hover
            context.area.tag_redraw()

        # Arrasto
        if event.type == 'MOUSEMOVE' and self.handle_active != constants.HandleType.NONE:
            delta = mouse_pos - self.mouse_start
            pivot = constants._pivot_pos or get_bbox_center(self.bbox_start)

            if self.handle_active == constants.HandleType.PIVOT:
                xmin, xmax, ymin, ymax = constants._bbox_data
                margin = 10
                constants._pivot_pos = Vector((
                    max(xmin + margin, min(mouse_pos.x, xmax - margin)),
                    max(ymin + margin, min(mouse_pos.y, ymax - margin))
                ))
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}

            elif self.handle_active in [constants.HandleType.ROTATE_TOP_LEFT, constants.HandleType.ROTATE_TOP_RIGHT,
                                        constants.HandleType.ROTATE_BOTTOM_LEFT, constants.HandleType.ROTATE_BOTTOM_RIGHT]:
                angle = atan2((mouse_pos - pivot).y, (mouse_pos - pivot).x)
                if not hasattr(self, '_start_angle'):
                    self._start_angle = angle
                self.apply_rotation_to_bones(context, angle - self._start_angle, pivot)
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}

            elif self.handle_active == constants.HandleType.CENTER:
                self.apply_translation_to_bones(context, delta)
                new_bbox = (
                    self.bbox_start[0] + delta.x,
                    self.bbox_start[1] + delta.x,
                    self.bbox_start[2] + delta.y,
                    self.bbox_start[3] + delta.y
                )
                constants._bbox_data = new_bbox
                if constants._pivot_pos:
                    constants._pivot_pos = get_bbox_center(new_bbox)
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}

            else:  # Escala direcionada (principal)
                self.apply_scale_to_bones(context, self.bbox_start, delta, pivot, self.is_proportional, self.handle_active)
                self.update_bbox(context)
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}

        # Início do arrasto
        elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            handle = get_handle_under_mouse(constants._bbox_data, mouse_pos)
            if handle == constants.HandleType.NONE:
                self.finish(context)
                return {'CANCELLED'}
            self.handle_active = handle
            self.mouse_start = mouse_pos
            self.bbox_start = constants._bbox_data
            self.is_proportional = event.shift
            if hasattr(self, '_start_angle'):
                del self._start_angle
            context.area.tag_redraw()

        # Fim do arrasto
        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            self.handle_active = constants.HandleType.NONE
            if hasattr(self, '_start_angle'):
                del self._start_angle
            context.window.cursor_modal_restore()
            context.area.tag_redraw()

        # Cancelar
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            self.finish(context)
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        selected_bones, _, screen_points, _ = BoneManager.get_selected_bones(context)
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

        # Salvar estado original
        obj = BoneManager.get_active_armature(context)
        constants._original_bones = {}
        for pb in selected_bones:
            constants._original_bones[pb.name] = {
                'pose_bone': pb,
                'matrix_basis': pb.matrix_basis.copy(),
                'location': pb.location.copy(),
                'rotation_euler': pb.rotation_euler.copy(),
                'scale': pb.scale.copy()
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
        obj = BoneManager.get_active_armature(context)
        if not obj or not constants._original_bones:
            return
        region = context.region
        rv3d = BoneManager.get_region_3d(context)
        if not rv3d:
            return
        armature_matrix = obj.matrix_world

        for original in constants._original_bones.values():
            pb = original['pose_bone']
            if not pb:
                continue
            head_world = armature_matrix @ original.get('head', pb.head)
            head_screen = location_3d_to_region_2d(region, rv3d, head_world)
            if head_screen:
                new_screen = Vector((head_screen.x + delta.x, head_screen.y + delta.y))
                new_world = region_2d_to_location_3d(region, rv3d, new_screen, head_world)
                new_local = armature_matrix.inverted() @ new_world
                pb.location = original['location'] + (new_local - original.get('head', pb.head))

    def apply_scale_to_bones(self, context, bbox_start, delta, pivot_pos, is_proportional, handle_active):
        """Escala direcionada - mais próximo do S + X / S + Y"""
        obj = BoneManager.get_active_armature(context)
        if not obj or not constants._original_bones:
            return

        xmin, xmax, ymin, ymax = bbox_start

        dx_l = delta.x if handle_active in [constants.HandleType.LEFT, constants.HandleType.TOP_LEFT, constants.HandleType.BOTTOM_LEFT] else 0
        dx_r = delta.x if handle_active in [constants.HandleType.RIGHT, constants.HandleType.TOP_RIGHT, constants.HandleType.BOTTOM_RIGHT] else 0
        dy_t = delta.y if handle_active in [constants.HandleType.TOP, constants.HandleType.TOP_LEFT, constants.HandleType.TOP_RIGHT] else 0
        dy_b = delta.y if handle_active in [constants.HandleType.BOTTOM, constants.HandleType.BOTTOM_LEFT, constants.HandleType.BOTTOM_RIGHT] else 0

        sx = (xmax + dx_r - (xmin + dx_l)) / (xmax - xmin) if (xmax - xmin) != 0 else 1.0
        sy = (ymax + dy_t - (ymin + dy_b)) / (ymax - ymin) if (ymax - ymin) != 0 else 1.0

        if is_proportional:
            s = min(abs(sx), abs(sy)) if sx != 0 and sy != 0 else max(abs(sx), abs(sy))
            sx = s * (1 if sx >= 0 else -1)
            sy = s * (1 if sy >= 0 else -1)

        for original in constants._original_bones.values():
            pb = original['pose_bone']
            if not pb:
                continue
            orig_basis = original['matrix_basis'].copy()

            # Escala no eixo X e Y da tela (aproximação forte do comportamento nativo)
            scale_mat = Matrix.Scale(sx, 4, Vector((1, 0, 0))) @ Matrix.Scale(sy, 4, Vector((0, 1, 0)))
            pb.matrix_basis = orig_basis @ scale_mat

        context.view_layer.update()

    def apply_rotation_to_bones(self, context, angle, pivot_pos):
        # (mantido simples - use a versão anterior se precisar ajustar)
        obj = BoneManager.get_active_armature(context)
        if not obj or not constants._original_bones:
            return
        cos_a = cos(angle)
        sin_a = sin(angle)
        region = context.region
        rv3d = BoneManager.get_region_3d(context)
        if not rv3d:
            return
        armature_matrix = obj.matrix_world

        for original in constants._original_bones.values():
            pb = original['pose_bone']
            if not pb:
                continue
            head_world = armature_matrix @ pb.head
            head_screen = location_3d_to_region_2d(region, rv3d, head_world)
            if head_screen:
                rel = head_screen - pivot_pos
                rotated = Vector((rel.x * cos_a - rel.y * sin_a, rel.x * sin_a + rel.y * cos_a))
                new_screen = pivot_pos + rotated
                new_world = region_2d_to_location_3d(region, rv3d, new_screen, head_world)
                new_local = armature_matrix.inverted() @ new_world
                pb.location = new_local - pb.head   # simplificado

    def update_bbox(self, context):
        _, _, screen_points, _ = BoneManager.get_selected_bones(context)
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
    bl_idname = "pose.activate_bbox_tool"
    bl_label = "Ativar BBox Tool"
    bl_description = "Ativa a ferramenta de bounding box"
    bl_options = {'REGISTER'}

    def execute(self, context):
        BoneManager.activate_tool("pose.wst_bbox_tool")
        return {'FINISHED'}
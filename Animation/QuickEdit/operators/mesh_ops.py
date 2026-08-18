# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025, Rapadura Atômica. All rights reserved.
"""Seleção e transformação de meshes de cenário (BGs) sem sair do modo Draw."""

import bpy
from math import atan2
from mathutils import Vector, Matrix
from bpy_extras.view3d_utils import (
    location_3d_to_region_2d, region_2d_to_location_3d,
    region_2d_to_origin_3d, region_2d_to_vector_3d
)

from ..core import constants
from ..core.utilities import calculate_screen_bbox, get_bbox_center, get_handle_under_mouse
from ..compatibility.api_router import obj_is_gp

# Quantos objetos não-mesh o raio pode atravessar antes de desistir
MAX_RAYCAST_STEPS = 8
RAY_EPSILON = 1e-4

# Tolerância para considerar que uma matriz cabe em location/rotation/scale
REPRESENTABLE_TOLERANCE = 1e-4

# Handles de cisalhamento: não se aplicam a objetos, que só guardam loc/rot/scale
SHEAR_HANDLES = (
    constants.HandleType.SHEAR_TOP, constants.HandleType.SHEAR_BOTTOM,
    constants.HandleType.SHEAR_LEFT, constants.HandleType.SHEAR_RIGHT
)

def is_representable(matrix):
    """Diz se a matriz sobrevive à decomposição em location/rotation/scale de um objeto.

    O Blender guarda objetos como loc/rot/scale, então cisalhamento é descartado em
    silêncio ao atribuir matrix_world. Isso detecta o caso antes de o usuário ver
    o objeto saltar.
    """
    location, rotation, scale = matrix.decompose()
    rebuilt = Matrix.LocRotScale(location, rotation, scale)

    basis = matrix.to_3x3()
    rebuilt_basis = rebuilt.to_3x3()

    # Tolerância relativa: BGs podem ter escalas muito grandes ou muito pequenas
    magnitude = max((abs(value) for row in basis for value in row), default=1.0)
    tolerance = REPRESENTABLE_TOLERANCE * max(1.0, magnitude)

    return all(abs(a - b) < tolerance
               for row, rebuilt_row in zip(basis, rebuilt_basis)
               for a, b in zip(row, rebuilt_row))

def get_mesh_target():
    """Retorna o mesh atualmente sob controle da BBox, ou None"""
    if not constants._mesh_target:
        return None

    obj = bpy.data.objects.get(constants._mesh_target)
    if obj is None or obj.type != 'MESH':
        constants._mesh_target = None
        return None

    return obj

def get_object_world_corners(context, obj):
    """Retorna os 8 cantos da bounding box do objeto em coordenadas de mundo"""
    eval_obj = obj
    try:
        eval_obj = obj.evaluated_get(context.evaluated_depsgraph_get())
    except Exception:
        pass

    matrix = obj.matrix_world
    return [matrix @ Vector(corner) for corner in eval_obj.bound_box]

def get_object_world_center(context, obj):
    """Centro da bounding box do objeto em coordenadas de mundo"""
    corners = get_object_world_corners(context, obj)
    center = Vector((0.0, 0.0, 0.0))
    for corner in corners:
        center += corner
    return center / len(corners)

def get_object_screen_bbox(context, obj):
    """Projeta a bounding box do objeto para coordenadas de tela"""
    from ..core.tool_manager import GPToolManager

    region = context.region
    rv3d = GPToolManager.get_region_3d(context)
    if not rv3d:
        return None

    screen_points = []
    for corner in get_object_world_corners(context, obj):
        screen_pos = location_3d_to_region_2d(region, rv3d, corner)
        if screen_pos:
            screen_points.append(screen_pos)

    if len(screen_points) < 2:
        return None

    return calculate_screen_bbox(context, screen_points)

def pick_mesh_under_mouse(context, mouse_pos):
    """Raycast que ignora tudo que não for MESH (atravessa os outros tipos)"""
    from ..core.tool_manager import GPToolManager

    region = context.region
    rv3d = GPToolManager.get_region_3d(context)
    if not rv3d:
        return None

    depsgraph = context.evaluated_depsgraph_get()
    origin = region_2d_to_origin_3d(region, rv3d, mouse_pos)
    direction = region_2d_to_vector_3d(region, rv3d, mouse_pos)

    ray_origin = origin.copy()
    for _ in range(MAX_RAYCAST_STEPS):
        hit, location, _normal, _index, hit_obj, _matrix = context.scene.ray_cast(
            depsgraph, ray_origin, direction
        )
        if not hit or hit_obj is None:
            break

        real_obj = hit_obj.original if hasattr(hit_obj, 'original') else hit_obj
        if real_obj.type == 'MESH' and not real_obj.hide_select:
            return real_obj

        # Não é mesh (ou não é selecionável): continua o raio logo atrás dele
        ray_origin = location + direction * RAY_EPSILON

    # Fallback: meshes sem geometria sob o cursor (planos de BG vistos de canto, etc.)
    return pick_mesh_by_screen_bounds(context, mouse_pos)

def pick_mesh_by_screen_bounds(context, mouse_pos):
    """Escolhe o mesh visível mais próximo cuja bounding box em tela contém o cursor"""
    from ..core.tool_manager import GPToolManager

    region = context.region
    rv3d = GPToolManager.get_region_3d(context)
    if not rv3d:
        return None

    view_origin = region_2d_to_origin_3d(region, rv3d, mouse_pos)
    best_obj = None
    best_distance = None

    for obj in context.visible_objects:
        if obj.type != 'MESH' or obj.hide_select:
            continue

        corners = get_object_world_corners(context, obj)
        screen_points = [location_3d_to_region_2d(region, rv3d, c) for c in corners]
        screen_points = [p for p in screen_points if p]
        if len(screen_points) < 2:
            continue

        xs = [p.x for p in screen_points]
        ys = [p.y for p in screen_points]
        if not (min(xs) <= mouse_pos.x <= max(xs) and min(ys) <= mouse_pos.y <= max(ys)):
            continue

        distance = (get_object_world_center(context, obj) - view_origin).length
        if best_distance is None or distance < best_distance:
            best_obj = obj
            best_distance = distance

    return best_obj

def insert_object_keyframe_if_auto(obj):
    """Insere keyframe de transformação no objeto se o Auto-Key estiver ligado"""
    if not bpy.context.scene.tool_settings.use_keyframe_insert_auto:
        return False

    if obj is None:
        return False

    frame = bpy.context.scene.frame_current
    rotation_path = 'rotation_quaternion' if obj.rotation_mode == 'QUATERNION' else 'rotation_euler'

    try:
        for data_path in ('location', rotation_path, 'scale'):
            obj.keyframe_insert(data_path=data_path, frame=frame)
    except Exception as e:
        print(f"QuickEdit: erro ao inserir keyframe em '{obj.name}': {e}")
        return False

    return True

class GPENCIL_OT_pick_mesh_object(bpy.types.Operator):
    """Ctrl+Clique: seleciona apenas objetos Mesh (BGs de cenário) sob o cursor"""
    bl_idname = "gpencil.pick_mesh_object"
    bl_label = "Selecionar Mesh de Cenário"
    bl_description = "Detecta somente objetos do tipo Mesh sob o cursor e abre a BBox de transformação"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return (context.object and
                obj_is_gp(context.object) and
                context.object.mode == 'PAINT_GREASE_PENCIL')

    def invoke(self, context, event):
        mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))
        obj = pick_mesh_under_mouse(context, mouse_pos)

        if obj is None:
            constants._mesh_target = None
            self.report({'INFO'}, "Nenhum mesh sob o cursor")
            return {'PASS_THROUGH'}

        constants._mesh_target = obj.name
        self.report({'INFO'}, f"Mesh: {obj.name}")

        # O modal roda por conta própria; este operador não pode devolver RUNNING_MODAL
        # sem ter registrado o próprio handler
        bpy.ops.gpencil.mesh_bbox_transform('INVOKE_DEFAULT')
        return {'FINISHED'}

class GPENCIL_OT_mesh_bbox_transform(bpy.types.Operator):
    """BBox de transformação para um mesh de cenário, sem sair do modo Draw"""
    bl_idname = "gpencil.mesh_bbox_transform"
    bl_label = "Mesh BBox Transform"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        obj = get_mesh_target()
        if obj is None:
            self.report({'ERROR'}, "Nenhum mesh selecionado")
            return {'CANCELLED'}

        bbox = get_object_screen_bbox(context, obj)
        if not bbox:
            self.report({'ERROR'}, "Não foi possível calcular a bounding box do mesh")
            constants._mesh_target = None
            return {'CANCELLED'}

        bpy.ops.ed.undo_push(message="Before Mesh BBox Transform")

        constants._bbox_data = bbox
        constants._pivot_pos = get_bbox_center(bbox)

        self.handle_hover = constants.HandleType.NONE
        self.handle_active = constants.HandleType.NONE
        self.mouse_start = Vector((0, 0))
        self.bbox_start = bbox
        self.is_proportional = False
        self._original_matrix = obj.matrix_world.copy()
        self._pivot_world = self.compute_pivot_world(context, obj)
        self._start_center_world = get_object_world_center(context, obj)
        self._transformed = False
        self._last_view_matrix = None
        self._last_persp_matrix = None
        self.remember_view(context)

        if constants._mesh_bbox_handle is None:
            constants._mesh_bbox_handle = bpy.types.SpaceView3D.draw_handler_add(
                self.draw_callback, (context,), 'WINDOW', 'POST_PIXEL'
            )

        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        obj = get_mesh_target()
        if obj is None or not constants._bbox_data:
            self.finish(context)
            return {'CANCELLED'}

        # Ctrl+Clique novamente: troca de mesh alvo
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS' and event.ctrl:
            self.finish(context)
            bpy.ops.gpencil.pick_mesh_object('INVOKE_DEFAULT')
            return {'FINISHED'}

        # Navegação de câmera: recalcula a BBox depois de passar o evento adiante
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            self.update_bbox_from_view(context, obj)
            return {'PASS_THROUGH'}

        if event.ctrl and event.type == 'Z' and event.value == 'PRESS':
            self.finish(context)
            return {'PASS_THROUGH'}

        if event.type in {'RIGHTMOUSE', 'ESC'}:
            self.finish(context)
            return {'CANCELLED'}

        self.is_proportional = event.shift
        mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))

        # A view pode ter mudado por atalho de teclado (Numpad, etc.)
        self.update_bbox_from_view(context, obj)

        # Hover nos handles
        if event.type == 'MOUSEMOVE' and self.handle_active == constants.HandleType.NONE:
            handle_under_mouse = self.get_handle(mouse_pos)

            if handle_under_mouse in [constants.HandleType.ROTATE_TOP_LEFT, constants.HandleType.ROTATE_TOP_RIGHT,
                                        constants.HandleType.ROTATE_BOTTOM_LEFT, constants.HandleType.ROTATE_BOTTOM_RIGHT]:
                context.window.cursor_modal_set('SCROLL_XY')
            elif handle_under_mouse == constants.HandleType.PIVOT:
                context.window.cursor_modal_set('CROSSHAIR')
            else:
                context.window.cursor_modal_set('DEFAULT')

            self.handle_hover = handle_under_mouse if handle_under_mouse != constants.HandleType.NONE else self.handle_hover
            context.area.tag_redraw()

        # Arrasto
        if event.type == 'MOUSEMOVE' and self.handle_active != constants.HandleType.NONE:
            delta = mouse_pos - self.mouse_start

            if self.is_proportional:
                context.window.cursor_modal_set('CROSSHAIR')

            # Move apenas o pivot (não transforma o objeto)
            if self.handle_active == constants.HandleType.PIVOT:
                xmin, xmax, ymin, ymax = constants._bbox_data
                margin = 10
                new_x = max(xmin + margin, min(event.mouse_region_x, xmax - margin))
                new_y = max(ymin + margin, min(event.mouse_region_y, ymax - margin))
                constants._pivot_pos = Vector((new_x, new_y))
                self._pivot_world = self.compute_pivot_world(context, obj)
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}

            # Rotação em torno do eixo da view
            if self.handle_active in [constants.HandleType.ROTATE_TOP_LEFT, constants.HandleType.ROTATE_TOP_RIGHT,
                                      constants.HandleType.ROTATE_BOTTOM_LEFT, constants.HandleType.ROTATE_BOTTOM_RIGHT]:
                pivot_pos = constants._pivot_pos if constants._pivot_pos else get_bbox_center(self.bbox_start)
                vec_current = mouse_pos - pivot_pos
                current_angle = atan2(vec_current.y, vec_current.x)
                if not hasattr(self, '_start_angle'):
                    self._start_angle = current_angle

                self.apply_rotation(context, obj, current_angle - self._start_angle)
                self.refresh_bbox(context, obj, keep_pivot=True)
                return {'RUNNING_MODAL'}

            # Translação
            elif self.handle_active == constants.HandleType.CENTER:
                self.apply_translation(context, obj, delta)
                self.refresh_bbox(context, obj, keep_pivot=False)
                return {'RUNNING_MODAL'}

            # Escala
            else:
                xmin, xmax, ymin, ymax = self.bbox_start

                delta_x_left = delta.x if self.handle_active in [
                    constants.HandleType.LEFT, constants.HandleType.TOP_LEFT, constants.HandleType.BOTTOM_LEFT] else 0
                delta_x_right = delta.x if self.handle_active in [
                    constants.HandleType.RIGHT, constants.HandleType.TOP_RIGHT, constants.HandleType.BOTTOM_RIGHT] else 0
                delta_y_top = delta.y if self.handle_active in [
                    constants.HandleType.TOP, constants.HandleType.TOP_LEFT, constants.HandleType.TOP_RIGHT] else 0
                delta_y_bottom = delta.y if self.handle_active in [
                    constants.HandleType.BOTTOM, constants.HandleType.BOTTOM_LEFT, constants.HandleType.BOTTOM_RIGHT] else 0

                original_width = xmax - xmin
                original_height = ymax - ymin

                scale_x = ((xmax + delta_x_right) - (xmin + delta_x_left)) / original_width if original_width else 1.0
                scale_y = ((ymax + delta_y_top) - (ymin + delta_y_bottom)) / original_height if original_height else 1.0

                if self.is_proportional:
                    uniform_scale = min(scale_x, scale_y) if scale_x > 0 and scale_y > 0 else max(scale_x, scale_y)
                    scale_x = uniform_scale
                    scale_y = uniform_scale

                self.apply_scale(context, obj, scale_x, scale_y)
                self.refresh_bbox(context, obj, keep_pivot=True)
                return {'RUNNING_MODAL'}

        # Início do arrasto
        elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            handle_under_mouse = self.get_handle(mouse_pos)
            if handle_under_mouse == constants.HandleType.NONE:
                self.finish(context)
                return {'CANCELLED'}

            self.handle_active = handle_under_mouse
            self.mouse_start = mouse_pos
            self.bbox_start = constants._bbox_data
            self.is_proportional = event.shift

            # Congela o estado de partida deste arrasto
            self._original_matrix = obj.matrix_world.copy()
            self._start_center_world = get_object_world_center(context, obj)
            self._pivot_world = self.compute_pivot_world(context, obj)
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

        return {'RUNNING_MODAL'}

    def get_handle(self, mouse_pos):
        """Handle sob o mouse, ignorando os de cisalhamento (não valem para objetos)"""
        handle = get_handle_under_mouse(constants._bbox_data, mouse_pos)
        return constants.HandleType.NONE if handle in SHEAR_HANDLES else handle

    def compute_pivot_world(self, context, obj):
        """Converte o pivot de tela para mundo, no plano paralelo à view que passa pelo objeto"""
        from ..core.tool_manager import GPToolManager

        region = context.region
        rv3d = GPToolManager.get_region_3d(context)
        center_world = get_object_world_center(context, obj)
        if not rv3d:
            return center_world

        pivot_screen = constants._pivot_pos
        if pivot_screen is None:
            pivot_screen = get_bbox_center(constants._bbox_data or self.bbox_start)
        if pivot_screen is None:
            return center_world

        return region_2d_to_location_3d(region, rv3d, pivot_screen, center_world)

    def get_view_basis(self, context):
        """Matriz 4x4 cujos eixos são direita/cima/frente da tela em coordenadas de mundo"""
        from ..core.tool_manager import GPToolManager

        rv3d = GPToolManager.get_region_3d(context)
        if not rv3d:
            return Matrix.Identity(4)
        return rv3d.view_rotation.to_matrix().to_4x4()

    def build_around_pivot(self, local_matrix, view_basis=None):
        """Monta a matrix_world final para uma transformação de tela em torno do pivot"""
        pivot = self._pivot_world
        if view_basis is None:
            view_basis = Matrix.Identity(4)

        matrix = (Matrix.Translation(pivot) @ view_basis @ local_matrix @
                  view_basis.inverted() @ Matrix.Translation(-pivot))
        return matrix @ self._original_matrix

    def apply_matrix(self, obj, matrix):
        obj.matrix_world = matrix
        self._transformed = True

    def apply_translation(self, context, obj, delta):
        """Move o objeto acompanhando o mouse no plano da tela"""
        from ..core.tool_manager import GPToolManager

        region = context.region
        rv3d = GPToolManager.get_region_3d(context)
        if not rv3d:
            return

        start_center = self._start_center_world
        start_screen = location_3d_to_region_2d(region, rv3d, start_center)
        if not start_screen:
            return

        new_world = region_2d_to_location_3d(region, rv3d, start_screen + delta, start_center)
        self.apply_matrix(obj, Matrix.Translation(new_world - start_center) @ self._original_matrix)

    def apply_scale(self, context, obj, scale_x, scale_y):
        """Escala nos eixos horizontal/vertical da tela, em torno do pivot"""
        # Evita colapsar o objeto a zero (matriz singular)
        scale_x = scale_x if abs(scale_x) > 1e-4 else 1e-4
        scale_y = scale_y if abs(scale_y) > 1e-4 else 1e-4

        if self.is_proportional:
            # Escala isotrópica: independe da view e sempre cabe em loc/rot/scale
            self.apply_isotropic_scale(obj, (scale_x + scale_y) / 2.0)
            return

        target = self.build_around_pivot(
            Matrix.Diagonal(Vector((scale_x, scale_y, 1.0, 1.0))),
            self.get_view_basis(context)
        )

        # Objetos guardam loc/rot/scale: uma matriz com cisalhamento (objeto girado em
        # relação à tela) seria descartada em silêncio pelo Blender. Testar ANTES de
        # atribuir, porque a leitura de volta já vem decomposta.
        if is_representable(target):
            self.apply_matrix(obj, target)
        else:
            self.apply_isotropic_scale(obj, (abs(scale_x) * abs(scale_y)) ** 0.5)
            self.warn_once("Objeto girado em relação à tela: escala aplicada de forma uniforme")

    def apply_isotropic_scale(self, obj, factor):
        """Escala uniforme nos três eixos, em torno do pivot"""
        factor = factor if abs(factor) > 1e-4 else 1e-4
        self.apply_matrix(obj, self.build_around_pivot(
            Matrix.Diagonal(Vector((factor, factor, factor, 1.0)))))

    def warn_once(self, message):
        """Evita floodar o report a cada MOUSEMOVE do arrasto"""
        if getattr(self, '_last_warning', None) == message:
            return
        self._last_warning = message
        self.report({'INFO'}, message)

    def apply_rotation(self, context, obj, angle):
        """Rotação em torno do eixo de visão, passando pelo pivot"""
        from ..core.tool_manager import GPToolManager

        rv3d = GPToolManager.get_region_3d(context)
        if not rv3d:
            return

        axis = rv3d.view_rotation @ Vector((0.0, 0.0, 1.0))
        self.apply_matrix(obj, self.build_around_pivot(Matrix.Rotation(angle, 4, axis)))

    def refresh_bbox(self, context, obj, keep_pivot=True):
        """Recalcula a BBox de tela a partir do objeto já transformado"""
        new_bbox = get_object_screen_bbox(context, obj)
        if new_bbox:
            constants._bbox_data = new_bbox
            if not keep_pivot:
                constants._pivot_pos = get_bbox_center(new_bbox)
                self._pivot_world = self.compute_pivot_world(context, obj)

        context.area.tag_redraw()

    def remember_view(self, context):
        """Guarda as matrizes da view; retorna True se elas mudaram desde a última chamada"""
        rv3d = context.region_data
        if not rv3d:
            return False

        current_view_matrix = rv3d.view_matrix.copy()
        current_persp_matrix = rv3d.perspective_matrix.copy()

        changed = (self._last_view_matrix != current_view_matrix or
                   self._last_persp_matrix != current_persp_matrix)

        self._last_view_matrix = current_view_matrix
        self._last_persp_matrix = current_persp_matrix
        return changed

    def update_bbox_from_view(self, context, obj):
        """Recalcula a BBox quando a view muda (zoom, pan, orbit)"""
        if self.handle_active != constants.HandleType.NONE:
            return

        if not self.remember_view(context):
            return

        new_bbox = get_object_screen_bbox(context, obj)
        if new_bbox:
            constants._bbox_data = new_bbox
            constants._pivot_pos = get_bbox_center(new_bbox)
            self._pivot_world = self.compute_pivot_world(context, obj)
            self.bbox_start = new_bbox

        context.area.tag_redraw()

    def draw_callback(self, context):
        from .transform_ops import draw_bbox

        draw_bbox(constants._bbox_data, self.handle_hover, self.handle_active,
                  self.is_proportional, color_override=constants.COLOR_BBOX_MESH,
                  show_shear=False)

    def finish(self, context):
        context.window.cursor_modal_restore()

        # Só marca a timeline se o mesh realmente foi transformado
        if getattr(self, '_transformed', False):
            insert_object_keyframe_if_auto(get_mesh_target())
            bpy.ops.ed.undo_push(message="Mesh BBox Transform")

        remove_mesh_bbox_handle()

        constants._bbox_data = None
        constants._pivot_pos = None
        constants._mesh_target = None

        if context.area:
            context.area.tag_redraw()

class GPENCIL_OT_clear_mesh_target(bpy.types.Operator):
    """Solta o mesh de cenário controlado pela BBox"""
    bl_idname = "gpencil.clear_mesh_target"
    bl_label = "Soltar Mesh"
    bl_description = "Encerra a BBox do mesh de cenário e volta para os strokes"

    def execute(self, context):
        constants._mesh_target = None
        constants._bbox_data = None
        constants._pivot_pos = None
        remove_mesh_bbox_handle()

        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}

def remove_mesh_bbox_handle():
    """Remove o draw handler da BBox de mesh, se existir"""
    if constants._mesh_bbox_handle is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(constants._mesh_bbox_handle, 'WINDOW')
        except Exception:
            pass
        constants._mesh_bbox_handle = None

def unregister():
    remove_mesh_bbox_handle()
    constants._mesh_target = None

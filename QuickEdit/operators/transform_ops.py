import bpy
import gpu
import blf
from gpu_extras.batch import batch_for_shader
from mathutils import Vector, Matrix
from math import atan2, pi, cos, sin
from bpy_extras.view3d_utils import region_2d_to_location_3d

from ..core import constants
from ..core.event_handler import BBoxEventHandler
from ..core.utilities import (
    calculate_screen_bbox, get_bbox_corners, get_bbox_center,
    get_handle_under_mouse, apply_transformation
)
from ..compatibility.api_router import obj_is_gp, layer_hidden, get_layer_frame_by_number, is_frame_valid
from ..ui.visual_feedback import StrokeHighlighter

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
        shader.uniform_float("color", (0.2, 0.8, 0.8, 0.8))  # Ciano para proporcional
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
        blf.draw(font_id, " ")

    # 3. Desenhar TODOS os handles normais (ESSE BLOCO DEVE FICAR INTACTO)
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

    # 4. Roda de rotação (se ativa/hover)
    if handle_active == constants.HandleType.ROTATION or handle_hover == constants.HandleType.ROTATION:
        shader.uniform_float("color", constants.COLOR_ROTATION)
        gpu.state.line_width_set(1)
        rotation_handle_pos = center + Vector((0, constants.ROTATION_HANDLE_DISTANCE))
        batch_line = batch_for_shader(shader, 'LINES', {"pos": [center, rotation_handle_pos]})
        batch_line.draw(shader)

    # 5. Desenhar o gizmo pivot (sempre no final, para sobrepor se necessário)
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

class GPENCIL_OT_bbox_transform(bpy.types.Operator):
    """Transformação interativa com bounding box para Grease Pencil com escala proporcional"""
    bl_idname = "gpencil.bbox_transform"
    bl_label = "GP BBox Transform"
    bl_options = {'REGISTER', 'UNDO'}

    def modal(self, context, event):
        from ..core.event_handler import BBoxEventHandler
        from ..core.tool_manager import GPToolManager
        from ..core.utilities import calculate_screen_bbox, get_bbox_center
        
        # Debug opcional (descomente para ver todos os eventos no console)
        # print(f"[BBox Modal] Evento: type={event.type} | ctrl={event.ctrl} | shift={event.shift} | alt={event.alt} | value={event.value} | mouse=({event.mouse_region_x}, {event.mouse_region_y})")
        
        # 1. Checa se o evento deve passar para outros operadores (clipboard, delete, undo, navegação, etc.)
        if BBoxEventHandler.handle_event(context, event, self):
            # Se passou, ainda redesenha se necessário (hover, etc.)
            if event.type == 'MOUSEMOVE':
                context.area.tag_redraw()
            return {'PASS_THROUGH'}

        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            self.update_bbox(context)
            return {'PASS_THROUGH'}
        
        # 2. Fallback manual para clipboard (garante que funcione mesmo com modal ativo)
        if event.ctrl and event.value == 'PRESS':
            if event.type == 'C':
                print("[BBox Modal] Ctrl+C detectado manualmente → executando copy")
                bpy.ops.gpencil.copy_strokes()
                return {'PASS_THROUGH'}
            elif event.type == 'V':
                print("[BBox Modal] Ctrl+V detectado manualmente → executando paste")
                bpy.ops.gpencil.paste_strokes()
                return {'PASS_THROUGH'}
            elif event.type == 'X':
                print("[BBox Modal] Ctrl+X detectado manualmente → executando cut")
                bpy.ops.gpencil.cut_strokes_simple()
                return {'PASS_THROUGH'}
        
        # 3. Atualiza estado proporcional em tempo real (Shift para escala uniforme)
        self.is_proportional = event.shift
        
        # 4. Se não há mais BBox (seleção vazia ou cancelada), finaliza
        if not constants._bbox_data:
            self.finish(context)
            return {'CANCELLED'}
        
        mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))
        
        # 5. Recalcula BBox se a view mudou (zoom, pan, rotate)
        current_view_matrix = context.region_data.view_matrix.copy()
        current_persp_matrix = context.region_data.perspective_matrix.copy()
        if not hasattr(self, '_last_view_matrix'):
            self._last_view_matrix = current_view_matrix
            self._last_persp_matrix = current_persp_matrix
        
        view_changed = (self._last_view_matrix != current_view_matrix or
                        self._last_persp_matrix != current_persp_matrix)
        
        if view_changed:
            world_points, screen_points, point_indices = GPToolManager.get_selected_points(context)
            if screen_points:
                new_bbox = calculate_screen_bbox(context, screen_points)
                constants._bbox_data = new_bbox
                constants._pivot_pos = get_bbox_center(new_bbox)
                # Atualiza pontos originais para manter referência correta
                constants._original_points.clear()
                constants._original_screen_points.clear()
                for idx, world_point in zip(point_indices, world_points):
                    constants._original_points[idx] = world_point.copy()
                for idx, screen_point in zip(point_indices, screen_points):
                    constants._original_screen_points[idx] = screen_point.copy()
            self._last_view_matrix = current_view_matrix
            self._last_persp_matrix = current_persp_matrix
            context.area.tag_redraw()
        
        # 6. Hover nos handles + cursor personalizado
        if event.type == 'MOUSEMOVE' and self.handle_active == constants.HandleType.NONE:
            handle_under_mouse = get_handle_under_mouse(constants._bbox_data, mouse_pos)
            # Cursor baseado no tipo de handle
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
        
        # 7. Arrasto de handles ou pivot
        if event.type == 'MOUSEMOVE' and self.handle_active != constants.HandleType.NONE:
            delta = mouse_pos - self.mouse_start
            
            # Atualiza cursor durante Shift (proporcional)
            if self.is_proportional:
                context.window.cursor_modal_set('CROSSHAIR')
            
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
                self.apply_rotation_2d(context, total_angle)
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            
            # Translação (CENTER)
            elif self.handle_active == constants.HandleType.CENTER:
                total_delta = mouse_pos - self.mouse_start
                self.apply_translation_from_original(context, total_delta)
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
                # Get pivot position
                if hasattr(constants, '_pivot_pos') and constants._pivot_pos is not None:
                    pivot_pos = constants._pivot_pos
                else:
                    pivot_pos = get_bbox_center(self.bbox_start)
                
                if self.handle_active in [constants.HandleType.SHEAR_LEFT, constants.HandleType.SHEAR_RIGHT]:
                    new_bbox = (
                        self.bbox_start[0] + (delta.x if self.handle_active == constants.HandleType.SHEAR_LEFT else 0),
                        self.bbox_start[1] + (delta.x if self.handle_active == constants.HandleType.SHEAR_RIGHT else 0),
                        self.bbox_start[2],
                        self.bbox_start[3]
                    )
                else:
                    new_bbox = (
                        self.bbox_start[0],
                        self.bbox_start[1],
                        self.bbox_start[2] + (delta.y if self.handle_active == constants.HandleType.SHEAR_BOTTOM else 0),
                        self.bbox_start[3] + (delta.y if self.handle_active == constants.HandleType.SHEAR_TOP else 0)
                    )
                
                # Aplica shear relativo ao pivot
                self.apply_shear_around_pivot(context, self.bbox_start, new_bbox, self.handle_active, pivot_pos)
                constants._bbox_data = new_bbox
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            
            # Escala (handles de canto e lados)
            else:
                pivot_pos = constants._pivot_pos if constants._pivot_pos else get_bbox_center(self.bbox_start)
                xmin, xmax, ymin, ymax = self.bbox_start
                
                # Calcula deltas por direção do handle
                delta_x_left   = delta.x if self.handle_active in [constants.HandleType.LEFT, constants.HandleType.TOP_LEFT, constants.HandleType.BOTTOM_LEFT] else 0
                delta_x_right  = delta.x if self.handle_active in [constants.HandleType.RIGHT, constants.HandleType.TOP_RIGHT, constants.HandleType.BOTTOM_RIGHT] else 0
                delta_y_top    = delta.y if self.handle_active in [constants.HandleType.TOP, constants.HandleType.TOP_LEFT, constants.HandleType.TOP_RIGHT] else 0
                delta_y_bottom = delta.y if self.handle_active in [constants.HandleType.BOTTOM, constants.HandleType.BOTTOM_LEFT, constants.HandleType.BOTTOM_RIGHT] else 0
                
                new_xmin = xmin + delta_x_left
                new_xmax = xmax + delta_x_right
                new_ymin = ymin + delta_y_bottom
                new_ymax = ymax + delta_y_top
                
                original_width  = xmax - xmin
                original_height = ymax - ymin
                
                scale_x = (new_xmax - new_xmin) / original_width if original_width != 0 else 1.0
                scale_y = (new_ymax - new_ymin) / original_height if original_height != 0 else 1.0
                
                # Proporcional (Shift)
                if self.is_proportional and self.handle_active in [
                    constants.HandleType.TOP_LEFT, constants.HandleType.TOP_RIGHT,
                    constants.HandleType.BOTTOM_LEFT, constants.HandleType.BOTTOM_RIGHT,
                    constants.HandleType.TOP, constants.HandleType.BOTTOM,
                    constants.HandleType.LEFT, constants.HandleType.RIGHT
                ]:
                    uniform_scale = min(scale_x, scale_y) if scale_x > 0 and scale_y > 0 else max(scale_x, scale_y)
                    scale_x = uniform_scale
                    scale_y = uniform_scale
                
                # Aplica escala nos pontos reais
                self.apply_scale_around_pivot(context, scale_x, scale_y, pivot_pos, self.handle_active)
                
                # Atualiza BBox visual (recalcula dos pontos reais)
                world_points, screen_points, _ = GPToolManager.get_selected_points(context)
                if screen_points:
                    constants._bbox_data = calculate_screen_bbox(context, screen_points)
                
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
            
            if hasattr(self, 'last_rotation_angle'):
                del self.last_rotation_angle
            
            # Salva pontos originais
            world_points, screen_points, point_indices = GPToolManager.get_selected_points(context)
            constants._original_points.clear()
            constants._original_screen_points.clear()
            for idx, world_point in zip(point_indices, world_points):
                constants._original_points[idx] = world_point.copy()
            for idx, screen_point in zip(point_indices, screen_points):
                constants._original_screen_points[idx] = screen_point.copy()
            
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
        from ..core.tool_manager import GPToolManager
        
        # Define pivot como centro da bbox inicial
        world_points, screen_points, point_indices = GPToolManager.get_selected_points(context)
        if not world_points:
            self.report({'ERROR'}, "Selecione alguns pontos primeiro")
            return {'CANCELLED'}
        
        constants._bbox_data = calculate_screen_bbox(context, screen_points)
        if not constants._bbox_data:
            self.report({'ERROR'}, "Não foi possível calcular a bounding box")
            return {'CANCELLED'}
        
        constants._pivot_pos = get_bbox_center(constants._bbox_data)
        
        bpy.ops.ed.undo_push(message="Before BBox Transform")

        obj = context.object
        if not obj or not obj_is_gp(obj):
            self.report({'ERROR'}, "Selecione um objeto Grease Pencil")
            return {'CANCELLED'}
        
        self.handle_hover = constants.HandleType.NONE
        self.handle_active = constants.HandleType.NONE
        self.mouse_start = Vector((0, 0))
        self.bbox_start = constants._bbox_data
        self.is_proportional = False
        
        global _bbox_handle
        if constants._bbox_handle is None:
            constants._bbox_handle = bpy.types.SpaceView3D.draw_handler_add(
                self.draw_callback, (context,), 'WINDOW', 'POST_PIXEL'
            )
        
        StrokeHighlighter.enable()

        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}
    
    def apply_scale_around_pivot(self, context, scale_x, scale_y, pivot_pos, handle_type):
        """Aplica escala relativa ao pivot"""
        from ..core.tool_manager import GPToolManager
        from bpy_extras.view3d_utils import region_2d_to_location_3d
        
        obj = context.object
        if not obj or not obj_is_gp(obj):
            return
        
        region = context.region
        rv3d = GPToolManager.get_region_3d(context)
        if not rv3d:
            return
        
        # Converte pivot para 3D para cálculos de profundidade
        pivot_depth = 0
        if constants._original_points:
            # Pega a profundidade do primeiro ponto como referência
            first_key = next(iter(constants._original_points))
            pivot_depth = constants._original_points[first_key].z
        
        # Aplica escala para cada ponto
        for (layer_name, stroke_idx, point_idx), original_screen_pos in constants._original_screen_points.items():
            # Encontra layer e frame
            target_layer = None
            for layer in obj.data.layers:
                if layer.name == layer_name:
                    target_layer = layer
                    break
            
            if not target_layer:
                continue
                
            target_frame = get_layer_frame_by_number(target_layer, context.scene.frame_current)
            if not target_frame or not is_frame_valid(target_frame):
                continue
            
            if stroke_idx < len(target_frame.drawing.strokes) and point_idx < len(target_frame.drawing.strokes[stroke_idx].points):
                point = target_frame.drawing.strokes[stroke_idx].points[point_idx]
                
                # Vetor relativo ao pivot
                rel_to_pivot = original_screen_pos - pivot_pos
                
                # Aplica escala
                scaled_rel = Vector((rel_to_pivot.x * scale_x, rel_to_pivot.y * scale_y))
                
                # Nova posição na tela
                new_screen_pos = pivot_pos + scaled_rel
                
                # Converte para 3D
                depth = constants._original_points[(layer_name, stroke_idx, point_idx)].z
                new_world_pos = region_2d_to_location_3d(region, rv3d, new_screen_pos, Vector((0, 0, depth)))
                
                # Aplica transformação
                point.position = obj.matrix_world.inverted() @ new_world_pos
    
    def apply_shear_around_pivot(self, context, bbox_start, bbox_end, handle_type, pivot_pos):
        """Aplica deformação de cisalhamento relativa ao pivot"""
        from ..core.tool_manager import GPToolManager
        from bpy_extras.view3d_utils import region_2d_to_location_3d
        
        obj = context.object
        if not obj or not obj_is_gp(obj):
            return
        
        # Calcula fator de shear
        if handle_type == constants.HandleType.SHEAR_LEFT:
            shear_amount = (bbox_end[0] - bbox_start[0]) / 100.0
        elif handle_type == constants.HandleType.SHEAR_RIGHT:
            shear_amount = (bbox_end[1] - bbox_start[1]) / 100.0
        elif handle_type == constants.HandleType.SHEAR_TOP:
            shear_amount = (bbox_end[3] - bbox_start[3]) / 100.0
        elif handle_type == constants.HandleType.SHEAR_BOTTOM:
            shear_amount = (bbox_end[2] - bbox_start[2]) / 100.0
        else:
            return
        
        region = context.region
        rv3d = GPToolManager.get_region_3d(context)
        if not rv3d:
            return
        
        # Aplica shear para cada ponto
        for (layer_name, stroke_idx, point_idx), original_screen_pos in constants._original_screen_points.items():
            # Encontra layer e frame
            target_layer = None
            for layer in obj.data.layers:
                if layer.name == layer_name:
                    target_layer = layer
                    break
            
            if not target_layer:
                continue
                
            target_frame = get_layer_frame_by_number(target_layer, context.scene.frame_current)
            if not target_frame or not is_frame_valid(target_frame):
                continue
            
            if stroke_idx < len(target_frame.drawing.strokes) and point_idx < len(target_frame.drawing.strokes[stroke_idx].points):
                point = target_frame.drawing.strokes[stroke_idx].points[point_idx]
                
                # Vetor relativo ao pivot
                rel_to_pivot = original_screen_pos - pivot_pos
                
                # Aplica transformação de shear
                if handle_type in [constants.HandleType.SHEAR_LEFT, constants.HandleType.SHEAR_RIGHT]:
                    # Shear horizontal
                    new_screen_pos = pivot_pos + Vector((
                        rel_to_pivot.x + shear_amount * rel_to_pivot.y,
                        rel_to_pivot.y
                    ))
                else:
                    # Shear vertical
                    new_screen_pos = pivot_pos + Vector((
                        rel_to_pivot.x,
                        rel_to_pivot.y + shear_amount * rel_to_pivot.x
                    ))
                
                # Converte para 3D
                depth = constants._original_points[(layer_name, stroke_idx, point_idx)].z
                new_world_pos = region_2d_to_location_3d(region, rv3d, new_screen_pos, Vector((0, 0, depth)))
                
                # Aplica transformação
                point.position = obj.matrix_world.inverted() @ new_world_pos
    
    def apply_translation_from_original(self, context, delta):
        """Aplica translação usando os pontos ORIGINAIS como referência"""
        from ..core.tool_manager import GPToolManager
        from bpy_extras.view3d_utils import region_2d_to_location_3d
        
        obj = context.object
        if not obj or not obj_is_gp(obj):
            return
        
        region = context.region
        rv3d = GPToolManager.get_region_3d(context)
        if not rv3d:
            return
        
        # DEBUG opcional
        # print(f"DEBUG: Aplicando translação delta={delta}")
        # print(f"DEBUG: Tem {len(constants._original_points)} pontos originais")
        
        # Aplica translação para cada ponto
        for (layer_name, stroke_idx, point_idx), original_world_pos in constants._original_points.items():
            # Encontra layer e frame
            target_layer = None
            for layer in obj.data.layers:
                if layer.name == layer_name:
                    target_layer = layer
                    break
            
            if not target_layer:
                continue
                
            target_frame = get_layer_frame_by_number(target_layer, context.scene.frame_current)
            if not target_frame or not is_frame_valid(target_frame):
                continue
            
            if stroke_idx < len(target_frame.drawing.strokes) and point_idx < len(target_frame.drawing.strokes[stroke_idx].points):
                point = target_frame.drawing.strokes[stroke_idx].points[point_idx]
                
                # Pega a posição ORIGINAL na tela
                if (layer_name, stroke_idx, point_idx) in constants._original_screen_points:
                    original_screen_pos = constants._original_screen_points[(layer_name, stroke_idx, point_idx)]
                else:
                    # Fallback: se não tiver screen point salvo, calcula a partir do world point
                    from ..core.utilities import world_to_screen
                    original_screen_pos = world_to_screen(context, original_world_pos)
                
                # Calcula NOVA posição na tela (translação simples)
                new_screen_pos = Vector((original_screen_pos.x + delta.x, original_screen_pos.y + delta.y))
                
                # Converte para 3D (mantém a mesma profundidade Z)
                depth = original_world_pos.z
                new_world_pos = region_2d_to_location_3d(region, rv3d, new_screen_pos, Vector((0, 0, depth)))
                
                # Aplica transformação
                point.position = obj.matrix_world.inverted() @ new_world_pos
        
        # DEBUG opcional
        # print(f"DEBUG: Translação aplicada a {len(constants._original_points)} pontos")

    def apply_rotation_2d(self, context, new_total_angle):
        """Aplica rotação 2D no espaço da tela relativa ao pivot"""
        from ..core.tool_manager import GPToolManager
        from bpy_extras.view3d_utils import region_2d_to_location_3d
        
        bpy.context.window.cursor_set("HAND")

        obj = context.object
        constants._total_rotation = new_total_angle

        if not obj or not obj_is_gp(obj):
            return
        
        # Get pivot position
        if hasattr(constants, '_pivot_pos') and constants._pivot_pos is not None:
            pivot_pos = constants._pivot_pos
        else:
            pivot_pos = get_bbox_center(self.bbox_start)
        
        cos_a = cos(constants._total_rotation)
        sin_a = sin(constants._total_rotation)
        
        region = context.region
        rv3d = GPToolManager.get_region_3d(context)
        if not rv3d:
            return
        
        # Aplica rotação para cada ponto
        for (layer_name, stroke_idx, point_idx), original_screen_pos in constants._original_screen_points.items():
            # Encontra layer e frame
            target_layer = None
            for layer in obj.data.layers:
                if layer.name == layer_name:
                    target_layer = layer
                    break
            
            if not target_layer:
                continue
                
            target_frame = get_layer_frame_by_number(target_layer, context.scene.frame_current)
            if not target_frame or not is_frame_valid(target_frame):
                continue
            
            if (stroke_idx < len(target_frame.drawing.strokes) and 
                point_idx < len(target_frame.drawing.strokes[stroke_idx].points)):
                
                point = target_frame.drawing.strokes[stroke_idx].points[point_idx]
                
                # Vetor relativo ao pivot
                rel_to_pivot = original_screen_pos - pivot_pos
                
                # Aplica rotação
                rotated_rel = Vector((
                    rel_to_pivot.x * cos_a - rel_to_pivot.y * sin_a,
                    rel_to_pivot.x * sin_a + rel_to_pivot.y * cos_a
                ))
                
                # Nova posição na tela
                rotated_screen = pivot_pos + rotated_rel
                
                # Converte para 3D
                depth = constants._original_points[(layer_name, stroke_idx, point_idx)].z
                new_world_pos = region_2d_to_location_3d(region, rv3d, rotated_screen, Vector((0, 0, depth)))
                
                # Aplica transformação
                point.position = obj.matrix_world.inverted() @ new_world_pos
    
    def reactivate_bbox(self, context):
        """Reativa a BBox após uma ação"""
        from ..core.tool_manager import GPToolManager

        world_points, screen_points, point_indices = GPToolManager.get_selected_points(context)
        if world_points:
            constants._bbox_data = calculate_screen_bbox(context, screen_points)
            constants._pivot_pos = get_bbox_center(constants._bbox_data)
            context.area.tag_redraw()
        else:
            # Se não há mais seleção, finalizar
            self.finish(context)

    def update_bbox_from_selection(self, context):
        """Atualiza a BBox quando a seleção muda"""
        from ..core.tool_manager import GPToolManager
        
        world_points, screen_points, point_indices = GPToolManager.get_selected_points(context)
        
        if world_points:
            constants._bbox_data = calculate_screen_bbox(context, screen_points)
            constants._pivot_pos = get_bbox_center(constants._bbox_data)
            
            # Atualizar pontos originais
            constants._original_points.clear()
            constants._original_screen_points.clear()

            for idx, world_point in zip(point_indices, world_points):
                constants._original_points[idx] = world_point.copy()

            for idx, screen_point in zip(point_indices, screen_points):
                constants._original_screen_points[idx] = screen_point.copy()
            
            context.area.tag_redraw()
        else:
            # Se não há mais seleção, finalizar a BBox
            self.finish(context)

    def update_bbox_after_action(self, context):
        """Atualiza ou finaliza a BBox após uma ação como delete"""
        from ..core.tool_manager import GPToolManager

        world_points, screen_points, point_indices = GPToolManager.get_selected_points(context)
        
        if world_points:
            # Atualizar a BBox com a nova seleção
            constants._bbox_data = calculate_screen_bbox(context, screen_points)
            constants._pivot_pos = get_bbox_center(constants._bbox_data)
            
            # Atualizar pontos originais
            constants._original_points.clear()
            constants._original_screen_points.clear()

            for idx, world_point in zip(point_indices, world_points):
                constants._original_points[idx] = world_point.copy()

            for idx, screen_point in zip(point_indices, screen_points):
                constants._original_screen_points[idx] = screen_point.copy()
            
            context.area.tag_redraw()
        else:
            # Se não há mais seleção, finalizar a BBox
            self.finish(context)
    
    def update_bbox(self, context):
        from ..core.tool_manager import GPToolManager
        from ..core.utilities import calculate_screen_bbox

        # Recalcula BBox quando a view muda (zoom, pan, rotate)
        current_view_matrix = context.region_data.view_matrix.copy()
        current_persp_matrix = context.region_data.perspective_matrix.copy()

        if not hasattr(self, '_last_view_matrix'):
            self._last_view_matrix = current_view_matrix
            self._last_persp_matrix = current_persp_matrix

        view_changed = (self._last_view_matrix != current_view_matrix or
                        self._last_persp_matrix != current_persp_matrix)

        if view_changed:
            world_points, screen_points, point_indices = GPToolManager.get_selected_points(context)
            if screen_points:
                new_bbox = calculate_screen_bbox(context, screen_points)
                constants._bbox_data = new_bbox
                constants._pivot_pos = get_bbox_center(new_bbox)

                # Atualiza pontos originais (mantém referência correta)
                constants._original_points.clear()
                constants._original_screen_points.clear()
                for idx, world_point in zip(point_indices, world_points):
                    constants._original_points[idx] = world_point.copy()
                for idx, screen_point in zip(point_indices, screen_points):
                    constants._original_screen_points[idx] = screen_point.copy()

            self._last_view_matrix = current_view_matrix
            self._last_persp_matrix = current_persp_matrix
            context.area.tag_redraw()

    def draw_callback(self, context):
        draw_bbox(constants._bbox_data, self.handle_hover, self.handle_active, self.is_proportional)
    
    def finish(self, context):
        context.window.cursor_modal_restore()
        from ..compatibility.api_router import insert_gp_keyframe_if_auto
        insert_gp_keyframe_if_auto(context.object)
        
        bpy.ops.ed.undo_push(message="BBox Transform")

        if constants._bbox_handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(constants._bbox_handle, 'WINDOW')
            constants._bbox_handle = None
        
        constants._bbox_data = None
        constants._pivot_pos = None
        constants._original_points.clear()
        constants._original_screen_points.clear()
        
        context.area.tag_redraw()

class GPENCIL_OT_activate_bbox_tool(bpy.types.Operator):
    bl_idname = "gpencil.activate_bbox_tool"
    bl_label = "Ativar Ferramenta BBox"
    bl_description = "Ativa a ferramenta de bounding box"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from ..core.tool_manager import GPToolManager

        GPToolManager.activate_tool("gpencil.wst_bbox_tool")
        return {'FINISHED'}

class GPENCIL_OT_auto_activate_bbox(bpy.types.Operator):
    bl_idname = "gpencil.auto_activate_bbox"
    bl_label = "Ativar BBox Automaticamente"
    
    def execute(self, context):
        bpy.ops.wm.tool_set_by_id(name="gpencil.wst_bbox_tool")
        return {'FINISHED'}
    
class GPENCIL_OT_flip_horizontal(bpy.types.Operator):
    """Flip horizontal com um clique"""
    bl_idname = "gpencil.flip_horizontal"
    bl_label = "Flip Horizontal"
    bl_description = "Flip horizontal dos strokes selecionados"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        from ..compatibility.api_router import obj_is_gp
        return context.object and obj_is_gp(context.object)
    
    def execute(self, context):
        try:
            # Usar operador nativo de mirror
            bpy.ops.transform.mirror(constraint_axis=(True, False, False))
            self.report({'INFO'}, "Flip horizontal aplicado")
        except Exception as e:
            self.report({'ERROR'}, f"Erro no flip: {str(e)}")
        
        return {'FINISHED'}

class GPENCIL_OT_flip_vertical(bpy.types.Operator):
    """Flip vertical com um clique"""
    bl_idname = "gpencil.flip_vertical"
    bl_label = "Flip Vertical"
    bl_description = "Flip vertical dos strokes selecionados"
    bl_options = {'REGISTER', 'UNDO'}
    
    direction: bpy.props.EnumProperty(
        items=[
            ('HORIZONTAL', "Horizontal", "Flip horizontal"),
            ('VERTICAL', "Vertical", "Flip vertical"),
        ],
        default='HORIZONTAL'
    ) # type: ignore
    
    @classmethod
    def poll(cls, context):
        from ..compatibility.api_router import obj_is_gp
        return context.object and obj_is_gp(context.object)
    
    def execute(self, context):
        try:
            if self.direction == 'HORIZONTAL':
                bpy.ops.transform.mirror(constraint_axis=(True, False, False))
            else:
                bpy.ops.transform.mirror(constraint_axis=(False, True, False))
            
            self.report({'INFO'}, f"Flip {self.direction.lower()} aplicado")
        except Exception as e:
            self.report({'ERROR'}, f"Erro no flip: {str(e)}")
        
        return {'FINISHED'}

class GPENCIL_OT_rotate_90(bpy.types.Operator):
    """Rotação de 90° com um clique"""
    bl_idname = "gpencil.rotate_90"
    bl_label = "Rotate 90°"
    bl_description = "Rotação de 90° dos strokes selecionados"
    bl_options = {'REGISTER', 'UNDO'}
    
    direction: bpy.props.EnumProperty(
        items=[
            ('CW', "Clockwise", "Rotação horária (90°)"),
            ('CCW', "Counter Clockwise", "Rotação anti-horária (90°)"),
        ],
        default='CW'
    ) # type: ignore
    
    @classmethod
    def poll(cls, context):
        from ..compatibility.api_router import obj_is_gp
        return context.object and obj_is_gp(context.object)
    
    def execute(self, context):
        try:
            # Mudar para modo transformação
            bpy.ops.transform.rotate(value=3.14159/2 if self.direction == 'CW' else -3.14159/2)
            self.report({'INFO'}, f"Rotação 90° {self.direction} aplicada")
        except Exception as e:
            self.report({'ERROR'}, f"Erro na rotação: {str(e)}")
        
        return {'FINISHED'}

class GPENCIL_OT_scale_uniform(bpy.types.Operator):
    """Escala uniforme rápida"""
    bl_idname = "gpencil.scale_uniform"
    bl_label = "Scale Uniform"
    bl_description = "Escala uniforme rápida (150%, 50%)"
    bl_options = {'REGISTER', 'UNDO'}
    
    factor: bpy.props.FloatProperty(
        name="Factor",
        default=1.5,
        min=0.1,
        max=10.0
    ) # type: ignore
    
    @classmethod
    def poll(cls, context):
        from ..compatibility.api_router import obj_is_gp
        return context.object and obj_is_gp(context.object)
    
    def execute(self, context):
        try:
            bpy.ops.transform.resize(value=(self.factor, self.factor, self.factor))
            self.report({'INFO'}, f"Escala {self.factor:.1f}x aplicada")
        except Exception as e:
            self.report({'ERROR'}, f"Erro na escala: {str(e)}")
        
        return {'FINISHED'}

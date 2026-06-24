import bpy
import gpu
import blf
from math import cos, sin
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from bpy_extras.view3d_utils import location_3d_to_region_2d

from ..compatibility.api_router import (
    obj_is_gp, layer_hidden, get_layer_frame_by_number, is_frame_valid
)

class StrokeHighlighter:
    """Sistema de highlight visual para strokes selecionados"""
    
    _draw_handler = None
    _enabled = False
    
    @classmethod
    def enable(cls):
        if cls._draw_handler is not None:
            print("StrokeHighlighter: handler já existe, não registrando novo")
            return
        cls._draw_handler = bpy.types.SpaceView3D.draw_handler_add(
            cls.draw_callback, (), 'WINDOW', 'POST_PIXEL'
        )
        cls._enabled = True
        print("StrokeHighlighter ATIVADO! Handler registrado:", cls._draw_handler)
    
    @classmethod
    def disable(cls):
        """Desativa o sistema de highlight"""
        if cls._draw_handler is not None:
            bpy.types.SpaceView3D.draw_handler_remove(cls._draw_handler, 'WINDOW')
            cls._draw_handler = None
            cls._enabled = False
    
    @classmethod
    def toggle(cls):
        """Alterna o estado do highlight"""
        if cls._enabled:
            cls.disable()
        else:
            cls.enable()
    
    @classmethod
    def draw_callback(cls):
        context = bpy.context
        if not context.object or not obj_is_gp(context.object):
            return

        obj = context.object
        region = context.region
        rv3d = context.region_data
        if not rv3d:
            return

        # Configurações do highlight simples: só linha laranja vibrante
        SELECTED_COLOR = (1.0, 0.6, 0.0, 1.0)  # Laranja vibrante (ajuste se quiser)
        LINE_WIDTH = 0.5                       # Grossura confortável (2.5 a 4.0 fica bom)

        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('NONE')

        try:
            for layer in obj.data.layers:
                if layer_hidden(layer):
                    continue

                target_frame = get_layer_frame_by_number(layer, context.scene.frame_current)
                if not target_frame or not is_frame_valid(target_frame):
                    continue

                drawing = target_frame.drawing
                for stroke in drawing.strokes:
                    # Só desenhar se o stroke tiver algum ponto selecionado ou ele mesmo estiver selecionado
                    has_selection = stroke.select or any(point.select for point in stroke.points)
                    if not has_selection:
                        continue

                    # Coleta coordenadas na tela
                    screen_points = []
                    for point in stroke.points:
                        world_pos = obj.matrix_world @ point.position
                        screen_pos = location_3d_to_region_2d(region, rv3d, world_pos)
                        if screen_pos:
                            screen_points.append(screen_pos)

                    if len(screen_points) < 2:
                        continue

                    gpu.state.line_width_set(LINE_WIDTH)
                    batch_line = batch_for_shader(shader, 'LINE_STRIP', {"pos": screen_points})
                    shader.bind()
                    shader.uniform_float("color", (SELECTED_COLOR))  # laranja Edit-like
                    batch_line.draw(shader)

        except Exception as e:
            print(f"Erro no highlight visual: {e}")

        finally:
            gpu.state.blend_set('NONE')
            gpu.state.line_width_set(1.0)

    @classmethod
    def update_for_selection(cls, context):
        """Força atualização do highlight quando a seleção muda"""
        if cls._enabled and context.area:
            context.area.tag_redraw()

# Sistema automático que ativa/desativa baseado no modo
class AutoStrokeHighlighter:
    """Ativa/desativa automaticamente o highlight baseado no contexto"""
    
    @staticmethod
    def update_highlight_state(context):
        """Atualiza estado do highlight baseado no contexto atual"""
        if (context.object and 
            obj_is_gp(context.object) and 
            context.object.mode == 'PAINT_GREASE_PENCIL'):
            
            StrokeHighlighter.enable()
        else:
            StrokeHighlighter.disable()
    
    @staticmethod
    def setup_handlers():
        """Configura handlers para atualização automática"""
        # Handler para mudanças de seleção
        bpy.app.handlers.depsgraph_update_post.append(AutoStrokeHighlighter._on_depsgraph_update)
    
    @staticmethod
    def _on_depsgraph_update(scene, depsgraph):
        """Callback para atualizações do depsgraph (seleção muda)"""
        for update in depsgraph.updates:
            if hasattr(update.id, 'type') and update.id.type == 'GREASEPENCIL':
                # GPencil foi modificado, atualizar highlight
                if bpy.context.area:
                    bpy.context.area.tag_redraw()
                break
import bpy
import gpu
import blf
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from bpy_extras.view3d_utils import location_3d_to_region_2d

from ..core import constants
from ..compatibility.api_router import obj_is_gp, layer_hidden, get_layer_frame_by_number, layer_locked

class GPENCIL_OT_draw_mode_box_select(bpy.types.Operator):
    bl_idname = "gpencil.draw_mode_box_select"
    bl_label = "Box Select no Draw Mode"
    bl_options = {'REGISTER', 'UNDO'}

    def modal(self, context, event):
        from ..core.tool_manager import GPToolManager

        if event.type == 'MOUSEMOVE':
            self.end_x = event.mouse_region_x
            self.end_y = event.mouse_region_y
            context.area.tag_redraw()

        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            self.execute_selection(context, event)
            
            world_points, _, _ = GPToolManager.get_selected_points(context)
            if world_points:
                bpy.ops.gpencil.bbox_transform('INVOKE_DEFAULT')
            else:
                GPToolManager.activate_tool("gpencil.wst_select_tool")
            
            return self.finish(context)

        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            return self.finish(context)

        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        if not self.poll(context):
            self.report({'WARNING'}, "Selecione um objeto Grease Pencil no modo Draw")
            return {'CANCELLED'}

        if hasattr(context.scene, 'gpencil_select_mode'):
            context.scene.gpencil_select_mode = 'BOX'

        self.start_x = event.mouse_region_x
        self.start_y = event.mouse_region_y
        self.end_x = self.start_x
        self.end_y = self.start_y
        self.drawing = True

        self._handle = bpy.types.SpaceView3D.draw_handler_add(
            self.draw_callback, (context,), 'WINDOW', 'POST_PIXEL'
        )
        
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    @classmethod
    def poll(cls, context):
        return (context.object and 
                obj_is_gp(context.object) and 
                context.object.mode == 'PAINT_GREASE_PENCIL')

    def execute_selection(self, context, event):
        from ..core.tool_manager import GPToolManager
        """Executa a seleção real dos pontos com box, ignorando layers locked/hidden"""
        obj = context.object
        current_mode = obj.mode
        selection_successful = False
        ignored_locked = 0  # Contador para feedback

        try:
            bpy.ops.object.mode_set(mode='EDIT')
            gpencil = obj.data

            select_mode = 'SET'
            if event.shift:
                select_mode = 'ADD'
            elif event.ctrl:
                select_mode = 'SUB'

            region = context.region
            rv3d = GPToolManager.get_region_3d(context)

            total_selected_points = 0

            for layer in gpencil.layers:
                # Ignora layers locked (travadas)
                if layer_locked(layer):
                    ignored_locked += 1
                    continue

                # Ignora layers ocultas
                if layer_hidden(layer):
                    continue

                target_frame = get_layer_frame_by_number(layer, context.scene.frame_current)
                if not target_frame or not hasattr(target_frame, 'drawing') or not target_frame.drawing:
                    continue

                drawing = target_frame.drawing

                for stroke in drawing.strokes:
                    selected_in_this_stroke = 0
                    total_points_in_stroke = len(stroke.points)

                    # Resetar seleção do stroke se for modo SET
                    if select_mode == 'SET':
                        stroke.select = False

                    for point in stroke.points:
                        screen_coord = location_3d_to_region_2d(region, rv3d, obj.matrix_world @ point.position)
                        if screen_coord:
                            min_x = min(self.start_x, self.end_x)
                            max_x = max(self.start_x, self.end_x)
                            min_y = min(self.start_y, self.end_y)
                            max_y = max(self.start_y, self.end_y)

                            if (min_x <= screen_coord.x <= max_x and min_y <= screen_coord.y <= max_y):
                                # Selecionar o ponto individualmente
                                if select_mode in {'SET', 'ADD'}:
                                    point.select = True
                                elif select_mode == 'SUB':
                                    point.select = False
                                else:
                                    point.select = False

                                if point.select:
                                    selected_in_this_stroke += 1
                                    total_selected_points += 1

                    # Se pelo menos 1 ponto foi selecionado, marca o stroke como parcialmente selecionado
                    if selected_in_this_stroke > 0:
                        stroke.select = True

            selection_successful = total_selected_points > 0
            context.area.tag_redraw()

            # Feedback opcional
            if ignored_locked > 0:
                self.report({'INFO'}, f"{ignored_locked} layer(s) locked ignorada(s) durante a seleção")

        except Exception as e:
            self.report({'ERROR'}, f"Erro na seleção: {str(e)}")
            selection_successful = False

        finally:
            if current_mode == 'PAINT_GREASE_PENCIL':
                bpy.ops.object.mode_set(mode='PAINT_GREASE_PENCIL')

        if selection_successful:
            GPToolManager.check_selection_and_activate_bbox(context)
            GPToolManager.update_selection_visuals(context)

        return selection_successful

    def finish(self, context):
        """Finaliza a operação e limpa recursos"""
        if hasattr(self, '_handle') and self._handle:
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
        
        self.drawing = False
        context.area.tag_redraw()
        return {'FINISHED'}

    def draw_callback(self, context):
        """Desenha o retângulo de seleção na tela"""
        if not hasattr(self, 'drawing') or not self.drawing:
            return

        color = (1.0, 1.0, 0.5, 0.3)
        border_color = (1.0, 0.8, 0.0, 1.0)

        x1, y1 = self.start_x, self.start_y
        x2, y2 = self.end_x, self.end_y
        
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        batch = batch_for_shader(shader, 'TRI_STRIP', {
            "pos": [(x1, y1), (x2, y1), (x1, y2), (x2, y2)]
        })
        
        gpu.state.blend_set('ALPHA')
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)
        
        coords = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        indices = ((0, 1), (1, 2), (2, 3), (3, 0))
        border_batch = batch_for_shader(shader, 'LINES', {"pos": coords}, indices=indices)
        shader.uniform_float("color", border_color)
        border_batch.draw(shader)
        
        gpu.state.blend_set('NONE')

    def cancel(self, context):
        return self.finish(context)

class GPENCIL_OT_draw_mode_lasso_select(bpy.types.Operator):
    bl_idname = "gpencil.draw_mode_lasso_select"
    bl_label = "Lasso Select no Draw Mode"
    bl_options = {'REGISTER', 'UNDO'}

    def modal(self, context, event):
        from ..core.tool_manager import GPToolManager
        if event.type == 'MOUSEMOVE':
            current_pos = (event.mouse_region_x, event.mouse_region_y)
            if len(self.points) == 0 or (Vector(current_pos) - Vector(self.points[-1])).length > 2.0:
                self.points.append(current_pos)
            context.area.tag_redraw()

        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            if len(self.points) > 2:
                self.execute_selection(context, event)
                
                world_points, _, _ = GPToolManager.get_selected_points(context)
                if world_points:
                    bpy.ops.gpencil.bbox_transform('INVOKE_DEFAULT')
                else:
                    GPToolManager.activate_tool("gpencil.wst_select_tool")
            
            return self.finish(context)

        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            return self.finish(context)

        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        if not self.poll(context):
            self.report({'WARNING'}, "Selecione um objeto Grease Pencil no modo Draw")
            return {'CANCELLED'}
        
        if hasattr(context.scene, 'gpencil_select_mode'):
            context.scene.gpencil_select_mode = 'LASSO'

        self.points = [(event.mouse_region_x, event.mouse_region_y)]
        self.drawing = True

        self._handle = bpy.types.SpaceView3D.draw_handler_add(
            self.draw_callback, (context,), 'WINDOW', 'POST_PIXEL'
        )
        
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    @classmethod
    def poll(cls, context):
        return (context.object and 
                obj_is_gp(context.object) and 
                context.object.mode == 'PAINT_GREASE_PENCIL')

    def execute_selection(self, context, event):
        from ..core.tool_manager import GPToolManager
        obj = context.object
        current_mode = obj.mode
        selection_successful = False
        ignored_locked = 0

        try:
            bpy.ops.object.mode_set(mode='EDIT')
            gpencil = obj.data

            select_mode = 'SET'
            if event.shift:
                select_mode = 'ADD'
            elif event.ctrl:
                select_mode = 'SUB'

            region = context.region
            rv3d = GPToolManager.get_region_3d(context)

            total_selected_points = 0

            for layer in gpencil.layers:
                # Ignora explicitamente layers locked (travadas)
                if layer_locked(layer):
                    ignored_locked += 1
                    # Debug temporário para confirmar que pula múltiplas
                    print(f"Layer '{layer.name or 'sem nome'}' LOCKED → ignorada")
                    continue  # Pula completamente essa layer

                # Ignora layers ocultas
                if layer_hidden(layer):
                    continue

                target_frame = get_layer_frame_by_number(layer, context.scene.frame_current)
                if not target_frame or not hasattr(target_frame, 'drawing') or not target_frame.drawing:
                    continue

                drawing = target_frame.drawing

                for stroke in drawing.strokes:
                    selected_in_this_stroke = 0
                    total_points_in_stroke = len(stroke.points)

                    if select_mode == 'SET':
                        stroke.select = False

                    for point in stroke.points:
                        screen_coord = location_3d_to_region_2d(region, rv3d, obj.matrix_world @ point.position)
                        if screen_coord:
                            # Condição do box (para box select) ou lasso (para lasso)
                            # (mantenha a sua condição aqui: if self.is_point_in_lasso ou box check)
                            if (self.is_point_in_lasso(screen_coord) if hasattr(self, 'is_point_in_lasso') else 
                                (min(self.start_x, self.end_x) <= screen_coord.x <= max(self.start_x, self.end_x) and 
                                min(self.start_y, self.end_y) <= screen_coord.y <= max(self.start_y, self.end_y))):
                                
                                if select_mode in {'SET', 'ADD'}:
                                    point.select = True
                                elif select_mode == 'SUB':
                                    point.select = False
                                else:
                                    point.select = False

                                if point.select:
                                    selected_in_this_stroke += 1
                                    total_selected_points += 1

                    if selected_in_this_stroke > 0:
                        stroke.select = True

            selection_successful = total_selected_points > 0
            context.area.tag_redraw()

            # Report final com contagem correta
            if ignored_locked > 0:
                self.report({'INFO'}, f"{ignored_locked} layer(s) locked ignorada(s) na seleção")

        except Exception as e:
            self.report({'ERROR'}, f"Erro na seleção: {str(e)}")
            selection_successful = False

        finally:
            if current_mode == 'PAINT_GREASE_PENCIL':
                bpy.ops.object.mode_set(mode='PAINT_GREASE_PENCIL')

        if selection_successful:
            GPToolManager.check_selection_and_activate_bbox(context)
            GPToolManager.update_selection_visuals(context)

        return selection_successful


    def is_point_in_lasso(self, point):
        """Verifica se um ponto está dentro do polígono do lasso usando ray casting"""
        if len(self.points) < 3:
            return False
            
        x, y = point.x, point.y
        inside = False
        
        points_closed = self.points + [self.points[0]]
        
        j = len(points_closed) - 1
        for i in range(len(points_closed)):
            xi, yi = points_closed[i]
            xj, yj = points_closed[j]
            
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
            
        return inside

    def finish(self, context):
        """Finaliza a operação e limpa recursos"""
        if hasattr(self, '_handle') and self._handle:
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
        
        self.drawing = False
        context.area.tag_redraw()
        return {'FINISHED'}

    def draw_callback(self, context):
        """Desenha apenas o rastro aberto do lasso (sem fechar automaticamente)"""
        if not hasattr(self, 'drawing') or not self.drawing or len(self.points) < 2:
            return

        # Usamos self.points diretamente (sem fechar com + [self.points[0]])
        lasso_path = [Vector(p) for p in self.points]  # converte tuplas em Vectors se necessário

        DASH_LENGTH = 6.0
        GAP_LENGTH = 3.0
        LINE_WIDTH = 1.8

        import time
        time_offset = time.time() * 10.0  # velocidade do march

        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        gpu.state.blend_set('ALPHA')
        gpu.state.line_width_set(LINE_WIDTH)

        def draw_dashed(color, offset):
            coords = []
            accumulated = offset % (DASH_LENGTH + GAP_LENGTH)
            prev = lasso_path[0]

            for curr in lasso_path[1:]:
                vec = curr - prev
                length = vec.length
                if length < 0.01:
                    continue
                unit = vec / length
                pos_along = 0.0
                while pos_along < length:
                    dash_start = pos_along + accumulated
                    if dash_start >= length:
                        break
                    dash_end = min(length, dash_start + DASH_LENGTH)
                    coords.extend([prev + unit * dash_start, prev + unit * dash_end])
                    pos_along = dash_end + GAP_LENGTH
                accumulated = (accumulated - length) % (DASH_LENGTH + GAP_LENGTH)
                prev = curr

            if len(coords) >= 2:
                batch = batch_for_shader(shader, 'LINES', {"pos": coords})
                shader.bind()
                shader.uniform_float("color", color)
                batch.draw(shader)

        # Fundo preto sutil (opcional, melhora contraste)
        gpu.state.line_width_set(LINE_WIDTH + 1.5)
        batch_bg = batch_for_shader(shader, 'LINE_STRIP', {"pos": lasso_path})
        shader.uniform_float("color", (0.0, 0.0, 0.0, 0.35))
        batch_bg.draw(shader)

        gpu.state.line_width_set(LINE_WIDTH)
        draw_dashed((0.0, 0.0, 0.0, 1.0), time_offset)
        draw_dashed((1.0, 1.0, 1.0, 1.0), time_offset + (DASH_LENGTH + GAP_LENGTH) / 2)

        gpu.state.line_width_set(1.0)
        gpu.state.blend_set('NONE')

    def cancel(self, context):
        return self.finish(context)

class GPENCIL_OT_toggle_select_mode(bpy.types.Operator):
    bl_idname = "gpencil.toggle_select_mode"
    bl_label = "Alternar Modo de Seleção"
    bl_description = "Alterna entre Box Select e Lasso Select"

    def execute(self, context):
        if not hasattr(context.scene, 'gpencil_select_mode'):
            context.scene.gpencil_select_mode = 'BOX'
        
        if context.scene.gpencil_select_mode == 'BOX':
            context.scene.gpencil_select_mode = 'LASSO'
            self.report({'INFO'}, "Lasso Select ativado")
        else:
            context.scene.gpencil_select_mode = 'BOX'
            self.report({'INFO'}, "Box Select ativado")
        
        return {'FINISHED'}

class GPENCIL_OT_activate_lasso_tool(bpy.types.Operator):
    bl_idname = "gpencil.activate_lasso_tool"
    bl_label = "Ativar Ferramenta Lasso"
    bl_description = "Ativa a ferramenta de seleção por lasso"
    bl_options = {'REGISTER'}

    def execute(self, context):
        from ..core.tool_manager import GPToolManager
        GPToolManager.activate_tool("gpencil.wst_lasso_tool")
        return {'FINISHED'}

class GPENCIL_OT_shift_select_strokes(bpy.types.Operator):
    """Seleciona ou desseleciona strokes com Shift + Clique e ATUALIZA BBox"""
    bl_idname = "gpencil.shift_select_strokes"
    bl_label = "Shift Select Strokes"
    bl_description = "Seleciona ou desseleciona strokes com Shift pressionado"
    bl_options = {'REGISTER', 'UNDO'}
    
    mouse_x: bpy.props.IntProperty() # type: ignore
    mouse_y: bpy.props.IntProperty() # type: ignore
    
    @classmethod
    def poll(cls, context):
        return (context.object and 
                obj_is_gp(context.object) and 
                context.object.mode == 'PAINT_GREASE_PENCIL')

    def invoke(self, context, event):
        # Só executar se Shift estiver pressionado
        if not event.shift:
            return {'PASS_THROUGH'}
            
        self.mouse_x = event.mouse_region_x
        self.mouse_y = event.mouse_region_y
        return self.execute(context)

    def execute(self, context):
        mouse_pos = Vector((self.mouse_x, self.mouse_y))
        
        # 1. Primeiro executar a seleção normal
        selection_changed = self.perform_shift_selection(context, mouse_pos)
        
        # 2. Se a seleção mudou, atualizar/ativar BBox
        if selection_changed:
            self.update_bbox_for_selection(context)
        
        return {'FINISHED'}
    
    def perform_shift_selection(self, context, mouse_pos):
        from ..core.tool_manager import GPToolManager
        """Executa a seleção com Shift e retorna se algo mudou"""
        from ..compatibility.api_router import layer_hidden, get_layer_frame_by_number
        from bpy_extras.view3d_utils import location_3d_to_region_2d
        
        obj = context.object
        region = context.region
        rv3d = GPToolManager.get_region_3d(context)
        
        if not rv3d:
            return False
        
        stroke_found = None
        layer_found = None
        
        # Procurar por strokes sob o cursor
        for layer in obj.data.layers:
            if layer_hidden(layer):
                continue
                
            target_frame = get_layer_frame_by_number(layer, context.scene.frame_current)
            if not target_frame or not hasattr(target_frame, 'drawing') or not target_frame.drawing:
                continue
            
            for stroke in target_frame.drawing.strokes:
                for point in stroke.points:
                    world_pos = obj.matrix_world @ point.position
                    screen_pos = location_3d_to_region_2d(region, rv3d, world_pos)
                    
                    if screen_pos and (screen_pos - mouse_pos).length < 15:  # 15 pixels de tolerância
                        stroke_found = stroke
                        layer_found = layer
                        break
                if stroke_found:
                    break
            if stroke_found:
                break
        
        if not stroke_found:
            return False
        
        try:
            # Mudar para modo EDIT para garantir que a seleção funcione
            original_mode = context.object.mode
            if original_mode != 'EDIT':
                bpy.ops.object.mode_set(mode='EDIT')
            
            # Alternar seleção do stroke encontrado
            old_selection_state = stroke_found.select
            stroke_found.select = not stroke_found.select
            GPToolManager.update_selection_visuals(context)

            # Manter consistência nos pontos
            for point in stroke_found.points:
                point.select = stroke_found.select
            
            # Voltar para modo original
            if original_mode != 'EDIT':
                bpy.ops.object.mode_set(mode=original_mode)
            
            # Atualizar visualização
            GPToolManager.set_selection_mode('STROKE')
            context.area.tag_redraw()
            
            # Retornar True se a seleção mudou
            return old_selection_state != stroke_found.select
            
        except Exception as e:
            print(f"QuickEdit: Erro na seleção com Shift: {e}")
            return False
    
    def update_bbox_for_selection(self, context):
        """Atualiza ou ativa a BBox baseado na seleção atual"""
        from ..core.tool_manager import GPToolManager
        from ..core import constants
        from ..core.utilities import calculate_screen_bbox
        
        # Obter pontos selecionados atuais
        world_points, screen_points, point_indices = GPToolManager.get_selected_points(context)
        
        if not world_points:
            # Se não há seleção, remover BBox se existir
            if constants._bbox_data:
                constants._bbox_data = None
                context.area.tag_redraw()
            return
        
        # Calcular nova BBox
        new_bbox = calculate_screen_bbox(context, screen_points)
        
        # Se já existe uma BBox ativa, atualizar
        if constants._bbox_data:
            constants._bbox_data = new_bbox
            # Atualizar pontos originais também
            constants._original_points.clear()
            constants._original_screen_points.clear()
            
            for idx, world_point in zip(point_indices, world_points):
                constants._original_points[idx] = world_point.copy()
            
            for idx, screen_point in zip(point_indices, screen_points):
                constants._original_screen_points[idx] = screen_point.copy()
            
            context.area.tag_redraw()
        else:
            # Se não há BBox ativa, criar uma automaticamente
            # (O usuário pode optar por ativar manualmente depois)
            constants._bbox_data = new_bbox
            context.area.tag_redraw()
            
            # Opcional: Ativar BBox automaticamente
            # bpy.ops.gpencil.bbox_transform('INVOKE_DEFAULT')

class GPENCIL_OT_auto_bbox_after_selection(bpy.types.Operator):
    """Ativa BBox automaticamente após qualquer seleção"""
    bl_idname = "gpencil.auto_bbox_after_selection"
    bl_label = "Auto BBox"
    bl_description = "Ativa BBox automaticamente quando há seleção"
    
    _timer = None
    _selection_count = 0
    
    def modal(self, context, event):
        from ..core.tool_manager import GPToolManager
        # Verificar seleção periodicamente
        if event.type == 'TIMER':
            current_count = GPToolManager.get_selection_count(context)
            
            # Se a seleção mudou
            if current_count != self._selection_count:
                self._selection_count = current_count
                
                if current_count > 0:
                    # Se há seleção e BBox não está ativa, ativar
                    from ..core import constants
                    if not constants._bbox_data:
                        bpy.ops.gpencil.bbox_transform('INVOKE_DEFAULT')
                else:
                    # Se não há seleção, cancelar este operador
                    self.cancel(context)
                    return {'CANCELLED'}
        
        return {'PASS_THROUGH'}
    
    def execute(self, context):
        # Iniciar timer para verificar seleção periodicamente
        from ..core.tool_manager import GPToolManager
        
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        self._selection_count = GPToolManager.get_selection_count(context)
        
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def cancel(self, context):
        if self._timer:
            wm = context.window_manager
            wm.event_timer_remove(self._timer)

class GPENCIL_OT_activate_select_tool(bpy.types.Operator):
    bl_idname = "gpencil.activate_select_tool"
    bl_label = "Ativar Ferramenta de Seleção"
    bl_description = "Ativa a ferramenta de seleção por caixa"
    bl_options = {'REGISTER'}

    def execute(self, context):
        from ..core.tool_manager import GPToolManager
        GPToolManager.activate_tool("gpencil.wst_select_tool")
        return {'FINISHED'}
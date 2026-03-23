import bpy
from ..compatibility.api_router import obj_is_gp, layer_hidden, get_layer_frame_by_number

class GPENCIL_OT_select_all(bpy.types.Operator):
    """Selecionar ou desselecionar todos os strokes"""
    bl_idname = "gpencil.select_all"
    bl_label = "Select All"
    bl_description = "Selecionar ou desselecionar todos os strokes"
    bl_options = {'REGISTER', 'UNDO'}
    
    action: bpy.props.EnumProperty(
        name="Action",
        description="Ação de seleção",
        items=[
            ('SELECT', "Select", "Selecionar todos"),
            ('DESELECT', "Deselect", "Desselecionar todos"),
        ],
        default='SELECT'
    ) # type: ignore

    @classmethod
    def poll(cls, context):
        return context.object and obj_is_gp(context.object)

    def execute(self, context):
        try:
            if self.action == 'SELECT':
                bpy.ops.gpencil.select_all(action='SELECT')
            else:
                bpy.ops.gpencil.select_all(action='DESELECT')
        except:
            # Fallback manual se o operador nativo falhar
            self.manual_select_all(context)
        
        return {'FINISHED'}
    
    def manual_select_all(self, context):
        """Seleção manual fallback"""
        obj = context.object
        for layer in obj.data.layers:
            if layer_hidden(layer):
                continue
                
            target_frame = get_layer_frame_by_number(layer, context.scene.frame_current)
            if not target_frame or not hasattr(target_frame, 'drawing') or not target_frame.drawing:
                continue
            
            for stroke in target_frame.drawing.strokes:
                stroke.select = (self.action == 'SELECT')
                for point in stroke.points:
                    point.select = (self.action == 'SELECT')

class GPENCIL_OT_delete_selected_strokes(bpy.types.Operator):
    bl_idname = "gpencil.delete_selected_strokes"
    bl_label = "Deletar Strokes Selecionados"
    bl_description = "Deleta todos os strokes selecionados em todas as layers"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.object and 
                obj_is_gp(context.object) and 
                context.object.mode == 'PAINT_GREASE_PENCIL')

    def execute(self, context):
        obj = context.object
        deleted_strokes = 0
        
        # Manter o modo atual (não mudar para EDIT)
        try:
            # Para cada layer, deletar strokes selecionados
            for layer in obj.data.layers:
                if layer_hidden(layer):
                    continue
                    
                target_frame = get_layer_frame_by_number(layer, context.scene.frame_current)
                if not target_frame or not hasattr(target_frame, 'drawing') or not target_frame.drawing:
                    continue
                
                # Coletar strokes selecionados
                selected_strokes = []
                for stroke in target_frame.drawing.strokes:
                    if stroke.select:
                        selected_strokes.append(stroke)
                
                # Deletar strokes selecionados
                for stroke in selected_strokes:
                    target_frame.drawing.strokes.remove(stroke)
                    deleted_strokes += 1
            
            self.report({'INFO'}, f"{deleted_strokes} strokes deletados")
            
        except Exception as e:
            self.report({'ERROR'}, f"Erro ao deletar strokes: use SHIFT + DEL")
        
        return {'FINISHED'}

class GPENCIL_OT_delete_selected_points(bpy.types.Operator):
    bl_idname = "gpencil.delete_selected_points"
    bl_label = "Deletar Pontos Selecionados"
    bl_description = "Deleta apenas os pontos selecionados nos strokes"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        from ..compatibility.api_router import obj_is_gp
        return (context.object and 
                obj_is_gp(context.object) and 
                context.object.mode == 'PAINT_GREASE_PENCIL')

    def execute(self, context):
        from ..compatibility.api_router import obj_is_gp, layer_hidden, get_layer_frame_by_number, is_frame_valid, is_gpv3
        from ..core.tool_manager import GPToolManager
        
        obj = context.object
        deleted_points = 0
        
        try:
            # Verificar se é GPv3 ou GPv2
            gpv3 = is_gpv3()
            
            for layer in obj.data.layers:
                if layer_hidden(layer):
                    continue
                    
                target_frame = get_layer_frame_by_number(layer, context.scene.frame_current)
                if not target_frame or not is_frame_valid(target_frame):
                    continue
                
                if gpv3:
                    # GPv3: Reconstruir strokes sem os pontos deletados
                    deleted_points += self._delete_points_gpv3(target_frame)
                else:
                    # GPv2: Usar método nativo
                    deleted_points += self._delete_points_gpv2(target_frame)
            
            if deleted_points > 0:
                self.report({'INFO'}, f"{deleted_points} pontos deletados")
                # Atualizar seleção e BBox
                GPToolManager.check_and_update_bbox(context)
            else:
                self.report({'INFO'}, "Nenhum ponto selecionado")
            
        except Exception as e:
            self.report({'ERROR'}, f"Erro ao deletar pontos: {str(e)}")
            import traceback
            traceback.print_exc()
        
        return {'FINISHED'}
    
    def _delete_points_gpv3(self, frame):
        """Deleta pontos no GPv3 (Blender ≥ 4.3)"""
        deleted = 0
        drawing = frame.drawing
        
        # Percorrer strokes em ordem reversa para não bagunçar índices
        for stroke_idx in range(len(drawing.strokes) - 1, -1, -1):
            stroke = drawing.strokes[stroke_idx]
            original_points = list(stroke.points)
            
            # Filtrar pontos não selecionados
            kept_points = [p for p in original_points if not p.select]
            
            if len(kept_points) == 0:
                # Stroke ficou vazio - deletar o stroke inteiro
                drawing.remove_strokes(indices=(stroke_idx,))
                deleted += len(original_points)
            elif len(kept_points) < len(original_points):
                # Precisa recriar o stroke com pontos restantes
                # Método: pegar os dados dos pontos mantidos e recriar
                kept_count = len(kept_points)
                
                # Salvar dados dos pontos mantidos
                positions = [p.position.copy() for p in kept_points]
                radii = [p.radius for p in kept_points]
                opacities = [p.opacity for p in kept_points]
                rotations = [p.rotation for p in kept_points]
                
                # Guardar propriedades do stroke original
                stroke_select = stroke.select
                stroke_material = stroke.material_index
                stroke_cyclic = stroke.cyclic
                stroke_softness = stroke.softness
                stroke_start_cap = stroke.start_cap
                stroke_end_cap = stroke.end_cap
                
                # Remover stroke original
                drawing.remove_strokes(indices=(stroke_idx,))
                
                # Criar novo stroke com o número correto de pontos
                drawing.add_strokes([kept_count], indices=(stroke_idx,))
                new_stroke = drawing.strokes[stroke_idx]
                
                # Restaurar propriedades
                new_stroke.select = stroke_select
                new_stroke.material_index = stroke_material
                new_stroke.cyclic = stroke_cyclic
                new_stroke.softness = stroke_softness
                new_stroke.start_cap = stroke_start_cap
                new_stroke.end_cap = stroke_end_cap
                
                # Restaurar pontos
                for i, point in enumerate(new_stroke.points):
                    point.position = positions[i]
                    point.radius = radii[i]
                    point.opacity = opacities[i]
                    point.rotation = rotations[i]
                
                deleted += (len(original_points) - kept_count)
        
        return deleted
    
    def _delete_points_gpv2(self, frame):
        """Deleta pontos no GPv2 (Blender < 4.3)"""
        deleted = 0
        
        for stroke in frame.strokes:
            # Coletar pontos selecionados (em ordem reversa para remover)
            points_to_remove = []
            for point_idx, point in enumerate(stroke.points):
                if point.select:
                    points_to_remove.append(point_idx)
            
            if points_to_remove:
                # Remover em ordem reversa para não bagunçar índices
                for point_idx in sorted(points_to_remove, reverse=True):
                    stroke.points.remove(stroke.points[point_idx])
                    deleted += 1
        
        return deleted
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
            self.report({'ERROR'}, f"Erro ao deletar strokes: {str(e)}")
        
        return {'FINISHED'}

class GPENCIL_OT_delete_selected_points(bpy.types.Operator):
    bl_idname = "gpencil.delete_selected_points"
    bl_label = "Deletar Pontos Selecionados"
    bl_description = "Deleta apenas os pontos selecionados nos strokes"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.object and 
                obj_is_gp(context.object) and 
                context.object.mode == 'PAINT_GREASE_PENCIL')

    def execute(self, context):
        obj = context.object
        deleted_points = 0
        
        try:
            # Para cada layer, deletar pontos selecionados
            for layer in obj.data.layers:
                if layer_hidden(layer):
                    continue
                    
                target_frame = get_layer_frame_by_number(layer, context.scene.frame_current)
                if not target_frame or not hasattr(target_frame, 'drawing') or not target_frame.drawing:
                    continue
                
                for stroke in target_frame.drawing.strokes:
                    # Coletar pontos selecionados
                    selected_points = []
                    for point in stroke.points:
                        if point.select:
                            selected_points.append(point)
                    
                    # Deletar pontos selecionados
                    for point in selected_points:
                        stroke.points.remove(point)
                        deleted_points += 1
            
            self.report({'INFO'}, f"{deleted_points} pontos deletados")
            
        except Exception as e:
            self.report({'ERROR'}, f"Erro ao deletar pontos: {str(e)}")
        
        return {'FINISHED'}
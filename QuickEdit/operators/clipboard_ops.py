import bpy
from ..compatibility.api_router import obj_is_gp, layer_hidden, get_layer_frame_by_number

class GPENCIL_OT_copy_strokes(bpy.types.Operator):
    bl_idname = "gpencil.copy_strokes"
    bl_label = "Copiar Strokes"
    bl_description = "Copia os strokes selecionados"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.object and 
                obj_is_gp(context.object) and 
                context.object.mode == 'PAINT_GREASE_PENCIL')

    def execute(self, context):
        try:
            if bpy.app.version >= (4, 3, 0):
                bpy.ops.grease_pencil.copy()
            else:
                bpy.ops.gpencil.copy()
            self.report({'INFO'}, "Strokes copiados")
        except Exception as e:
            self.report({'ERROR'}, f"Erro ao copiar: {str(e)}")
        return {'FINISHED'}

class GPENCIL_OT_paste_strokes(bpy.types.Operator):
    bl_idname = "gpencil.paste_strokes"
    bl_label = "Colar Strokes"
    bl_description = "Cola os strokes"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.object and 
                obj_is_gp(context.object) and 
                context.object.mode == 'PAINT_GREASE_PENCIL')

    def execute(self, context):
        try:
            # Chamar operador nativo
            if bpy.app.version >= (4, 3, 0):
                bpy.ops.grease_pencil.paste()
            else:
                bpy.ops.gpencil.paste()
            self.report({'INFO'}, "Strokes colados")
        except Exception as e:
            self.report({'ERROR'}, f"Erro ao colar: {str(e)}")
        
        return {'FINISHED'}

class GPENCIL_OT_cut_strokes_simple(bpy.types.Operator):
    bl_idname = "gpencil.cut_strokes_simple"
    bl_label = "Recortar Strokes"
    bl_description = "Recorta os strokes selecionados usando operadores nativos"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.object and 
                obj_is_gp(context.object) and 
                context.object.mode == 'PAINT_GREASE_PENCIL')

    def execute(self, context):
        try:
            # Método 1: Tentar usar operadores nativos
            original_mode = context.object.mode
            
            # Se não estiver em EDIT, mudar temporariamente
            if original_mode != 'EDIT':
                bpy.ops.object.mode_set(mode='EDIT')
            
            # Copiar usando operador nativo
            if bpy.app.version >= (4, 3, 0):
                bpy.ops.grease_pencil.copy()
                # Deletar usando operador nativo
                bpy.ops.grease_pencil.delete(type='SELECTED_STROKES')
            else:
                bpy.ops.gpencil.copy()
                bpy.ops.gpencil.delete(type='STROKES')
            
            # Voltar para modo original
            if original_mode != 'EDIT':
                bpy.ops.object.mode_set(mode=original_mode)
            
            self.report({'INFO'}, "Strokes recortados")
            
        except Exception as e:
            # Método 2: Fallback manual se o operador nativo falhar
            try:
                self.cut_manual(context)
            except Exception as e2:
                self.report({'ERROR'}, f"Erro ao recortar: {str(e2)}")
                import traceback
                traceback.print_exc()
        
        return {'FINISHED'}
    
    def cut_manual(self, context):
        """Método manual de cut para fallback"""
        from ..compatibility.api_router import (
            layer_hidden, get_layer_frame_by_number, is_frame_valid
        )
        
        obj = context.object
        
        # 1. Copiar primeiro
        if bpy.app.version >= (4, 3, 0):
            bpy.ops.grease_pencil.copy()
        else:
            bpy.ops.gpencil.copy()
        
        # 2. Deletar manualmente
        deleted_count = 0
        
        for layer in obj.data.layers:
            if layer_hidden(layer):
                continue
                
            target_frame = get_layer_frame_by_number(layer, context.scene.frame_current)
            if not target_frame or not is_frame_valid(target_frame):
                continue
            
            # Método diferente para GPv3
            if bpy.app.version >= (4, 3, 0):
                # GPv3: Usar remove_strokes
                drawing = target_frame.drawing
                indices_to_remove = []
                
                for i, stroke in enumerate(drawing.strokes):
                    if stroke.select:
                        indices_to_remove.append(i)
                
                # Remover em ordem reversa
                for i in sorted(indices_to_remove, reverse=True):
                    drawing.remove_strokes(indices=(i,))
                    deleted_count += 1
            else:
                # GPv2: Método tradicional
                drawing = target_frame.drawing
                strokes_to_remove = []
                
                for stroke in drawing.strokes:
                    if stroke.select:
                        strokes_to_remove.append(stroke)
                
                for stroke in strokes_to_remove:
                    drawing.strokes.remove(stroke)
                    deleted_count += 1
        
        self.report({'INFO'}, f"{deleted_count} strokes recortados (manual)")

# Operador que detecta se está no modo Grease Pencil e redireciona
class GPENCIL_OT_smart_copy(bpy.types.Operator):
    bl_idname = "gpencil.smart_copy"
    bl_label = "Smart Copy"
    bl_description = "Copia strokes se estiver no modo Grease Pencil, senão usa copy normal"

    def execute(self, context):
        # Verificar se está no modo Grease Pencil com objeto selecionado
        if (context.object and 
            obj_is_gp(context.object) and 
            context.object.mode == 'PAINT_GREASE_PENCIL'):
            
            return bpy.ops.gpencil.copy_strokes()
        else:
            # Usar copy normal do Blender
            return bpy.ops.view3d.copybuffer()

class GPENCIL_OT_smart_paste(bpy.types.Operator):
    bl_idname = "gpencil.smart_paste"
    bl_label = "Smart Paste"
    bl_description = "Cola strokes se estiver no modo Grease Pencil, senão usa paste normal"

    def execute(self, context):
        # Verificar se está no modo Grease Pencil com objeto selecionado
        if (context.object and 
            obj_is_gp(context.object) and 
            context.object.mode == 'PAINT_GREASE_PENCIL'):
            
            return bpy.ops.gpencil.paste_strokes()
        else:
            # Usar paste normal do Blender
            return bpy.ops.view3d.pastebuffer()
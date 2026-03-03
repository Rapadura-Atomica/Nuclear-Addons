# SPDX-License-Identifier: GPL-3.0-or-later
bl_info = {
    "name": "Stroke Subdivide Tool",
    "author": "Rapadura Atomica Ltda.",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Stroke Subdivide",
    "description": "Ferramentas para adicionar ou remover subdivisões em traços Grease Pencil",
    "category": "Animation",
}

import bpy
from bpy.types import Operator, Panel


class STROKE_SUBDIVIDE_OT_add_points(Operator):
    """Adiciona pontos de subdivisão aos traços selecionados"""
    bl_idname = "stroke_subdivide.add_points"
    bl_label = "Adicionar Subdivisões"
    bl_options = {'REGISTER', 'UNDO'}

    subdivisions: bpy.props.IntProperty(
        name="Subdivisões",
        description="Número de subdivisões para adicionar",
        default=1,
        min=1,
        max=10
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type == 'GREASEPENCIL' and context.mode == 'EDIT_GREASE_PENCIL'

    def execute(self, context):
        try:
            bpy.ops.grease_pencil.stroke_subdivide(number_cuts=self.subdivisions)
            self.report({'INFO'}, f"Adicionadas {self.subdivisions} subdivisões")
        except Exception as e:
            self.report({'ERROR'}, f"Erro ao subdividir: {str(e)}")
            return {'CANCELLED'}
        
        return {'FINISHED'}


class STROKE_SUBDIVIDE_OT_decimate_points(Operator):
    """Remove pontos dos traços selecionados (simplifica)"""
    bl_idname = "stroke_subdivide.decimate_points"
    bl_label = "Reduzir Pontos"
    bl_options = {'REGISTER', 'UNDO'}

    ratio: bpy.props.FloatProperty(
        name="Razão",
        description="Razão de decimação (0.1 = remove 90% dos pontos)",
        default=0.5,
        min=0.1,
        max=1.0
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type == 'GREASEPENCIL' and context.mode == 'EDIT_GREASE_PENCIL'

    def execute(self, context):
        try:
            bpy.ops.grease_pencil.stroke_simplify(factor=self.ratio)
            self.report({'INFO'}, f"Decimado com razão {self.ratio}")
        except Exception as e:
            self.report({'ERROR'}, f"Erro ao decimar: {str(e)}")
            return {'CANCELLED'}
        
        return {'FINISHED'}


class STROKE_SUBDIVIDE_OT_simplify_points(Operator):
    """Simplifica traços mantendo a forma geral"""
    bl_idname = "stroke_subdivide.simplify_points"
    bl_label = "Simplificar Traços"
    bl_options = {'REGISTER', 'UNDO'}

    factor: bpy.props.FloatProperty(
        name="Fator",
        description="Fator de simplificação",
        default=0.1,
        min=0.01,
        max=1.0
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type == 'GREASEPENCIL' and context.mode == 'EDIT_GREASE_PENCIL'

    def execute(self, context):
        try:
            bpy.ops.grease_pencil.stroke_simplify(factor=self.factor)
            self.report({'INFO'}, f"Simplificado com fator {self.factor}")
        except Exception as e:
            self.report({'ERROR'}, f"Erro ao simplificar: {str(e)}")
            return {'CANCELLED'}
        
        return {'FINISHED'}


class STROKE_SUBDIVIDE_OT_smooth_subdivide(Operator):
    """Subdivide e suaviza os traços"""
    bl_idname = "stroke_subdivide.smooth_subdivide"
    bl_label = "Subdividir e Suavizar"
    bl_options = {'REGISTER', 'UNDO'}

    subdivisions: bpy.props.IntProperty(
        name="Subdivisões",
        default=2,
        min=1,
        max=5
    )

    smooth_iterations: bpy.props.IntProperty(
        name="Suavizações",
        default=2,
        min=1,
        max=10
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type == 'GREASEPENCIL' and context.mode == 'EDIT_GREASE_PENCIL'

    def execute(self, context):
        try:
            # Primeiro subdivide
            bpy.ops.grease_pencil.stroke_subdivide(number_cuts=self.subdivisions)
            # Depois suaviza
            for _ in range(self.smooth_iterations):
                bpy.ops.grease_pencil.stroke_smooth()
            
            self.report({'INFO'}, f"Subdividido {self.subdivisions}x e suavizado {self.smooth_iterations}x")
        except Exception as e:
            self.report({'ERROR'}, f"Erro: {str(e)}")
            return {'CANCELLED'}
        
        return {'FINISHED'}


class STROKE_SUBDIVIDE_OT_quick_double(Operator):
    """Duplica rapidamente a quantidade de pontos"""
    bl_idname = "stroke_subdivide.quick_double"
    bl_label = "Duplicar Pontos"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type == 'GREASEPENCIL' and context.mode == 'EDIT_GREASE_PENCIL'

    def execute(self, context):
        try:
            bpy.ops.grease_pencil.stroke_subdivide(number_cuts=1)
            self.report({'INFO'}, "Pontos duplicados")
        except Exception as e:
            self.report({'ERROR'}, f"Erro: {str(e)}")
            return {'CANCELLED'}
        
        return {'FINISHED'}


class STROKE_SUBDIVIDE_OT_quick_half(Operator):
    """Reduz rapidamente pela metade a quantidade de pontos"""
    bl_idname = "stroke_subdivide.quick_half"
    bl_label = "Reduzir Pontos pela Metade"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type == 'GREASEPENCIL' and context.mode == 'EDIT_GREASE_PENCIL'

    def execute(self, context):
        try:
            bpy.ops.grease_pencil.stroke_simplify(factor=0.5)
            self.report({'INFO'}, "Pontos reduzidos pela metade")
        except Exception as e:
            self.report({'ERROR'}, f"Erro: {str(e)}")
            return {'CANCELLED'}
        
        return {'FINISHED'}


class STROKE_SUBDIVIDE_PT_main_panel(Panel):
    """Painel principal de subdivisão de traços"""
    bl_label = "Stroke Subdivide"
    bl_idname = "STROKE_SUBDIVIDE_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Edit"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type == 'GREASEPENCIL' and context.mode == 'EDIT_GREASE_PENCIL'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # Verificar se há seleção
        has_selection = self.has_selected_strokes(context)

        if not has_selection:
            layout.label(text="Selecione alguns traços", icon='INFO')
        else:
            layout.label(text="Traços selecionados: ✓", icon='CHECKMARK')
        
        layout.separator()

        # Operações Rápidas
        box = layout.box()
        box.label(text="Operações Rápidas:", icon='PLAY')
        
        row = box.row(align=True)
        row.operator("stroke_subdivide.quick_double", text="Duplicar", icon='ADD')
        row.operator("stroke_subdivide.quick_half", text="Reduzir", icon='REMOVE')

        # Subdivisão Controlada
        box = layout.box()
        box.label(text="Subdivisão Controlada:", icon='MOD_SUBSURF')
        
        col = box.column()
        op = col.operator("stroke_subdivide.add_points", text="Adicionar Subdivisões", icon='ADD')
        op.subdivisions = scene.gpencil_stroke_subdivide_subdivisions
        col.prop(scene, "gpencil_stroke_subdivide_subdivisions")
        
        # Simplificação
        box = layout.box()
        box.label(text="Simplificação:", icon='MOD_DECIM')
        
        col = box.column()
        op = col.operator("stroke_subdivide.decimate_points", text="Decimar Pontos", icon='REMOVE')
        op.ratio = scene.gpencil_stroke_subdivide_ratio
        col.prop(scene, "gpencil_stroke_subdivide_ratio")
        
        col = box.column()
        op = col.operator("stroke_subdivide.simplify_points", text="Simplificar", icon='SMOOTHCURVE')
        op.factor = scene.gpencil_stroke_subdivide_factor
        col.prop(scene, "gpencil_stroke_subdivide_factor")

        # Operação Combinada
        box = layout.box()
        box.label(text="Combinado:", icon='MOD_SMOOTH')
        
        col = box.column()
        op = col.operator("stroke_subdivide.smooth_subdivide", text="Subdividir e Suavizar", icon='OUTLINER_OB_CURVE')
        op.subdivisions = scene.gpencil_stroke_subdivide_subdivisions
        op.smooth_iterations = scene.gpencil_stroke_subdivide_smooth_iterations
        
        col.prop(scene, "gpencil_stroke_subdivide_smooth_iterations")

    def has_selected_strokes(self, context):
        """Verifica se há traços selecionados de forma direta"""
        obj = context.active_object
        if not obj or obj.type != 'GREASEPENCIL':
            return False

        # Método 1: Tentar operador de seleção (mais confiável)
        try:
            result = bpy.ops.gpencil.select_all(action='INVERT')
            if result == {'FINISHED'}:
                bpy.ops.gpencil.select_all(action='INVERT')  # Reverter
                return True
        except:
            pass

        # Método 2: Verificar diretamente nos dados
        try:
            gpencil_data = obj.data
            
            for layer in gpencil_data.layers:
                if layer.hide or layer.lock:
                    continue
                    
                frame = layer.active_frame
                if not frame:
                    continue
                    
                for stroke in frame.strokes:
                    # Verificar seleção do stroke
                    if hasattr(stroke, 'select') and stroke.select:
                        return True
                    if hasattr(stroke, 'selected') and stroke.selected:
                        return True
                    
                    # Verificar seleção de pontos
                    if hasattr(stroke, 'points'):
                        for point in stroke.points:
                            if hasattr(point, 'select') and point.select:
                                return True
                            if hasattr(point, 'selected') and point.selected:
                                return True
        except:
            pass

        return False


# Propriedades da cena
def init_scene_properties():
    """Inicializa propriedades da cena"""
    
    bpy.types.Scene.gpencil_stroke_subdivide_subdivisions = bpy.props.IntProperty(
        name="Subdivisões",
        description="Número de subdivisões",
        default=2,
        min=1,
        max=10
    )
    
    bpy.types.Scene.gpencil_stroke_subdivide_ratio = bpy.props.FloatProperty(
        name="Razão de Decimação",
        description="Razão para decimação",
        default=0.5,
        min=0.1,
        max=1.0
    )
    
    bpy.types.Scene.gpencil_stroke_subdivide_factor = bpy.props.FloatProperty(
        name="Fator de Simplificação",
        description="Fator para simplificação",
        default=0.1,
        min=0.01,
        max=1.0
    )
    
    bpy.types.Scene.gpencil_stroke_subdivide_smooth_iterations = bpy.props.IntProperty(
        name="Iterações de Suavização",
        description="Número de iterações de suavização",
        default=2,
        min=1,
        max=10
    )


def clear_scene_properties():
    """Remove propriedades da cena"""
    props = [
        'gpencil_stroke_subdivide_subdivisions',
        'gpencil_stroke_subdivide_ratio', 
        'gpencil_stroke_subdivide_factor',
        'gpencil_stroke_subdivide_smooth_iterations'
    ]
    
    for prop in props:
        if hasattr(bpy.types.Scene, prop):
            try:
                delattr(bpy.types.Scene, prop)
            except:
                pass


# Classes para registro
classes = (
    STROKE_SUBDIVIDE_OT_add_points,
    STROKE_SUBDIVIDE_OT_decimate_points,
    STROKE_SUBDIVIDE_OT_simplify_points,
    STROKE_SUBDIVIDE_OT_smooth_subdivide,
    STROKE_SUBDIVIDE_OT_quick_double,
    STROKE_SUBDIVIDE_OT_quick_half,
    STROKE_SUBDIVIDE_PT_main_panel,
)


def register():
    """Registra o addon"""
    init_scene_properties()
    
    for cls in classes:
        bpy.utils.register_class(cls)
    
    print("Stroke Subdivide Tool registrado com sucesso!")


def unregister():
    """Desregistra o addon"""
    clear_scene_properties()
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    print("Stroke Subdivide Tool desregistrado!")


if __name__ == "__main__":
    register()
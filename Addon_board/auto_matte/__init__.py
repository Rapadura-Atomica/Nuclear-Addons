import bpy
from mathutils import Vector

# --- PROPRIEDADES ---

class H2D_AutoMatteSettings(bpy.types.PropertyGroup):
    matte_color: bpy.props.FloatVectorProperty(
        name="Cor do Preenchimento",
        subtype="COLOR",
        default=(1.0, 1.0, 1.0),
        min=0.0, max=1.0,
        description="Cor do preenchimento do Auto-Matte"
    ) # type: ignore
    
    fill_threshold: bpy.props.FloatProperty(
        name="Tolerância do Preenchimento",
        default=10.0,
        min=1.0,
        max=50.0,
        description="Tolerância para detectar áreas fechadas"
    ) # type: ignore
    
    all_frames: bpy.props.BoolProperty(
        name="Todos os Frames",
        default=False,
        description="Aplicar auto-matte para todos os frames"
    ) # type: ignore

# --- OPERADORES ---

class H2D_OT_auto_matte(bpy.types.Operator):
    bl_idname = "h2d.auto_matte"
    bl_label = "Criar Auto-Matte"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return (context.active_object and 
                context.active_object.type == 'GREASEPENCIL' and 
                context.active_object.data.layers.active)

    def create_fill_material(self, color):
        """Cria ou atualiza um material de Grease Pencil para preenchimento"""
        mat_name = "AutoMatte_Fill"
        gp_mat = bpy.data.materials.get(mat_name)
        
        if not gp_mat:
            gp_mat = bpy.data.materials.new(name=mat_name)
        
        # Configuração simples usando nodes (funciona para qualquer material)
        gp_mat.use_nodes = True
        nodes = gp_mat.node_tree.nodes
        nodes.clear()
        
        # Criar nodes básicos
        output = nodes.new(type='ShaderNodeOutputMaterial')
        bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
        bsdf.inputs[0].default_value = (*color, 1.0)  # Cor
        
        gp_mat.node_tree.links.new(bsdf.outputs[0], output.inputs[0])
        
        return gp_mat

    @staticmethod
    def is_stroke_closed(stroke, threshold):
        """Verifica se um stroke é fechado"""
        if len(stroke.points) < 3:
            return False
        
        first_point = stroke.points[0].position
        last_point = stroke.points[-1].position
        
        return (Vector(first_point) - Vector(last_point)).length < threshold

    def execute(self, context):
        obj = context.active_object
        gp = obj.data
        settings = context.scene.h2d_auto_matte_settings

        if not gp.layers.active:
            self.report({'ERROR'}, "Nenhuma layer ativa.")
            return {'CANCELLED'}

        frames_to_process = []
        if settings.all_frames:
            frames_to_process = [frame.frame_number for frame in gp.layers.active.frames]
        else:
            frames_to_process.append(context.scene.frame_current)
        
        if not frames_to_process:
            self.report({'ERROR'}, "Nenhum frame para processar.")
            return {'CANCELLED'}

        fill_material = self.create_fill_material(settings.matte_color)
        if fill_material.name not in obj.data.materials:
            obj.data.materials.append(fill_material)
        mat_index = obj.data.materials.find(fill_material.name)
        
        original_layer = gp.layers.active
        original_layer_name = original_layer.info if hasattr(original_layer, 'info') else original_layer.name
        matte_layer_name = f"{original_layer_name}_matte"
        
        if matte_layer_name in gp.layers:
            self.report({'ERROR'}, f"A layer '{matte_layer_name}' já existe. Por favor, a remova ou renomeie.")
            return {'CANCELLED'}
        
        matte_layer = gp.layers.new(name=matte_layer_name)

        filled_areas_count = 0
        
        for frame_number in frames_to_process:
            src_frame = None
            for frame in original_layer.frames:
                if frame.frame_number == frame_number:
                    src_frame = frame
                    break
            
            if not src_frame or not src_frame.drawing:
                continue

            dst_frame = None
            for frame in matte_layer.frames:
                if frame.frame_number == frame_number:
                    dst_frame = frame
                    break
            
            if not dst_frame:
                dst_frame = matte_layer.frames.new(frame_number)

            for stroke in src_frame.drawing.strokes:
                if self.is_stroke_closed(stroke, settings.fill_threshold):
                    # CORREÇÃO: Criar stroke corretamente para Grease Pencil V3
                    new_stroke = dst_frame.drawing.strokes.new()
                    new_stroke.display_mode = '3DSPACE'  # Modo de exibição
                    
                    # Copiar pontos do stroke original
                    for point in stroke.points:
                        new_point = new_stroke.points.add()
                        new_point.position = point.position
                        new_point.pressure = point.pressure
                        new_point.strength = point.strength
                    
                    new_stroke.use_cyclic = True
                    new_stroke.material_index = mat_index
                    new_stroke.line_width = 1  # Largura da linha
                    
                    filled_areas_count += 1
        
        # Mover a layer matte para trás da original
        original_layer_index = gp.layers.find(original_layer.name)
        matte_layer_index = gp.layers.find(matte_layer.name)
        if matte_layer_index > original_layer_index:
            gp.layers.move(from_index=matte_layer_index, to_index=original_layer_index)

        self.report({'INFO'}, f"Preenchidas {filled_areas_count} áreas em {len(frames_to_process)} frame(s).")
        return {'FINISHED'}

# --- TESTE SIMPLIFICADO ---

class H2D_OT_simple_test(bpy.types.Operator):
    bl_idname = "h2d.simple_test"
    bl_label = "Teste Simples"
    bl_options = {'REGISTER'}

    def execute(self, context):
        obj = context.active_object
        if not (obj and obj.type == 'GREASEPENCIL' and obj.data.layers.active):
            self.report({'ERROR'}, "Selecione um objeto Grease Pencil e uma layer ativa.")
            return {'CANCELLED'}
        
        layer = obj.data.layers.active
        
        frame = None
        for f in layer.frames:
            if f.frame_number == context.scene.frame_current:
                frame = f
                break

        if not (frame and frame.drawing):
            self.report({'INFO'}, "Nenhum stroke encontrado no frame atual.")
            return {'CANCELLED'}
        
        closed_count = 0
        settings = context.scene.h2d_auto_matte_settings
        
        for stroke in frame.drawing.strokes:
            if H2D_OT_auto_matte.is_stroke_closed(stroke, settings.fill_threshold):
                closed_count += 1
        
        self.report({'INFO'}, f"Strokes: {len(frame.drawing.strokes)}, Fechados: {closed_count}")
        return {'FINISHED'}

# --- PAINEL ---

class H2D_PT_panel(bpy.types.Panel):
    bl_label = "Auto-Matte (Balde de Tinta)"
    bl_idname = "H2D_PT_auto_matte"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Auto-Matte"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        
        layout.label(text="Balde de Tinta - Auto-Matte", icon='COLOR')
        
        if not (obj and obj.type == 'GREASEPENCIL' and obj.data.layers.active):
            layout.label(text="Selecione um GP e uma layer", icon='ERROR')
            return
        
        settings = context.scene.h2d_auto_matte_settings
        
        box = layout.box()
        box.label(text="Configurações:", icon='SETTINGS')
        
        row = box.row()
        row.prop(settings, 'matte_color', text="Cor")
        row = box.row()
        row.prop(settings, 'fill_threshold', text="Tolerância")
        row = box.row()
        row.prop(settings, 'all_frames', text="Todos os Frames")
        
        box.operator("h2d.auto_matte", text="Aplicar Preenchimento", icon='BRUSH_DATA')
        box.operator("h2d.simple_test", text="Testar Detecção", icon='VIEWZOOM')
        
        box = layout.box()
        box.label(text="Como usar:", icon='INFO')
        box.label(text="1. Desenhe formas FECHADAS")
        box.label(text="2. Ajuste a tolerância se necessário")
        box.label(text="3. Clique em Aplicar Preenchimento")
        layout.separator()
        layout.label(text="O preenchimento aparecerá em uma nova layer atrás da original.")

# --- REGISTRO DO ADDON ---

classes = (
    H2D_AutoMatteSettings,
    H2D_OT_auto_matte,
    H2D_OT_simple_test,
    H2D_PT_panel
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.h2d_auto_matte_settings = bpy.props.PointerProperty(type=H2D_AutoMatteSettings)

def unregister():
    if hasattr(bpy.types.Scene, 'h2d_auto_matte_settings'):
        del bpy.types.Scene.h2d_auto_matte_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
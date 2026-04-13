# ============================================
# TRACER PLUS - Addon para Blender 5
# Usando api_router.py para compatibilidade
# ============================================

bl_info = {
    "name": "Tracer Plus - Image to Grease Pencil",
    "author": "Seu Nome",
    "version": (2, 2, 0),
    "blender": (5, 0, 0),
    "location": "3D Viewport > Sidebar > Tracer Plus",
    "description": "Converte imagens em Grease Pencil strokes com compatibilidade GPv2/GPv3",
    "category": "Grease Pencil",
}

import bpy
import sys
import os
from mathutils import Vector
from bpy.props import (
    StringProperty, BoolProperty, FloatProperty, 
    IntProperty
)
from bpy.types import Panel, Operator, AddonPreferences
import numpy as np
from PIL import Image

# Adiciona o diretório do addon ao path se necessário
# Assumindo que api_router.py está no mesmo diretório
try:
    from .api_router import (
        is_gpv3, obj_is_gp, get_gp_modifiers,
        get_ctx_mode_str, get_obj_mode_str,
        get_active_layer_index, set_active_layer_index,
        get_multiedit, set_multiedit,
        get_layer_frame_by_number, is_frame_valid,
        remove_frame, copy_frame, new_active_frame,
        LegacyStrokeCollection, LegacyStrokeRef,
        insert_gp_keyframe_if_auto,
        register_alternative_api_paths, unregister_alternative_api_paths
    )
except ImportError:
    # Fallback para desenvolvimento (api_router.py no mesmo diretório)
    import importlib.util
    spec = importlib.util.spec_from_file_location("api_router", os.path.join(os.path.dirname(__file__), "api_router.py"))
    api_router = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api_router)
    from api_router import (
        is_gpv3, obj_is_gp, get_gp_modifiers,
        get_ctx_mode_str, get_obj_mode_str,
        get_active_layer_index, set_active_layer_index,
        get_multiedit, set_multiedit,
        get_layer_frame_by_number, is_frame_valid,
        remove_frame, copy_frame, new_active_frame,
        LegacyStrokeCollection, LegacyStrokeRef,
        insert_gp_keyframe_if_auto,
        register_alternative_api_paths, unregister_alternative_api_paths
    )

# Verifica scikit-image
try:
    from skimage import measure
    SKIMAGE_AVAILABLE = True
except ImportError:
    SKIMAGE_AVAILABLE = False
    print("Tracer Plus: scikit-image não encontrado")


# ============================================
# UTILITÁRIOS
# ============================================

def get_or_create_gpencil_material(color_rgb):
    """Cria ou retorna um material para Grease Pencil"""
    
    hex_color = f"{int(color_rgb[0]*255):02x}{int(color_rgb[1]*255):02x}{int(color_rgb[2]*255):02x}"
    mat_name = f"GP_Trace_{hex_color}"
    
    # Verifica se já existe
    for mat in bpy.data.materials:
        if mat.name == mat_name:
            return mat
    
    # Cria novo material
    mat = bpy.data.materials.new(name=mat_name)
    mat.use_fake_user = True
    
    # Configura para Grease Pencil
    if is_gpv3():
        if hasattr(mat, 'grease_pencil') and mat.grease_pencil is not None:
            mat.grease_pencil.show_stroke = True
            mat.grease_pencil.stroke_color = color_rgb
            mat.grease_pencil.stroke_style = 'SOLID'
            mat.grease_pencil.show_fill = True
            mat.grease_pencil.fill_color = (*color_rgb, 0.5)
            mat.grease_pencil.stroke_thickness = 2
    else:
        # GPv2
        mat.grease_pencil.color = color_rgb
        mat.grease_pencil.fill_color = (*color_rgb, 0.5)
    
    return mat


def quantize_image_robust(image, n_colors=16):
    """Quantização de cores robusta"""
    if n_colors >= 256:
        return image.convert('RGB')
    
    if image.mode not in ('RGBA', 'RGB'):
        image = image.convert('RGBA')
    elif image.mode == 'RGB':
        image = image.convert('RGBA')
    
    for method in [3, 2, 1, 0]:
        try:
            quantized = image.quantize(colors=n_colors, method=method)
            return quantized.convert('RGB')
        except:
            continue
    
    return image.convert('RGB')


def simplify_contour(contour, factor):
    """Simplifica o contorno"""
    if len(contour) < 5:
        return contour
    
    simplified = [contour[0]]
    tolerance = factor * 5
    
    for i in range(1, len(contour)-1):
        prev = np.array(simplified[-1])
        curr = np.array(contour[i])
        next_pt = np.array(contour[i+1])
        
        v1 = curr - prev
        v2 = next_pt - curr
        
        angle1 = np.arctan2(v1[1], v1[0])
        angle2 = np.arctan2(v2[1], v2[0])
        angle_diff = abs(angle1 - angle2)
        
        if angle_diff > tolerance:
            simplified.append(contour[i])
    
    simplified.append(contour[-1])
    
    if len(simplified) < 3 and len(contour) >= 3:
        return contour[::max(1, len(contour)//10)]
    
    return np.array(simplified)


# ============================================
# OPERADOR PRINCIPAL
# ============================================

class GP_OT_trace_image(Operator):
    bl_idname = "gp.trace_image"
    bl_label = "Traçar Imagem"
    bl_description = "Converte uma imagem para Grease Pencil strokes"
    bl_options = {'REGISTER', 'UNDO'}
    
    filepath: StringProperty(subtype='FILE_PATH')
    resolution_scale: FloatProperty(
        name="Escala de Resolução",
        default=0.5,
        min=0.1,
        max=1.0
    )
    color_quantize: IntProperty(
        name="Quantização de Cores",
        default=16,
        min=2,
        max=64
    )
    simplify_strokes: FloatProperty(
        name="Simplificar Strokes",
        default=0.5,
        min=0.0,
        max=1.0
    )
    close_contours: BoolProperty(
        name="Fechar Contornos",
        default=True
    )
    
    def execute(self, context):
        try:
            # Carrega imagem
            if not os.path.exists(self.filepath):
                self.report({'ERROR'}, f"Arquivo não encontrado: {self.filepath}")
                return {'CANCELLED'}
            
            self.report({'INFO'}, "Carregando imagem...")
            img = Image.open(self.filepath)
            
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            original_width, original_height = img.size
            
            # Redimensiona
            new_size = (int(img.width * self.resolution_scale), int(img.height * self.resolution_scale))
            img_resized = img.resize(new_size, Image.Resampling.LANCZOS)
            
            # Quantiza cores
            self.report({'INFO'}, f"Quantizando cores ({self.color_quantize} cores)...")
            img_quantized = quantize_image_robust(img_resized, self.color_quantize)
            img_array = np.array(img_quantized)
            
            # Cria objeto Grease Pencil usando API compatível
            if is_gpv3():
                bpy.ops.object.grease_pencil_add(type='EMPTY')
            else:
                bpy.ops.object.gpencil_add(type='EMPTY')
            
            gp_obj = context.active_object
            gp_obj.name = "Traced_Image"
            
            # Acessa dados
            gp_data = gp_obj.data
            
            # Cria layer
            layer = gp_data.layers.new(name="Traces", set_active=True)
            
            # Cria frame
            current_frame = context.scene.frame_current
            frame = new_active_frame(layer.frames, current_frame)
            
            # Acessa strokes via LegacyStrokeCollection (compatível)
            strokes = frame.nuclear_strokes
            
            # Detecta cores únicas
            unique_colors = np.unique(img_array.reshape(-1, 3), axis=0)
            total_colors = len(unique_colors)
            
            self.report({'INFO'}, f"Detectando {total_colors} regiões de cor...")
            stroke_count = 0
            
            for idx, color in enumerate(unique_colors):
                if idx % 5 == 0:
                    self.report({'INFO'}, f"Processando cor {idx+1}/{total_colors}...")
                
                # Cria máscara
                mask = np.all(img_array == color, axis=-1).astype(np.uint8)
                
                if np.sum(mask) == 0:
                    continue
                
                # Extrai contornos
                if not SKIMAGE_AVAILABLE:
                    self.report({'WARNING'}, "Instale scikit-image para melhor resultado")
                    continue
                
                contours = measure.find_contours(mask, 0.5)
                
                # Cria material
                color_normalized = color / 255.0
                material = get_or_create_gpencil_material(color_normalized)
                
                if material.name not in [m.name for m in gp_obj.data.materials]:
                    gp_obj.data.materials.append(material)
                
                material_index = gp_obj.data.materials.find(material.name)
                
                # Cria strokes usando LegacyStrokeCollection
                for contour in contours:
                    if len(contour) < 3:
                        continue
                    
                    # Escala
                    scale_x = original_width / new_size[0]
                    scale_y = original_height / new_size[1]
                    contour_scaled = contour.copy()
                    contour_scaled[:, 0] *= scale_y
                    contour_scaled[:, 1] *= scale_x
                    
                    # Simplifica
                    if self.simplify_strokes > 0:
                        contour_scaled = simplify_contour(contour_scaled, self.simplify_strokes)
                    
                    # Cria stroke usando API compatível
                    stroke = strokes.new()
                    stroke.material_index = material_index
                    stroke.use_cyclic = self.close_contours
                    
                    # Adiciona pontos
                    for point in contour_scaled:
                        co = (point[1] - original_width/2, -(point[0] - original_height/2), 0)
                        stroke.points.add(1)
                        stroke.points[-1].co = co
                        stroke.points[-1].pressure = 1.0
                        stroke.points[-1].strength = 1.0
                    
                    stroke_count += 1
            
            # Insere keyframe se auto-keyframe estiver ativo
            insert_gp_keyframe_if_auto(gp_obj, current_frame)
            
            # Configura viewport
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    for space in area.spaces:
                        if space.type == 'VIEW_3D':
                            space.shading.type = 'SOLID'
                            space.overlay.show_gpencil = True
                            break
                    break
            
            bpy.ops.view3d.view_all(center=True)
            
            self.report({'INFO'}, f"Traçado concluído! {stroke_count} strokes criados.")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Erro: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


# ============================================
# OPERADOR: SIMPLIFY STROKES
# ============================================

class GP_OT_simplify_strokes(Operator):
    bl_idname = "gp.simplify_strokes"
    bl_label = "Simplificar Strokes"
    bl_description = "Remove pontos redundantes dos strokes"
    bl_options = {'REGISTER', 'UNDO'}
    
    factor: FloatProperty(
        name="Fator de Simplificação",
        default=0.5,
        min=0.0,
        max=1.0
    )
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or not obj_is_gp(obj):
            self.report({'ERROR'}, "Selecione um objeto Grease Pencil")
            return {'CANCELLED'}
        
        total_removed = 0
        gp_data = obj.data
        
        for layer in gp_data.layers:
            if layer.lock or layer.hide:
                continue
            
            for frame in layer.frames:
                if not is_frame_valid(frame):
                    continue
                
                strokes = frame.nuclear_strokes
                for stroke in strokes:
                    if len(stroke.points) <= 3:
                        continue
                    
                    original_count = len(stroke.points)
                    self._simplify_stroke(stroke, self.factor)
                    total_removed += original_count - len(stroke.points)
        
        self.report({'INFO'}, f"Removidos {total_removed} pontos")
        return {'FINISHED'}
    
    def _simplify_stroke(self, stroke, factor):
        if len(stroke.points) <= 3:
            return
        
        points = [p.co for p in stroke.points]
        epsilon = factor * 10
        
        simplified = self._douglas_peucker(points, epsilon)
        
        while len(stroke.points) > len(simplified):
            stroke.points.pop(-1)
        
        for i, point in enumerate(simplified):
            if i < len(stroke.points):
                stroke.points[i].co = point
            else:
                stroke.points.add(1)
                stroke.points[-1].co = point
    
    def _douglas_peucker(self, points, epsilon):
        if len(points) <= 2:
            return points
        
        dmax = 0
        index = 0
        end = len(points) - 1
        
        for i in range(1, end):
            d = self._perpendicular_distance(points[i], points[0], points[end])
            if d > dmax:
                index = i
                dmax = d
        
        if dmax > epsilon:
            rec_results1 = self._douglas_peucker(points[:index+1], epsilon)
            rec_results2 = self._douglas_peucker(points[index:], epsilon)
            return rec_results1[:-1] + rec_results2
        else:
            return [points[0], points[end]]
    
    def _perpendicular_distance(self, point, line_start, line_end):
        p = Vector(point)
        ls = Vector(line_start)
        le = Vector(line_end)
        
        if ls == le:
            return (p - ls).length
        
        line_vec = le - ls
        point_vec = p - ls
        
        t = point_vec.dot(line_vec) / line_vec.dot(line_vec)
        
        if t < 0:
            closest = ls
        elif t > 1:
            closest = le
        else:
            closest = ls + t * line_vec
        
        return (p - closest).length


# ============================================
# OPERADOR: CLEAR TRACES
# ============================================

class GP_OT_clear_traces(Operator):
    bl_idname = "gp.clear_traces"
    bl_label = "Limpar Traços"
    bl_description = "Remove todos os objetos de trace da cena"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        removed = 0
        for obj in bpy.data.objects:
            if obj_is_gp(obj) and obj.name.startswith("Traced_Image"):
                bpy.data.objects.remove(obj, do_unlink=True)
                removed += 1
        
        self.report({'INFO'}, f"Removidos {removed} objetos")
        return {'FINISHED'}


# ============================================
# PAINEL UI
# ============================================

class GP_PT_tracer_panel(Panel):
    bl_label = "Tracer Plus"
    bl_idname = "GP_PT_tracer_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tracer Plus"
    
    @classmethod
    def poll(cls, context):
        return True
    
    def draw(self, context):
        layout = self.layout
        
        box = layout.box()
        box.label(text="Traçar Imagem", icon='IMAGE_DATA')
        box.operator("gp.trace_image", text="Selecionar Imagem", icon='FILE_IMAGE')
        
        if context.scene.tracer_show_advanced:
            col = box.column(align=True)
            col.prop(context.scene, "tracer_resolution_scale")
            col.prop(context.scene, "tracer_color_quantize")
            col.prop(context.scene, "tracer_simplify_strokes")
            col.prop(context.scene, "tracer_close_contours")
        
        box.prop(context.scene, "tracer_show_advanced", text="Opções Avançadas", icon='SETTINGS')
        
        box = layout.box()
        box.label(text="Ferramentas", icon='TOOL_SETTINGS')
        box.operator("gp.simplify_strokes", text="Simplificar Strokes", icon='MOD_SIMPLIFY')
        box.operator("gp.clear_traces", text="Limpar Traços", icon='TRASH')
        
        box = layout.box()
        box.label(text="Informação", icon='INFO')
        col = box.column(align=True)
        col.label(text=f"Blender: {'GPv3' if is_gpv3() else 'GPv2'}")
        col.label(text=f"scikit-image: {'✓ OK' if SKIMAGE_AVAILABLE else '✗ Não'}")
        col.label(text="Resolução 0.5 para rápido")
        col.label(text="16-32 cores para melhor resultado")


# ============================================
# PROPRIEDADES
# ============================================

def register_properties():
    bpy.types.Scene.tracer_show_advanced = BoolProperty(default=False)
    bpy.types.Scene.tracer_resolution_scale = FloatProperty(default=0.5, min=0.1, max=1.0)
    bpy.types.Scene.tracer_color_quantize = IntProperty(default=16, min=2, max=64)
    bpy.types.Scene.tracer_simplify_strokes = FloatProperty(default=0.5, min=0.0, max=1.0)
    bpy.types.Scene.tracer_close_contours = BoolProperty(default=True)

def unregister_properties():
    props = ['tracer_show_advanced', 'tracer_resolution_scale', 'tracer_color_quantize', 'tracer_simplify_strokes', 'tracer_close_contours']
    for prop in props:
        if hasattr(bpy.types.Scene, prop):
            delattr(bpy.types.Scene, prop)


# ============================================
# PREFERÊNCIAS
# ============================================

class TracerPlusPreferences(AddonPreferences):
    bl_idname = __name__
    
    def draw(self, context):
        layout = self.layout
        layout.label(text="Tracer Plus v2.2.0")
        layout.label(text=f"Modo: {'GPv3' if is_gpv3() else 'GPv2'}")
        layout.label(text="Compatível com Blender 3.0+ até 5.0+")


# ============================================
# REGISTRO
# ============================================

classes = [
    GP_OT_trace_image,
    GP_OT_simplify_strokes,
    GP_OT_clear_traces,
    GP_PT_tracer_panel,
    TracerPlusPreferences,
]

def register():
    # Registra APIs alternativas primeiro
    register_alternative_api_paths()
    
    for cls in classes:
        bpy.utils.register_class(cls)
    
    register_properties()
    
    print("=" * 50)
    print("Tracer Plus v2.2.0")
    print("=" * 50)
    print("✓ Registrado com sucesso!")
    print(f"✓ Modo: {'GPv3' if is_gpv3() else 'GPv2'}")
    print(f"✓ scikit-image: {'OK' if SKIMAGE_AVAILABLE else 'NÃO'}")
    print("=" * 50)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    unregister_properties()
    
    # Remove APIs alternativas
    unregister_alternative_api_paths()
    
    print("Tracer Plus removido!")

if __name__ == "__main__":
    register()
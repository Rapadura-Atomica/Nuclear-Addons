bl_info = {
    "name": "Tracer Plus - Image to Grease Pencil",
    "author": "Seu Nome",
    "version": (2, 4, 0),
    "blender": (5, 0, 0),
    "location": "3D Viewport > Sidebar > Tracer Plus",
    "description": "Converte linhas de imagens em Grease Pencil strokes",
    "category": "Grease Pencil",
}

import bpy
import os
from mathutils import Vector
from bpy.props import (
    StringProperty, BoolProperty, FloatProperty, 
    IntProperty
)
from bpy.types import Panel, Operator, AddonPreferences
import numpy as np
from PIL import Image

# Importa o api_router.py (mesmo diretório)
try:
    from .api_router import (
        is_gpv3, obj_is_gp,
        get_layer_frame_by_number, is_frame_valid,
        remove_frame, copy_frame, new_active_frame,
        LegacyStrokeCollection, LegacyStrokeRef,
        insert_gp_keyframe_if_auto,
        register_alternative_api_paths, unregister_alternative_api_paths
    )
except ImportError:
    # Fallback para desenvolvimento
    import importlib.util
    spec = importlib.util.spec_from_file_location("api_router", os.path.join(os.path.dirname(__file__), "api_router.py"))
    api_router = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api_router)
    from api_router import (
        is_gpv3, obj_is_gp,
        get_layer_frame_by_number, is_frame_valid,
        remove_frame, copy_frame, new_active_frame,
        LegacyStrokeCollection, LegacyStrokeRef,
        insert_gp_keyframe_if_auto,
        register_alternative_api_paths, unregister_alternative_api_paths
    )

# Verifica scikit-image
try:
    from skimage import measure
    from scipy import ndimage
    SKIMAGE_AVAILABLE = True
except ImportError:
    SKIMAGE_AVAILABLE = False
    print("Tracer Plus: scikit-image e scipy são necessários")


# ============================================
# UTILITÁRIOS
# ============================================

def get_or_create_gpencil_material(color_rgb):
    """Cria ou retorna um material para Grease Pencil - SOMENTE LINHAS"""
    
    hex_color = f"{int(color_rgb[0]*255):02x}{int(color_rgb[1]*255):02x}{int(color_rgb[2]*255):02x}"
    mat_name = f"GP_Trace_{hex_color}"
    
    # Verifica se já existe
    for mat in bpy.data.materials:
        if mat.name == mat_name:
            return mat
    
    # Cria novo material
    mat = bpy.data.materials.new(name=mat_name)
    mat.use_fake_user = True
    
    # Configura para Grease Pencil - SOMENTE STROKE (linha)
    if is_gpv3():
        if hasattr(mat, 'grease_pencil') and mat.grease_pencil is not None:
            # Configura o STROKE (linha)
            mat.grease_pencil.show_stroke = True
            mat.grease_pencil.stroke_color = color_rgb
            mat.grease_pencil.stroke_style = 'SOLID'
            mat.grease_pencil.stroke_thickness = 1  # Traço fino
            
            # DESATIVA o FILL completamente
            mat.grease_pencil.show_fill = False
            mat.grease_pencil.fill_color = (0, 0, 0, 0)  # Transparente
            
            # IMPORTANTE: Força o estilo de linha
            mat.grease_pencil.stroke_image = None
            mat.grease_pencil.mode = 'LINE'  # Modo linha (se disponível)
    else:
        # GPv2
        if hasattr(mat, 'grease_pencil'):
            mat.grease_pencil.color = color_rgb
            mat.grease_pencil.fill_color = (0, 0, 0, 0)  # Transparente
            mat.grease_pencil.use_fill = False  # Desativa fill
    
    return mat


def simplify_contour_douglas_peucker(contour, tolerance):
    """Simplifica contorno usando algoritmo Douglas-Peucker - CORRIGIDO"""
    if len(contour) <= 2:
        return list(contour)
    
    # Encontra ponto com maior distância
    dmax = 0
    index = 0
    end = len(contour) - 1
    
    for i in range(1, end):
        d = point_line_distance(contour[i], contour[0], contour[end])
        if d > dmax:
            index = i
            dmax = d
    
    # Se maior que tolerância, recursão
    if dmax > tolerance:
        # Converte para listas para evitar problemas de broadcasting
        left = list(simplify_contour_douglas_peucker(contour[:index+1], tolerance))
        right = list(simplify_contour_douglas_peucker(contour[index:], tolerance))
        # Remove duplicata do meio
        return left[:-1] + right
    else:
        return [list(contour[0]), list(contour[end])]

def point_line_distance(point, line_start, line_end):
    """Distância de um ponto a uma linha"""
    p = np.array(point)
    ls = np.array(line_start)
    le = np.array(line_end)
    
    if np.all(ls == le):
        return np.linalg.norm(p - ls)
    
    line_vec = le - ls
    point_vec = p - ls
    t = np.dot(point_vec, line_vec) / np.dot(line_vec, line_vec)
    
    if t < 0:
        closest = ls
    elif t > 1:
        closest = le
    else:
        closest = ls + t * line_vec
    
    return np.linalg.norm(p - closest)


# ============================================
# OPERADOR PRINCIPAL - TRACING
# ============================================

class GP_OT_trace_image(Operator):
    bl_idname = "gp.trace_image"
    bl_label = "Traçar Imagem"
    bl_description = "Converte as linhas de uma imagem para Grease Pencil strokes"
    bl_options = {'REGISTER', 'UNDO'}
    
    filepath: StringProperty(subtype='FILE_PATH')
    
    # === CONFIGURAÇÕES DE TRACING ===
    edge_threshold: FloatProperty(
        name="Sensibilidade",
        description="Quanto MENOR, MAIS detalhes (0.2 = muitos detalhes, 0.6 = apenas linhas fortes)",
        default=0.35,
        min=0.1,
        max=1.0
    )
    simplify_strokes: FloatProperty(
        name="Simplificação",
        description="Remove pontos redundantes (0 = nenhum, 1 = máximo)",
        default=0.2,
        min=0.0,
        max=1.0
    )
    min_contour_length: IntProperty(
        name="Contorno Mínimo",
        description="Ignora contornos menores que este valor (remove ruídos)",
        default=15,
        min=1,
        max=100
    )
    
    # === CONFIGURAÇÕES DE PRÉ-PROCESSAMENTO ===
    pre_blur: FloatProperty(
        name="Suavização Prévia",
        description="Suaviza a imagem antes de detectar bordas (remove ruídos)",
        default=0.5,
        min=0.0,
        max=2.0
    )
    contrast_boost: FloatProperty(
        name="Contraste",
        description="Aumenta o contraste da imagem (1.0 = normal)",
        default=1.0,
        min=0.5,
        max=2.0
    )
    
    # === CONFIGURAÇÕES DE ESCALA E ROTAÇÃO ===
    image_scale: FloatProperty(
        name="Escala",
        description="Tamanho da imagem na cena",
        default=0.2,
        min=0.001,
        max=0.5
    )
    rotation_x: FloatProperty(
        name="Rotação X",
        description="Rotação no eixo X (90° = plano 2D)",
        default=90.0,
        min=0.0,
        max=180.0
    )
    
    def execute(self, context):
        if not SKIMAGE_AVAILABLE:
            self.report({'ERROR'}, "Instale: pip install scikit-image scipy")
            return {'CANCELLED'}
        
        try:
            # Carrega imagem
            if not os.path.exists(self.filepath):
                self.report({'ERROR'}, f"Arquivo não encontrado: {self.filepath}")
                return {'CANCELLED'}
            
            self.report({'INFO'}, "Carregando imagem...")
            img = Image.open(self.filepath)
            
            # Converte para escala de cinza
            if img.mode != 'L':
                img = img.convert('L')
            
            original_width, original_height = img.size
            
            # Converte para numpy array
            img_array = np.array(img).astype(np.float32)
            img_array = img_array / 255.0
            
            # Aplica contraste
            if self.contrast_boost != 1.0:
                img_array = (img_array - 0.5) * self.contrast_boost + 0.5
                img_array = np.clip(img_array, 0, 1)
            
            # Aplica suavização (blur) para reduzir ruído
            if self.pre_blur > 0:
                from scipy.ndimage import gaussian_filter
                img_array = gaussian_filter(img_array, sigma=self.pre_blur)
            
            # Detecção de bordas com Sobel
            self.report({'INFO'}, "Detectando bordas...")
            edges_x = ndimage.sobel(img_array, axis=0)
            edges_y = ndimage.sobel(img_array, axis=1)
            edges = np.hypot(edges_x, edges_y)
            
            # Normaliza bordas
            edges = edges / edges.max() if edges.max() > 0 else edges
            
            # Aplica threshold
            edge_mask = edges > self.edge_threshold
            
            self.report({'INFO'}, "Extraindo contornos...")
            contours = measure.find_contours(edge_mask, 0.5)
            
            # Filtra contornos pequenos (ruído)
            contours = [c for c in contours if len(c) > self.min_contour_length]
            
            self.report({'INFO'}, f"Encontrados {len(contours)} contornos")
            
            if len(contours) == 0:
                self.report({'WARNING'}, "Nenhum contorno encontrado. Diminua a 'Sensibilidade'.")
                return {'CANCELLED'}
            
            # Cria objeto Grease Pencil (compatível GPv2/GPv3)
            if is_gpv3():
                bpy.ops.object.grease_pencil_add(type='EMPTY')
            else:
                bpy.ops.object.gpencil_add(type='EMPTY')
            
            gp_obj = context.active_object
            gp_obj.name = "Traced_Image"
            
            # === APLICA ROTAÇÃO (X = 90 graus para 2D) ===
            gp_obj.rotation_euler = (self.rotation_x * 3.14159 / 180, 0, 0)
            
            # === APLICA ESCALA (menor tamanho) ===
            gp_obj.scale = (self.image_scale, self.image_scale, self.image_scale)
            
            # Prepara dados
            gp_data = gp_obj.data
            
            # Remove layers padrão
            if hasattr(gp_data.layers, 'clear'):
                gp_data.layers.clear()
            else:
                for layer in list(gp_data.layers):
                    gp_data.layers.remove(layer)
            
            # Cria layer
            layer = gp_data.layers.new(name="Lines", set_active=True)
            
            # Cria frame usando api_router
            current_frame = context.scene.frame_current
            frame = new_active_frame(layer.frames, current_frame)
            
            # Acessa strokes via LegacyStrokeCollection (compatível)
            if hasattr(frame, 'nuclear_strokes'):
                strokes = frame.nuclear_strokes
            elif hasattr(frame, 'drawing') and hasattr(frame.drawing, 'strokes'):
                strokes = frame.drawing.strokes
            else:
                strokes = frame.strokes
            
            # Cria material preto
            material = get_or_create_gpencil_material((0, 0, 0))
            if material.name not in [m.name for m in gp_obj.data.materials]:
                gp_obj.data.materials.append(material)
            material_index = gp_obj.data.materials.find(material.name)
            
            # Cria strokes
            stroke_count = 0
            total_points = 0
            
            for contour in contours:
                if len(contour) < 3:
                    continue
                
                # Simplifica contorno
                points = contour
                if self.simplify_strokes > 0:
                    tolerance = self.simplify_strokes * 3
                    points = simplify_contour_douglas_peucker(contour, tolerance)
                
                # Cria stroke
                stroke = strokes.new()
                stroke.material_index = material_index
                stroke.use_cyclic = False
                stroke.display_mode = 'SCREEN'
                
                # Adiciona pontos
                for point in points:
                    x = (point[1] - (original_width / 2)) * 0.01
                    y = -(point[0] - (original_height / 2)) * 0.01
                    
                    stroke.points.add(1)
                    # gp_obj.rotation_euler = (0, 0, 0)
                    stroke.points[-1].co = (x, 0, -y)

                    stroke.points[-1].pressure = 0.01
                    stroke.points[-1].radius = 0.01
                    stroke.points[-1].strength = 1.0
                
                stroke_count += 1
                
                if stroke_count % 20 == 0:
                    self.report({'INFO'}, f"Criados {stroke_count} strokes...")
            
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
            
            self.report({'INFO'}, f"Tracing concluído! {stroke_count} strokes, {total_points} pontos")
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
        name="Fator",
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
            if hasattr(layer, 'hide') and layer.hide:
                continue
            
            for frame in layer.frames:
                if not is_frame_valid(frame):
                    continue
                
                if hasattr(frame, 'nuclear_strokes'):
                    strokes = frame.nuclear_strokes
                elif hasattr(frame, 'drawing') and hasattr(frame.drawing, 'strokes'):
                    strokes = frame.drawing.strokes
                else:
                    strokes = frame.strokes
                
                for stroke in strokes:
                    if len(stroke.points) <= 3:
                        continue
                    
                    original = len(stroke.points)
                    points = [stroke.points[i].co for i in range(len(stroke.points))]
                    tolerance = self.factor * 10
                    simplified = simplify_contour_douglas_peucker(points, tolerance)
                    
                    while len(stroke.points) > len(simplified):
                        stroke.points.pop(-1)
                    
                    for i, point in enumerate(simplified):
                        if i < len(stroke.points):
                            stroke.points[i].co = point
                        else:
                            stroke.points.add(1)
                            stroke.points[-1].co = point
                    
                    total_removed += original - len(stroke.points)
        
        self.report({'INFO'}, f"Removidos {total_removed} pontos")
        return {'FINISHED'}


# ============================================
# OPERADOR: CLEAR TRACES
# ============================================

class GP_OT_clear_traces(Operator):
    bl_idname = "gp.clear_traces"
    bl_label = "Limpar Traços"
    bl_description = "Remove todos os objetos de trace"
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
    
    def draw(self, context):
        layout = self.layout
        
        # Seção principal
        box = layout.box()
        box.label(text="Tracing de Imagem", icon='IMAGE_DATA')
        box.operator("gp.trace_image", text="Selecionar Imagem", icon='FILE_IMAGE')
        
        # Configurações de Tracing
        if context.scene.tracer_show_advanced:
            box = layout.box()
            box.label(text="Configurações de Tracing", icon='TOOL_SETTINGS')
            col = box.column(align=True)
            col.prop(context.scene, "tracer_edge_threshold")
            col.prop(context.scene, "tracer_simplify_strokes")
            col.prop(context.scene, "tracer_min_contour")
            
            box = layout.box()
            box.label(text="Pré-processamento", icon='IMAGE_ZDEPTH')
            col = box.column(align=True)
            col.prop(context.scene, "tracer_pre_blur")
            col.prop(context.scene, "tracer_contrast_boost")
            
            box = layout.box()
            box.label(text="Transformação", icon='OBJECT_ORIGIN')
            col = box.column(align=True)
            col.prop(context.scene, "tracer_image_scale")
            col.prop(context.scene, "tracer_rotation_x")
        
        box.prop(context.scene, "tracer_show_advanced", text="Configurações Avançadas", icon='SETTINGS')
        
        # Ferramentas
        box = layout.box()
        box.label(text="Ferramentas", icon='TOOL_SETTINGS')
        box.operator("gp.simplify_strokes", text="Simplificar Selecionados", icon='MOD_SIMPLIFY')
        box.operator("gp.clear_traces", text="Limpar Todos", icon='TRASH')
        
        # Dicas
        box = layout.box()
        box.label(text="Dicas para traços mais limpos", icon='INFO')
        col = box.column(align=True)
        col.label(text="• Diminua a SENSIBILIDADE (0.2-0.3)")
        col.label(text="• Aumente o CONTRASTE (1.5-2.0)")
        col.label(text="• Use SUAVIZAÇÃO (0.5-1.0)")
        col.label(text="• Aumente CONTORNO MÍNIMO (15-30)")
        
        # Status
        box = layout.box()
        box.label(text="Status", icon='CHECKMARK')
        col = box.column(align=True)
        col.label(text=f"Modo: {'GPv3' if is_gpv3() else 'GPv2'}")
        col.label(text=f"scikit-image: {'✓ OK' if SKIMAGE_AVAILABLE else '✗ Faltando'}")


# ============================================
# PROPRIEDADES
# ============================================

def register_properties():
    bpy.types.Scene.tracer_show_advanced = BoolProperty(default=False)
    bpy.types.Scene.tracer_edge_threshold = FloatProperty(default=0.35, min=0.1, max=1.0)
    bpy.types.Scene.tracer_simplify_strokes = FloatProperty(default=0.2, min=0.0, max=1.0)
    bpy.types.Scene.tracer_min_contour = IntProperty(default=15, min=1, max=100)
    bpy.types.Scene.tracer_pre_blur = FloatProperty(default=0.5, min=0.0, max=2.0)
    bpy.types.Scene.tracer_contrast_boost = FloatProperty(default=1.0, min=0.5, max=2.0)
    bpy.types.Scene.tracer_image_scale = FloatProperty(default=0.02, min=0.001, max=0.5)
    bpy.types.Scene.tracer_rotation_x = FloatProperty(default=90.0, min=0.0, max=180.0)

def unregister_properties():
    props = ['tracer_show_advanced', 'tracer_edge_threshold', 'tracer_simplify_strokes', 
             'tracer_min_contour', 'tracer_pre_blur', 'tracer_contrast_boost',
             'tracer_image_scale', 'tracer_rotation_x']
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
        layout.label(text="Tracer Plus v2.4.0")
        layout.label(text=f"Compatível: {'GPv3' if is_gpv3() else 'GPv2'}")


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
    register_alternative_api_paths()
    
    for cls in classes:
        bpy.utils.register_class(cls)
    
    register_properties()
    
    print("=" * 50)
    print("Tracer Plus v2.4.0")
    print("=" * 50)
    print(f"✓ Modo: {'GPv3' if is_gpv3() else 'GPv2'}")
    print(f"✓ scikit-image: {'OK' if SKIMAGE_AVAILABLE else 'NÃO'}")
    print("=" * 50)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    unregister_properties()
    unregister_alternative_api_paths()
    
    print("Tracer Plus removido!")

if __name__ == "__main__":
    register()
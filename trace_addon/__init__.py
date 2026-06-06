bl_info = {
    "name": "Tracer Plus - Image to Grease Pencil",
    "author": "Seu Nome",
    "version": (3, 0, 0),
    "blender": (5, 0, 0),
    "location": "3D Viewport > Sidebar > Tracer Plus",
    "description": "Converte imagens em Grease Pencil: contornos como linhas e regiões fechadas como fill",
    "category": "Grease Pencil",
}

import bpy
import os
from mathutils import Vector
from bpy.props import (
    StringProperty, BoolProperty, FloatProperty,
    IntProperty, FloatVectorProperty
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
    from .region_solver import triangulate_polylines, solve_regions
except ImportError:
    # Fallback para desenvolvimento
    import importlib.util
    _here = os.path.dirname(__file__)
    spec = importlib.util.spec_from_file_location("api_router", os.path.join(_here, "api_router.py"))
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
    spec2 = importlib.util.spec_from_file_location("region_solver", os.path.join(_here, "region_solver.py"))
    region_solver = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(region_solver)
    from region_solver import triangulate_polylines, solve_regions

# Verifica scikit-image
try:
    from skimage import measure
    from scipy import ndimage
    SKIMAGE_AVAILABLE = True
except ImportError:
    SKIMAGE_AVAILABLE = False
    print("Tracer Plus: scikit-image e scipy são necessários")


LINE_LAYER_NAME = "Lines"
FILL_LAYER_NAME = "Fill"
LINE_MAT_NAME = "GP_Trace_Line"
FILL_MAT_NAME = "GP_Trace_Fill"
FILL_HOLDOUT_MAT_NAME = "GP_Trace_Fill Holdout"


# ============================================
# UTILITÁRIOS
# ============================================

def _ensure_gpencil_data(mat):
    """Garante que o material tenha dados de Grease Pencil (GPv3/Blender 5)."""
    if not getattr(mat, 'grease_pencil', None):
        try:
            bpy.data.materials.create_gpencil_data(mat)
        except Exception:
            pass
    return mat.grease_pencil


def _hex(rgb):
    """Hex string de uma cor (usado como chave/nome de material)."""
    def ch(v):
        return f"{int(max(0.0, min(1.0, v)) * 255):02x}"
    return ch(rgb[0]) + ch(rgb[1]) + ch(rgb[2])


def get_or_create_line_material(gp_obj, color_rgb=(0, 0, 0)):
    """Material só de LINHA (stroke), sem fill. Um material por cor."""
    name = f"GP_TraceLine_{_hex(color_rgb)}"
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name=name)
        mat.use_fake_user = True
    gpmat = _ensure_gpencil_data(mat)
    if gpmat:
        gpmat.show_stroke = True
        gpmat.show_fill = False
        # GPv3/Blender 5: a cor do stroke é 'color' (não 'stroke_color')
        gpmat.color = (color_rgb[0], color_rgb[1], color_rgb[2], 1.0)
    return _append_material(gp_obj, mat)


def get_or_create_fill_material(gp_obj, color_rgb, holdout=False):
    """Material só de FILL, sem stroke. holdout = recorta buracos. Um material por cor."""
    name = FILL_HOLDOUT_MAT_NAME if holdout else f"GP_TraceFill_{_hex(color_rgb)}"
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name=name)
        mat.use_fake_user = True
    gpmat = _ensure_gpencil_data(mat)
    if gpmat:
        gpmat.show_fill = True
        gpmat.show_stroke = False
        if hasattr(gpmat, 'use_fill_holdout'):
            gpmat.use_fill_holdout = holdout
        if not holdout:
            gpmat.fill_color = (color_rgb[0], color_rgb[1], color_rgb[2], 1.0)
    return _append_material(gp_obj, mat)


def _append_material(gp_obj, mat):
    """Adiciona o material ao objeto se necessário e retorna seu índice de slot."""
    idx = gp_obj.material_slots.find(mat.name)
    if idx < 0:
        gp_obj.data.materials.append(mat)
        idx = gp_obj.material_slots.find(mat.name)
    return idx


def _get_frame_strokes(frame):
    """Acessa a coleção de strokes compatível GPv2/GPv3."""
    if hasattr(frame, 'nuclear_strokes'):
        return frame.nuclear_strokes
    elif hasattr(frame, 'drawing') and hasattr(frame.drawing, 'strokes'):
        return frame.drawing.strokes
    return frame.strokes


def simplify_contour_douglas_peucker(contour, tolerance):
    """Simplifica contorno usando algoritmo Douglas-Peucker."""
    if len(contour) <= 2:
        return [list(c) for c in contour]

    dmax = 0
    index = 0
    end = len(contour) - 1
    for i in range(1, end):
        d = point_line_distance(contour[i], contour[0], contour[end])
        if d > dmax:
            index = i
            dmax = d

    if dmax > tolerance:
        left = simplify_contour_douglas_peucker(contour[:index + 1], tolerance)
        right = simplify_contour_douglas_peucker(contour[index:], tolerance)
        return left[:-1] + right
    else:
        return [list(contour[0]), list(contour[end])]


def point_line_distance(point, line_start, line_end):
    """Distância de um ponto a um segmento de reta."""
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
    bl_description = "Converte uma imagem em Grease Pencil: contornos como linhas e regiões como fill"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: StringProperty(subtype='FILE_PATH')

    # === O QUE GERAR ===
    generate_lines: BoolProperty(
        name="Gerar Linhas",
        description="Cria strokes de linha a partir dos contornos da imagem",
        default=True
    )
    generate_fill: BoolProperty(
        name="Gerar Preenchimento",
        description="Detecta regiões fechadas e cria strokes de fill atrás das linhas",
        default=True
    )
    keep_holes: BoolProperty(
        name="Manter Buracos",
        description="Usa regra par-ímpar: espaços internos (anéis/janelas) ficam vazados. "
                    "Desligue para preencher tudo sólido (mais robusto em arte bagunçada)",
        default=True
    )

    # === DETECÇÃO ===
    level: FloatProperty(
        name="Limiar",
        description="Nível de cinza onde o contorno é traçado (0.5 = meio-tom). "
                    "Imagens com linha escura sobre fundo claro funcionam bem em ~0.5",
        default=0.5,
        min=0.05,
        max=0.95
    )
    precision: FloatProperty(
        name="Fechar Vãos",
        description="Pontos próximos viram um só. MENOR fecha vãos MAIORES na linha "
                    "(útil para regiões que não fecham). 1.0 = precisão de 1 pixel",
        default=1.0,
        min=0.05,
        max=4.0
    )
    min_contour_length: IntProperty(
        name="Contorno Mínimo",
        description="Ignora contornos com menos pontos que este valor (remove ruído)",
        default=15,
        min=1,
        max=200
    )
    simplify_strokes: FloatProperty(
        name="Simplificação",
        description="Remove pontos redundantes das linhas (0 = nenhum)",
        default=0.2,
        min=0.0,
        max=1.0
    )

    # === PRÉ-PROCESSAMENTO ===
    pre_blur: FloatProperty(
        name="Suavização Prévia",
        description="Suaviza a imagem antes de traçar (remove ruído)",
        default=0.5,
        min=0.0,
        max=3.0
    )
    contrast_boost: FloatProperty(
        name="Contraste",
        description="Aumenta o contraste antes de traçar (1.0 = normal)",
        default=1.0,
        min=0.5,
        max=3.0
    )

    # === APARÊNCIA / TRANSFORMAÇÃO ===
    image_scale: FloatProperty(
        name="Escala",
        description="Unidades de mundo por pixel da imagem",
        default=0.01,
        min=0.0005,
        max=0.1
    )
    line_thickness: FloatProperty(
        name="Espessura da Linha",
        description="Raio dos pontos de linha (em unidades de mundo)",
        default=0.02,
        min=0.001,
        max=1.0
    )
    fill_color: FloatVectorProperty(
        name="Cor do Fill",
        subtype='COLOR',
        size=3,
        default=(0.5, 0.5, 0.5),
        min=0.0, max=1.0,
        description="Cor plana usada quando 'Usar Cor da Imagem' está desligado"
    )
    use_image_color: BoolProperty(
        name="Usar Cor da Imagem",
        description="Amostra a cor média de cada região (fill) e contorno (linha) da imagem original. "
                    "Desligado: fill usa a 'Cor do Fill' e linhas ficam pretas",
        default=True
    )

    def execute(self, context):
        if not SKIMAGE_AVAILABLE:
            self.report({'ERROR'}, "Instale: pip install scikit-image scipy")
            return {'CANCELLED'}

        if not (self.generate_lines or self.generate_fill):
            self.report({'WARNING'}, "Ative ao menos Linhas ou Preenchimento.")
            return {'CANCELLED'}

        try:
            if not os.path.exists(self.filepath):
                self.report({'ERROR'}, f"Arquivo não encontrado: {self.filepath}")
                return {'CANCELLED'}

            # --- Carrega e pré-processa ---
            self.report({'INFO'}, "Carregando imagem...")
            pil = Image.open(self.filepath)
            W, H = pil.size
            img_rgb = np.asarray(pil.convert('RGB')).astype(np.float32) / 255.0
            gray = np.asarray(pil.convert('L')).astype(np.float32) / 255.0
            if self.contrast_boost != 1.0:
                gray = np.clip((gray - 0.5) * self.contrast_boost + 0.5, 0, 1)
            if self.pre_blur > 0:
                gray = ndimage.gaussian_filter(gray, sigma=self.pre_blur)

            # --- Contornos em tons de cinza (uma linha por borda, sem duplicação) ---
            self.report({'INFO'}, "Extraindo contornos...")
            raw_contours = measure.find_contours(gray, self.level)
            raw_contours = [c for c in raw_contours if len(c) >= self.min_contour_length]
            if not raw_contours:
                self.report({'WARNING'}, "Nenhum contorno. Ajuste o 'Limiar' ou o 'Contorno Mínimo'.")
                return {'CANCELLED'}
            self.report({'INFO'}, f"{len(raw_contours)} contornos encontrados")

            # Polilinhas 2D em (x=col, y=row) para o solver
            poly2d = [[(float(p[1]), float(p[0])) for p in c] for c in raw_contours]

            # --- Cria objeto Grease Pencil ---
            if is_gpv3():
                bpy.ops.object.grease_pencil_add(type='EMPTY')
            else:
                bpy.ops.object.gpencil_add(type='EMPTY')
            gp_obj = context.active_object
            gp_obj.name = "Traced_Image"
            gp_data = gp_obj.data

            # Remove layers padrão
            if hasattr(gp_data.layers, 'clear'):
                gp_data.layers.clear()
            else:
                for layer in list(gp_data.layers):
                    gp_data.layers.remove(layer)

            current_frame = context.scene.frame_current
            s = self.image_scale

            def to_co(x, y):
                """(col, row) da imagem -> coordenada de mundo no plano XZ, em pé."""
                return Vector(((x - W / 2.0) * s, 0.0, -(y - H / 2.0) * s))

            def sample_fill_color(co):
                """Cor média dos pixels dentro do polígono da região."""
                from skimage.draw import polygon
                rr = [p[1] for p in co]
                cc = [p[0] for p in co]
                yy, xx = polygon(rr, cc, shape=(H, W))
                if len(yy) == 0:
                    return tuple(self.fill_color)
                return tuple(float(v) for v in img_rgb[yy, xx].mean(axis=0))

            def sample_line_color(pts):
                """Cor média dos pixels ao longo do contorno."""
                cols = np.clip(np.array([p[0] for p in pts]).astype(int), 0, W - 1)
                rows = np.clip(np.array([p[1] for p in pts]).astype(int), 0, H - 1)
                return tuple(float(v) for v in img_rgb[rows, cols].mean(axis=0))

            n_fill = 0
            n_lines = 0

            # --- FILL (atrás) ---
            if self.generate_fill:
                self.report({'INFO'}, "Resolvendo regiões...")
                tr = triangulate_polylines(poly2d, self.precision)
                regions = solve_regions(tr, keep_holes=self.keep_holes) if tr else []
                regions = [(co, hole) for (co, hole) in regions if len(co) >= 3]

                if regions:
                    fill_layer = gp_data.layers.new(name=FILL_LAYER_NAME, set_active=True)
                    fill_frame = new_active_frame(fill_layer.frames, current_frame)
                    fill_strokes = _get_frame_strokes(fill_frame)

                    fill_idx = (None if self.use_image_color
                                else get_or_create_fill_material(gp_obj, self.fill_color, holdout=False))
                    holdout_idx = (get_or_create_fill_material(gp_obj, self.fill_color, holdout=True)
                                   if self.keep_holes else fill_idx)

                    # Preenchimentos primeiro, buracos por cima
                    for co, is_hole in sorted(regions, key=lambda r: r[1]):
                        if is_hole and not self.keep_holes:
                            continue
                        if is_hole:
                            midx = holdout_idx
                        elif self.use_image_color:
                            midx = get_or_create_fill_material(gp_obj, sample_fill_color(co), holdout=False)
                        else:
                            midx = fill_idx
                        stroke = fill_strokes.new()
                        stroke.points.add(len(co))
                        stroke.use_cyclic = True
                        stroke.material_index = midx
                        for i, c in enumerate(co):
                            stroke.points[i].co = to_co(c[0], c[1])
                            stroke.points[i].pressure = 0.01
                            stroke.points[i].strength = 1.0
                        if not is_hole:
                            n_fill += 1
                else:
                    self.report({'WARNING'}, "Nenhuma região fechada. Diminua 'Fechar Vãos'.")

            # --- LINHAS (na frente) ---
            if self.generate_lines:
                line_layer = gp_data.layers.new(name=LINE_LAYER_NAME, set_active=True)
                line_frame = new_active_frame(line_layer.frames, current_frame)
                line_strokes = _get_frame_strokes(line_frame)
                line_idx_black = None if self.use_image_color else get_or_create_line_material(gp_obj, (0, 0, 0))

                for contour in poly2d:
                    pts = contour
                    closed = (abs(pts[0][0] - pts[-1][0]) < 1.0 and abs(pts[0][1] - pts[-1][1]) < 1.0)
                    if self.simplify_strokes > 0 and len(pts) > 2:
                        pts = simplify_contour_douglas_peucker(pts, self.simplify_strokes * 3.0)
                    if len(pts) < 2:
                        continue

                    line_idx = (get_or_create_line_material(gp_obj, sample_line_color(contour))
                                if self.use_image_color else line_idx_black)
                    stroke = line_strokes.new()
                    stroke.points.add(len(pts))
                    stroke.use_cyclic = closed
                    stroke.material_index = line_idx
                    for i, c in enumerate(pts):
                        stroke.points[i].co = to_co(c[0], c[1])
                        stroke.points[i].pressure = self.line_thickness
                        stroke.points[i].strength = 1.0
                    n_lines += 1

            insert_gp_keyframe_if_auto(gp_obj, current_frame)

            # Configura viewport (cosmético — nunca deve abortar o tracing)
            try:
                for area in context.screen.areas:
                    if area.type == 'VIEW_3D':
                        for space in area.spaces:
                            if space.type == 'VIEW_3D':
                                space.shading.type = 'SOLID'
                                if hasattr(space.overlay, 'show_gpencil'):
                                    space.overlay.show_gpencil = True
                                break
                        break
                if bpy.ops.view3d.view_all.poll():
                    bpy.ops.view3d.view_all(center=True)
            except Exception:
                pass

            self.report({'INFO'}, f"Concluído: {n_lines} linha(s), {n_fill} região(ões) preenchida(s)")
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

    factor: FloatProperty(name="Fator", default=0.5, min=0.0, max=1.0)

    def execute(self, context):
        obj = context.active_object
        if not obj or not obj_is_gp(obj):
            self.report({'ERROR'}, "Selecione um objeto Grease Pencil")
            return {'CANCELLED'}

        total_removed = 0
        for layer in obj.data.layers:
            if hasattr(layer, 'hide') and layer.hide:
                continue
            for frame in layer.frames:
                if not is_frame_valid(frame):
                    continue
                strokes = _get_frame_strokes(frame)
                for stroke in strokes:
                    if len(stroke.points) <= 3:
                        continue
                    original = len(stroke.points)
                    points = [list(stroke.points[i].co) for i in range(len(stroke.points))]
                    simplified = simplify_contour_douglas_peucker(points, self.factor * 10)
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
        for obj in list(bpy.data.objects):
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
        scn = context.scene

        box = layout.box()
        box.label(text="Tracing de Imagem", icon='IMAGE_DATA')
        box.operator("gp.trace_image", text="Selecionar Imagem", icon='FILE_IMAGE')

        if scn.tracer_show_advanced:
            box = layout.box()
            box.label(text="O que gerar", icon='OUTLINER_DATA_GP_LAYER')
            col = box.column(align=True)
            col.prop(scn, "tracer_generate_lines")
            col.prop(scn, "tracer_generate_fill")
            col.prop(scn, "tracer_keep_holes")

            box = layout.box()
            box.label(text="Detecção", icon='TOOL_SETTINGS')
            col = box.column(align=True)
            col.prop(scn, "tracer_level")
            col.prop(scn, "tracer_precision")
            col.prop(scn, "tracer_min_contour")
            col.prop(scn, "tracer_simplify_strokes")

            box = layout.box()
            box.label(text="Pré-processamento", icon='IMAGE_ZDEPTH')
            col = box.column(align=True)
            col.prop(scn, "tracer_pre_blur")
            col.prop(scn, "tracer_contrast_boost")

            box = layout.box()
            box.label(text="Aparência", icon='OBJECT_ORIGIN')
            col = box.column(align=True)
            col.prop(scn, "tracer_image_scale")
            col.prop(scn, "tracer_line_thickness")
            col.prop(scn, "tracer_use_image_color")
            sub = col.column(align=True)
            sub.enabled = not scn.tracer_use_image_color
            sub.prop(scn, "tracer_fill_color")

        box.prop(scn, "tracer_show_advanced", text="Configurações Avançadas", icon='SETTINGS')

        box = layout.box()
        box.label(text="Ferramentas", icon='TOOL_SETTINGS')
        box.operator("gp.simplify_strokes", text="Simplificar Selecionados", icon='MOD_SIMPLIFY')
        box.operator("gp.clear_traces", text="Limpar Todos", icon='TRASH')

        box = layout.box()
        box.label(text="Dicas", icon='INFO')
        col = box.column(align=True)
        col.label(text="• Sem regiões? Diminua 'Fechar Vãos'")
        col.label(text="• Linha grossa/dupla? Suba o 'Limiar'")
        col.label(text="• Ruído? Suba 'Suavização' e 'Contorno Mínimo'")

        box = layout.box()
        box.label(text="Status", icon='CHECKMARK')
        col = box.column(align=True)
        col.label(text=f"Modo: {'GPv3' if is_gpv3() else 'GPv2'}")
        col.label(text=f"scikit-image: {'✓ OK' if SKIMAGE_AVAILABLE else '✗ Faltando'}")


# ============================================
# PROPRIEDADES
# ============================================

def register_properties():
    S = bpy.types.Scene
    S.tracer_show_advanced = BoolProperty(default=False)
    S.tracer_generate_lines = BoolProperty(default=True, name="Gerar Linhas")
    S.tracer_generate_fill = BoolProperty(default=True, name="Gerar Preenchimento")
    S.tracer_keep_holes = BoolProperty(default=True, name="Manter Buracos")
    S.tracer_level = FloatProperty(default=0.5, min=0.05, max=0.95, name="Limiar")
    S.tracer_precision = FloatProperty(default=1.0, min=0.05, max=4.0, name="Fechar Vãos")
    S.tracer_min_contour = IntProperty(default=15, min=1, max=200, name="Contorno Mínimo")
    S.tracer_simplify_strokes = FloatProperty(default=0.2, min=0.0, max=1.0, name="Simplificação")
    S.tracer_pre_blur = FloatProperty(default=0.5, min=0.0, max=3.0, name="Suavização Prévia")
    S.tracer_contrast_boost = FloatProperty(default=1.0, min=0.5, max=3.0, name="Contraste")
    S.tracer_image_scale = FloatProperty(default=0.01, min=0.0005, max=0.1, name="Escala")
    S.tracer_line_thickness = FloatProperty(default=0.02, min=0.001, max=1.0, name="Espessura da Linha")
    S.tracer_fill_color = FloatVectorProperty(subtype='COLOR', size=3, default=(0.5, 0.5, 0.5),
                                              min=0.0, max=1.0, name="Cor do Fill")
    S.tracer_use_image_color = BoolProperty(default=True, name="Usar Cor da Imagem")


def unregister_properties():
    props = ['tracer_show_advanced', 'tracer_generate_lines', 'tracer_generate_fill',
             'tracer_keep_holes', 'tracer_level', 'tracer_precision', 'tracer_min_contour',
             'tracer_simplify_strokes', 'tracer_pre_blur', 'tracer_contrast_boost',
             'tracer_image_scale', 'tracer_line_thickness', 'tracer_fill_color',
             'tracer_use_image_color']
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
        layout.label(text="Tracer Plus v3.0.0")
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
    print("Tracer Plus v3.0.0")
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

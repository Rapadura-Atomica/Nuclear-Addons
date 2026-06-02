import bpy
import math
from collections import deque
from .common import *
from ..utils import *
from ..api_router import *

MATTE_LAYER_NAME = "AutoMatte"
MATTE_FILL_MAT_NAME = "AutoMatte"
MATTE_HOLDOUT_MAT_NAME = "AutoMatte Holdout"


# ---------------------------------------------------------------------------
# Dependency-free region solver
#
# Unlike nijiGPen's SmartFill (which needs SciPy max-flow + PyClipper to colour
# each region from a user hint), Auto Matte fills *every* closed region with a
# single colour. That removes the labelling step entirely, so the whole pipeline
# can run on Blender-native triangulation + a pure-Python parity flood fill.
# ---------------------------------------------------------------------------

def lineart_triangulation(stroke_list, t_mat, poly_list, scale_factor, resolution):
    """Constrained Delaunay triangulation of the line art using Blender's native solver.
    Returns a dict with vertices/segments/triangles/orig_edges (orig_edges marks the
    segments that come from the original strokes, i.e. the 'walls')."""
    corners = get_2d_bound_box(stroke_list, t_mat)
    corners = [co * scale_factor for co in corners]
    co_idx = {}
    tr_input = dict(vertices=[], segments=[])
    for i, co_list in enumerate(poly_list):
        for j, co in enumerate(co_list):
            key = (int(co[0] * resolution), int(co[1] * resolution))
            if key not in co_idx:
                co_idx[key] = len(co_idx)
                tr_input['vertices'].append(tuple(co))
            if j > 0:
                key0 = (int(co_list[j - 1][0] * resolution), int(co_list[j - 1][1] * resolution))
                tr_input['segments'].append((co_idx[key], co_idx[key0]))
            if j == len(co_list) - 1 and stroke_list[i].use_cyclic:
                key0 = (int(co_list[0][0] * resolution), int(co_list[0][1] * resolution))
                tr_input['segments'].append((co_idx[key], co_idx[key0]))
    # Several margins around the bound box so the exterior region is well defined
    for ratio in (0.1, 0.3, 0.5):
        tr_input['vertices'] += pad_2d_box(corners, ratio)

    tr_output = {}
    (tr_output['vertices'], tr_output['segments'], tr_output['triangles'],
     _, tr_output['orig_edges'], _) = geometry.delaunay_2d_cdt(
        tr_input['vertices'], tr_input['segments'], [], 0, 1e-9)
    return tr_output


def _edge_key(a, b):
    return (a, b) if a < b else (b, a)


def solve_matte_regions(tr_output, keep_holes=True):
    """Detect the regions to fill from a triangulated line art.

    The line art partitions the plane into flat areas ('regions') separated by the
    original stroke edges ('walls'). We:
      1. group triangles into regions through connected components over NON-wall edges
         (so a region is never split by an unrelated diagonal),
      2. seed the exterior region geometrically (the region of the left-most triangle,
         which is always on the convex hull / padding ring -- this avoids the global
         inversion that bites a naive 'single-owner-edge = exterior' seed), and
      3. BFS the region-adjacency graph, counting how many walls separate each region
         from the exterior.

    keep_holes=True  -> even-odd rule: regions an odd number of walls deep are filled,
                        so negative space (rings/windows) stays empty (punched as holes).
    keep_holes=False -> binary rule: every region enclosed by the line art is filled
                        solid. This is bulletproof on messy/overlapping art.

    Working on whole regions instead of per-triangle parity removes the checkerboard
    artefacts that overlapping strokes used to cause.

    Returns a list of (loop_co, is_hole), one per boundary loop, in scaled 2D coords."""
    vertices = tr_output['vertices']
    segments = tr_output['segments']
    triangles = tr_output['triangles']
    orig_edges = tr_output['orig_edges']
    n_tri = len(triangles)
    if n_tri == 0:
        return []

    # Walls = edges that belong to an original stroke
    solid = set()
    for i, seg in enumerate(segments):
        if len(orig_edges[i]) > 0:
            solid.add(_edge_key(seg[0], seg[1]))

    # Map every edge to the triangle(s) that share it
    edge_tris = {}
    for ti, tri in enumerate(triangles):
        for e in (_edge_key(tri[0], tri[1]), _edge_key(tri[1], tri[2]), _edge_key(tri[2], tri[0])):
            edge_tris.setdefault(e, []).append(ti)

    # 1. Group triangles into regions (union-find over non-wall shared edges)
    parent = list(range(n_tri))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e, tris in edge_tris.items():
        if e not in solid and len(tris) == 2:
            parent[find(tris[0])] = find(tris[1])

    # 2. Region-adjacency graph (regions sharing a wall edge)
    region_adj = {}
    for e, tris in edge_tris.items():
        if e in solid and len(tris) == 2:
            ra, rb = find(tris[0]), find(tris[1])
            if ra != rb:
                region_adj.setdefault(ra, set()).add(rb)
                region_adj.setdefault(rb, set()).add(ra)

    # 3. Seed the exterior region geometrically, then BFS wall-depth over regions
    ext_tri = min(range(n_tri), key=lambda t: min(vertices[v][0] for v in triangles[t]))
    ext_region = find(ext_tri)
    level = {ext_region: 0}
    queue = deque([ext_region])
    while queue:
        r = queue.popleft()
        for nb in region_adj.get(r, ()):
            if nb not in level:
                level[nb] = level[r] + 1
                queue.append(nb)

    # A region the BFS never reaches is a fully isolated pocket; default it to filled.
    if keep_holes:
        fill_mask = [(level.get(find(t), 1) % 2) == 1 for t in range(n_tri)]
    else:
        fill_mask = [level.get(find(t), 1) >= 1 for t in range(n_tri)]

    # Build directed boundary half-edges, keeping the filled region on the left.
    # Outer contours come out CCW (area > 0), holes come out CW (area < 0).
    adj = {}
    for ti, tri in enumerate(triangles):
        if not fill_mask[ti]:
            continue
        a, b, c = tri
        area2 = ((vertices[b][0] - vertices[a][0]) * (vertices[c][1] - vertices[a][1])
                 - (vertices[c][0] - vertices[a][0]) * (vertices[b][1] - vertices[a][1]))
        seq = (a, b, c) if area2 >= 0 else (a, c, b)
        for k in range(3):
            u, v = seq[k], seq[(k + 1) % 3]
            opp = None
            for t in edge_tris[_edge_key(u, v)]:
                if t != ti:
                    opp = t
                    break
            if opp is None or not fill_mask[opp]:
                adj.setdefault(u, []).append(v)

    # Chain half-edges into closed loops
    loops = []
    remaining = sum(len(v) for v in adj.values())
    while remaining > 0:
        start = next((k for k, v in adj.items() if v), None)
        if start is None:
            break
        loop = [start]
        cur = start
        while adj.get(cur):
            nv = adj[cur].pop()
            remaining -= 1
            if nv == start:
                break
            loop.append(nv)
            cur = nv
        if len(loop) >= 3:
            loops.append(loop)

    # Classify and emit
    result = []
    for loop in loops:
        co = [vertices[i] for i in loop]
        area2 = 0.0
        for i in range(len(co)):
            x1, y1 = co[i]
            x2, y2 = co[(i + 1) % len(co)]
            area2 += x1 * y2 - x2 * y1
        is_hole = area2 < 0
        result.append((_simplify_collinear(co), is_hole))
    return result


def _simplify_collinear(co, eps=1e-6):
    """Drop near-collinear interior points to keep generated strokes light."""
    if len(co) < 3:
        return co
    out = []
    n = len(co)
    for i in range(n):
        p0 = co[(i - 1) % n]
        p1 = co[i]
        p2 = co[(i + 1) % n]
        cross = (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p2[0] - p0[0]) * (p1[1] - p0[1])
        seg = max((p2[0] - p0[0]) ** 2 + (p2[1] - p0[1]) ** 2, 1e-12)
        if (cross * cross) / seg > eps:
            out.append(p1)
    return out if len(out) >= 3 else co


# ---------------------------------------------------------------------------
# Material / layer helpers
# ---------------------------------------------------------------------------

def _get_or_create_material(gp_obj, name, color, holdout=False):
    mat = bpy.data.materials.get(name)
    if mat is None or not getattr(mat, 'grease_pencil', None):
        mat = bpy.data.materials.new(name)
        bpy.data.materials.create_gpencil_data(mat)
    gpmat = mat.grease_pencil
    gpmat.show_fill = True
    gpmat.show_stroke = False
    gpmat.use_fill_holdout = holdout
    if not holdout:
        gpmat.fill_color = (color[0], color[1], color[2], 1.0)
    # Make sure it is in the object's slots
    idx = gp_obj.material_slots.find(mat.name)
    if idx < 0:
        gp_obj.data.materials.append(mat)
        idx = len(gp_obj.material_slots) - 1
    return idx


def _move_layer_to_bottom(gp_obj, layer):
    """Best-effort: send the matte layer to the bottom of the stack (drawn behind the
    line art). Different Blender 4.3-5.0 builds expose slightly different APIs, so try
    several and never fail the operation if none works."""
    layers = gp_obj.data.layers
    for attempt in (
        lambda: layers.move_bottom(layer),
        lambda: layers.move(layer, 'BOTTOM'),
    ):
        try:
            attempt()
            return
        except Exception:
            pass
    try:
        prev_active = layers.active
        layers.active = layer
        for _ in range(len(layers)):
            bpy.ops.grease_pencil.layer_reorder(direction='DOWN')
        layers.active = prev_active
    except Exception:
        pass


def _get_or_create_matte_layer(gp_obj):
    layers = gp_obj.data.layers
    for layer in layers:
        if layer.info == MATTE_LAYER_NAME:
            return layer
    matte_layer = layers.new(MATTE_LAYER_NAME)
    _move_layer_to_bottom(gp_obj, matte_layer)
    return matte_layer


# ---------------------------------------------------------------------------
# Operator
# ---------------------------------------------------------------------------

class GenerateAutoMatteOperator(bpy.types.Operator):
    """Fill every closed region of the active line art with a flat colour on a dedicated AutoMatte layer"""
    bl_idname = "gpencil.generate_auto_matte"
    bl_label = "Generate Auto Matte"
    bl_category = 'View'
    bl_options = {'REGISTER', 'UNDO'}

    matte_color: bpy.props.FloatVectorProperty(
        name="Matte Color",
        subtype="COLOR",
        default=(0.5, 0.5, 0.5),
        min=0.0, max=1.0, size=3,
        description="Flat colour used to fill every closed region"
    )  # type: ignore
    line_layer: bpy.props.StringProperty(
        name="Line Art Layer",
        description="Layer whose strokes define the closed regions. Empty = active layer",
        default='',
        search=lambda self, context, edit_text: [layer.info for layer in context.object.data.layers
                                                  if layer.info != MATTE_LAYER_NAME]
    )  # type: ignore
    precision: bpy.props.FloatProperty(
        name="Precision",
        default=0.05, min=0.001, max=1,
        description="Treat points in proximity as one. Lower values close larger gaps in the line art"
    )  # type: ignore
    fill_holes: bpy.props.BoolProperty(
        name="Keep Holes",
        default=True,
        description="Punch the inner negative space of shapes (e.g. rings) as real holes using a holdout material. "
                    "Turn this OFF to fill every enclosed region solid -- the most robust option for messy or overlapping line art"
    )  # type: ignore
    clear_previous: bpy.props.BoolProperty(
        name="Clear Previous Matte",
        default=True,
        description="Remove existing strokes on the AutoMatte layer for this frame before generating"
    )  # type: ignore

    @classmethod
    def poll(cls, context):
        return context.object is not None and obj_is_gp(context.object)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "matte_color")
        row = layout.row()
        row.label(text="Line Art Layer:")
        row.prop(self, "line_layer", icon='OUTLINER_DATA_GP_LAYER', text='')
        layout.prop(self, "precision")
        layout.prop(self, "fill_holes")
        layout.prop(self, "clear_previous")

    def execute(self, context):
        gp_obj = context.object
        current_mode = gp_obj.mode

        # Resolve the line art layer
        if self.line_layer:
            line_layer = next((l for l in gp_obj.data.layers if l.info == self.line_layer), None)
        else:
            line_layer = gp_obj.data.layers.active
        if line_layer is None:
            self.report({"WARNING"}, "Please select a line art layer.")
            return {'CANCELLED'}
        if line_layer.info == MATTE_LAYER_NAME:
            self.report({"WARNING"}, "The line art layer cannot be the AutoMatte layer.")
            return {'CANCELLED'}

        line_frame = line_layer.active_frame
        if not is_frame_valid(line_frame) or len(line_frame.nijigp_strokes) < 1:
            self.report({"WARNING"}, "The line art layer has no strokes on the current frame.")
            return {'CANCELLED'}

        # Edit the drawing data from Object mode for safety
        if current_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        try:
            n_regions = self._generate(context, gp_obj, line_layer, line_frame)
        finally:
            if gp_obj.mode != current_mode:
                bpy.ops.object.mode_set(mode=current_mode)

        if n_regions == 0:
            self.report({"WARNING"}, "No closed region found. Try lowering Precision to close gaps.")
        else:
            self.report({"INFO"}, f"Auto Matte: filled {n_regions} region(s).")
        return {'FINISHED'}

    def _generate(self, context, gp_obj, line_layer, line_frame):
        stroke_list = [s for s in line_frame.nijigp_strokes if not is_stroke_protected(s, gp_obj)]
        if len(stroke_list) < 1:
            return 0

        t_mat, inv_mat = get_transformation_mat(mode=context.scene.nijigp_working_plane,
                                                gp_obj=gp_obj, strokes=stroke_list,
                                                operator=self, requires_layer=False)
        poly_list, depth_list, scale_factor = get_2d_co_from_strokes(stroke_list, t_mat, scale=True)
        depth_tree = DepthLookupTree(poly_list, depth_list)

        tr_output = lineart_triangulation(stroke_list, t_mat, poly_list, scale_factor, self.precision)
        regions = solve_matte_regions(tr_output, keep_holes=self.fill_holes)
        regions = [(co, hole) for (co, hole) in regions if len(co) >= 3]
        if not regions:
            return 0

        # Materials and target layer/frame
        fill_idx = _get_or_create_material(gp_obj, MATTE_FILL_MAT_NAME, self.matte_color, holdout=False)
        holdout_idx = (_get_or_create_material(gp_obj, MATTE_HOLDOUT_MAT_NAME, self.matte_color, holdout=True)
                       if self.fill_holes else fill_idx)

        matte_layer = _get_or_create_matte_layer(gp_obj)
        frame_number = context.scene.frame_current
        matte_frame = get_layer_frame_by_number(matte_layer, frame_number)
        if not matte_frame or matte_frame.frame_number != frame_number:
            matte_frame = new_active_frame(matte_layer.frames, frame_number)

        if self.clear_previous:
            for stroke in list(matte_frame.nijigp_strokes):
                matte_frame.nijigp_strokes.remove(stroke)

        # Emit outer fills first, then holes on top so the holdout punches through
        ordered = sorted(regions, key=lambda r: r[1])  # False (fill) before True (hole)
        n_filled = 0
        for co, is_hole in ordered:
            if is_hole and not self.fill_holes:
                continue
            new_stroke = matte_frame.nijigp_strokes.new()
            new_stroke.points.add(len(co))
            new_stroke.use_cyclic = True
            new_stroke.material_index = holdout_idx if is_hole else fill_idx
            for i, c in enumerate(co):
                new_stroke.points[i].co = restore_3d_co(c, depth_tree.get_depth(c), inv_mat, scale_factor)
            if not is_hole:
                n_filled += 1

        # Keep the user working on their line art, not on the matte layer
        try:
            gp_obj.data.layers.active = line_layer
        except Exception:
            pass

        refresh_strokes(gp_obj, [frame_number])
        return n_filled

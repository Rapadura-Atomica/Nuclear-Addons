import bpy
import math
import numpy as np
from .common import *
from ..utils import *
from ..api_router import *
from ..solvers.line_fit import longest_path_spine, smooth_and_resample


# ---------------------------------------------------------------------------
# Automatic line cleanup
#
# Turns rough, overlapping sketch strokes into clean lines. Based on nijiGPen's
# "Single-Line Fit" and "Multi-Line (Cluster) Fit" but reworked to need no
# SciPy: the heavy maths (Euclidean MST, longest path, smoothing) lives in
# ../solvers/line_fit.py as pure numpy, and the hierarchical clustering is
# replaced by single-linkage via union-find (a distance-cut single-linkage
# dendrogram is exactly the connected components of the threshold graph).
#
# Two operators share everything here:
#   * Cleanup Lines        -> all selected strokes become ONE clean line.
#   * Cleanup Lines (Multi) -> selection is split into clusters of nearby/similar
#                              strokes and each cluster becomes its own line.
# ---------------------------------------------------------------------------

# How many times the spine is pulled onto the centre of the sketch bundle. One
# pass centres the line among the strokes without dragging detail away; more
# passes would start to over-smooth, which we deliberately avoid here.
CENTROID_ITERATIONS = 1

# distance_to_another_stroke returns this when two lines are not comparable.
NO_SIMILARITY = 65535.0


# ---------------------------------------------------------------------------
# Point gathering / fitting (single line)
# ---------------------------------------------------------------------------

def _collect_points(stroke_list, t_mat, ignore_transparent):
    """Project every selected point to 2D and gather its attributes.

    Returns (kdt, arrays) where kdt is a balanced mathutils.kdtree over the 2D
    points and arrays holds per-point numpy data used for averaging."""
    poly_list, depth_list, _ = get_2d_co_from_strokes(stroke_list, t_mat, scale=False)

    co, depth, pressure, strength, uv_rot = [], [], [], [], []
    color = []
    seen = set()
    for i, stroke in enumerate(stroke_list):
        if len(stroke.points) < 2:
            continue
        for j, point in enumerate(stroke.points):
            if ignore_transparent and point.strength < 1e-3:
                continue
            key = (round(poly_list[i][j][0], 6), round(poly_list[i][j][1], 6))
            if key in seen:
                continue
            seen.add(key)
            co.append((poly_list[i][j][0], poly_list[i][j][1]))
            depth.append(depth_list[i][j])
            pressure.append(point.pressure)
            strength.append(point.strength)
            uv_rot.append(point.uv_rotation)
            color.append(tuple(point.vertex_color))

    n = len(co)
    if n < 4:
        return None, None

    kdt = kdtree.KDTree(n)
    for idx, c in enumerate(co):
        kdt.insert(xy0(c), idx)
    kdt.balance()

    arrays = {
        'co': np.asarray(co, dtype=float),
        'depth': np.asarray(depth, dtype=float),
        'pressure': np.asarray(pressure, dtype=float),
        'strength': np.asarray(strength, dtype=float),
        'uv_rotation': np.asarray(uv_rot, dtype=float),
        'color': np.asarray(color, dtype=float),
    }
    return kdt, arrays


def _neighbor_indices(kdt, co, radius):
    """Indices of original points within radius of co (falls back to nearest one)."""
    hits = kdt.find_range(xy0(co), radius)
    if hits:
        return [h[1] for h in hits]
    _, idx, _ = kdt.find(xy0(co))
    return [idx]


def _fit_cleanup_line(stroke_list, t_mat, search_radius, ignore_transparent,
                      closed, smooth_steps, chaikin_steps, resample_length):
    """Compute the cleaned-up polyline and its inherited attributes for one
    bundle of strokes.

    Returns (co2d, attrs, mean_radius) or (None, None, 0.0) when the input is
    too sparse to fit."""
    kdt, arr = _collect_points(stroke_list, t_mat, ignore_transparent)
    if kdt is None:
        return None, None, 0.0

    spine, total_length = longest_path_spine(arr['co'].tolist())
    if not spine:
        return None, None, 0.0

    # Pull the spine onto the centre of the surrounding sketch points. This is
    # what fuses several rough lines into one clean centreline.
    centered = np.asarray(spine, dtype=float)
    for _ in range(CENTROID_ITERATIONS):
        moved = np.empty_like(centered)
        for i, c in enumerate(centered):
            idxs = _neighbor_indices(kdt, c, search_radius)
            moved[i] = arr['co'][idxs].mean(axis=0)
        centered = moved

    co2d = smooth_and_resample(centered, total_length, closed=closed,
                               smooth_steps=smooth_steps, chaikin_steps=chaikin_steps,
                               resample_length=resample_length)
    if len(co2d) < 2:
        return None, None, 0.0

    m = len(co2d)
    attrs = {
        'depth': np.empty(m),
        'pressure': np.empty(m),
        'strength': np.empty(m),
        'uv_rotation': np.empty(m),
        'color': np.empty((m, 4)),
    }
    for i, c in enumerate(co2d):
        idxs = _neighbor_indices(kdt, c, search_radius)
        attrs['depth'][i] = arr['depth'][idxs].mean()
        attrs['pressure'][i] = arr['pressure'][idxs].mean()
        attrs['strength'][i] = arr['strength'][idxs].mean()
        attrs['uv_rotation'][i] = arr['uv_rotation'][idxs].mean()
        attrs['color'][i] = arr['color'][idxs].mean(axis=0)

    mean_radius = float(arr['pressure'].mean()) if len(arr['pressure']) else 0.0
    return co2d, attrs, mean_radius


# ---------------------------------------------------------------------------
# Stroke similarity + clustering (multi line), dependency-free
# ---------------------------------------------------------------------------

def _stroke_kdtree(co_list):
    kdt = kdtree.KDTree(len(co_list))
    for i, c in enumerate(co_list):
        kdt.insert(xy0(c), i)
    kdt.balance()
    return kdt


def _polyline_length(co_list):
    total = 0.0
    for i in range(1, len(co_list)):
        a, b = co_list[i - 1], co_list[i]
        total += math.hypot(b[0] - a[0], b[1] - a[1])
    return total


def _polyline_distance(co_list1, co_list2, kdt2, angular_tolerance):
    """Similarity cost between two polylines (ported from nijiGPen's
    distance_to_another_stroke). Low = similar; NO_SIMILARITY = unrelated or
    differing direction by more than angular_tolerance."""
    n1, n2 = len(co_list1), len(co_list2)
    if n1 < 2 or n2 < 2:
        return NO_SIMILARITY

    idx_arr = np.zeros(n1, dtype=int)
    dist_arr = np.zeros(n1)
    for i in range(n1):
        _, idx_arr[i], dist_arr[i] = kdt2.find(xy0(co_list1[i]))

    contact_idx1 = int(np.argmin(dist_arr))
    contact_idx2 = min(int(idx_arr[contact_idx1]), n2 - 2)
    contact_idx1 = min(contact_idx1, n1 - 2)
    direction1 = Vector(co_list1[contact_idx1 + 1]) - Vector(co_list1[contact_idx1])
    direction2 = Vector(co_list2[contact_idx2 + 1]) - Vector(co_list2[contact_idx2])
    if math.isclose(direction1.length, 0) or math.isclose(direction2.length, 0):
        angle_diff = 0.0
    else:
        angle_diff = direction1.angle(direction2)

    end2 = n2 - 1
    if angle_diff > math.pi / 2:        # lines drawn in opposite directions still match
        angle_diff = math.pi - angle_diff
        end2 = 0
    if angle_diff > angular_tolerance:
        return NO_SIMILARITY

    total_cost, total_count = 0.0, 0.0
    for i in range(n1):
        total_cost += dist_arr[i]
        total_count += 1
        if idx_arr[i] == end2:
            break
    return total_cost / total_count if total_count else NO_SIMILARITY


def _cluster_strokes(stroke_list, t_mat, criterion, cluster_dist, cluster_ratio,
                     cluster_num, angular_tolerance):
    """Split strokes into clusters of nearby/similar lines.

    Single-linkage clustering: a distance-cut dendrogram equals the connected
    components of the graph that links stroke pairs closer than the threshold,
    so a union-find over those pairs gives the same result without SciPy.
    Returns a list of stroke lists, ordered by drawing sequence."""
    n = len(stroke_list)
    poly_list, _, _ = get_2d_co_from_strokes(stroke_list, t_mat, scale=False)
    kdts = [_stroke_kdtree(p) for p in poly_list]
    lengths = [_polyline_length(p) for p in poly_list]

    edges = []  # (cost, i, j)
    for i in range(n):
        for j in range(i + 1, n):
            d1 = _polyline_distance(poly_list[i], poly_list[j], kdts[j], angular_tolerance)
            d2 = _polyline_distance(poly_list[j], poly_list[i], kdts[i], angular_tolerance)
            d = min(d1, d2)
            if criterion == 'RATIO' and d < NO_SIMILARITY:
                denom = 0.5 * (lengths[i] + lengths[j]) or 1e-9
                d = d / denom
            edges.append((d, i, j))

    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
            return True
        return False

    if criterion == 'NUM':
        comps = n
        for d, i, j in sorted(edges, key=lambda e: e[0]):
            if d >= NO_SIMILARITY or comps <= cluster_num:
                break
            if union(i, j):
                comps -= 1
    else:
        threshold = cluster_dist if criterion == 'DIST' else cluster_ratio / 100.0
        for d, i, j in edges:
            if d < threshold:
                union(i, j)

    # Group, ordered by the index of each cluster's first-drawn stroke.
    clusters = {}
    order = {}
    for i in range(n):
        root = find(i)
        if root not in clusters:
            clusters[root] = []
            order[root] = i
        clusters[root].append(stroke_list[i])
    return [clusters[r] for r in sorted(clusters, key=lambda r: order[r])]


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _delete_strokes(frame, target_strokes):
    """Remove exactly the given strokes from a frame, identified by their stable
    hash. Iterating indices in descending order keeps every remaining index valid
    while the collection shrinks, so no stroke is ever skipped or mis-deleted."""
    target_hashes = {s._hash for s in target_strokes}
    strokes = frame.nijigp_strokes
    for i in reversed(range(len(strokes))):
        s = strokes[i]
        if s._hash in target_hashes:
            strokes.remove(s)


def _create_clean_stroke(frame, gp_obj, co2d, attrs, mean_radius, inv_mat,
                         src_strokes, cfg):
    """Build one clean stroke from a fit result. cfg is the operator (read-only)."""
    if cfg.uniform_thickness:
        base = cfg.thickness if cfg.thickness > 1e-6 else (mean_radius or 0.02)
        radii = np.full(len(co2d), base)
    else:
        radii = attrs['pressure'].copy()
    radii = np.maximum(radii * cfg.thickness_scale, 1e-5)

    new_stroke = frame.nijigp_strokes.new()
    new_stroke.material_index = gp_obj.active_material_index
    copy_stroke_attributes(new_stroke, src_strokes,
                           copy_cap=True, copy_uv=True, copy_color=cfg.inherit_color)
    new_stroke.points.add(len(co2d))
    for i, point in enumerate(new_stroke.points):
        point.co = restore_3d_co(co2d[i], attrs['depth'][i], inv_mat)
        point.pressure = radii[i]
        point.strength = attrs['strength'][i]
        point.uv_rotation = attrs['uv_rotation'][i]
        if cfg.inherit_color:
            point.vertex_color = tuple(attrs['color'][i])
    new_stroke.use_cyclic = cfg.closed
    new_stroke.select = True
    return new_stroke


# ---------------------------------------------------------------------------
# Shared operator properties
# ---------------------------------------------------------------------------

class _CleanupConfig:
    """Fit + output options shared by the single- and multi-line operators."""
    line_spacing: bpy.props.IntProperty(
        name="Merge Distance",
        description="Sketch lines closer than this are fused into one. Increase it to "
                    "merge a looser, messier bundle of strokes",
        default=50, min=1, soft_max=200, subtype='PIXEL'
    )  # type: ignore
    smooth_steps: bpy.props.IntProperty(
        name="Smooth",
        description="Vertex averaging applied to the result. Keep it low to preserve the "
                    "shape of the original sketch; raise it only if the line stays jittery",
        default=1, min=0, max=20
    )  # type: ignore
    chaikin_steps: bpy.props.IntProperty(
        name="Roundness",
        description="Corner-cutting passes. 0 keeps every corner of the sketch; higher "
                    "values give a softer, more rounded line",
        default=1, min=0, max=4
    )  # type: ignore
    resample: bpy.props.BoolProperty(
        name="Resample",
        default=False,
        description="Redistribute the output points evenly. Off keeps the original point "
                    "density (more detail); on simplifies to evenly spaced points"
    )  # type: ignore
    resample_length: bpy.props.FloatProperty(
        name="Spacing",
        default=0.02, min=0.002, soft_max=0.5,
        description="Distance between points when resampling"
    )  # type: ignore
    closed: bpy.props.BoolProperty(
        name="Closed Shape",
        default=False,
        description="Treat each line as a closed loop instead of an open line"
    )  # type: ignore
    ignore_transparent: bpy.props.BoolProperty(
        name="Ignore Transparent",
        default=False,
        description="Skip points with zero opacity when fitting"
    )  # type: ignore
    uniform_thickness: bpy.props.BoolProperty(
        name="Uniform Thickness",
        default=True,
        description="Give the clean line a single, even thickness instead of inheriting "
                    "the uneven pressure of the sketch"
    )  # type: ignore
    thickness: bpy.props.FloatProperty(
        name="Thickness",
        default=0.0, min=0.0, soft_max=0.5, precision=4,
        description="Radius of the clean line when Uniform Thickness is on. "
                    "0 keeps the average thickness of the original sketch"
    )  # type: ignore
    thickness_scale: bpy.props.FloatProperty(
        name="Thickness Scale",
        default=1.0, min=0.0, soft_max=5.0,
        description="Multiply the final line thickness"
    )  # type: ignore
    inherit_color: bpy.props.BoolProperty(
        name="Inherit Color",
        default=True,
        description="Average the vertex color of the original strokes onto the new line"
    )  # type: ignore
    keep_original: bpy.props.BoolProperty(
        name="Keep Original Strokes",
        default=False,
        description="Keep the rough sketch strokes instead of replacing them with the clean line"
    )  # type: ignore

    @classmethod
    def poll(cls, context):
        return context.object is not None and obj_is_gp(context.object)

    def _draw_fit_options(self, col):
        col.label(text="Shape:")
        col.prop(self, "smooth_steps")
        col.prop(self, "chaikin_steps")
        row = col.row()
        row.prop(self, "resample")
        sub = row.row()
        sub.enabled = self.resample
        sub.prop(self, "resample_length")
        col.separator()
        col.label(text="Thickness:")
        col.prop(self, "uniform_thickness")
        if self.uniform_thickness:
            col.prop(self, "thickness")
        col.prop(self, "thickness_scale")
        col.separator()
        col.label(text="Output:")
        col.prop(self, "inherit_color")
        col.prop(self, "keep_original")

    def _resolve_target(self, context):
        """Return (layer, frame, selected_strokes) or (None, None, msg)."""
        gp_obj = context.object
        layer = gp_obj.data.layers.active
        if layer is None:
            return None, None, "Please select a layer."
        frame = layer.active_frame
        if not is_frame_valid(frame):
            return None, None, "The active layer has no drawing on this frame."
        stroke_list = get_input_strokes(gp_obj, frame)
        if len(stroke_list) < 1:
            return None, None, "Please select the sketch strokes to clean up (on the active layer)."
        return layer, frame, stroke_list


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class CleanupLinesOperator(_CleanupConfig, bpy.types.Operator):
    """Merge the selected rough sketch strokes into a single clean, smooth line"""
    bl_idname = "gpencil.automatte_cleanup_lines"
    bl_label = "Cleanup Lines"
    bl_category = 'View'
    bl_options = {'REGISTER', 'UNDO'}

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "line_spacing")
        col.prop(self, "closed")
        col.prop(self, "ignore_transparent")
        col.separator()
        self._draw_fit_options(col)

    def execute(self, context):
        gp_obj = context.object
        _, frame, stroke_list = self._resolve_target(context)
        if frame is None:
            self.report({'WARNING'}, stroke_list)  # stroke_list holds the message here
            return {'CANCELLED'}

        current_mode = gp_obj.mode
        if current_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        try:
            t_mat, inv_mat = get_transformation_mat(mode=context.scene.nijigp_working_plane,
                                                    gp_obj=gp_obj, strokes=stroke_list)
            search_radius = self.line_spacing / LINE_WIDTH_FACTOR
            resample_length = self.resample_length if self.resample else None

            co2d, attrs, mean_radius = _fit_cleanup_line(
                stroke_list, t_mat, search_radius, self.ignore_transparent,
                self.closed, self.smooth_steps, self.chaikin_steps, resample_length)
            if co2d is None:
                self.report({'WARNING'}, "Not enough stroke detail to fit a line. "
                                         "Select more of the sketch or raise Merge Distance.")
                return {'CANCELLED'}

            if not self.keep_original:
                _delete_strokes(frame, stroke_list)
            _create_clean_stroke(frame, gp_obj, co2d, attrs, mean_radius, inv_mat,
                                 stroke_list, self)
            refresh_strokes(gp_obj, [frame.frame_number])
        finally:
            if gp_obj.mode != current_mode:
                bpy.ops.object.mode_set(mode=current_mode)

        verb = "cleaned up" if self.keep_original else "merged"
        self.report({'INFO'}, f"Cleanup: {verb} {len(stroke_list)} stroke(s) into one clean line.")
        return {'FINISHED'}


class ClusterCleanupLinesOperator(_CleanupConfig, bpy.types.Operator):
    """Split the selection into clusters of nearby/similar strokes and clean each cluster into its own line"""
    bl_idname = "gpencil.automatte_cluster_cleanup"
    bl_label = "Cleanup Lines (Multi)"
    bl_category = 'View'
    bl_options = {'REGISTER', 'UNDO'}

    cluster_criterion: bpy.props.EnumProperty(
        name="Group By",
        items=[('RATIO', 'Distance (Relative)', 'Split where the gap is large relative to the line length'),
               ('DIST', 'Distance (Absolute)', 'Split where the gap exceeds a fixed distance'),
               ('NUM', 'Max Lines', 'Allow at most this many clusters')],
        default='RATIO',
        description="How the selected strokes are divided into separate lines"
    )  # type: ignore
    cluster_ratio: bpy.props.FloatProperty(
        name="Relative Gap",
        default=5.0, min=0.0, soft_max=100.0, subtype='PERCENTAGE',
        description="Strokes split into different lines when their gap is larger than this "
                    "share of the line length"
    )  # type: ignore
    cluster_dist: bpy.props.FloatProperty(
        name="Absolute Gap",
        default=0.05, min=0.0, unit='LENGTH',
        description="Strokes split into different lines when their gap exceeds this distance"
    )  # type: ignore
    cluster_num: bpy.props.IntProperty(
        name="Max Lines",
        default=8, min=1,
        description="Maximum number of clean lines to produce"
    )  # type: ignore
    angular_tolerance: bpy.props.FloatProperty(
        name="Angular Tolerance",
        default=math.pi / 3, min=math.pi / 18, max=math.pi / 2, unit='ROTATION',
        description="Strokes whose directions differ by more than this are never put in the same line"
    )  # type: ignore

    def draw(self, context):
        col = self.layout.column()
        col.label(text="Clustering:")
        col.prop(self, "cluster_criterion")
        if self.cluster_criterion == 'RATIO':
            col.prop(self, "cluster_ratio")
        elif self.cluster_criterion == 'DIST':
            col.prop(self, "cluster_dist")
        else:
            col.prop(self, "cluster_num")
        col.prop(self, "angular_tolerance")
        col.separator()
        col.label(text="Input:")
        col.prop(self, "line_spacing")
        col.prop(self, "closed")
        col.prop(self, "ignore_transparent")
        col.separator()
        self._draw_fit_options(col)

    def execute(self, context):
        gp_obj = context.object
        _, frame, stroke_list = self._resolve_target(context)
        if frame is None:
            self.report({'WARNING'}, stroke_list)
            return {'CANCELLED'}
        if len(stroke_list) < 2:
            self.report({'WARNING'}, "Select at least 2 strokes (use Cleanup Lines for a single line).")
            return {'CANCELLED'}

        current_mode = gp_obj.mode
        if current_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        try:
            t_mat, inv_mat = get_transformation_mat(mode=context.scene.nijigp_working_plane,
                                                    gp_obj=gp_obj, strokes=stroke_list)
            search_radius = self.line_spacing / LINE_WIDTH_FACTOR
            resample_length = self.resample_length if self.resample else None

            clusters = _cluster_strokes(stroke_list, t_mat, self.cluster_criterion,
                                        self.cluster_dist, self.cluster_ratio,
                                        self.cluster_num, self.angular_tolerance)

            # Fit every cluster first (reads the originals), then delete and emit.
            results = []
            for cl in clusters:
                co2d, attrs, mean_radius = _fit_cleanup_line(
                    cl, t_mat, search_radius, self.ignore_transparent,
                    self.closed, self.smooth_steps, self.chaikin_steps, resample_length)
                if co2d is not None:
                    results.append((co2d, attrs, mean_radius, cl))

            if not results:
                self.report({'WARNING'}, "Could not fit any cluster. Try raising Merge Distance "
                                         "or selecting cleaner strokes.")
                return {'CANCELLED'}

            if not self.keep_original:
                fitted = [s for (_, _, _, cl) in results for s in cl]
                _delete_strokes(frame, fitted)

            for co2d, attrs, mean_radius, cl in results:
                _create_clean_stroke(frame, gp_obj, co2d, attrs, mean_radius, inv_mat, cl, self)

            refresh_strokes(gp_obj, [frame.frame_number])
        finally:
            if gp_obj.mode != current_mode:
                bpy.ops.object.mode_set(mode=current_mode)

        self.report({'INFO'}, f"Cleanup (Multi): {len(stroke_list)} stroke(s) -> "
                              f"{len(results)} clean line(s).")
        return {'FINISHED'}

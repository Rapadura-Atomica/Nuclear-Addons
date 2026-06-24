import bpy
import numpy as np
from .common import *
from ..utils import *
from ..api_router import *
from ..solvers.line_fit import longest_path_spine, smooth_and_resample


# ---------------------------------------------------------------------------
# Automatic line cleanup
#
# Turns a bundle of rough, overlapping sketch strokes into a single clean line.
# Based on nijiGPen's "Single-Line Fit" but reworked to need no SciPy: the heavy
# maths (Euclidean MST, longest path, curve smoothing) lives in
# ../solvers/line_fit.py as pure numpy. This file is the Blender glue -- it
# projects the strokes to 2D, finds the centreline, pulls it to the middle of
# the sketch bundle (the step that "merges" nearby lines) and writes out one
# stroke that inherits the averaged attributes of the originals.
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
    """Compute the cleaned-up polyline and its inherited attributes.

    Returns (co2d, attrs) where co2d is an (M, 2) array and attrs maps each
    attribute name to an (M,) / (M, 4) array, or (None, None) when the input is
    too sparse to fit."""
    kdt, arr = _collect_points(stroke_list, t_mat, ignore_transparent)
    if kdt is None:
        return None, None

    spine, total_length = longest_path_spine(arr['co'].tolist())
    if not spine:
        return None, None

    # Pull each spine point to the centroid of the surrounding sketch points.
    # This is what fuses several rough lines into one clean centreline.
    centered = []
    for c in spine:
        idxs = _neighbor_indices(kdt, c, search_radius)
        centered.append(arr['co'][idxs].mean(axis=0))
    centered = np.asarray(centered, dtype=float)

    co2d = smooth_and_resample(centered, total_length, closed=closed,
                               smooth_steps=smooth_steps, chaikin_steps=chaikin_steps,
                               resample_length=resample_length)
    if len(co2d) < 2:
        return None, None

    # Re-inherit point attributes onto the final, resampled line.
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
    return co2d, attrs


class CleanupLinesOperator(bpy.types.Operator):
    """Merge the selected rough sketch strokes into a single clean, smooth line"""
    bl_idname = "gpencil.automatte_cleanup_lines"
    bl_label = "Cleanup Lines"
    bl_category = 'View'
    bl_options = {'REGISTER', 'UNDO'}

    line_spacing: bpy.props.IntProperty(
        name="Merge Distance",
        description="Sketch lines closer than this are fused into one. Increase it to "
                    "merge a looser, messier bundle of strokes",
        default=50, min=1, soft_max=200, subtype='PIXEL'
    )  # type: ignore
    smooth_steps: bpy.props.IntProperty(
        name="Smooth",
        description="Amount of vertex averaging applied to the result",
        default=2, min=0, max=20
    )  # type: ignore
    chaikin_steps: bpy.props.IntProperty(
        name="Roundness",
        description="Corner-cutting passes. Higher values give a softer, more curved line",
        default=2, min=0, max=4
    )  # type: ignore
    resample: bpy.props.BoolProperty(
        name="Resample",
        default=True,
        description="Distribute the output points evenly along the line"
    )  # type: ignore
    resample_length: bpy.props.FloatProperty(
        name="Spacing",
        default=0.02, min=0.002, soft_max=0.5,
        description="Distance between points when resampling"
    )  # type: ignore
    closed: bpy.props.BoolProperty(
        name="Closed Shape",
        default=False,
        description="Treat the selection as a closed loop instead of an open line"
    )  # type: ignore
    ignore_transparent: bpy.props.BoolProperty(
        name="Ignore Transparent",
        default=False,
        description="Skip points with zero opacity when fitting"
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

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, "line_spacing")
        col.prop(self, "closed")
        col.prop(self, "ignore_transparent")
        col.separator()
        col.label(text="Shape:")
        col.prop(self, "smooth_steps")
        col.prop(self, "chaikin_steps")
        row = col.row()
        row.prop(self, "resample")
        sub = row.row()
        sub.enabled = self.resample
        sub.prop(self, "resample_length")
        col.separator()
        col.label(text="Output:")
        col.prop(self, "inherit_color")
        col.prop(self, "keep_original")

    def execute(self, context):
        gp_obj = context.object
        layer = gp_obj.data.layers.active
        if layer is None:
            self.report({'WARNING'}, "Please select a layer.")
            return {'CANCELLED'}
        frame = layer.active_frame
        if not is_frame_valid(frame):
            self.report({'WARNING'}, "The active layer has no drawing on this frame.")
            return {'CANCELLED'}

        stroke_list = get_input_strokes(gp_obj, frame)
        if len(stroke_list) < 1:
            self.report({'WARNING'}, "Please select the sketch strokes to clean up.")
            return {'CANCELLED'}

        current_mode = gp_obj.mode
        if current_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        try:
            t_mat, inv_mat = get_transformation_mat(mode=context.scene.nijigp_working_plane,
                                                    gp_obj=gp_obj, strokes=stroke_list)
            search_radius = self.line_spacing / LINE_WIDTH_FACTOR
            resample_length = self.resample_length if self.resample else None

            co2d, attrs = _fit_cleanup_line(
                stroke_list, t_mat, search_radius, self.ignore_transparent,
                self.closed, self.smooth_steps, self.chaikin_steps, resample_length)

            if co2d is None:
                self.report({'WARNING'}, "Not enough stroke detail to fit a line. "
                                         "Select more of the sketch or raise Merge Distance.")
                return {'CANCELLED'}

            new_stroke = frame.nijigp_strokes.new()
            new_stroke.material_index = gp_obj.active_material_index
            copy_stroke_attributes(new_stroke, stroke_list,
                                   copy_cap=True, copy_uv=True, copy_color=self.inherit_color)
            new_stroke.points.add(len(co2d))
            for i, point in enumerate(new_stroke.points):
                point.co = restore_3d_co(co2d[i], attrs['depth'][i], inv_mat)
                point.pressure = attrs['pressure'][i]
                point.strength = attrs['strength'][i]
                point.uv_rotation = attrs['uv_rotation'][i]
                if self.inherit_color:
                    point.vertex_color = tuple(attrs['color'][i])
            new_stroke.use_cyclic = self.closed
            new_stroke.select = True

            # Replace the rough sketch unless the artist asked to keep it
            if not self.keep_original:
                originals = set(stroke_list)
                for stroke in [s for s in frame.nijigp_strokes if s in originals]:
                    frame.nijigp_strokes.remove(stroke)

            refresh_strokes(gp_obj, [frame.frame_number])
        finally:
            if gp_obj.mode != current_mode:
                bpy.ops.object.mode_set(mode=current_mode)

        self.report({'INFO'}, f"Cleanup: merged {len(stroke_list)} stroke(s) into one clean line.")
        return {'FINISHED'}

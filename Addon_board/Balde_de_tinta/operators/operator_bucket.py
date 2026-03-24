# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import bpy
import numpy as np
from mathutils import *
from mathutils.geometry import intersect_line_plane, intersect_line_line

# Import from addon modules
from ..utils import *
from ..api_router import *
from .common import (
    get_input_strokes,
    get_input_frames,
    save_stroke_selection,
    load_stroke_selection,
    refresh_strokes,
    copy_stroke_attributes,
    smooth_stroke_attributes,
    get_generated_meshes
)
from ..solvers.graph import SmartFillSolver


# Constant for addon name
ADDON_NAME = "Balde_de_tinta"


class NIJIGP_OT_simple_bucket_fill(bpy.types.Operator):
    """Fill a closed area with the active material by clicking inside it"""
    bl_idname = "gpencil.nijigp_simple_bucket_fill"
    bl_label = "Bucket Fill"
    bl_description = "Click inside a closed area to fill it with the active material"
    bl_options = {'REGISTER', 'UNDO'}

    _waiting_for_click = False
    _modal_handler = None

    @classmethod
    def poll(cls, context):
        """Only available when a Grease Pencil object is active and in edit/draw mode"""
        if not context.object or not obj_is_gp(context.object):
            return False
        return context.mode in {'EDIT_GPENCIL', 'PAINT_GPENCIL', 'EDIT_GREASE_PENCIL', 'PAINT_GREASE_PENCIL'}

    def get_preferences(self, context):
        """Get addon preferences safely"""
        try:
            return context.preferences.addons[ADDON_NAME].preferences
        except KeyError:
            return None

    def invoke(self, context, event):
        """Activate modal mode to wait for click"""
        if context.area:
            context.area.tag_redraw()
        
        # Get preferences for bucket fill settings
        prefs = self.get_preferences(context)
        
        if prefs:
            self.click_tolerance = prefs.bucket_fill_tolerance
            self.use_fill_layer = prefs.bucket_fill_use_fill_layer
            self.fill_layer_name = prefs.bucket_fill_layer_name
        else:
            # Default values if preferences not available
            self.click_tolerance = 15.0
            self.use_fill_layer = True
            self.fill_layer_name = "Fills"
        
        # Store the current object and mode
        self.gp_obj = context.object
        self.original_mode = context.mode
        
        # Store transformation matrix and strokes before modal
        result = self.prepare_data(context)
        if result == {'CANCELLED'}:
            return {'CANCELLED'}
        
        # Add modal handler
        context.window_manager.modal_handler_add(self)
        
        # Change cursor to indicate waiting for click
        context.window.cursor_modal_set('EYEDROPPER')
        
        self._waiting_for_click = True
        
        # Build info message
        layer_info = f" -> Fill Layer: {self.fill_layer_name}" if self.use_fill_layer else ""
        self.report({"INFO"}, f"Click inside the area you want to fill (tolerance: {self.click_tolerance:.0f}px){layer_info}")
        
        return {'RUNNING_MODAL'}

    def prepare_data(self, context):
        """Pre-compute transformation and triangulation before modal"""
        gp_obj = self.gp_obj
        active_layer = gp_obj.data.layers.active
        
        if not active_layer:
            self.report({"WARNING"}, "No active layer found")
            return {'CANCELLED'}
        
        # Get or create fill layer if needed
        if self.use_fill_layer:
            self.fill_layer = self.get_or_create_fill_layer(gp_obj)
            if not self.fill_layer:
                self.report({"WARNING"}, f"Could not create fill layer: {self.fill_layer_name}")
                return {'CANCELLED'}
        else:
            self.fill_layer = active_layer
        
        # Get current frame
        if is_gpv3():
            self.current_frame = active_layer.active_frame
        else:
            self.current_frame = active_layer.active_frame
        
        if not self.current_frame:
            self.current_frame = active_layer.frames.new(context.scene.frame_current)
        
        # Get fill frame (same frame number as current frame)
        if self.use_fill_layer:
            self.fill_frame = self.get_or_create_frame(self.fill_layer, self.current_frame.frame_number)
        else:
            self.fill_frame = self.current_frame
        
        # Get all strokes from the active layer (these are the boundaries)
        self.all_strokes = get_input_strokes(gp_obj, self.current_frame, select_all=True)
        
        if len(self.all_strokes) < 1:
            self.report({"WARNING"}, "No strokes found in the current frame")
            return {'CANCELLED'}
        
        # Store original selection to restore later
        self.select_map = save_stroke_selection(gp_obj)
        
        # Get transformation matrix for 2D projection
        self.t_mat, self.inv_mat = get_transformation_mat(
            mode=context.scene.nijigp_working_plane,
            gp_obj=gp_obj,
            strokes=self.all_strokes,
            operator=self,
            requires_layer=False
        )
        
        # Convert strokes to 2D coordinates
        self.poly_list, self.depth_list, self.scale_factor = get_2d_co_from_strokes(
            self.all_strokes, self.t_mat, scale=True, correct_orientation=True
        )
        
        if len(self.poly_list) < 1:
            self.report({"WARNING"}, "Could not convert strokes to 2D")
            return {'CANCELLED'}
        
        # Create depth lookup tree
        self.depth_lookup = DepthLookupTree(self.poly_list, self.depth_list)
        
        # Triangulate the line art with higher resolution for better tolerance
        self.tr_map = lineart_triangulation(
            self.all_strokes, self.t_mat, self.poly_list, self.scale_factor, 0.02
        )
        
        if len(self.tr_map['triangles']) < 1:
            self.report({"WARNING"}, "Triangulation failed")
            return {'CANCELLED'}
        
        # Build graph from triangulation
        self.solver = SmartFillSolver()
        self.solver.build_graph(self.tr_map)
        
        # Precompute triangle centers for distance-based fallback
        self.triangle_centers = []
        for tri in self.tr_map['triangles']:
            v0 = Vector(self.tr_map['vertices'][tri[0]])
            v1 = Vector(self.tr_map['vertices'][tri[1]])
            v2 = Vector(self.tr_map['vertices'][tri[2]])
            center = (v0 + v1 + v2) / 3
            self.triangle_centers.append(center)
        
        return {'FINISHED'}

    def get_or_create_fill_layer(self, gp_obj):
        """Get existing fill layer or create a new one"""
        layers = gp_obj.data.layers
        
        # Check if layer already exists
        for layer in layers:
            if hasattr(layer, 'info') and layer.info == self.fill_layer_name:
                return layer
            elif hasattr(layer, 'name') and layer.name == self.fill_layer_name:
                return layer
        
        # Create new layer
        if is_gpv3():
            new_layer = layers.new(name=self.fill_layer_name, set_active=False)
        else:
            new_layer = layers.new(name=self.fill_layer_name)
        
        return new_layer

    def get_or_create_frame(self, layer, frame_number):
        """Get existing frame or create a new one"""
        for frame in layer.frames:
            if frame.frame_number == frame_number:
                return frame
        
        return layer.frames.new(frame_number)

    def modal(self, context, event):
        """Handle mouse click detection"""
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS' and self._waiting_for_click:
            # Mouse click detected
            self._waiting_for_click = False
            context.window.cursor_modal_restore()
            
            # Get click position
            self.click_x = event.mouse_region_x
            self.click_y = event.mouse_region_y
            
            # Execute fill at click position
            result = self.fill_at_click(context)
            
            if result == {'CANCELLED'}:
                self.report({"WARNING"}, "Click outside any closed area or fill failed")
            else:
                self.report({"INFO"}, "Fill created successfully")
            
            return {'FINISHED'}
        
        elif event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS':
            # Cancel operation
            self._waiting_for_click = False
            context.window.cursor_modal_restore()
            self.report({"INFO"}, "Bucket fill cancelled")
            return {'CANCELLED'}
        
        # Redraw to keep UI responsive
        if context.area:
            context.area.tag_redraw()
        
        return {'RUNNING_MODAL'}

    def fill_at_click(self, context):
        """Execute fill at the stored click position"""
        
        # Get click position in 3D using raycast
        click_3d = self.get_click_3d(context)
        
        if click_3d is None:
            self.report({"WARNING"}, "Could not determine click position in 3D")
            return {'CANCELLED'}
        
        # Convert to 2D coordinates
        click_2d = self.t_mat @ click_3d
        click_2d_scaled = Vector((
            click_2d[0] * self.scale_factor,
            click_2d[1] * self.scale_factor
        ))
        
        # Find which triangle was clicked (with tolerance)
        triangle_idx = self.find_triangle_at_point_with_tolerance(
            (click_2d_scaled[0], click_2d_scaled[1]),
            context
        )
        
        if triangle_idx < 0:
            self.report({"WARNING"}, "Click outside any closed area")
            return {'CANCELLED'}
        
        # Initialize labels: only the clicked triangle gets label 1
        self.solver.labels = -np.ones(len(self.tr_map['triangles']), dtype=np.int32)
        self.solver.labels[triangle_idx] = 1
        
        # Propagate labels to all connected triangles (flood fill)
        self.solver.propagate_labels()
        
        # Extract contours of the labeled region
        contours, component_labels = self.solver.get_contours()
        
        # Find the contour corresponding to label 1
        target_contour = None
        for i, contour_list in enumerate(contours):
            if i < len(component_labels) and component_labels[i] == 1:
                if len(contour_list) > 0:
                    target_contour = contour_list[0]
                    break
        
        if not target_contour or len(target_contour) < 3:
            self.report({"WARNING"}, "Could not extract contour from selected area")
            return {'CANCELLED'}
        
        # Get active material index
        if self.gp_obj.active_material:
            material_index = self.gp_obj.material_slots.find(self.gp_obj.active_material.name)
            if material_index < 0:
                material_index = 0
        else:
            material_index = 0
        
        # Create new stroke in the fill frame
        new_stroke = self.fill_frame.nijigp_strokes.new()
        new_stroke.use_cyclic = True
        new_stroke.material_index = material_index
        new_stroke.select = True
        
        # Add points to the stroke
        num_points = len(target_contour)
        new_stroke.points.add(num_points)
        
        # Restore 3D coordinates for each point
        for i, co_2d in enumerate(target_contour):
            depth = self.depth_lookup.get_depth(co_2d)
            co_3d = restore_3d_co(co_2d, depth, self.inv_mat, self.scale_factor)
            new_stroke.points[i].co = co_3d
            new_stroke.points[i].strength = 1.0
        
        # Deselect all other strokes and select only the new one
        op_deselect()
        new_stroke.select = True
        
        # Refresh to ensure proper display
        refresh_strokes(self.gp_obj, [self.fill_frame.frame_number])
        
        # Restore original selection
        load_stroke_selection(self.gp_obj, self.select_map)
        
        return {'FINISHED'}

    def get_click_3d(self, context):
        """
        Get 3D coordinates of mouse click using raycast against Grease Pencil strokes.
        This is more accurate than projection-based methods.
        """
        region = context.region
        rv3d = context.space_data.region_3d
        
        if not region or not rv3d:
            return None
        
        # Get mouse position in region coordinates
        coord = (self.click_x, self.click_y)
        
        # Get ray from view through mouse position
        from bpy_extras.view3d_utils import region_2d_to_vector_3d, region_2d_to_origin_3d
        ray_origin = region_2d_to_origin_3d(region, rv3d, coord)
        ray_direction = region_2d_to_vector_3d(region, rv3d, coord)
        
        # Find closest point on Grease Pencil strokes
        closest_point = None
        min_distance = float('inf')
        
        for stroke in self.all_strokes:
            if len(stroke.points) < 2:
                continue
            
            for i in range(len(stroke.points) - 1):
                p1 = stroke.points[i].co
                p2 = stroke.points[i + 1].co
                
                # Find intersection of ray with line segment
                intersect = intersect_line_line(
                    ray_origin, ray_origin + ray_direction * 10000,
                    p1, p2
                )
                
                if intersect and len(intersect) >= 2:
                    point_on_ray = intersect[0]
                    
                    # Check if the intersection point is within the segment bounds
                    seg_vec = p2 - p1
                    seg_len = seg_vec.length
                    if seg_len > 0:
                        t = (point_on_ray - p1).dot(seg_vec) / (seg_len * seg_len)
                        if 0 <= t <= 1:
                            dist = (point_on_ray - ray_origin).length
                            if dist < min_distance:
                                min_distance = dist
                                closest_point = point_on_ray
        
        # If raycast didn't hit any stroke, fall back to plane intersection
        if closest_point is None:
            # Use the working plane as fallback
            plane_normal = self.t_mat.inverted().to_3x3() @ Vector((0, 0, 1))
            plane_point = self.gp_obj.location
            
            closest_point = intersect_line_plane(
                ray_origin,
                ray_origin + ray_direction * 10000,
                plane_point,
                plane_normal
            )
        
        return closest_point

    def find_triangle_at_point_with_tolerance(self, point_co, context):
        """
        Find triangle containing point, with tolerance.
        If exact point not in any triangle, find nearest triangle within tolerance.
        """
        import pyclipper
        
        # First, check if point is inside any polygon (closed stroke)
        inside_any_polygon = False
        for poly in self.poly_list:
            if pyclipper.PointInPolygon(point_co, poly) == 1:
                inside_any_polygon = True
                break
        
        if not inside_any_polygon:
            # Point is outside all polygons, try to find nearby triangle with tolerance
            return self.find_nearest_triangle(point_co, context)
        
        # Find exact triangle containing the point
        for i, tri in enumerate(self.tr_map['triangles']):
            poly = [self.tr_map['vertices'][v] for v in tri]
            if pyclipper.PointInPolygon(point_co, poly) == 1:
                return i
        
        # Point is inside a polygon but not in any triangle (rare)
        # Fall back to nearest triangle
        return self.find_nearest_triangle(point_co, context)

    def find_nearest_triangle(self, point_co, context):
        """
        Find the triangle closest to the click point within tolerance.
        """
        point = Vector(point_co)
        
        # Convert pixel tolerance to world units (approximate)
        # Use a more generous scaling for better user experience
        tolerance_world = self.click_tolerance / 50.0
        
        # Find triangle with closest center
        best_idx = -1
        best_dist = float('inf')
        
        for i, center in enumerate(self.triangle_centers):
            dist = (center - point).length
            if dist < best_dist and dist < tolerance_world:
                best_dist = dist
                best_idx = i
        
        if best_idx >= 0 and best_dist > 0:
            self.report({"INFO"}, f"Click adjusted by {best_dist:.2f} units")
        
        return best_idx


def lineart_triangulation(stroke_list, t_mat, poly_list, scale_factor, resolution):
    """
    Perform Delaunay triangulation on the line art strokes.
    Returns a triangle map compatible with SmartFillSolver.
    """
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
                key0 = (int(co_list[j-1][0] * resolution), int(co_list[j-1][1] * resolution))
                tr_input['segments'].append((co_idx[key], co_idx[key0]))
            if j == len(co_list) - 1 and stroke_list[i].use_cyclic:
                key0 = (int(co_list[0][0] * resolution), int(co_list[0][1] * resolution))
                tr_input['segments'].append((co_idx[key], co_idx[key0]))
    
    # Add margins to the bounding box to ensure complete triangulation
    margin_sizes = (0.1, 0.3, 0.5)
    for ratio in margin_sizes:
        tr_input['vertices'].extend(pad_2d_box(corners, ratio))
    
    tr_output = {}
    tr_output['vertices'], tr_output['segments'], tr_output['triangles'], _, tr_output['orig_edges'], _ = \
        geometry.delaunay_2d_cdt(tr_input['vertices'], tr_input['segments'], [], 0, 1e-9)
    
    return tr_output
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import bpy
import numpy as np
import time
import traceback
from mathutils import *
from mathutils.geometry import intersect_line_plane, intersect_line_line
from math import isclose

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


ADDON_NAME = "Balde_de_tinta"


class NIJIGP_OT_simple_bucket_fill(bpy.types.Operator):
    """Fill a closed area with the active material by clicking inside it"""
    bl_idname = "gpencil.nijigp_simple_bucket_fill"
    bl_label = "Bucket Fill"
    bl_description = "Click inside a closed area to fill it with the active material"
    bl_options = {'REGISTER', 'UNDO'}

    _waiting_for_click = False
    
    # Debug options
    debug_mode: bpy.props.BoolProperty(
        name="Debug Mode",
        description="Enable debug logging",
        default=False
    )

    @classmethod
    def poll(cls, context):
        if not context.object or not obj_is_gp(context.object):
            return False
        return context.mode in {'EDIT_GPENCIL', 'PAINT_GPENCIL', 'EDIT_GREASE_PENCIL', 'PAINT_GREASE_PENCIL'}

    def get_preferences(self, context):
        try:
            prefs = context.preferences.addons[ADDON_NAME].preferences
            if not hasattr(prefs, 'bucket_fill_tolerance'):
                prefs.bucket_fill_tolerance = 20.0
            if not hasattr(prefs, 'bucket_fill_auto_close_gap'):
                prefs.bucket_fill_auto_close_gap = 30.0
            if not hasattr(prefs, 'bucket_fill_use_fill_layer'):
                prefs.bucket_fill_use_fill_layer = True
            if not hasattr(prefs, 'bucket_fill_layer_name'):
                prefs.bucket_fill_layer_name = "Fills"
            if not hasattr(prefs, 'bucket_fill_use_simplification'):
                prefs.bucket_fill_use_simplification = True
            if not hasattr(prefs, 'bucket_fill_max_points'):
                prefs.bucket_fill_max_points = 200
            return prefs
        except KeyError:
            return None

    def invoke(self, context, event):
        start_time = time.time()
        
        prefs = self.get_preferences(context)
        
        if prefs:
            self.click_tolerance = prefs.bucket_fill_tolerance
            self.use_fill_layer = prefs.bucket_fill_use_fill_layer
            self.fill_layer_name = prefs.bucket_fill_layer_name
            self.auto_close_gap = prefs.bucket_fill_auto_close_gap
            self.use_simplification = prefs.bucket_fill_use_simplification
            self.max_points = prefs.bucket_fill_max_points
        else:
            self.click_tolerance = 20.0
            self.use_fill_layer = True
            self.fill_layer_name = "Fills"
            self.auto_close_gap = 30.0
            self.use_simplification = True
            self.max_points = 200
        
        self.gp_obj = context.object
        self.original_mode = context.mode
        self.current_frame_number = context.scene.frame_current
        
        result = self.prepare_data(context)
        if result == {'CANCELLED'}:
            return {'CANCELLED'}
        
        context.window_manager.modal_handler_add(self)
        context.window.cursor_modal_set('EYEDROPPER')
        
        self._waiting_for_click = True
        
        elapsed = time.time() - start_time
        self.report({"INFO"}, f"Ready ({elapsed:.1f}s) - {len(self.all_strokes)} strokes")
        
        return {'RUNNING_MODAL'}

    def prepare_data(self, context):
        """Pre-compute transformation and triangulation"""
        gp_obj = self.gp_obj
        active_layer = gp_obj.data.layers.active
        
        if not active_layer:
            self.report({"WARNING"}, "No active layer found")
            return {'CANCELLED'}
        
        # Get or create fill layer
        if self.use_fill_layer:
            self.fill_layer = self.get_or_create_fill_layer(gp_obj)
        else:
            self.fill_layer = active_layer
        
        # Get current frame
        if is_gpv3():
            self.current_frame = active_layer.active_frame
        else:
            self.current_frame = active_layer.active_frame
        
        if not self.current_frame:
            self.current_frame = active_layer.frames.new(self.current_frame_number)
        
        # Ensure fill frame exists
        if self.use_fill_layer:
            self.fill_frame = self.get_or_create_frame(self.fill_layer, self.current_frame_number)
        else:
            self.fill_frame = self.current_frame
        
        # Get all strokes from current frame
        self.all_strokes = get_input_strokes(gp_obj, self.current_frame, select_all=True)
        
        if len(self.all_strokes) < 1:
            self.report({"WARNING"}, "No strokes found")
            return {'CANCELLED'}
        
        # Simplify strokes if needed
        if self.use_simplification and self.max_points > 0:
            self.simplify_strokes()
        
        # Store original selection
        self.select_map = save_stroke_selection(gp_obj)
        
        # Get transformation matrix
        self.t_mat, self.inv_mat = get_transformation_mat(
            mode=context.scene.nijigp_working_plane,
            gp_obj=gp_obj,
            strokes=self.all_strokes,
            operator=self,
            requires_layer=False
        )
        
        # Convert strokes to 2D with guides
        self.poly_list, self.depth_list, self.scale_factor, self.guide_count = \
            self.get_2d_co_with_guides(self.all_strokes, self.t_mat)
        
        if len(self.poly_list) < 1:
            self.report({"WARNING"}, "Could not convert strokes to 2D")
            return {'CANCELLED'}
        
        # Align lists
        self.align_poly_and_depth_lists()
        
        # Create depth lookup
        try:
            self.depth_lookup = DepthLookupTree(self.poly_list, self.depth_list)
        except Exception as e:
            self.report({"WARNING"}, f"Depth lookup failed: {str(e)}")
            return {'CANCELLED'}
        
        # Triangulate
        self.tr_map = self.triangulate_optimized()
        
        self.triangle_count = len(self.tr_map.get('triangles', []))
        if self.triangle_count < 1:
            self.report({"WARNING"}, "Triangulation failed")
            return {'CANCELLED'}
        
        # Build graph
        self.solver = SmartFillSolver()
        self.solver.build_graph(self.tr_map)
        
        # Precompute triangle centers for fast search
        self.triangle_centers = []
        for tri in self.tr_map['triangles']:
            v0 = Vector(self.tr_map['vertices'][tri[0]])
            v1 = Vector(self.tr_map['vertices'][tri[1]])
            v2 = Vector(self.tr_map['vertices'][tri[2]])
            center = (v0 + v1 + v2) / 3
            self.triangle_centers.append(center)
        
        # KDTree for fast triangle search
        self.triangle_kdtree = kdtree.KDTree(len(self.triangle_centers))
        for i, center in enumerate(self.triangle_centers):
            self.triangle_kdtree.insert(Vector((center.x, center.y, 0.0)), i)
        self.triangle_kdtree.balance()
        
        return {'FINISHED'}

    def get_2d_co_with_guides(self, strokes, t_mat):
        """Convert strokes to 2D and generate guide lines"""
        import pyclipper
        
        poly_list = []
        depth_list = []
        guide_count = 0
        
        # First pass: convert strokes to 2D
        for stroke in strokes:
            if len(stroke.points) < 2:
                continue
            
            co_list = []
            depth_vals = []
            
            for point in stroke.points:
                transformed_co = t_mat @ point.co
                co_list.append([transformed_co[0], transformed_co[1]])
                depth_vals.append(transformed_co[2])
            
            poly_list.append(co_list)
            depth_list.append(depth_vals)
        
        # Calculate scale factor
        if len(poly_list) > 0:
            all_coords = [co for poly in poly_list for co in poly]
            if all_coords:
                xs = [c[0] for c in all_coords]
                ys = [c[1] for c in all_coords]
                w = max(xs) - min(xs)
                h = max(ys) - min(ys)
                scale_factor = 8192 / min(w, h, 8192) if w > 0 and h > 0 else 1.0
                
                for poly in poly_list:
                    for co in poly:
                        co[0] *= scale_factor
                        co[1] *= scale_factor
            else:
                scale_factor = 1.0
        else:
            scale_factor = 1.0
        
        # Guides for closing gaps
        if self.auto_close_gap > 0 and len(poly_list) > 0:
            gap_threshold = self.auto_close_gap / 25.0 * scale_factor
            
            # Collect endpoints
            endpoints = []
            for i, poly in enumerate(poly_list):
                if len(poly) >= 2:
                    endpoints.append((poly[0], i))
                    endpoints.append((poly[-1], i))
            
            # Find and connect nearby endpoints
            used = set()
            connections = 0
            
            for a_idx, (point_a, poly_a) in enumerate(endpoints):
                if a_idx in used:
                    continue
                
                best_idx = -1
                best_dist = float('inf')
                best_point = None
                
                for b_idx, (point_b, poly_b) in enumerate(endpoints):
                    if a_idx == b_idx or b_idx in used or poly_a == poly_b:
                        continue
                    
                    dx = point_a[0] - point_b[0]
                    dy = point_a[1] - point_b[1]
                    dist = (dx*dx + dy*dy) ** 0.5
                    
                    if dist < best_dist and dist < gap_threshold:
                        best_dist = dist
                        best_idx = b_idx
                        best_point = point_b
                
                if best_idx >= 0 and best_point:
                    poly_list.append([point_a, best_point])
                    depth_list.append([0, 0])
                    guide_count += 1
                    connections += 1
                    used.add(a_idx)
                    used.add(b_idx)
        
        return poly_list, depth_list, scale_factor, guide_count

    def triangulate_optimized(self):
        """Triangulação rápida e otimizada"""
        all_coords = [co for poly in self.poly_list for co in poly]
        if not all_coords:
            return {'vertices': [], 'segments': [], 'triangles': [], 'orig_edges': []}
        
        xs = [c[0] for c in all_coords]
        ys = [c[1] for c in all_coords]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        
        # Add margin
        expand = max(max_x - min_x, max_y - min_y) * 0.1
        min_x -= expand
        max_x += expand
        min_y -= expand
        max_y += expand
        
        co_idx = {}
        tr_input = dict(vertices=[], segments=[])
        
        # Add segments from polylines
        for co_list in self.poly_list:
            if len(co_list) < 2:
                continue
            
            prev_key = None
            for j, co in enumerate(co_list):
                key = (int(co[0] * 0.05), int(co[1] * 0.05))
                if key not in co_idx:
                    co_idx[key] = len(co_idx)
                    tr_input['vertices'].append(tuple(co))
                
                if j > 0 and prev_key is not None:
                    tr_input['segments'].append((prev_key, co_idx[key]))
                
                prev_key = co_idx[key]
        
        # Add boundary points
        for x in [min_x, max_x]:
            for y in [min_y, max_y]:
                key = (int(x * 0.05), int(y * 0.05))
                if key not in co_idx:
                    co_idx[key] = len(co_idx)
                    tr_input['vertices'].append((x, y))
        
        try:
            tr_output = {}
            tr_output['vertices'], tr_output['segments'], tr_output['triangles'], _, tr_output['orig_edges'], _ = \
                geometry.delaunay_2d_cdt(tr_input['vertices'], tr_input['segments'], [], 0, 1e-6)
            return tr_output
        except Exception as e:
            self.report({"WARNING"}, f"Triangulation error: {str(e)}")
            return {'vertices': [], 'segments': [], 'triangles': [], 'orig_edges': []}

    def extract_boundary_contour(self, labels):
        """Extrai contorno da região rotulada"""
        triangles = self.tr_map['triangles']
        vertices = self.tr_map['vertices']
        
        # Map edges to triangles
        edge_to_tris = {}
        for t_idx, tri in enumerate(triangles):
            for i in range(3):
                v1 = tri[i]
                v2 = tri[(i + 1) % 3]
                key = (min(v1, v2), max(v1, v2))
                if key not in edge_to_tris:
                    edge_to_tris[key] = []
                edge_to_tris[key].append(t_idx)
        
        # Collect boundary edges
        boundary_edges = []
        for key, tris in edge_to_tris.items():
            if len(tris) == 1:
                if labels[tris[0]] == 1:
                    boundary_edges.append(key)
            elif len(tris) == 2:
                t1, t2 = tris
                if (labels[t1] == 1) != (labels[t2] == 1):
                    boundary_edges.append(key)
        
        if not boundary_edges:
            return None
        
        # Build edge graph
        graph = {}
        for a, b in boundary_edges:
            graph.setdefault(a, []).append(b)
            graph.setdefault(b, []).append(a)
        
        # Find start point
        start = None
        for v, neighbors in graph.items():
            if len(neighbors) == 1:
                start = v
                break
        if start is None:
            start = next(iter(graph.keys()))
        
        # Walk the contour
        contour = []
        current = start
        prev = None
        max_iterations = len(boundary_edges) * 2
        iteration = 0
        
        while iteration < max_iterations:
            contour.append(current)
            neighbors = graph.get(current, [])
            
            next_v = None
            for n in neighbors:
                if n != prev:
                    next_v = n
                    break
            
            if next_v is None or next_v == start:
                break
            
            prev = current
            current = next_v
            iteration += 1
        
        if len(contour) < 3:
            return None
        
        # Convert to 2D coordinates
        return [vertices[v] for v in contour]

    def find_triangle_exact(self, point_co):
        """Encontra triângulo que contém o ponto"""
        import pyclipper
        
        point = (point_co[0], point_co[1])
        
        # Search with KDTree
        if hasattr(self, 'triangle_kdtree') and self.triangle_kdtree:
            search_center = Vector((point_co[0], point_co[1], 0.0))
            nearest = self.triangle_kdtree.find_n(search_center, 50)
            
            for _, idx, _ in nearest:
                if idx < len(self.tr_map['triangles']):
                    tri = self.tr_map['triangles'][idx]
                    poly = [self.tr_map['vertices'][v] for v in tri]
                    if pyclipper.PointInPolygon(point, poly) == 1:
                        return idx
                    
                    # Test with small tolerance
                    tolerance = self.click_tolerance / 100.0
                    for dx, dy in [(tolerance, 0), (-tolerance, 0), (0, tolerance), (0, -tolerance)]:
                        test_pt = (point[0] + dx, point[1] + dy)
                        if pyclipper.PointInPolygon(test_pt, poly) == 1:
                            return idx
        
        # Fallback: linear search
        for i, tri in enumerate(self.tr_map['triangles']):
            poly = [self.tr_map['vertices'][v] for v in tri]
            if pyclipper.PointInPolygon(point, poly) == 1:
                return i
        
        return -1

    def find_nearest_triangle(self, point_co):
        """Encontra triângulo mais próximo (fallback)"""
        point = Vector((point_co[0], point_co[1], 0.0))
        tolerance = self.click_tolerance * 2.0
        
        if hasattr(self, 'triangle_kdtree') and self.triangle_kdtree:
            nearest = self.triangle_kdtree.find_n(point, 20)
            
            for co, idx, dist in nearest:
                if dist < tolerance:
                    return idx
        
        # Fallback: linear search with distance
        best_idx = -1
        best_dist = float('inf')
        point_2d = Vector((point_co[0], point_co[1]))
        
        for i, center in enumerate(self.triangle_centers):
            dist = (center - point_2d).length
            if dist < best_dist and dist < tolerance:
                best_dist = dist
                best_idx = i
        
        return best_idx

    def simplify_contour(self, contour, target_points=100):
        """Simplifica contorno para melhor performance"""
        if len(contour) <= target_points:
            return contour
        
        # Uniform sampling
        step = len(contour) / target_points
        simplified = []
        for i in range(target_points):
            idx = int(i * step)
            if idx < len(contour):
                simplified.append(contour[idx])
        
        return simplified

    def fill_at_click(self, context):
        """Executa o preenchimento no clique"""
        
        click_3d = self.get_click_3d(context)
        if click_3d is None:
            self.report({"WARNING"}, "Could not determine click position")
            return {'CANCELLED'}
        
        # Transform click to 2D space
        click_2d = self.t_mat @ click_3d
        click_2d_scaled = (
            click_2d[0] * self.scale_factor,
            click_2d[1] * self.scale_factor
        )
        
        # Store click depth for fallback
        click_depth = click_2d[2]
        
        # Find triangle at click
        triangle_idx = self.find_triangle_exact(click_2d_scaled)
        
        if triangle_idx < 0:
            triangle_idx = self.find_nearest_triangle(click_2d_scaled)
        
        if triangle_idx < 0:
            self.report({"WARNING"}, "No triangle found at click position")
            return {'CANCELLED'}
        
        # Propagate labels
        self.solver.labels = -np.ones(len(self.tr_map['triangles']), dtype=np.int32)
        self.solver.labels[triangle_idx] = 1
        self.solver.propagate_labels()
        
        labeled_count = np.sum(self.solver.labels == 1)
        
        if labeled_count < 2:
            self.report({"WARNING"}, "Region too small")
            return {'CANCELLED'}
        
        # Extract contour
        target_contour = self.extract_boundary_contour(self.solver.labels)
        
        if not target_contour or len(target_contour) < 3:
            # Fallback to SmartFillSolver method
            contours, component_labels = self.solver.get_contours()
            for i, contour_list in enumerate(contours):
                if i < len(component_labels) and component_labels[i] == 1:
                    if len(contour_list) > 0:
                        target_contour = max(contour_list, key=lambda x: len(x))
                        break
        
        if not target_contour or len(target_contour) < 3:
            self.report({"WARNING"}, "Could not extract contour")
            return {'CANCELLED'}
        
        # Simplify contour
        target_contour = self.simplify_contour(target_contour, 200)
        
        # Get material
        if self.gp_obj.active_material:
            material_index = self.gp_obj.material_slots.find(self.gp_obj.active_material.name)
            if material_index < 0:
                material_index = 0
        else:
            material_index = 0
        
        # Create fill stroke
        new_stroke = self.fill_frame.nijigp_strokes.new()
        new_stroke.use_cyclic = True
        new_stroke.material_index = material_index
        new_stroke.select = True
        
        num_points = len(target_contour)
        new_stroke.points.add(num_points)
        
        # Restore 3D coordinates - CORRIGIDO
        for i, co_2d in enumerate(target_contour):
            try:
                # Try to get depth from lookup
                depth = self.depth_lookup.get_depth(co_2d)
                co_3d = restore_3d_co(co_2d, depth, self.inv_mat, self.scale_factor)
                new_stroke.points[i].co = co_3d
                new_stroke.points[i].strength = 1.0
            except:
                # Fallback: use click depth
                co_3d = restore_3d_co(co_2d, click_depth, self.inv_mat, self.scale_factor)
                new_stroke.points[i].co = co_3d
                new_stroke.points[i].strength = 1.0
        
        # Clear selection and restore
        op_deselect()
        new_stroke.select = True
        refresh_strokes(self.gp_obj, [self.fill_frame.frame_number])
        load_stroke_selection(self.gp_obj, self.select_map)
        
        self.report({"INFO"}, f"Fill created with {num_points} points")
        return {'FINISHED'}

    # ====================== FUNÇÕES AUXILIARES ======================

    def align_poly_and_depth_lists(self):
        """Alinha listas de polígonos e profundidades"""
        aligned_polys = []
        aligned_depths = []
        for i, poly in enumerate(self.poly_list):
            if i < len(self.depth_list):
                min_len = min(len(poly), len(self.depth_list[i]))
                aligned_polys.append(poly[:min_len])
                aligned_depths.append(self.depth_list[i][:min_len])
            else:
                aligned_polys.append(poly)
                aligned_depths.append([0.0] * len(poly))
        self.poly_list = aligned_polys
        self.depth_list = aligned_depths

    def get_or_create_fill_layer(self, gp_obj):
        """Obtém ou cria camada de preenchimento"""
        layers = gp_obj.data.layers
        for layer in layers:
            name = layer.info if hasattr(layer, 'info') else layer.name
            if name == self.fill_layer_name:
                return layer
        
        if is_gpv3():
            return layers.new(name=self.fill_layer_name, set_active=False)
        else:
            return layers.new(name=self.fill_layer_name)

    def get_or_create_frame(self, layer, frame_number):
        """Obtém ou cria frame no número específico"""
        for frame in layer.frames:
            if frame.frame_number == frame_number:
                return frame
        return layer.frames.new(frame_number)

    def simplify_strokes(self):
        """Simplifica strokes para performance"""
        simplified_count = 0
        for stroke in self.all_strokes:
            if len(stroke.points) <= self.max_points:
                continue
            
            target_points = min(self.max_points, len(stroke.points))
            step = len(stroke.points) / target_points
            
            # Create simplified stroke
            new_stroke = self.current_frame.nijigp_strokes.new()
            new_stroke.use_cyclic = stroke.use_cyclic
            new_stroke.material_index = stroke.material_index
            new_stroke.select = stroke.select
            
            if hasattr(stroke, 'vertex_color_fill'):
                new_stroke.vertex_color_fill = stroke.vertex_color_fill
            
            new_points = []
            for i in range(target_points):
                idx = int(i * step)
                if idx < len(stroke.points):
                    new_points.append(stroke.points[idx])
            
            new_stroke.points.add(len(new_points))
            for j, point in enumerate(new_points):
                new_stroke.points[j].co = point.co
                new_stroke.points[j].strength = point.strength
                if hasattr(point, 'pressure'):
                    new_stroke.points[j].pressure = point.pressure
            
            self.current_frame.nijigp_strokes.remove(stroke)
            simplified_count += 1
        
        if simplified_count > 0:
            self.report({"INFO"}, f"Simplified {simplified_count} strokes")

    def get_click_3d(self, context):
        """Obtém coordenadas 3D do clique do mouse - CORRIGIDO"""
        region = context.region
        rv3d = context.space_data.region_3d
        
        if not region or not rv3d:
            return None
        
        coord = (self.click_x, self.click_y)
        
        from bpy_extras.view3d_utils import region_2d_to_vector_3d, region_2d_to_origin_3d
        
        ray_origin = region_2d_to_origin_3d(region, rv3d, coord)
        ray_direction = region_2d_to_vector_3d(region, rv3d, coord)
        
        # Find closest point on strokes
        closest_point = None
        min_distance = float('inf')
        
        for stroke in self.all_strokes:
            if len(stroke.points) < 2:
                continue
            
            for i in range(len(stroke.points) - 1):
                p1 = stroke.points[i].co
                p2 = stroke.points[i + 1].co
                
                intersect = intersect_line_line(
                    ray_origin, ray_origin + ray_direction * 10000,
                    p1, p2
                )
                
                if intersect and len(intersect) >= 2:
                    point_on_ray = intersect[0]
                    seg_vec = p2 - p1
                    seg_len = seg_vec.length
                    if seg_len > 0:
                        t = (point_on_ray - p1).dot(seg_vec) / (seg_len * seg_len)
                        if 0 <= t <= 1:
                            dist = (point_on_ray - ray_origin).length
                            if dist < min_distance:
                                min_distance = dist
                                closest_point = point_on_ray
        
        # Fallback: working plane
        if closest_point is None:
            plane_normal = self.t_mat.inverted().to_3x3() @ Vector((0, 0, 1))
            plane_point = self.gp_obj.location
            closest_point = intersect_line_plane(
                ray_origin,
                ray_origin + ray_direction * 10000,
                plane_point,
                plane_normal
            )
        
        return closest_point

    def modal(self, context, event):
        """Gerencia o modo modal para capturar clique"""
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS' and self._waiting_for_click:
            self._waiting_for_click = False
            context.window.cursor_modal_restore()
            
            self.click_x = event.mouse_region_x
            self.click_y = event.mouse_region_y
            
            result = self.fill_at_click(context)
            
            if result == {'CANCELLED'}:
                self.report({"WARNING"}, "Could not find area to fill")
            else:
                self.report({"INFO"}, "Fill created")
            
            return {'FINISHED'}
        
        elif event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS':
            self._waiting_for_click = False
            context.window.cursor_modal_restore()
            self.report({"INFO"}, "Cancelled")
            return {'CANCELLED'}
        
        return {'RUNNING_MODAL'}


def register():
    pass

def unregister():
    pass
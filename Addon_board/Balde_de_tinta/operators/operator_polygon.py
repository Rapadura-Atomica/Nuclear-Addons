import bpy
import math
import numpy as np
from .common import *
from ..utils import *
from ..api_router import *

class HoleProcessingOperator(bpy.types.Operator):
    """Reorder strokes and assign holdout materials to holes inside another stroke"""
    bl_idname = "gpencil.nijigp_hole_processing"
    bl_label = "Hole Processing"
    bl_category = 'View'
    bl_options = {'REGISTER', 'UNDO'}

    rearrange: bpy.props.BoolProperty(
            name='Rearrange Strokes',
            default=True,
            description='Move holes to the top, which may be useful for handling some imported SVG shapes'
    )
    separate_colors: bpy.props.BoolProperty(
            name='Separate Colors',
            default=False,
            description='Detect holes separately for each vertex fill color'
    )
    apply_holdout: bpy.props.BoolProperty(default=True)

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.prop(self, "rearrange")
        row = layout.row()
        row.prop(self, "separate_colors")

    def execute(self, context):
        try:
            import pyclipper
        except ImportError:
            self.report({"ERROR"}, "Please install PyClipper in the Preferences panel.")
            return {'FINISHED'}
        
        gp_obj: bpy.types.Object = context.object
        frames_to_process = get_input_frames(gp_obj, get_multiedit(gp_obj))
        material_idx_map = {}
        def change_material(stroke):
            '''
            Duplicate the stroke's material but enable holdout for it. Reuse existing material if possible.
            '''
            src_mat_idx = stroke.material_index
            src_mat = gp_obj.material_slots[src_mat_idx].material
            src_mat_name = gp_obj.material_slots[src_mat_idx].name

            if not src_mat or src_mat.grease_pencil.use_fill_holdout:
                return

            # Case 1: holdout material available in cache
            if src_mat_idx in material_idx_map:
                stroke.material_index = material_idx_map[src_mat_idx]
                return

            # Case 2: holdout material has been added to this object
            dst_mat_name = src_mat_name + '_Holdout'
            for i,material_slot in enumerate(gp_obj.material_slots):
                if dst_mat_name == material_slot.name:
                    stroke.material_index = i
                    material_idx_map[src_mat_idx] = i
                    return

            # Case 3: create a new material
            dst_mat: bpy.types.Material = src_mat.copy()
            dst_mat.name = dst_mat_name
            dst_mat['original_material_index'] = stroke.material_index
            dst_mat.grease_pencil.fill_style = 'SOLID'
            dst_mat.grease_pencil.fill_color = (0,0,0,1)
            dst_mat.grease_pencil.use_fill_holdout = True
            gp_obj.data.materials.append(dst_mat)
            dst_mat_idx = len(gp_obj.data.materials)-1
            material_idx_map[src_mat_idx] = dst_mat_idx
            stroke.material_index = dst_mat_idx

        def process_one_frame(frame):
            select_map = save_stroke_selection(gp_obj)
            to_process = get_input_strokes(gp_obj, frame)
            t_mat, inv_mat = get_transformation_mat(mode=context.scene.nijigp_working_plane,
                                                    gp_obj=gp_obj, strokes=to_process, operator=self,
                                                    requires_layer=False)
            # Initialize the relationship matrix
            poly_list, _, _ = get_2d_co_from_strokes(to_process, t_mat, scale=True)
            relation_mat = np.zeros((len(to_process),len(to_process)))
            for i in range(len(to_process)):
                for j in range(len(to_process)):
                    if i!=j and is_poly_in_poly(poly_list[i], poly_list[j]) and not is_stroke_line(to_process[j], gp_obj):
                        relation_mat[i][j] = 1

            # Record each vertex color
            is_hole_map = {0: False}
            if self.separate_colors:
                for stroke in to_process:
                    is_hole_map[rgb_to_hex_code(stroke.vertex_color_fill)] = False

            # Iteratively process and exclude outmost strokes
            processed = set()
            while len(processed) < len(to_process):
                op_deselect()
                idx_list = []
                color_modified = set()
                for i in range(len(to_process)):
                    if np.sum(relation_mat[i]) == 0 and i not in processed:
                        idx_list.append(i)
                for i in idx_list:
                    processed.add(i)
                    relation_mat[:,i] = 0
                    to_process[i].select = True
                    key = rgb_to_hex_code(to_process[i].vertex_color_fill) if self.separate_colors else 0
                    if self.apply_holdout and is_hole_map[key] and not is_stroke_line(to_process[i], gp_obj):
                        if hasattr(to_process[i], 'fill_opacity'):
                            to_process[i].fill_opacity = 1.0
                        change_material(to_process[i])
                    color_modified.add(key)
                if self.rearrange:
                    op_arrange_stroke(direction='TOP')

                for color in color_modified:
                    is_hole_map[color] = not is_hole_map[color]
                if len(idx_list)==0:
                    break

            load_stroke_selection(gp_obj, select_map)

        for frame in frames_to_process:
            process_one_frame(frame)

        return {'FINISHED'}

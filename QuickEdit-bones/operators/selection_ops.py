# SPDX-License-Identifier: GPL-3.0-or-later
"""
Operadores de seleção para bones em modo Pose
Box Select e Lasso Select - Compatível com Blender 5.0+
"""

import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from bpy_extras.view3d_utils import location_3d_to_region_2d

from ..core.bone_manager import BoneManager
from ..core import constants


class POSE_OT_box_select_bones(bpy.types.Operator):
    """Box Select para bones em modo Pose"""
    bl_idname = "pose.box_select_bones"
    bl_label = "Box Select Bones"
    bl_description = "Seleciona bones dentro de uma caixa"
    bl_options = {'REGISTER', 'UNDO'}

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            self.end_x = event.mouse_region_x
            self.end_y = event.mouse_region_y
            context.area.tag_redraw()

        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            self.execute_selection(context, event)
            
            # Verificar se há seleção e ativar BBox
            selected_bones, _, _, _ = BoneManager.get_selected_bones(context)
            if selected_bones:
                bpy.ops.pose.bbox_transform_bones('INVOKE_DEFAULT')
            else:
                BoneManager.activate_tool("pose.wst_select_tool")
            
            return self.finish(context)

        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            return self.finish(context)

        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        if not self.poll(context):
            self.report({'WARNING'}, "Selecione uma armature no modo Pose")
            return {'CANCELLED'}

        self.start_x = event.mouse_region_x
        self.start_y = event.mouse_region_y
        self.end_x = self.start_x
        self.end_y = self.start_y
        self.drawing = True

        self._handle = bpy.types.SpaceView3D.draw_handler_add(
            self.draw_callback, (context,), 'WINDOW', 'POST_PIXEL'
        )
        
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj and obj.type == 'ARMATURE' and obj.mode == 'POSE'

    def execute_selection(self, context, event):
        """Executa a seleção real dos bones com box"""
        obj = BoneManager.get_active_armature(context)
        if not obj:
            return False

        select_mode = 'SET'
        if event.shift:
            select_mode = 'ADD'
        elif event.ctrl:
            select_mode = 'SUB'

        region = context.region
        rv3d = BoneManager.get_region_3d(context)

        if not rv3d:
            return False

        armature_matrix = obj.matrix_world
        selected_count = 0

        # Calcular limites da caixa
        min_x = min(self.start_x, self.end_x)
        max_x = max(self.start_x, self.end_x)
        min_y = min(self.start_y, self.end_y)
        max_y = max(self.start_y, self.end_y)

        bones_to_select = []
        bones_to_deselect = []

        for pose_bone in obj.pose.bones:
            # Verificar head e tail do bone
            head_world = armature_matrix @ pose_bone.head
            tail_world = armature_matrix @ pose_bone.tail
            
            head_screen = location_3d_to_region_2d(region, rv3d, head_world)
            tail_screen = location_3d_to_region_2d(region, rv3d, tail_world)
            
            bone_inside = False
            
            if head_screen:
                if min_x <= head_screen.x <= max_x and min_y <= head_screen.y <= max_y:
                    bone_inside = True
            
            if not bone_inside and tail_screen:
                if min_x <= tail_screen.x <= max_x and min_y <= tail_screen.y <= max_y:
                    bone_inside = True
            
            if select_mode == 'SET':
                if bone_inside:
                    bones_to_select.append(pose_bone)
                else:
                    bones_to_deselect.append(pose_bone)
            elif select_mode == 'ADD':
                if bone_inside:
                    bones_to_select.append(pose_bone)
            elif select_mode == 'SUB':
                if bone_inside:
                    bones_to_deselect.append(pose_bone)

        # CORREÇÃO: usar pose_bone.select diretamente (Blender 5.0+)
        for pose_bone in bones_to_select:
            pose_bone.select = True
            selected_count += 1
        
        for pose_bone in bones_to_deselect:
            pose_bone.select = False

        context.area.tag_redraw()
        
        if selected_count > 0:
            self.report({'INFO'}, f"{selected_count} bones selecionados")
        
        return selected_count > 0

    def finish(self, context):
        """Finaliza a operação e limpa recursos"""
        if hasattr(self, '_handle') and self._handle:
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
        
        self.drawing = False
        context.area.tag_redraw()
        return {'FINISHED'}

    def draw_callback(self, context):
        """Desenha o retângulo de seleção na tela"""
        if not hasattr(self, 'drawing') or not self.drawing:
            return

        color = (1.0, 1.0, 0.5, 0.3)
        border_color = (1.0, 0.8, 0.0, 1.0)

        x1, y1 = self.start_x, self.start_y
        x2, y2 = self.end_x, self.end_y
        
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        batch = batch_for_shader(shader, 'TRI_STRIP', {
            "pos": [(x1, y1), (x2, y1), (x1, y2), (x2, y2)]
        })
        
        gpu.state.blend_set('ALPHA')
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)
        
        coords = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        indices = ((0, 1), (1, 2), (2, 3), (3, 0))
        border_batch = batch_for_shader(shader, 'LINES', {"pos": coords}, indices=indices)
        shader.uniform_float("color", border_color)
        border_batch.draw(shader)
        
        gpu.state.blend_set('NONE')


class POSE_OT_lasso_select_bones(bpy.types.Operator):
    """Lasso Select para bones em modo Pose"""
    bl_idname = "pose.lasso_select_bones"
    bl_label = "Lasso Select Bones"
    bl_description = "Seleciona bones dentro de um lasso"
    bl_options = {'REGISTER', 'UNDO'}

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            current_pos = (event.mouse_region_x, event.mouse_region_y)
            if len(self.points) == 0 or (Vector(current_pos) - Vector(self.points[-1])).length > 2.0:
                self.points.append(current_pos)
            context.area.tag_redraw()

        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            if len(self.points) > 2:
                self.execute_selection(context, event)
                
                selected_bones, _, _, _ = BoneManager.get_selected_bones(context)
                if selected_bones:
                    bpy.ops.pose.bbox_transform_bones('INVOKE_DEFAULT')
                else:
                    BoneManager.activate_tool("pose.wst_select_tool")
            
            return self.finish(context)

        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            return self.finish(context)

        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        if not self.poll(context):
            self.report({'WARNING'}, "Selecione uma armature no modo Pose")
            return {'CANCELLED'}

        self.points = [(event.mouse_region_x, event.mouse_region_y)]
        self.drawing = True

        self._handle = bpy.types.SpaceView3D.draw_handler_add(
            self.draw_callback, (context,), 'WINDOW', 'POST_PIXEL'
        )
        
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj and obj.type == 'ARMATURE' and obj.mode == 'POSE'

    def execute_selection(self, context, event):
        """Executa a seleção real dos bones com lasso"""
        obj = BoneManager.get_active_armature(context)
        if not obj:
            return False

        select_mode = 'SET'
        if event.shift:
            select_mode = 'ADD'
        elif event.ctrl:
            select_mode = 'SUB'

        region = context.region
        rv3d = BoneManager.get_region_3d(context)

        if not rv3d or len(self.points) < 3:
            return False

        armature_matrix = obj.matrix_world
        selected_count = 0

        bones_to_select = []
        bones_to_deselect = []

        for pose_bone in obj.pose.bones:
            head_world = armature_matrix @ pose_bone.head
            tail_world = armature_matrix @ pose_bone.tail
            
            head_screen = location_3d_to_region_2d(region, rv3d, head_world)
            tail_screen = location_3d_to_region_2d(region, rv3d, tail_world)
            
            bone_inside = False
            
            if head_screen and self.is_point_in_lasso(head_screen):
                bone_inside = True
            
            if not bone_inside and tail_screen and self.is_point_in_lasso(tail_screen):
                bone_inside = True
            
            if select_mode == 'SET':
                if bone_inside:
                    bones_to_select.append(pose_bone)
                else:
                    bones_to_deselect.append(pose_bone)
            elif select_mode == 'ADD':
                if bone_inside:
                    bones_to_select.append(pose_bone)
            elif select_mode == 'SUB':
                if bone_inside:
                    bones_to_deselect.append(pose_bone)

        # CORREÇÃO: usar pose_bone.select diretamente (Blender 5.0+)
        for pose_bone in bones_to_select:
            pose_bone.select = True
            selected_count += 1
        
        for pose_bone in bones_to_deselect:
            pose_bone.select = False

        context.area.tag_redraw()
        
        if selected_count > 0:
            self.report({'INFO'}, f"{selected_count} bones selecionados")
        
        return selected_count > 0

    def is_point_in_lasso(self, point):
        """Verifica se um ponto está dentro do polígono do lasso"""
        if len(self.points) < 3:
            return False
            
        x, y = point.x, point.y
        inside = False
        
        points_closed = self.points + [self.points[0]]
        
        j = len(points_closed) - 1
        for i in range(len(points_closed)):
            xi, yi = points_closed[i]
            xj, yj = points_closed[j]
            
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
            
        return inside

    def finish(self, context):
        """Finaliza a operação e limpa recursos"""
        if hasattr(self, '_handle') and self._handle:
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
        
        self.drawing = False
        context.area.tag_redraw()
        return {'FINISHED'}

    def draw_callback(self, context):
        """Desenha o lasso na tela"""
        if not hasattr(self, 'drawing') or not self.drawing or len(self.points) < 2:
            return

        lasso_path = [Vector(p) for p in self.points]
        
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        gpu.state.blend_set('ALPHA')
        gpu.state.line_width_set(2.0)

        batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": lasso_path})
        shader.bind()
        shader.uniform_float("color", (1.0, 0.8, 0.2, 1.0))
        batch.draw(shader)

        gpu.state.blend_set('NONE')
        gpu.state.line_width_set(1.0)
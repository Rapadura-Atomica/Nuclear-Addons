# SPDX-License-Identifier: GPL-3.0-or-later
"""
Gerenciador de seleção de bones em modo Pose - Compatível com Blender 5.0+
"""

import bpy
from mathutils import Vector, Matrix
from bpy_extras.view3d_utils import location_3d_to_region_2d

from ..core import constants


class BoneManager:
    """Gerencia seleção e transformação de bones em modo Pose"""
    
    _active_tool = None
    _tools_registered = False
    _selection_mode = 'BONE'
    
    @classmethod
    def register_tools(cls):
        """Registra as ferramentas na interface do Blender"""
        if cls._tools_registered:
            return
            
        from ..tools.selection_tools import POSE_WST_SelectTool, POSE_WST_LassoTool
        
        bpy.utils.register_tool(POSE_WST_SelectTool, separator=True, group=True)
        bpy.utils.register_tool(POSE_WST_LassoTool, separator=False, group=True)
        
        cls._tools_registered = True
    
    @classmethod
    def unregister_tools(cls):
        """Remove o registro das ferramentas"""
        from ..tools.selection_tools import POSE_WST_SelectTool, POSE_WST_LassoTool
        
        if cls._tools_registered:
            bpy.utils.unregister_tool(POSE_WST_SelectTool)
            bpy.utils.unregister_tool(POSE_WST_LassoTool)
            cls._tools_registered = False
    
    @classmethod
    def activate_tool(cls, tool_id):
        """Ativa uma ferramenta específica"""
        try:
            bpy.ops.wm.tool_set_by_id(name=tool_id)
            cls._active_tool = tool_id
            return True
        except:
            return False
    
    @staticmethod
    def get_active_armature(context):
        """Retorna a armature ativa em modo Pose"""
        obj = context.object
        if obj and obj.type == 'ARMATURE' and obj.mode == 'POSE':
            return obj
        return None
    
    @staticmethod
    def get_selected_bones(context):
        """
        Obtém todos os bones selecionados na armature ativa
        Retorna: (lista de bones, lista de pontos 3D, lista de pontos 2D, lista de nomes)
        """
        obj = BoneManager.get_active_armature(context)
        if not obj:
            return [], [], [], []
        
        region = context.region
        rv3d = BoneManager.get_region_3d(context)
        
        if not rv3d:
            return [], [], [], []
        
        selected_bones = []
        world_points = []
        screen_points = []
        bone_names = []
        
        armature_matrix = obj.matrix_world
        
        for pose_bone in obj.pose.bones:
            # CORREÇÃO: usar pose_bone.select diretamente (Blender 5.0+)
            if not pose_bone.select:
                continue
            
            selected_bones.append(pose_bone)
            bone_names.append(pose_bone.name)
            
            head_world = armature_matrix @ pose_bone.head
            tail_world = armature_matrix @ pose_bone.tail
            
            head_screen = location_3d_to_region_2d(region, rv3d, head_world)
            tail_screen = location_3d_to_region_2d(region, rv3d, tail_world)
            
            world_points.append(head_world)
            world_points.append(tail_world)
            
            if head_screen:
                screen_points.append(head_screen)
            if tail_screen:
                screen_points.append(tail_screen)
        
        return selected_bones, world_points, screen_points, bone_names
    
    @staticmethod
    def get_region_3d(context):
        """Obtém a região 3D de forma segura"""
        if hasattr(context, 'region_data') and context.region_data:
            return context.region_data
        
        if hasattr(context, 'space_data') and hasattr(context.space_data, 'region_3d'):
            return context.space_data.region_3d
        
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        return area.spaces.active.region_3d
        
        return None
    
    @classmethod
    def get_selection_count(cls, context):
        """Retorna o número de bones selecionados"""
        obj = cls.get_active_armature(context)
        if not obj:
            return 0
        
        count = 0
        for pose_bone in obj.pose.bones:
            # CORREÇÃO: usar pose_bone.select diretamente (Blender 5.0+)
            if pose_bone.select:
                count += 1
        
        return count
    
    @classmethod
    def set_selection_mode(cls, mode='BONE'):
        """Define o modo de seleção"""
        cls._selection_mode = mode
    
    @classmethod
    def update_selection_visuals(cls, context):
        """Atualiza a visualização da seleção"""
        if context.area:
            context.area.tag_redraw()
        return True
    
    @classmethod
    def check_selection_and_activate_bbox(cls, context):
        """Verifica se há seleção e ativa a BBoxTool automaticamente"""
        selected_bones, _, _, _ = cls.get_selected_bones(context)
        if selected_bones:
            return cls.activate_tool("pose.wst_bbox_tool")
        return False
    
    @classmethod
    def check_and_update_bbox(cls, context):
        """Verifica a seleção e atualiza/ativa BBox automaticamente"""
        from ..core.utilities import calculate_screen_bbox
        
        selected_bones, world_points, screen_points, bone_names = cls.get_selected_bones(context)
        
        if not world_points:
            if constants._bbox_data:
                constants._bbox_data = None
                if context.area:
                    context.area.tag_redraw()
            return False
        
        new_bbox = calculate_screen_bbox(context, screen_points)
        
        if constants._bbox_data:
            constants._bbox_data = new_bbox
            constants._original_points.clear()
            constants._original_bones.clear()
            
            for i, bone in enumerate(selected_bones):
                constants._original_bones[bone.name] = {
                    'bone': bone,
                    'head': bone.head.copy(),
                    'tail': bone.tail.copy(),
                    'matrix': bone.matrix.copy()
                }
            
            for i, world_point in enumerate(world_points):
                constants._original_points[i] = world_point.copy()
        else:
            constants._bbox_data = new_bbox
            constants._original_bones = {}
            for bone in selected_bones:
                constants._original_bones[bone.name] = {
                    'bone': bone,
                    'head': bone.head.copy(),
                    'tail': bone.tail.copy(),
                    'matrix': bone.matrix.copy()
                }
        
        if context.area:
            context.area.tag_redraw()
        return True


def register():
    BoneManager.register_tools()


def unregister():
    BoneManager.unregister_tools()
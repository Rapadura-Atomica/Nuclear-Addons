# tool_manager.py - VERSÃO CORRIGIDA
import bpy
from mathutils import Vector
from bpy_extras.view3d_utils import location_3d_to_region_2d

from . import constants
from ..compatibility.api_router import layer_hidden, get_layer_frame_by_number

class GPToolManager:
    _active_tool = None
    _tools_registered = False
    _selection_mode = 'POINT'
    
    @classmethod
    def register_tools(cls):
        if cls._tools_registered:
            return
            
        # IMPORTAR AQUI, não no topo do arquivo
        from ..tools.selection_tools import GPENCIL_WST_SelectTool, GPENCIL_WST_LassoTool
        
        bpy.utils.register_tool(GPENCIL_WST_SelectTool, separator=True, group=True)
        bpy.utils.register_tool(GPENCIL_WST_LassoTool, separator=False, group=True)
        
        cls._tools_registered = True
    
    @classmethod
    def unregister_tools(cls):
        from ..tools.selection_tools import GPENCIL_WST_SelectTool, GPENCIL_WST_LassoTool

        if cls._tools_registered:
            bpy.utils.unregister_tool(GPENCIL_WST_SelectTool)
            bpy.utils.unregister_tool(GPENCIL_WST_LassoTool)
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
    
    @classmethod
    def check_selection_and_activate_bbox(cls, context):
        """Verifica se há seleção e ativa a BBoxTool automaticamente"""
        # Importar aqui para evitar circular
        from ..compatibility.api_router import obj_is_gp
        
        if not context.object or not obj_is_gp(context.object):
            return False
        
        world_points, _, _ = GPToolManager.get_selected_points(context)
        if world_points:
            return cls.activate_tool("gpencil.wst_bbox_tool")
        return False
    
    @staticmethod
    def get_selected_points(context):
        """Obtém todos os pontos selecionados do Grease Pencil"""
        # Importar aqui para evitar circular
        from ..compatibility.api_router import obj_is_gp, is_frame_valid
        
        obj = context.object
        if not obj or not obj_is_gp(obj):
            return [], [], []
        
        world_points = []
        screen_points = []
        point_indices = []
        
        region = context.region
        rv3d = GPToolManager.get_region_3d(context)
        
        if not rv3d:
            return [], [], []
        
        for layer in obj.data.layers:
            if layer_hidden(layer):
                continue
                
            frame = get_layer_frame_by_number(layer, context.scene.frame_current)
            
            if not frame or not hasattr(frame, 'drawing') or not frame.drawing:
                continue
            
            for stroke_idx, stroke in enumerate(frame.drawing.strokes):
                for point_idx, point in enumerate(stroke.points):
                    if point.select:
                        world_pos = obj.matrix_world @ point.position
                        screen_pos = location_3d_to_region_2d(region, rv3d, world_pos)
                        
                        world_points.append(world_pos)
                        if screen_pos:
                            screen_points.append(screen_pos)
                        point_indices.append((layer.name, stroke_idx, point_idx))
        
        return world_points, screen_points, point_indices

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
        """Retorna o número de strokes selecionados"""
        # Importar aqui para evitar circular
        from ..compatibility.api_router import obj_is_gp
        
        obj = context.object
        if not obj or not obj_is_gp(obj):
            return 0
        
        count = 0
        for layer in obj.data.layers:
            if layer_hidden(layer):
                continue
                
            target_frame = get_layer_frame_by_number(layer, context.scene.frame_current)
            if not target_frame or not hasattr(target_frame, 'drawing') or not target_frame.drawing:
                continue
            
            for stroke in target_frame.drawing.strokes:
                if stroke.select:
                    count += 1
        
        return count

    @classmethod
    def set_selection_mode(cls, mode='STROKE'):
        """Define o modo de seleção"""
        try:
            if bpy.app.version >= (4, 3, 0):
                bpy.ops.grease_pencil.set_selection_mode(mode=mode)
            else:
                bpy.ops.gpencil.selectmode(type=mode)
            return True
        except:
            return False
    
    @classmethod
    def highlight_selected_strokes(cls, context):
        """Atualiza a visualização dos strokes selecionados"""
        if context.area:
            context.area.tag_redraw()
        return True
    
    @classmethod
    def update_selection_visuals(cls, context):
        try:
            from ..ui.visual_feedback import StrokeHighlighter
            if not StrokeHighlighter._enabled:
                StrokeHighlighter.enable()
                print("Forçando ativação do StrokeHighlighter")
            else:
                print("StrokeHighlighter já estava ativado")
        except Exception as e:
            print(f"Erro ao ativar highlight: {e}")

        cls.check_and_update_bbox(context)

        # Forçar redraw em todas as áreas VIEW_3D
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
                for region in area.regions:
                    if region.type == 'WINDOW':
                        region.tag_redraw()

    @classmethod
    def check_and_update_bbox(cls, context):
        """Verifica a seleção e atualiza/ativa BBox automaticamente"""
        from ..core import constants
        from ..core.utilities import calculate_screen_bbox
        
        world_points, screen_points, point_indices = cls.get_selected_points(context)
        
        if not world_points:
            # Remover BBox se não há seleção
            if constants._bbox_data:
                constants._bbox_data = None
                if context.area:
                    context.area.tag_redraw()
            return False
        
        # Calcular nova BBox
        new_bbox = calculate_screen_bbox(context, screen_points)
        
        if constants._bbox_data:
            # Atualizar BBox existente
            constants._bbox_data = new_bbox
            
            # Atualizar pontos originais
            constants._original_points.clear()
            constants._original_screen_points.clear()
            
            for idx, world_point in zip(point_indices, world_points):
                constants._original_points[idx] = world_point.copy()
            
            for idx, screen_point in zip(point_indices, screen_points):
                constants._original_screen_points[idx] = screen_point.copy()
        else:
            # Criar nova BBox (sem ativar operador ainda)
            constants._bbox_data = new_bbox
        
        if context.area:
            context.area.tag_redraw()
        return True

def register():
    GPToolManager.register_tools()

def unregister():
    GPToolManager.unregister_tools()
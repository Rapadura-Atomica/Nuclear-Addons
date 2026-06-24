import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from bpy_extras.view3d_utils import location_3d_to_region_2d, region_2d_to_location_3d

from . import constants
from ..compatibility.api_router import layer_hidden, get_layer_frame_by_number, is_frame_valid

def get_gpencil_frame_for_layer(layer, frame_number):
    """Obtém o frame apropriado para uma layer específica (compatível)"""
    return get_layer_frame_by_number(layer, frame_number)

def calculate_screen_bbox(context, screen_points):
    """Calcula a bounding box em coordenadas de tela"""
    if not screen_points:
        return None
    
    xs = [p.x for p in screen_points]
    ys = [p.y for p in screen_points]
    
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    
    margin = constants.HANDLE_SIZE * 2
    
    bbox = (
        max(0, xmin - margin),
        min(context.region.width, xmax + margin),
        max(0, ymin - margin),
        min(context.region.height, ymax + margin)
    )
    
    return bbox

def get_bbox_corners(bbox):
    """Retorna os cantos da bounding box"""
    if not bbox:
        return []
    
    xmin, xmax, ymin, ymax = bbox
    return [
        Vector((xmin, ymin)),
        Vector((xmax, ymin)),
        Vector((xmax, ymax)),
        Vector((xmin, ymax))
    ]

def get_bbox_center(bbox):
    """Retorna o centro da bounding box"""
    if not bbox:
        return None
    
    xmin, xmax, ymin, ymax = bbox
    return Vector(((xmin + xmax) / 2, (ymin + ymax) / 2))

def get_handle_under_mouse(bbox, mouse_pos):
    """Retorna o tipo de handle sob o mouse, incluindo handles de rotação invisíveis"""
    if not bbox:
        return constants.HandleType.NONE
    
    pivot_pos = constants._pivot_pos
    if pivot_pos is None:
        pivot_pos = get_bbox_center(bbox)

    distance = (pivot_pos - mouse_pos).length

    if distance < constants.PIVOT_HOTSPOT:
        return constants.HandleType.PIVOT

    
    corners = get_bbox_corners(bbox)
    center = get_bbox_center(bbox)
    
    xmin, xmax, ymin, ymax = bbox
    if (xmin <= mouse_pos.x <= xmax and ymin <= mouse_pos.y <= ymax):
        return constants.HandleType.CENTER
    
    handles = [
        (constants.HandleType.BOTTOM_LEFT, corners[0]),
        (constants.HandleType.BOTTOM_RIGHT, corners[1]),
        (constants.HandleType.TOP_RIGHT, corners[2]),
        (constants.HandleType.TOP_LEFT, corners[3]),
        (constants.HandleType.TOP, (corners[2] + corners[3]) / 2),
        (constants.HandleType.BOTTOM, (corners[0] + corners[1]) / 2),
        (constants.HandleType.LEFT, (corners[0] + corners[3]) / 2),
        (constants.HandleType.RIGHT, (corners[1] + corners[2]) / 2),
        (constants.HandleType.CENTER, center),
    ]
    
    rotation_handles = [
        (constants.HandleType.ROTATE_TOP_LEFT, corners[3], 35),
        (constants.HandleType.ROTATE_TOP_RIGHT, corners[2], 35),
        (constants.HandleType.ROTATE_BOTTOM_LEFT, corners[0], 35),
        (constants.HandleType.ROTATE_BOTTOM_RIGHT, corners[1], 35),
    ]
    
    shear_offset = 25
    handles += [
        (constants.HandleType.SHEAR_TOP, (corners[2] + corners[3]) / 2 + Vector((0, shear_offset))),
        (constants.HandleType.SHEAR_BOTTOM, (corners[0] + corners[1]) / 2 + Vector((0, -shear_offset))),
        (constants.HandleType.SHEAR_LEFT, (corners[0] + corners[3]) / 2 + Vector((-shear_offset, 0))),
        (constants.HandleType.SHEAR_RIGHT, (corners[1] + corners[2]) / 2 + Vector((shear_offset, 0))),
    ]
    
    for handle_type, pos in handles:
        hotspot_size = constants.HANDLE_HOTSPOT * 1.5 if handle_type in [
            constants.HandleType.SHEAR_TOP, constants.HandleType.SHEAR_BOTTOM, 
            constants.HandleType.SHEAR_LEFT, constants.HandleType.SHEAR_RIGHT
        ] else constants.HANDLE_HOTSPOT
        
        if (pos - mouse_pos).length < hotspot_size:
            return handle_type
    
    for handle_type, pos, radius in rotation_handles:
        if (pos - mouse_pos).length < radius:
            return handle_type
        

    return constants.HandleType.NONE

def apply_transformation(context, bbox_start, bbox_end, handle_type, is_proportional=False):
    """Aplica a transformação aos pontos do Grease Pencil com suporte a escala proporcional"""
    from . import constants
    
    obj = context.object
    if not obj or not obj_is_gp(obj):
        return
    
    center_start = get_bbox_center(bbox_start)
    center_end = get_bbox_center(bbox_end)
    
    # Calcular escalas
    scale_x = (bbox_end[1] - bbox_end[0]) / (bbox_start[1] - bbox_start[0])
    scale_y = (bbox_end[3] - bbox_end[2]) / (bbox_start[3] - bbox_start[2])
    
    # Aplicar escala proporcional se Shift estiver pressionado
    if is_proportional and handle_type in [
        constants.HandleType.TOP_LEFT, constants.HandleType.TOP_RIGHT, 
        constants.HandleType.BOTTOM_LEFT, constants.HandleType.BOTTOM_RIGHT,
        constants.HandleType.TOP, constants.HandleType.BOTTOM, 
        constants.HandleType.LEFT, constants.HandleType.RIGHT
    ]:
        uniform_scale = min(scale_x, scale_y) if scale_x > 0 and scale_y > 0 else max(scale_x, scale_y)
        scale_x = uniform_scale
        scale_y = uniform_scale
    
    for (layer_name, stroke_idx, point_idx), original_screen_pos in constants._original_screen_points.items():
        
        target_layer = None
        for layer in obj.data.layers:
            if layer.name == layer_name:
                target_layer = layer
                break
        
        if not target_layer:
            continue
            
        target_frame = get_gpencil_frame_for_layer(target_layer, context.scene.frame_current)
        if not target_frame or not is_frame_valid(target_frame):
            continue
            
        if stroke_idx < len(target_frame.drawing.strokes) and point_idx < len(target_frame.drawing.strokes[stroke_idx].points):
            point = target_frame.drawing.strokes[stroke_idx].points[point_idx]
            
            rel_pos = original_screen_pos - center_start
            
            if handle_type == constants.HandleType.CENTER:
                new_screen_pos = center_end + rel_pos
            elif handle_type in [constants.HandleType.TOP_LEFT, constants.HandleType.TOP_RIGHT, 
                               constants.HandleType.BOTTOM_LEFT, constants.HandleType.BOTTOM_RIGHT]:
                scale = (scale_x + scale_y) / 2
                new_screen_pos = center_end + rel_pos * scale
            elif handle_type in [constants.HandleType.TOP, constants.HandleType.BOTTOM]:
                new_screen_pos = center_end + Vector((rel_pos.x, rel_pos.y * scale_y))
            elif handle_type in [constants.HandleType.LEFT, constants.HandleType.RIGHT]:
                new_screen_pos = center_end + Vector((rel_pos.x * scale_x, rel_pos.y))
            else:
                new_screen_pos = center_end + rel_pos
            
            region = context.region
            rv3d = GPToolManager.get_region_3d(context)
            if not rv3d:
                continue
                
            depth = constants._original_points[(layer_name, stroke_idx, point_idx)].z
            new_world_pos = region_2d_to_location_3d(region, rv3d, new_screen_pos, Vector((0, 0, depth)))
            
            point.position = obj.matrix_world.inverted() @ new_world_pos

# Importação circular resolvida no final
from ..compatibility.api_router import obj_is_gp
from .tool_manager import GPToolManager
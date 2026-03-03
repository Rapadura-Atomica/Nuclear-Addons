import bpy
from mathutils import Vector

def get_active_gpencil_object(context):
    """Retorna o objeto Grease Pencil ativo de forma compatível"""
    obj = context.object
    if obj and ((bpy.app.version >= (4, 3, 0) and obj.type == "GREASEPENCIL") or 
                (bpy.app.version < (4, 3, 0) and obj.type == "GPENCIL")):
        return obj
    return None

def get_gpencil_modifiers(obj):
    """Retorna os modificadores do Grease Pencil de forma compatível"""
    if bpy.app.version >= (4, 3, 0):
        return obj.modifiers
    else:
        return obj.grease_pencil_modifiers

def create_gpencil_brush(name, color=(0, 0, 0)):
    """Cria um pincel Grease Pencil de forma compatível"""
    if bpy.app.version >= (4, 3, 0):
        brush = bpy.data.brushes.new(name, mode='PAINT_GREASE_PENCIL')
        brush.color = color
        return brush
    else:
        # Para versões anteriores, copiar um pincel existente
        source_brush = None
        for brush in bpy.data.brushes:
            if brush.use_paint_grease_pencil:
                source_brush = brush
                break
        
        if source_brush:
            new_brush = source_brush.copy()
            new_brush.name = name
            return new_brush
        return None
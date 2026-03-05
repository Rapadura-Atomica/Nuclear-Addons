"""
Utility modules associated with timeoffset
"""


import bpy
import bpy_extras.anim_utils as anim_utils
import bpy.utils.previews as previews
from .. import api_route as gp_api
import os

def set_pose_id(obj, frame_number: int, pose_id: str):
    """Armazena pose_id por frame_number no objeto GP"""
    if "timeoffset_pose_ids" not in obj:
        obj["timeoffset_pose_ids"] = {}
    obj["timeoffset_pose_ids"][str(frame_number)] = pose_id
  
def get_pose_id(obj, frame_number: int) -> str | None:
    pose_map = obj.get("timeoffset_pose_ids", {})
    pose_id = pose_map.get(str(frame_number), None)
    return pose_id

def get_time_offset_modifier(obj):
    """Encontra o modificador TimeOffset no objeto"""
    if not obj or not gp_api.obj_is_gp(obj):
        return None
    modifiers = gp_api.get_gp_modifiers(obj)
    time_modifier_type = gp_api.get_modifier_str('TIME')
    for mod in modifiers:
        if mod.type == time_modifier_type:
            return mod
    return None

def is_offset_animated(obj, time_mod):
    """Verifica se a propriedade offset está animada"""
    anim_data = obj.animation_data
    if not anim_data or not anim_data.action or not anim_data.action_slot:
        return False
    channelbag = anim_utils.action_ensure_channelbag_for_slot(anim_data.action, anim_data.action_slot)
    if not channelbag:
        return False
    for fcurve in channelbag.fcurves:
        if (fcurve.data_path.endswith('offset') and
            fcurve.data_path.startswith(f'grease_pencil_modifiers["{time_mod.name}"]')):
            return True
    return False

def has_negative_frames(obj):
    """Verifica se existem frames negativos (biblioteca)"""
    for layer in obj.data.layers:
        for frame in layer.frames:
            if frame.frame_number < 0:
                return True
    return False

def get_library_frame_range(obj):
    """Retorna o frame mais negativo e o menos negativo da biblioteca"""
    min_frame = 0
    max_frame = 0
    for layer in obj.data.layers:
        for frame in layer.frames:
            if frame.frame_number < 0:
                if frame.frame_number < min_frame:
                    min_frame = frame.frame_number
                if frame.frame_number > max_frame or max_frame == 0:
                    max_frame = frame.frame_number
    return min_frame, max_frame

def get_max_positive_frame_number(obj):
    """Encontra o frame máximo positivo (timeline normal)"""
    max_frame = 0
    for layer in obj.data.layers:
        if layer.frames:
            for frame in layer.frames:
                if frame.frame_number > max_frame:
                    max_frame = frame.frame_number
    return max(0, max_frame)


_preview_collections = {}


def get_preview_collection():
    pcoll = _preview_collections.get("timeoffset")
    if pcoll is None:
        pcoll = previews.new()
        _preview_collections["timeoffset"] = pcoll
    return pcoll


def invalidate_library_previews():
    pcoll = _preview_collections.get("timeoffset")
    if pcoll:
        previews.remove(pcoll)
        _preview_collections.pop("timeoffset", None)

def clear_preview_collections():
    for pcoll in _preview_collections.values():
        previews.remove(pcoll)
    _preview_collections.clear()

def generate_library_preview(obj, frame):
    """Gera preview do frame da biblioteca (usa pose_id do objeto)"""
    if frame >= 0:
        return
    scene = bpy.context.scene
    view_layer = bpy.context.view_layer
    old_frame = scene.frame_current
    
    # Garantir objeto ativo
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    view_layer.objects.active = obj
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    
    # Preparar diretório
    preview_dir = os.path.join(
        bpy.app.tempdir,
        "timeoffset_previews",
        obj.name
    )
    os.makedirs(preview_dir, exist_ok=True)
    
    pose_id = get_pose_id(obj, frame)
    if not pose_id:
        print(f"❌ Frame {frame} sem pose_id, preview cancelado")
        scene.frame_set(old_frame)
        return
    
    filepath = os.path.join(preview_dir, f"{pose_id}.png")
    
    # Se já existe, não recriar
    if os.path.exists(filepath):
        print(f"ℹ️ Preview já existe: {filepath}")
        scene.frame_set(old_frame)
        return
    
    # Procurar área 3D
    screenshot_taken = False
    for area in bpy.context.window.screen.areas:
        if area.type == 'VIEW_3D':
            # Encontrar a região WINDOW
            region = None
            for r in area.regions:
                if r.type == 'WINDOW':
                    region = r
                    break
            
            if not region:
                continue
            
            # Tirar screenshot
            try:
                # Forçar atualização da viewport
                bpy.context.view_layer.update()
                
                # Override de contexto
                override = {
                    'area': area,
                    'region': region,
                    'screen': bpy.context.screen,
                    'window': bpy.context.window
                }
                
                with bpy.context.temp_override(**override):
                    bpy.ops.screen.screenshot(
                        filepath=filepath,
                        check_existing=False,
                        full=False
                    )
                print(f"✅ Screenshot salvo: {filepath}")
                screenshot_taken = True
                break
            except Exception as e:
                print(f"⚠️ Erro no screenshot (não crítico): {e}")
                # Não interrompe o fluxo principal
                continue
    
    if not screenshot_taken:
        print("⚠️ Não foi possível tirar screenshot - continuando sem preview")
    
    # Voltar ao frame original
    scene.frame_set(old_frame)
    bpy.context.view_layer.update()
    
    # Invalidar previews para forçar recarregamento
    invalidate_library_previews()

def get_library_preview(obj, frame):
    if frame >= 0:
        return None
    pose_id = get_pose_id(obj, frame)  # ← Mudança aqui!
    if not pose_id:
        print(f"❌ Frame {frame} não tem pose_id")
        return None
    preview_dir = os.path.join(
        bpy.app.tempdir,
        "timeoffset_previews",
        obj.name
    )
    preview_path = os.path.join(preview_dir, f"{pose_id}.png")
    if not os.path.exists(preview_path):
        print(f"❌ Preview não encontrado: {preview_path}")
        return None
    pcoll = get_preview_collection()
    key = f"{obj.name}_{pose_id}"
    if key not in pcoll:
        pcoll.load(key, preview_path, 'IMAGE')
    return key
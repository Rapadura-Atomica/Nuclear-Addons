# SPDX-License-Identifier: GPL-3.0-or-later
"""
Onion Skin para rigs com biblioteca de substituição (Time Offset).

"""

import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector
from bpy.props import (
    BoolProperty, IntProperty, FloatProperty,
    FloatVectorProperty, PointerProperty, EnumProperty,
)
from bpy.types import PropertyGroup, Panel, Operator

from . import api_route as gp_api


# ----------------------------------------------------------------------
# Estado global do módulo
# ----------------------------------------------------------------------

# {absolute_frame: (color_rgba, [ [Vector3, Vector3, ...], ... ])}
_ghost_cache: dict[int, tuple[tuple[float, float, float, float], list[list[Vector]]]] = {}
_last_eval_frame = None
_last_eval_settings_hash = None
_eval_in_progress = False
_draw_handler = None
_timer_registered = False
_pending_rebuild = False
_pending_since = 0.0   # timestamp do último request — usado p/ debounce


# ----------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------

class TimeOffsetOnionSettings(PropertyGroup):
    enabled: BoolProperty(
        name="Ativar Onion Skin",
        default=False,
        description="Liga/desliga o overlay de onion skin no viewport",
        update=lambda s, c: _on_settings_change(c),
    )
    frames_before: IntProperty(
        name="Keyframes atrás",
        default=1, min=0, soft_max=5, max=20,
        description="Quantos keyframes anteriores mostrar como ghost",
        update=lambda s, c: _on_settings_change(c),
    )
    frames_after: IntProperty(
        name="Keyframes à frente",
        default=1, min=0, soft_max=5, max=20,
        description="Quantos keyframes posteriores mostrar como ghost (caro)",
        update=lambda s, c: _on_settings_change(c),
    )
    color_before: FloatVectorProperty(
        name="Cor (antes)",
        subtype='COLOR', size=3, default=(0.95, 0.25, 0.25),
        min=0.0, max=1.0,
        update=lambda s, c: _on_settings_change(c),
    )
    color_after: FloatVectorProperty(
        name="Cor (depois)",
        subtype='COLOR', size=3, default=(0.25, 0.55, 1.0),
        min=0.0, max=1.0,
        update=lambda s, c: _on_settings_change(c),
    )
    opacity: FloatProperty(
        name="Opacidade",
        default=0.6, min=0.0, max=1.0,
        update=lambda s, c: _on_settings_change(c),
    )
    use_fade: BoolProperty(
        name="Fade por distância",
        default=True,
        description="Keyframes mais distantes ficam mais transparentes",
        update=lambda s, c: _on_settings_change(c),
    )
    line_width: FloatProperty(
        name="Espessura",
        default=1.5, min=0.5, max=8.0,
        update=lambda s, c: _on_settings_change(c),
    )
    include_hidden: BoolProperty(
        name="Incluir ocultos",
        default=False,
        description="Inclui objetos GP ocultos no viewport",
        update=lambda s, c: _on_settings_change(c),
    )
    live_update: BoolProperty(
        name="Atualizar ao animar",
        default=False,
        description="Recomputa ghosts ao mexer em pose/strokes. Desligado por padrão (caro).",
        update=lambda s, c: _on_settings_change(c),
    )
    debounce_ms: IntProperty(
        name="Debounce (ms)",
        default=120, min=0, max=1000,
        description="Tempo mínimo de espera antes de recomputar após pedido",
    )
    source: EnumProperty(
        name="Fonte de keyframes",
        items=[
            ('ALL', "Todos", "Armature + GPs + GP frame_numbers"),
            ('ARMATURE', "Só armature", "Apenas keyframes da armature (mais rápido)"),
            ('GP_ONLY', "Só GP", "Keyframes dos GPs + frame_numbers positivos"),
        ],
        default='ALL',
        update=lambda s, c: _on_settings_change(c),
    )


def _settings_signature(s: TimeOffsetOnionSettings):
    return (
        bool(s.enabled),
        int(s.frames_before),
        int(s.frames_after),
        tuple(s.color_before),
        tuple(s.color_after),
        float(s.opacity),
        bool(s.use_fade),
        bool(s.include_hidden),
        str(s.source),
    )


def _on_settings_change(context):
    global _last_eval_frame, _last_eval_settings_hash
    _last_eval_frame = None
    _last_eval_settings_hash = None
    _request_rebuild()
    _tag_redraw_3d()


# ----------------------------------------------------------------------
# Coleta de keyframes — multi-API (slots/channelbag no 4.4+ / 5.0)
# ----------------------------------------------------------------------

def _collect_action_keyframes(action, out: set):
    """Adiciona posições de keyframe de uma Action em `out`. Lida com layered (slot+channelbag) e legacy."""
    if action is None:
        return

    # Modelo novo (Blender 4.4+ / 5.0): action.layers[*].strips[*].channelbags
    layers = getattr(action, 'layers', None)
    found_any = False
    if layers is not None:
        try:
            for layer in layers:
                strips = getattr(layer, 'strips', None) or []
                for strip in strips:
                    channelbags = getattr(strip, 'channelbags', None)
                    if channelbags is not None:
                        for cb in channelbags:
                            for fc in cb.fcurves:
                                for kp in fc.keyframe_points:
                                    out.add(int(round(kp.co.x)))
                                    found_any = True
        except Exception:
            pass

    if found_any:
        return

    # Fallback legacy: action.fcurves direto (pré-slots)
    fcurves = getattr(action, 'fcurves', None)
    if fcurves is not None:
        try:
            for fc in fcurves:
                for kp in fc.keyframe_points:
                    out.add(int(round(kp.co.x)))
        except Exception:
            pass


def _collect_relevant_keyframes(scene, gp_objs, source: str) -> list[int]:
    """Retorna lista ordenada de posições de keyframe que devem participar do onion skin."""
    positions: set[int] = set()

    if source in {'ALL', 'ARMATURE'}:
        for obj in scene.objects:
            if obj.type != 'ARMATURE':
                continue
            ad = obj.animation_data
            if ad and ad.action:
                _collect_action_keyframes(ad.action, positions)

    if source in {'ALL', 'GP_ONLY'}:
        for obj in gp_objs:
            ad = obj.animation_data
            if ad and ad.action:
                _collect_action_keyframes(ad.action, positions)
            # GP keyframes "do timeline" são os com frame_number > 0
            # (negativos são biblioteca de poses, não devem contar)
            data = obj.data
            if data is not None:
                for layer in data.layers:
                    for frame in layer.frames:
                        fn = int(frame.frame_number)
                        if fn > 0:
                            positions.add(fn)

    return sorted(positions)


def _select_neighbor_keyframes(current: int, positions: list[int],
                               n_before: int, n_after: int):
    """Retorna (lista_before_ordenada_do_mais_próximo_pro_mais_distante,
                lista_after_ordenada_do_mais_próximo_pro_mais_distante)."""
    before_all = [p for p in positions if p < current]
    after_all = [p for p in positions if p > current]
    before_sel = before_all[-n_before:][::-1] if n_before else []  # mais próximo primeiro
    after_sel = after_all[:n_after] if n_after else []
    return before_sel, after_sel


# ----------------------------------------------------------------------
# Extração de strokes do estado avaliado
# ----------------------------------------------------------------------

def _layer_matrix(layer):
    m = getattr(layer, 'matrix_local', None)
    if m is None:
        m = getattr(layer, 'matrix_layer', None)
    return m if m is not None else Matrix.Identity(4)


def _eval_strokes_world(gp_obj, depsgraph):
    try:
        eval_obj = gp_obj.evaluated_get(depsgraph)
    except Exception:
        return []
    data = eval_obj.data
    if data is None:
        return []
    mw = eval_obj.matrix_world

    out: list[list[Vector]] = []
    for layer in data.layers:
        if gp_api.layer_hidden(layer):
            continue
        try:
            frame = layer.current_frame()
        except Exception:
            frame = None
        if frame is None:
            continue
        drawing = getattr(frame, 'drawing', None)
        if drawing is None:
            continue

        m = mw @ _layer_matrix(layer)
        strokes = drawing.strokes
        if not strokes:
            continue

        for stroke in strokes:
            pts_n = len(stroke.points)
            if pts_n < 2:
                continue
            buf = [0.0] * (pts_n * 3)
            try:
                stroke.points.foreach_get('position', buf)
                pts_world = [
                    m @ Vector((buf[i*3], buf[i*3+1], buf[i*3+2]))
                    for i in range(pts_n)
                ]
            except Exception:
                pts_world = [m @ p.position for p in stroke.points]
            out.append(pts_world)
    return out


# ----------------------------------------------------------------------
# Cores
# ----------------------------------------------------------------------

def _color_for_rank(side: str, rank_from_current: int, total_on_side: int,
                   settings: TimeOffsetOnionSettings):
    """side='before'|'after'; rank_from_current=1..total_on_side (1 = mais próximo)."""
    base = settings.color_before if side == 'before' else settings.color_after
    if settings.use_fade and total_on_side > 0:
        fade = (total_on_side - rank_from_current + 1) / total_on_side
    else:
        fade = 1.0
    alpha = max(0.0, min(1.0, settings.opacity * fade))
    return (float(base[0]), float(base[1]), float(base[2]), alpha)


# ----------------------------------------------------------------------
# Visibilidade GPs
# ----------------------------------------------------------------------

def _visible_gp_objects(scene, include_hidden: bool):
    out = []
    for o in scene.objects:
        if not gp_api.obj_is_gp(o):
            continue
        if not include_hidden and not o.visible_get():
            continue
        out.append(o)
    return out


# ----------------------------------------------------------------------
# Rebuild
# ----------------------------------------------------------------------

def _rebuild_cache():
    global _ghost_cache, _last_eval_frame, _last_eval_settings_hash, _eval_in_progress

    if _eval_in_progress:
        return
    _eval_in_progress = True
    try:
        ctx = bpy.context
        scene = ctx.scene
        if scene is None:
            return
        settings = getattr(scene, "timeoffset_onion", None)
        if settings is None or not settings.enabled:
            if _ghost_cache:
                _ghost_cache = {}
                _tag_redraw_3d()
            return

        sig = _settings_signature(settings)
        cur = scene.frame_current
        if cur == _last_eval_frame and sig == _last_eval_settings_hash and _ghost_cache:
            return

        gp_objs = _visible_gp_objects(scene, settings.include_hidden)
        if not gp_objs:
            _ghost_cache = {}
            _last_eval_frame = cur
            _last_eval_settings_hash = sig
            _tag_redraw_3d()
            return

        # Descobre quais frames avaliar
        positions = _collect_relevant_keyframes(scene, gp_objs, settings.source)
        before_sel, after_sel = _select_neighbor_keyframes(
            cur, positions, settings.frames_before, settings.frames_after
        )

        targets = []  # list of (abs_frame, side, rank, total_on_side)
        n_b = len(before_sel)
        for i, f in enumerate(before_sel):
            targets.append((f, 'before', i + 1, n_b))
        n_a = len(after_sel)
        for i, f in enumerate(after_sel):
            targets.append((f, 'after', i + 1, n_a))

        new_cache: dict[int, tuple[tuple[float, float, float, float], list[list[Vector]]]] = {}
        if not targets:
            _ghost_cache = {}
            _last_eval_frame = cur
            _last_eval_settings_hash = sig
            _tag_redraw_3d()
            return

        saved_frame = cur
        try:
            for abs_frame, side, rank, total_side in targets:
                scene.frame_set(abs_frame)
                depsgraph = ctx.evaluated_depsgraph_get()
                strokes_all: list[list[Vector]] = []
                for obj in gp_objs:
                    strokes_all.extend(_eval_strokes_world(obj, depsgraph))
                if strokes_all:
                    new_cache[abs_frame] = (
                        _color_for_rank(side, rank, total_side, settings),
                        strokes_all,
                    )
        finally:
            scene.frame_set(saved_frame)

        _ghost_cache = new_cache
        _last_eval_frame = cur
        _last_eval_settings_hash = sig
        _tag_redraw_3d()
    finally:
        _eval_in_progress = False


# ----------------------------------------------------------------------
# Desenho viewport
# ----------------------------------------------------------------------

def _get_shader():
    return gpu.shader.from_builtin('UNIFORM_COLOR')


def _draw_callback():
    if not _ghost_cache:
        return
    scene = bpy.context.scene
    settings = getattr(scene, "timeoffset_onion", None)
    if settings is None or not settings.enabled:
        return

    shader = _get_shader()
    gpu.state.blend_set('ALPHA')
    try:
        gpu.state.line_width_set(settings.line_width)
    except Exception:
        pass
    try:
        gpu.state.depth_test_set('NONE')
    except Exception:
        pass

    shader.bind()
    for _frame_key, (color, strokes) in _ghost_cache.items():
        shader.uniform_float("color", color)
        for pts in strokes:
            if len(pts) < 2:
                continue
            batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": [tuple(p) for p in pts]})
            batch.draw(shader)

    gpu.state.blend_set('NONE')
    try:
        gpu.state.line_width_set(1.0)
    except Exception:
        pass


def _tag_redraw_3d():
    wm = bpy.context.window_manager
    if not wm:
        return
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


# ----------------------------------------------------------------------
# Defer/timer (com debounce)
# ----------------------------------------------------------------------

import time as _time


def _request_rebuild():
    global _pending_rebuild, _pending_since
    _pending_rebuild = True
    _pending_since = _time.monotonic()


def _timer_tick():
    global _pending_rebuild
    if _pending_rebuild:
        scene = bpy.context.scene
        settings = getattr(scene, "timeoffset_onion", None) if scene else None
        debounce_s = (settings.debounce_ms / 1000.0) if settings else 0.12
        if _time.monotonic() - _pending_since >= debounce_s:
            _pending_rebuild = False
            try:
                _rebuild_cache()
            except Exception as e:
                print(f"[TimeOffset OnionSkin] rebuild error: {e}")
    return 0.05  # 20 Hz


@bpy.app.handlers.persistent
def _on_frame_change_post(scene, depsgraph):
    settings = getattr(scene, "timeoffset_onion", None)
    if settings is None or not settings.enabled:
        return
    _request_rebuild()


@bpy.app.handlers.persistent
def _on_depsgraph_update_post(scene, depsgraph):
    if _eval_in_progress:
        return
    settings = getattr(scene, "timeoffset_onion", None)
    if settings is None or not settings.enabled or not settings.live_update:
        return
    _request_rebuild()


# ----------------------------------------------------------------------
# Lifecycle dos handlers
# ----------------------------------------------------------------------

def _install_handlers():
    global _draw_handler, _timer_registered

    if _draw_handler is None:
        _draw_handler = bpy.types.SpaceView3D.draw_handler_add(
            _draw_callback, (), 'WINDOW', 'POST_VIEW'
        )

    if _on_frame_change_post not in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.append(_on_frame_change_post)
    if _on_depsgraph_update_post not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph_update_post)

    if not _timer_registered:
        bpy.app.timers.register(_timer_tick, persistent=True)
        _timer_registered = True


def _remove_handlers():
    global _draw_handler, _timer_registered, _ghost_cache, _last_eval_frame, _last_eval_settings_hash

    if _draw_handler is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_draw_handler, 'WINDOW')
        except Exception:
            pass
        _draw_handler = None

    if _on_frame_change_post in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(_on_frame_change_post)
    if _on_depsgraph_update_post in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph_update_post)

    if _timer_registered:
        try:
            bpy.app.timers.unregister(_timer_tick)
        except Exception:
            pass
        _timer_registered = False

    _ghost_cache = {}
    _last_eval_frame = None
    _last_eval_settings_hash = None
    _tag_redraw_3d()


# ----------------------------------------------------------------------
# Operators
# ----------------------------------------------------------------------

class TIMEOFFSET_OT_onion_refresh(Operator):
    bl_idname = "time_offset.onion_refresh"
    bl_label = "Atualizar Onion Skin"
    bl_description = "Força recomputar os ghosts agora"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        global _last_eval_frame, _last_eval_settings_hash
        _last_eval_frame = None
        _last_eval_settings_hash = None
        _rebuild_cache()
        return {'FINISHED'}


# ----------------------------------------------------------------------
# Panel
# ----------------------------------------------------------------------

class TIMEOFFSET_PT_onion_skin(Panel):
    bl_label = "Onion Skin"
    bl_idname = "TIMEOFFSET_PT_onion_skin"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "TimeOffset"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.timeoffset_onion

        row = layout.row()
        row.prop(settings, "enabled", text="Ativar",
                 icon='ONIONSKIN_ON' if settings.enabled else 'ONIONSKIN_OFF')

        col = layout.column(align=True)
        col.enabled = settings.enabled
        col.prop(settings, "frames_before")
        col.prop(settings, "frames_after")
        col.prop(settings, "source")

        col = layout.column(align=True)
        col.enabled = settings.enabled
        col.prop(settings, "color_before")
        col.prop(settings, "color_after")

        col = layout.column(align=True)
        col.enabled = settings.enabled
        col.prop(settings, "opacity", slider=True)
        col.prop(settings, "line_width", slider=True)
        col.prop(settings, "use_fade")
        col.prop(settings, "include_hidden")

        box = layout.box()
        box.label(text="Performance", icon='TIME')
        box.enabled = settings.enabled
        box.prop(settings, "live_update")
        box.prop(settings, "debounce_ms")

        layout.operator("time_offset.onion_refresh", icon='FILE_REFRESH')


# ----------------------------------------------------------------------
# Registro
# ----------------------------------------------------------------------

classes = (
    TimeOffsetOnionSettings,
    TIMEOFFSET_OT_onion_refresh,
    TIMEOFFSET_PT_onion_skin,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.timeoffset_onion = PointerProperty(type=TimeOffsetOnionSettings)
    _install_handlers()
    print("TimeOffset OnionSkin registrado")


def unregister():
    _remove_handlers()
    if hasattr(bpy.types.Scene, "timeoffset_onion"):
        del bpy.types.Scene.timeoffset_onion
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    print("TimeOffset OnionSkin desregistrado")

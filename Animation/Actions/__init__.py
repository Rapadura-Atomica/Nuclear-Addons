bl_info = {
    "name": "Action Retarget (Rig Derivado)",
    "author": "rapaduraatomica + Claude",
    "version": (1, 0, 0),
    "blender": (4, 4, 0),
    "location": "View3D > Sidebar (N) > Retarget",
    "description": "Reaproveita uma Action de um personagem em outro com esqueleto parecido/derivado, copiando o delta local (matrix_basis) por nome de osso.",
    "category": "Animation",
}

import bpy
import re
from bpy.props import (StringProperty, PointerProperty, IntProperty,
                       BoolProperty, EnumProperty)
from bpy.types import PropertyGroup, Operator, Panel

# Padrões excluídos no modo "Só corpo" (rosto / cabelo / roupa / acessórios)
DEFAULT_EXCLUDE = ("CABELO,CABELINHO,CABELOCOSTAS,FACE,BOCA,NARIZ,OLHO,PUPILA,"
                   "SOBRANCELHA,ORELHA,OCULOS,LACO,RABO,SHORT,MANGA,squash,"
                   "CabecaUP,Corpo_UP")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _action_bone_names(action):
    """Ossos referenciados por uma action (compatível com slotted actions 4.4/5.0)."""
    names = set()
    fcs = []
    if hasattr(action, "layers"):
        for layer in action.layers:
            for strip in layer.strips:
                for cbag in getattr(strip, "channelbags", []):
                    fcs.extend(cbag.fcurves)
    if hasattr(action, "fcurves"):
        try:
            fcs.extend(action.fcurves)
        except Exception:
            pass
    for fc in fcs:
        dp = fc.data_path
        if 'pose.bones[' in dp:
            try:
                names.add(dp.split('"')[1])
            except Exception:
                pass
    return names


def _strip_suffix(name):
    return re.sub(r"\.\d+$", "", name)


def _build_mapping(props, src_obj, tgt_obj, action):
    """Retorna (lista de (src_bone, tgt_bone), avisos)."""
    warnings = []
    driven = _action_bone_names(action)
    src_pose = {pb.name for pb in src_obj.pose.bones}
    tgt_pose = {pb.name for pb in tgt_obj.pose.bones}

    # filtro de escopo
    if props.scope == 'ALL':
        excl = []
    else:
        raw = props.exclude_patterns if props.scope == 'CUSTOM' else DEFAULT_EXCLUDE
        excl = [p.strip().upper() for p in raw.split(",") if p.strip()]

    def passes(name):
        up = name.upper()
        return not any(e in up for e in excl)

    # índice de destino por nome (com ou sem sufixo .NNN)
    tgt_by_base = {}
    if props.ignore_number_suffix:
        for n in tgt_pose:
            tgt_by_base.setdefault(_strip_suffix(n), n)

    pairs = []
    for src_name in sorted(driven):
        if src_name not in src_pose:
            continue  # canal órfão na action
        if not passes(src_name):
            continue
        if src_name in tgt_pose:
            pairs.append((src_name, src_name))
        elif props.ignore_number_suffix and _strip_suffix(src_name) in tgt_by_base:
            pairs.append((src_name, tgt_by_base[_strip_suffix(src_name)]))
        else:
            warnings.append(src_name)
    return pairs, warnings


def _resolve_action(props, src_obj):
    if props.source_action:
        return props.source_action
    if src_obj.animation_data and src_obj.animation_data.action:
        return src_obj.animation_data.action
    return None


# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------
def _is_armature(self, obj):
    return obj.type == 'ARMATURE'


class ARETARGET_Props(PropertyGroup):
    source_armature: PointerProperty(name="Origem (A)", type=bpy.types.Object, poll=_is_armature)
    target_armature: PointerProperty(name="Destino (B)", type=bpy.types.Object, poll=_is_armature)
    source_action: PointerProperty(name="Action", type=bpy.types.Action,
                                   description="Vazio = usa a Action ativa da Origem")
    new_action_name: StringProperty(name="Nome da nova Action", default="")
    use_action_range: BoolProperty(name="Usar range da Action", default=True)
    frame_start: IntProperty(name="Início", default=1)
    frame_end: IntProperty(name="Fim", default=64)
    scope: EnumProperty(name="Escopo", default='BODY',
                        items=[('BODY', "Só corpo/locomoção", "Exclui rosto, cabelo, roupa"),
                               ('ALL', "Todos com nome igual", "Todos os ossos coincidentes"),
                               ('CUSTOM', "Personalizado", "Defina os padrões a excluir")])
    exclude_patterns: StringProperty(name="Excluir (vírgula)", default=DEFAULT_EXCLUDE)
    ignore_number_suffix: BoolProperty(name="Casar ignorando sufixo .001",
                                       default=False,
                                       description="Casa 'CABECA' com 'CABECA.001' etc. Use com cuidado.")
    copy_location: BoolProperty(name="Location", default=True)
    copy_rotation: BoolProperty(name="Rotation", default=True)
    copy_scale: BoolProperty(name="Scale", default=True)


# ---------------------------------------------------------------------------
# operators
# ---------------------------------------------------------------------------
class ARETARGET_OT_preview(Operator):
    bl_idname = "aretarget.preview"
    bl_label = "Pré-visualizar mapeamento"
    bl_description = "Mostra quantos ossos vão casar e quais ficam de fora"

    def execute(self, context):
        p = context.scene.aretarget
        src, tgt = p.source_armature, p.target_armature
        if not (src and tgt):
            self.report({'ERROR'}, "Defina Origem e Destino.")
            return {'CANCELLED'}
        act = _resolve_action(p, src)
        if not act:
            self.report({'ERROR'}, "Sem Action na Origem.")
            return {'CANCELLED'}
        pairs, warn = _build_mapping(p, src, tgt, act)
        self.report({'INFO'}, f"{len(pairs)} ossos casam | {len(warn)} sem correspondência no destino")
        print(f"[Retarget] Action '{act.name}': {len(pairs)} mapeados, {len(warn)} fora")
        for s, t in pairs:
            print(f"   {s}  ->  {t}")
        if warn:
            print("   SEM CORRESPONDÊNCIA:", ", ".join(warn))
        return {'FINISHED'}


class ARETARGET_OT_run(Operator):
    bl_idname = "aretarget.run"
    bl_label = "Retarget!"
    bl_description = "Copia a animação da Origem para o Destino numa nova Action"

    def execute(self, context):
        p = context.scene.aretarget
        src, tgt = p.source_armature, p.target_armature
        if not (src and tgt):
            self.report({'ERROR'}, "Defina Origem e Destino.")
            return {'CANCELLED'}
        if src == tgt:
            self.report({'ERROR'}, "Origem e Destino são o mesmo objeto.")
            return {'CANCELLED'}
        act = _resolve_action(p, src)
        if not act:
            self.report({'ERROR'}, "Sem Action na Origem.")
            return {'CANCELLED'}

        pairs, warn = _build_mapping(p, src, tgt, act)
        if not pairs:
            self.report({'ERROR'}, "Nenhum osso casou — confira nomes/escopo.")
            return {'CANCELLED'}

        if p.use_action_range:
            f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
        else:
            f0, f1 = p.frame_start, p.frame_end

        scene = context.scene
        depsgraph = context.evaluated_depsgraph_get  # noqa
        view_layer = context.view_layer

        # ---- garante que a Origem está tocando a Action escolhida ----
        if not src.animation_data:
            src.animation_data_create()
        prev_action = src.animation_data.action
        prev_slot = getattr(src.animation_data, "action_slot", None)
        src.animation_data.action = act
        # garante slot (slotted actions 4.4/5.0)
        if hasattr(src.animation_data, "action_slot") and src.animation_data.action_slot is None:
            slots = getattr(act, "slots", None)
            if slots and len(slots):
                src.animation_data.action_slot = slots[0]

        # ---- nova Action no Destino ----
        name = p.new_action_name.strip() or f"{src.name}_to_{tgt.name}_Retarget"
        if name in bpy.data.actions:
            bpy.data.actions.remove(bpy.data.actions[name])
        new_act = bpy.data.actions.new(name)
        new_act.use_fake_user = True
        if not tgt.animation_data:
            tgt.animation_data_create()
        prev_tgt_action = tgt.animation_data.action
        tgt.animation_data.action = new_act

        # rotation_mode coerente origem->destino
        for s_name, t_name in pairs:
            tgt.pose.bones[t_name].rotation_mode = src.pose.bones[s_name].rotation_mode

        # ---- bake ----
        for f in range(f0, f1 + 1):
            scene.frame_set(f)
            view_layer.update()
            basis = {t: src.pose.bones[s].matrix_basis.copy() for s, t in pairs}
            for s, t in pairs:
                tgt.pose.bones[t].matrix_basis = basis[t]
            for s, t in pairs:
                pb = tgt.pose.bones[t]
                if p.copy_location:
                    pb.keyframe_insert('location', frame=f)
                if p.copy_rotation:
                    if pb.rotation_mode == 'QUATERNION':
                        pb.keyframe_insert('rotation_quaternion', frame=f)
                    elif pb.rotation_mode == 'AXIS_ANGLE':
                        pb.keyframe_insert('rotation_axis_angle', frame=f)
                    else:
                        pb.keyframe_insert('rotation_euler', frame=f)
                if p.copy_scale:
                    pb.keyframe_insert('scale', frame=f)

        # ---- restaura a Origem ----
        src.animation_data.action = prev_action
        if prev_action and hasattr(src.animation_data, "action_slot") and prev_slot:
            try:
                src.animation_data.action_slot = prev_slot
            except Exception:
                pass

        scene.frame_start, scene.frame_end = f0, f1
        msg = f"OK: '{new_act.name}' — {len(pairs)} ossos, frames {f0}-{f1}"
        if warn:
            msg += f" ({len(warn)} sem correspondência, ignorados)"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
class ARETARGET_PT_panel(Panel):
    bl_label = "Action Retarget"
    bl_idname = "ARETARGET_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Retarget"

    def draw(self, context):
        layout = self.layout
        p = context.scene.aretarget
        col = layout.column(align=True)
        col.prop(p, "source_armature")
        col.prop(p, "source_action")
        col.prop(p, "target_armature")

        box = layout.box()
        box.prop(p, "scope")
        if p.scope == 'CUSTOM':
            box.prop(p, "exclude_patterns")
        box.prop(p, "ignore_number_suffix")
        row = box.row(align=True)
        row.prop(p, "copy_location", toggle=True)
        row.prop(p, "copy_rotation", toggle=True)
        row.prop(p, "copy_scale", toggle=True)

        box.prop(p, "use_action_range")
        if not p.use_action_range:
            r = box.row(align=True)
            r.prop(p, "frame_start")
            r.prop(p, "frame_end")

        layout.prop(p, "new_action_name")
        layout.operator("aretarget.preview", icon='VIEWZOOM')
        layout.operator("aretarget.run", icon='ARMATURE_DATA')


classes = (ARETARGET_Props, ARETARGET_OT_preview, ARETARGET_OT_run, ARETARGET_PT_panel)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.aretarget = PointerProperty(type=ARETARGET_Props)


def unregister():
    del bpy.types.Scene.aretarget
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()

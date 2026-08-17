bl_info = {
    "name": "Reaproveitar Animação (Esqueleto Parecido)",
    "author": "rapaduraatomica + Claude",
    "version": (1, 1, 0),
    "blender": (4, 4, 0),
    "location": "Vista 3D > Barra lateral (N) > Reaproveitar",
    "description": "Reaproveita a animação de um personagem em outro de esqueleto parecido, copiando o movimento de cada osso pelo nome.",
    "category": "Animation",
}

import bpy
import re
from bpy.props import (StringProperty, PointerProperty, IntProperty,
                       BoolProperty, EnumProperty, FloatProperty)
from bpy.types import PropertyGroup, Operator, Panel

# Padrões excluídos no modo "Só corpo" (rosto / cabelo / roupa / acessórios)
DEFAULT_EXCLUDE = ("CABELO,CABELINHO,CABELOCOSTAS,FACE,BOCA,NARIZ,OLHO,PUPILA,"
                   "SOBRANCELHA,ORELHA,OCULOS,LACO,RABO,SHORT,MANGA,squash,"
                   "CabecaUP,Corpo_UP")

# Tolerância para considerar dois rest poses idênticos (pula a conjugação)
REST_EPSILON = 1e-6


# ---------------------------------------------------------------------------
# helpers de API (isolam o que varia entre versões/slotted actions)
# ---------------------------------------------------------------------------
def _action_fcurves(action):
    """Todas as fcurves de uma action (slotted 4.4/5.0 ou legado)."""
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
    return fcs


def _action_bone_names(action):
    """Ossos referenciados por uma action."""
    names = set()
    for fc in _action_fcurves(action):
        dp = fc.data_path
        if 'pose.bones[' in dp:
            try:
                names.add(dp.split('"')[1])
            except Exception:
                pass
    return names


def _enum_value(owner, prop_name, identifier):
    """Valor inteiro de um item de enum, lido do RNA (não hardcoded)."""
    try:
        return owner.bl_rna.properties[prop_name].enum_items[identifier].value
    except Exception:
        return None


def _strip_suffix(name):
    return re.sub(r"\.\d+$", "", name)


# ---------------------------------------------------------------------------
# mapeamento
# ---------------------------------------------------------------------------
def _build_mapping(props, src_obj, tgt_obj, action):
    """Retorna (pares, sem_correspondencia, colisoes).

    colisoes = [(src_descartado, tgt, src_que_ficou)] — dois ossos de origem
    disputando o mesmo osso de destino.
    """
    warnings = []
    collisions = []
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

    candidates = [n for n in sorted(driven) if n in src_pose and passes(n)]

    pairs = []
    used_tgt = {}

    def claim(src_name, tgt_name):
        """Reserva o osso de destino; acusa colisão se já estiver tomado."""
        if tgt_name in used_tgt:
            collisions.append((src_name, tgt_name, used_tgt[tgt_name]))
            return
        used_tgt[tgt_name] = src_name
        pairs.append((src_name, tgt_name))

    # 1ª passada: nomes idênticos têm prioridade sobre o casamento por sufixo
    matched_exact = set()
    for src_name in candidates:
        if src_name in tgt_pose:
            claim(src_name, src_name)
            matched_exact.add(src_name)

    # 2ª passada: casamento ignorando o sufixo .NNN
    for src_name in candidates:
        if src_name in matched_exact:
            continue
        base = _strip_suffix(src_name)
        if props.ignore_number_suffix and base in tgt_by_base:
            claim(src_name, tgt_by_base[base])
        else:
            warnings.append(src_name)

    return pairs, warnings, collisions


def _resolve_action(props, src_obj):
    if props.source_action:
        return props.source_action
    if src_obj.animation_data and src_obj.animation_data.action:
        return src_obj.animation_data.action
    return None


# ---------------------------------------------------------------------------
# conversão entre rest poses
# ---------------------------------------------------------------------------
def _matrices_close(a, b, eps=REST_EPSILON):
    for row_a, row_b in zip(a, b):
        for va, vb in zip(row_a, row_b):
            if abs(va - vb) > eps:
                return False
    return True


def _build_conversions(src_obj, tgt_obj, pairs, use_rest_comp):
    """Pré-calcula, por par, as matrizes de repouso usadas na conjugação.

    O delta local M do osso de origem vira, em espaço de armadura,
    M_arm = B_src @ M @ B_src⁻¹. Reprojetado no osso de destino:
    M_tgt = B_tgt⁻¹ @ M_arm @ B_tgt. Se os rest poses são iguais isso é a
    identidade, então nesse caso guardamos None e pulamos a conta.
    """
    conv = {}
    for s, t in pairs:
        if not use_rest_comp:
            conv[t] = None
            continue
        b_src = src_obj.data.bones[s].matrix_local
        b_tgt = tgt_obj.data.bones[t].matrix_local
        if _matrices_close(b_src, b_tgt):
            conv[t] = None
        else:
            conv[t] = (b_src.copy(), b_src.inverted_safe(),
                       b_tgt.copy(), b_tgt.inverted_safe())
    return conv


def _convert_basis(mat, conv, scale):
    """Aplica compensação de rest pose e de escala ao delta local."""
    if conv is None:
        if scale != 1.0:
            mat = mat.copy()
            mat.translation = mat.translation * scale
        return mat
    b_src, b_src_i, b_tgt, b_tgt_i = conv
    m_arm = b_src @ mat @ b_src_i
    if scale != 1.0:
        m_arm.translation = m_arm.translation * scale
    return b_tgt_i @ m_arm @ b_tgt


def _auto_scale_factor(src_obj, tgt_obj, pairs):
    """Razão média de comprimento dos ossos casados (destino / origem)."""
    ratios = []
    for s, t in pairs:
        ls = src_obj.data.bones[s].length
        lt = tgt_obj.data.bones[t].length
        if ls > 1e-6 and lt > 1e-6:
            ratios.append(lt / ls)
    if not ratios:
        return 1.0
    return sum(ratios) / len(ratios)


# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------
def _is_armature(self, obj):
    return obj.type == 'ARMATURE'


class ARETARGET_Props(PropertyGroup):
    source_armature: PointerProperty(
        name="Personagem original", type=bpy.types.Object, poll=_is_armature,
        description="O personagem que já tem a animação pronta")
    target_armature: PointerProperty(
        name="Personagem novo", type=bpy.types.Object, poll=_is_armature,
        description="O personagem que vai receber a animação")
    source_action: PointerProperty(
        name="Animação", type=bpy.types.Action,
        description="Qual animação reaproveitar. Deixe vazio para usar a que o "
                    "personagem original já está tocando")
    new_action_name: StringProperty(
        name="Nome da nova animação", default="",
        description="Deixe vazio para o nome ser montado sozinho")
    overwrite_existing: BoolProperty(
        name="Substituir animação de mesmo nome",
        default=False,
        description="Desligado: se já existir uma animação com esse nome, ela é "
                    "preservada e a nova ganha um número no fim. "
                    "Ligado: a antiga é APAGADA, mesmo que outro personagem esteja usando ela")
    use_action_range: BoolProperty(
        name="Usar a duração da animação original", default=True,
        description="Copia do primeiro ao último quadro da animação original")
    frame_start: IntProperty(name="Do quadro", default=1)
    frame_end: IntProperty(name="Até o quadro", default=64)
    scope: EnumProperty(
        name="Quais ossos", default='BODY',
        items=[('BODY', "Só o corpo", "Deixa de fora rosto, cabelo, roupa e acessórios"),
               ('ALL', "Tudo que tiver o mesmo nome", "Copia todos os ossos que existem nos dois"),
               ('CUSTOM', "Eu escolho", "Você define o que deixar de fora")],
        description="Quais ossos entram na cópia")
    exclude_patterns: StringProperty(
        name="Deixar de fora", default=DEFAULT_EXCLUDE,
        description="Pedaços de nome, separados por vírgula. Qualquer osso que "
                    "contenha um desses pedaços é ignorado")
    ignore_number_suffix: BoolProperty(
        name="Aceitar nomes terminados em .001",
        default=False,
        description="Faz 'CABECA' casar com 'CABECA.001'. Use com cuidado: pode "
                    "juntar ossos que não são o mesmo")
    copy_location: BoolProperty(name="Posição", default=True,
                                description="Copia o deslocamento dos ossos")
    copy_rotation: BoolProperty(name="Rotação", default=True,
                                description="Copia o giro dos ossos")
    copy_scale: BoolProperty(name="Tamanho", default=True,
                             description="Copia o esticar e encolher dos ossos")

    use_rest_compensation: BoolProperty(
        name="Corrigir esqueletos diferentes",
        default=True,
        description="Recalcula o movimento levando em conta a posição de descanso de "
                    "cada osso. Deixe ligado: conserta o movimento quando os ossos dos "
                    "dois personagens não estão exatamente na mesma direção, e não "
                    "muda nada quando os esqueletos já são iguais")
    scale_mode: EnumProperty(
        name="Diferença de tamanho",
        default='NONE',
        items=[('NONE', "Ignorar", "Copia o deslocamento do jeito que está"),
               ('AUTO', "Calcular sozinho", "Mede a diferença de tamanho entre os dois esqueletos"),
               ('MANUAL', "Eu defino", "Você digita a proporção")],
        description="Use quando um personagem é maior ou menor que o outro e o "
                    "deslocamento sai errado (pé escorregando, personagem fora do chão)")
    scale_factor: FloatProperty(
        name="Proporção", default=1.0, min=0.001, soft_max=10.0,
        description="2.0 = o personagem novo é o dobro do original")
    sync_rotation_mode: BoolProperty(
        name="Igualar o modo de rotação",
        default=False,
        description="Deixe desligado. Ligado, muda o modo de rotação dos ossos do "
                    "personagem novo para bater com o do original — isso altera o "
                    "esqueleto dele de forma permanente")


# ---------------------------------------------------------------------------
# operators
# ---------------------------------------------------------------------------
class ARETARGET_OT_preview(Operator):
    bl_idname = "aretarget.preview"
    bl_label = "Conferir antes"
    bl_description = ("Mostra quantos ossos vão ser copiados e quais ficam de fora, "
                      "sem alterar nada")
    bl_options = {'REGISTER'}

    def execute(self, context):
        p = context.scene.aretarget
        src, tgt = p.source_armature, p.target_armature
        if not (src and tgt):
            self.report({'ERROR'}, "Escolha o personagem original e o novo.")
            return {'CANCELLED'}
        act = _resolve_action(p, src)
        if not act:
            self.report({'ERROR'}, "O personagem original não tem nenhuma animação.")
            return {'CANCELLED'}
        pairs, warn, collisions = _build_mapping(p, src, tgt, act)

        msg = f"{len(pairs)} ossos vão ser copiados | {len(warn)} não existem no personagem novo"
        if collisions:
            msg += f" | {len(collisions)} nomes repetidos"
        self.report({'WARNING'} if collisions else {'INFO'}, msg)

        print(f"[Reaproveitar] Animação '{act.name}': {len(pairs)} ossos copiados, {len(warn)} de fora")
        for s, t in pairs:
            print(f"   {s}  ->  {t}")
        if warn:
            print("   NÃO EXISTEM NO PERSONAGEM NOVO:", ", ".join(warn))
        for dropped, t, kept in collisions:
            print(f"   NOME REPETIDO: '{dropped}' foi ignorado, '{t}' já recebe '{kept}'")

        if p.scale_mode == 'AUTO' and pairs:
            print(f"   Diferença de tamanho calculada: {_auto_scale_factor(src, tgt, pairs):.4f}")
        return {'FINISHED'}


class ARETARGET_OT_run(Operator):
    bl_idname = "aretarget.run"
    bl_label = "Reaproveitar animação"
    bl_description = ("Copia a animação do personagem original para o novo, "
                      "criando uma animação separada")
    bl_options = {'REGISTER', 'UNDO'}

    # -- fase 1: amostra o movimento da origem ------------------------------
    def _sample(self, context, src, tgt, pairs, conv, scale, f0, f1):
        """Percorre os frames uma única vez e devolve {data_path: {idx: [vals]}}."""
        scene = context.scene
        view_layer = context.view_layer
        wm = context.window_manager

        p = context.scene.aretarget
        frames = list(range(f0, f1 + 1))

        src_bones = {s: src.pose.bones[s] for s, _ in pairs}
        tgt_bones = {t: tgt.pose.bones[t] for _, t in pairs}
        rot_mode = {t: tgt_bones[t].rotation_mode for t in tgt_bones}
        paths = {t: tgt_bones[t].path_from_id for t in tgt_bones}

        channels = {}   # (data_path, array_index) -> lista de valores
        prev_euler = {}

        def push(data_path, values):
            for i, v in enumerate(values):
                channels.setdefault((data_path, i), []).append(v)

        wm.progress_begin(0, len(frames))
        try:
            for i, f in enumerate(frames):
                scene.frame_set(f)
                view_layer.update()
                for s, t in pairs:
                    mat = _convert_basis(src_bones[s].matrix_basis, conv[t], scale)
                    loc, quat, scl = mat.decompose()
                    if p.copy_location:
                        push(paths[t]("location"), loc)
                    if p.copy_rotation:
                        mode = rot_mode[t]
                        if mode == 'QUATERNION':
                            push(paths[t]("rotation_quaternion"), quat)
                        elif mode == 'AXIS_ANGLE':
                            axis, angle = quat.to_axis_angle()
                            push(paths[t]("rotation_axis_angle"),
                                 (angle, axis.x, axis.y, axis.z))
                        else:
                            # euler_compat evita saltos de 360° entre frames
                            eul = quat.to_euler(mode, prev_euler[t]) if t in prev_euler \
                                else quat.to_euler(mode)
                            prev_euler[t] = eul
                            push(paths[t]("rotation_euler"), eul)
                    if p.copy_scale:
                        push(paths[t]("scale"), scl)
                wm.progress_update(i)
        finally:
            wm.progress_end()

        return frames, channels

    # -- fase 2: cria as fcurves deixando o Blender montar slot/channelbag --
    def _seed_channels(self, tgt, pairs, channels, frames):
        """Insere um keyframe por canal para que a action ganhe as fcurves."""
        f0 = frames[0]
        touched = set()
        for (data_path, idx) in channels:
            if data_path in touched:
                continue
            touched.add(data_path)
            prop = data_path.rsplit(".", 1)[-1]
            bone_path = data_path.rsplit(".", 1)[0]
            try:
                pb = tgt.path_resolve(bone_path)
            except Exception:
                continue
            # valores do primeiro frame, para o keyframe semente não nascer errado
            n = len(getattr(pb, prop))
            first = [channels[(data_path, i)][0] for i in range(n)]
            setattr(pb, prop, first)
            try:
                pb.keyframe_insert(prop, frame=f0)
            except Exception:
                pass

    # -- fase 3: preenche as curvas em lote --------------------------------
    def _fill_curves(self, action, frames, channels):
        """Escreve todos os keyframes com foreach_set. Retorna nº de canais preenchidos."""
        index = {}
        for fc in _action_fcurves(action):
            index[(fc.data_path, fc.array_index)] = fc

        n = len(frames)
        filled = 0
        interp = None
        handle = None

        for key, values in channels.items():
            fc = index.get(key)
            if fc is None or len(values) != n:
                continue

            kps = fc.keyframe_points
            have = len(kps)
            if have != n:
                if have > n:
                    try:
                        kps.clear()
                    except Exception:
                        continue
                    have = 0
                kps.add(n - have)

            flat = []
            for i, f in enumerate(frames):
                flat.append(float(f))
                flat.append(float(values[i]))
            kps.foreach_set("co", flat)

            if interp is None and len(kps):
                interp = _enum_value(kps[0], "interpolation", 'BEZIER')
                handle = _enum_value(kps[0], "handle_left_type", 'AUTO_CLAMPED')
            if interp is not None:
                kps.foreach_set("interpolation", [interp] * n)
            if handle is not None:
                kps.foreach_set("handle_left_type", [handle] * n)
                kps.foreach_set("handle_right_type", [handle] * n)

            fc.update()
            filled += 1
        return filled

    # -- fallback: se as fcurves não puderem ser localizadas ----------------
    def _fill_by_insert(self, tgt, frames, channels):
        """Caminho lento, mas sem frame_set: reinsere canal a canal."""
        by_path = {}
        for (data_path, idx), values in channels.items():
            by_path.setdefault(data_path, {})[idx] = values

        for data_path, comps in by_path.items():
            prop = data_path.rsplit(".", 1)[-1]
            bone_path = data_path.rsplit(".", 1)[0]
            try:
                pb = tgt.path_resolve(bone_path)
            except Exception:
                continue
            n = len(comps)
            for i, f in enumerate(frames):
                setattr(pb, prop, [comps[c][i] for c in range(n)])
                try:
                    pb.keyframe_insert(prop, frame=f)
                except Exception:
                    break

    def execute(self, context):
        p = context.scene.aretarget
        src, tgt = p.source_armature, p.target_armature
        if not (src and tgt):
            self.report({'ERROR'}, "Escolha o personagem original e o novo.")
            return {'CANCELLED'}
        if src == tgt:
            self.report({'ERROR'}, "O personagem original e o novo são o mesmo.")
            return {'CANCELLED'}
        if not (p.copy_location or p.copy_rotation or p.copy_scale):
            self.report({'ERROR'}, "Marque ao menos um: Posição, Rotação ou Tamanho.")
            return {'CANCELLED'}
        act = _resolve_action(p, src)
        if not act:
            self.report({'ERROR'}, "O personagem original não tem nenhuma animação.")
            return {'CANCELLED'}

        pairs, warn, collisions = _build_mapping(p, src, tgt, act)
        if not pairs:
            self.report({'ERROR'}, "Nenhum osso combinou — confira os nomes e o que foi deixado de fora.")
            return {'CANCELLED'}

        if p.use_action_range:
            f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
        else:
            f0, f1 = p.frame_start, p.frame_end
        if f1 < f0:
            self.report({'ERROR'}, f"Os quadros estão invertidos: {f0} até {f1}.")
            return {'CANCELLED'}

        scene = context.scene

        # ---- estado a restaurar ao final ----
        prev_frame = scene.frame_current
        if not src.animation_data:
            src.animation_data_create()
        prev_action = src.animation_data.action
        prev_slot = getattr(src.animation_data, "action_slot", None)

        # ---- garante que a Origem está tocando a Action escolhida ----
        src.animation_data.action = act
        if hasattr(src.animation_data, "action_slot") and src.animation_data.action_slot is None:
            slots = getattr(act, "slots", None)
            if slots and len(slots):
                src.animation_data.action_slot = slots[0]

        # ---- nova Action no Destino ----
        name = p.new_action_name.strip() or f"{src.name}_to_{tgt.name}_Retarget"
        replaced = False
        if p.overwrite_existing and name in bpy.data.actions:
            bpy.data.actions.remove(bpy.data.actions[name])
            replaced = True
        new_act = bpy.data.actions.new(name)   # auto-numera se o nome já existir
        new_act.use_fake_user = True
        if not tgt.animation_data:
            tgt.animation_data_create()
        tgt.animation_data.action = new_act

        # ---- rotation_mode ----
        if p.sync_rotation_mode:
            for s_name, t_name in pairs:
                tgt.pose.bones[t_name].rotation_mode = src.pose.bones[s_name].rotation_mode

        # ---- fatores de conversão ----
        conv = _build_conversions(src, tgt, pairs, p.use_rest_compensation)
        if p.scale_mode == 'AUTO':
            scale = _auto_scale_factor(src, tgt, pairs)
        elif p.scale_mode == 'MANUAL':
            scale = p.scale_factor
        else:
            scale = 1.0

        # ---- bake ----
        fast_path = True
        try:
            frames, channels = self._sample(context, src, tgt, pairs, conv, scale, f0, f1)
            if not channels:
                self.report({'ERROR'}, "Não havia nada para copiar.")
                return {'CANCELLED'}
            self._seed_channels(tgt, pairs, channels, frames)
            filled = self._fill_curves(new_act, frames, channels)
            if filled < len(channels):
                fast_path = False
                self._fill_by_insert(tgt, frames, channels)
        finally:
            # ---- restaura a Origem e o frame atual ----
            src.animation_data.action = prev_action
            if prev_action and hasattr(src.animation_data, "action_slot") and prev_slot:
                try:
                    src.animation_data.action_slot = prev_slot
                except Exception:
                    pass
            scene.frame_set(prev_frame)

        msg = f"Pronto: '{new_act.name}' — {len(pairs)} ossos, quadros {f0} a {f1}"
        if scale != 1.0:
            msg += f", tamanho ajustado em {scale:.3f}"
        if warn:
            msg += f" ({len(warn)} ossos não existem no personagem novo)"
        if collisions:
            msg += f" ({len(collisions)} nomes repetidos — veja o console)"
        if replaced:
            msg += " [animação anterior substituída]"
        if not fast_path:
            msg += " [modo lento]"
        self.report({'WARNING'} if collisions else {'INFO'}, msg)
        for dropped, t, kept in collisions:
            print(f"[Reaproveitar] NOME REPETIDO: '{dropped}' foi ignorado, '{t}' já recebe '{kept}'")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
class ARETARGET_PT_panel(Panel):
    bl_label = "Reaproveitar Animação"
    bl_idname = "ARETARGET_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Reaproveitar"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        p = context.scene.aretarget

        # --- de quem, para quem ---
        col = layout.column()
        col.prop(p, "source_armature", icon='ARMATURE_DATA')
        col.prop(p, "source_action", icon='ACTION')
        col.separator()
        col.prop(p, "target_armature", icon='OUTLINER_OB_ARMATURE')

        # --- quais ossos ---
        layout.separator()
        col = layout.column()
        col.prop(p, "scope")
        if p.scope == 'CUSTOM':
            col.prop(p, "exclude_patterns")
        col.prop(p, "ignore_number_suffix")

        col = layout.column(heading="Copiar")
        col.prop(p, "copy_location")
        col.prop(p, "copy_rotation")
        col.prop(p, "copy_scale")

        # --- que trecho ---
        layout.separator()
        col = layout.column()
        col.prop(p, "use_action_range")
        sub = col.column(align=True)
        sub.enabled = not p.use_action_range
        sub.prop(p, "frame_start")
        sub.prop(p, "frame_end")

        # --- resultado ---
        layout.separator()
        col = layout.column()
        col.prop(p, "new_action_name")
        col.prop(p, "overwrite_existing")

        # --- ação ---
        layout.separator()
        acoes = layout.column(align=True)
        acoes.use_property_split = False
        pronto = bool(p.source_armature and p.target_armature)
        if not pronto:
            acoes.label(text="Escolha os dois personagens acima", icon='INFO')
        elif p.source_armature == p.target_armature:
            acoes.label(text="Os dois personagens são o mesmo", icon='ERROR')
            pronto = False

        conferir = acoes.column(align=True)
        conferir.enabled = pronto
        conferir.operator("aretarget.preview", icon='VIEWZOOM')

        executar = acoes.column(align=True)
        executar.enabled = pronto
        executar.scale_y = 1.5
        executar.operator("aretarget.run", icon='PLAY')


class ARETARGET_PT_fit(Panel):
    bl_label = "Ajuste fino"
    bl_idname = "ARETARGET_PT_fit"
    bl_parent_id = "ARETARGET_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Reaproveitar"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        p = context.scene.aretarget

        col = layout.column()
        col.prop(p, "use_rest_compensation")
        col.prop(p, "sync_rotation_mode")

        layout.separator()
        col = layout.column()
        col.prop(p, "scale_mode")
        sub = col.column()
        sub.enabled = p.scale_mode == 'MANUAL'
        sub.prop(p, "scale_factor")


classes = (ARETARGET_Props, ARETARGET_OT_preview, ARETARGET_OT_run,
           ARETARGET_PT_panel, ARETARGET_PT_fit)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.aretarget = PointerProperty(type=ARETARGET_Props)


def unregister():
    if hasattr(bpy.types.Scene, "aretarget"):
        del bpy.types.Scene.aretarget
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()

import bpy
import bpy_extras.anim_utils as anim_utils  # Essencial para Blender 5.0+

from collections import defaultdict

bl_info = {
    "name": "Animação por 2",
    "author": 'https://rapaduraatomica.com.br',
    "version": (1, 6),
    "blender": (5, 0, 0),
    "location": "View3D > Sidebar > Animation OR Dope Sheet > Animation",
    "description": "Criação de animação por 2's, interpolação constante e movimento de keyframes (compatível Blender 5.0)",
    "category": "Animation"
}

addon_keymaps = []

# --- OPERATORS ---

class KEYFRAME_OT_move_keyframes(bpy.types.Operator):
    """Move keyframes futuros para frente ou para trás"""
    bl_idname = "anim.move_keyframes"
    bl_label = "Mover Keyframes Futuros"
    bl_options = {'REGISTER', 'UNDO'}

    offset: bpy.props.IntProperty(
        name="Offset",
        description="Quantos frames mover (valor negativo p/ trás)",
        default=10,
        min=-250,
        max=250
    )

    include_selected: bpy.props.BoolProperty(
        name="Incluir Selecionados",
        description="Move também o(s) keyframe(s) selecionado(s) se Shift estiver pressionado",
        default=False
    )

    def get_all_selected_keyframes(self, context):
        selected_frames = set()
        frame_atual = context.scene.frame_current

        for obj in context.selected_objects:
            if obj.animation_data and obj.animation_data.action:
                action = obj.animation_data.action
                slot = obj.animation_data.action_slot
                if slot:
                    channelbag = anim_utils.action_ensure_channelbag_for_slot(action, slot)
                    if channelbag:
                        for fcurve in channelbag.fcurves:
                            for kf in fcurve.keyframe_points:
                                frame = int(kf.co[0])
                                if frame > frame_atual:
                                    selected_frames.add(frame)

            if obj.type == 'GREASEPENCIL' and obj.data:
                gp_data = obj.data
                for layer in gp_data.layers:
                    for frame in layer.frames:
                        if frame.frame_number > frame_atual:
                            selected_frames.add(frame.frame_number)

        return sorted(selected_frames)

    def execute(self, context):
        offset = self.offset
        include_selected = self.include_selected
        total_movidos = 0

        frames_selecionados = self.get_all_selected_keyframes(context)
        if not frames_selecionados:
            self.report({'WARNING'}, "Nenhum keyframe futuro encontrado")
            return {'CANCELLED'}

        frame_minimo = context.scene.frame_current

        for obj in context.selected_objects:
            # Actions normais (já corrigido com channelbag)
            if obj.animation_data and obj.animation_data.action:
                action = obj.animation_data.action
                slot = obj.animation_data.action_slot
                if slot:
                    channelbag = anim_utils.action_ensure_channelbag_for_slot(action, slot)
                    if channelbag:
                        movidos = self.move_action_keyframes(channelbag, frame_minimo, offset, include_selected)
                        total_movidos += movidos

            # Grease Pencil (já ok)
            if obj.type == 'GREASEPENCIL' and obj.data:
                movidos = self.move_grease_pencil_keyframes(obj.data, frame_minimo, offset, include_selected)
                total_movidos += movidos

        # Correção aqui: sequencer_movidos
        sequencer_movidos = 0
        if context.scene.sequence_editor:
            for strip in context.scene.sequence_editor.strips_all:  # <--- MUDANÇA AQUI
                if strip.type == 'SOUND':
                    if include_selected:
                        if strip.frame_final_end >= frame_minimo:
                            strip.frame_start += offset
                            sequencer_movidos += 1
                    else:
                        if strip.frame_final_start >= frame_minimo:
                            strip.frame_start += offset
                            sequencer_movidos += 1

        # Atualizar UI e relatório (igual)
        for area in context.screen.areas:
            if area.type in {'DOPESHEET_EDITOR', 'GRAPH_EDITOR', 'SEQUENCE_EDITOR'}:
                area.tag_redraw()

        msg = f"{total_movidos} keyframes movidos"
        if include_selected:
            msg += " (incluindo selecionados)"
        context.scene.frame_current += offset
        if sequencer_movidos > 0:
            msg += f", {sequencer_movidos} faixas de áudio movidas"

        self.report({'INFO'}, msg)
        return {'FINISHED'}

    def move_action_keyframes(self, channelbag, frame_minimo, offset, include_selected):
        movidos = 0
        for fcurve in channelbag.fcurves:
            for kf in fcurve.keyframe_points:
                frame = kf.co[0]
                if (include_selected and frame >= frame_minimo) or (not include_selected and frame > frame_minimo):
                    kf.co[0] += offset
                    movidos += 1
            fcurve.update()
        return movidos

    def move_grease_pencil_keyframes(self, gp_data, frame_minimo, offset, include_selected):
        movidos = 0
        for layer in gp_data.layers:
            if not layer.frames:
                continue

            frames_para_mover = []
            for frame in layer.frames:
                fn = frame.frame_number
                if (include_selected and fn >= frame_minimo) or (not include_selected and fn > frame_minimo):
                    frames_para_mover.append(fn)
                    movidos += 1

            frames_info = {f.frame_number: f for f in layer.frames}

            for old_fn in frames_para_mover:
                if old_fn not in frames_info:
                    continue
                old_frame = frames_info[old_fn]
                new_fn = old_fn + offset
                try:
                    new_frame = layer.frames.new(new_fn)
                    new_frame.drawing = old_frame.drawing
                    layer.frames.remove(old_fn)
                except Exception as e:
                    print(f"Erro ao mover GP frame {old_fn} → {new_fn}: {e}")

        return movidos


class ANIM_OT_duplicate_keys_for_twos(bpy.types.Operator):
    bl_idname = "anim.duplicate_keys_for_twos"
    bl_label = "Aplicar Por 2's na Interpolação"
    bl_description = "Cria keyframes por 2's ao longo das interpolações entre keyframes"
    bl_options = {'REGISTER', 'UNDO'}

    start_from_selected: bpy.props.BoolProperty(
        name="Começar do Keyframe Selecionado",
        default=False,
        description="Aplica por 2's apenas a partir do keyframe selecionado em diante"
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj and obj.animation_data and obj.animation_data.action)

    def execute(self, context):
        obj = context.active_object
        action = obj.animation_data.action
        anim_data = obj.animation_data

        if not anim_data.action_slot:
            self.report({'WARNING'}, "Nenhum Action Slot atribuído ao objeto ativo")
            return {'CANCELLED'}

        channelbag = anim_utils.action_ensure_channelbag_for_slot(action, anim_data.action_slot)
        if not channelbag:
            self.report({'WARNING'}, "Não foi possível obter ChannelBag")
            return {'CANCELLED'}

        scene = context.scene
        keyframes_added_total = 0
        start_frame = 1

        if self.start_from_selected:
            selected_frames = []
            for fcurve in channelbag.fcurves:
                for keyframe in fcurve.keyframe_points:
                    if keyframe.select_control_point:
                        selected_frames.append(int(keyframe.co[0]))
            if selected_frames:
                start_frame = min(selected_frames)
        else:
            start_frame = scene.frame_current

        for fcurve in channelbag.fcurves:
            keyframes = sorted(fcurve.keyframe_points, key=lambda k: k.co[0])
            if len(keyframes) < 2:
                continue

            keyframes_to_add = []
            for i in range(len(keyframes) - 1):
                start_key = keyframes[i]
                end_key = keyframes[i + 1]
                start_segment = int(start_key.co[0])
                end_segment = int(end_key.co[0])

                if end_segment < start_frame:
                    continue

                actual_start = max(start_segment, start_frame)
                current_frame = actual_start

                while current_frame < end_segment:
                    if current_frame != start_segment and current_frame != end_segment:
                        value = fcurve.evaluate(current_frame)
                        keyframes_to_add.append({
                            'frame': current_frame,
                            'value': value,
                            'interpolation': 'CONSTANT'
                        })
                    current_frame += 2

            for key_data in sorted(keyframes_to_add, key=lambda k: k['frame'], reverse=True):
                fcurve.keyframe_points.insert(key_data['frame'], key_data['value'])
                new_key = fcurve.keyframe_points[-1]
                new_key.interpolation = key_data['interpolation']
                keyframes_added_total += 1

            fcurve.update()

        context.area.tag_redraw()

        msg = f"Adicionados {keyframes_added_total} keyframes por 2's"
        if self.start_from_selected:
            msg += f" a partir do frame {start_frame}"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class ANIM_OT_create_twos_from_scratch(bpy.types.Operator):
    bl_idname = "anim.create_twos_from_scratch"
    bl_label = "Criar Poses Vagas"
    bl_description = "Cria keyframe inicial para animação por 2's"
    bl_options = {'REGISTER', 'UNDO'}

    clear_existing: bpy.props.BoolProperty(
        name="Limpar Animação Existente",
        default=True,
        description="Remove animação existente antes de criar nova"
    )

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        obj = context.active_object
        scene = context.scene
        current_frame = scene.frame_current

        if self.clear_existing and obj.animation_data and obj.animation_data.action:
            bpy.data.actions.remove(obj.animation_data.action)

        if not obj.animation_data:
            obj.animation_data_create()

        if not obj.animation_data.action:
            action = bpy.data.actions.new(f"{obj.name}_Action")
            obj.animation_data.action = action

        scene.frame_set(1)
        obj.keyframe_insert(data_path="location")
        obj.keyframe_insert(data_path="rotation_euler")
        obj.keyframe_insert(data_path="scale")

        if obj.type == 'GREASEPENCIL' and obj.data.layers.active:
            gp_layer = obj.data.layers.active
            # Keyframe em algo genérico do GP (ex: use se for visibility ou opacity)
            # Ajuste conforme seu uso; se não precisar, comente
            try:
                obj.keyframe_insert(data_path=f'grease_pencil.layers["{gp_layer.name}"].use')
            except:
                pass

        if obj.animation_data and obj.animation_data.action:
            anim_data = obj.animation_data
            channelbag = anim_utils.action_ensure_channelbag_for_slot(obj.animation_data.action, anim_data.action_slot)
            if channelbag:
                for fcurve in channelbag.fcurves:
                    for keyframe in fcurve.keyframe_points:
                        keyframe.interpolation = 'CONSTANT'

        scene.frame_set(current_frame)
        self.report({'INFO'}, "Keyframe inicial criado no frame 1")
        return {'FINISHED'}


class ANIM_OT_remove_twos(bpy.types.Operator):
    bl_idname = "anim.remove_twos"
    bl_label = "Remover Por 2's"
    bl_description = "Remove keyframes em frames pares (animação por 2's)"
    bl_options = {'REGISTER', 'UNDO'}

    remove_from_selected: bpy.props.BoolProperty(
        name="Remover a partir do Selecionado",
        default=False,
        description="Remove por 2's apenas a partir do keyframe selecionado em diante"
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj and obj.animation_data and obj.animation_data.action)

    def execute(self, context):
        obj = context.active_object
        action = obj.animation_data.action
        anim_data = obj.animation_data

        channelbag = anim_utils.action_ensure_channelbag_for_slot(action, anim_data.action_slot)
        if not channelbag:
            self.report({'WARNING'}, "Não foi possível obter ChannelBag")
            return {'CANCELLED'}

        scene = context.scene
        start_frame = 1

        if self.remove_from_selected:
            selected_frames = []
            for fcurve in channelbag.fcurves:
                for keyframe in fcurve.keyframe_points:
                    if keyframe.select_control_point:
                        selected_frames.append(int(keyframe.co[0]))
            if selected_frames:
                start_frame = min(selected_frames)
        else:
            start_frame = scene.frame_current

        removed_count = 0
        for fcurve in channelbag.fcurves:
            keys_to_remove = []
            for keyframe in fcurve.keyframe_points:
                frame = keyframe.co[0]
                if frame < start_frame:
                    continue
                if int(frame) % 2 == 0:
                    # Verifica se há key no frame anterior (para não remover originais)
                    is_original = any(
                        other_key.co[0] == frame - 1
                        for other_fcurve in channelbag.fcurves
                        for other_key in other_fcurve.keyframe_points
                    )
                    if not is_original:
                        keys_to_remove.append(keyframe)
                        removed_count += 1

            for key in sorted(keys_to_remove, key=lambda k: k.co[0], reverse=True):
                fcurve.keyframe_points.remove(key)

        context.area.tag_redraw()

        msg = f"Removidos {removed_count} keyframes"
        if self.remove_from_selected:
            msg += f" a partir do frame {start_frame}"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class ANIM_OT_set_all_interpolation(bpy.types.Operator):
    bl_idname = "anim.set_all_interpolation"
    bl_label = "Definir Interpolação"
    bl_description = "Define o tipo de interpolação para todos os keyframes"
    bl_options = {'REGISTER', 'UNDO'}

    interp_type: bpy.props.EnumProperty(
        items=[
            ('CONSTANT', 'Constante', 'Interpolação constante (degelo)'),
            ('LINEAR', 'Linear', 'Interpolação linear'),
            ('BEZIER', 'Bezier', 'Interpolação Bezier suave')
        ],
        name="Tipo de Interpolação",
        default='CONSTANT'
    )

    apply_from_selected: bpy.props.BoolProperty(
        name="Aplicar a partir do Selecionado",
        default=False,
        description="Aplica interpolação apenas a partir do keyframe selecionado em diante"
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj and obj.animation_data and obj.animation_data.action)

    def execute(self, context):
        obj = context.active_object
        action = obj.animation_data.action
        anim_data = obj.animation_data

        channelbag = anim_utils.action_ensure_channelbag_for_slot(action, anim_data.action_slot)
        if not channelbag:
            self.report({'WARNING'}, "Não foi possível obter ChannelBag")
            return {'CANCELLED'}

        scene = context.scene
        start_frame = 1

        if self.apply_from_selected:
            selected_frames = []
            for fcurve in channelbag.fcurves:
                for keyframe in fcurve.keyframe_points:
                    if keyframe.select_control_point:
                        selected_frames.append(int(keyframe.co[0]))
            if selected_frames:
                start_frame = min(selected_frames)
        else:
            start_frame = scene.frame_current

        keyframe_count = 0
        for fcurve in channelbag.fcurves:
            for keyframe in fcurve.keyframe_points:
                frame = keyframe.co[0]
                if frame < start_frame:
                    continue
                keyframe.interpolation = self.interp_type
                keyframe_count += 1

        context.area.tag_redraw()

        msg = f"Interpolação {self.interp_type} aplicada em {keyframe_count} keyframes"
        if self.apply_from_selected:
            msg += f" a partir do frame {start_frame}"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class ANIM_OT_convert_to_twos_auto(bpy.types.Operator):
    bl_idname = "anim.convert_to_twos_auto"
    bl_label = "Converter para 2's Automaticamente"
    bl_description = "Converte automaticamente animação existente para por 2's"
    bl_options = {'REGISTER', 'UNDO'}

    start_from_selected: bpy.props.BoolProperty(
        name="Começar do Keyframe Selecionado",
        default=False,
        description="Converte para 2's apenas a partir do keyframe selecionado em diante"
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj and obj.animation_data and obj.animation_data.action)

    def execute(self, context):
        obj = context.active_object
        action = obj.animation_data.action
        anim_data = obj.animation_data

        channelbag = anim_utils.action_ensure_channelbag_for_slot(action, anim_data.action_slot)
        if not channelbag:
            self.report({'WARNING'}, "Não foi possível obter ChannelBag")
            return {'CANCELLED'}

        scene = context.scene
        start_frame = 1

        if self.start_from_selected:
            selected_frames = []
            for fcurve in channelbag.fcurves:
                for keyframe in fcurve.keyframe_points:
                    if keyframe.select_control_point:
                        selected_frames.append(int(keyframe.co[0]))
            if selected_frames:
                start_frame = min(selected_frames)
        else:
            start_frame = scene.frame_current

        # Primeiro seta tudo para CONSTANT
        bpy.ops.anim.set_all_interpolation(interp_type='CONSTANT', apply_from_selected=self.start_from_selected)

        keyframes_added_total = 0
        for fcurve in channelbag.fcurves:
            keyframes = sorted(fcurve.keyframe_points, key=lambda k: k.co[0])
            if len(keyframes) < 2:
                continue

            keyframes_to_add = []
            for i in range(len(keyframes) - 1):
                start_segment = int(keyframes[i].co[0])
                end_segment = int(keyframes[i + 1].co[0])

                if end_segment < start_frame:
                    continue

                current_frame = max(start_segment, start_frame) + 2
                while current_frame < end_segment:
                    value = fcurve.evaluate(current_frame)
                    keyframes_to_add.append({
                        'frame': current_frame,
                        'value': value,
                        'interpolation': 'CONSTANT'
                    })
                    current_frame += 2

            for key_data in sorted(keyframes_to_add, key=lambda k: k['frame'], reverse=True):
                fcurve.keyframe_points.insert(key_data['frame'], key_data['value'])
                keyframes_added_total += 1

            fcurve.update()

        context.area.tag_redraw()

        msg = f"Conversão completa! Adicionados {keyframes_added_total} keyframes"
        if self.start_from_selected:
            msg += f" a partir do frame {start_frame}"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


# --- UI PANEL ---

class ANIM_PT_twos_panel(bpy.types.Panel):
    bl_label = "Animação por 2's"
    bl_idname = "ANIM_PT_twos_panel"
    bl_space_type = 'DOPESHEET_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Animation"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object

        layout.label(text="Animação por 2's", icon='POSE_HLT')

        if not obj:
            layout.label(text="Selecione um objeto", icon='ERROR')
            return

        if not (obj.animation_data and obj.animation_data.action):
            box = layout.box()
            box.label(text="Iniciar Animação:", icon='PLAY')
            box.operator("anim.create_twos_from_scratch", text="Criar Poses Vagas")
            return

        box = layout.box()
        box.label(text="Controle de Por 2's:", icon='ARROW_LEFTRIGHT')
        col = box.column(align=True)
        row = col.row(align=True)
        op = row.operator("anim.duplicate_keys_for_twos", text="Aplicar em Tudo")
        op.start_from_selected = False
        op = row.operator("anim.duplicate_keys_for_twos", text="Aplicar da Seleção")
        op.start_from_selected = True

        row = col.row(align=True)
        op = row.operator("anim.remove_twos", text="Remover Tudo")
        op.remove_from_selected = False
        op = row.operator("anim.remove_twos", text="Remover da Seleção")
        op.remove_from_selected = True

        row = box.row(align=True)
        op = row.operator("anim.convert_to_twos_auto", text="Converter Tudo", icon='AUTO')
        op.start_from_selected = False
        op = row.operator("anim.convert_to_twos_auto", text="Converter da Seleção", icon='AUTO')
        op.start_from_selected = True

        box = layout.box()
        box.label(text="Interpolação:", icon='CURVE_BEZCURVE')
        col = box.column(align=True)
        row = col.row(align=True)
        op = row.operator("anim.set_all_interpolation", text="Constante em Tudo")
        op.interp_type = 'CONSTANT'
        op.apply_from_selected = False
        op = row.operator("anim.set_all_interpolation", text="Constante da Seleção")
        op.interp_type = 'CONSTANT'
        op.apply_from_selected = True

        row = col.row(align=True)
        op = row.operator("anim.set_all_interpolation", text="Linear em Tudo")
        op.interp_type = 'LINEAR'
        op.apply_from_selected = False
        op = row.operator("anim.set_all_interpolation", text="Linear da Seleção")
        op.interp_type = 'LINEAR'
        op.apply_from_selected = True

        row = col.row(align=True)
        op = row.operator("anim.set_all_interpolation", text="Bezier em Tudo")
        op.interp_type = 'BEZIER'
        op.apply_from_selected = False
        op = row.operator("anim.set_all_interpolation", text="Bezier da Seleção")
        op.interp_type = 'BEZIER'
        op.apply_from_selected = True


# --- REGISTRO ---

classes = (
    KEYFRAME_OT_move_keyframes,
    ANIM_OT_duplicate_keys_for_twos,
    ANIM_OT_create_twos_from_scratch,
    ANIM_OT_remove_twos,
    ANIM_OT_set_all_interpolation,
    ANIM_OT_convert_to_twos_auto,
    ANIM_PT_twos_panel,
)

def register_keymap():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name='Window', space_type='EMPTY')

        kmi = km.keymap_items.new("anim.move_keyframes", 'NUMPAD_PLUS', 'PRESS')
        kmi.properties.offset = 1
        kmi.properties.include_selected = False
        addon_keymaps.append((km, kmi))

        kmi = km.keymap_items.new("anim.move_keyframes", 'NUMPAD_PLUS', 'PRESS', shift=True)
        kmi.properties.offset = 1
        kmi.properties.include_selected = True
        addon_keymaps.append((km, kmi))

        kmi = km.keymap_items.new("anim.move_keyframes", 'NUMPAD_MINUS', 'PRESS')
        kmi.properties.offset = -1
        kmi.properties.include_selected = False
        addon_keymaps.append((km, kmi))

        kmi = km.keymap_items.new("anim.move_keyframes", 'NUMPAD_MINUS', 'PRESS', shift=True)
        kmi.properties.offset = -1
        kmi.properties.include_selected = True
        addon_keymaps.append((km, kmi))


def unregister_keymap():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    register_keymap()


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    unregister_keymap()


if __name__ == "__main__":
    register()
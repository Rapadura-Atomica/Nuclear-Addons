#lembrar de diminuir os comentarios desnecessarios depois, tipo esse
# E PQP 500+ linhas só de operators, que isso bixo

import bpy
from bpy.types import Operator, Panel
from .. import api_route as gp_api
import bpy_extras.anim_utils as anim_utils
from ..core import helpers
import os
import uuid

class TIME_OFFSET_OT_create_clean_frame(Operator):
    """Cria um novo frame limpo na biblioteca (frames negativos) para TODAS as layers"""
    bl_idname = "time_offset.create_clean_frame"
    bl_label = "Novo Frame na Biblioteca"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and gp_api.obj_is_gp(obj)

    def execute(self, context):
        pose_id = uuid.uuid4().hex
        obj = context.active_object
        if not obj.data.layers:
            self.report({'WARNING'}, "Nenhuma layer encontrada no objeto")
            return {'CANCELLED'}

        # Encontrar o menor frame number (mais negativo) entre TODAS as layers
        first_negative_frame = 0  # Começa com 0
        for layer in obj.data.layers:
            for frame in layer.frames:
                if frame.frame_number < first_negative_frame:
                    first_negative_frame = frame.frame_number

        # O novo frame será ainda mais negativo
        new_frame_number = first_negative_frame - 1

        # Criar novo frame em TODAS as layers
        layers_processed = 0
        for layer in obj.data.layers:
            # Verificar se a layer está habilitada para edição
            if gp_api.layer_locked(layer) or gp_api.layer_hidden(layer):
                continue

            # Criar novo frame
            new_frame = gp_api.new_active_frame(layer.frames, new_frame_number)

            helpers.set_pose_id(obj, new_frame_number, pose_id)

            # Limpar strokes
            if gp_api.is_frame_valid(new_frame):
                self.clear_frame_strokes(new_frame)

            layers_processed += 1

        self.report({'INFO'}, f"Frame {new_frame_number} criado na biblioteca ({layers_processed} layers)")
        
        helpers.generate_library_preview(obj, new_frame_number)
        return {'FINISHED'}

    def clear_frame_strokes(self, frame):
        """Limpa todos os strokes de um frame de forma compatível"""
        if hasattr(frame, 'nuclear_strokes'):
            strokes = frame.nuclear_strokes
            strokes_to_remove = [stroke for stroke in strokes]
            for stroke in strokes_to_remove:
                strokes.remove(stroke)
        elif hasattr(frame, 'strokes'):
            frame.strokes.clear()

class TIME_OFFSET_OT_duplicate_current_frame(Operator):
    """Duplica o frame da biblioteca que está definido no TimeOffset (valor negativo)"""
    bl_idname = "time_offset.duplicate_current_frame"
    bl_label = "Duplicar Frame da Biblioteca"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and gp_api.obj_is_gp(obj) and obj.data.layers

    def execute(self, context):
        obj = context.active_object
        time_mod = helpers.get_time_offset_modifier(obj)
        if not time_mod:
            self.report({'WARNING'}, "Modificador TimeOffset não encontrado")
            return {'CANCELLED'}

        # Usar o valor do offset como frame da biblioteca
        target_frame = time_mod.offset

        # Garantir que estamos trabalhando com frames negativos
        if target_frame >= 0:
            self.report({'WARNING'}, "TimeOffset deve apontar para frames negativos (biblioteca)")
            return {'CANCELLED'}

        # ENCONTRAR O FRAME MAIS NEGATIVO
        most_negative_frame = 0
        for layer in obj.data.layers:
            for frame in layer.frames:
                if frame.frame_number < most_negative_frame:
                    most_negative_frame = frame.frame_number

        # O novo frame será AINDA MAIS NEGATIVO
        new_frame_number = most_negative_frame - 1
        new_pose_id = uuid.uuid4().hex
        layers_processed = 0
        layers_skipped = 0
        frames_duplicated = 0

        print(f"=== DEBUG: Duplicando frame {target_frame} para {new_frame_number} ===")

        # PARA CADA LAYER, USAR A FUNÇÃO copy_frame DO API_ROUTER
        for layer in obj.data.layers:
            # Verificar se a layer está habilitada para edição
            if gp_api.layer_locked(layer) or gp_api.layer_hidden(layer):
                layers_skipped += 1
                print(f" Layer {layer.info}: SKIPPED (locked or hidden)")
                continue

            # Buscar o frame TARGET na biblioteca
            src_frame = None
            for frame in layer.frames:
                if frame.frame_number == target_frame:
                    src_frame = frame
                    break

            if src_frame:
                try:
                    print(f" Layer {layer.info}: Encontrado frame {target_frame}")
                    # VERIFICAR SE O FRAME TEM CONTEÚDO
                    has_content = False
                    stroke_count = 0
                    if hasattr(src_frame, 'strokes'):
                        stroke_count = len(src_frame.strokes)
                        has_content = stroke_count > 0
                        print(f" Strokes no original: {stroke_count}")
                    elif hasattr(src_frame, 'nuclear_strokes'):
                        stroke_count = len(list(src_frame.nuclear_strokes))
                        has_content = stroke_count > 0
                        print(f" Nuclear strokes no original: {stroke_count}")

                    if not has_content:
                        print(f" AVISO: Frame original vazio na layer {layer.info}")
                        # Criar frame vazio
                        new_frame = gp_api.new_active_frame(layer.frames, new_frame_number)
                        helpers.set_pose_id(obj, new_frame_number, new_pose_id)
                        layers_processed += 1
                        continue

                    # USAR A FUNÇÃO copy_frame DO API_ROUTER
                    print(f" Chamando gp_api.copy_frame...")
                    new_frame = gp_api.copy_frame(layer.frames, src_frame, target_frame, new_frame_number)
                    helpers.set_pose_id(obj, new_frame_number, new_pose_id)


                    # VERIFICAR SE O NOVO FRAME TEM CONTEÚDO
                    new_has_content = False
                    if hasattr(new_frame, 'strokes'):
                        new_stroke_count = len(new_frame.strokes)
                        new_has_content = new_stroke_count > 0
                        print(f" Strokes no novo: {new_stroke_count}")
                    elif hasattr(new_frame, 'nuclear_strokes'):
                        new_stroke_count = len(list(new_frame.nuclear_strokes))
                        new_has_content = new_stroke_count > 0
                        print(f" Nuclear strokes no novo: {new_stroke_count}")

                    if new_has_content:
                        frames_duplicated += 1
                        layers_processed += 1
                        print(f" ✓ Frame duplicado com sucesso!")
                    else:
                        print(f" ✗ ERRO: Frame duplicado mas sem conteúdo!")
                        # Tentar abordagem alternativa para GPv3
                        if hasattr(src_frame, 'nuclear_strokes'):
                            print(f" Tentando abordagem alternativa para GPv3...")
                            self.duplicate_gpv3_frame_manually(layer, src_frame, new_frame_number)
                except Exception as e:
                    print(f" ERRO na layer {layer.info}: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    # Fallback: criar frame vazio
                    try:
                        new_frame = gp_api.new_active_frame(layer.frames, new_frame_number)
                        layers_processed += 1
                    except:
                        pass
            else:
                # Se não existe frame TARGET nesta layer, criar um vazio
                print(f" Layer {layer.info}: Frame {target_frame} não encontrado, criando vazio")
                try:
                    new_frame = gp_api.new_active_frame(layer.frames, new_frame_number)
                    layers_processed += 1
                except Exception as e:
                    print(f" ERRO ao criar frame vazio: {str(e)}")

        print(f"=== FIM DEBUG: {frames_duplicated} frames duplicados ===")

        # Report
        if frames_duplicated > 0:
            self.report({'INFO'}, f"Frame {target_frame} → {new_frame_number} ({frames_duplicated} layers com conteúdo)")
        else:
            self.report({'WARNING'}, f"Frame duplicado, mas nenhum conteúdo copiado. Verifique o console.")

        helpers.generate_library_preview(obj, new_frame_number)
        helpers.get_library_preview(obj, new_frame_number)
        return {'FINISHED'}

class TIME_OFFSET_OT_capture_to_library(Operator):
    """Captura o frame atual da timeline e armazena na biblioteca sem sair do frame atual"""
    bl_idname = "time_offset.capture_to_library"
    bl_label = "Capturar para Biblioteca"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and gp_api.obj_is_gp(obj)

    def execute(self, context):
        obj = context.active_object
        current_frame = context.scene.frame_current
        
        # Encontrar o frame mais negativo para criar o novo
        most_negative = 0
        for layer in obj.data.layers:
            for frame in layer.frames:
                if frame.frame_number < most_negative:
                    most_negative = frame.frame_number
        
        new_frame_number = most_negative - 1
        new_pose_id = uuid.uuid4().hex
        
        layers_processed = 0
        frames_captured = 0
        
        print(f"=== Capturando frame {current_frame} para {new_frame_number} ===")
        
        for layer in obj.data.layers:
            if gp_api.layer_locked(layer) or gp_api.layer_hidden(layer):
                continue
                
            # Verificar se existe um frame no número atual
            src_frame = None
            for frame in layer.frames:
                if frame.frame_number == current_frame:
                    src_frame = frame
                    break
            
            if src_frame and gp_api.is_frame_valid(src_frame):
                # Se existe frame, copiar seu conteúdo
                try:
                    new_frame = gp_api.copy_frame(
                        layer.frames, 
                        src_frame, 
                        current_frame,  # Este é o frame_number de origem
                        new_frame_number
                    )
                    helpers.set_pose_id(obj, new_frame_number, new_pose_id)
                    frames_captured += 1
                    print(f"  Layer {layer.info}: Frame {current_frame} copiado")
                except Exception as e:
                    print(f"  Layer {layer.info}: Erro ao copiar - {str(e)}")
                    # Fallback: criar frame vazio
                    new_frame = gp_api.new_active_frame(layer.frames, new_frame_number)
                    helpers.set_pose_id(obj, new_frame_number, new_pose_id)
            else:
                # Se não tem frame nesta layer, criar vazio
                new_frame = gp_api.new_active_frame(layer.frames, new_frame_number)
                helpers.set_pose_id(obj, new_frame_number, new_pose_id)
                print(f"  Layer {layer.info}: Frame vazio criado (sem frame em {current_frame})")
            
            layers_processed += 1
        
        # Gerar preview do novo frame
        helpers.generate_library_preview(obj, new_frame_number)
        
        # IMPORTANTE: Não mudar o offset! Permanece no frame positivo
        
        # Forçar atualização da UI
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        self.report({'INFO'}, 
                   f"Frame {current_frame} capturado → Biblioteca {new_frame_number} "
                   f"({frames_captured} layers com conteúdo)")
        
        return {'FINISHED'}

#region Old

    # EU, digo EU. Tiraria isso aqui vai na fé
    # def duplicate_gpv3_frame_manually(self, layer, src_frame, new_frame_number, obj, new_pose_id):
    #     """Tentativa manual para GPv3 quando copy_frame não funciona"""
    #     try:
    #         if hasattr(src_frame, 'drawing') and src_frame.drawing:
    #             print(f" Tentando duplicação via drawing API...")
    #             new_frame = gp_api.new_active_frame(layer.frames, new_frame_number)
    #             helpers.set_pose_id(obj, new_frame_number, new_pose_id)  # obj vem do contexto, mas como é método, use self
    #             print(f" Novo frame criado (sem cópia de drawing)")
    #             return new_frame
    #     except Exception as e:
    #         print(f" ERRO na duplicação manual: {str(e)}")
    #         return None
#endregion

class TIME_OFFSET_OT_flip_horizontal(bpy.types.Operator):
    """Flip horizontal do bone selecionado (Numpad 4) - o GP acompanha automaticamente"""
    bl_idname = "time_offset.flip_horizontal"
    bl_label = "Flip Horizontal (Bone)"
    bl_description = "Flip horizontal do bone ativo (escala X ou Y = -1 dependendo da orientação). O Grease Pencil deformado acompanha"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.mode == 'POSE' and
                context.object and context.object.type == 'ARMATURE' and
                context.active_pose_bone is not None)

    def execute(self, context):
        bone = context.active_pose_bone
        if not bone:
            self.report({'WARNING'}, "Selecione um bone em Pose Mode")
            return {'CANCELLED'}

        # Pegar vetor do bone no rest pose (head → tail)
        head_local = bone.bone.head_local
        tail_local = bone.bone.tail_local
        bone_vector = tail_local - head_local
        bone_vector.normalize()  # unitário para comparação melhor

        # Ângulos com eixos globais (dot product)
        from mathutils import Vector
        dot_x = abs(bone_vector.dot(Vector((1, 0, 0))))
        dot_y = abs(bone_vector.dot(Vector((0, 1, 0))))
        dot_z = abs(bone_vector.dot(Vector((0, 0, 1))))

        # Decidir eixo de flip: o mais alinhado com Y/Z (vertical) → flip Y; senão flip X
        if max(dot_y, dot_z) > dot_x + 0.1:  # tolerância pequena para evitar falsos positivos
            flip_axis = 'Y'  # bone mais vertical → flip Y
        else:
            flip_axis = 'X'  # horizontal padrão → flip X

        # Aplicar flip no eixo escolhido
        if flip_axis == 'X':
            bone.scale.y *= -1.0
        else:
            bone.scale.x *= -1.0

        # Keyframe no eixo flipado
        current_frame = context.scene.frame_current
        bone.keyframe_insert(data_path="scale", frame=current_frame)

        # Busca GP associado e keyframe offset (como antes)
        gp_obj = None
        armature = context.object
        for obj in context.scene.objects:
            if obj.type == 'GREASEPENCIL':
                if obj.parent == armature or any(m.type == 'ARMATURE' and m.object == armature for m in obj.modifiers):
                    gp_obj = obj
                    break

        if gp_obj:
            time_mod = helpers.get_time_offset_modifier(gp_obj)
            if time_mod:
                time_mod.keyframe_insert(data_path="offset", frame=current_frame)
                self.report({'INFO'}, f"Bone '{bone.name}' flipado ({flip_axis} invertido) + keyframes (scale + offset)")
            else:
                self.report({'INFO'}, f"Bone '{bone.name}' flipado ({flip_axis} invertido) + keyframe na escala (sem offset)")
        else:
            self.report({'INFO'}, f"Bone '{bone.name}' flipado ({flip_axis} invertido) + keyframe na escala")

        return {'FINISHED'}

class TIME_OFFSET_OT_toggle_edit_mode(Operator):
    """Ativa/desativa a visibilidade do modificador para permitir edição"""
    bl_idname = "time_offset.toggle_edit_mode"
    bl_label = "Toggle Edição"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and gp_api.obj_is_gp(obj)

    def execute(self, context):
        obj = context.active_object
        time_mod = helpers.get_time_offset_modifier(obj)
        if not time_mod:
            self.report({'WARNING'}, "Modificador TimeOffset não encontrado")
            return {'CANCELLED'}

        # Inverter estado
        new_state = not time_mod.show_in_editmode
        time_mod.show_in_editmode = new_state
        time_mod.show_viewport = new_state
        time_mod.show_render = new_state
        state_str = "ATIVADO" if new_state else "DESATIVADO"
        self.report({'INFO'}, f"Modificador {state_str} para edição")
        return {'FINISHED'}

class TIME_OFFSET_OT_navigate_previous(Operator):
    """Navega para o frame anterior na biblioteca (mais negativo)"""
    bl_idname = "time_offset.navigate_previous"
    bl_label = "Frame Anterior (Biblioteca)"
    bl_options = {'REGISTER'}

    def execute(self, context):
        obj = context.active_object
        time_mod = helpers.get_time_offset_modifier(obj)
        if not time_mod:
            self.report({'WARNING'}, "Modificador TimeOffset não encontrado")
            return {'CANCELLED'}

        # Diminuir o offset (tornar mais negativo)
        time_mod.offset -= 1
        # Garantir que não fique positivo
        if time_mod.offset >= 0:
            time_mod.offset = -1
        return {'FINISHED'}

class TIME_OFFSET_OT_navigate_next(Operator):
    """Navega para o próximo frame na biblioteca (menos negativo)"""
    bl_idname = "time_offset.navigate_next"
    bl_label = "Próximo Frame (Biblioteca)"
    bl_options = {'REGISTER'}

    def execute(self, context):
        obj = context.active_object
        time_mod = helpers.get_time_offset_modifier(obj)
        if not time_mod:
            self.report({'WARNING'}, "Modificador TimeOffset não encontrado")
            return {'CANCELLED'}

        # Aumentar o offset (tornar menos negativo)
        time_mod.offset += 1
        # Garantir que não fique positivo
        if time_mod.offset >= 0:
            time_mod.offset = -1
        return {'FINISHED'}

class TIME_OFFSET_OT_go_to_first_library_frame(Operator):
    """Vai para o primeiro frame da biblioteca (mais negativo)"""
    bl_idname = "time_offset.go_to_first_library_frame"
    bl_label = "Primeiro Frame da Biblioteca"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and gp_api.obj_is_gp(obj)

    def execute(self, context):
        obj = context.active_object
        time_mod = helpers.get_time_offset_modifier(obj)
        if not time_mod:
            self.report({'WARNING'}, "Modificador TimeOffset não encontrado")
            return {'CANCELLED'}

        # Encontrar o frame mais negativo na biblioteca
        first_negative_frame = 0
        has_negative_frames = False
        for layer in obj.data.layers:
            for frame in layer.frames:
                if frame.frame_number < first_negative_frame:
                    first_negative_frame = frame.frame_number
                    has_negative_frames = True

        if has_negative_frames:
            time_mod.offset = first_negative_frame
            self.report({'INFO'}, f"Frame {first_negative_frame} (primeiro da biblioteca)")
        else:
            time_mod.offset = -1
            self.report({'INFO'}, "Criado frame -1 (biblioteca vazia)")
        return {'FINISHED'}

class TIME_OFFSET_OT_animate_offset(Operator):
    """Ativa a animação do offset atual criando um keyframe"""
    bl_idname = "time_offset.animate_offset"
    bl_label = "Animar Offset"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and gp_api.obj_is_gp(obj)

    def execute(self, context):
        obj = context.active_object
        time_mod = helpers.get_time_offset_modifier(obj)
        if not time_mod:
            self.report({'WARNING'}, "Modificador TimeOffset não encontrado")
            return {'CANCELLED'}

        # Garantir que o objeto tenha dados de animação
        if not obj.animation_data:
            obj.animation_data_create()

        # Verificar se a propriedade offset já está animada
        is_animated = helpers.is_offset_animated(obj, time_mod)

        # Criar keyframe no frame atual
        time_mod.keyframe_insert(data_path="offset", frame=context.scene.frame_current)

        if not is_animated:
            self.report({'INFO'}, f"Animação ativada no frame {context.scene.frame_current}")
        else:
            self.report({'INFO'}, f"Keyframe adicionado no frame {context.scene.frame_current}")
        return {'FINISHED'}

class TIME_OFFSET_OT_remove_animation(Operator):
    """Remove toda a animação do offset"""
    bl_idname = "time_offset.remove_animation"
    bl_label = "Remover Animação"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and gp_api.obj_is_gp(obj)

    def execute(self, context):
        obj = context.active_object
        time_mod = helpers.get_time_offset_modifier(obj)
        if not time_mod:
            self.report({'WARNING'}, "Modificador TimeOffset não encontrado")
            return {'CANCELLED'}

        # Verificar se está animado
        if helpers.is_offset_animated(obj, time_mod):
            time_mod.keyframe_delete(data_path="offset")
            self.report({'INFO'}, "Animação removida do offset")
        else:
            self.report({'WARNING'}, "Offset não está animado")
        return {'FINISHED'}

class TIME_OFFSET_OT_next_keyframe(Operator):
    """Vai para o próximo keyframe do offset"""
    bl_idname = "time_offset.next_keyframe"
    bl_label = "Próximo Keyframe"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if not obj or not gp_api.obj_is_gp(obj):
            return False
        time_mod = helpers.get_time_offset_modifier(obj)
        return time_mod and helpers.is_offset_animated(obj, time_mod)

    def execute(self, context):
        obj = context.active_object
        time_mod = helpers.get_time_offset_modifier(obj)
        if not time_mod or not helpers.is_offset_animated(obj, time_mod):
            self.report({'WARNING'}, "Offset não está animado")
            return {'CANCELLED'}

        if not obj.animation_data or not obj.animation_data.action:
            self.report({'WARNING'}, "Nenhuma animação encontrada")
            return {'CANCELLED'}

        action = obj.animation_data.action
        channelbag = anim_utils.action_ensure_channelbag_for_slot(action, obj.animation_data.action_slot)
        if not channelbag:
            self.report({'WARNING'}, "ChannelBag não encontrado")
            return {'CANCELLED'}

        fcurve = None
        for fc in channelbag.fcurves:
            if 'offset' in fc.data_path and fc.data_path.endswith('offset'):
                fcurve = fc
                break

        if not fcurve:
            self.report({'WARNING'}, "FCurve do offset não encontrada")
            return {'CANCELLED'}

        # Encontrar próximo keyframe
        current_frame = context.scene.frame_current
        next_keyframe = None
        for keyframe in fcurve.keyframe_points:
            if keyframe.co.x > current_frame:
                if next_keyframe is None or keyframe.co.x < next_keyframe.co.x:
                    next_keyframe = keyframe

        if next_keyframe:
            context.scene.frame_current = int(next_keyframe.co.x)
            self.report({'INFO'}, f"Frame {int(next_keyframe.co.x)}")
        else:
            self.report({'INFO'}, "Último keyframe alcançado")
        return {'FINISHED'}

class TIME_OFFSET_OT_previous_keyframe(Operator):
    """Vai para o keyframe anterior do offset"""
    bl_idname = "time_offset.previous_keyframe"
    bl_label = "Keyframe Anterior"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if not obj or not gp_api.obj_is_gp(obj):
            return False
        time_mod = helpers.get_time_offset_modifier(obj)
        return time_mod and helpers.is_offset_animated(obj, time_mod)

    def execute(self, context):
        obj = context.active_object
        time_mod = helpers.get_time_offset_modifier(obj)
        if not time_mod or not helpers.is_offset_animated(obj, time_mod):
            self.report({'WARNING'}, "Offset não está animado")
            return {'CANCELLED'}

        if not obj.animation_data or not obj.animation_data.action:
            self.report({'WARNING'}, "Nenhuma animação encontrada")
            return {'CANCELLED'}

        action = obj.animation_data.action
        channelbag = anim_utils.action_ensure_channelbag_for_slot(action, obj.animation_data.action_slot)
        if not channelbag:
            self.report({'WARNING'}, "ChannelBag não encontrado")
            return {'CANCELLED'}

        fcurve = None
        for fc in channelbag.fcurves:
            if 'offset' in fc.data_path and fc.data_path.endswith('offset'):
                fcurve = fc
                break

        if not fcurve:
            self.report({'WARNING'}, "FCurve do offset não encontrada")
            return {'CANCELLED'}

        # Encontrar keyframe anterior
        current_frame = context.scene.frame_current
        prev_keyframe = None
        for keyframe in fcurve.keyframe_points:
            if keyframe.co.x < current_frame:
                if prev_keyframe is None or keyframe.co.x > prev_keyframe.co.x:
                    prev_keyframe = keyframe

        if prev_keyframe:
            context.scene.frame_current = int(prev_keyframe.co.x)
            self.report({'INFO'}, f"Frame {int(prev_keyframe.co.x)}")
        else:
            self.report({'INFO'}, "Primeiro keyframe alcançado")
        return {'FINISHED'}

class TIME_OFFSET_OT_insert_keyframe_timeline(Operator):
    """Insere keyframes na timeline (equivalente a pressionar I) - tecla F6"""
    bl_idname = "time_offset.insert_keyframe_timeline"
    bl_label = "Inserir Keyframes (Timeline)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and gp_api.obj_is_gp(obj)

    def execute(self, context):
        # Procurar uma área válida para override
        area = None
        for a in context.screen.areas:
            if a.type in {'DOPESHEET_EDITOR', 'GRAPH_EDITOR', 'TIMELINE'}:
                area = a
                break

        if not area:
            self.report({'WARNING'}, "Nenhuma Dope Sheet, Graph Editor ou Timeline aberta. Abra uma para inserir keyframes.")
            return {'CANCELLED'}

        # Criar override de contexto correto
        override = context.copy()
        override['area'] = area
        override['region'] = [r for r in area.regions if r.type == 'WINDOW'][0]
        override['space_data'] = area.spaces.active

        try:
            # Forma correta e compatível com Blender 4.2+
            with context.temp_override(**override):
                result = bpy.ops.action.keyframe_insert(type='ALL')

            if result == {'FINISHED'}:
                frame = context.scene.frame_current
                self.report({'INFO'}, f"Keyframes inseridos no frame {frame}")
            else:
                self.report({'WARNING'}, "Falha ao inserir keyframes (verifique seleção ou animação)")

            return result

        except Exception as e:
            self.report({'ERROR'}, f"Erro ao inserir keyframes: {str(e)}")
            return {'CANCELLED'}

class TIME_OFFSET_OT_remove_keyframe_timeline(Operator):
    """Remove os keyframes atualmente selecionados no Dope Sheet / Graph Editor (F7)"""
    bl_idname = "time_offset.remove_keyframe_timeline"
    bl_label = "Remover Keyframes Selecionados"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if not obj or not gp_api.obj_is_gp(obj):
            return False
        
        # Opcional: só permitir se tiver alguma animação
        if not obj.animation_data or not obj.animation_data.action:
            return False
        
        return True

    def execute(self, context):
        # Procuramos uma área de animação aberta (Dope Sheet, Graph Editor, etc.)
        anim_area = None
        for area in context.screen.areas:
            if area.type in {'DOPESHEET_EDITOR', 'GRAPH_EDITOR', 'TIMELINE'}:
                anim_area = area
                break

        if not anim_area:
            self.report({'WARNING'}, "Abra uma Dope Sheet ou Graph Editor para remover keyframes.")
            return {'CANCELLED'}

        # Criamos o override mais simples possível
        override = context.copy()
        override['area'] = anim_area
        override['space_data'] = anim_area.spaces.active
        
        # Pegamos a região WINDOW (geralmente a última ou a maior)
        for region in anim_area.regions:
            if region.type == 'WINDOW':
                override['region'] = region
                break
        else:
            self.report({'ERROR'}, "Não foi possível encontrar região válida na área de animação.")
            return {'CANCELLED'}

        try:
            # Chamamos o delete com o contexto correto
            with context.temp_override(**override):
                result = bpy.ops.action.delete()

            if result == {'FINISHED'}:
                self.report({'INFO'}, "Keyframes selecionados removidos")
            else:
                self.report({'INFO'}, "Nenhum keyframe foi removido (verifique se algo está selecionado)")

            return result

        except Exception as e:
            self.report({'ERROR'}, f"Erro ao remover keyframes: {str(e)}")
            return {'CANCELLED'}
        
class TIME_OFFSET_OT_assign_all_frames(Operator):
    """Assign automático de TODOS os frames para os vertex groups correspondentes"""
    bl_idname = "time_offset.assign_all_frames"
    bl_label = "Assign Todos Frames"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and gp_api.obj_is_gp(obj) and obj.vertex_groups
    
    def execute(self, context):
        obj = context.active_object
        total_assignments = 0
        layers_processed = 0
        
        for layer in obj.data.layers:
            if gp_api.layer_locked(layer) or gp_api.layer_hidden(layer):
                continue
                
            layer_name = self.normalize_name(layer.info)
            matching_groups = self.find_matching_groups(obj, layer_name)
            
            if not matching_groups:
                continue
            
            for frame in layer.frames:
                for vgroup in matching_groups:
                    if self.assign_frame_to_group(obj, frame, vgroup):
                        total_assignments += 1
            
            layers_processed += 1
        
        self.report({'INFO'}, 
                   f"Assign completo: {total_assignments} atribuições em {layers_processed} layers")
        return {'FINISHED'}
    
    def normalize_name(self, name):
        return name.lower().strip().replace(' ', '_')
    
    def find_matching_groups(self, obj, layer_name):
        matching = []
        for vgroup in obj.vertex_groups:
            vgroup_name = self.normalize_name(vgroup.name)
            if layer_name == vgroup_name or vgroup_name in layer_name:
                matching.append(vgroup)
        return matching
    
    def assign_frame_to_group(self, obj, frame, vgroup):
        try:
            if hasattr(frame, 'strokes'):
                for stroke in frame.strokes:
                    stroke.vertex_groups.append(vgroup)
            elif hasattr(frame, 'nuclear_strokes'):
                for stroke in frame.nuclear_strokes:
                    # GPv3 - implementação específica
                    pass
            return True
        except:
            return False

class TIME_OFFSET_PT_main_panel(Panel):
    """Painel principal do TimeOffset Tool"""
    bl_label = "TimeOffset Tool"
    bl_idname = "TIME_OFFSET_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "TimeOffset"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and gp_api.obj_is_gp(obj)

    def draw(self, context):
        layout = self.layout
        obj = context.active_object

        if not obj or not gp_api.obj_is_gp(obj):
            layout.label(text="Selecione um objeto Grease Pencil", icon='ERROR')
            return

        time_mod = helpers.get_time_offset_modifier(obj)

        if not time_mod:
                box = layout.box()
                box.alert = True
                box.label(text="Modificador TimeOffset não encontrado!", icon='ERROR')
                box.label(text="Adicione o modificador para usar as funções completas")
                box.operator("object.gpencil_modifier_add", text="Adicionar TimeOffset").type = 'GP_TIME'
                return

        library_frame = time_mod.offset

        layout.separator()
        preview_key = helpers.get_library_preview(obj, library_frame)
        pcoll = helpers.get_preview_collection()    

        if preview_key and preview_key in pcoll:
            preview_box = layout.box()
            preview_box.label(text="Preview do Frame", icon='IMAGE_DATA')
            preview_box.template_icon(
                icon_value=pcoll[preview_key].icon_id,
                scale=6
            )
        else:
            preview_box = layout.box()
            preview_box.label(text="Preview indisponível", icon='IMAGE_DATA')
            print(helpers.get_library_preview)
            preview_box.label(text=f"Frame {library_frame}")


        # Informações do modificador
        box = layout.box()
        box.label(text="Biblioteca de Frames", icon='LIBRARY_DATA_DIRECT')

        # Status da biblioteca
        has_library_frames = helpers.has_negative_frames(obj)
        if has_library_frames:
            # Encontrar range da biblioteca
            min_frame, max_frame = helpers.get_library_frame_range(obj)
            box.label(text=f"Biblioteca: {min_frame} a {max_frame}", icon='BOOKMARKS')
        else:
            box.label(text="Biblioteca vazia", icon='INFO')

        box.prop(time_mod, "offset", text="Frame da Biblioteca")

        # Status da animação
        is_animated = helpers.is_offset_animated(obj, time_mod)
        anim_icon = 'ANIM' if is_animated else 'KEYFRAME'
        box.label(text=f"Animado: {'SIM' if is_animated else 'NÃO'}", icon=anim_icon)

        # Informação sobre o frame atual da biblioteca
        box.separator()
        box.label(text=f"Exibindo Frame da Biblioteca: {library_frame}", icon='RESTRICT_VIEW_OFF')

        # Controles de edição
        row = layout.row()
        row.prop(time_mod, "show_in_editmode", text="Permitir Edição", toggle=True)
        row.prop(time_mod, "show_viewport", text="", toggle=True)
        row.prop(time_mod, "show_render", text="", toggle=True)

        col = layout.column(align=True)
        col.operator("time_offset.create_clean_frame", icon='ADD')
        col.operator("time_offset.duplicate_current_frame",
                    text=f"Duplicar Frame {library_frame}",
                    icon='DUPLICATE')

        # NOVO BOTÃO: Capturar frame atual
        row = col.row(align=True)
        row.operator("time_offset.capture_to_library", 
                    text=f"Capturar Frame {context.scene.frame_current}",
                    icon='IMPORT')
        row.prop(time_mod, "show_viewport", text="", icon='RESTRICT_VIEW_OFF')

        col.operator("time_offset.update_current_preview", 
                    text="Atualizar Preview Atual", 
                    icon='FILE_REFRESH')

        # Botões de ação de frames
        col = layout.column(align=True)
        col.operator("time_offset.create_clean_frame", icon='ADD')
        col.operator("time_offset.duplicate_current_frame",
                     text=f"Duplicar Frame {library_frame}",
                     icon='DUPLICATE')
        col.operator("time_offset.update_current_preview", 
                     text="Atualizar Preview Atual", 
                     icon='FILE_REFRESH')  # ícone de refresh/atualizar
        # Nova feature: Flip Horizontal
        col.operator("time_offset.flip_horizontal", text="Flip Horizontal", icon='UV_SYNC_SELECT')  # Icon para flip

        col = layout.column(align=True)
        col.operator("time_offset.assign_all_frames", 
                    text="Assign Todos Frames", 
                    icon='GROUP_VERTEX')
        
        # Navegação na biblioteca
        col = layout.column(align=True)
        row = col.row(align=True)
        row.operator("time_offset.navigate_previous", text="Anterior", icon='TRIA_LEFT')
        row.operator("time_offset.navigate_next", text="Próximo", icon='TRIA_RIGHT')

        # Botão para ir ao primeiro frame da biblioteca
        col.operator("time_offset.go_to_first_library_frame", text="Primeiro da Biblioteca", icon='REW')

        # Seção de animação
        layout.separator()
        layout.label(text="Animação do Offset", icon='ANIM')
        col = layout.column(align=True)
        if is_animated:
            # Já está animado - mostrar controles de animação
            row = col.row(align=True)
            row.operator("time_offset.animate_offset", text="Add Keyframe", icon='KEYFRAME')
            row.operator("time_offset.remove_animation", text="", icon='X')

            # Navegação entre keyframes
            row = col.row(align=True)
            row.operator("time_offset.previous_keyframe", text="", icon='PREV_KEYFRAME')
            row.operator("time_offset.next_keyframe", text="", icon='NEXT_KEYFRAME')
        else:
            # Não está animado - botão para iniciar animação
            col.operator("time_offset.animate_offset", text="Iniciar Animação", icon='KEYFRAME_HLT')

        # Status atual da timeline
        layout.separator()
        current_frame = context.scene.frame_current
        # Calcular frame máximo positivo (timeline normal)
        max_positive_frame = helpers.get_max_positive_frame_number(obj)
        layout.label(text=f"Timeline: Frame {current_frame}", icon='TIME')
        layout.label(text=f"Frames positivos: 0 a {max_positive_frame}", icon='PMARKER')

class TIME_OFFSET_PT_missing_modifier(Panel):
    """Painel de aviso quando não há modificador TimeOffset"""
    bl_label = "TimeOffset Tool"
    bl_idname = "TIME_OFFSET_PT_missing_modifier"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "TimeOffset"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if not obj or not gp_api.obj_is_gp(obj):
            return False
        return helpers.get_time_offset_modifier(obj) is None

    def draw(self, context):
        layout = self.layout
        layout.label(text="TimeOffset não encontrado!", icon='ERROR')
        layout.label(text="Adicione manualmente o modificador")
        layout.separator()
        layout.operator("object.gpencil_modifier_add", text="Adicionar TimeOffset").type = 'GP_TIME'

class TIME_OFFSET_OT_update_current_preview(Operator):
    """Atualiza/gera o preview apenas do frame da biblioteca atual selecionado"""
    bl_idname = "time_offset.update_current_preview"
    bl_label = "Atualizar Preview Atual"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        time_mod = helpers.get_time_offset_modifier(obj) if obj else None
        return obj and gp_api.obj_is_gp(obj) and time_mod and time_mod.offset < 0

    def execute(self, context):
        obj = context.active_object
        time_mod = helpers.get_time_offset_modifier(obj)

        current_library_frame = time_mod.offset
        if current_library_frame >= 0:
            self.report({'WARNING'}, "Selecione um frame negativo da biblioteca")
            return {'CANCELLED'}

        pose_id = helpers.get_pose_id(obj, current_library_frame)
        if not pose_id:
            self.report({'WARNING'}, f"Frame {current_library_frame} sem pose_id. Crie/duplique o frame primeiro.")
            return {'CANCELLED'}

        # Caminho do arquivo
        preview_dir = os.path.join(bpy.app.tempdir, "timeoffset_previews", obj.name)
        filepath = os.path.join(preview_dir, f"{pose_id}.png")

        # Remove arquivo antigo para forçar recriação
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                print(f"DEBUG: Arquivo antigo removido: {filepath}")
            except Exception as e:
                print(f"DEBUG: Erro ao remover arquivo antigo: {e}")

        # Gera o novo preview (vai criar o PNG novo)
        helpers.generate_library_preview(obj, current_library_frame)

        # Força recarregamento na coleção de previews
        pcoll = helpers.get_preview_collection()
        key = f"{obj.name}_{pose_id}"

        # Remove a entrada antiga da coleção (importante!)
        if key in pcoll:
            pcoll.unload(key)  # Descarrega da memória
            print(f"DEBUG: Imagem antiga descarregada da coleção: {key}")

        # Recarrega o arquivo novo com a mesma chave
        try:
            pcoll.load(key, filepath, 'IMAGE')
            print(f"DEBUG: Nova imagem carregada: {key}")
        except Exception as e:
            print(f"DEBUG: Erro ao recarregar preview: {e}")
            self.report({'ERROR'}, "Falha ao recarregar a imagem no painel")
            return {'CANCELLED'}

        # Invalidar tudo para garantir refresh do UI
        helpers.invalidate_library_previews()

        # Força redraw do painel (muito útil!)
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

        self.report({'INFO'}, f"Preview atualizado com sucesso para frame {current_library_frame}")
        return {'FINISHED'}

# Graças a deus é pouca classe
classes = (
    TIME_OFFSET_OT_create_clean_frame,
    TIME_OFFSET_OT_duplicate_current_frame,
    TIME_OFFSET_OT_capture_to_library,
    TIME_OFFSET_OT_toggle_edit_mode,
    TIME_OFFSET_OT_navigate_previous,
    TIME_OFFSET_OT_navigate_next,
    TIME_OFFSET_OT_go_to_first_library_frame,
    TIME_OFFSET_OT_animate_offset,
    TIME_OFFSET_OT_remove_animation,
    TIME_OFFSET_OT_next_keyframe,
    TIME_OFFSET_OT_previous_keyframe,
    TIME_OFFSET_OT_insert_keyframe_timeline,
    TIME_OFFSET_OT_remove_keyframe_timeline,
    TIME_OFFSET_OT_assign_all_frames,
    TIME_OFFSET_OT_flip_horizontal,
    TIME_OFFSET_PT_main_panel,
    TIME_OFFSET_PT_missing_modifier,
    TIME_OFFSET_OT_update_current_preview,
)


#lembrar de diminuir os comentarios desnecessarios depois, tipo esse
# E PQP 500+ linhas só de operators, que isso bixo

import bpy
from bpy.types import Operator, Panel
from mathutils import Vector
from .. import api_route as gp_api
import bpy_extras.anim_utils as anim_utils
from ..core import helpers
import os
import uuid

def get_monitor_state():
    return getattr(bpy.types.Scene, 'timeoffset_monitor_active', False)

def set_monitor_state(value):
    bpy.types.Scene.timeoffset_monitor_active = value

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

class TIME_OFFSET_OT_duplicate_current_positive(Operator):
    """Duplica o frame atual da timeline, criando uma cópia para edição no mesmo frame"""
    bl_idname = "time_offset.duplicate_current_positive"
    bl_label = "Duplicar Frame Atual"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and gp_api.obj_is_gp(obj)

    def execute(self, context):
        obj = context.active_object
        current_frame = context.scene.frame_current
        
        print(f"\n=== Duplicando frame {current_frame} para edição local ===")
        
        layers_processed = 0
        frames_duplicated = 0
        
        for layer in obj.data.layers:
            if gp_api.layer_locked(layer) or gp_api.layer_hidden(layer):
                print(f"  Layer {layer.info}: SKIPPED (locked/hidden)")
                continue
            
            # Encontrar o frame atual
            src_frame = None
            for frame in layer.frames:
                if frame.frame_number == current_frame:
                    src_frame = frame
                    break
            
            if src_frame and gp_api.is_frame_valid(src_frame):
                # Verificar se tem conteúdo
                if hasattr(src_frame, 'strokes'):  # GPv2
                    stroke_count = len(src_frame.strokes)
                    print(f"  Layer {layer.info}: GPv2 com {stroke_count} strokes")
                    
                    if stroke_count > 0:
                        # IMPORTANTE: NÃO limpar o frame! Queremos DUPLICAR, não substituir
                        # Vamos copiar os strokes existentes para o MESMO frame
                        
                        # Criar uma lista dos strokes existentes para não modificar durante iteração
                        existing_strokes = list(src_frame.strokes)
                        
                        for src_stroke in existing_strokes:
                            # Copiar cada stroke
                            new_stroke = src_frame.strokes.copy(src_stroke)
                            print(f"    Stroke copiado")
                        
                        frames_duplicated += 1
                        print(f"  Layer {layer.info}: {stroke_count} strokes duplicados (agora {len(src_frame.strokes)} total)")
                    
                elif hasattr(src_frame, 'nuclear_strokes'):  # GPv3
                    stroke_count = len(list(src_frame.nuclear_strokes))
                    print(f"  Layer {layer.info}: GPv3 com {stroke_count} strokes")
                    
                    if stroke_count > 0 and hasattr(src_frame, 'drawing'):
                        drawing = src_frame.drawing
                        existing_strokes = list(drawing.strokes)
                        
                        for src_stroke in existing_strokes:
                            # Criar novo stroke
                            new_stroke = drawing.strokes.new()
                            # Copiar pontos
                            for src_point in src_stroke.points:
                                new_point = new_stroke.points.new()
                                new_point.position = src_point.position.copy()
                            print(f"    Stroke copiado")
                        
                        frames_duplicated += 1
                        print(f"  Layer {layer.info}: {stroke_count} strokes duplicados")
            else:
                print(f"  Layer {layer.info}: Frame {current_frame} não encontrado")
            
            layers_processed += 1
        
        print(f"=== Duplicação concluída: {frames_duplicated} layers processadas ===\n")
        
        self.report({'INFO'}, 
                   f"Frame {current_frame} duplicado para edição local ({frames_duplicated} layers)")
        
        # Forçar atualização da viewport
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        return {'FINISHED'}

class TIME_OFFSET_OT_bring_to_timeline(Operator):
    """Traz o frame atual da biblioteca para a timeline para edição local"""
    bl_idname = "time_offset.bring_to_timeline"
    bl_label = "Trazer Frame para Timeline"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        time_mod = helpers.get_time_offset_modifier(obj) if obj else None
        return obj and gp_api.obj_is_gp(obj) and time_mod and time_mod.offset < 0

    def execute(self, context):
        obj = context.active_object
        time_mod = helpers.get_time_offset_modifier(obj)
        
        library_frame = time_mod.offset
        timeline_frame = context.scene.frame_current
        
        print(f"\n=== Trazendo biblioteca {library_frame} → timeline {timeline_frame} ===")
        
        layers_processed = 0
        frames_copied = 0
        
        for layer in obj.data.layers:
            if gp_api.layer_locked(layer) or gp_api.layer_hidden(layer):
                continue
            
            # Encontrar frame origem na biblioteca
            src_frame = None
            for frame in layer.frames:
                if frame.frame_number == library_frame:
                    src_frame = frame
                    break
            
            if not src_frame:
                print(f"  Layer {layer.info}: Frame {library_frame} não encontrado")
                continue
            
            # Verificar se tem strokes via nuclear_strokes
            if not hasattr(src_frame, 'nuclear_strokes'):
                print(f"  Layer {layer.info}: Frame sem nuclear_strokes")
                continue
            
            # Contar strokes
            stroke_count = 0
            src_strokes = []
            for stroke in src_frame.nuclear_strokes:
                src_strokes.append(stroke)
                stroke_count += 1
            
            print(f"  Layer {layer.info}: {stroke_count} strokes encontrados")
            
            if stroke_count == 0:
                continue
            
            # Verificar frame destino na timeline
            dst_frame = None
            for frame in layer.frames:
                if frame.frame_number == timeline_frame:
                    dst_frame = frame
                    break
            
            if dst_frame:
                # Limpar frame existente
                if hasattr(dst_frame, 'nuclear_strokes'):
                    strokes_to_remove = []
                    for stroke in dst_frame.nuclear_strokes:
                        strokes_to_remove.append(stroke)
                    
                    for stroke in strokes_to_remove:
                        dst_frame.nuclear_strokes.remove(stroke)
                    
                    print(f"    Frame {timeline_frame} existente limpo")
            else:
                # Criar novo frame
                dst_frame = gp_api.new_active_frame(layer.frames, timeline_frame)
                print(f"    Novo frame {timeline_frame} criado")
            
            # Copiar strokes
            if dst_frame and hasattr(dst_frame, 'nuclear_strokes'):
                for src_stroke in src_strokes:
                    # Criar novo stroke
                    new_stroke = dst_frame.nuclear_strokes.new()
                    
                    # Copiar pontos - usando add() em vez de new()
                    if hasattr(src_stroke, 'points'):
                        # Contar pontos para adicionar
                        point_count = 0
                        src_points = []
                        for src_point in src_stroke.points:
                            src_points.append(src_point)
                            point_count += 1
                        
                        if point_count > 0:
                            # Adicionar pontos de uma vez
                            new_stroke.points.add(point_count)
                            
                            # Copiar dados dos pontos
                            for i, src_point in enumerate(src_points):
                                if hasattr(src_point, 'co'):
                                    new_stroke.points[i].co = src_point.co.copy()
                                if hasattr(src_point, 'pressure'):
                                    new_stroke.points[i].pressure = src_point.pressure
                                if hasattr(src_point, 'strength'):
                                    new_stroke.points[i].strength = src_point.strength
                
                frames_copied += 1
                print(f"    {stroke_count} strokes copiados")
            
            layers_processed += 1
        
        # Desligar modificador
        if time_mod:
            time_mod.show_viewport = False
            print(f"  Modificador desligado para edição local")
        
        print(f"=== Concluído: {frames_copied} layers processadas ===\n")
        
        self.report({'INFO'}, 
                   f"Frame {library_frame} da biblioteca copiado para timeline {timeline_frame}")
        
        # Forçar atualização
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        return {'FINISHED'}

class TIME_OFFSET_OT_send_to_library(Operator):
    """Envia o frame atual da timeline para a biblioteca como um novo frame"""
    bl_idname = "time_offset.send_to_library"
    bl_label = "Enviar para Biblioteca"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and gp_api.obj_is_gp(obj)

    def execute(self, context):
        obj = context.active_object
        timeline_frame = context.scene.frame_current
        
        # Encontrar o frame MAIS NEGATIVO (menor número) para criar o NOVO
        # Inicializar com 0 (nenhum frame negativo)
        most_negative = 0
        
        # Primeiro, listar todos os frames negativos existentes
        negative_frames = []
        for layer in obj.data.layers:
            for frame in layer.frames:
                if frame.frame_number < 0:
                    negative_frames.append(frame.frame_number)
                    # Atualizar o mais negativo
                    if frame.frame_number < most_negative:
                        most_negative = frame.frame_number
        
        print(f"  Frames negativos existentes: {sorted(set(negative_frames))}")
        print(f"  Frame mais negativo atual: {most_negative}")
        
        # O novo frame será 1 a mais negativo que o mais negativo atual
        # Se most_negative for 0 (não há frames negativos), começa com -1
        if most_negative == 0:
            new_library_frame = -1
        else:
            new_library_frame = most_negative - 1
            
        new_pose_id = uuid.uuid4().hex
        
        print(f"  Novo frame da biblioteca: {new_library_frame}")
        print(f"  Novo pose_id: {new_pose_id}")
        print(f"\n=== Enviando timeline {timeline_frame} → biblioteca {new_library_frame} ===")
        
        layers_processed = 0
        frames_sent = 0
        
        for layer in obj.data.layers:
            if gp_api.layer_locked(layer) or gp_api.layer_hidden(layer):
                print(f"  Layer {layer.info}: ignorada (locked/hidden)")
                continue
            
            # Encontrar frame origem na timeline
            src_frame = None
            for frame in layer.frames:
                if frame.frame_number == timeline_frame:
                    src_frame = frame
                    break
            
            if not src_frame:
                print(f"  Layer {layer.info}: Frame {timeline_frame} não encontrado")
                continue
            
            # Verificar strokes via nuclear_strokes
            if not hasattr(src_frame, 'nuclear_strokes'):
                print(f"  Layer {layer.info}: sem nuclear_strokes")
                continue
            
            # Contar strokes
            stroke_count = 0
            src_strokes = []
            for stroke in src_frame.nuclear_strokes:
                src_strokes.append(stroke)
                stroke_count += 1
            
            print(f"  Layer {layer.info}: {stroke_count} strokes encontrados")
            
            if stroke_count == 0:
                continue
            
            # VERIFICAR SE O FRAME DESTINO JÁ EXISTE
            frame_exists = False
            for frame in layer.frames:
                if frame.frame_number == new_library_frame:
                    frame_exists = True
                    print(f"    AVISO: Frame {new_library_frame} já existe nesta layer!")
                    break
            
            if frame_exists:
                print(f"    Pulando layer {layer.info} - frame já existe")
                continue
            
            # Criar novo frame na biblioteca
            print(f"    Criando novo frame {new_library_frame}...")
            new_frame = gp_api.new_active_frame(layer.frames, new_library_frame)
            
            # Copiar strokes
            if new_frame and hasattr(new_frame, 'nuclear_strokes'):
                for src_stroke in src_strokes:
                    new_stroke = new_frame.nuclear_strokes.new()
                    
                    if hasattr(src_stroke, 'points'):
                        # Contar pontos
                        point_count = 0
                        src_points = []
                        for src_point in src_stroke.points:
                            src_points.append(src_point)
                            point_count += 1
                        
                        if point_count > 0:
                            # Adicionar pontos de uma vez
                            new_stroke.points.add(point_count)
                            
                            # Copiar dados
                            for i, src_point in enumerate(src_points):
                                if hasattr(src_point, 'co'):
                                    new_stroke.points[i].co = src_point.co.copy()
                                if hasattr(src_point, 'pressure'):
                                    new_stroke.points[i].pressure = src_point.pressure
                                if hasattr(src_point, 'strength'):
                                    new_stroke.points[i].strength = src_point.strength
                
                helpers.set_pose_id(obj, new_library_frame, new_pose_id)
                frames_sent += 1
                print(f"    {stroke_count} strokes enviados para biblioteca")
            
            layers_processed += 1
        
        # Gerar preview apenas se enviou algo
        if frames_sent > 0:
            print(f"\n  Gerando preview para frame {new_library_frame}...")
            helpers.generate_library_preview(obj, new_library_frame)
        
        print(f"\n=== RESUMO ===")
        print(f"  Layers processadas: {layers_processed}")
        print(f"  Frames enviados: {frames_sent}")
        print(f"  Novo frame da biblioteca: {new_library_frame}")
        
        # Listar frames negativos atualizados
        updated_negatives = []
        for layer in obj.data.layers:
            for frame in layer.frames:
                if frame.frame_number < 0:
                    updated_negatives.append(frame.frame_number)
        print(f"  Frames negativos agora: {sorted(set(updated_negatives))}")
        print("=== CONCLUÍDO ===\n")
        
        self.report({'INFO'}, 
                   f"Timeline {timeline_frame} enviado para biblioteca {new_library_frame}")
        
        # Forçar atualização
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        return {'FINISHED'}

class TIME_OFFSET_OT_capture_edited_to_library(Operator):
    """Envia a versão editada do frame atual para a biblioteca"""
    bl_idname = "time_offset.capture_edited_to_library"
    bl_label = "Enviar Edição para Biblioteca"
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
        frames_with_content = 0
        
        print(f"=== Enviando edição do frame {current_frame} para biblioteca {new_frame_number} ===")
        
        for layer in obj.data.layers:
            if gp_api.layer_locked(layer) or gp_api.layer_hidden(layer):
                continue
            
            # Encontrar o frame atual (editado)
            src_frame = None
            for frame in layer.frames:
                if frame.frame_number == current_frame:
                    src_frame = frame
                    break
            
            if src_frame:
                # Verificar se tem conteúdo
                has_content = False
                stroke_count = 0
                
                if hasattr(src_frame, 'strokes'):  # GPv2
                    stroke_count = len(src_frame.strokes)
                    has_content = stroke_count > 0
                    print(f"  Layer {layer.info}: GPv2 com {stroke_count} strokes")
                elif hasattr(src_frame, 'nuclear_strokes'):  # GPv3
                    stroke_count = len(list(src_frame.nuclear_strokes))
                    has_content = stroke_count > 0
                    print(f"  Layer {layer.info}: GPv3 com {stroke_count} strokes")
                
                if has_content:
                    frames_with_content += 1
                    
                    # PARA GPv2 - método direto
                    if hasattr(src_frame, 'strokes'):
                        try:
                            # Criar novo frame
                            new_frame = gp_api.new_active_frame(layer.frames, new_frame_number)
                            
                            # Copiar strokes manualmente
                            for src_stroke in src_frame.strokes:
                                new_stroke = new_frame.strokes.copy(src_stroke)
                            
                            helpers.set_pose_id(obj, new_frame_number, new_pose_id)
                            frames_captured += 1
                            print(f"  Layer {layer.info}: {stroke_count} strokes copiados manualmente")
                            
                        except Exception as e:
                            print(f"  Layer {layer.info}: Erro na cópia manual - {str(e)}")
                    
                    # PARA GPv3 - via nuclear_strokes
                    elif hasattr(src_frame, 'nuclear_strokes'):
                        try:
                            new_frame = gp_api.new_active_frame(layer.frames, new_frame_number)
                            
                            # Acessar o drawing
                            if hasattr(src_frame, 'drawing') and src_frame.drawing:
                                src_drawing = src_frame.drawing
                                dst_drawing = new_frame.drawing
                                
                                # Copiar strokes
                                for src_stroke in src_drawing.strokes:
                                    new_stroke = dst_drawing.strokes.new()
                                    # Copiar pontos
                                    for src_point in src_stroke.points:
                                        new_point = new_stroke.points.new()
                                        new_point.position = src_point.position.copy()
                            
                            helpers.set_pose_id(obj, new_frame_number, new_pose_id)
                            frames_captured += 1
                            print(f"  Layer {layer.info}: GPv3 copiado via drawing")
                            
                        except Exception as e:
                            print(f"  Layer {layer.info}: Erro GPv3 - {str(e)}")
                else:
                    # Frame sem conteúdo, criar vazio
                    new_frame = gp_api.new_active_frame(layer.frames, new_frame_number)
                    helpers.set_pose_id(obj, new_frame_number, new_pose_id)
                    print(f"  Layer {layer.info}: Frame vazio criado")
            else:
                # Não tem frame na layer, criar vazio
                new_frame = gp_api.new_active_frame(layer.frames, new_frame_number)
                helpers.set_pose_id(obj, new_frame_number, new_pose_id)
                print(f"  Layer {layer.info}: Frame vazio criado (sem frame origem)")
            
            layers_processed += 1
        
        # Gerar preview
        print(f"=== Gerando preview para frame {new_frame_number} ===")
        helpers.generate_library_preview(obj, new_frame_number)
        
        # Verificar se o preview foi criado
        preview_key = helpers.get_library_preview(obj, new_frame_number)
        if preview_key:
            print(f"✓ Preview gerado com sucesso")
        else:
            print(f"✗ Preview não foi gerado")
        
        self.report({'INFO'}, 
                   f"Edição do frame {current_frame} enviada para biblioteca {new_frame_number} "
                   f"({frames_captured} layers com conteúdo de {frames_with_content} layers com conteúdo original)")
        
        # Forçar atualização da UI
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
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

"""Operador pq a May pediu"""
class TIME_OFFSET_OT_flip_horizontal_object(Operator):
    """Flip horizontal do objeto selecionado (Numpad 4) - aplica escala -1 no eixo adequado"""
    bl_idname = "time_offset.flip_horizontal_object"
    bl_label = "Flip Horizontal (Object)"
    bl_description = "Flip horizontal do objeto ativo (escala X ou Y = -1 baseado na orientação)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.mode == 'OBJECT' and
                context.object is not None)

    def execute(self, context):
        obj = context.object
        
        if not obj:
            self.report({'WARNING'}, "Selecione um objeto")
            return {'CANCELLED'}
        
        # Pegar a matriz do objeto no espaço global
        matrix = obj.matrix_world
        
        # Extrair vetores de direção dos eixos locais
        x_axis = matrix.to_3x3() @ Vector((1, 0, 0))
        y_axis = matrix.to_3x3() @ Vector((0, 1, 0))
        z_axis = matrix.to_3x3() @ Vector((0, 0, 1))
        
        # Normalizar
        x_axis.normalize()
        y_axis.normalize()
        z_axis.normalize()
        
        # Calcular quanto cada eixo local aponta para a direita (X global)
        # Queremos o eixo que tem o MAIOR componente no X global
        right_alignment = {
            'X': abs(x_axis.x),  # Quanto do eixo X local aponta para X global
            'Y': abs(y_axis.x),  # Quanto do eixo Y local aponta para X global
            'Z': abs(z_axis.x)   # Quanto do eixo Z local aponta para X global
        }
        
        # Escolher o eixo mais alinhado com a direita (X global)
        flip_axis = max(right_alignment, key=right_alignment.get)
        
        print(f"  Alinhamentos: X={right_alignment['X']:.2f}, Y={right_alignment['Y']:.2f}, Z={right_alignment['Z']:.2f}")
        print(f"  Eixo escolhido para flip: {flip_axis}")
        
        # Aplicar flip no eixo escolhido
        if flip_axis == 'X':
            obj.scale.x *= -1.0
        elif flip_axis == 'Y':
            obj.scale.y *= -1.0
        else:  # 'Z'
            obj.scale.z *= -1.0
        
        # Keyframe na escala
        current_frame = context.scene.frame_current
        obj.keyframe_insert(data_path="scale", frame=current_frame)
        
        # Se for um Grease Pencil, também keyframe no offset (se existir)
        if gp_api.obj_is_gp(obj):
            time_mod = helpers.get_time_offset_modifier(obj)
            if time_mod:
                time_mod.keyframe_insert(data_path="offset", frame=current_frame)
                self.report({'INFO'}, f"Objeto '{obj.name}' flipado (eixo {flip_axis}) + keyframes (scale + offset)")
            else:
                self.report({'INFO'}, f"Objeto '{obj.name}' flipado (eixo {flip_axis}) + keyframe na escala")
        else:
            self.report({'INFO'}, f"Objeto '{obj.name}' flipado (eixo {flip_axis}) + keyframe na escala")
        
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

class TIME_OFFSET_OT_monitor_keyframes(Operator):
    """Monitora substituição perigosa de keyframes"""
    bl_idname = "time_offset.monitor_keyframes"
    bl_label = "Monitor Keyframes"
    bl_description = "Detecta substituição de frames que podem causar crash"
    bl_options = {'REGISTER'}

    _timer = None
    _monitoring = False
    _last_frame_content = {}
    _last_warning_frame = 0  # Frame do último aviso
    _warning_cooldown = 0    # Contador de cooldown
    _operation_in_progress = False

    def _get_frame_content_map(self, obj):
        """Mapeia quais frames têm conteúdo por layer"""
        content_map = {}
        
        if not obj or not obj.data:
            return content_map
        
        try:
            for layer in obj.data.layers:
                layer_name = layer.info if hasattr(layer, 'info') else layer.name
                frames_with_content = set()
                
                for frame in layer.frames:
                    frame_num = frame.frame_number
                    has_content = False
                    
                    try:
                        if hasattr(frame, 'nuclear_strokes'):
                            stroke_count = 0
                            for _ in frame.nuclear_strokes:
                                stroke_count += 1
                                if stroke_count > 5:  # Se tiver mais de 5 strokes, considerado conteúdo pesado
                                    break
                            has_content = stroke_count > 0
                        elif hasattr(frame, 'strokes'):
                            has_content = len(frame.strokes) > 0
                    except:
                        pass
                    
                    if has_content:
                        frames_with_content.add(frame_num)
                
                content_map[layer_name] = frames_with_content
                
        except Exception as e:
            print(f"DEBUG: erro no mapeamento - {e}")
            
        return content_map

    def _detect_dangerous_operation(self, old_map, new_map):
        """Detecta substituição perigosa de frames com conteúdo"""
        warnings = []
        
        try:
            for layer_name, new_frames in new_map.items():
                old_frames = old_map.get(layer_name, set())
                
                # Frames removidos (perderam conteúdo)
                removed = old_frames - new_frames
                
                # Frames adicionados (ganharam conteúdo)
                added = new_frames - old_frames
                
                # Detectar movimento de conteúdo (remove um, adiciona outro)
                if removed and added:
                    warnings.append({
                        'layer': layer_name,
                        'removed': list(removed),
                        'added': list(added),
                        'type': 'movement'
                    })
                
                # Detectar sobrescrita (frame existente perdeu e ganhou conteúdo)
                for frame_num in old_frames.intersection(new_frames):
                    warnings.append({
                        'layer': layer_name,
                        'frame': frame_num,
                        'type': 'overwrite'
                    })
                        
        except Exception as e:
            print(f"DEBUG: erro na detecção - {e}")
            
        return warnings

    def _show_warning(self, warnings, current_frame):
        """Mostra aviso apenas uma vez por operação"""
        # Cooldown: só avisa a cada 30 frames ou se passaram 2 segundos
        if self._warning_cooldown > 0:
            self._warning_cooldown -= 1
            return
            
        if self._last_warning_frame == current_frame:
            return  # Já avisou neste frame
            
        self._last_warning_frame = current_frame
        self._warning_cooldown = 10  # Não avisar novamente por 10 ciclos (~3 segundos)
        
        # Construir mensagem
        msg = f"⚠️ OPERAÇÃO PERIGOSA DETECTADA!\n\n"
        msg += f"Movimentação de frames com conteúdo pode causar CRASH!\n\n"
        
        for w in warnings[:3]:
            if w['type'] == 'movement':
                removed_str = ', '.join(str(f) for f in w['removed'][:3])
                added_str = ', '.join(str(f) for f in w['added'][:3])
                msg += f"• Layer '{w['layer']}': {removed_str} → {added_str}\n"
            elif w['type'] == 'overwrite':
                msg += f"• Layer '{w['layer']}': Frame {w['frame']} foi sobrescrito\n"
        
        if len(warnings) > 3:
            msg += f"\n• e mais {len(warnings)-3} alterações\n"
        
        msg += f"\n💡 RECOMENDAÇÃO:\n"
        msg += f"• Desfaça a operação (Ctrl+Z) para evitar crash\n"
        msg += f"• Use os operadores do addon para mover/duplicar frames\n"
        msg += f"• Desative o monitor se precisar fazer várias operações"
        
        def draw(self, context):
            layout = self.layout
            for line in msg.split('\n'):
                if line.startswith('⚠️'):
                    layout.label(text=line, icon='ERROR')
                elif line.startswith('💡'):
                    layout.label(text=line, icon='INFO')
                elif line == '':
                    layout.separator()
                else:
                    layout.label(text=line)
        
        try:
            bpy.context.window_manager.popup_menu(draw, title="⚠️ ALERTA DE SEGURANÇA", icon='ERROR')
            self.report({'WARNING'}, "Operação perigosa detectada! Desfaça para prevenir crash.")
        except:
            self.report({'WARNING'}, "⚠️ Operação perigosa! Desfaça imediatamente (Ctrl+Z)")

    def modal(self, context, event):
        if not self._monitoring:
            return {'FINISHED'}
        
        if event.type == 'TIMER':
            obj = context.active_object
            if not obj or not gp_api.obj_is_gp(obj):
                return {'PASS_THROUGH'}
            
            try:
                current_map = self._get_frame_content_map(obj)
                current_frame = context.scene.frame_current
                
                # Detectar mudanças perigosas
                if self._last_frame_content:
                    # Verificar se houve mudança significativa
                    if current_map != self._last_frame_content:
                        warnings = self._detect_dangerous_operation(self._last_frame_content, current_map)
                        
                        if warnings and not self._operation_in_progress:
                            self._operation_in_progress = True
                            self._show_warning(warnings, current_frame)
                        else:
                            # Se não há warnings, resetar flag
                            self._operation_in_progress = False
                
                self._last_frame_content = current_map
                
                # Decrementar cooldown
                if self._warning_cooldown > 0:
                    self._warning_cooldown -= 1
                
            except Exception as e:
                print(f"DEBUG: erro no modal - {e}")
                pass
        
        return {'PASS_THROUGH'}

    def execute(self, context):
        """Ativa/desativa o monitoramento"""
        wm = context.window_manager
        
        if self._monitoring:
            if self._timer:
                try:
                    wm.event_timer_remove(self._timer)
                except:
                    pass
                self._timer = None
            self._monitoring = False
            self._last_frame_content = {}
            self._last_warning_frame = 0
            self._warning_cooldown = 0
            self._operation_in_progress = False
            bpy.types.Scene.timeoffset_monitor_active = False
            self.report({'INFO'}, "🔒 Monitor DESATIVADO")
            print("DEBUG: Monitor desativado")
            return {'FINISHED'}
        
        obj = context.active_object
        if not obj or not gp_api.obj_is_gp(obj):
            self.report({'WARNING'}, "Selecione um objeto Grease Pencil")
            return {'CANCELLED'}
        
        try:
            self._timer = wm.event_timer_add(0.3, window=context.window)
            self._last_frame_content = self._get_frame_content_map(obj)
            self._monitoring = True
            self._last_warning_frame = 0
            self._warning_cooldown = 0
            self._operation_in_progress = False
            bpy.types.Scene.timeoffset_monitor_active = True
            
            wm.modal_handler_add(self)
            self.report({'INFO'}, "🛡️ Monitor ATIVADO - alerta em operações perigosas")
            print("DEBUG: Monitor ativado - modo proteção ativo")
            
        except Exception as e:
            self.report({'ERROR'}, f"Erro ao ativar monitor: {e}")
            return {'CANCELLED'}
        
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        if self._timer:
            try:
                context.window_manager.event_timer_remove(self._timer)
            except:
                pass
            self._timer = None
        self._monitoring = False
        self._last_frame_content = {}
        self._last_warning_frame = 0
        self._warning_cooldown = 0
        self._operation_in_progress = False

class TIME_OFFSET_OT_assign_all_frames(Operator):
    """Assign automático de TODOS os keyframes selecionados para o vertex group ativo"""
    bl_idname = "time_offset.assign_all_frames"
    bl_label = "Assign Keyframes Selecionados"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        # Só permite em Edit Mode, com vertex group ativo e multi-frame ativado
        return (obj and gp_api.obj_is_gp(obj) and 
                obj.mode == 'EDIT' and
                gp_api.get_multiedit(obj))  # Usar função do api_route
    
    def execute(self, context):
        obj = context.active_object
        active_vgroup = obj.vertex_groups.active
        
        if not active_vgroup:
            self.report({'WARNING'}, "Nenhum vertex group ativo selecionado")
            return {'CANCELLED'}
        
        print(f"\n=== Assign Multi-Frame para grupo '{active_vgroup.name}' ===")
        
        # Guardar estado original
        old_frame = context.scene.frame_current
        frames_assigned = 0
        total_strokes = 0
        
        # Coletar TODOS os frames que estão em multi-frame editing
        frames_to_process = set()
        
        for layer in obj.data.layers:
            if gp_api.layer_locked(layer) or gp_api.layer_hidden(layer):
                continue
            
            for frame in layer.frames:
                # No multi-frame editing, todos os frames são considerados
                frames_to_process.add(frame.frame_number)
        
        print(f"  Frames encontrados: {sorted(frames_to_process)}")
        
        if not frames_to_process:
            self.report({'WARNING'}, "Nenhum frame encontrado")
            return {'CANCELLED'}
        
        # Processar cada frame
        for frame_number in sorted(frames_to_process):
            # Ir para o frame
            context.scene.frame_current = frame_number
            context.view_layer.update()
            
            # Usar api_route para selecionar tudo
            try:
                gp_api.op_select_all()  # Usar função do api_route
            except:
                # Fallback: tentar método alternativo
                try:
                    bpy.ops.grease_pencil.select_all(action='SELECT')
                except:
                    print(f"  Frame {frame_number}: não foi possível selecionar")
                    continue
            
            # Verificar se há algo selecionado (opcional - pode pular para performance)
            has_selection = True  # Assumir que tem seleção
            
            if has_selection:
                # Executar o assign
                try:
                    # O assign ainda é o mesmo operador
                    bpy.ops.object.vertex_group_assign()
                    frames_assigned += 1
                    
                    # Contar strokes (opcional, para relatório)
                    stroke_count = 0
                    for layer in obj.data.layers:
                        for frame in layer.frames:
                            if frame.frame_number == frame_number:
                                if hasattr(frame, 'strokes'):
                                    stroke_count = len(frame.strokes)
                                elif hasattr(frame, 'nuclear_strokes'):
                                    stroke_count = len(list(frame.nuclear_strokes))
                                break
                    
                    total_strokes += stroke_count
                    print(f"  Frame {frame_number}: assign realizado ({stroke_count} strokes)")
                    
                except Exception as e:
                    print(f"  Frame {frame_number}: erro no assign - {e}")
            
            # Deselecionar para o próximo frame
            try:
                gp_api.op_deselect()  # Usar função do api_route
            except:
                try:
                    bpy.ops.grease_pencil.select_all(action='DESELECT')
                except:
                    pass
        
        # Restaurar frame original
        context.scene.frame_current = old_frame
        context.view_layer.update()
        
        print(f"=== Concluído: {frames_assigned} frames processados, {total_strokes} strokes assignados ===\n")
        
        self.report({'INFO'}, 
                   f"Assign: {frames_assigned} frames para grupo '{active_vgroup.name}' "
                   f"({total_strokes} strokes)")
        
        return {'FINISHED'}

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
        current_frame = context.scene.frame_current

        # ============================================
        # PREVIEW DO FRAME DA BIBLIOTECA
        # ============================================
        layout.separator()
        preview_key = helpers.get_library_preview(obj, library_frame)
        pcoll = helpers.get_preview_collection()    

        if preview_key and preview_key in pcoll:
            preview_box = layout.box()
            preview_box.label(text=f"Preview Frame {library_frame}", icon='IMAGE_DATA')
            preview_box.template_icon(
                icon_value=pcoll[preview_key].icon_id,
                scale=6
            )
        else:
            preview_box = layout.box()
            preview_box.label(text="Preview indisponível", icon='IMAGE_DATA')
            preview_box.label(text=f"Frame {library_frame}")

        # ============================================
        # INFORMAÇÕES DA BIBLIOTECA
        # ============================================
        box = layout.box()
        box.label(text="Biblioteca de Frames", icon='LIBRARY_DATA_DIRECT')

        # Status da biblioteca
        has_library_frames = helpers.has_negative_frames(obj)
        if has_library_frames:
            min_frame, max_frame = helpers.get_library_frame_range(obj)
            box.label(text=f"Biblioteca: {min_frame} a {max_frame}", icon='BOOKMARKS')
        else:
            box.label(text="Biblioteca vazia", icon='INFO')

        box.prop(time_mod, "offset", text="Frame da Biblioteca")

        # Status da animação
        is_animated = helpers.is_offset_animated(obj, time_mod)
        anim_icon = 'ANIM' if is_animated else 'KEYFRAME'
        box.label(text=f"Animado: {'SIM' if is_animated else 'NÃO'}", icon=anim_icon)

        # ============================================
        # CONTROLES DE EDIÇÃO
        # ============================================
        layout.separator()
        layout.label(text="Controles de Edição", icon='TOOL_SETTINGS')
        
        # Toggle do modificador
        row = layout.row(align=True)
        row.prop(time_mod, "show_in_editmode", text="Editar", toggle=True)
        row.prop(time_mod, "show_viewport", text="Visualizar", toggle=True)
        row.prop(time_mod, "show_render", text="Render", toggle=True)

        # ============================================
        # GERENCIAMENTO DE FRAMES (POSITIVO → BIBLIOTECA)
        # ============================================
        layout.separator()
        layout.label(text="Frame Positivo → Biblioteca", icon='FORWARD')
        
        col = layout.column(align=True)
        
        # Duplicar frame atual para edição local
        col.operator(
            "time_offset.duplicate_current_positive", 
            text=f"Duplicar Frame {current_frame} (Edição Local)",
            icon='DUPLICATE'
        )
        
        # Enviar edição para biblioteca
        row = col.row(align=True)
        row.operator(
            "time_offset.capture_edited_to_library", 
            text=f"Enviar Frame {current_frame} para Biblioteca",
            icon='EXPORT'
        )
        row.prop(time_mod, "show_viewport", text="", icon='RESTRICT_VIEW_OFF')

        # ============================================
        # GERENCIAMENTO DA BIBLIOTECA (FRAMES NEGATIVOS)
        # ============================================
        layout.separator()
        layout.label(text="Biblioteca (Frames Negativos)", icon='LIBRARY_DATA_DIRECT')
        
        col = layout.column(align=True)
        
        # Criar novo frame limpo
        col.operator("time_offset.create_clean_frame", icon='ADD')
        
        # Duplicar frame atual da biblioteca
        col.operator(
            "time_offset.duplicate_current_frame",
            text=f"Duplicar Frame {library_frame} (Biblioteca)",
            icon='COPY_ID'
        )
        
        # Seção: Biblioteca → Timeline (Edição)
        layout.separator()
        layout.label(text="Editar Frame da Biblioteca", icon='GREASEPENCIL')

        col = layout.column(align=True)
        # Trazer frame da biblioteca para timeline
        col.operator(
            "time_offset.bring_to_timeline",
            text=f"Trazer Frame {library_frame} para Timeline {current_frame}",
            icon='COPYDOWN'
        )

        # Desligar modificador automaticamente (já faz no operador)
        col.prop(time_mod, "show_viewport", text="Ver Edição Local", icon='RESTRICT_VIEW_OFF')

        # Seção: Timeline → Biblioteca (Salvar)
        layout.separator()
        layout.label(text="Salvar na Biblioteca", icon='EXPORT')

        col = layout.column(align=True)
        # Enviar timeline para biblioteca
        col.operator(
            "time_offset.send_to_library",
            text=f"Enviar Frame {current_frame} para Biblioteca",
            icon='IMPORT'
        )

        # Atualizar preview
        col.operator(
            "time_offset.update_current_preview", 
            text="Atualizar Preview Atual", 
            icon='FILE_REFRESH'
        )

        # ============================================
        # NAVEGAÇÃO NA BIBLIOTECA
        # ============================================
        layout.separator()
        layout.label(text="Navegação na Biblioteca", icon='VIEW_PAN')
        
        col = layout.column(align=True)
        row = col.row(align=True)
        row.operator("time_offset.navigate_previous", text="Anterior", icon='TRIA_LEFT')
        row.operator("time_offset.navigate_next", text="Próximo", icon='TRIA_RIGHT')
        col.operator("time_offset.go_to_first_library_frame", text="Primeiro da Biblioteca", icon='REW')

        # ============================================
        # FERRAMENTAS EXTRAS
        # ============================================
        layout.separator()
        layout.label(text="Ferramentas Extras", icon='TOOL_SETTINGS')
        
        col = layout.column(align=True)
        col.operator("time_offset.flip_horizontal", text="Flip Horizontal", icon='UV_SYNC_SELECT')
        col.operator("time_offset.assign_all_frames", text="Assign Todos Frames", icon='GROUP_VERTEX')

        # ============================================
        # ANIMAÇÃO DO OFFSET
        # ============================================
        layout.separator()
        layout.label(text="Animação do Offset", icon='ANIM')
        
        col = layout.column(align=True)
        if is_animated:
            row = col.row(align=True)
            row.operator("time_offset.animate_offset", text="Add Keyframe", icon='KEYFRAME')
            row.operator("time_offset.remove_animation", text="", icon='X')

            row = col.row(align=True)
            row.operator("time_offset.previous_keyframe", text="", icon='PREV_KEYFRAME')
            row.operator("time_offset.next_keyframe", text="", icon='NEXT_KEYFRAME')
        else:
            col.operator("time_offset.animate_offset", text="Iniciar Animação", icon='KEYFRAME_HLT')
    
        # ============================================
        # MONITOR DE SEGURANÇA
        # ============================================
        layout.separator()
        box = layout.box()
        box.label(text="Segurança", icon='TOOL_SETTINGS')
        
        # Verificar se monitor está ativo (usando propriedade global simples)
        # Vamos usar um atributo simples no objeto para track
        is_monitoring = getattr(context.scene, 'timeoffset_monitor_active', False)
        
        row = box.row(align=True)
        if is_monitoring:
            row.operator("time_offset.monitor_keyframes", text="Desativar Monitor", icon='TOOL_SETTINGS')
            row.label(text="", icon='CHECKMARK')
            box.label(text="Monitor ATIVO - detectando sobreposição", icon='INFO')
        else:
            row.operator("time_offset.monitor_keyframes", text="Ativar Monitor", icon='TOOL_SETTINGS')
            box.label(text="Monitor INATIVO - risco de crash ao duplicar/mover", icon='ERROR')

        # ============================================
        # STATUS DA TIMELINE
        # ============================================
        layout.separator()
        max_positive_frame = helpers.get_max_positive_frame_number(obj)
        
        box = layout.box()
        box.label(text=f"Timeline: Frame {current_frame}", icon='TIME')
        box.label(text=f"Frames positivos: 0 a {max_positive_frame}", icon='PMARKER')
        box.label(text=f"Biblioteca atual: {library_frame}", icon='BOOKMARKS')

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
    TIME_OFFSET_OT_bring_to_timeline,
    TIME_OFFSET_OT_send_to_library,
    TIME_OFFSET_OT_duplicate_current_positive,
    TIME_OFFSET_OT_capture_edited_to_library,
    TIME_OFFSET_OT_toggle_edit_mode,
    TIME_OFFSET_OT_navigate_previous,
    TIME_OFFSET_OT_navigate_next,
    TIME_OFFSET_OT_go_to_first_library_frame,
    TIME_OFFSET_OT_animate_offset,
    TIME_OFFSET_OT_monitor_keyframes,
    TIME_OFFSET_OT_remove_animation,
    TIME_OFFSET_OT_next_keyframe,
    TIME_OFFSET_OT_previous_keyframe,
    TIME_OFFSET_OT_insert_keyframe_timeline,
    TIME_OFFSET_OT_remove_keyframe_timeline,
    TIME_OFFSET_OT_assign_all_frames,
    TIME_OFFSET_OT_flip_horizontal,
    TIME_OFFSET_OT_flip_horizontal_object,
    TIME_OFFSET_PT_main_panel,
    TIME_OFFSET_PT_missing_modifier,
    TIME_OFFSET_OT_update_current_preview,
)


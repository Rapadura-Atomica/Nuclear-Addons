# SPDX-License-Identifier: GPL-3.0-or-later
bl_info = {
    "name": "Custom Timeline View", 
    "author": "Test Developer",
    "version": (1, 1, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Custom Timeline",
    "description": "View customizada de timeline integrada com Dopesheet",
    "category": "Animation",
}

import bpy
from bpy.types import Operator, Panel, Menu, UIList, PropertyGroup
from bpy.props import IntProperty, StringProperty, BoolProperty, CollectionProperty, PointerProperty, FloatProperty

# =====================================================
# PROPRIEDADES E DADOS
# =====================================================

class TimelineKeyframe(PropertyGroup):
    """Propriedade para armazenar keyframes na timeline"""
    
    frame_number: IntProperty(
        name="Frame Number",
        description="Número do frame",
        default=1
    ) #type: ignore
    
    name: StringProperty(
        name="Name", 
        description="Nome do keyframe",
        default="Keyframe"
    ) #type: ignore 
    
    selected: BoolProperty(
        name="Selected",
        description="Keyframe selecionado",
        default=False
    ) #type: ignore
    
    type: StringProperty(
        name="Type",
        description="Tipo de keyframe",
        default="OBJECT"
    ) #type: ignore

class CustomTimelineProperties(PropertyGroup):
    """Propriedades globais da Custom Timeline"""
    active_keyframe_index: IntProperty(default=0) #type: ignore
    visible_start_frame: IntProperty(default=1) #type: ignore
    visible_end_frame: IntProperty(default=250) #type: ignore
    zoom_level: FloatProperty(default=1.0, min=0.1, max=10.0) #type: ignore
    show_timeline_visual: BoolProperty(default=True) #type: ignore
    show_keyframes_list: BoolProperty(default=True) #type: ignore

# =====================================================
# OPERATORS PARA A TIMELINE
# =====================================================

class CUSTOM_TIMELINE_OT_open_dopesheet_area(Operator):
    """Abre uma área com Dopesheet integrado à nossa timeline"""
    bl_idname = "custom_timeline.open_dopesheet_area"
    bl_label = "Open Timeline in Dopesheet"
    bl_description = "Abre uma área com Dopesheet para trabalhar com animação"
    
    def execute(self, context):
        try:
            # Dividir área verticalmente
            bpy.ops.screen.area_split(direction='VERTICAL', factor=0.3)
            
            # Encontrar a área mais recente (a que foi criada) e mudar para DOPESHEET
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':  # A nova área geralmente fica como VIEW_3D
                    area.type = 'DOPESHEET_EDITOR'
                    # Configurar o Dopesheet para mostrar ação certa
                    if context.active_object and context.active_object.animation_data:
                        space = area.spaces.active
                        space.action = context.active_object.animation_data.action
                    break
            
            self.report({'INFO'}, "Timeline area aberta no Dopesheet!")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'WARNING'}, f"Erro ao abrir área: {str(e)}")
            return {'CANCELLED'}

class CUSTOM_TIMELINE_OT_add_keyframe(Operator):
    """Adiciona keyframe na timeline"""
    bl_idname = "custom_timeline.add_keyframe"
    bl_label = "Add Keyframe"
    
    frame_number: IntProperty(default=1) #type: ignore
    
    def execute(self, context):
        scene = context.scene
        
        # Adicionar keyframe
        keyframe = scene.custom_timeline_keyframes.add()
        keyframe.frame_number = self.frame_number
        keyframe.name = f"Key_{self.frame_number}"
        
        # Se for objeto ativo, usar nome do objeto
        if context.active_object:
            keyframe.name = f"{context.active_object.name}_{self.frame_number}"
            keyframe.type = "OBJECT"
        
        # Atualizar índice ativo
        scene.custom_timeline_props.active_keyframe_index = len(scene.custom_timeline_keyframes) - 1
        
        self.report({'INFO'}, f"Keyframe adicionado no frame {self.frame_number}")
        return {'FINISHED'}

class CUSTOM_TIMELINE_OT_remove_keyframe(Operator):
    """Remove keyframe da timeline"""
    bl_idname = "custom_timeline.remove_keyframe"
    bl_label = "Remove Keyframe"
    
    index: IntProperty() #type: ignore
    
    def execute(self, context):
        scene = context.scene
        
        if 0 <= self.index < len(scene.custom_timeline_keyframes):
            removed_frame = scene.custom_timeline_keyframes[self.index].frame_number
            scene.custom_timeline_keyframes.remove(self.index)
            
            # Ajustar índice ativo
            props = scene.custom_timeline_props
            if props.active_keyframe_index >= len(scene.custom_timeline_keyframes):
                props.active_keyframe_index = max(0, len(scene.custom_timeline_keyframes) - 1)
            
            self.report({'INFO'}, f"Keyframe no frame {removed_frame} removido!")
        
        return {'FINISHED'}

class CUSTOM_TIMELINE_OT_jump_to_frame(Operator):
    """Pula para frame específico"""
    bl_idname = "custom_timeline.jump_to_frame"
    bl_label = "Jump to Frame"
    
    frame_number: IntProperty() #type: ignore
    
    def execute(self, context):
        context.scene.frame_current = self.frame_number
        return {'FINISHED'}

class CUSTOM_TIMELINE_OT_play_animation(Operator):
    """Play/Stop animation"""
    bl_idname = "custom_timeline.play_animation"
    bl_label = "Play Animation"
    
    def execute(self, context):
        if context.screen.is_animation_playing:
            bpy.ops.screen.animation_play()
        else:
            bpy.ops.screen.animation_play()
        return {'FINISHED'}

class CUSTOM_TIMELINE_OT_clear_all_keyframes(Operator):
    """Remove todos os keyframes"""
    bl_idname = "custom_timeline.clear_all_keyframes"
    bl_label = "Clear All Keyframes"
    
    def execute(self, context):
        scene = context.scene
        scene.custom_timeline_keyframes.clear()
        scene.custom_timeline_props.active_keyframe_index = 0
        self.report({'INFO'}, "Todos os keyframes removidos!")
        return {'FINISHED'}

class CUSTOM_TIMELINE_OT_sync_to_dopesheet(Operator):
    """Sincroniza nossos keyframes com o Dopesheet real"""
    bl_idname = "custom_timeline.sync_to_dopesheet"
    bl_label = "Sync to Dopesheet"
    bl_description = "Sincroniza os keyframes customizados com o Dopesheet do Blender"
    
    def execute(self, context):
        scene = context.scene
        
        # Limpar keyframes antigos
        scene.custom_timeline_keyframes.clear()
        
        # Coletar keyframes reais do objeto ativo
        if context.active_object and context.active_object.animation_data:
            action = context.active_object.animation_data.action
            if action:
                for fcurve in action.fcurves:
                    for keyframe in fcurve.keyframe_points:
                        # Adicionar keyframe customizado
                        kf = scene.custom_timeline_keyframes.add()
                        kf.frame_number = int(keyframe.co.x)
                        kf.name = f"{context.active_object.name}_F{int(keyframe.co.x)}"
                        kf.type = "FCURVE"
        
        self.report({'INFO'}, f"{len(scene.custom_timeline_keyframes)} keyframes sincronizados!")
        return {'FINISHED'}

# =====================================================
# UI LIST PARA KEYFRAMES
# =====================================================

class CUSTOM_TIMELINE_UL_keyframes_list(UIList):
    """Lista de keyframes na timeline"""
    
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        keyframe = item
        
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.prop(keyframe, "selected", text="")
            row.label(text=keyframe.name, icon='KEYFRAME_HLT')
            row.label(text=f"Frame: {keyframe.frame_number}")
            
            op = row.operator("custom_timeline.jump_to_frame", text="", icon='TRIA_RIGHT')
            op.frame_number = keyframe.frame_number
            
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon='KEYFRAME')

# =====================================================
# PAINEL PRINCIPAL DA TIMELINE (MELHORADO)
# =====================================================

class CUSTOM_TIMELINE_PT_main_panel(Panel):
    """Painel principal da Custom Timeline"""
    bl_label = "Custom Timeline View"
    bl_idname = "CUSTOM_TIMELINE_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Custom Timeline"
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        timeline_props = scene.custom_timeline_props
        
        # Cabeçalho melhorado
        header_box = layout.box()
        row = header_box.row()
        row.label(text="🎬 Custom Timeline", icon='TIME')
        
        # Botão para abrir Dopesheet (AGORA FAZ SENTIDO!)
        row = header_box.row()
        row.operator("custom_timeline.open_dopesheet_area", text="Open Dopesheet Area", icon='ACTION')
        row.operator("custom_timeline.sync_to_dopesheet", text="", icon='FILE_REFRESH')
        
        # Controles principais em box organizado
        control_box = layout.box()
        control_box.label(text="Animation Controls", icon='TOOL_SETTINGS')
        
        # Linha de frame atual + add keyframe
        row = control_box.row(align=True)
        row.prop(scene, "frame_current", text="Frame")
        op = row.operator("custom_timeline.add_keyframe", text="Add Key", icon='KEYFRAME_HLT')
        op.frame_number = scene.frame_current
        
        # Controles de playback estilo profissional
        row = control_box.row(align=True)
        row.scale_y = 1.2  # Botões maiores
        row.operator("screen.frame_jump", text="", icon='REW').end = False
        row.operator("screen.keyframe_jump", text="", icon='PREV_KEYFRAME').next = False
        row.operator("custom_timeline.play_animation", text="Play", icon='PLAY')
        row.operator("screen.keyframe_jump", text="", icon='NEXT_KEYFRAME').next = True
        row.operator("screen.frame_jump", text="", icon='FF').end = True
        
        # Configurações de visualização com ícones
        viz_box = layout.box()
        viz_box.label(text="Display Options", icon='VIS_SEL_11')
        
        row = viz_box.row()
        row.prop(timeline_props, "show_timeline_visual", text="Timeline", icon='TIME')
        row.prop(timeline_props, "show_keyframes_list", text="Keyframes", icon='ANIM_DATA')
        
        # Controles de zoom/visualização
        if timeline_props.show_timeline_visual:
            row = viz_box.row(align=True)
            row.prop(timeline_props, "zoom_level", text="Zoom", slider=True)
            row.prop(timeline_props, "visible_start_frame", text="Start")
            row.prop(timeline_props, "visible_end_frame", text="End")
        
        # Timeline visual (AGORA MAIS COMPACTA)
        if timeline_props.show_timeline_visual:
            layout.separator()
            self.draw_timeline_visual(layout, context)
        
        # Lista de keyframes
        if timeline_props.show_keyframes_list:
            layout.separator()
            self.draw_keyframes_list(layout, context)
    
    def draw_timeline_visual(self, layout, context):
        """Desenha a representação visual da timeline - Versão Compacta"""
        scene = context.scene
        timeline_props = scene.custom_timeline_props
        
        box = layout.box()
        box.label(text="Timeline", icon='GRAPH')
        
        # Timeline mais compacta e prática
        timeline_row = box.row(align=True)
        timeline_row.alignment = 'EXPAND'
        
        start = timeline_props.visible_start_frame
        end = timeline_props.visible_end_frame
        
        # Calcular densidade baseada no zoom
        visible_range = end - start
        if visible_range > 50:
            step = max(1, visible_range // 20)  # Menos elementos quando zoom out
        else:
            step = 1
        
        current_frame = scene.frame_current
        
        for frame in range(start, end + 1, step):
            is_keyframe = any(kf.frame_number == frame for kf in scene.custom_timeline_keyframes)
            is_current = frame == current_frame
            
            # Ícones mais inteligentes
            if is_current and is_keyframe:
                icon = 'DECORATE_KEYFRAME'
                text = str(frame)
            elif is_current:
                icon = 'PMARKER_SEL' 
                text = str(frame)
            elif is_keyframe:
                icon = 'KEYFRAME'
                text = ""
            else:
                icon = 'DOT'
                text = ""
            
            # Mostrar números apenas em frames "redondos" ou current
            show_text = (frame % 10 == 0 or is_current) and (visible_range < 100)
            
            op = timeline_row.operator(
                "custom_timeline.jump_to_frame", 
                text=text if show_text else "", 
                icon=icon,
                depress=is_current
            )
            op.frame_number = frame
    
    def draw_keyframes_list(self, layout, context):
        """Desenha a lista de keyframes - Versão Melhorada"""
        scene = context.scene
        timeline_props = scene.custom_timeline_props
        
        box = layout.box()
        
        # Header da lista com contador
        row = box.row()
        row.label(text=f"Keyframes: {len(scene.custom_timeline_keyframes)}", icon='ANIM_DATA')
        row.operator("custom_timeline.clear_all_keyframes", text="Clear All", icon='TRASH')
        
        if not scene.custom_timeline_keyframes:
            box.label(text="No keyframes yet", icon='INFO')
            row = box.row()
            row.operator("custom_timeline.add_keyframe", text="Add First Keyframe", icon='ADD')
            row.operator("custom_timeline.sync_to_dopesheet", text="Sync from Dopesheet", icon='IMPORT')
            return
        
        # Lista de keyframes
        row = box.row()
        row.template_list(
            "CUSTOM_TIMELINE_UL_keyframes_list", 
            "", 
            scene, 
            "custom_timeline_keyframes", 
            timeline_props, 
            "active_keyframe_index"
        )
        
        # Controles da lista
        col = row.column(align=True)
        col.operator("custom_timeline.add_keyframe", icon='ADD', text="")
        col.operator("custom_timeline.remove_keyframe", icon='REMOVE', text="").index = timeline_props.active_keyframe_index

# =====================================================
# PAINEL NO DOPESHEET (INTEGRAÇÃO PERFEITA!)
# =====================================================

class CUSTOM_TIMELINE_PT_dopesheet_panel(Panel):
    """Painel da Custom Timeline no Dopesheet - AGORA FAZ SENTIDO!"""
    bl_label = "Custom Timeline"
    bl_idname = "CUSTOM_TIMELINE_PT_dopesheet_panel"
    bl_space_type = 'DOPESHEET_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Timeline"
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        layout.label(text="Custom Timeline Controls", icon='TIME')
        layout.separator()
        
        # Mostrar apenas controles essenciais no Dopesheet
        box = layout.box()
        
        # Sincronização com Dopesheet
        row = box.row()
        row.operator("custom_timeline.sync_to_dopesheet", text="Sync Keyframes", icon='FILE_REFRESH')
        
        # Controles rápidos
        row = box.row(align=True)
        row.prop(scene, "frame_current", text="Frame")
        op = row.operator("custom_timeline.add_keyframe", text="", icon='KEYFRAME_HLT')
        op.frame_number = scene.frame_current
        
        # Info sobre keyframes
        if scene.custom_timeline_keyframes:
            box.label(text=f"{len(scene.custom_timeline_keyframes)} custom keyframes", icon='KEYINGSET')

# =====================================================
# REGISTRO
# =====================================================

classes = (
    TimelineKeyframe,
    CustomTimelineProperties,
    CUSTOM_TIMELINE_OT_open_dopesheet_area,
    CUSTOM_TIMELINE_OT_add_keyframe,
    CUSTOM_TIMELINE_OT_remove_keyframe,
    CUSTOM_TIMELINE_OT_jump_to_frame,
    CUSTOM_TIMELINE_OT_play_animation,
    CUSTOM_TIMELINE_OT_clear_all_keyframes,
    CUSTOM_TIMELINE_OT_sync_to_dopesheet,
    CUSTOM_TIMELINE_UL_keyframes_list,
    CUSTOM_TIMELINE_PT_main_panel,
    CUSTOM_TIMELINE_PT_dopesheet_panel,
)

def register():
    """Registra o addon"""
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Registrar propriedades na cena
    bpy.types.Scene.custom_timeline_props = PointerProperty(type=CustomTimelineProperties)
    bpy.types.Scene.custom_timeline_keyframes = CollectionProperty(type=TimelineKeyframe)
    
    print("Custom Timeline View registrado com sucesso!")

def unregister():
    """Desregistra o addon"""
    # Limpar propriedades
    del bpy.types.Scene.custom_timeline_props
    del bpy.types.Scene.custom_timeline_keyframes
    
    # Desregistrar classes
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    print("Custom Timeline View desregistrado!")

if __name__ == "__main__":
    register()
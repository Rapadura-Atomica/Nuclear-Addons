bl_info = {
    "name": "Focus Object Everywhere",
    "author": "Based on original idea + improvements",
    "version": (2, 0, 0),
    "blender": (4, 2, 0),
    "location": "3D View > Ctrl+Shift+O",
    "description": "Evidencia objeto no Dope Sheet e Viewport 3D: isola, foca e destaca visualmente",
    "category": "Animation",
}

import bpy
from mathutils import Vector

# ============================================
# PROPRIEDADES PARA ARMAZENAR ESTADO ANTERIOR
# ============================================
class FocusObjectSettings(bpy.types.PropertyGroup):
    previous_local_view: bpy.props.BoolProperty(name="Previous Local View")
    previous_hide_state: bpy.props.CollectionProperty(type=bpy.types.PropertyGroup)
    previous_active_layer: bpy.props.IntProperty(name="Previous Active Layer")
    is_focused: bpy.props.BoolProperty(name="Is Focused", default=False)

# ============================================
# OPERADOR PRINCIPAL
# ============================================
class OBJECT_OT_focus_object_everywhere(bpy.types.Operator):
    bl_idname = "object.focus_object_everywhere"
    bl_label = "Focus Object Everywhere"
    bl_description = "Evidencia objeto no Dope Sheet e Viewport 3D"
    bl_options = {'REGISTER', 'UNDO'}
    
    def get_dopesheet_area(self, context):
        """Encontra ou cria uma área Dope Sheet"""
        # Primeiro tenta encontrar área existente
        for area in context.screen.areas:
            if area.type == 'DOPESHEET_EDITOR':
                return area
        
        # Se não encontrar, usa a área 3D View atual e divide
        view3d = next((a for a in context.screen.areas if a.type == 'VIEW_3D'), None)
        if view3d:
            # Salva região original
            original_region = view3d.regions[0]
            
            # Divide a área verticalmente
            context.screen.areas.update()
            bpy.ops.screen.area_split(
                {'area': view3d, 'region': original_region},
                direction='VERTICAL',
                factor=0.3
            )
            
            # Procura pela nova área Dope Sheet
            for area in context.screen.areas:
                if area.type == 'VIEW_3D' and area != view3d:
                    area.type = 'DOPESHEET_EDITOR'
                    return area
        
        return None

    def isolate_in_viewport(self, context, obj):
        """Isola o objeto na viewport 3D"""
        view3d = next((a for a in context.screen.areas if a.type == 'VIEW_3D'), None)
        if not view3d:
            return False
        
        # Salva estado atual
        settings = context.scene.focus_settings
        
        # Limpa estado anterior
        settings.previous_hide_state.clear()
        
        # Salva estado de TODOS os objetos
        for other_obj in context.view_layer.objects:
            item = settings.previous_hide_state.add()
            item.name = other_obj.name
            item["hide_viewport"] = other_obj.hide_viewport
            item["hide_select"] = other_obj.hide_select
            item["select"] = other_obj.select_get()
        
        # Esconde todos os outros objetos
        for other_obj in context.view_layer.objects:
            if other_obj != obj:
                other_obj.hide_viewport = True
                other_obj.hide_select = True
            else:
                other_obj.hide_viewport = False
                other_obj.hide_select = False
                other_obj.select_set(True)
        
        # Foca no objeto selecionado
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        with context.temp_override(area=area, region=region):
                            bpy.ops.view3d.view_selected()
                        break
                break
        
        return True

    def restore_original_state(self, context):
        """Restaura estado anterior da viewport"""
        settings = context.scene.focus_settings
        if not settings.is_focused:
            return
        
        # Restaura visibilidade dos objetos
        for item in settings.previous_hide_state:
            obj = bpy.data.objects.get(item.name)
            if obj:
                obj.hide_viewport = item.get("hide_viewport", False)
                obj.hide_select = item.get("hide_select", False)
                obj.select_set(item.get("select", False))
        
        # Restaura objeto ativo
        if len(settings.previous_hide_state) > 0:
            first_item = settings.previous_hide_state[0]
            first_obj = bpy.data.objects.get(first_item.name)
            if first_obj and first_item.get("select", False):
                context.view_layer.objects.active = first_obj
        
        # Limpa propriedade is_focused
        settings.is_focused = False
        
        # Limpa coleção para próximo uso
        settings.previous_hide_state.clear()
        
        self.report({'INFO'}, "Estado original restaurado")

    def focus_in_dopesheet(self, context, obj):
        """Foca apenas nos canais do objeto no Dope Sheet"""
        dopesheet = self.get_dopesheet_area(context)
        if not dopesheet:
            self.report({'WARNING'}, "Não foi possível criar área Dope Sheet")
            return False
        
        # Usa override para operações no Dope Sheet
        with context.temp_override(area=dopesheet, region=dopesheet.regions[0]):
            try:
                # Limpa seleção atual
                bpy.ops.anim.channels_select_all(action='DESELECT')
                
                # Verifica se objeto tem animação
                if obj.animation_data and obj.animation_data.action:
                    # Seleciona todas as fcurves do objeto
                    for fcurve in obj.animation_data.action.fcurves:
                        fcurve.select = True
                    
                    # Expande canais (apenas 1 nível é suficiente)
                    bpy.ops.anim.channels_expand(all=False)
                    
                    # Ajusta view para mostrar seleção
                    bpy.ops.anim.channels_view_selected()
                    
                    # Muda cor dos canais selecionados (opcional)
                    self.highlight_selected_channels(context)
                    
                    return True
                
                # Suporte para Grease Pencil
                elif obj.type == 'GREASEPENCIL' and obj.data.layers:
                    active_layer = obj.data.layers.active
                    if active_layer:
                        # Seleciona layer ativa
                        for layer in obj.data.layers:
                            layer.select = (layer == active_layer)
                        
                        bpy.ops.anim.channels_expand(all=False)
                        bpy.ops.anim.channels_view_selected()
                        return True
                
                else:
                    self.report({'INFO'}, f"Objeto '{obj.name}' não tem animação")
                    return False
                    
            except Exception as e:
                self.report({'WARNING'}, f"Erro no Dope Sheet: {e}")
                return False
    
    def highlight_selected_channels(self, context):
        """Destaca visualmente os canais selecionados (opcional)"""
        theme = context.preferences.themes[0]
        dopesheet = theme.dopesheet_editor
        
        # Salva cores originais para restaurar depois
        if not hasattr(context.scene, 'original_dopesheet_colors'):
            context.scene.original_dopesheet_colors = {
                'selected': dopesheet.channels_selected[:],
                'text': dopesheet.list_text[:]
            }
        
        # Aplica cores de destaque
        dopesheet.channels_selected = (0.2, 0.8, 0.4, 1.0)  # Verde vibrante
    
    def restore_original_state(self, context):
        """Restaura estado anterior da viewport"""
        settings = context.scene.focus_settings
        if not settings.is_focused:
            return
        
        # Restaura visibilidade dos objetos
        for item in settings.previous_hide_state:
            obj = bpy.data.objects.get(item.name)
            if obj:
                obj.hide_viewport = item.get("hide_viewport", False)
                obj.hide_select = item.get("hide_select", False)
        
        # Restaura cores do Dope Sheet
        if hasattr(context.scene, 'original_dopesheet_colors'):
            theme = context.preferences.themes[0]
            dopesheet = theme.dopesheet_editor
            colors = context.scene.original_dopesheet_colors
            dopesheet.channels_selected = colors['selected']
            dopesheet.list_text = colors['text']
            del context.scene.original_dopesheet_colors
        
        settings.is_focused = False
        self.report({'INFO'}, "Estado original restaurado")
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj:
            self.report({'WARNING'}, "Nenhum objeto ativo selecionado")
            return {'CANCELLED'}
        
        settings = context.scene.focus_settings
        
        # Se já está focado, restaura estado anterior
        if settings.is_focused:
            self.restore_original_state(context)
            return {'FINISHED'}
        
        # Isola objeto na viewport 3D
        if not self.isolate_in_viewport(context, obj):
            self.report({'WARNING'}, "Falha ao isolar objeto na viewport")
            return {'CANCELLED'}
        
        # Foca no Dope Sheet
        if self.focus_in_dopesheet(context, obj):
            settings.is_focused = True
            self.report({'INFO'}, f"✓ Objeto '{obj.name}' evidenciado (pressione novamente para restaurar)")
            return {'FINISHED'}
        else:
            # Se falhar no Dope Sheet, restaura viewport
            self.restore_original_state(context)
            return {'CANCELLED'}

# ============================================
# OPERADOR PARA LIMPAR FOCO
# ============================================
class OBJECT_OT_clear_focus(bpy.types.Operator):
    bl_idname = "object.clear_focus"
    bl_label = "Clear Focus"
    bl_description = "Restaura visibilidade de todos os objetos"
    
    def execute(self, context):
        settings = context.scene.focus_settings
        if settings.is_focused:
            # Chama o operador principal para restaurar
            bpy.ops.object.focus_object_everywhere()
        else:
            # Restaura manualmente
            for obj in context.view_layer.objects:
                obj.hide_viewport = False
                obj.hide_select = False
            self.report({'INFO'}, "Visibilidade restaurada")
        
        return {'FINISHED'}

# ============================================
# PANEL NA VIEWPORT
# ============================================
class VIEW3D_PT_focus_panel(bpy.types.Panel):
    bl_label = "Focus Object"
    bl_idname = "VIEW3D_PT_focus_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Focus"
    
    def draw(self, context):
        layout = self.layout
        settings = context.scene.focus_settings
        
        if settings.is_focused:
            layout.label(text="🔍 Focus Mode ACTIVE", icon='HIDE_OFF')
            layout.operator("object.clear_focus", text="Exit Focus Mode", icon='X')
        else:
            layout.operator("object.focus_object_everywhere", text="Focus Object", icon='VIEWZOOM')
            layout.label(text="Shortcut: Ctrl+Shift+O", icon='INFO')

# ============================================
# KEYMAPS
# ============================================
addon_keymaps = []

def register_keymaps():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        # Keymap para Object Mode
        km = kc.keymaps.new(name='Object Mode', space_type='EMPTY')
        kmi = km.keymap_items.new(
            "object.focus_object_everywhere",
            'O', 'PRESS',
            ctrl=True, shift=True
        )
        addon_keymaps.append((km, kmi))
        
        # Keymap para Dope Sheet também
        km_dopesheet = kc.keymaps.new(name='Dopesheet', space_type='DOPESHEET_EDITOR')
        kmi_dopesheet = km_dopesheet.keymap_items.new(
            "object.focus_object_everywhere",
            'O', 'PRESS',
            ctrl=True, shift=True
        )
        addon_keymaps.append((km_dopesheet, kmi_dopesheet))

def unregister_keymaps():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()

# ============================================
# REGISTRO
# ============================================
classes = [
    FocusObjectSettings,
    OBJECT_OT_focus_object_everywhere,
    OBJECT_OT_clear_focus,
    VIEW3D_PT_focus_panel,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.focus_settings = bpy.props.PointerProperty(type=FocusObjectSettings)
    register_keymaps()
    
    print("✓ Focus Object Everywhere addon registrado")

def unregister():
    unregister_keymaps()
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    del bpy.types.Scene.focus_settings
    
    print("✓ Focus Object Everywhere addon removido")

if __name__ == "__main__":
    register()
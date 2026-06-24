bl_info = {
    "name": "Focus Object Everywhere",
    "author": "Rapadura Atômica LTDA",
    "website": "https://github.com/Rapadura-Atomica",
    "version": (2, 1, 0),
    "blender": (4, 2, 0),
    "location": "3D View > Ctrl+Shift+O",
    "description": "Isola objeto no viewport e mostra apenas ele no Dope Sheet",
    "category": "Animation",
}

import bpy

# ============================================
# PROPRIEDADES PARA ARMAZENAR ESTADO ANTERIOR
# ============================================
class FocusObjectSettings(bpy.types.PropertyGroup):
    previous_hide_state: bpy.props.CollectionProperty(type=bpy.types.PropertyGroup)
    previous_active_object: bpy.props.StringProperty(name="Previous Active Object")
    is_focused: bpy.props.BoolProperty(name="Is Focused", default=False)

# ============================================
# OPERADOR PRINCIPAL
# ============================================
class OBJECT_OT_focus_object_everywhere(bpy.types.Operator):
    bl_idname = "object.focus_object_everywhere"
    bl_label = "Focus Object Everywhere"
    bl_description = "Isola objeto no viewport e Dope Sheet"
    bl_options = {'REGISTER', 'UNDO'}
    
    def save_visibility_state(self, context):
        """Salva o estado de visibilidade de todos os objetos"""
        settings = context.scene.focus_settings
        settings.previous_hide_state.clear()
        
        for obj in context.view_layer.objects:
            item = settings.previous_hide_state.add()
            item.name = obj.name
            item["hide_viewport"] = obj.hide_viewport
            item["hide_select"] = obj.hide_select
            item["hide_render"] = obj.hide_render
        
        # Salva o objeto ativo atual
        if context.active_object:
            settings.previous_active_object = context.active_object.name
    
    def restore_visibility_state(self, context):
        """Restaura o estado de visibilidade salvo"""
        settings = context.scene.focus_settings
        
        for item in settings.previous_hide_state:
            obj = bpy.data.objects.get(item.name)
            if obj:
                obj.hide_viewport = item.get("hide_viewport", False)
                obj.hide_select = item.get("hide_select", False)
                obj.hide_render = item.get("hide_render", False)
        
        # Restaura objeto ativo
        if settings.previous_active_object:
            obj = bpy.data.objects.get(settings.previous_active_object)
            if obj:
                context.view_layer.objects.active = obj
                obj.select_set(True)
        
        settings.is_focused = False
    
    def isolate_in_viewport(self, context, obj):
        """Isola o objeto na viewport 3D"""
        # Esconde todos os outros objetos
        for other_obj in context.view_layer.objects:
            if other_obj != obj:
                other_obj.hide_viewport = True
                other_obj.hide_select = True
            else:
                other_obj.hide_viewport = False
                other_obj.hide_select = False
                other_obj.select_set(True)
        
        # Garante que o objeto está ativo
        context.view_layer.objects.active = obj
        
        # Foca no objeto selecionado na viewport
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        with context.temp_override(area=area, region=region):
                            bpy.ops.view3d.view_selected()
                        break
                break
        
        return True
    
    def focus_in_dopesheet(self, context, obj):
        """Mostra apenas o objeto selecionado no Dope Sheet"""
        # Encontra uma área Dope Sheet
        dopesheet_area = None
        for area in context.screen.areas:
            if area.type == 'DOPESHEET_EDITOR':
                dopesheet_area = area
                break
        
        if not dopesheet_area:
            self.report({'WARNING'}, "Abra um Dope Sheet manualmente (Editor de Animação)")
            return False
        
        # Encontra a região WINDOW do Dope Sheet
        window_region = None
        for region in dopesheet_area.regions:
            if region.type == 'WINDOW':
                window_region = region
                break
        
        if not window_region:
            return False
        
        # Usa override para manipular o Dope Sheet
        with context.temp_override(area=dopesheet_area, region=window_region):
            try:
                # Limpa seleção atual de canais
                bpy.ops.anim.channels_select_all(action='DESELECT')
                
                # No Dope Sheet, podemos filtrar por objeto selecionado
                # Mas primeiro, vamos garantir que o objeto está selecionado na view layer
                obj.select_set(True)
                context.view_layer.objects.active = obj
                
                # Força atualização do Dope Sheet para mostrar apenas objetos selecionados
                # Alternativa: usa o filtro de "Only Selected" no Dope Sheet
                space = dopesheet_area.spaces.active
                if hasattr(space, 'dopesheet'):
                    space.dopesheet.show_only_selected = True
                
                # Tenta expandir e focar nos canais
                try:
                    bpy.ops.anim.channels_expand(all=False)
                    bpy.ops.anim.channels_view_selected()
                except:
                    pass  # Ignora erros se não houver canais
                
                return True
                
            except Exception as e:
                self.report({'WARNING'}, f"Erro no Dope Sheet: {str(e)}")
                return False
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj:
            self.report({'WARNING'}, "Selecione um objeto primeiro")
            return {'CANCELLED'}
        
        settings = context.scene.focus_settings
        
        # Se já está focado, restaura
        if settings.is_focused:
            self.restore_visibility_state(context)
            self.report({'INFO'}, "Modo foco desativado")
            return {'FINISHED'}
        
        # Salva estado atual
        self.save_visibility_state(context)
        
        # Isola no viewport
        if not self.isolate_in_viewport(context, obj):
            self.restore_visibility_state(context)
            self.report({'WARNING'}, "Falha ao isolar na viewport")
            return {'CANCELLED'}
        
        # Foca no Dope Sheet (opcional - não falha se não conseguir)
        self.focus_in_dopesheet(context, obj)
        
        settings.is_focused = True
        self.report({'INFO'}, f"✓ Foco no objeto: {obj.name} (Ctrl+Shift+O para sair)")
        return {'FINISHED'}

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
            bpy.ops.object.focus_object_everywhere()
        else:
            # Restaura manualmente todos os objetos
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
            row = layout.row()
            row.operator("object.focus_object_everywhere", text="Focus Object", icon='VIEWZOOM')
            layout.label(text="Shortcut: Ctrl+Shift+O", icon='INFO')

# ============================================
# KEYMAPS
# ============================================
addon_keymaps = []

def register_keymaps():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name='Object Mode', space_type='EMPTY')
        kmi = km.keymap_items.new(
            "object.focus_object_everywhere",
            'O', 'PRESS',
            ctrl=True, shift=True
        )
        addon_keymaps.append((km, kmi))

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
    
    print("✓ Focus Object Everywhere v2.1 registrado")

def unregister():
    unregister_keymaps()
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    del bpy.types.Scene.focus_settings
    
    print("✓ Focus Object Everywhere removido")

if __name__ == "__main__":
    register()
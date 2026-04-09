bl_info = {
    "name": "Keyframe Love Alert",
    "author": "Seu Dev Favorito",
    "version": (1, 0, 0),
    "blender": (5, 0, 0),
    "description": "Um lembrete sobre os perigos de duplicar keyframes",
    "category": "Animation",
}

import bpy

class KeyframeAlertSettings(bpy.types.PropertyGroup):
    show_duplicate_alert: bpy.props.BoolProperty(
        name="Mostrar alerta ao duplicar keyframes",
        default=True
    )


class ANIM_OT_love_alert(bpy.types.Operator):
    bl_idname = "anim.love_alert"
    bl_label = "Aviso Importante"
    
    def draw(self, context):
        layout = self.layout
        settings = context.scene.keyframe_alert_settings
        
        layout.label(text="=" * 50)
        layout.separator()
        
        layout.label(text="ATENCAO!", icon='ERROR')
        layout.separator()
        
        box = layout.box()
        box.label(text="Voce executou uma acao de:")
        box.label(text="   DUPLICAR KEYFRAMES (Shift+D)")
        
        layout.separator()
        
        box = layout.box()
        box.label(text="MENSAGEM IMPORTANTE:")
        box.label(text="")
        box.label(text="   Sobrepor keyframes em cima de outros")
        box.label(text="   pode fazer o Blender CRASHAR!")
        box.label(text="")
        box.label(text="   Evite copiar keyframes em cima de outros.")
        box.label(text="")
        box.label(text="   Para isso agora use o CTRL + D!")
        
        layout.separator()
        
        box = layout.box()
        box.label(text="DICA:")
        box.label(text="   Blender tem auto-save a cada 2 minutos!")
        box.label(text="   File > Recover > Auto Save")
        box.label(text="   Se crashar, voce não perde tudo!")
        
        layout.separator()
        
        layout.prop(settings, "show_duplicate_alert", text="mostrar esta mensagem novamente")
        
        layout.separator()
        
        row = layout.row(align=True)
        row.scale_y = 1.5
        row.operator("anim.understood", text="ENTENDI! Vou tomar cuidado")
        
        layout.separator()
        layout.label(text="=" * 50)
    
    def execute(self, context):
        return {'FINISHED'}
    
    def invoke(self, context, event):
        settings = context.scene.keyframe_alert_settings
        
        if not settings.show_duplicate_alert:
            return {'FINISHED'}
        
        return context.window_manager.invoke_props_dialog(self, width=500)


class ANIM_OT_understood(bpy.types.Operator):
    bl_idname = "anim.understood"
    bl_label = "Entendi"
    
    def execute(self, context):
        self.report({'INFO'}, "Lembre-se: evite sobrepor keyframes!")
        return {'FINISHED'}


class DOPESHEET_PT_love_alert(bpy.types.Panel):
    bl_label = "Alertas"
    bl_space_type = 'DOPESHEET_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Alert"
    
    def draw(self, context):
        layout = self.layout
        settings = context.scene.keyframe_alert_settings
        
        layout.label(text="Configuracoes", icon='SETTINGS')
        layout.separator()
        
        layout.prop(settings, "show_duplicate_alert", text="Alertar ao duplicar (Shift+D)")
        
        layout.separator()
        layout.operator("anim.reset_alerts", text="Reativar alerta")


class ANIM_OT_reset_alerts(bpy.types.Operator):
    bl_idname = "anim.reset_alerts"
    bl_label = "Reset Alerts"
    
    def execute(self, context):
        settings = context.scene.keyframe_alert_settings
        settings.show_duplicate_alert = True
        self.report({'INFO'}, "Alerta reativado!")
        return {'FINISHED'}


# ============================================
# APENAS MOSTRA O POPUP, NAO INTERFERE NA ACAO
# ============================================
class ANIM_OT_show_alert_only(bpy.types.Operator):
    bl_idname = "anim.show_alert_only"
    bl_label = "Show Alert"
    
    def execute(self, context):
        settings = context.scene.keyframe_alert_settings
        
        if settings.show_duplicate_alert:
            bpy.ops.anim.love_alert('INVOKE_DEFAULT')
        
        # Deixa o Blender continuar com a ação normal
        return {'PASS_THROUGH'}


classes = [
    KeyframeAlertSettings,
    ANIM_OT_love_alert,
    ANIM_OT_understood,
    ANIM_OT_reset_alerts,
    ANIM_OT_show_alert_only,
    DOPESHEET_PT_love_alert,
]

addon_keymaps = []

def register_keymaps():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    
    if kc:
        km = kc.keymaps.new(name='Dopesheet', space_type='DOPESHEET_EDITOR')
        
        # Adiciona nosso alerta ANTES da ação nativa
        # O 'PASS_THROUGH' permite que o atalho continue
        kmi = km.keymap_items.new(
            'anim.show_alert_only',
            'D', 'PRESS',
            shift=True
        )
        # Isso faz o atalho executar nosso operador E continuar
        kmi.active = True
        addon_keymaps.append((km, kmi))

def unregister_keymaps():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.keyframe_alert_settings = bpy.props.PointerProperty(type=KeyframeAlertSettings)
    register_keymaps()
    print("Keyframe Love Alert registrado! (So mostra popup, nao interfere na duplicacao)")

def unregister():
    unregister_keymaps()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.keyframe_alert_settings
    print("Keyframe Love Alert removido!")

if __name__ == "__main__":
    register()
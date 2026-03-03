bl_info = {
    "name": "Focus Object in Dope Sheet",
    "author": "",
    "version": (1, 6),
    "blender": (4, 4, 0),
    "location": "3D View > Ctrl+Shift+O",
    "description": "Abre o Dope Sheet e foca apenas no objeto ativo",
    "category": "Animation",
}

import bpy
import mathutils

addon_keymaps = []

class LastRenamedData(bpy.types.PropertyGroup):
    original_name: bpy.props.StringProperty(name="Original Name") # type: ignore 
    object_ref: bpy.props.PointerProperty(type=bpy.types.Object, name="Previous Object") #type: ignore

def change_dopesheet_channel_colors(): 
    theme = bpy.context.preferences.themes['Default'] 
    dopesheet = theme.dopesheet_editor 
    #dopesheet.list_text_hi = (0.349, 0.961, 0.600) 
    dopesheet.channels_selected = (0.4196, 0.7608, 0.5176, 1.0)

class OBJECT_OT_focus_in_dopesheet(bpy.types.Operator):
    bl_idname = "object.focus_in_dopesheet"
    bl_label = "Focar Objeto no Dope Sheet"
    bl_description = "Abre o Dope Sheet e expande apenas os canais do objeto ativo"

    def execute(self, context):
        obj = context.active_object
        if not obj:
            self.report({'WARNING'}, "Nenhum objeto selecionado.")
            return {'CANCELLED'}

        # Procura área Dope Sheet
        dopesheet_area = next((a for a in context.screen.areas if a.type == 'DOPESHEET_EDITOR'), None)

        if not dopesheet_area:
            view3d_area = next((a for a in context.screen.areas if a.type == 'VIEW_3D'), None)
            if not view3d_area:
                self.report({'WARNING'}, "Nenhuma área Dope Sheet ou 3D View disponível.")
                return {'CANCELLED'}
            dopesheet_area = view3d_area
            dopesheet_area.type = 'DOPESHEET_EDITOR'

        region = next((r for r in dopesheet_area.regions if r.type == 'WINDOW'), None)
        if not region:
            self.report({'WARNING'}, "Não foi possível acessar a região do Dope Sheet.")
            return {'CANCELLED'}
        
        with context.temp_override(area=dopesheet_area, region=region, window=context.window):
            try:
                bpy.ops.anim.channels_collapse(all=True)
                bpy.ops.anim.channels_select_all(action='DESELECT')
                scene = context.scene
                data = scene.last_renamed_object

                if data.object_ref and data.object_ref.name.startswith("Act_"):
                    try:
                        data.object_ref.name = data.original_name
                    except RuntimeError:
                        pass 
                    
                if not obj.name.startswith("Act_"):
                    data.original_name = obj.name
                    data.object_ref = obj
                    obj.name = "Act_" + obj.name

                if obj.animation_data and obj.animation_data.action:
                    layers = obj.data.layers
                    active_layer = layers.active
                    change_dopesheet_channel_colors()
                    
                    if active_layer:
                        for layer in layers:
                            layer.select = (layer == active_layer)
                        
                    for _ in range(len(layers)+1):
                        bpy.ops.anim.channels_expand(all=False)
                        
                    for fcurve in obj.animation_data.action.fcurves:
                        fcurve.select = True
                    
                    bpy.ops.anim.channels_view_selected()

                elif obj.type == 'GREASEPENCIL':
                    layers = obj.data.layers
                    active_layer = layers.active
                    change_dopesheet_channel_colors()
                    if active_layer:
                        for layer in layers:
                            layer.select = (layer == active_layer)

                        for _ in range(len(layers)+1):
                            bpy.ops.anim.channels_expand(all=False)

                        bpy.ops.anim.channels_view_selected()
                    else:
                        self.report({'WARNING'}, "Objeto Grease Pencil sem layers ativos.")
                        return {'CANCELLED'}
                        
                else:
                    self.report({'WARNING'}, "Objeto não possui animação ou é de tipo não suportado.")
                    return {'CANCELLED'}
                
            except Exception as e:
                self.report({'WARNING'}, f"Falha ao expandir/focar: {e}")
                return {'CANCELLED'}
        
        self.report({'INFO'}, f"Objeto '{obj.name}' focado no Dope Sheet.")
        return {'FINISHED'}

    
def register_keymap():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name='Object Mode', space_type='EMPTY')
        kmi = km.keymap_items.new(
            idname="object.focus_in_dopesheet",
            type='O',
            value='PRESS',
            ctrl=True,
            shift=True
        )
        addon_keymaps.append((km, kmi))

def unregister_keymap():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()

def register():
    bpy.utils.register_class(OBJECT_OT_focus_in_dopesheet)
    register_keymap()
    bpy.utils.register_class(LastRenamedData)
    bpy.types.Scene.last_renamed_object = bpy.props.PointerProperty(type=LastRenamedData)


def unregister():
    unregister_keymap()
    bpy.utils.unregister_class(OBJECT_OT_focus_in_dopesheet)
    del bpy.types.Scene.last_renamed_object
    bpy.utils.unregister_class(LastRenamedData)


if __name__ == "__main__":
    register()
import bpy
from nuclear.drawing.core import is_parented_to
from nuclear.drawing.ops import (
    view3d_is_rolled,
    view3d_is_mirrored,
    view3d_supports_mirroring,
    view3d_supports_roll,
)
from nuclear.utils import register_classes, unregister_classes
from nuclear.keymaps import register_keymap

class SCENE_UL_gpencil_objects(bpy.types.UIList):
    bl_idname = "SCENE_UL_gpencil"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        layout.prop(item, "name", text="", emboss=False)
        camera_pin_icon = "CON_CAMERASOLVER" if is_parented_to(item, context.scene.camera) else "BLANK1"
        layout.label(icon=camera_pin_icon, text="")
        layout.prop(item, "show_in_front", text="", icon="AXIS_FRONT")

    def filter_items(self, context, data, propname):
        objects = getattr(data, propname)
        flt_flags = []
        flt_neworder = []
        
        # Filtrar apenas objetos Grease Pencil
        for obj in objects:
            # Verificar se é um objeto Grease Pencil válido
            if obj and obj.type == 'GREASEPENCIL' and obj.data:
                if self.filter_name:
                    # Aplicar filtro por nome
                    if self.filter_name.lower() in obj.name.lower():
                        flt_flags.append(self.bitflag_filter_item)
                    else:
                        flt_flags.append(0)
                else:
                    flt_flags.append(self.bitflag_filter_item)
            else:
                flt_flags.append(0)
        
        return flt_flags, flt_neworder

class GPENCIL_UL_draw_layer(bpy.types.UIList):
    bl_idname = "GPENCIL_UL_draw_layer"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        layout.prop(item, "info", text="", emboss=False)
        sub = layout.row(align=True)
        sub.prop(item, "opacity", text="", slider=True, emboss=True)
        sub.separator()
        onion_icon = "ONIONSKIN_ON" if item.use_onion_skinning else "ONIONSKIN_OFF"
        sub.prop(item, "use_onion_skinning", text="", icon=onion_icon, emboss=False)
        sub.prop(item, "hide", text="", emboss=False)
        sub.prop(item, "lock", text="", emboss=False)

class VIEW3D_PT_draw_panel(bpy.types.Panel):
    bl_label = "Drawings"
    bl_category = "Nuclear"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw_header_preset(self, context):
        region_3d = context.space_data.region_3d
        row = self.layout.row(align=True)

        if view3d_supports_mirroring(region_3d):
            row.alert = view3d_is_mirrored(region_3d)
            row.operator("view3d.view_mirror", icon="MOD_MIRROR", text="")
            row.alert = False
            row.separator()

        if view3d_supports_roll(region_3d):
            row.operator(
                "view3d.view_roll_2d_reset",
                icon="FILE_REFRESH",
                text="",
                depress=view3d_is_rolled(region_3d),
            )

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.label(text="Grease Pencil Objects:")
        row = layout.row()
        row.template_list(
            SCENE_UL_gpencil_objects.bl_idname,
            "",
            scene,
            "objects",
            scene,
            "active_gp_index",
            type="DEFAULT",
            rows=3,
        )

        active_gp = None
        if 0 <= scene.active_gp_index < len(scene.objects):
            obj = scene.objects[scene.active_gp_index]
            if isinstance(obj.data, bpy.types.GreasePencil):
                active_gp = obj

        layout.label(text="Layers do GP selecionado:")
        if active_gp:
            row = layout.row()
            row.template_list(
                GPENCIL_UL_draw_layer.bl_idname,
                "",
                active_gp.data,
                "layers",
                active_gp.data,
                "active_layer_index",
                type="DEFAULT",
                rows=3,
            )
        else:
            layout.label(text="Nenhum Grease Pencil selecionado.")

class GPENCIL_MT_drawing_add(bpy.types.Menu):
    bl_idname = "GPENCIL_MT_drawing_add"
    bl_label = "Add"
    bl_description = ""

    @classmethod
    def poll(cls, context):
        return context.mode == "PAINT_GREASE_PENCIL"

    def draw(self, context):
        layout = self.layout
        layout.operator_context = "INVOKE_DEFAULT"
        layout.operator("import.gpencil_references_from_file", text="Reference(s) from file...", icon="IMAGE_DATA")

def draw_quick_edit_header(self, context):
    tool = context.workspace.tools.from_space_view3d_mode(context.mode)
    if tool and tool.mode == "PAINT_GREASE_PENCIL" and tool.widget == "VIEW3D_GGT_gpencil_xform_box":
        row = self.layout.row(align=True)
        row.label(text="Mirror: ")
        row.operator("gpencil.mirror_strokes", text="X").axis = "X"
        row.operator("gpencil.mirror_strokes", text="Y").axis = "Y"

classes = (
    SCENE_UL_gpencil_objects,
    GPENCIL_UL_draw_layer,
    VIEW3D_PT_draw_panel,
    GPENCIL_MT_drawing_add,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    # Propriedades para seleção GP e layer
    bpy.types.Scene.active_gp_index = bpy.props.IntProperty(default=0)
    bpy.types.GreasePencil.active_layer_index = bpy.props.IntProperty(default=0)

    register_keymap(
        "wm.call_menu", "A", shift=True, properties={"name": "GPENCIL_MT_drawing_add"}
    )
    bpy.types.VIEW3D_HT_tool_header.prepend(draw_quick_edit_header)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    if hasattr(bpy.types.Scene, "active_gp_index"):
        del bpy.types.Scene.active_gp_index
    if hasattr(bpy.types.GreasePencil, "active_layer_index"):
        del bpy.types.GreasePencil.active_layer_index

    bpy.types.VIEW3D_HT_tool_header.remove(draw_quick_edit_header)

# 
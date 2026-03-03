
bl_info = {
    "name": "Bone Manager",
    "author": "Rapadura Atômica LTDA",
    "version": (1, 0),
    "blender": (4, 2, 0), 
    "location": "View3D > Sidebar > Bone Mgr",
    "description": "Painel centralizado para editar propriedades de ossos (nome, display, cores, etc)",
    "category": "Rigging",
}

import bpy
from bpy.types import Panel

class VIEW3D_PT_bone_manager(Panel):
    bl_label = "Bone Manager"
    bl_idname = "VIEW3D_PT_bone_manager"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Bone Mgr' 

    @classmethod
    def poll(cls, context):
        obj = context.object
        return (obj and obj.type == 'ARMATURE' and 
                context.mode in {'POSE', 'EDIT_ARMATURE'})

    def draw(self, context):
        layout = self.layout
        obj = context.object
        arm = obj.data

        if context.mode == 'POSE':
            bones = context.selected_pose_bones_from_active_object
            source = "pose"
        else:
            bones = context.selected_editable_bones
            source = "edit"

        if not bones:
            layout.label(text="Selecione pelo menos um osso", icon='INFO')
            return

        layout.label(text=f"{len(bones)} osso(s) selecionado(s)", icon='BONE_DATA')

        for bone in bones:
            box = layout.box()

            row = box.row(align=True)
            row.label(text=bone.name, icon='BONE_DATA')

            if source == "pose":
                real_bone = bone.bone
            else:
                real_bone = bone

            col = box.column(align=True)

            col.prop(real_bone, "name", text="Nome")

            col.prop(real_bone, "display_type", text="Display As")

            col.prop(real_bone, "bbone_segments", text="Subdivisões")

            col.separator()
            col.prop(real_bone, "use_deform", text="Deform")
            col.prop(real_bone, "use_connect", text="Connected")
            col.prop(real_bone, "use_inherit_rotation", text="Inherit Rotation")
            col.prop(real_bone, "use_inherit_scale", text="Inherit Scale")

            col.separator()
            col.label(text="Bone Color", icon='COLOR')

            col.prop(real_bone.color, "palette", text="Palette")

            if real_bone.color.palette == 'CUSTOM':
                subcol = col.column(align=True)
                subcol.prop(real_bone.color.custom, "regular", text="Regular")
                subcol.prop(real_bone.color.custom, "selected", text="Selected")
                subcol.prop(real_bone.color.custom, "active", text="Active")

# Registro
classes = (
    VIEW3D_PT_bone_manager,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
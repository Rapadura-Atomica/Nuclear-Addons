bl_info = {
    "name": "Hierarquia",
    "author": "Rapadura Atomica LTDA",
    "version": (1, 3),
    "blender": (4, 0, 0),
    "location": "3D View > Pose Mode",
    "description": "Seleciona o bone pai com Shift+B",
    "category": "Animation",
}

import bpy
from bpy.types import Operator

class OBJECT_OT_select_parent_bone(Operator):
    """Seleciona o bone pai na hierarquia"""
    bl_idname = "object.select_parent_bone"
    bl_label = "Select Parent Bone"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        # Apenas funciona em modo Pose com bones selecionados
        return (context.object and 
                context.object.type == 'ARMATURE' and 
                context.object.mode == 'POSE' and 
                context.selected_pose_bones)
    
    def execute(self, context):
        armature = context.object
        selected_bones = context.selected_pose_bones
        
        # Guarda os nomes dos bones selecionados originalmente
        original_selection = [bone.name for bone in selected_bones]
        
        # Limpa a seleção atual
        bpy.ops.pose.select_all(action='DESELECT')
        
        # Para cada bone selecionado, seleciona seu pai
        parents_selected = []
        for bone in selected_bones:
            if bone.parent:
                bone.parent.select = True
                parents_selected.append(bone.parent.name)
        
        if not parents_selected:
            self.report({'WARNING'}, "Nenhum dos bones selecionados tem pai")
            # Restaura seleção original
            for bone_name in original_selection:
                if bone_name in armature.pose.bones:
                    armature.pose.bones[bone_name].select = True
            return {'CANCELLED'}
        
        # Atualiza a viewport
        context.view_layer.update()
        
        self.report({'INFO'}, f"Selecionado(s): {', '.join(parents_selected)}")
        return {'FINISHED'}

# Keymap
addon_keymaps = []

def register():
    bpy.utils.register_class(OBJECT_OT_select_parent_bone)
    
    # Configurar atalho de teclado
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    
    if kc:
        km = kc.keymaps.new(name='Pose', space_type='EMPTY')
        kmi = km.keymap_items.new(
            OBJECT_OT_select_parent_bone.bl_idname,
            'BACK_SLASH',
            'PRESS',
            shift=True,  # Shift+B
            ctrl=False,
            alt=False
        )
        addon_keymaps.append((km, kmi))

def unregister():
    # Remover atalhos
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    
    bpy.utils.unregister_class(OBJECT_OT_select_parent_bone)

if __name__ == "__main__":
    register()
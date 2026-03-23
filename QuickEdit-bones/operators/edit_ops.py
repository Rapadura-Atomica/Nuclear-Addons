# SPDX-License-Identifier: GPL-3.0-or-later
"""
Operadores de edição para bones (Delete, Select All, Flip, Rotate)
"""

import bpy
from math import pi

from ..core.bone_manager import BoneManager


class POSE_OT_delete_selected_bones(bpy.types.Operator):
    """Deleta os bones selecionados"""
    bl_idname = "pose.delete_selected_bones"
    bl_label = "Delete Selected Bones"
    bl_description = "Deleta todos os bones selecionados"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj and obj.type == 'ARMATURE' and obj.mode == 'POSE'

    def execute(self, context):
        obj = BoneManager.get_active_armature(context)
        if not obj:
            self.report({'ERROR'}, "Nenhuma armature ativa")
            return {'CANCELLED'}
        
        bpy.ops.object.mode_set(mode='EDIT')
        
        deleted_count = 0
        for bone in obj.data.edit_bones:
            if bone.select:
                obj.data.edit_bones.remove(bone)
                deleted_count += 1
        
        bpy.ops.object.mode_set(mode='POSE')
        
        self.report({'INFO'}, f"{deleted_count} bones deletados")
        return {'FINISHED'}


class POSE_OT_select_all_bones(bpy.types.Operator):
    """Seleciona ou desseleciona todos os bones"""
    bl_idname = "pose.select_all_bones"
    bl_label = "Select All Bones"
    bl_description = "Selecionar ou desselecionar todos os bones"
    bl_options = {'REGISTER', 'UNDO'}
    
    action: bpy.props.EnumProperty(
        name="Action",
        items=[
            ('SELECT', "Select", "Selecionar todos"),
            ('DESELECT', "Deselect", "Desselecionar todos"),
        ],
        default='SELECT'
    )

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj and obj.type == 'ARMATURE' and obj.mode == 'POSE'

    def execute(self, context):
        obj = BoneManager.get_active_armature(context)
        if not obj:
            return {'CANCELLED'}
        
        select = (self.action == 'SELECT')
        for bone in obj.pose.bones:
            bone.bone.select = select
        
        return {'FINISHED'}


class POSE_OT_flip_bones_horizontal(bpy.types.Operator):
    """Flip horizontal dos bones selecionados"""
    bl_idname = "pose.flip_bones_horizontal"
    bl_label = "Flip Bones Horizontal"
    bl_description = "Espelha horizontalmente os bones selecionados"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj and obj.type == 'ARMATURE' and obj.mode == 'POSE'

    def execute(self, context):
        bpy.ops.transform.mirror(constraint_axis=(True, False, False))
        return {'FINISHED'}


class POSE_OT_flip_bones_vertical(bpy.types.Operator):
    """Flip vertical dos bones selecionados"""
    bl_idname = "pose.flip_bones_vertical"
    bl_label = "Flip Bones Vertical"
    bl_description = "Espelha verticalmente os bones selecionados"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj and obj.type == 'ARMATURE' and obj.mode == 'POSE'

    def execute(self, context):
        bpy.ops.transform.mirror(constraint_axis=(False, True, False))
        return {'FINISHED'}


class POSE_OT_rotate_bones_90(bpy.types.Operator):
    """Rotação de 90° dos bones selecionados"""
    bl_idname = "pose.rotate_bones_90"
    bl_label = "Rotate Bones 90°"
    bl_description = "Rotaciona 90° os bones selecionados"
    bl_options = {'REGISTER', 'UNDO'}
    
    direction: bpy.props.EnumProperty(
        items=[
            ('CW', "Clockwise", "Rotação horária (90°)"),
            ('CCW', "Counter Clockwise", "Rotação anti-horária (90°)"),
        ],
        default='CW'
    )

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj and obj.type == 'ARMATURE' and obj.mode == 'POSE'

    def execute(self, context):
        angle = pi / 2 if self.direction == 'CW' else -pi / 2
        bpy.ops.transform.rotate(value=angle)
        return {'FINISHED'}


class POSE_OT_copy_bones(bpy.types.Operator):
    """Copia os bones selecionados"""
    bl_idname = "pose.copy_bones"
    bl_label = "Copy Bones"
    bl_description = "Copia os bones selecionados"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj and obj.type == 'ARMATURE' and obj.mode == 'POSE'

    def execute(self, context):
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.armature.copy()
        bpy.ops.object.mode_set(mode='POSE')
        self.report({'INFO'}, "Bones copiados")
        return {'FINISHED'}


class POSE_OT_paste_bones(bpy.types.Operator):
    """Cola os bones copiados"""
    bl_idname = "pose.paste_bones"
    bl_label = "Paste Bones"
    bl_description = "Cola os bones copiados"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj and obj.type == 'ARMATURE' and obj.mode == 'POSE'

    def execute(self, context):
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.armature.paste()
        bpy.ops.object.mode_set(mode='POSE')
        self.report({'INFO'}, "Bones colados")
        return {'FINISHED'}


class POSE_OT_cut_bones(bpy.types.Operator):
    """Recorta os bones selecionados"""
    bl_idname = "pose.cut_bones"
    bl_label = "Cut Bones"
    bl_description = "Recorta os bones selecionados"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj and obj.type == 'ARMATURE' and obj.mode == 'POSE'

    def execute(self, context):
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.armature.copy()
        
        # Deletar selecionados
        for bone in context.object.data.edit_bones:
            if bone.select:
                context.object.data.edit_bones.remove(bone)
        
        bpy.ops.object.mode_set(mode='POSE')
        self.report({'INFO'}, "Bones recortados")
        return {'FINISHED'}


class POSE_OT_toggle_bone_highlight(bpy.types.Operator):
    """Alterna o highlight visual dos bones selecionados"""
    bl_idname = "pose.toggle_bone_highlight"
    bl_label = "Toggle Bone Highlight"
    bl_description = "Ativa/desativa o highlight dos bones selecionados"

    def execute(self, context):
        from ..ui.visual_feedback import BoneHighlighter
        BoneHighlighter.toggle()
        context.area.tag_redraw()
        return {'FINISHED'}


class POSE_OT_activate_select_tool(bpy.types.Operator):
    """Ativa a ferramenta de seleção por caixa"""
    bl_idname = "pose.activate_select_tool"
    bl_label = "Activate Select Tool"
    bl_description = "Ativa a ferramenta de seleção por caixa"

    def execute(self, context):
        BoneManager.activate_tool("pose.wst_select_tool")
        return {'FINISHED'}


class POSE_OT_activate_lasso_tool(bpy.types.Operator):
    """Ativa a ferramenta de seleção por lasso"""
    bl_idname = "pose.activate_lasso_tool"
    bl_label = "Activate Lasso Tool"
    bl_description = "Ativa a ferramenta de seleção por lasso"

    def execute(self, context):
        BoneManager.activate_tool("pose.wst_lasso_tool")
        return {'FINISHED'}
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Painéis UI para o addon de transformação de bones
"""

import bpy
from bpy.types import Panel

from ..core.bone_manager import BoneManager
from ..core import constants


class POSE_PT_quick_edit_tools(Panel):
    """Painel minimalista com ferramentas essenciais para bones"""
    bl_label = "Quick Edit Bones"
    bl_idname = "POSE_PT_quick_edit_tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "QuickEdit"
    bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj and obj.type == 'ARMATURE' and obj.mode == 'POSE'

    def draw(self, context):
        layout = self.layout
        
        # Seção 1: Ferramentas de Seleção
        box = layout.box()
        row = box.row(align=True)
        row.label(text="Seleção:", icon='RESTRICT_SELECT_OFF')
        
        col = box.column(align=True)
        row = col.row(align=True)
        row.operator("pose.activate_select_tool", text="", icon='RESTRICT_SELECT_OFF')
        row.operator("pose.activate_lasso_tool", text="", icon='GP_SELECT_POINTS')
        
        # Se houver seleção, mostrar botão da BBox
        selected_bones, _, _, _ = BoneManager.get_selected_bones(context)
        if selected_bones:
            col.operator("pose.bbox_transform_bones", text="Transformar", icon='ORIENTATION_GLOBAL')
        
        # Seção 2: Transformações Rápidas
        box = layout.box()
        box.label(text="Transformações:", icon='ORIENTATION_GLOBAL')
        
        # Flip Horizontal/Vertical
        row = box.row(align=True)
        row.operator("pose.flip_bones_horizontal", text="Flip H", icon='ARROW_LEFTRIGHT')
        row.operator("pose.flip_bones_vertical", text="Flip V", icon='ARROW_LEFTRIGHT')
        
        # Rotação rápida
        row = box.row(align=True)
        op = row.operator("pose.rotate_bones_90", text="↶ 90°", icon='LOOP_BACK')
        op.direction = 'CCW'
        op = row.operator("pose.rotate_bones_90", text="↷ 90°", icon='LOOP_FORWARDS')
        op.direction = 'CW'
        
        # Seção 3: Clipboard
        box = layout.box()
        box.label(text="Clipboard:", icon='PASTEDOWN')
        
        row = box.row(align=True)
        row.operator("pose.copy_bones", text="", icon='COPYDOWN')
        row.operator("pose.cut_bones", text="", icon='TRASH')
        row.operator("pose.paste_bones", text="", icon='PASTEDOWN')
        
        # Seção 4: Ações Rápidas
        box = layout.box()
        box.label(text="Ações:", icon='PLAY')
        
        row = box.row(align=True)
        row.operator("pose.delete_selected_bones", text="", icon='TRASH')
        row.operator("pose.select_all_bones", text="Sel All", icon='SELECT_SET')
        row.operator("pose.select_all_bones", text="Desel", icon='SELECT_DIFFERENCE').action = 'DESELECT'

        # Seção 5: Visual
        box = layout.box()
        row = box.row(align=True)
        row.label(text="Visual:", icon='HIDE_OFF')
        
        from .visual_feedback import BoneHighlighter
        icon = 'HIDE_ON' if BoneHighlighter._enabled else 'HIDE_OFF'
        text = "Ocultar Highlight" if BoneHighlighter._enabled else "Mostrar Highlight"
        
        row.operator("pose.toggle_bone_highlight", text=text, icon=icon)


class POSE_PT_bbox_display(Panel):
    """Painel que aparece apenas quando a BBox está ativa"""
    bl_label = "BBox Controls"
    bl_idname = "POSE_PT_bbox_display"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "QuickEdit"
    bl_parent_id = "POSE_PT_quick_edit_tools"
    
    @classmethod
    def poll(cls, context):
        return constants._bbox_data is not None
    
    def draw(self, context):
        layout = self.layout
        layout.label(text="BBox Ativa", icon='VIEW_PAN')
        
        row = layout.row(align=True)
        row.operator("pose.delete_selected_bones", text="Del", icon='TRASH')
        row.operator("pose.copy_bones", text="Copy", icon='COPYDOWN')
        row.operator("pose.paste_bones", text="Paste", icon='PASTEDOWN')
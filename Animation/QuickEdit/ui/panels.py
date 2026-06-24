import bpy
from bpy.types import Panel

class GPENCIL_PT_quick_edit_tools(Panel):
    """Painel minimalista com ferramentas essenciais de Quick Edit"""
    bl_label = "Quick Edit"
    bl_idname = "GPENCIL_PT_quick_edit_tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "QuickEdit"
    bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(cls, context):
        # Mostrar apenas quando um objeto Grease Pencil está selecionado
        from ..compatibility.api_router import obj_is_gp
        return context.object and obj_is_gp(context.object)

    def draw(self, context):
        from ..core.tool_manager import GPToolManager
        
        layout = self.layout
        obj = context.object
        
        # Seção 1: Ferramentas de Seleção (Compacta)
        box = layout.box()
        row = box.row(align=True)
        row.label(text="Seleção:", icon='RESTRICT_SELECT_OFF')
        
        col = box.column(align=True)
        row = col.row(align=True)
        row.operator("gpencil.activate_select_tool", text="", icon='RESTRICT_SELECT_OFF')
        row.operator("gpencil.activate_lasso_tool", text="", icon='GP_SELECT_POINTS')
        
        # Se houver seleção, mostrar botão da BBox
        world_points, _, _ = GPToolManager.get_selected_points(context)
        if world_points:
            col.operator("gpencil.bbox_transform", text="Transformar", icon='ORIENTATION_GLOBAL')
        
        # Seção 2: Transformações Rápidas (Flip, Rotate, Scale)
        box = layout.box()
        box.label(text="Transformações:", icon='ORIENTATION_GLOBAL')
        
        # Flip Horizontal/Vertical
        row = box.row(align=True)
        row.operator("gpencil.flip_horizontal", text="Flip H", icon='ARROW_LEFTRIGHT')
        row.operator("gpencil.flip_vertical", text="Flip V", icon='ARROW_LEFTRIGHT').direction = 'VERTICAL'
        
        # Rotação rápida (90°)
        row = box.row(align=True)
        op = row.operator("gpencil.rotate_90", text="↶ 90°", icon='LOOP_BACK')
        op.direction = 'CCW'
        op = row.operator("gpencil.rotate_90", text="↷ 90°", icon='LOOP_FORWARDS')
        op.direction = 'CW'
        
        # Seção 3: Clipboard (Copy, Cut, Paste)
        box = layout.box()
        box.label(text="Clipboard:", icon='PASTEDOWN')
        
        row = box.row(align=True)
        row.operator("gpencil.copy_strokes", text="", icon='COPYDOWN')
        row.operator("gpencil.cut_strokes_simple", text="", icon='TRASH')
        row.operator("gpencil.paste_strokes", text="", icon='PASTEDOWN')
        
        # Seção 4: Ações Rápidas (Delete, Select All)
        box = layout.box()
        box.label(text="Ações:", icon='PLAY')
        
        row = box.row(align=True)
        row.operator("gpencil.delete_selected_strokes", text="", icon='TRASH')
        row.operator("gpencil.select_all", text="Sel All", icon='SELECT_SET').action = 'SELECT'
        row.operator("gpencil.select_all", text="Desel", icon='SELECT_DIFFERENCE').action = 'DESELECT'

        box = layout.box()
        row = box.row(align=True)
        row.label(text="Visual:", icon='HIDE_OFF')
        
        from .visual_feedback import StrokeHighlighter
        icon = 'HIDE_ON' if StrokeHighlighter._enabled else 'HIDE_OFF'
        text = "Ocultar Highlight" if StrokeHighlighter._enabled else "Mostrar Highlight"
        
        row.operator("gpencil.toggle_stroke_highlight", text=text, icon=icon)

class GPENCIL_PT_bbox_display(Panel):
    """Painel que aparece apenas quando a BBox está ativa"""
    bl_label = "BBox Controls"
    bl_idname = "GPENCIL_PT_bbox_display"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "QuickEdit"
    bl_parent_id = "GPENCIL_PT_quick_edit_tools"
    
    @classmethod
    def poll(cls, context):
        # Mostrar apenas quando a BBox está ativa
        from ..core import constants
        return constants._bbox_data is not None
    
    def draw(self, context):
        layout = self.layout
        layout.label(text="BBox Ativa", icon='VIEW_PAN')
        
        # Ações rápidas enquanto a BBox está ativa
        row = layout.row(align=True)
        row.operator("gpencil.delete_selected_strokes", text="Del", icon='TRASH')
        row.operator("gpencil.copy_strokes", text="Copy", icon='COPYDOWN')
        row.operator("gpencil.cut_strokes_simple", text="Cut", icon='CUT')
        row.operator("gpencil.paste_strokes", text="Paste", icon='PASTEDOWN')
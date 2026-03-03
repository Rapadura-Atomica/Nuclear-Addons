import bpy
from ..core import constants

def register():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        constants.addon_keymaps.clear()
        
        km = kc.keymaps.new(name='Grease Pencil', space_type='EMPTY')
        
        # Ferramentas principais
        km.keymap_items.new("gpencil.activate_select_tool", 'Q', 'PRESS')
        km.keymap_items.new("gpencil.activate_bbox_tool", 'W', 'PRESS') 
        km.keymap_items.new("gpencil.activate_lasso_tool", 'E', 'PRESS')

        # Clipboard
        km.keymap_items.new("gpencil.copy_strokes", 'C', 'PRESS', ctrl=True)
        km.keymap_items.new("gpencil.paste_strokes", 'V', 'PRESS', ctrl=True)

        # Delete
        km.keymap_items.new("gpencil.delete_selected_strokes", 'DEL', 'PRESS')
        km.keymap_items.new("gpencil.delete_selected_points", 'DEL', 'PRESS', shift=True)

        # Toggle select mode
        km.keymap_items.new("gpencil.toggle_select_mode", 'TAB', 'PRESS')
        
        # NOVO: Shift + Clique para seleção múltipla
        km.keymap_items.new("gpencil.shift_select_strokes", 'LEFTMOUSE', 'PRESS', shift=True)

        # CTRL X
        km.keymap_items.new("gpencil.cut_strokes_simple", 'X', 'PRESS', ctrl=True)
        
        # Registrar para limpeza
        for kmi in km.keymap_items:
            constants.addon_keymaps.append((km, kmi))

        print("QuickEdit: Keymaps registrados!")

def unregister():
    for km, kmi in constants.addon_keymaps:
        try:
            km.keymap_items.remove(kmi)
        except:
            pass
    constants.addon_keymaps.clear()
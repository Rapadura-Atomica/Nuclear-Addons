# SPDX-License-Identifier: GPL-3.0-or-later
"""
Configuração de keymaps para modo Pose
"""

import bpy
from ..core import constants


def register():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        constants.addon_keymaps.clear()
        
        # Keymap para modo Pose
        km = kc.keymaps.new(name='Pose', space_type='EMPTY')
        
        # Ferramentas principais
        km.keymap_items.new("pose.activate_select_tool", 'Q', 'PRESS')
        km.keymap_items.new("pose.activate_bbox_tool", 'W', 'PRESS') 
        km.keymap_items.new("pose.activate_lasso_tool", 'E', 'PRESS')

        # Clipboard
        km.keymap_items.new("pose.copy_bones", 'C', 'PRESS', ctrl=True)
        km.keymap_items.new("pose.paste_bones", 'V', 'PRESS', ctrl=True)
        km.keymap_items.new("pose.cut_bones", 'X', 'PRESS', ctrl=True)

        # Delete
        km.keymap_items.new("pose.delete_selected_bones", 'DEL', 'PRESS')
        
        # Select all
        km.keymap_items.new("pose.select_all_bones", 'A', 'PRESS')
        km.keymap_items.new("pose.select_all_bones", 'A', 'PRESS', ctrl=True)
        
        # Shift + Clique para seleção múltipla (delegado ao operador padrão)
        
        # Registrar para limpeza
        for kmi in km.keymap_items:
            constants.addon_keymaps.append((km, kmi))

        print("QuickEdit Bones: Keymaps registrados!")


def unregister():
    for km, kmi in constants.addon_keymaps:
        try:
            km.keymap_items.remove(kmi)
        except:
            pass
    constants.addon_keymaps.clear()
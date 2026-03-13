# SPDX-License-Identifier: GPL-3.0-or-later

bl_info = {
    "name": "TimeOffset Tool",
    "author": "Rapadura Atomica Ltda.",
    "version": (2, 4, 0),
    "blender": (5, 0, 0),
    "location": "View3D > Sidebar > TimeOffset",
    "description": "Ferramentas práticas para manipulação de drawings com modificador TimeOffset",
    "category": "Animation",
}

import bpy
from . import api_route as gp_api
from .operators import ops as opers

def register_alternative_apis():
    """Registra APIs alternativas para compatibilidade"""
    try:
        gp_api.register_alternative_api_paths()
    except Exception as e:
        print(f"Warning: Could not register alternative APIs: {e}")

def unregister_alternative_apis():
    """Remove APIs alternativas"""
    try:
        gp_api.unregister_alternative_api_paths()
    except Exception as e:
        print(f"Warning: Could not unregister alternative APIs: {e}")

def register_keymaps():
    """Registra os keymaps personalizados"""
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name="Grease Pencil", space_type='EMPTY')
        keymaps = []
        # Keymap para frame anterior na biblioteca
        kmi_prev = km.keymap_items.new(
            "time_offset.navigate_previous",
            type='COMMA',
            value='PRESS',
            shift=False
        )
        keymaps.append((km, kmi_prev))
        # Keymap para próximo frame na biblioteca
        kmi_next = km.keymap_items.new(
            "time_offset.navigate_next",
            type='PERIOD',
            value='PRESS',
            shift=False
        )
        keymaps.append((km, kmi_next))
        # Keymaps para navegação de keyframes (com Shift)
        kmi_prev_key = km.keymap_items.new(
            "time_offset.previous_keyframe",
            type='COMMA',
            value='PRESS',
            shift=True
        )
        keymaps.append((km, kmi_prev_key))
        kmi_next_key = km.keymap_items.new(
            "time_offset.next_keyframe",
            type='PERIOD',
            value='PRESS',
            shift=True
        )
        keymaps.append((km, kmi_next_key))

        # Novo atalho para Flip Horizontal (NUMPAD_4)
        kmi_flip = km.keymap_items.new(
            "time_offset.flip_horizontal",
            type='NUMPAD_4',
            value='PRESS'
        )
        keymaps.append((km, kmi_flip))

        kmi_flip_obj = km.keymap_items.new(
        # Flip de objeto
            "time_offset.flip_horizontal_object",
            type='NUMPAD_4',
            value='PRESS'
        )
        keymaps.append((km, kmi_flip_obj))

        # Insert Keyframe
        kmi_insert = km.keymap_items.new(
            "time_offset.insert_keyframe_timeline",
            type='F6',
            value='PRESS'
        )
        keymaps.append((km, kmi_insert))

        # Remove Keyframe
        kmi_remove = km.keymap_items.new(
            "time_offset.remove_keyframe_timeline",
            type='F7',
            value='PRESS'
        )
        keymaps.append((km, kmi_remove))

        return keymaps
    return []

def unregister_keymaps(keymaps):
    """Remove os keymaps personalizados"""
    for km, kmi in keymaps:
        km.keymap_items.remove(kmi)

keymaps = []

def register():
    """Registra o addon"""
    register_alternative_apis()
    global keymaps
    keymaps = register_keymaps()
    for cls in opers.classes:
        bpy.utils.register_class(cls)
    print("TimeOffset Tool v2.2.0 registrado com sucesso!")

def unregister():
    """Desregistra o addon"""
    unregister_alternative_apis()
    global keymaps
    unregister_keymaps(keymaps)
    for cls in reversed(opers.classes):
        bpy.utils.unregister_class(cls)
    print("TimeOffset Tool desregistrado!")

if __name__ == "__main__":
    register()
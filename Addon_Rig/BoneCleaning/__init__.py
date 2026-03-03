# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025, Rapadura Atômica. All rights reserved.

bl_info = {
    "name": "Cutout Pen - Mega Utilities",
    "author": "Rapadura Atômica LTDA",
    "version": (2, 0),
    "blender": (4, 0, 0),
    "location": "View3D > UI > Cutout Pen",
    "description": "Addon para animação Cutout com Grease Pencil",
    "category": "Animation",
}

import bpy
from . import (
    properties,
    preferences,
    panel_ui,
    bone_collections_ui,
    bone_buttons_ui,
)

modules = (
    properties,
    preferences,
    bone_collections_ui,
    bone_buttons_ui,
    panel_ui,
)

def register():
    for module in modules:
        if hasattr(module, 'register'):
            module.register()
    
    bpy.types.Scene.gp_cutout_bone_buttons = bpy.props.CollectionProperty(
        type=properties.GP_CUTOUT_BoneButtonItem
    )
    bpy.types.Scene.gp_cutout_bone_buttons_index = bpy.props.IntProperty(default=0)
    
    #bpy.app.handlers.depsgraph_update_post.append(bone_buttons_ui.bone_button_handler)
    
    print("Cutout Pen Mega Utilities registered successfully.")

def unregister():
    if bone_buttons_ui.bone_button_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(bone_buttons_ui.bone_button_handler)
    
    for module in reversed(modules):
        if hasattr(module, 'unregister'):
            module.unregister()
    
    try:
        del bpy.types.Scene.gp_cutout_bone_buttons
        del bpy.types.Scene.gp_cutout_bone_buttons_index
    except:
        pass
    
    print("Cutout Pen Mega Utilities unregistered.")

if __name__ == "__main__":
    register()
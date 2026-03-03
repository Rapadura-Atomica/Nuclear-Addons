# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025, Rapadura Atômica. All rights reserved.

import bpy

class GP_CUTOUT_BoneButtonItem(bpy.types.PropertyGroup):
    """Item para armazenar o mapeamento osso-botão -> collection"""
    name: bpy.props.StringProperty(
        name="Button Name",
        description="Name for this bone button",
        default=""
    ) #type: ignore
    
    bone_name: bpy.props.StringProperty(
        name="Bone Name",
        description="Name of the bone that will act as a button",
        default=""
    ) #type: ignore
    
    target_collection: bpy.props.StringProperty(
        name="Target Collection",
        description="Name of the bone collection to show when clicked",
        default=""
    ) #type: ignore
    
    icon: bpy.props.StringProperty(
        name="Icon",
        description="Icon for UI display",
        default="LAYER_ACTIVE"
    ) #type: ignore

def register():
    bpy.utils.register_class(GP_CUTOUT_BoneButtonItem)

def unregister():
    bpy.utils.unregister_class(GP_CUTOUT_BoneButtonItem)
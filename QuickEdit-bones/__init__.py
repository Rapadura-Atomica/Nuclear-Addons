# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025, Rapadura Atômica. All rights reserved.

bl_info = {
    "name": "Quick Edit para Bones",
    "author": "Rapadura Atomica LTDA.",
    "version": (1, 0),
    "blender": (4, 4, 0),
    "location": "View3D > Toolbar > QuickEdit",
    "description": "Transformação interativa de bones com bounding box",
    "category": "Animation",
}

from . import auto_load

def register():
    auto_load.init()
    auto_load.register()

def unregister():
    auto_load.unregister()
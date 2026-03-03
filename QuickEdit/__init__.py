# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025, Rapadura Atômica. All rights reserved.

bl_info = {
    "name": "Quick Edit para Strokes",
    "author": "Rapadura Atomica LTDA.",
    "version": (2, 0),
    "blender": (4, 4, 0),
    "location": "View3D > Toolbar > GPencil Tools",
    "description": "Quick Edit para Drawings",
    "category": "Grease Pencil",
}

from . import auto_load

def register():
    auto_load.init()
    auto_load.register()

def unregister():
    auto_load.unregister()
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2023, Rapadura Atômica. All rights reserved.

from nuclear import (
    animation,
    drawing,
    gpencil_references,
    keymaps,
    preferences,
)

bl_info = {
    "name": "Nuclear",
    "author": "Rapadura Atômica LTDA",
    "website": "https://github.com/Rapadura-Atomica",
    "description": "2D Animation Workflow Revolution - Advanced Grease Pencil Tools",
    "blender": (4, 4, 0),
    "version": (1, 0, 0),
    "location": "View3D > Sidebar > Nuclear",
    "warning": "",
    "category": "Animation",
}

packages = (
    drawing,
    animation,
    gpencil_references,
    preferences,
    keymaps,
)

def register():
    for package in packages:
        package.register()


def unregister():
    for package in packages:
        package.unregister()

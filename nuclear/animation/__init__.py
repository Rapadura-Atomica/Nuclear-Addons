# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2023, Rapadura Atômica. All rights reserved.
import bpy

def register():
    # 1. Registrar core (propriedades) primeiro
    from .core import register as register_core
    register_core()
    
    # 2. Registrar operadores
    from . import ops
    ops.register()
    
    # 3. Registrar UI
    from . import ui
    ui.register()

def unregister():
    from . import ui, ops
    ui.unregister()
    ops.unregister()
    
    from .core import unregister as unregister_core
    unregister_core()
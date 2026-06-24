# SPDX-License-Identifier: GPL-3.0-or-later

from . import api_router

def register():
    api_router.register_alternative_api_paths()

def unregister():
    api_router.unregister_alternative_api_paths()
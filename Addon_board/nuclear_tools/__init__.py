import bpy

bl_info = {
    "name" : "Nuclear Tools",
    "Author" : "Rapadura Atômica Ltda",
    "description" : "Addon de suavização de traços",
    "blender" : (3, 3, 0),
    "version" : (1, 0, 0),
    "location" : "View3D > Sidebar > Nuclear_Tools",
    "category" : "Object"
}

from . import auto_load
from .api_router import register_alternative_api_paths, unregister_alternative_api_paths
from .ui_viewport_tools import *

auto_load.init()

def register():
    auto_load.register()

    # Propriedades
    bpy.types.Scene.nijigp_working_plane = bpy.props.EnumProperty(
        name='Working Plane',
        items=[
            ('X-Z', 'Front (X-Z)', ''),
            ('Y-Z', 'Side (Y-Z)', ''),
            ('X-Y', 'Top (X-Y)', ''),
            ('VIEW', 'View', 'Use the current view as the 2D working plane'),
            ('AUTO', 'Auto', 'Calculate the 2D plane automatically based on input points and view angle')
        ],
        default='AUTO'
    )
    bpy.types.Scene.nijigp_working_plane_layer_transform = bpy.props.BoolProperty(default=True)

    register_viewport_tools()
    register_alternative_api_paths()

    custom_lib_path = bpy.context.preferences.addons[__package__].preferences.custom_lib_path
    if len(custom_lib_path) > 0:
        import sys
        sys.path.append(custom_lib_path)
        
def unregister():
    auto_load.unregister()    
    unregister_viewport_tools()
    unregister_alternative_api_paths()
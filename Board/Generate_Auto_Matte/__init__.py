import bpy
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

bl_info = {
    "name" : "Generate Auto Matte",
    "author" : "Rapadura Atômica LTDA (baseado em nijiGPen de chsh2)",
    "website" : "https://github.com/Rapadura-Atomica",
    "description" : "Board/storyboard toolkit: one-click matte generation (fills every closed region with a flat color) plus automatic line cleanup (merge rough sketch strokes into clean lines, single or multi-line).",
    "blender" : (4, 3, 0),
    "version" : (1, 3, 0),
    "location" : "View3D > Sidebar > Auto Matte, in Grease Pencil Draw/Edit modes",
    "category" : "Object"
}

from . import auto_load
from .api_router import register_alternative_api_paths, unregister_alternative_api_paths

auto_load.init()

def register():
    auto_load.register()
    # The 2D working plane shared by the core geometry helpers inherited from nijiGPen.
    # Names are kept as-is so the reused utils.py does not need to be modified.
    bpy.types.Scene.nijigp_working_plane = bpy.props.EnumProperty(
                        name='Working Plane',
                        items=[('X-Z', 'Front (X-Z)', ''),
                                ('Y-Z', 'Side (Y-Z)', ''),
                                ('X-Y', 'Top (X-Y)', ''),
                                ('VIEW', 'View', 'Use the current view as the 2D working plane'),
                                ('AUTO', 'Auto', 'Calculate the 2D plane automatically based on input points and view angle')],
                        default='AUTO',
                        description='The 2D (local) plane that the matte generator works on'
                        )
    bpy.types.Scene.nijigp_working_plane_layer_transform = bpy.props.BoolProperty(
                        default=True,
                        description="Take the active layer's transform into consideration when calculating the view angle"
                        )
    register_alternative_api_paths()

def unregister():
    auto_load.unregister()
    unregister_alternative_api_paths()
    del bpy.types.Scene.nijigp_working_plane
    del bpy.types.Scene.nijigp_working_plane_layer_transform

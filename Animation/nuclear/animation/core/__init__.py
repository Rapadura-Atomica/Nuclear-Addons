import bpy

from .properties import (
    register as register_properties,
    unregister as unregister_properties,
    register_grease_pencil_properties,
    unregister_grease_pencil_properties
)

def register():
    register_properties()  # Registra as classes PropertyGroup
    register_grease_pencil_properties()  # Registra as propriedades no GreasePencil

def unregister():
    unregister_grease_pencil_properties()
    unregister_properties()
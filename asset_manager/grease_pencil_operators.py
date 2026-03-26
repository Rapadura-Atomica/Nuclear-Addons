# grease_pencil_operators.py
"""
Operadores para interação com a biblioteca Grease Pencil
"""

import bpy
from bpy.props import StringProperty, BoolProperty, EnumProperty
from .grease_pencil_library import GPLibrary


class GP_OT_add_current_to_library(bpy.types.Operator):
    """Adiciona o Grease Pencil selecionado à biblioteca"""
    bl_idname = "gp.add_current_to_library"
    bl_label = "Add Current Drawing to Library"
    bl_description = "Salva o desenho atual na biblioteca de poses"
    bl_options = {'REGISTER', 'UNDO'}
    
    pose_name: StringProperty(
        name="Pose Name",
        description="Nome para identificar esta pose",
        default="Nova Pose"
    )
    
    category: EnumProperty(
        name="Category",
        description="Categoria da pose",
        items=[
            ('hands', 'Hands', 'Mãos e gestos'),
            ('mouths', 'Mouths', 'Bocas e expressões'),
            ('eyes', 'Eyes', 'Olhos'),
            ('eyebrows', 'Eyebrows', 'Sobrancelhas'),
            ('head', 'Head', 'Cabeças'),
            ('body', 'Body', 'Corpos'),
            ('props', 'Props', 'Adereços'),
            ('expressions', 'Expressions', 'Expressões completas'),
            ('custom', 'Custom', 'Categoria personalizada')
        ],
        default='custom'
    )
    
    tags: StringProperty(
        name="Tags",
        description="Tags separadas por vírgula",
        default=""
    )
    
    description: StringProperty(
        name="Description",
        description="Descrição detalhada da pose",
        default=""
    )
    
    def execute(self, context):
        # Processar tags
        tags = [t.strip() for t in self.tags.split(',') if t.strip()]
        
        # Adicionar à biblioteca
        library = GPLibrary()
        success, message, pose_id = library.add_pose_from_current(
            name=self.pose_name,
            category=self.category,
            tags=tags,
            description=self.description
        )
        
        if success:
            self.report({'INFO'}, message)
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, message)
            return {'CANCELLED'}
    
    def invoke(self, context, event):
        # Preencher nome sugerido baseado no objeto atual
        if context.active_object and context.active_object.type == 'GREASEPENCIL':
            self.pose_name = context.active_object.name
        
        return context.window_manager.invoke_props_dialog(self, width=300)

class GP_OT_apply_pose(bpy.types.Operator):
    """Aplica uma pose da biblioteca ao objeto selecionado"""
    bl_idname = "gp.apply_pose"
    bl_label = "Apply Pose"
    bl_description = "Substitui o desenho atual pela pose selecionada"
    bl_options = {'REGISTER', 'UNDO'}
    
    pose_id: StringProperty()
    
    def execute(self, context):
        library = GPLibrary()
        
        # Verificar se há objeto selecionado
        if not context.active_object or context.active_object.type != 'GREASEPENCIL':
            self.report({'ERROR'}, "Selecione um objeto Grease Pencil")
            return {'CANCELLED'}
        
        # Aplicar pose
        success, message = library.swap_pose(context.active_object, self.pose_id)
        
        if success:
            self.report({'INFO'}, message)
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, message)
            return {'CANCELLED'}

class GP_OT_refresh_library(bpy.types.Operator):
    """Atualiza a biblioteca (recarrega o JSON)"""
    bl_idname = "gp.refresh_library"
    bl_label = "Refresh Library"
    bl_description = "Recarrega a biblioteca de poses"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        # Forçar recriação da biblioteca
        library = GPLibrary()
        # Atualizar UI
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        self.report({'INFO'}, f"Biblioteca atualizada: {len(library.poses)} poses")
        return {'FINISHED'}

class GP_OT_delete_pose(bpy.types.Operator):
    """Remove uma pose da biblioteca"""
    bl_idname = "gp.delete_pose"
    bl_label = "Delete Pose"
    bl_description = "Remove esta pose da biblioteca"
    bl_options = {'REGISTER', 'UNDO'}
    
    pose_id: StringProperty()
    
    def execute(self, context):
        library = GPLibrary()
        success, message = library.delete_pose(self.pose_id)
        
        if success:
            self.report({'INFO'}, message)
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, message)
            return {'CANCELLED'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)
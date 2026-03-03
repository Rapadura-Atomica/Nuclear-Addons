# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025, Rapadura Atômica. All rights reserved.

import bpy
from bpy_extras import view3d_utils

_modal_handler = None
_last_selected_bone = None  # ADICIONAR
_activation_key_pressed = False  # ADICIONAR

def start_modal_handler():
    """Inicia o handler modal"""
    global _modal_handler
    if not _modal_handler:
        bpy.ops.gp_cutout.activate_bone_button_modal('INVOKE_DEFAULT')
        _modal_handler = True

def stop_modal_handler():
    """Para o handler modal"""
    global _modal_handler
    _modal_handler = False

def show_only_collection(armature_obj, collection_name):
    """Mostra apenas a collection especificada, escondendo todas as outras"""
    for coll in armature_obj.data.collections:
        coll.is_visible = False
    
    target_coll = armature_obj.data.collections.get(collection_name)
    if target_coll:
        target_coll.is_visible = True

def show_all_collections(armature_obj):
    """Mostra todas as collections"""
    for coll in armature_obj.data.collections:
        coll.is_visible = True

class GP_CUTOUT_OT_activate_bone_button_modal(bpy.types.Operator):
    """Modal operator to detect bone selection + O key press"""
    bl_idname = "gp_cutout.activate_bone_button_modal"
    bl_label = "Activate Bone Button Modal"
    bl_options = {'REGISTER'}

    def modal(self, context, event):
        # Verifica se está no contexto certo
        if not (context.active_object and 
                context.active_object.type == 'ARMATURE' and
                context.mode == 'POSE'):
            return {'PASS_THROUGH'}
        
        # Tecla O para ativar bone buttons
        if event.type == 'O' and event.value == 'PRESS':
            selected_bones = context.selected_pose_bones
            if selected_bones and len(selected_bones) == 1:
                bone_name = selected_bones[0].name
                
                bone_buttons = context.scene.gp_cutout_bone_buttons
                armature_obj = context.active_object

                for button in bone_buttons:
                    if button.bone_name == bone_name and button.target_collection:
                        show_only_collection(armature_obj, button.target_collection)
                        self.report({'INFO'}, f"Showing: {button.target_collection}")
        
        # NOVO: Tecla P para mostrar todos os bones
        elif event.type == 'P' and event.value == 'PRESS':
            armature_obj = context.active_object
            if armature_obj and armature_obj.type == 'ARMATURE':
                show_all_collections(armature_obj)
                self.report({'INFO'}, "Showing all collections")

        if event.type in {'ESC'}:
            return {'CANCELLED'}
        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

class GP_CUTOUT_OT_create_bone_button(bpy.types.Operator):
    bl_idname = "gp_cutout.create_bone_button"
    bl_label = "Create Bone Button"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return (context.active_object and 
                context.active_object.type == 'ARMATURE' and
                context.mode == 'POSE' and
                context.selected_pose_bones)
    
    def execute(self, context):
        selected_bones = context.selected_pose_bones
        if not selected_bones:
            self.report({'ERROR'}, "No bone selected")
            return {'CANCELLED'}
        
        bone_name = selected_bones[0].name
        
        for button in context.scene.gp_cutout_bone_buttons:
            if button.bone_name == bone_name:
                self.report({'WARNING'}, f"Bone '{bone_name}' is already a button")
                return {'CANCELLED'}
       
        new_button = context.scene.gp_cutout_bone_buttons.add()
        new_button.name = f"Button_{bone_name}"
        new_button.bone_name = bone_name
        new_button.target_collection = ""  # Usuário vai definir depois
        
        self.report({'INFO'}, f"Created button from bone: {bone_name}")
        return {'FINISHED'}

class GP_CUTOUT_OT_remove_bone_button(bpy.types.Operator):
    """Remove bone button mapping"""
    bl_idname = "gp_cutout.remove_bone_button"
    bl_label = "Remove Bone Button"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return context.scene.gp_cutout_bone_buttons
    
    def execute(self, context):
        index = context.scene.gp_cutout_bone_buttons_index
        buttons = context.scene.gp_cutout_bone_buttons
        
        if 0 <= index < len(buttons):
            button_name = buttons[index].name
            buttons.remove(index)
            if index >= len(buttons):
                context.scene.gp_cutout_bone_buttons_index = max(0, len(buttons) - 1)
            
            self.report({'INFO'}, f"Button '{button_name}' removed")
        
        return {'FINISHED'}

class GP_CUTOUT_OT_test_bone_button(bpy.types.Operator):
    """Test the selected bone button"""
    bl_idname = "gp_cutout.test_bone_button"
    bl_label = "Test Button"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        index = context.scene.gp_cutout_bone_buttons_index
        buttons = context.scene.gp_cutout_bone_buttons
        
        if 0 <= index < len(buttons):
            button = buttons[index]
            armature_obj = context.active_object
            
            if armature_obj and armature_obj.type == 'ARMATURE':
                show_only_collection(armature_obj, button.target_collection)
                self.report({'INFO'}, f"Showing: {button.target_collection}")
        
        return {'FINISHED'}

class GP_CUTOUT_OT_show_all_collections(bpy.types.Operator):
    """Show all bone collections"""
    bl_idname = "gp_cutout.show_all_collections"
    bl_label = "Show All"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        armature_obj = context.active_object
        if armature_obj and armature_obj.type == 'ARMATURE':
            show_all_collections(armature_obj)
            self.report({'INFO'}, "Showing all collections")
        return {'FINISHED'}

class GP_CUTOUT_OT_start_modal_handler(bpy.types.Operator):
    """Start the modal key listener"""
    bl_idname = "gp_cutout.start_modal_handler"
    bl_label = "Start Key Listener"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        start_modal_handler()
        self.report({'INFO'}, "Modal handler started. Press O on bone buttons.")
        return {'FINISHED'}

class GP_CUTOUT_OT_stop_modal_handler(bpy.types.Operator):
    """Stop the modal key listener"""
    bl_idname = "gp_cutout.stop_modal_handler"
    bl_label = "Stop Key Listener"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        stop_modal_handler()
        self.report({'INFO'}, "Modal handler stopped.")
        return {'FINISHED'}

class VIEW3D_PT_gp_cutout_bone_buttons(bpy.types.Panel):
    """Panel for managing bone buttons"""
    bl_label = "Bone Buttons Manager"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Cutout Pen'
    bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(cls, context):
        return (context.active_object and 
                context.active_object.type == 'ARMATURE')
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        buttons = scene.gp_cutout_bone_buttons
        armature_obj = context.active_object
        
        # Status do handler modal
        row = layout.row()
        if _modal_handler:
            row.label(text="Modal Active: Press O on bone buttons", icon='PLAY')
            row.operator("gp_cutout.stop_modal_handler", text="Stop", icon='X')
        else:
            row.label(text="Modal Inactive", icon='PAUSE')
            row.operator("gp_cutout.start_modal_handler", text="Start", icon='PLAY')
        
        layout.separator()
        
        # Botão para criar novo osso-botão
        if context.mode == 'POSE' and context.selected_pose_bones:
            selected_bone = context.selected_pose_bones[0].name
            layout.operator("gp_cutout.create_bone_button", 
                          text=f"Create Button from: {selected_bone}", 
                          icon='BONE_DATA')
        else:
            layout.label(text="Select a bone in Pose Mode", icon='INFO')
        
        layout.separator()
        
        # Lista de botões existentes
        if buttons:
            for i, button in enumerate(buttons):
                box = layout.box()
                row = box.row()
                
                # Informações do botão
                col = row.column()
                col.label(text=f"Bone: {button.bone_name}", icon='BONE_DATA')
                col.label(text=f"Collection: {button.target_collection}", icon='OUTLINER_COLLECTION')
                
                # Configuração da collection
                if armature_obj:
                    row.prop_search(button, "target_collection", 
                                   armature_obj.data, "collections", 
                                   text="")
                
                # Botões de ação
                row = box.row(align=True)
                row.operator("gp_cutout.test_bone_button", text="Test", icon='PLAY')
                row.operator("gp_cutout.remove_bone_button", text="Remove", icon='X')
        
        # Botão para mostrar tudo
        layout.separator()
        layout.operator("gp_cutout.show_all_collections", text="Show All Collections", icon='RESTRICT_VIEW_OFF')

def register():
    bpy.utils.register_class(GP_CUTOUT_OT_activate_bone_button_modal)
    bpy.utils.register_class(GP_CUTOUT_OT_start_modal_handler)
    bpy.utils.register_class(GP_CUTOUT_OT_stop_modal_handler)
    bpy.utils.register_class(GP_CUTOUT_OT_create_bone_button)
    bpy.utils.register_class(GP_CUTOUT_OT_remove_bone_button)
    bpy.utils.register_class(GP_CUTOUT_OT_test_bone_button)
    bpy.utils.register_class(GP_CUTOUT_OT_show_all_collections)
    bpy.utils.register_class(VIEW3D_PT_gp_cutout_bone_buttons)

def unregister():
    bpy.utils.unregister_class(VIEW3D_PT_gp_cutout_bone_buttons)
    bpy.utils.unregister_class(GP_CUTOUT_OT_show_all_collections)
    bpy.utils.unregister_class(GP_CUTOUT_OT_test_bone_button)
    bpy.utils.unregister_class(GP_CUTOUT_OT_remove_bone_button)
    bpy.utils.unregister_class(GP_CUTOUT_OT_create_bone_button)
    bpy.utils.unregister_class(GP_CUTOUT_OT_stop_modal_handler)
    bpy.utils.unregister_class(GP_CUTOUT_OT_start_modal_handler)
    bpy.utils.unregister_class(GP_CUTOUT_OT_activate_bone_button_modal)

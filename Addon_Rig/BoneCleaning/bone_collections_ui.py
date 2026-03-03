# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025, Rapadura Atômica. All rights reserved.

import bpy

class GP_CUTOUT_OT_add_to_bone_collection(bpy.types.Operator):
    bl_idname = "gp_cutout.add_to_bone_collection"
    bl_label = "Add to Collection"
    bl_options = {'REGISTER', 'UNDO'}

    collection_name: bpy.props.StringProperty() #type: ignore

    def execute(self, context):
        armature_obj = context.active_object
        if not armature_obj or armature_obj.type != 'ARMATURE':
            return {'CANCELLED'}

        target_collection = None
        for coll in armature_obj.data.collections:
            if coll.name == self.collection_name:
                target_collection = coll
                break

        if not target_collection:
            self.report({'ERROR'}, f"Collection '{self.collection_name}' not found!")
            return {'CANCELLED'}

        added_count = 0
        for bone in context.selected_pose_bones:
            if target_collection.assign(bone):
                added_count += 1

        self.report({'INFO'}, f"Added {added_count} bones to '{self.collection_name}'")
        return {'FINISHED'}

class GP_CUTOUT_OT_toggle_bone_collection_visibility(bpy.types.Operator):
    bl_idname = "gp_cutout.toggle_bone_collection_visibility"
    bl_label = "Toggle Collection Visibility"
    bl_options = {'REGISTER'}

    collection_name: bpy.props.StringProperty() #type: ignore

    def execute(self, context):
        armature_obj = context.active_object
        if not armature_obj or armature_obj.type != 'ARMATURE':
            return {'CANCELLED'}

        for coll in armature_obj.data.collections:
            if coll.name == self.collection_name:
                coll.is_visible = not coll.is_visible
                status = "Visible" if coll.is_visible else "Hidden"
                self.report({'INFO'}, f"{coll.name}: {status}")
                break

        return {'FINISHED'}

class GP_CUTOUT_OT_open_bone_collections(bpy.types.Operator):
    bl_idname = "gp_cutout.open_bone_collections"
    bl_label = "Open Bone Collections"
    bl_description = "Open bone collections management window"

    def execute(self, context):
        bpy.ops.wm.call_panel(name="VIEW3D_PT_gp_cutout_bone_collections", keep_open=True)
        return {'FINISHED'}

class VIEW3D_PT_gp_cutout_bone_collections(bpy.types.Panel):
    bl_label = "Bone Collections Manager"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Cutout Pen'
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return (context.active_object and 
                context.active_object.type == 'ARMATURE' and
                context.mode == 'POSE')

    def draw(self, context):
        layout = self.layout
        armature_obj = context.active_object
        collections = armature_obj.data.collections

        row = layout.row()
        row.operator("armature.collection_add", text="New Collection", icon='ADD')

        if not collections:
            layout.label(text="No collections found.", icon='INFO')
            return

        for coll in collections:
            box = layout.box()
            row = box.row(align=True)

            icon = 'HIDE_OFF' if coll.is_visible else 'HIDE_ON'
            op = row.operator("gp_cutout.toggle_bone_collection_visibility", 
                             text=coll.name, icon=icon, emboss=False)
            op.collection_name = coll.name

            if context.selected_pose_bones:
                op_add = row.operator("gp_cutout.add_to_bone_collection", 
                                     text="", icon='ADD')
                op_add.collection_name = coll.name

def register():
    bpy.utils.register_class(GP_CUTOUT_OT_add_to_bone_collection)
    bpy.utils.register_class(GP_CUTOUT_OT_toggle_bone_collection_visibility)
    bpy.utils.register_class(GP_CUTOUT_OT_open_bone_collections)
    bpy.utils.register_class(VIEW3D_PT_gp_cutout_bone_collections)

def unregister():
    bpy.utils.unregister_class(VIEW3D_PT_gp_cutout_bone_collections)
    bpy.utils.unregister_class(GP_CUTOUT_OT_open_bone_collections)
    bpy.utils.unregister_class(GP_CUTOUT_OT_toggle_bone_collection_visibility)
    bpy.utils.unregister_class(GP_CUTOUT_OT_add_to_bone_collection)
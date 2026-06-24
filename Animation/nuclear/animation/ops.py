# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2023, Rapadura Atômica. All rights reserved.

import itertools
import bpy

from .core.utilities import (  # Importe do core utilities
    frame_options_to_traits,
    get_gp_keyframes,
    keyframe_types,
    LayerTraits,
    shift_keyframes,
    get_active_gp_keyframe,
    get_active_gp_object
)

from .core.properties import (  # Importe do core properties
    GPencilFlippingSettings,
    GPencilCurrentKeyframeSettings,
    GPencilShiftAndTraceSettings
)

from nuclear.utils import register_classes, unregister_classes
from nuclear.preferences import get_addon_prefs


class TRANSFORM_OT_keyframes_shift(bpy.types.Operator):
    bl_idname = "transform.keyframes_shift"
    bl_label = "Shift Grease Pencil Keyframes"
    bl_description = "Shift active Grease Pencil's Keyframes after current Frame"
    bl_options = {"BLOCKING", "GRAB_CURSOR", "UNDO", "REGISTER"}

    offset: bpy.props.IntProperty(
        name="Offset",
        description="Frame offset to apply",
        default=0,
        options={"SKIP_SAVE"},
    ) 
    only_active_layer: bpy.props.BoolProperty(
        name="Only Active Layer",
        description="Only affect active Layer",
        default=False,
        options={"SKIP_SAVE"},
    )

    only_selected_layers: bpy.props.BoolProperty(
        name="Only Selected Layers",
        description="Only affect selected Layers",
        default=False,
        options={"SKIP_SAVE"},
    )

    interactive: bpy.props.BoolProperty(
        name="Interactive",
        description="Use interactive mode to offset keyframes",
        default=False,
        options={"SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return (
            context.area.type == "DOPESHEET_EDITOR"
            and context.active_object
            and isinstance(context.active_object.data, bpy.types.GreasePencil)
        )

    def setup(self, context):
        # Get all GP keyframes after current frame
        self.keyframes = get_gp_keyframes(
            context.active_object.data,
            layer_options_to_traits(
                self.only_active_layer,
                True,
                self.only_selected_layers,
            ),
            frame_min=context.scene.frame_current + 1,
        )

        if not self.keyframes:
            return

        # Store the first keyframe initial value
        self.first_keyframe_init_value = self.keyframes[0].frame_number

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        self.setup(context)

        if not self.keyframes:
            return {"CANCELLED"}

        if self.interactive:
            context.window.cursor_modal_set("SCROLL_X")
            self.start_mouse_coords = context.region.view2d.region_to_view(
                x=event.mouse_region_x, y=event.mouse_region_y
            )
            context.window_manager.modal_handler_add(self)
            return {"RUNNING_MODAL"}
        else:
            return self.execute(context)

    def update_header_text(self, context, event):
        context.area.header_text_set(f"Offset: {self.offset}")

    def modal(self, context: bpy.types.Context, event: bpy.types.Event):
        self.update_header_text(context, event)
        # Cancel
        if event.type in {"RIGHTMOUSE", "ESC"}:
            self.cancel(context)
            return {"CANCELLED"}
        # Validate
        elif (
            event.type in {"LEFTMOUSE", "RET", "NUMPAD_ENTER"}
            and event.value == "PRESS"
        ):
            if self.offset == 0:
                self.cancel(context)
                return {"CANCELLED"}
            self.restore_ui(context)
            return {"FINISHED"}
        # Update
        elif event.type in {"MOUSEMOVE"}:
            mouse_coords = context.region.view2d.region_to_view(
                x=event.mouse_region_x, y=event.mouse_region_y
            )
            offset = int(mouse_coords[0] - self.start_mouse_coords[0])
            if offset != self.offset:
                self.offset = offset
                self.execute(context)

        return {"RUNNING_MODAL"}

    def restore_ui(self, context: bpy.types.Context):
        context.area.header_text_set(None)
        context.window.cursor_modal_restore()

    def cancel(self, context: bpy.types.Context):
        if self.offset:
            self.offset = 0
            self.execute(context)
        self.restore_ui(context)

    def execute(self, context: bpy.types.Context):
        # Setup operator if invoke was not called
        if not self.options.is_invoke:
            self.setup(context)
            if not self.keyframes:
                return {"CANCELLED"}

        # Compute absolute offset from original position
        current_delta = self.keyframes[0].frame_number - self.first_keyframe_init_value
        offset = self.offset - current_delta

        res = shift_keyframes(
            self.keyframes, offset, context.scene.frame_current + 1, adjust_offset=True
        )

        if not res:
            return {"CANCELLED"}

        # Select all the keyframes that have been moved
        # Note: moving GP keyframes in Python does not invalidate the depsgraph,
        #       leading to potentially incorrect results in the viewport.
        #       Here, calling `select_all` operator fixes the issue.
        bpy.ops.action.select_all(action="DESELECT")
        for keyframe in self.keyframes:
            keyframe.select = True

        return {"FINISHED"}

class ANIM_OT_lightbox_edit(bpy.types.Operator):
    bl_idname = "anim.lightbox_edit"
    bl_label = "Edit the lightbox"
    bl_options = {"UNDO", "REGISTER"}

    action: bpy.props.EnumProperty(
        items=[
            ("ADD", "Add selected", ""),
            ("REMOVE", "Remove selected", ""),
            ("CLEAR", "Clear", ""),
        ],
        name="Action",
        description="The action to perform on the lightbox",
        default="ADD",
        options={"SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return context.active_object and isinstance(
            context.active_object.data, bpy.types.GreasePencil
        )

    @classmethod
    def description(cls, context: bpy.types.Context, properties):
        if properties.action == "ADD":
            return "Add selected keyframes to the lightbox"
        elif properties.action == "REMOVE":
            return "Remove selected keyframes from the lightbox"
        elif properties.action == "CLEAR":
            return "Clear all keyframes from the lightbox"

    def execute(self, context: bpy.types.Context):
        if self.action == "ADD":
            selected_filter = True
            onion_tag_filter = False
        if self.action == "REMOVE":
            selected_filter = True
            onion_tag_filter = True
        if self.action == "CLEAR":
            selected_filter = False
            onion_tag_filter = True

        keyframes = get_gp_keyframes(
            context.active_object.data,
            frame_filter=frame_options_to_traits(
                selected=selected_filter, onion_tag=onion_tag_filter
            ),
        )

        if not keyframes:
            return {"CANCELLED"}

        for key in keyframes:
            key.tag = True if self.action == "ADD" else False

        return {"FINISHED"}

class ANIM_OT_keyframes_flip(bpy.types.Operator):
    bl_idname = "anim.keyframes_flip"
    bl_label = "Keyframes Flipping"
    bl_description = "Flip between keyframes"

    bl_keymaps_defaults = {
        "space_type": "DOPESHEET_EDITOR",
        "category_name": "Dopesheet",
    }
    bl_keymaps = [
        {"key": "COMMA", "properties": {"direction": "LEFT"}},
        {"key": "PERIOD", "properties": {"direction": "RIGHT"}},
        {
            "space_type": "VIEW_3D",
            "category_name": "3D View Generic",
            "key": "COMMA",
            "properties": {"direction": "LEFT"},
        },
        {
            "space_type": "VIEW_3D",
            "category_name": "3D View Generic",
            "key": "PERIOD",
            "properties": {"direction": "RIGHT"},
        },
    ]

    direction: bpy.props.EnumProperty(
        name="Direction", items=(("LEFT", "Left", ""), ("RIGHT", "Right", ""))
    )

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return context.active_object and context.active_object.type == "GREASEPENCIL"

    def execute(self, context: bpy.types.Context):
        gpd: bpy.types.GreasePencil = context.active_object.data

        # Select impacted layers.
        if gpd.flipping_settings.layer_mode == "VISIBLE":
            layers = [gpl for gpl in gpd.layers if not gpl.hide]
        else:
            layers = [gpd.layers.active]

        # Build a flat list with keyframes matching to current filter type settings.
        keyframe_types_list = list(keyframe_types.keys())
        keyframe_types_filter = gpd.flipping_settings.keyframe_types
        frames = [
            kf
            for kf in itertools.chain.from_iterable([gpl.frames for gpl in layers])
            if (
                not gpd.flipping_settings.use_filter
                or keyframe_types_filter[keyframe_types_list.index(kf.keyframe_type)]
            )
        ]

        # Remove frames not in preview range if enabled
        preview_start = context.scene.frame_preview_start
        preview_end = context.scene.frame_preview_end
        if gpd.flipping_settings.use_preview_range and context.scene.use_preview_range:
            frames = [
                kf for kf in frames if preview_start <= kf.frame_number <= preview_end
            ]

        # Early return if no keyframes match the filtering.
        if not frames:
            return {"CANCELLED"}

        # Sort those keyframes by frame number.
        sorted_frames = sorted(
            frames, reverse=self.direction == "LEFT", key=lambda x: x.frame_number
        )

        def compare_func(x: int, y: int):
            return x < y if self.direction == "LEFT" else x > y

        # Get prev/next frame relative to scene's current frame.
        actframe = context.scene.frame_current
        # Use first keyframe in list as fallback when looping is enabled.
        fallback = sorted_frames[0] if gpd.flipping_settings.loop else None

        keyframe = next(
            (kf for kf in sorted_frames if compare_func(kf.frame_number, actframe)),
            fallback,
        )

        if not keyframe:
            return {"CANCELLED"}

        # Update scene's current frame.
        context.scene.frame_current = keyframe.frame_number

        return {"FINISHED"}

class GPENCIL_OT_reset_frame_transforms(bpy.types.Operator):
    bl_idname = "gpencil.reset_frame_transforms"
    bl_label = "Reset Frame Transforms"
    bl_description = "Reset transformations for Grease Pencil frames"
    bl_options = {'REGISTER', 'UNDO'}

    type: bpy.props.EnumProperty(
        name="Type",
        items=[
            ('ACTIVE', "Active", "Reset active frame only"),
            ('SELECTED', "Selected", "Reset selected frames"),
            ('ALL', "All", "Reset all frames")
        ],
        default='ACTIVE'
    )

    def execute(self, context):
        gp_obj = get_active_gp_object()
        if not gp_obj:
            self.report({'WARNING'}, "No active Grease Pencil object")
            return {'CANCELLED'}

        for layer in gp_obj.data.layers:
            if layer.lock:  # ignora camadas travadas
                continue

            if self.type == 'ACTIVE':
                frame_number = context.scene.frame_current
                frame = next((f for f in layer.frames if f.frame_number == frame_number), None)
                if frame:
                    self.reset_frame(frame)

            elif self.type == 'SELECTED':
                for frame in layer.frames:
                    if getattr(frame, "select", False):
                        self.reset_frame(frame)

            elif self.type == 'ALL':
                for frame in layer.frames:
                    self.reset_frame(frame)

        return {'FINISHED'}

    def reset_frame(self, frame):
        """Reseta posição, rotação e escala do frame."""
        # Aqui vai depender do que você quer resetar:
        # Se tiver transformações armazenadas, zera
        if hasattr(frame, "transform"):
            frame.transform.translation = (0.0, 0.0)
            frame.transform.rotation = 0.0
            frame.transform.scale = (1.0, 1.0)
        # Caso não tenha "transform", só reporta
        else:
            pass
@bpy.app.handlers.persistent
def on_frame_changed(scene: bpy.types.Scene, depsgraph: bpy.types.Depsgraph):
    snt_settings = bpy.context.window_manager.shift_and_trace_settings
    if not snt_settings.pin_to_frame:
        return

    gp_obj = get_active_gp_object()
    if not gp_obj:
        return

    # Usando o Onion Skinning do GPencil ativo para simular o offset
    onion = gp_obj.data.onion_skinning
    onion.use_onion_skinning = (snt_settings.pinned_frame_number == scene.frame_current)

def update_onion_skinning_worldspace(*args):
    """Trigger world space onion skinning update."""
    if bpy.context.window_manager.gp_onion_skinning_worldspace_auto_update:
        bpy.ops.gpencil.cache_ghost_frame_transformations()

def gp_onion_skinning_worldspace_auto_update_cb(self, context):
    """WindowManager.gp_onion_skinning_worldspace_auto_update update callback."""
    update_onion_skinning_worldspace()

@bpy.app.handlers.persistent
def on_depsgraph_update_post(scene: bpy.types.Scene, depsgraph: bpy.types.Depsgraph):
    """Reacts to depsgraph update to update grease pencil world space onion skinning."""

    wm = bpy.context.window_manager
    if not hasattr(wm, 'gp_onion_skinning_worldspace_auto_update'):
        return
    
    if not wm.gp_onion_skinning_worldspace_auto_update:
        return

    if not bpy.context.window_manager.gp_onion_skinning_worldspace_auto_update:
        return

    obact = bpy.context.active_object
    if (
        not isinstance((gpd := obact.data), bpy.types.GreasePencil)
        or not gpd.onion_space == "WORLD"
    ):
        return

    gpd_eval = depsgraph.id_eval_get(gpd)

    for update in depsgraph.updates:
        # If the active gpencil data has been tagged update,
        if gpd_eval == update.id:
            if bpy.app.timers.is_registered(update_onion_skinning_worldspace):
                bpy.app.timers.unregister(update_onion_skinning_worldspace)
            bpy.app.timers.register(
                update_onion_skinning_worldspace, first_interval=0.05
            )
            break

class FlippingUndoHandler:
    """
    Helper class to deal with specific undoing behavior when flipping between
    grease pencil keyframes.

    Undoing a gpencil edit step might both:
        - remove a stroke from a frame
        - and change the current time to the previously active frame

    This behavior can be confusing, as one could expect the stroke to be undone,
    but still stay on the same frame.

    To counteract this behavior, this class stores the last edited frame value after a
    depgraph update, and restore it as current frame after an undo.
    """

    gpencil_edit_geo_modes = ("PAINT_GREASE_PENCIL", "SCULPT_GREASE_PENCIL", "EDIT_GREASE_PENCIL")

    @classmethod
    def register(cls):
        bpy.app.handlers.undo_post.append(cls.on_undo_post)
        bpy.app.handlers.depsgraph_update_post.append(cls.on_depsgraph_update_post)

    @classmethod
    def unregister(cls):
        bpy.app.handlers.undo_post.remove(cls.on_undo_post)
        bpy.app.handlers.depsgraph_update_post.remove(cls.on_depsgraph_update_post)

    @staticmethod
    def get_active_gpd(context):
        obact = context.active_object
        if getattr(obact, "mode") not in FlippingUndoHandler.gpencil_edit_geo_modes:
            return None
        return obact.data

    @staticmethod
    def undo_stick_to_frame() -> bool:
        return get_addon_prefs().anim_flipping_undo_mode == "STICK_TO_FRAME"

    @staticmethod
    @bpy.app.handlers.persistent
    def on_depsgraph_update_post(
        scene: bpy.types.Scene, depsgraph: bpy.types.Depsgraph
    ):
        """React on depsgraph update to look for grease pencil data changes."""

        if not FlippingUndoHandler.undo_stick_to_frame():
            return

        if not (gpd := FlippingUndoHandler.get_active_gpd(bpy.context)):
            return

        wm = bpy.context.window_manager

        gpd_id = depsgraph.id_eval_get(gpd)
        for update in depsgraph.updates:
            # If the active gpencil data has been tagged for geometry update,
            # store current frame as last edit frame value.
            if gpd_id == update.id and update.is_updated_geometry:
                wm.gp_last_edit_frame = scene.frame_current

    @staticmethod
    @bpy.app.handlers.persistent
    def on_undo_post(scene: bpy.types.Scene, _):
        """React to undo to reset frame value to last edit frame, if applicable."""
        if not FlippingUndoHandler.undo_stick_to_frame():
            return

        if not (gpd := FlippingUndoHandler.get_active_gpd(bpy.context)):
            return

        wm = bpy.context.window_manager
        # If scene frame has changed but does not match last gpencil edit frame:
        scene_frame = scene.frame_current
        if scene_frame != wm.gp_last_edit_frame:
            # Go back to last edit frame to see the impact of undoing.
            scene.frame_current = wm.gp_last_edit_frame
            # Store the frame value the undo went back to as the last edit frame, for
            # potential next undos to use this as the new reference value.
            wm.gp_last_edit_frame = scene_frame

classes = (
    TRANSFORM_OT_keyframes_shift,
    ANIM_OT_lightbox_edit,
    ANIM_OT_keyframes_flip,
    GPENCIL_OT_reset_frame_transforms,
)

def register():
    # Registrar operadores
    from bpy.utils import register_class
    for cls in classes:
        try:
            register_class(cls)
        except ValueError:
            pass  # Ignora se já estiver registrado

    # Registrar handlers com verificação
    handlers = bpy.app.handlers.depsgraph_update_post
    if on_depsgraph_update_post not in handlers:
        handlers.append(on_depsgraph_update_post)

def unregister():
    # Remover handlers com verificação
    handlers = bpy.app.handlers.depsgraph_update_post
    if on_depsgraph_update_post in handlers:
        handlers.remove(on_depsgraph_update_post)

    # Desregistrar operadores
    from bpy.utils import unregister_class
    for cls in reversed(classes):
        try:
            unregister_class(cls)
        except RuntimeError:
            pass  # Ignora se já não estiver registrado
    
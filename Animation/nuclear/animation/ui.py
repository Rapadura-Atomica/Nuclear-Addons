# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025, Rapadura Atômica. All rights reserved.

import bpy

from .core.utilities import get_active_gp_keyframe, keyframe_types
from nuclear.drawing.core import get_active_gp_object

from nuclear.utils import register_classes, unregister_classes

from .ops import (
    ANIM_OT_keyframes_flip,
    TRANSFORM_OT_keyframes_shift,
    ANIM_OT_lightbox_edit
)

class DOPESHEET_PT_KeyframeTools(bpy.types.Panel):
    bl_label = "Keyframe Tools"
    bl_space_type = "DOPESHEET_EDITOR"
    bl_region_type = "UI"
    bl_category = "Nuclear"

    def draw(self, context: bpy.types.Context):



        self.layout.label(text="Shift Keyframes", icon="PREV_KEYFRAME")
        box = self.layout.box()
        col = box.column()

        keyframes_shift_options = {
            "All Layers": {},
            "Selected": {
                "only_selected_layers": True,
            },
            "Active": {
                "only_active_layer": True,
            },
        }

        # Populate panel with variations for frame-by-frame keyframe shifting
        for name, options in keyframes_shift_options.items():
            row = col.row(align=True)
            row.label(text=name)
            row.operator_context = "EXEC_DEFAULT"
            for offset, icon in ((-1, "REW"), (+1, "FF")):
                props = row.operator("transform.keyframes_shift", icon=icon, text="")
                props.offset = offset
                for k, v in options.items():
                    setattr(props, k, v)

class VIEW3D_PT_animation_box(bpy.types.Panel):
    bl_label = "Animation"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Nuclear"

    def draw(self, context: bpy.types.Context):
        obj = get_active_gp_object()
        if not obj or not hasattr(obj.data, 'flipping_settings'):
            self.layout.label(text="Grease Pencil not properly initialized", icon='ERROR')
            return
    
        gpd = obj.data
        layer = gpd.layers.active

        # Current Keyframe - agora via função, e sem duração
        gpf = get_active_gp_keyframe(gpd)

        keyframe_box = self.layout.box()
        row = keyframe_box.row(align=True)
        row.label(text="Current Keyframe", icon="DECORATE_KEYFRAME")

        row = keyframe_box.row(align=True)
        row.enabled = gpf is not None and (layer and not layer.lock)

        if gpf:
            row.prop(
                gpf,
                "keyframe_type",
                text="",
                expand=True,
                icon_only=True,
            )
        row.separator()

        # Flipping 
        flipping_box = self.layout.box()
        row = flipping_box.row(align=True)
        row.label(text="Flipping", icon="STRANDS")

        row.separator()
        row.prop(gpd.flipping_settings, "layer_mode", expand=True, icon_only=True)
        row.separator()
        row.prop(gpd.flipping_settings, "use_filter", icon="FILTER", icon_only=True)
        subrow = row.row(align=True)
        subrow.enabled = gpd.flipping_settings.use_filter
        for i, icon in enumerate(keyframe_types.values()):
            subrow.prop(
                gpd.flipping_settings,
                "keyframe_types",
                icon=icon,
                icon_only=True,
                text="",
                index=i,
            )

        subrow = flipping_box.row(align=True)

        subrow.operator(
            "anim.keyframes_flip", icon="TRIA_LEFT", text="Previous"
        ).direction = "LEFT"
        subrow.operator(
            "anim.keyframes_flip",
            icon="TRIA_RIGHT",
            text="Next",
        ).direction = "RIGHT"

        subrow.separator()
        subrow.prop(gpd.flipping_settings, "loop", icon="FILE_REFRESH", icon_only=True)
        subrow.separator()
        subrow.prop(
            gpd.flipping_settings,
            "use_preview_range",
            icon_only=True,
            expand=True,
            icon="PREVIEW_RANGE",
        )

        # Onion Skinning
        onion_skin_box = self.layout.box()
        overlay = context.area.spaces.active.overlay
        onion_skin_enabled = overlay.use_gpencil_onion_skin

        row = onion_skin_box.row()
        row.prop(
            overlay,
            "use_gpencil_onion_skin",
            text="",
            icon="ONIONSKIN_ON",
        )
        row.label(text="Onion Skinning")

        if context.space_data.shading.type not in ("SOLID", "MATERIAL"):
            warning_row = onion_skin_box.row()
            warning_row.alert = True
            warning_row.label(
                text="Solid or Material Preview shading required",
                icon="ERROR",
            )
            warning_row.prop(context.space_data.shading, "type", text="", expand=True)

        subrow = row.row(align=True)
        subrow.enabled = onion_skin_enabled

        for i, icon in enumerate(keyframe_types.values()):
            subrow.prop(
                gpd,
                "onion_keyframe_type",
                icon=icon,
                icon_only=True,
                text="",
                index=i,
            )

        col = onion_skin_box.column()
        col.enabled = onion_skin_enabled

        if hasattr(gpd, "onion_space"):
            r = col.row(align=True)
            r.prop(gpd, "onion_space", expand=True)

            r = r.row(align=True)
            r.enabled = (gpd.onion_space == "WORLD")

            r.operator(
                "gpencil.cache_ghost_frame_transformations",
                text="",
                icon="FILE_REFRESH",
            )
            r.prop(
                context.window_manager,
                "gp_onion_skinning_worldspace_auto_update",
                text="",
                icon="RECOVER_LAST",
            )

            col.separator()

        r = col.row(align=True)
        r.prop(gpd, "onion_factor", text="Opacity", slider=True)
        r.prop(gpd, "use_onion_fade", icon_only=True, icon="PARTICLE_PATH")

        r = col.row(align=True)
        r.prop(gpd, "before_color", text="")
        r.prop(gpd, "after_color", text="")

        col.prop(gpd, "onion_mode", text="", icon="KEYFRAME_HLT")
        col2 = col.column()
        if gpd.onion_mode == "TAGGED":
            col2.operator("anim.lightbox_edit", text="Untag All").action = "CLEAR"
        elif gpd.onion_mode in {"RELATIVE", "ABSOLUTE"}:
            rr = col2.row(align=True)
            rr.prop(gpd, "ghost_before_range", text="Before")
            rr.prop(gpd, "ghost_after_range", text="After")

        # Shift & Trace (Blender 4.4 compatível)
            ts = context.scene.tool_settings
            box = self.layout.box()

            # Title.
            row = box.row()
            row.label(text="Shift & Trace", icon="OBJECT_HIDDEN")

            # Pin to frame control.
            subrow = row.row()
            subrow.alignment = "RIGHT"
            snt_settings = context.window_manager.shift_and_trace_settings

            icon = "UNPINNED"
            text = "Pin"

            if snt_settings.pin_to_frame:
                text = str(snt_settings.pinned_frame_number)
                if snt_settings.pinned_frame_number == context.scene.frame_current:
                    icon = "PINNED"

            subrow.prop(snt_settings, "pin_to_frame", icon=icon, text=text)

            # Reset operators.
            row = box.row(align=True)
            row.enabled = snt_settings.pin_to_frame  # habilita se estiver pinado
            row.label(text="Reset", icon="LOOP_BACK")

            op = row.operator("gpencil.reset_frame_transforms", text="Active")
            op.type = "ACTIVE"
            
            op = row.operator("gpencil.reset_frame_transforms", text="Selected")
            op.type = "SELECTED"

            op = row.operator("gpencil.reset_frame_transforms", text="All")
            op.type = "ALL"

classes = (
    DOPESHEET_PT_KeyframeTools,
    VIEW3D_PT_animation_box,
)

def register():
    register_classes(classes)

def unregister():
    unregister_classes(classes)

# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
from .utilities import get_active_gp_keyframe, shift_gp_keyframes

class GPencilFlippingSettings(bpy.types.PropertyGroup):
    use_filter: bpy.props.BoolProperty(
        name="Use Keyframe Type Filter",
        description="Use keyframe type filtering when flipping",
        default=True,
        options=set(),
    )

    keyframe_types: bpy.props.BoolVectorProperty(
        name="Keyframe Types",
        description="Keyframe types filter for flipping",
        size=5,
        default=[True] * 5,
        options=set(),
    )

    layer_mode: bpy.props.EnumProperty(
        name="Layer Mode",
        items=(
            ("ACTIVE", "Active", "Flip on active layer", "IMAGE_DATA", 0),
            ("VISIBLE", "Visible", "Flip on all visible layers", "RENDERLAYERS", 1),
        ),
        default="ACTIVE",
        options=set(),
    )

    loop: bpy.props.BoolProperty(
        name="Loop",
        description="Loop when reaching first or last keyframe",
        default=True,
        options=set(),
    )

    use_preview_range: bpy.props.BoolProperty(
        name="Use Preview Range",
        description="Flip only within the preview range, if enabled",
        default=True,
        options=set(),
    )

class GPencilCurrentKeyframeSettings(bpy.types.PropertyGroup):
    def get_current_keyframe_type(self):
        key_types = self.rna_type.properties["keyframe_type"].enum_items.keys()
        gpf = get_active_gp_keyframe(self.id_data)
        return key_types.index(gpf.keyframe_type) if gpf else 0

    def set_current_keyframe_type(self, keyframe_type_idx: int):
        key_types = self.rna_type.properties["keyframe_type"].enum_items.keys()
        gpf = get_active_gp_keyframe(self.id_data)
        if gpf:
            gpf.keyframe_type = key_types[keyframe_type_idx]

    keyframe_type: bpy.props.EnumProperty(
        name="Keyframe Type",
        items=(
            ("KEYFRAME", "Normal", "", "HANDLETYPE_FREE_VEC", 0),
            ("EXTREME", "Extreme", "", "KEYTYPE_EXTREME_VEC", 1),
            ("BREAKDOWN", "Breakdown", "", "KEYTYPE_BREAKDOWN_VEC", 2),
            ("JITTER", "Jitter", "", "KEYTYPE_JITTER_VEC", 3),
            ("MOVING_HOLD", "Moving Hold", "", "KEYTYPE_MOVING_HOLD_VEC", 4),
        ),
        default="KEYFRAME",
        options=set(),
        get=get_current_keyframe_type,
        set=set_current_keyframe_type,
    )

    def get_current_keyframe_duration(self):
        gpd = self.id_data
        gpf = get_active_gp_keyframe(gpd)
        if gpf is None:
            return 0
        for kf in gpd.layers.active.frames:
            if kf.frame_number > gpf.frame_number:
                return kf.frame_number - gpf.frame_number
        return 0

    def set_current_keyframe_duration(self, duration: int):
        gpd = self.id_data
        gpf = get_active_gp_keyframe(gpd)
        if gpf is None:
            return
        offset = duration - self.duration
        bpy.context.scene.frame_set(gpf.frame_number)
        shift_gp_keyframes(gpd, gpf.frame_number, offset, False, True, True, False)
        for area in bpy.context.screen.areas:
            if area.type == "DOPESHEET_EDITOR":
                area.tag_redraw()

    duration: bpy.props.IntProperty(
        name="Keyframe Duration",
        default=1,
        get=get_current_keyframe_duration,
        set=set_current_keyframe_duration,
        min=1,
    )

class GPencilShiftAndTraceSettings(bpy.types.PropertyGroup):
    def pin_to_frame_update_cb(self, context):
        if self.pin_to_frame:
            self.pinned_frame_number = context.scene.frame_current
            context.scene.frame_current = context.scene.frame_current
        else:
            context.scene.tool_settings.use_gpencil_offset_frames = True

    pin_to_frame: bpy.props.BoolProperty(
        name="Pin to Frame",
        description="Only show shifted drawings at this frame",
        default=False,
        update=pin_to_frame_update_cb,
        options=set(),
    )

    pinned_frame_number: bpy.props.IntProperty(
        name="Pinned Frame",
        description="Pinned frame value",
        default=0,
        options=set(),
    )

classes = (
    GPencilFlippingSettings,
    GPencilCurrentKeyframeSettings,
    GPencilShiftAndTraceSettings,
)

def register_classes():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)

def unregister_classes():
    from bpy.utils import unregister_class
    for cls in reversed(classes):
        unregister_class(cls)

def register_grease_pencil_properties():
    gp_classes = [bpy.types.GreasePencil]
    if hasattr(bpy.types, 'GreasePencilv3'):
        gp_classes.append(bpy.types.GreasePencilv3)

    for gp_class in gp_classes:
        if not hasattr(gp_class, "flipping_settings"):
            gp_class.flipping_settings = bpy.props.PointerProperty(
                type=GPencilFlippingSettings
            )
        if not hasattr(gp_class, "current_keyframe_settings"):
            gp_class.current_keyframe_settings = bpy.props.PointerProperty(
                type=GPencilCurrentKeyframeSettings
            )

def unregister_grease_pencil_properties():
    gp_classes = [bpy.types.GreasePencil]
    if hasattr(bpy.types, 'GreasePencilv3'):
        gp_classes.append(bpy.types.GreasePencilv3)

    for gp_class in gp_classes:
        if hasattr(gp_class, "flipping_settings"):
            del gp_class.flipping_settings
        if hasattr(gp_class, "current_keyframe_settings"):
            del gp_class.current_keyframe_settings

def register():
    register_classes()
    register_grease_pencil_properties()
    
    # Registrar propriedades no WindowManager
    if not hasattr(bpy.types.WindowManager, "shift_and_trace_settings"):
        bpy.types.WindowManager.shift_and_trace_settings = bpy.props.PointerProperty(
            type=GPencilShiftAndTraceSettings
        )
    
    if not hasattr(bpy.types.WindowManager, "gp_last_edit_frame"):
        bpy.types.WindowManager.gp_last_edit_frame = bpy.props.IntProperty(default=-1)

def unregister():
    if hasattr(bpy.types.WindowManager, "shift_and_trace_settings"):
        del bpy.types.WindowManager.shift_and_trace_settings
    if hasattr(bpy.types.WindowManager, "gp_last_edit_frame"):
        del bpy.types.WindowManager.gp_last_edit_frame
    
    unregister_grease_pencil_properties()
    unregister_classes()
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025, Rapadura Atômica. All rights reserved.

import bpy
import gpu
from gpu_extras.batch import batch_for_shader

Vec3 = tuple[int, int, int]
Vec2f = tuple[float, float]
Vec4f = tuple[float, float, float, float]


def ui_scaled(val):
    """Return value multiplied by UI scale factor."""
    return val * bpy.context.preferences.system.ui_scale


class OverlayDrawer:
    """Helper class to draw overlays using the modern GPU API."""

    def __init__(self):
        # Usamos um shader 2D pronto que aplica cor uniforme
        self.shader = gpu.shader.from_builtin("UNIFORM_COLOR")

    def _enable_blend(self):
        gpu.state.blend_set("ALPHA")
    
    def _disable_blend(self):
        gpu.state.blend_set("NONE")

    def draw(self, coords: list[Vec2f], indices: list[Vec3], color: Vec4f):
        self._enable_blend()
        batch = batch_for_shader(self.shader, "TRIS", {"pos": coords}, indices=indices)
        self.shader.bind()
        self.shader.uniform_float("color", color)
        batch.draw(self.shader)
        self._disable_blend()

    def draw_points(self, coords: list[Vec2f], color: Vec4f):
        """Draw points at specified coords."""
        self._enable_blend()
        batch = batch_for_shader(self.shader, "POINTS", {"pos": coords})
        self.shader.bind()
        self.shader.uniform_float("color", color)
        batch.draw(self.shader)
        self._disable_blend()

    def draw_lines(self, coords: list[Vec2f], color: Vec4f):
        """Draw lines at specified coords."""
        self._enable_blend()
        batch = batch_for_shader(self.shader, "LINES", {"pos": coords})
        self.shader.bind()
        self.shader.uniform_float("color", color)
        batch.draw(self.shader)
        self._disable_blend()

    def draw_rect(self, x: float, y: float, width: float, height: float, color: Vec4f):
        """Draw a filled rectangle."""
        coords = [(x, y), (x + width, y), (x + width, y + height), (x, y + height)]
        indices = [(0, 1, 2), (2, 0, 3)]
        self.draw(coords, indices, color)

    def draw_box(self, x: float, y: float, width: float, height: float, color: Vec4f):
        """Draw an outline box."""
        bl = (x, y)
        br = (x + width, y)
        tr = (x + width, y + height)
        tl = (x, y + height)
        coords = [bl, br, br, tr, tr, tl, tl, bl]
        self.draw_lines(coords, color)

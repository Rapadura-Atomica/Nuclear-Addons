import bpy

class HandleType:
    NONE = 0
    CENTER = 1
    TOP_LEFT = 2
    TOP_RIGHT = 3
    BOTTOM_LEFT = 4
    BOTTOM_RIGHT = 5
    TOP = 6
    BOTTOM = 7
    LEFT = 8
    RIGHT = 9
    ROTATION = 10

    SHEAR_TOP = 11
    SHEAR_BOTTOM = 12
    SHEAR_LEFT = 13
    SHEAR_RIGHT = 14

    ROTATE_TOP_LEFT = 20
    ROTATE_TOP_RIGHT = 21
    ROTATE_BOTTOM_LEFT = 22
    ROTATE_BOTTOM_RIGHT = 23
    PIVOT = 40


# Constantes de tamanho e cores
HANDLE_SIZE = 12
HANDLE_HOTSPOT = 20
LINE_WIDTH = 2
CENTER_HANDLE_SIZE = 10
ROTATION_HANDLE_DISTANCE = 70
ROTATION_HANDLE_SIZE = 12

COLOR_BBOX = (0.8, 0.2, 0.2, 0.8)
COLOR_HANDLE = (0.2, 0.8, 0.2, 1.0)
COLOR_HANDLE_HOVER = (1.0, 0.8, 0.2, 1.0)
COLOR_HANDLE_ACTIVE = (1.0, 0.2, 0.2, 1.0)
COLOR_CENTER = (0.2, 0.2, 1.0, 1.0)
COLOR_ROTATION = (0.8, 0.8, 0.2, 1.0)
COLOR_SHEAR = (0.8, 0.5, 0.2, 1.0)
COLOR_SHEAR_HOVER = (1.0, 0.7, 0.3, 1.0)
COLOR_SHEAR_ACTIVE = (1.0, 0.4, 0.1, 1.0)

# Cores para o gizmo
COLOR_PIVOT = (0.8, 0.3, 0.0, 1.0)
COLOR_PIVOT_HOVER = (1.0, 0.5, 0.0, 1.0)
COLOR_PIVOT_ACTIVE = (1.0, 0.2, 0.0, 1.0)

PIVOT_RADIUS = 8.0
PIVOT_HOTSPOT = 16.0

# Variáveis globais
_bbox_handle = None
_bbox_data = None
_original_points = {}
_original_screen_points = {}
_total_rotation = 0.0
_pivot_pos = None 

#_gpencil_clipboard = {
#    'strokes_data': [],
#    'source_matrix': None,
#    'copied_time': None
#}

addon_keymaps = []
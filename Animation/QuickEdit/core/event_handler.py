import bpy
from . import constants

class BBoxEventHandler:
    _instance = None
    _active_operator = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = BBoxEventHandler()
        return cls._instance
    
    @classmethod
    def set_active_operator(cls, operator):
        cls._active_operator = operator
    
    # event_handler.py
    @classmethod
    def handle_event(cls, context, event, operator):
        """Processa eventos globais enquanto a BBox está ativa"""
        
        # PERMITIR DELETE SEMPRE (com ou sem shift)
        if event.type == 'DEL' and event.value == 'PRESS':
            print("DEBUG: DELETE permitido passar")
            return {'PASS_THROUGH'}
        
        # PERMITIR X (tecla delete alternativa)
        if event.type == 'X' and not event.ctrl and event.value == 'PRESS':
            print("DEBUG: X permitido passar")
            return {'PASS_THROUGH'}
        
        # Permitir eventos com SHIFT para seleção múltipla
        if event.shift and event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            return {'PASS_THROUGH'}
        
        # PERMITIR CTRL+C, CTRL+V, CTRL+X (clipboard)
        if event.ctrl and event.type in {'C', 'V', 'X'} and event.value == 'PRESS':
            print(f"DEBUG: Ctrl+{event.type} permitido passar")
            return {'PASS_THROUGH'}
        
        # PERMITIR CTRL+Z (undo)
        if event.ctrl and event.type == 'Z' and event.value == 'PRESS':
            return {'PASS_THROUGH'}
        
        # PERMITIR tecla DEL sozinha (sem shift)
        if event.type == 'DEL' and event.value == 'PRESS':
            return {'PASS_THROUGH'}
        
        # Menu de contexto
        if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            return {'PASS_THROUGH'}
        
        # Navegação de câmera
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        
        # Outros eventos importantes
        pass_through_events = {
            'A',    # Select All
            'H',    # Hide
            'G', 'R', 'S',  # Transformações
            'TAB',  # Switch mode
            'SPACE', # Tool menu
            'ESC',  # Cancel
        }
        
        if event.type in pass_through_events and event.value == 'PRESS':
            return {'PASS_THROUGH'}
        
        # Por padrão, bloqueia (BBox captura)
        return False
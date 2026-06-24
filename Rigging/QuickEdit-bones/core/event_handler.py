import bpy
from ..core import constants

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
    
    @classmethod
    def handle_event(cls, context, event, operator):
        """Processa eventos globais enquanto a BBox está ativa"""
        print(f"[DEBUG EventHandler] Evento recebido: {event.type} | ctrl={event.ctrl} | shift={event.shift} | alt={event.alt} | value={event.value}")


        # Permitir que eventos com SHIFT passem para seleção múltipla
        if event.shift and event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            print(f"[DEBUG EventHandler] Decidindo PASS_THROUGH para {event.type} (Ctrl={event.ctrl})")
            return {'PASS_THROUGH'}

        # Se não há operador BBox ativo, não fazer nada
        if not cls._active_operator:
            return False
        
        # Lista de eventos que devem passar através
        pass_through_events = {
            'X', 'DEL',                          # Delete
            'Z',                                 # Undo/Redo
            'A',                                 # Select All
            'H',                                 # Hide
            'G', 'R', 'S',                       # Transformações
            'TAB',                               # Switch mode
            'SPACE',                             # Tool menu
        }
        
        # Eventos com modificadores que devem passar
        modifier_events = {
            ('C', True, False),    # Ctrl+C - Copy
            ('V', True, False),    # Ctrl+V - Paste
            ('Z', True, False),    # Ctrl+Z - Undo
            ('Y', True, False),    # Ctrl+Y - Redo
            ('A', True, False),    # Ctrl+A - Select All
        }
        
        # Verificar eventos simples
        if event.type in pass_through_events and event.value == 'PRESS':
            print(f"[DEBUG EventHandler] Decidindo PASS_THROUGH para {event.type} (Ctrl={event.ctrl})")
            return True
        
        # Verificar eventos com modificadores
        event_key = (event.type, event.ctrl, event.shift)
        if event_key in modifier_events and event.value == 'PRESS':
            print(f"[DEBUG EventHandler] Decidindo PASS_THROUGH para {event.type} (Ctrl={event.ctrl})")
            return True
        
        # Permitir menu de contexto com botão direito
        if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            print(f"[DEBUG EventHandler] Decidindo PASS_THROUGH para {event.type} (Ctrl={event.ctrl})")
            return True
        
        return False
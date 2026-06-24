bl_info = {
    "name": "Heatmap & Workflow Tracker",
    "author": "Rapadura Atômica LTDA",
    "website": "https://github.com/Rapadura-Atomica",
    "version": (1, 2),
    "blender": (4, 0, 0),
    "location": "View3D > N-Panel > Analytics",
    "description": "Registra cliques, operadores, teclas e duração de ações para análise de fluxo de trabalho",
    "category": "Development",
}

import bpy
import json
import os
import time
from bpy.types import Operator, Panel
from bpy.app.handlers import persistent

# ──────────────────────────────────────────────── Configuração
LOG_FOLDER = os.path.join(os.path.expanduser("~"), "blender_usage_logs")
try:
    os.makedirs(LOG_FOLDER, exist_ok=True)
    print(f"[Workflow Tracker] Pasta confirmada/criada: {LOG_FOLDER}")
except Exception as e:
    print(f"[Workflow Tracker] Erro ao criar pasta: {e}")

SESSION_START = time.strftime("%Y%m%d_%H%M%S")
LOG_PATH = os.path.join(LOG_FOLDER, f"workflow_{SESSION_START}.jsonl")
print(f"[Workflow Tracker] Arquivo de log: {LOG_PATH}")

BUFFER = []
FLUSH_INTERVAL = 4.0  # segundos
TRACKING_ACTIVE = False

# Cache do último contexto válido
LAST_KNOWN = {
    "area": None,
    "region": None,
    "workspace": None,
    "mode": None,
    "active_object": None,
}

# ──────────────────────────────────────────────── Operador modal principal
class ANALYTICS_OT_tracker(Operator):
    bl_idname = "analytics.tracker"
    bl_label = "Workflow Tracker Interno"
    bl_options = {'INTERNAL'}

    _timer = None
    mouse_down_time = None
    mouse_down_pos = None

    def modal(self, context, event):
        global TRACKING_ACTIVE
        if not TRACKING_ACTIVE:
            self.cancel(context)
            return {'CANCELLED'}

        # Atualiza cache de contexto sempre que possível
        if context.area:
            LAST_KNOWN["area"] = context.area.type
            LAST_KNOWN["region"] = context.region.type if context.region else None
            LAST_KNOWN["workspace"] = context.workspace.name if context.workspace else None
            LAST_KNOWN["mode"] = context.mode
            LAST_KNOWN["active_object"] = context.active_object.name if context.active_object else None

        # Captura cliques
        if event.type == 'LEFTMOUSE':
            if event.value == 'PRESS':
                self.mouse_down_time = time.time()
                self.mouse_down_pos = (event.mouse_x, event.mouse_y)
                self.log_click(context, event)
                self.flush()  # flush rápido para teste
            elif event.value == 'RELEASE' and self.mouse_down_time:
                duration = time.time() - self.mouse_down_time
                self.log_mouse_release(context, event, duration)
                self.flush()
                self.mouse_down_time = None

        # Captura teclas de atalho comuns
        if event.value == 'PRESS' and event.type in {'A','G','R','S','D','E','TAB','ONE','TWO','THREE','FOUR','F','B','I','O','P','H','M'}:
            self.log_key_press(context, event)

        # Flush periódico
        if event.type == 'TIMER':
            self.flush()

        return {'PASS_THROUGH'}

    def log_click(self, context, event):
        entry = {
            "type": "click",
            "ts": time.time(),
            "mouse_x": event.mouse_x,
            "mouse_y": event.mouse_y,
            "norm_x": event.mouse_x / context.window.width if context.window.width else 0.0,
            "norm_y": event.mouse_y / context.window.height if context.window.height else 0.0,
            "area": LAST_KNOWN["area"] or "UNKNOWN",
            "region": LAST_KNOWN["region"] or "UNKNOWN",
            "workspace": LAST_KNOWN["workspace"] or "UNKNOWN",
            "mode": LAST_KNOWN["mode"] or "UNKNOWN",
            "active_object": LAST_KNOWN["active_object"],
        }
        BUFFER.append(entry)
        print(f"[Tracker] Clique: {entry['area']} - {entry['mode']}")

    def log_mouse_release(self, context, event, duration):
        entry = {
            "type": "mouse_release",
            "ts": time.time(),
            "duration_sec": round(duration, 3),
            "start_x": self.mouse_down_pos[0],
            "start_y": self.mouse_down_pos[1],
            "end_x": event.mouse_x,
            "end_y": event.mouse_y,
            "area": LAST_KNOWN["area"] or "UNKNOWN",
            "workspace": LAST_KNOWN["workspace"] or "UNKNOWN",
        }
        BUFFER.append(entry)
        print(f"[Tracker] Mouse solto após {duration:.2f}s")

    def log_key_press(self, context, event):
        entry = {
            "type": "key_press",
            "ts": time.time(),
            "key": event.type,
            "shift": event.shift,
            "ctrl": event.ctrl,
            "alt": event.alt,
            "mode": LAST_KNOWN["mode"] or "UNKNOWN",
            "active_object": LAST_KNOWN["active_object"],
        }
        BUFFER.append(entry)
        print(f"[Tracker] Tecla: {event.type} ({'Shift+' if event.shift else ''}{'Ctrl+' if event.ctrl else ''}{'Alt+' if event.alt else ''})")

    def flush(self):
        global BUFFER
        if not BUFFER:
            return
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                for entry in BUFFER:
                    f.write(json.dumps(entry) + "\n")
            print(f"[Tracker] Flush: {len(BUFFER)} entradas salvas")
            BUFFER.clear()
        except Exception as e:
            print(f"[Tracker] Erro ao salvar: {e}")

    def execute(self, context):
        global TRACKING_ACTIVE
        if TRACKING_ACTIVE:
            return {'CANCELLED'}
        TRACKING_ACTIVE = True
        wm = context.window_manager
        self._timer = wm.event_timer_add(FLUSH_INTERVAL, window=context.window)
        wm.modal_handler_add(self)
        self.report({'INFO'}, f"Iniciado → {os.path.basename(LOG_PATH)}")
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        self.flush()
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
        global TRACKING_ACTIVE
        TRACKING_ACTIVE = False
        self.report({'INFO'}, "Tracker parado")

# ──────────────────────────────────────────────── Toggle
class ANALYTICS_OT_toggle(Operator):
    bl_idname = "analytics.toggle"
    bl_label = "Toggle Workflow Tracker"

    def execute(self, context):
        wm = context.window_manager
        running = wm.get("analytics_running", False)
        if running:
            bpy.ops.analytics.tracker('INVOKE_DEFAULT')
            wm["analytics_running"] = False
            self.report({'INFO'}, "Tracker parado")
        else:
            bpy.ops.analytics.tracker('INVOKE_DEFAULT')
            wm["analytics_running"] = True
            self.report({'INFO'}, "Tracker iniciado")
        return {'FINISHED'}

# ──────────────────────────────────────────────── Painel
class ANALYTICS_PT_panel(Panel):
    bl_label = "Workflow Tracker"
    bl_idname = "ANALYTICS_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Analytics"

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        running = wm.get("analytics_running", False)

        row = layout.row(align=True)
        row.scale_y = 1.4
        icon = 'PAUSE' if running else 'PLAY'
        text = "Parar Tracker" if running else "Iniciar Tracker"
        row.operator("analytics.toggle", text=text, icon=icon)

        if running:
            box = layout.box()
            box.label(text="Gravando cliques, teclas e operadores...", icon='RADIOBUT_ON')
            box.label(text=f"Log: {os.path.basename(LOG_PATH)}")
        else:
            layout.label(text="Tracker parado", icon='X')

        layout.operator("wm.path_open", text="Abrir Pasta de Logs", icon='FOLDER_REDIRECT').filepath = LOG_FOLDER

# ──────────────────────────────────────────────── Captura de operadores
@persistent
def on_operator_post(scene, depsgraph):
    if not TRACKING_ACTIVE:
        return

    wm = bpy.context.window_manager
    if wm.operators:
        op = wm.operators[-1]
        entry = {
            "type": "operator",
            "ts": time.time(),
            "idname": op.bl_idname,
            "label": op.bl_label or "Sem label",
            "mode": bpy.context.mode,
            "active_object": bpy.context.active_object.name if bpy.context.active_object else None,
            "area": LAST_KNOWN["area"] or "UNKNOWN",
            "workspace": LAST_KNOWN["workspace"] or "UNKNOWN",
        }
        BUFFER.append(entry)
        print(f"[Tracker] Operador: {op.bl_idname} ({bpy.context.mode})")

# ──────────────────────────────────────────────── Registro
def register():
    bpy.utils.register_class(ANALYTICS_OT_tracker)
    bpy.utils.register_class(ANALYTICS_OT_toggle)
    bpy.utils.register_class(ANALYTICS_PT_panel)
    bpy.app.handlers.depsgraph_update_post.append(on_operator_post)
    bpy.context.window_manager["analytics_running"] = False

def unregister():
    bpy.app.handlers.depsgraph_update_post.remove(on_operator_post)
    bpy.utils.unregister_class(ANALYTICS_PT_panel)
    bpy.utils.unregister_class(ANALYTICS_OT_toggle)
    bpy.utils.unregister_class(ANALYTICS_OT_tracker)

if __name__ == "__main__":
    register()
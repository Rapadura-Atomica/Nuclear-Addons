# SPDX-License-Identifier: GPL-3.0-or-later
"""
Drawing Clipboard - Copia e cola desenhos entre arquivos
Versão FINAL para Blender 5.0 (Grease Pencil 3.0)
"""

bl_info = {
    "name": "Drawing Clipboard",
    "author": "Seu Nome",
    "version": (1, 6, 0),
    "blender": (5, 0, 0),
    "location": "View3D > Sidebar > Drawing",
    "description": "Copia e cola desenhos entre arquivos Blender 5.0",
    "category": "Animation",
}

import bpy
import tempfile
import os
import json

CACHE_FILE = os.path.join(tempfile.gettempdir(), "drawing_clipboard_cache.json")


def save_cache_to_disk(data):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)


def load_cache_from_disk():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


class GP_OT_copy_drawing(bpy.types.Operator):
    bl_idname = "gp.copy_drawing"
    bl_label = "Copy Drawing"
    bl_options = {'REGISTER'}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'GREASEPENCIL':
            self.report({'ERROR'}, "Selecione um objeto Grease Pencil")
            return {'CANCELLED'}

        frame = context.scene.frame_current
        data = self.capture_frame_data(obj.data, frame)

        cache = {"object_name": obj.name, "frame": frame, "data": data}
        save_cache_to_disk(cache)

        self.report({'INFO'}, f"Desenho do frame {frame} copiado!")
        return {'FINISHED'}

    def capture_frame_data(self, gp_data, frame_number):
        """Captura todos os strokes do frame atual"""
        captured = []
        
        for layer in gp_data.layers:
            if layer.hide:
                continue
            
            # Encontrar o frame correto
            gp_frame = layer.get_frame_at(frame_number)
            if not gp_frame or not gp_frame.drawing:
                continue
            
            drawing = gp_frame.drawing
            strokes = []
            
            for stroke in drawing.strokes:
                stroke_data = {
                    "points": [],
                    "material_index": stroke.material_index,
                    "cyclic": stroke.cyclic,
                    "start_cap": stroke.start_cap,
                    "end_cap": stroke.end_cap,
                    "softness": stroke.softness,
                    "fill_color": stroke.fill_color[:] if hasattr(stroke, "fill_color") else (0, 0, 0, 0),
                }
                
                # Capturar pontos
                for point in stroke.points:
                    stroke_data["points"].append({
                        "position": (point.position.x, point.position.y, point.position.z),
                        "radius": point.radius,
                        "opacity": point.opacity,
                        "rotation": point.rotation,
                        "vertex_color": point.vertex_color[:] if hasattr(point, "vertex_color") else (0, 0, 0, 0)
                    })
                
                strokes.append(stroke_data)
            
            captured.append({
                "layer_name": layer.name,
                "strokes": strokes,
                "layer_lock": layer.lock,
                "layer_hide": layer.hide
            })
        
        return captured


class GP_OT_paste_drawing(bpy.types.Operator):
    bl_idname = "gp.paste_drawing"
    bl_label = "Paste Drawing"
    bl_options = {'REGISTER'}

    def execute(self, context):
        cache = load_cache_from_disk()
        if not cache or not cache.get("data"):
            self.report({'ERROR'}, "Nenhum desenho copiado!")
            return {'CANCELLED'}

        obj = context.active_object
        if not obj or obj.type != 'GREASEPENCIL':
            # Criar um novo objeto Grease Pencil se não existir
            bpy.ops.object.grease_pencil_add(location=(0, 0, 0))
            obj = context.active_object

        gp_data = obj.data
        frame = context.scene.frame_current

        self.paste_frame_data(gp_data, cache["data"], frame)
        self.report({'INFO'}, f"Desenho colado no frame {frame}!")
        return {'FINISHED'}

    def paste_frame_data(self, gp_data, captured_data, frame_number):
        """Cola os strokes no frame atual"""
        for layer_data in captured_data:
            # Criar ou obter a layer
            layer = gp_data.layers.get(layer_data["layer_name"])
            if not layer:
                layer = gp_data.layers.new(name=layer_data["layer_name"])
            
            # Definir propriedades da layer
            layer.lock = layer_data.get("layer_lock", False)
            layer.hide = layer_data.get("layer_hide", False)
            
            # Obter ou criar o frame
            gp_frame = layer.get_frame_at(frame_number)
            if not gp_frame:
                gp_frame = layer.frames.new(frame_number)
            
            # Garantir que temos um drawing válido
            drawing = gp_frame.drawing
            
            for stroke_data in layer_data["strokes"]:
                point_count = len(stroke_data["points"])
                
                if point_count == 0:
                    continue
                
                # CORREÇÃO: Criar stroke com o número correto de pontos de uma vez
                # GPv3: add_strokes aceita uma lista com o número de pontos por stroke
                drawing.add_strokes([point_count])
                
                # Pegar o último stroke criado
                stroke = drawing.strokes[-1]
                
                # Definir propriedades do stroke
                stroke.material_index = stroke_data.get("material_index", 0)
                stroke.cyclic = stroke_data.get("cyclic", False)
                stroke.start_cap = stroke_data.get("start_cap", 0)
                stroke.end_cap = stroke_data.get("end_cap", 0)
                stroke.softness = stroke_data.get("softness", 0.0)
                
                if hasattr(stroke, "fill_color"):
                    stroke.fill_color = stroke_data.get("fill_color", (0, 0, 0, 0))
                
                # Adicionar pontos ao stroke
                for i, point_data in enumerate(stroke_data["points"]):
                    if i < len(stroke.points):
                        point = stroke.points[i]
                        point.position = point_data["position"]
                        point.radius = point_data.get("radius", 0.02)
                        point.opacity = point_data.get("opacity", 1.0)
                        point.rotation = point_data.get("rotation", 0.0)
                        if hasattr(point, "vertex_color"):
                            point.vertex_color = point_data.get("vertex_color", (0, 0, 0, 0))
        
        # Forçar redraw
        if bpy.context.area:
            bpy.context.area.tag_redraw()


class GP_OT_clear_cache(bpy.types.Operator):
    bl_idname = "gp.clear_cache"
    bl_label = "Clear Cache"
    bl_options = {'REGISTER'}

    def execute(self, context):
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
        self.report({'INFO'}, "Cache limpo!")
        return {'FINISHED'}


class VIEW3D_PT_drawing_clipboard(bpy.types.Panel):
    bl_label = "Drawing Clipboard"
    bl_idname = "VIEW3D_PT_drawing_clipboard"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Drawing"

    def draw(self, context):
        layout = self.layout
        cache = load_cache_from_disk()

        box = layout.box()
        if cache and cache.get("data"):
            box.label(text="✓ Desenho copiado", icon='CHECKMARK')
            box.label(text=f"Frame: {cache['frame']}")
            box.label(text=f"Objeto: {cache['object_name']}")
            box.operator("gp.clear_cache", text="Limpar", icon='X')
        else:
            box.label(text="✗ Nenhum desenho copiado", icon='INFO')

        layout.separator()
        col = layout.column(align=True)
        col.scale_y = 2.0
        col.operator("gp.copy_drawing", text="Copiar Desenho Atual", icon='COPYDOWN')
        col.operator("gp.paste_drawing", text="Colar Desenho", icon='PASTEDOWN')

        layout.separator()
        layout.label(text=f"Frame atual: {context.scene.frame_current}")


# ==================== Registro ====================
classes = [GP_OT_copy_drawing, GP_OT_paste_drawing, GP_OT_clear_cache, VIEW3D_PT_drawing_clipboard]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
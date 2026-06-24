bl_info = {
    "name": "GP Stamp Tool",
    "author": "Rapadura Atômica LTDA",
    "website": "https://github.com/Rapadura-Atomica",
    "version": (1, 0, 0),
    "blender": (5, 0, 0),
    "location": "View3D > N-Panel > GP Stamp",
    "description": "Salve e replique desenhos do Grease Pencil como carimbos",
    "category": "Animation",
}

import bpy
import json
import uuid
from pathlib import Path
from bpy.props import StringProperty, BoolProperty
from bpy_extras import view3d_utils
from mathutils import Vector

from . import api_route

# ===========================================================================
# CAMINHOS
# ===========================================================================
def get_stamps_path():
    """Retorna o caminho da pasta de carimbos"""
    stamps_dir = Path(bpy.utils.user_resource('SCRIPTS')) / "gp_stamps"
    stamps_dir.mkdir(parents=True, exist_ok=True)
    return stamps_dir

def get_index_path():
    return get_stamps_path() / "stamps_index.json"


# ===========================================================================
# MATERIAIS (cores do carimbo)
# ===========================================================================
def serialize_gp_material(mat):
    """Serializa um material de Grease Pencil para JSON"""
    data = {"name": mat.name}
    gp = getattr(mat, "grease_pencil", None)
    if gp:
        data["gp"] = {
            "color": list(gp.color),
            "fill_color": list(gp.fill_color),
            "show_stroke": gp.show_stroke,
            "show_fill": gp.show_fill,
            "mode": gp.mode,
            "stroke_style": gp.stroke_style,
            "fill_style": gp.fill_style,
        }
    return data

def ensure_material(obj, mat_data):
    """Garante que o material exista no objeto-alvo, retornando seu índice de slot.

    1. Se já houver um slot com o mesmo nome, reutiliza.
    2. Senão, reaproveita/cria o data-block de material e o anexa ao objeto.
    """
    name = mat_data.get("name", "Stamp_Mat")

    # Já existe um slot com esse nome?
    for i, slot_mat in enumerate(obj.data.materials):
        if slot_mat and slot_mat.name == name:
            return i

    # Reaproveita um data-block existente (se for GP) ou cria um novo
    mat = bpy.data.materials.get(name)
    if mat is None or getattr(mat, "grease_pencil", None) is None:
        mat = bpy.data.materials.new(name)
        if getattr(mat, "grease_pencil", None) is None:
            bpy.data.materials.create_gpencil_data(mat)
        gp_data = mat_data.get("gp")
        if gp_data and mat.grease_pencil:
            gp = mat.grease_pencil
            gp.color = gp_data.get("color", (0.0, 0.0, 0.0, 1.0))
            gp.fill_color = gp_data.get("fill_color", (0.0, 0.0, 0.0, 0.0))
            gp.show_stroke = gp_data.get("show_stroke", True)
            gp.show_fill = gp_data.get("show_fill", False)
            for prop in ("mode", "stroke_style", "fill_style"):
                if prop in gp_data:
                    try:
                        setattr(gp, prop, gp_data[prop])
                    except (TypeError, AttributeError):
                        pass

    obj.data.materials.append(mat)
    return len(obj.data.materials) - 1


def get_stamp_centroid(stamp_data):
    """Centro geométrico (média) de todos os pontos do carimbo, em espaço local."""
    total = Vector((0.0, 0.0, 0.0))
    count = 0
    for layer_data in stamp_data.get("strokes_data", []):
        for stroke_data in layer_data.get("strokes", []):
            for point_data in stroke_data.get("points", []):
                pos = point_data.get("position", [0, 0, 0])
                total += Vector(pos)
                count += 1
    if count == 0:
        return Vector((0.0, 0.0, 0.0))
    return total / count


# ===========================================================================
# OPERADOR: SALVAR CARIMBO
# ===========================================================================
class GP_OT_save_stamp(bpy.types.Operator):
    """Salva o desenho atual do Grease Pencil como um carimbo"""
    bl_idname = "gp.save_stamp"
    bl_label = "Save Current Drawing as Stamp"
    bl_options = {'REGISTER', 'UNDO'}

    stamp_name: StringProperty(
        name="Stamp Name",
        description="Nome do carimbo",
        default="MyStamp"
    ) #type: ignore

    def execute(self, context):
        obj = context.active_object
        
        if not obj or not api_route.obj_is_gp(obj):
            self.report({'ERROR'}, "Select a Grease Pencil object")
            return {'CANCELLED'}

        frame = context.scene.frame_current
        stamp_id = str(uuid.uuid4())[:8]
        
        # Coletar dados do desenho atual usando a API bridge
        stamp_data = self.capture_drawing(obj, frame)
        
        if not stamp_data or not stamp_data.get("strokes_data"):
            self.report({'ERROR'}, "No strokes found in current frame")
            return {'CANCELLED'}
        
        # Salvar arquivo
        stamp_file = get_stamps_path() / f"{stamp_id}.json"
        
        with open(stamp_file, 'w', encoding='utf-8') as f:
            json.dump(stamp_data, f, indent=2)
        
        # Atualizar índice
        index = self.load_index()
        index[stamp_id] = {
            "id": stamp_id,
            "name": self.stamp_name,
            "file": f"{stamp_id}.json",
            "created": self.get_timestamp(),
            "stroke_count": sum(len(s_data.get("strokes", [])) for s_data in stamp_data.get("strokes_data", []))
        }
        self.save_index(index)
        
        self.refresh_ui(context)
        
        self.report({'INFO'}, f"Stamp '{self.stamp_name}' saved with {index[stamp_id]['stroke_count']} strokes!")
        return {'FINISHED'}

    def capture_drawing(self, obj, frame):
        """Captura todos os strokes usando a API bridge"""
        data = {
            "strokes_data": [],
            "object_name": obj.name,
            "materials": {}  # nome do material -> dados serializados (cores)
        }

        gpdata = obj.data

        # Percorrer layers
        for layer_idx, layer in enumerate(gpdata.layers):
            if api_route.layer_hidden(layer):
                continue

            # Encontrar frame na layer
            frame_block = api_route.get_layer_frame_by_number(layer, frame)

            if not frame_block or not api_route.is_frame_valid(frame_block):
                continue

            # Acessar strokes via nuclear_strokes (API bridge)
            strokes = frame_block.nuclear_strokes

            if len(strokes) == 0:
                continue

            layer_data = {
                "layer_name": layer.name,
                "layer_index": layer_idx,
                "strokes": []
            }

            for stroke in strokes:
                stroke_data = self.capture_stroke(stroke, obj, data["materials"])
                if stroke_data and stroke_data.get("points"):
                    layer_data["strokes"].append(stroke_data)

            if layer_data["strokes"]:
                data["strokes_data"].append(layer_data)

        return data

    def capture_stroke(self, stroke, obj, materials_out):
        """Captura um stroke individual + registra seu material (cores)"""
        try:
            points = []
            for point in stroke.points:
                points.append({
                    "position": [point.co.x, point.co.y, point.co.z],
                    "strength": point.strength,
                    "pressure": point.pressure,
                    "vertex_color": list(point.vertex_color) if hasattr(point, 'vertex_color') else [0, 0, 0, 0]
                })

            # Registrar o material por nome para levar as cores junto
            mat_index = stroke.material_index
            mat_name = None
            mats = obj.data.materials
            if 0 <= mat_index < len(mats) and mats[mat_index]:
                mat = mats[mat_index]
                mat_name = mat.name
                if mat_name not in materials_out:
                    materials_out[mat_name] = serialize_gp_material(mat)

            data = {
                "points": points,
                "material_index": mat_index,
                "material_name": mat_name,
                "use_cyclic": stroke.use_cyclic,
                "line_width": stroke.line_width if hasattr(stroke, 'line_width') else 10,
                "hardness": stroke.hardness if hasattr(stroke, 'hardness') else 1.0,
            }

            # Cor de preenchimento por stroke (vertex color fill), se existir
            if hasattr(stroke, 'vertex_color_fill'):
                try:
                    data["vertex_color_fill"] = list(stroke.vertex_color_fill)
                except (TypeError, ValueError):
                    pass

            return data
        except Exception as e:
            print(f"Erro ao capturar stroke: {e}")
            return None

    def load_index(self):
        index_path = get_index_path()
        if index_path.exists():
            with open(index_path, 'r') as f:
                return json.load(f)
        return {}

    def save_index(self, index):
        with open(get_index_path(), 'w') as f:
            json.dump(index, f, indent=2)

    def get_timestamp(self):
        from datetime import datetime
        return datetime.now().isoformat()

    def refresh_ui(self, context):
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

    def invoke(self, context, event):
        obj = context.active_object
        if obj and api_route.obj_is_gp(obj):
            self.stamp_name = f"{obj.name}_frame{context.scene.frame_current}"
        return context.window_manager.invoke_props_dialog(self, width=300)


# ===========================================================================
# OPERADOR: APLICAR CARIMBO
# ===========================================================================
class GP_OT_apply_stamp(bpy.types.Operator):
    """Carimba o desenho: clique na viewport para posicioná-lo onde o mouse estiver"""
    bl_idname = "gp.apply_stamp"
    bl_label = "Apply Stamp"
    bl_options = {'REGISTER', 'UNDO'}

    stamp_id: StringProperty() #type: ignore
    use_mouse: BoolProperty(default=True) #type: ignore  # colar onde o mouse clicar

    # Estado interno do modal
    _stamp_data = None
    _stamp_name = ""
    _centroid = None

    # ----------------------------------------------------------------- INVOKE
    def invoke(self, context, event):
        obj = context.active_object
        if not obj or not api_route.obj_is_gp(obj):
            self.report({'ERROR'}, "Select a Grease Pencil object")
            return {'CANCELLED'}

        # Carregar stamp
        index = self.load_index()
        stamp_info = index.get(self.stamp_id)
        if not stamp_info:
            self.report({'ERROR'}, "Stamp not found")
            return {'CANCELLED'}

        stamp_file = get_stamps_path() / stamp_info["file"]
        if not stamp_file.exists():
            self.report({'ERROR'}, "Stamp file missing")
            return {'CANCELLED'}

        with open(stamp_file, 'r') as f:
            self._stamp_data = json.load(f)

        self._stamp_name = stamp_info.get("name", "Stamp")
        self._centroid = get_stamp_centroid(self._stamp_data)

        # Sem mouse ou fora da viewport -> cola na posição original
        if not self.use_mouse or context.area is None or context.area.type != 'VIEW_3D':
            return self.execute(context)

        context.window_manager.modal_handler_add(self)
        context.area.header_text_set(
            "🖱️ Clique para carimbar o desenho  |  ESC / botão direito: cancelar"
        )
        return {'RUNNING_MODAL'}

    # ------------------------------------------------------------------ MODAL
    def modal(self, context, event):
        context.area.tag_redraw()

        if event.type in {'RIGHTMOUSE', 'ESC'}:
            context.area.header_text_set(None)
            return {'CANCELLED'}

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            region = self.get_window_region(context, event)
            if region is None:
                # Clique fora da janela 3D (ex.: no N-panel) -> ignora e segue esperando
                return {'RUNNING_MODAL'}

            rv3d = context.space_data.region_3d
            obj = context.active_object
            coord = (event.mouse_x - region.x, event.mouse_y - region.y)

            # Projeta o clique num plano que passa pela origem do objeto
            depth = obj.matrix_world.translation
            world = view3d_utils.region_2d_to_location_3d(region, rv3d, coord, depth)
            local_target = obj.matrix_world.inverted() @ world
            offset = local_target - self._centroid

            ok = self.apply_stamp(obj, context.scene.frame_current, self._stamp_data, offset)
            context.area.header_text_set(None)

            if ok:
                self.report({'INFO'}, f"Stamp '{self._stamp_name}' aplicado!")
                context.view_layer.update()
                context.area.tag_redraw()
                return {'FINISHED'}
            self.report({'ERROR'}, "Failed to apply stamp")
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

    def get_window_region(self, context, event):
        """Retorna a região WINDOW (viewport 3D) sob o cursor, ou None."""
        for region in context.area.regions:
            if region.type == 'WINDOW':
                if (region.x <= event.mouse_x < region.x + region.width and
                        region.y <= event.mouse_y < region.y + region.height):
                    return region
        return None

    # ---------------------------------------------------------------- EXECUTE
    def execute(self, context):
        """Aplicação não-modal: cola na posição original (offset zero)."""
        obj = context.active_object
        if not obj or not api_route.obj_is_gp(obj):
            self.report({'ERROR'}, "Select a Grease Pencil object")
            return {'CANCELLED'}

        if self._stamp_data is None:
            index = self.load_index()
            stamp_info = index.get(self.stamp_id)
            if not stamp_info:
                self.report({'ERROR'}, "Stamp not found")
                return {'CANCELLED'}
            stamp_file = get_stamps_path() / stamp_info["file"]
            if not stamp_file.exists():
                self.report({'ERROR'}, "Stamp file missing")
                return {'CANCELLED'}
            with open(stamp_file, 'r') as f:
                self._stamp_data = json.load(f)
            self._stamp_name = stamp_info.get("name", "Stamp")

        success = self.apply_stamp(obj, context.scene.frame_current,
                                   self._stamp_data, Vector((0.0, 0.0, 0.0)))

        if success:
            self.report({'INFO'}, f"Stamp '{self._stamp_name}' applied!")
            context.view_layer.update()
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
            return {'FINISHED'}

        self.report({'ERROR'}, "Failed to apply stamp")
        return {'CANCELLED'}

    # ----------------------------------------------------------------- APPLY
    def apply_stamp(self, obj, frame, stamp_data, offset):
        """Aplica os strokes do carimbo, deslocados por `offset` (espaço local)."""
        try:
            gpdata = obj.data

            # Sair do modo EDIT se necessário
            if bpy.context.mode == 'EDIT':
                bpy.ops.object.mode_set(mode='OBJECT')

            # Remapear materiais (cores) do carimbo para o objeto-alvo
            mat_remap = self.build_material_remap(obj, stamp_data)

            strokes_added = 0

            for layer_data in stamp_data.get("strokes_data", []):
                layer_name = layer_data.get("layer_name", "StampLayer")

                # Encontrar ou criar layer
                layer = None
                for l in gpdata.layers:
                    if l.name == layer_name:
                        layer = l
                        break
                if not layer:
                    layer = gpdata.layers.new(name=layer_name, set_active=True)

                # Obter ou criar frame
                frame_block = api_route.get_layer_frame_by_number(layer, frame)
                if not frame_block or frame_block.frame_number != frame:
                    if api_route.is_gpv3():
                        frame_block = layer.frames.new(frame)
                    else:
                        frame_block = layer.frames.new(frame, active=True)

                if not frame_block or not api_route.is_frame_valid(frame_block):
                    continue

                strokes = frame_block.nuclear_strokes

                for stroke_data in layer_data.get("strokes", []):
                    new_stroke = strokes.new()
                    self.populate_stroke(new_stroke, stroke_data, offset, mat_remap)
                    strokes_added += 1

            print(f"✅ Aplicado: {strokes_added} strokes no frame {frame} (offset {offset})")
            return strokes_added > 0

        except Exception as e:
            print(f"Erro ao aplicar stamp: {e}")
            import traceback
            traceback.print_exc()
            return False

    def build_material_remap(self, obj, stamp_data):
        """nome do material salvo -> índice de slot no objeto-alvo (cria se faltar)."""
        remap = {}
        for name, mat_data in stamp_data.get("materials", {}).items():
            try:
                remap[name] = ensure_material(obj, mat_data)
            except Exception as e:
                print(f"Erro ao garantir material '{name}': {e}")
        return remap

    def populate_stroke(self, stroke, stroke_data, offset, mat_remap):
        """Popula um stroke com os dados salvos, aplicando offset e remapeando material."""
        try:
            # Material: prioriza o remapeamento por nome (leva as cores junto)
            mat_name = stroke_data.get("material_name")
            if mat_name and mat_name in mat_remap:
                stroke.material_index = mat_remap[mat_name]
            else:
                stroke.material_index = stroke_data.get("material_index", 0)

            stroke.use_cyclic = stroke_data.get("use_cyclic", False)

            if hasattr(stroke, 'hardness'):
                stroke.hardness = stroke_data.get("hardness", 1.0)

            if hasattr(stroke, 'vertex_color_fill') and "vertex_color_fill" in stroke_data:
                try:
                    stroke.vertex_color_fill = stroke_data["vertex_color_fill"]
                except (TypeError, ValueError):
                    pass

            # Adicionar pontos
            points_data = stroke_data.get("points", [])
            current_point_count = len(stroke.points)
            if len(points_data) > current_point_count:
                for _ in range(len(points_data) - current_point_count):
                    stroke.points.add(1)

            # Preencher dados dos pontos (com deslocamento do carimbo)
            for i, point_data in enumerate(points_data):
                if i >= len(stroke.points):
                    break

                point = stroke.points[i]
                pos = Vector(point_data["position"]) + offset
                point.co = pos
                point.strength = point_data.get("strength", 1.0)
                point.pressure = point_data.get("pressure", 1.0)

                if hasattr(point, 'vertex_color'):
                    point.vertex_color = point_data.get("vertex_color", [0, 0, 0, 0])

        except Exception as e:
            print(f"Erro ao popular stroke: {e}")

    def load_index(self):
        index_path = get_index_path()
        if index_path.exists():
            with open(index_path, 'r') as f:
                return json.load(f)
        return {}


# ===========================================================================
# OPERADOR: DELETAR CARIMBO
# ===========================================================================
class GP_OT_delete_stamp(bpy.types.Operator):
    """Deleta um carimbo"""
    bl_idname = "gp.delete_stamp"
    bl_label = "Delete Stamp"
    bl_options = {'REGISTER', 'UNDO'}

    stamp_id: StringProperty() #type: ignore
    stamp_name: StringProperty() #type: ignore

    def execute(self, context):
        index_path = get_index_path()
        
        if not index_path.exists():
            return {'CANCELLED'}
        
        with open(index_path, 'r') as f:
            index = json.load(f)
        
        stamp_info = index.get(self.stamp_id)
        if stamp_info:
            stamp_file = get_stamps_path() / stamp_info["file"]
            if stamp_file.exists():
                stamp_file.unlink()
            
            del index[self.stamp_id]
            
            with open(index_path, 'w') as f:
                json.dump(index, f, indent=2)
            
            self.report({'INFO'}, f"Stamp '{self.stamp_name}' deleted")
        
        self.refresh_ui(context)
        return {'FINISHED'}

    def refresh_ui(self, context):
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)


# ===========================================================================
# OPERADOR: ATUALIZAR LISTA
# ===========================================================================
class GP_OT_refresh_stamps(bpy.types.Operator):
    """Atualiza a lista de carimbos"""
    bl_idname = "gp.refresh_stamps"
    bl_label = "Refresh Stamps"
    bl_options = {'REGISTER'}

    def execute(self, context):
        self.refresh_ui(context)
        self.report({'INFO'}, "Stamps list refreshed")
        return {'FINISHED'}

    def refresh_ui(self, context):
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


# ===========================================================================
# PAINEL UI
# ===========================================================================
class GP_PT_stamp_panel(bpy.types.Panel):
    """Painel principal de Carimbos"""
    bl_label = "GP Stamp Tool"
    bl_idname = "GP_PT_stamp_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "GP Stamp"

    def draw(self, context):
        layout = self.layout
        
        obj = context.active_object
        has_gp = obj and api_route.obj_is_gp(obj)
        
        if not has_gp:
            layout.label(text="⚠️ Select a Grease Pencil object", icon='ERROR')
            return
        
        # Info do frame atual
        box = layout.box()
        box.label(text=f"📍 Current Frame: {context.scene.frame_current}", icon='TIME')
        
        # Info do objeto
        box.label(text=f"✏️ Object: {obj.name}", icon='GREASEPENCIL')
        
        layout.separator()
        
        # ===== SALVAR NOVO CARIMBO =====
        box = layout.box()
        box.label(text="📌 SAVE CURRENT DRAWING", icon='ADD')
        row = box.row()
        row.operator("gp.save_stamp", text="Save as Stamp", icon='GREASEPENCIL')
        
        layout.separator()
        
        # ===== LISTA DE CARIMBOS =====
        box = layout.box()
        box.label(text="🎨 STAMP LIBRARY", icon='FILE')
        box.label(text="Click ▶ then click in the viewport to place", icon='RESTRICT_SELECT_OFF')
        
        index_path = get_index_path()
        if not index_path.exists():
            box.label(text="No stamps saved yet", icon='INFO')
            box.label(text="Draw something and click 'Save'", icon='BLANK1')
            return
        
        with open(index_path, 'r') as f:
            index = json.load(f)
        
        if not index:
            box.label(text="No stamps found", icon='INFO')
            return
        
        # Listar stamps
        for stamp_id, info in index.items():
            row = box.row(align=True)
            row.label(text=f"📌 {info['name']}", icon='GREASEPENCIL')
            
            if 'stroke_count' in info:
                row.label(text=f"({info['stroke_count']} strokes)")
            
            # Botão aplicar
            op = row.operator("gp.apply_stamp", text="", icon='PLAY')
            op.stamp_id = stamp_id
            
            # Botão deletar
            op_del = row.operator("gp.delete_stamp", text="", icon='X')
            op_del.stamp_id = stamp_id
            op_del.stamp_name = info['name']
        
        layout.separator()
        
        # ===== BOTÃO ATUALIZAR =====
        row = layout.row()
        row.operator("gp.refresh_stamps", text="Refresh", icon='FILE_REFRESH')


# ===========================================================================
# REGISTRO
# ===========================================================================
classes = (
    GP_OT_save_stamp,
    GP_OT_apply_stamp,
    GP_OT_delete_stamp,
    GP_OT_refresh_stamps,
    GP_PT_stamp_panel,
)

def register():
    # Registrar a API bridge primeiro
    api_route.register_alternative_api_paths()
    
    for cls in classes:
        bpy.utils.register_class(cls)
    
    print("✅ GP Stamp Tool registered")

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    # Desregistrar a API bridge
    api_route.unregister_alternative_api_paths()
    
    print("👋 GP Stamp Tool unregistered")

if __name__ == "__main__":
    register()
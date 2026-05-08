bl_info = {
    "name": "GP Stamp Tool",
    "author": "Seu Nome",
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
from bpy.props import StringProperty

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
    )

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
            "object_name": obj.name
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
                stroke_data = self.capture_stroke(stroke)
                if stroke_data and stroke_data.get("points"):
                    layer_data["strokes"].append(stroke_data)
            
            if layer_data["strokes"]:
                data["strokes_data"].append(layer_data)
        
        return data

    def capture_stroke(self, stroke):
        """Captura um stroke individual"""
        try:
            points = []
            for point in stroke.points:
                points.append({
                    "position": [point.co.x, point.co.y, point.co.z],
                    "strength": point.strength,
                    "pressure": point.pressure,
                    "vertex_color": list(point.vertex_color) if hasattr(point, 'vertex_color') else [0, 0, 0, 0]
                })
            
            return {
                "points": points,
                "material_index": stroke.material_index,
                "use_cyclic": stroke.use_cyclic,
                "line_width": stroke.line_width if hasattr(stroke, 'line_width') else 10,
                "hardness": stroke.hardness if hasattr(stroke, 'hardness') else 1.0
            }
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
    """Aplica um carimbo no frame atual"""
    bl_idname = "gp.apply_stamp"
    bl_label = "Apply Stamp"
    bl_options = {'REGISTER', 'UNDO'}

    stamp_id: StringProperty()

    def execute(self, context):
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
            stamp_data = json.load(f)
        
        # Aplicar no frame atual
        success = self.apply_stamp(obj, context.scene.frame_current, stamp_data)
        
        if success:
            self.report({'INFO'}, f"Stamp '{stamp_info['name']}' applied!")
            # Refresh viewport
            context.view_layer.update()
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Failed to apply stamp")
            return {'CANCELLED'}

    def apply_stamp(self, obj, frame, stamp_data):
        """Aplica os strokes do carimbo usando a API bridge"""
        try:
            gpdata = obj.data
            
            # Sair do modo EDIT se necessário
            if bpy.context.mode == 'EDIT':
                bpy.ops.object.mode_set(mode='OBJECT')
            
            strokes_added = 0
            
            # Para cada layer no stamp
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
                
                if not frame_block:
                    # Criar novo frame
                    if api_route.is_gpv3():
                        frame_block = layer.frames.new(frame)
                    else:
                        frame_block = layer.frames.new(frame, active=True)
                
                if not frame_block or not api_route.is_frame_valid(frame_block):
                    continue
                
                # Acessar strokes via nuclear_strokes
                strokes = frame_block.nuclear_strokes
                
                # Adicionar cada stroke
                for stroke_data in layer_data.get("strokes", []):
                    new_stroke = strokes.new()
                    self.populate_stroke(new_stroke, stroke_data)
                    strokes_added += 1
            
            print(f"✅ Aplicado: {strokes_added} strokes no frame {frame}")
            return strokes_added > 0
            
        except Exception as e:
            print(f"Erro ao aplicar stamp: {e}")
            import traceback
            traceback.print_exc()
            return False

    def populate_stroke(self, stroke, stroke_data):
        """Popula um stroke com os dados salvos"""
        try:
            # Configurar propriedades do stroke
            stroke.material_index = stroke_data.get("material_index", 0)
            stroke.use_cyclic = stroke_data.get("use_cyclic", False)
            
            if hasattr(stroke, 'hardness'):
                stroke.hardness = stroke_data.get("hardness", 1.0)
            
            # Adicionar pontos
            points_data = stroke_data.get("points", [])
            
            # Ajustar número de pontos (se necessário)
            current_point_count = len(stroke.points)
            if len(points_data) > current_point_count:
                # Precisamos adicionar mais pontos
                for i in range(len(points_data) - current_point_count):
                    stroke.points.add(1)
            elif len(points_data) < current_point_count:
                # Remover pontos extras (menos comum)
                pass
            
            # Preencher dados dos pontos
            for i, point_data in enumerate(points_data):
                if i >= len(stroke.points):
                    break
                    
                point = stroke.points[i]
                point.co = point_data["position"]
                point.strength = point_data.get("strength", 1.0)
                point.pressure = point_data.get("pressure", 1.0)
                
                if hasattr(point, 'vertex_color'):
                    vcolor = point_data.get("vertex_color", [0, 0, 0, 0])
                    point.vertex_color = vcolor
                    
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

    stamp_id: StringProperty()
    stamp_name: StringProperty()

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
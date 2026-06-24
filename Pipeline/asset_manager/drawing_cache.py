# drawing_cache.py - CORRIGIDO PARA BLENDER 5.0 / GP v3

import bpy
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
import base64
import zlib
from mathutils import Vector


class DrawingCacheItem:
    """Um drawing armazenado no cache temporário"""
    def __init__(self):
        self.id = ""
        self.name = ""
        self.source_object = ""
        self.source_layer = ""
        self.source_frame = 0
        self.strokes_data = None
        self.thumbnail_base64 = ""
        self.timestamp = ""
        self.tags = []
        self.is_favorite = False

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'source_object': self.source_object,
            'source_layer': self.source_layer,
            'source_frame': self.source_frame,
            'strokes_data': self.strokes_data,
            'thumbnail_base64': self.thumbnail_base64,
            'timestamp': self.timestamp,
            'tags': self.tags,
            'is_favorite': self.is_favorite
        }

    def from_dict(self, data: dict):
        for k, v in data.items():
            if hasattr(self, k):
                setattr(self, k, v)
        return self


class DrawingCacheManager:
    """Gerenciador do cache temporário de drawings para Blender 5.0 / GP v3"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._initialized = True
            self._cache: List[DrawingCacheItem] = []
            self._max_cache_size = 30

    # ------------------------------------------------------------------
    # PERSISTÊNCIA
    # ------------------------------------------------------------------

    def get_cache(self) -> List[DrawingCacheItem]:
        """Carrega e retorna o cache da cena."""
        scene = bpy.context.scene
        raw = getattr(scene, 'drawing_cache_data', "")
        if raw:
            try:
                decompressed = zlib.decompress(base64.b64decode(raw))
                data = json.loads(decompressed.decode('utf-8'))
                self._cache = [DrawingCacheItem().from_dict(item) for item in data]
            except Exception as e:
                print(f"[DrawingCache] Erro ao carregar cache da cena: {e}")
                self._cache = []
        else:
            self._cache = []
        return self._cache

    def save_cache_to_scene(self):
        """Serializa e persiste o cache na propriedade da cena."""
        scene = bpy.context.scene
        if not hasattr(scene, 'drawing_cache_data'):
            print("[DrawingCache] Propriedade 'drawing_cache_data' não registrada na cena.")
            return
        try:
            data = [item.to_dict() for item in self._cache]
            compressed = zlib.compress(json.dumps(data, ensure_ascii=False).encode('utf-8'))
            scene.drawing_cache_data = base64.b64encode(compressed).decode('ascii')
        except Exception as e:
            print(f"[DrawingCache] Erro ao salvar cache: {e}")

    # ------------------------------------------------------------------
    # SERIALIZAÇÃO (leitura do GP)
    # ------------------------------------------------------------------

    def add_drawing(self, name: str = "", tags: list = None) -> Optional[str]:
        """
        Copia o drawing do frame atual do objeto GP ativo para o cache.
        Compatível com Grease Pencil v3 (Blender 5.0).
        """
        context = bpy.context
        obj = context.active_object

        if not obj or obj.type != 'GREASEPENCIL':
            print("[DrawingCache] ❌ Nenhum objeto Grease Pencil ativo.")
            return None

        current_frame = context.scene.frame_current
        gp_data = obj.data

        if not gp_data.layers:
            print("[DrawingCache] ❌ Objeto não tem layers.")
            return None

        # Encontra layer ativo e frame correspondente
        # Prioridade: layer ativo do GP → qualquer layer visível com frame no current_frame
        active_layer, active_frame = self._find_active_layer_and_frame(gp_data, current_frame)

        if not active_layer or not active_frame:
            print(f"[DrawingCache] ❌ Nenhum drawing encontrado no frame {current_frame}.")
            return None

        # Garantir modo Object para leitura estável
        original_mode = context.mode
        if original_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        try:
            strokes_data = self._serialize_drawing_v3(active_frame, obj.name, active_layer.name)
        finally:
            if original_mode != 'OBJECT':
                try:
                    bpy.ops.object.mode_set(mode=original_mode.replace('EDIT_GPENCIL', 'EDIT'))
                except Exception:
                    pass

        if not strokes_data or not strokes_data.get('strokes'):
            print("[DrawingCache] ❌ Nenhum stroke encontrado para serializar.")
            return None

        # Carregar cache atual antes de modificar
        self.get_cache()

        item = DrawingCacheItem()
        item.id = f"drawing_{int(datetime.now().timestamp() * 1000)}"
        item.name = name or f"Drawing_{active_layer.name}_f{current_frame:03d}"
        item.source_object = obj.name
        item.source_layer = active_layer.name
        item.source_frame = current_frame
        item.strokes_data = strokes_data
        item.timestamp = datetime.now().isoformat()
        item.tags = tags or []

        self._cache.insert(0, item)

        # Limitar tamanho
        if len(self._cache) > self._max_cache_size:
            self._cache = self._cache[:self._max_cache_size]

        self.save_cache_to_scene()

        print(f"[DrawingCache] ✅ Salvo: '{item.name}' — {len(strokes_data['strokes'])} strokes")
        return item.id

    def _find_active_layer_and_frame(self, gp_data, current_frame):
        """
        Retorna (layer, frame) para o frame atual.
        Tenta o layer ativo do GP primeiro; cai nos visíveis como fallback.
        """
        # Blender 5 GP: gp_data.layers.active existe
        layers_to_check = []
        active = getattr(gp_data.layers, 'active', None)
        if active and not active.hide:
            layers_to_check.append(active)

        # Adiciona os demais layers visíveis como fallback
        for layer in gp_data.layers:
            if not layer.hide and layer not in layers_to_check:
                layers_to_check.append(layer)

        for layer in layers_to_check:
            for frame in layer.frames:
                if frame.frame_number == current_frame:
                    return layer, frame

        # Segundo fallback: frame mais próximo antes do current_frame
        best_layer = None
        best_frame = None
        best_diff = float('inf')
        for layer in layers_to_check:
            for frame in layer.frames:
                diff = current_frame - frame.frame_number
                if 0 <= diff < best_diff:
                    best_diff = diff
                    best_layer = layer
                    best_frame = frame

        return best_layer, best_frame

    def _serialize_drawing_v3(self, frame, object_name: str, layer_name: str) -> Dict[str, Any]:
        """
        Serializa todos os strokes de um frame GP v3.
        No GP v3, o acesso é via frame.drawing.strokes (não frame.strokes diretamente).
        """
        strokes_data = {
            'object_name': object_name,
            'layer_name': layer_name,
            'strokes': []
        }

        try:
            # GP v3 (Blender 4.3+): strokes estão em frame.drawing.strokes
            drawing = getattr(frame, 'drawing', None)
            if drawing is not None:
                strokes = drawing.strokes
            elif hasattr(frame, 'strokes'):
                # fallback para versões anteriores
                strokes = frame.strokes
            else:
                print("[DrawingCache] ⚠️ Frame não tem 'drawing' nem 'strokes'.")
                return strokes_data

            for stroke in strokes:
                sd = self._serialize_stroke_v3(stroke)
                if sd and len(sd.get('points', [])) >= 1:
                    strokes_data['strokes'].append(sd)

            print(f"[DrawingCache]   📝 {len(strokes_data['strokes'])} strokes serializados")

        except Exception as e:
            print(f"[DrawingCache] ❌ Erro na serialização: {e}")
            import traceback; traceback.print_exc()

        return strokes_data

    def _serialize_stroke_v3(self, stroke) -> Dict[str, Any]:
        """Serializa um stroke individual GP v3."""
        sd = {
            'points': [],
            'line_width': 1,
            'material_index': 0,
            'cyclic': False,
            'hardness': 1.0,
            'start_cap_mode': 0,
            'end_cap_mode': 0,
        }
        try:
            for attr in ('line_width', 'cyclic', 'material_index', 'hardness',
                         'start_cap_mode', 'end_cap_mode'):
                if hasattr(stroke, attr):
                    sd[attr] = getattr(stroke, attr)

            # GP v3: pontos em stroke.points; posição em point.position
            points_src = getattr(stroke, 'points', None)
            if points_src is None:
                return sd

            for point in points_src:
                pos = list(point.position) if hasattr(point, 'position') else [0.0, 0.0, 0.0]
                pd = {
                    'position': pos,
                    'pressure': getattr(point, 'pressure', 1.0),
                    'strength': getattr(point, 'strength', 1.0),
                    'vertex_color': list(getattr(point, 'vertex_color', [1.0, 1.0, 1.0, 1.0])),
                }
                sd['points'].append(pd)

        except Exception as e:
            print(f"[DrawingCache]   ⚠️ Erro em stroke: {e}")

        return sd

    # ------------------------------------------------------------------
    # APLICAÇÃO (escrita no GP)
    # ------------------------------------------------------------------

    def apply_drawing(self, cache_id: str, target_object=None, target_frame: int = None) -> bool:
        """Aplica um drawing do cache ao objeto GP alvo no frame indicado."""
        context = bpy.context

        # Garantir que o cache está carregado
        self.get_cache()

        cache_item = next((i for i in self._cache if i.id == cache_id), None)
        if not cache_item:
            print(f"[DrawingCache] ❌ Item '{cache_id}' não encontrado no cache.")
            return False

        if target_object is None:
            target_object = context.active_object
        if not target_object or target_object.type != 'GREASEPENCIL':
            print("[DrawingCache] ❌ Objeto alvo não é Grease Pencil.")
            return False

        if target_frame is None:
            target_frame = context.scene.frame_current

        original_mode = context.mode
        if original_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        try:
            success = self._apply_strokes_v3(cache_item, target_object, target_frame)
        finally:
            if original_mode != 'OBJECT':
                try:
                    bpy.ops.object.mode_set(mode=original_mode.replace('EDIT_GPENCIL', 'EDIT'))
                except Exception:
                    pass

        if success:
            print(f"[DrawingCache] ✅ '{cache_item.name}' aplicado no frame {target_frame}")
        else:
            print(f"[DrawingCache] ❌ Falha ao aplicar drawing")

        return success

    def _apply_strokes_v3(self, cache_item: DrawingCacheItem, target_object, target_frame: int) -> bool:
        """
        Escreve os strokes do cache_item no target_object/target_frame.
        Usa a API correta do GP v3 (Blender 5.0):
          - frame.drawing para acessar o Drawing
          - drawing.strokes.new(point_count) para criar strokes
        """
        try:
            strokes_data = cache_item.strokes_data
            if not strokes_data or not strokes_data.get('strokes'):
                print("[DrawingCache]   ⚠️ Nenhum stroke no item de cache.")
                return False

            bpy.context.view_layer.objects.active = target_object
            gp_data = target_object.data

            # Obter ou criar o layer de destino
            layer_name = cache_item.source_layer
            layer = gp_data.layers.get(layer_name)
            if not layer:
                layer = gp_data.layers.new(name=layer_name)
                print(f"[DrawingCache]   📁 Layer criada: '{layer_name}'")

            # Obter ou criar o frame de destino
            frame = None
            for f in layer.frames:
                if f.frame_number == target_frame:
                    frame = f
                    break
            if not frame:
                frame = layer.frames.new(frame_number=target_frame)
                print(f"[DrawingCache]   📄 Frame criado: {target_frame}")

            # GP v3: recriar o frame para ter um drawing limpo.
            # drawing.strokes é GreasePencilStrokeSlice somente leitura (sem clear/remove/new).
            # layer.frames.remove() recebe frame_number:int, não o objeto frame.
            frame_number = frame.frame_number
            layer.frames.remove(frame_number)
            frame = layer.frames.new(frame_number=frame_number)
            print(f"[DrawingCache]   🔄 Frame {frame_number} recriado")

            drawing = getattr(frame, 'drawing', None)
            if drawing is None:
                print("[DrawingCache]   ❌ frame.drawing não disponível.")
                return False

            # Adicionar novos strokes
            stroke_count = 0
            for stroke_data in strokes_data['strokes']:
                if self._add_stroke_v3(drawing, stroke_data):
                    stroke_count += 1

            print(f"[DrawingCache]   ✏️ {stroke_count} strokes adicionados")

            # Forçar atualização da viewport
            target_object.data.update_tag()
            for area in bpy.context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()

            return stroke_count > 0

        except Exception as e:
            print(f"[DrawingCache] ❌ Erro ao aplicar strokes: {e}")
            import traceback; traceback.print_exc()
            return False

    def _add_stroke_v3(self, drawing, stroke_data: Dict) -> bool:
        """
        Adiciona um stroke ao Drawing GP v3.
        API real: drawing.add_strokes([point_count]) cria strokes em batch
        e retorna os índices criados. drawing.strokes é somente leitura.
        """
        try:
            points = stroke_data.get('points', [])
            if not points:
                return False

            point_count = len(points)

            # GP v3: criar via drawing.add_strokes([N]) — recebe lista de contagens
            drawing.add_strokes([point_count])

            # O stroke recém-criado é sempre o último
            stroke = drawing.strokes[-1]

            # Propriedades do stroke
            for attr in ('line_width', 'cyclic', 'material_index', 'hardness',
                         'start_cap_mode', 'end_cap_mode'):
                if attr in stroke_data and hasattr(stroke, attr):
                    try:
                        setattr(stroke, attr, stroke_data[attr])
                    except Exception:
                        pass

            # Preencher os pontos (já alocados pelo add_strokes)
            for i, pd in enumerate(points):
                point = stroke.points[i]
                point.position = Vector(pd['position'])
                if hasattr(point, 'pressure'):
                    point.pressure = pd.get('pressure', 1.0)
                if hasattr(point, 'strength'):
                    point.strength = pd.get('strength', 1.0)
                vc = pd.get('vertex_color')
                if vc and hasattr(point, 'vertex_color'):
                    try:
                        point.vertex_color = vc
                    except Exception:
                        pass

            return True

        except Exception as e:
            print(f"[DrawingCache]   ⚠️ Erro ao criar stroke: {e}")
            return False

    # ------------------------------------------------------------------
    # GESTÃO DO CACHE
    # ------------------------------------------------------------------

    def delete_drawing(self, cache_id: str) -> bool:
        self.get_cache()
        for i, item in enumerate(self._cache):
            if item.id == cache_id:
                removed = self._cache.pop(i)
                self.save_cache_to_scene()
                print(f"[DrawingCache] 🗑️ Removido: '{removed.name}'")
                return True
        return False

    def clear_cache(self):
        self.get_cache()
        count = len(self._cache)
        self._cache.clear()
        self.save_cache_to_scene()
        print(f"[DrawingCache] 🗑️ Cache limpo ({count} drawings removidos)")

    def get_recent_drawings(self, limit: int = 10) -> list:
        return self.get_cache()[:limit]


# Função auxiliar para debug no console do Blender
def debug_print_cache():
    manager = DrawingCacheManager()
    cache = manager.get_cache()
    print(f"\n📦 DRAWING CACHE ({len(cache)} items):")
    for item in cache:
        n_strokes = len(item.strokes_data.get('strokes', [])) if item.strokes_data else 0
        print(f"  [{item.id}] '{item.name}' — frame {item.source_frame}, {n_strokes} strokes, tags: {item.tags}")
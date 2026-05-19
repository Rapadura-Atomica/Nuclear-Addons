# drawing_cache_ui.py
import bpy
from .drawing_cache import DrawingCacheManager

class DRAWINGCACHE_PT_panel(bpy.types.Panel):
    """Painel do Drawing Cache Temporário"""
    bl_label = "Drawing Cache (Temp)"
    bl_idname = "DRAWINGCACHE_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Asset Pro"
    bl_parent_id = "ASSETMANAGER_PT_main"
    
    def draw(self, context):
        layout = self.layout
        manager = DrawingCacheManager()
        cache = manager.get_cache()
        
        # Status do objeto atual
        obj = context.active_object
        is_gp = obj and obj.type == 'GREASEPENCIL'
        
        # Botão salvar
        box = layout.box()
        box.label(text="📸 Save Current", icon='GREASEPENCIL')
        row = box.row(align=True)
        save_op = row.operator("drawingcache.save", text="Save Drawing", icon='ADD')
        
        if not is_gp:
            box.label(text="⚠️ Select a Grease Pencil object", icon='ERROR')
        
        layout.separator()
        
        # Galeria do cache
        if not cache:
            layout.label(text="No cached drawings", icon='INFO')
            layout.label(text="Click 'Save Drawing' to start")
            return
        
        box = layout.box()
        box.label(text=f"📋 CACHE ({len(cache)} drawings)", icon='COPY_ID')
        
        # Grid
        columns = 3
        flow = box.grid_flow(row_major=True, columns=columns, even_columns=True, align=True)
        
        for item in cache[:15]:
            self.draw_cache_item(flow, context, item)
        
        # Limpar cache
        if len(cache) > 0:
            layout.separator()
            row = layout.row(align=True)
            row.operator("drawingcache.clear_all", text="Clear All Cache", icon='TRASH')
    
    def draw_cache_item(self, layout, context, cache_item):
        """Desenha um item do cache"""
        box = layout.box()
        
        # Header com nome
        row = box.row(align=True)
        row.label(text=cache_item.name[:20], icon='GREASEPENCIL')
        
        # Info
        col = box.column(align=True)
        col.scale_y = 0.8
        col.label(text=f"📄 Frame: {cache_item.source_frame}")
        col.label(text=f"🎨 {cache_item.source_object[:15]}")
        
        if cache_item.tags:
            tags_str = ", ".join(cache_item.tags[:2])
            col.label(text=f"🏷️ {tags_str}")
        
        # Botões
        btn_row = box.row(align=True)
        btn_row.scale_y = 1.2
        
        op = btn_row.operator("drawingcache.apply", text="APPLY", icon='CHECKMARK')
        op.cache_id = cache_item.id
        
        op = btn_row.operator("drawingcache.delete", text="", icon='X')
        op.cache_id = cache_item.id
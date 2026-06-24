# drawing_cache_operators.py
import bpy
from bpy.props import StringProperty


class DRAWINGCACHE_OT_save(bpy.types.Operator):
    """Salva o drawing atual no cache temporário"""
    bl_idname = "drawingcache.save"
    bl_label = "Save Drawing"
    bl_description = "Save current Grease Pencil drawing to temporary cache"
    bl_options = {'REGISTER', 'UNDO'}

    drawing_name: StringProperty(
        name="Name",
        description="Nome para identificar este drawing",
        default=""
    )  # type: ignore

    tags: StringProperty(
        name="Tags",
        description="Tags separadas por vírgula (ex: cabeca, olho, sorriso)",
        default=""
    )  # type: ignore

    def execute(self, context):
        from .drawing_cache import DrawingCacheManager

        manager = DrawingCacheManager()
        tags_list = [t.strip() for t in self.tags.split(',') if t.strip()]

        cache_id = manager.add_drawing(
            name=self.drawing_name,
            tags=tags_list
        )

        if cache_id:
            self.report({'INFO'}, "✅ Drawing salvo no cache")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "❌ Falha ao salvar. Verifique se há strokes no frame atual.")
            return {'CANCELLED'}

    def invoke(self, context, event):
        obj = context.active_object
        frame = context.scene.frame_current
        if obj and obj.type == 'GREASEPENCIL':
            self.drawing_name = f"{obj.name}_f{frame:03d}"
        else:
            self.report({'ERROR'}, "Selecione um objeto Grease Pencil primeiro.")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=300)


class DRAWINGCACHE_OT_apply(bpy.types.Operator):
    """Aplica um drawing do cache ao objeto atual"""
    bl_idname = "drawingcache.apply"
    bl_label = "Apply Cached Drawing"
    bl_description = "Replace current drawing with cached one"
    bl_options = {'REGISTER', 'UNDO'}

    cache_id: StringProperty()  # type: ignore

    def execute(self, context):
        from .drawing_cache import DrawingCacheManager

        obj = context.active_object
        if not obj or obj.type != 'GREASEPENCIL':
            self.report({'ERROR'}, "Selecione um objeto Grease Pencil alvo.")
            return {'CANCELLED'}

        manager = DrawingCacheManager()
        success = manager.apply_drawing(self.cache_id)

        if success:
            self.report({'INFO'}, "✅ Drawing aplicado")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "❌ Falha ao aplicar drawing")
            return {'CANCELLED'}


class DRAWINGCACHE_OT_delete(bpy.types.Operator):
    """Remove um drawing do cache"""
    bl_idname = "drawingcache.delete"
    bl_label = "Delete"
    bl_description = "Remove este drawing do cache"
    bl_options = {'REGISTER'}

    cache_id: StringProperty()  # type: ignore

    def execute(self, context):
        from .drawing_cache import DrawingCacheManager

        manager = DrawingCacheManager()
        removed = manager.delete_drawing(self.cache_id)
        if removed:
            self.report({'INFO'}, "Drawing removido do cache")
        else:
            self.report({'WARNING'}, "Drawing não encontrado no cache")
        return {'FINISHED'}


class DRAWINGCACHE_OT_clear_all(bpy.types.Operator):
    """Limpa todo o cache"""
    bl_idname = "drawingcache.clear_all"
    bl_label = "Clear All Cache"
    bl_description = "Remove all saved drawings from cache"
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        from .drawing_cache import DrawingCacheManager

        manager = DrawingCacheManager()
        # get_cache() já é chamado dentro de clear_cache()
        count_before = len(manager.get_cache())
        manager.clear_cache()
        self.report({'INFO'}, f"✅ {count_before} drawings removidos do cache")
        return {'FINISHED'}
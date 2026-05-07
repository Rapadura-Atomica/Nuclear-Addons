import bpy
from bpy.props import StringProperty, BoolProperty, EnumProperty, IntVectorProperty
from .grease_pencil_ui import invalidate_library_previews
from .grease_pencil_library import GPLibrary
from typing import Tuple


class GP_OT_save_library(bpy.types.Operator):
    """Salva o objeto Grease Pencil atual como uma biblioteca"""
    bl_idname = "gp.save_library"
    bl_label = "Save as Library"
    bl_description = "Salva todas as poses do objeto atual como uma biblioteca"
    bl_options = {'REGISTER', 'UNDO'}
    
    library_name: StringProperty(
        name="Library Name",
        description="Nome da biblioteca",
        default="my_animation"
    ) #type: ignore 
    
    description: StringProperty(
        name="Description",
        description="Descrição da biblioteca",
        default=""
    ) #type: ignore
    
    frames: StringProperty(
        name="Frames",
        description="Frames para salvar (ex: 1,2,3 ou 1-10). Deixe em branco para todos",
        default=""
    ) #type: ignore 
    
    overwrite: BoolProperty(
        name="Overwrite",
        description="Substituir biblioteca se já existir",
        default=False
    ) #type: ignore 
    
    def execute(self, context):
        # Processar frames
        frames_list = None
        if self.frames.strip():
            frames_list = []
            parts = self.frames.split(',')
            for part in parts:
                part = part.strip()
                if '-' in part:
                    start, end = map(int, part.split('-'))
                    frames_list.extend(range(start, end + 1))
                else:
                    frames_list.append(int(part))
        
        library = GPLibrary()
        success, message = library.save_library(
            library_name=self.library_name,
            description=self.description,
            frames=frames_list,
            overwrite=self.overwrite
        )
        
        if success:
            self.report({'INFO'}, message)
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, message)
            return {'CANCELLED'}
    
    def invoke(self, context, event):
        # Sugerir nome baseado no objeto selecionado
        if context.active_object and context.active_object.type == 'GREASEPENCIL':
            self.library_name = context.active_object.name
        
        return context.window_manager.invoke_props_dialog(self, width=400)


def apply_pose_from_library(self, target_object, pose_id: str) -> Tuple[bool, str]:
    """Aplica uma pose específica da biblioteca ao objeto alvo"""
    if not target_object or target_object.type != 'GREASEPENCIL':
        return False, "Objeto alvo deve ser Grease Pencil"
    
    pose = self.poses.get(pose_id)
    if not pose:
        return False, "Pose não encontrada"
    
    library_path = self.project_path / pose.library_path
    if not library_path.exists():
        return False, f"Arquivo da biblioteca não encontrado: {library_path}"
    
    try:
        # Carregar biblioteca temporariamente
        with bpy.data.libraries.load(str(library_path), link=False, relative=False) as (data_from, data_to):
            data_to.objects = data_from.objects[:]
        
        # Encontrar objeto carregado
        loaded_obj = next((obj for obj in bpy.data.objects if obj.name in data_from.objects), None)
        if not loaded_obj:
            return False, "Não foi possível carregar a biblioteca"
        
        current_frame = bpy.context.scene.frame_current
        
        # Extrair a pose do frame específico
        success = self._extract_pose_from_frame(loaded_obj, pose.frame_number, target_object, current_frame)
        
        # Limpar objeto temporário
        bpy.data.objects.remove(loaded_obj, do_unlink=True)
        
        if success:
            return True, f"✅ Pose '{pose.name}' aplicada no frame {current_frame}"
        else:
            return False, "Erro ao extrair pose da biblioteca"
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, f"Erro ao aplicar pose: {str(e)}"


class GP_OT_import_library(bpy.types.Operator):
    """Importa uma biblioteca externa para o projeto"""
    bl_idname = "gp.import_library"
    bl_label = "Import Library"
    bl_description = "Importa um arquivo .blend de poses para o projeto"
    bl_options = {'REGISTER', 'UNDO'}
    
    filepath: StringProperty(subtype='FILE_PATH')
    library_name: StringProperty(
        name="Library Name",
        description="Nome para a biblioteca no projeto",
        default=""
    )
    
    def execute(self, context):
        library = GPLibrary()
        success, message = library.import_library(self.filepath, self.library_name)
        
        if success:
            self.report({'INFO'}, message)
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, message)
            return {'CANCELLED'}
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class GP_OT_generate_all_thumbs(bpy.types.Operator):
    """Gera thumbnails para todas as poses (um por vez)"""
    bl_idname = "gp.generate_all_thumbs"
    bl_label = "Generate All Thumbnails"
    bl_description = "Generate thumbnails for all poses (one by one)"
    bl_options = {'REGISTER'}
    
    _timer = None
    _poses = None
    _current_index = 0
    _library = None
    
    def modal(self, context, event):
        if event.type == 'TIMER':
            if self._current_index >= len(self._poses):
                self.finish(context)
                return {'FINISHED'}
            
            pose = self._poses[self._current_index]
            print(f"📸 [{self._current_index + 1}/{len(self._poses)}] {pose.name}")
            
            library_path = self._library.project_path / pose.library_path
            if library_path.exists():
                thumb_filename = f"{pose.id}.png"
                thumb_path = self._library.thumbnails_path / thumb_filename
                
                # CORREÇÃO AQUI: Passar o objeto pose
                self._library._generate_thumbnail(pose, thumb_path)
                
                if thumb_path.exists():
                    pose.thumbnail_path = str(thumb_path.relative_to(self._library.project_path))
                else:
                    pose.thumbnail_path = ""
            
            self._current_index += 1
            self._library._save_index()
            
            # Atualizar UI
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
        
        return {'PASS_THROUGH'}
    
    def finish(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        
        from .grease_pencil_library import invalidate_library_previews
        invalidate_library_previews()
        self.report({'INFO'}, f"✅ Generated {len(self._poses)} thumbnails")
        
        self._poses = None
        self._library = None
        self._current_index = 0
    
    def execute(self, context):
        from .grease_pencil_library import GPLibrary
        
        self._library = GPLibrary()
        
        if not self._library.poses:
            self.report({'WARNING'}, "No poses found")
            return {'CANCELLED'}
        
        self._poses = list(self._library.poses.values())
        self._current_index = 0
        
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        context.window_manager.modal_handler_add(self)
        
        self.report({'INFO'}, f"📸 Generating {len(self._poses)} thumbnails...")
        return {'RUNNING_MODAL'}
    
    def cancel(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        self.report({'WARNING'}, "Thumbnail generation cancelled")

class GP_OT_generate_thumbnail(bpy.types.Operator):
    """Gera thumbnail para uma pose específica"""
    bl_idname = "gp.generate_thumbnail"
    bl_label = "Generate Thumbnail"
    bl_description = "Generate thumbnail for this pose"
    bl_options = {'REGISTER'}
    
    pose_id: bpy.props.StringProperty()  #type: ignore
    
    def execute(self, context):
        library = GPLibrary()
        pose = library.poses.get(self.pose_id)
        
        if not pose:
            self.report({'ERROR'}, "Pose not found")
            return {'CANCELLED'}
        
        library_path = library.project_path / pose.library_path
        if not library_path.exists():
            self.report({'ERROR'}, "Library file not found")
            return {'CANCELLED'}
        
        thumb_filename = f"{pose.id}.png"
        thumb_path = library.thumbnails_path / thumb_filename
        
        print(f"📸 Generating thumbnail for {pose.name}")
        
        # Usar o método de thumbnail com câmera atual
        success = library._generate_thumbnail(pose.frame_number, thumb_path)
        
        if success and thumb_path.exists():
            pose.thumbnail_path = str(thumb_path.relative_to(library.project_path))
            library._save_index()
            invalidate_library_previews()
            self.report({'INFO'}, f"Thumbnail generated for {pose.name}")
        else:
            self.report({'WARNING'}, f"Failed to generate thumbnail for {pose.name}")
        
        # Atualizar UI
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        return {'FINISHED'}

class GP_OT_clear_thumbnails(bpy.types.Operator):
    """Limpa todos os thumbnails da biblioteca"""
    bl_idname = "gp.clear_thumbnails"
    bl_label = "Clear Thumbnails"
    bl_description = "Remove all generated thumbnails"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        library = GPLibrary()
        
        if not library.thumbnails_path or not library.thumbnails_path.exists():
            self.report({'WARNING'}, "No thumbnails found")
            return {'CANCELLED'}
        
        thumb_files = list(library.thumbnails_path.glob("*.png"))
        count = len(thumb_files)
        
        for thumb in thumb_files:
            try:
                thumb.unlink()
            except:
                pass
        
        for pose in library.poses.values():
            pose.thumbnail_path = ""
        
        library._save_index()
        invalidate_library_previews()
        
        self.report({'INFO'}, f"Removed {count} thumbnails")
        return {'FINISHED'}

class GP_OT_resync_thumbnails(bpy.types.Operator):
    """Ressincroniza thumbnails no projeto atual"""
    bl_idname = "gp.resync_thumbnails"
    bl_label = "Resync Thumbnails"
    bl_description = "Reassocia thumbnails às poses no projeto atual"
    bl_options = {'REGISTER'}
    
    library_name: bpy.props.StringProperty(
        name="Library",
        description="Specific library to resync (leave empty for all)",
        default=""
    )
    
    def execute(self, context):
        library = GPLibrary()
        
        if self.library_name:
            success, message = library.resync_thumbnails(self.library_name)
        else:
            success, message = library.resync_thumbnails()
        
        if success:
            self.report({'INFO'}, message)
        else:
            self.report({'WARNING'}, message)
        
        # Atualizar UI
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        return {'FINISHED'}
    
    def invoke(self, context, event):
        library = GPLibrary()
        libraries = library.get_libraries()
        
        if len(libraries) > 1:
            # Mostrar opções se houver múltiplas bibliotecas
            return context.window_manager.invoke_props_dialog(self, width=300)
        else:
            return self.execute(context)
    
    def draw(self, context):
        layout = self.layout
        library = GPLibrary()
        libraries = library.get_libraries()
        
        if libraries:
            items = [('ALL', "All Libraries", "Resync all libraries")] + \
                    [(name, name, f"Resync only {name}") for name in libraries.keys()]
            
            layout.prop(self, "library_name", text="Library")
            # Converter para enum na prática
            layout.label(text="Select library to resync:")
            for name in libraries.keys():
                row = layout.row()
                row.operator("gp.resync_thumbnails", text=f"Resync {name}").library_name = name

class GP_OT_refresh_library(bpy.types.Operator):
    """Atualiza a biblioteca"""
    bl_idname = "gp.refresh_library"
    bl_label = "Refresh Library"
    bl_description = "Recarrega a biblioteca de poses"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        # Forçar recriação
        library = GPLibrary()
        
        # Atualizar UI
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        self.report({'INFO'}, f"Biblioteca atualizada: {len(library.poses)} poses em {len(library.libraries)} bibliotecas")
        return {'FINISHED'}

class GP_OT_apply_pose(bpy.types.Operator):
    """Aplica uma pose da biblioteca ao objeto selecionado"""
    bl_idname = "gp.apply_pose"
    bl_label = "Apply Pose"
    bl_description = "Substitui o desenho atual pela pose selecionada"
    bl_options = {'REGISTER', 'UNDO'}
    
    pose_id: bpy.props.StringProperty()  #type: ignore
    
    def execute(self, context):
        library = GPLibrary()
        
        if not context.active_object or context.active_object.type != 'GREASEPENCIL':
            self.report({'ERROR'}, "Selecione um objeto Grease Pencil")
            return {'CANCELLED'}
        
        # Verificar se pose_id foi passada
        if not self.pose_id:
            self.report({'ERROR'}, "Nenhuma pose selecionada")
            return {'CANCELLED'}
        
        success, message = library.apply_pose_from_library(context.active_object, self.pose_id)
        
        if success:
            self.report({'INFO'}, message)
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, message)
            return {'CANCELLED'}

class GP_OT_delete_library(bpy.types.Operator):
    """Remove uma biblioteca completa"""
    bl_idname = "gp.delete_library"
    bl_label = "Delete Library"
    bl_description = "Remove esta biblioteca do projeto"
    bl_options = {'REGISTER', 'UNDO'}
    
    library_name: StringProperty()
    
    def execute(self, context):
        library = GPLibrary()
        success, message = library.delete_library(self.library_name)
        
        if success:
            self.report({'INFO'}, message)
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, message)
            return {'CANCELLED'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)
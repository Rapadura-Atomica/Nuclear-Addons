# grease_pencil_ui.py - VERSÃO CORRIGIDA

import bpy
from .grease_pencil_library import GPLibrary, get_preview_collection, invalidate_library_previews


class GP_PT_library_panel(bpy.types.Panel):
    """Painel principal da biblioteca Grease Pencil - Modo Galeria Organizado"""
    bl_label = "GPose Library"
    bl_idname = "GP_PT_library_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Asset Pro"
    bl_parent_id = "ASSETMANAGER_PT_main"
    
    def draw(self, context):
        layout = self.layout
        library = GPLibrary()
        
        # ==================== BARRA SUPERIOR ====================
        row = layout.row(align=True)
        
        # Botão Salvar
        op = row.operator("gp.save_library", text="", icon='FILE_BLEND')
        if context.active_object and context.active_object.type == 'GREASEPENCIL':
            op.library_name = context.active_object.name
        
        # Botão Importar
        row.operator("gp.import_library", text="", icon='IMPORT')
        
        # Botão Atualizar
        row.operator("gp.refresh_library", text="", icon='FILE_REFRESH')
        
        # Indicador de poses
        row.label(text="", icon='GREASEPENCIL')
        
        # Verificar projeto ativo
        if not library.project_path:
            box = layout.box()
            box.label(text="⚠️ No active project", icon='ERROR')
            box.operator("assetmanager.first_save", text="Start Project", icon='FILE_NEW')
            return
        
        layout.separator()
        
        # ==================== DROPDOWN DE BIBLIOTECAS ====================
        libraries = library.get_libraries()
        
        if not libraries:
            layout.label(text="No libraries found", icon='INFO')
            layout.label(text="Select a Grease Pencil object and click +")
            return
        
        # Pega a biblioteca atual (já existe ou usa a primeira)
        current_lib = getattr(context.scene, 'gp_current_library', None)
        if not current_lib or current_lib not in libraries:
            # NÃO atribuir aqui - apenas usar o primeiro como fallback para display
            current_lib = list(libraries.keys())[0] if libraries else ""
        
        # Dropdown estilizado
        box = layout.box()
        col = box.column(align=True)
        
        # Título do dropdown
        row = col.row(align=True)
        row.label(text="📚 LIBRARY", icon='BOOKMARKS')
        
        # O dropdown em si (apenas leitura - o Blender gerencia a atribuição)
        row = col.row(align=True)
        row.prop(context.scene, 'gp_current_library', text="")
        
        # Informações da biblioteca selecionada
        if current_lib in libraries:
            lib_info = libraries[current_lib]
            frames_count = len(lib_info.get('frames', []))
            poses_in_lib = len([p for p in library.poses.values() if p.library_name == current_lib])
            
            row = col.row(align=True)
            row.label(text=f"📄 {frames_count} frames  |  🖼️ {poses_in_lib} poses")
            
            # Botão de deletar biblioteca
            row = col.row(align=True)
            op = row.operator("gp.delete_library", text="Delete Library", icon='TRASH')
            op.library_name = current_lib
        
        layout.separator()
        
        # ==================== GALERIA DE THUMBS ====================
        poses = library.get_poses(library_name=current_lib)
        
        if not poses:
            layout.label(text=f"No poses in '{current_lib}'", icon='INFO')
            return
        
        # Cabeçalho com info
        row = layout.row()
        row.label(text=f"📸 GALLERY — {len(poses)} poses", icon='RENDER_STILL')
        row = layout.row()
        row.separator()
        
        # Galeria
        self.draw_gallery(layout, context, poses, current_lib)
        
        # Rodapé com dicas
        layout.separator()
        box = layout.box()
        col = box.column(align=True)
        col.scale_y = 0.8
        col.label(text="💡 Click 'Apply' to use pose", icon='INFO')
        col.label(text="📸 Click camera icon to generate thumbnail", icon='RENDER_STILL')
    
    def draw_gallery(self, layout, context, poses, library_name):
        """Desenha a galeria de thumbnails organizada"""
        columns = getattr(context.scene, 'gp_grid_columns', 4)
        
        # Usar grid_flow para layout organizado
        flow = layout.grid_flow(
            row_major=True, 
            columns=columns, 
            even_columns=True,
            even_rows=False,
            align=True
        )
        
        for pose in poses:
            self.draw_thumbnail(flow, context, pose, library_name)
    
    def draw_thumbnail(self, layout, context, pose, library_name):
        """Desenha um thumbnail com informações da pose"""
        
        box = layout.box()
        
        # ===== THUMBNAIL =====
        library = GPLibrary()
        icon_key = library.get_thumbnail_icon(pose.id, library_name, pose.frame_number)
        
        # Área do thumbnail
        thumb_row = box.row()
        thumb_row.scale_y = 3.0
        
        if icon_key:
            pcoll = get_preview_collection()
            if icon_key in pcoll:
                thumb_row.template_icon(icon_value=pcoll[icon_key].icon_id, scale=5.0)
            else:
                thumb_row.label(text=f"Frame {pose.frame_number:03d}", icon='GREASEPENCIL')
        else:
            # Placeholder com botão para gerar
            col = thumb_row.column(align=True)
            col.alignment = 'CENTER'
            col.label(text=f"Frame {pose.frame_number:03d}", icon='IMAGE')
            op = col.operator("gp.generate_thumbnail", text="Generate", icon='RENDER_STILL')
            op.pose_id = pose.id
        
        # ===== INFORMAÇÕES DA POSE =====
        info_row = box.row(align=True)
        info_row.label(text=f"#{pose.frame_number:03d}", icon='TIME')
        
        # Tag de categoria (se tiver)
        if pose.category and pose.category != "library":
            info_row.label(text=pose.category[:8], icon='TAG')
        
        # ===== BOTÃO DE APLICAR =====
        btn_row = box.row(align=True)
        btn_row.scale_y = 1.2
        
        try:
            op = btn_row.operator("gp.apply_pose", text="APPLY", icon='CHECKMARK')
            op.pose_id = pose.id
        except Exception as e:
            btn_row.label(text=f"Error", icon='ERROR')
        
        # Tooltip no hover (opcional, funciona no Blender 3.0+)
        if hasattr(pose, 'description') and pose.description:
            box.label(text=pose.description[:30], icon='INFO')


class GP_PT_library_settings(bpy.types.Panel):
    """Painel de configurações da biblioteca"""
    bl_label = "Library Settings"
    bl_idname = "GP_PT_library_settings"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Asset Pro"
    bl_parent_id = "ASSETMANAGER_PT_main"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        library = GPLibrary()
        
        # ===== CONFIGURAÇÕES DE EXIBIÇÃO =====
        box = layout.box()
        box.label(text="Display Settings:", icon='VIEWZOOM')
        
        # Número de colunas
        row = box.row(align=True)
        row.label(text="Grid Columns:")
        row.prop(context.scene, 'gp_grid_columns', text="")
        
        layout.separator()
        
        # ===== THUMBNAIL ACTIONS =====
        box = layout.box()
        box.label(text="Thumbnail Actions:", icon='RENDER_STILL')
        
        col = box.column(align=True)
        
        # Gerar todos thumbnails da biblioteca atual
        current_lib = getattr(context.scene, 'gp_current_library', None)
        if current_lib:
            row = col.row(align=True)
            row.label(text=f"Library: {current_lib}")
            row = col.row(align=True)
            row.operator("gp.generate_library_thumbs", text="Generate All Thumbs", icon='RENDER_STILL')
        
        # Limpar thumbnails
        col.separator()
        row = col.row(align=True)
        row.operator("gp.clear_thumbnails", text="Clear All Thumbnails", icon='X')
        
        layout.separator()
        
        # ===== ESTATÍSTICAS =====
        box = layout.box()
        box.label(text="Library Stats:", icon='INFO')
        
        col = box.column(align=True)
        col.scale_y = 0.8
        
        # Número de bibliotecas
        libraries_count = len(library.get_libraries())
        col.label(text=f"📚 Libraries: {libraries_count}")
        
        # Número de poses
        poses_count = len(library.poses)
        col.label(text=f"🎨 Total Poses: {poses_count}")
        
        # Thumbnails geradas
        if library.thumbnails_path and library.thumbnails_path.exists():
            thumbs_count = len(list(library.thumbnails_path.glob("*.png")))
            col.label(text=f"📸 Thumbnails: {thumbs_count}")
        
        # Caminho do projeto
        if library.project_path:
            col.separator()
            col.label(text=f"📁 Project: {library.project_path.name}")
        
        layout.separator()
        
        # ===== DICAS =====
        box = layout.box()
        box.label(text="💡 Tips:", icon='QUESTION')
        col = box.column(align=True)
        col.scale_y = 0.8
        col.label(text="• Position camera before saving library")
        col.label(text="• Use dropdown to switch libraries")
        col.label(text="• Click 'Apply' to use a pose")
        col.label(text="• Import libraries to reuse poses")
        col.label(text="• Thumbnails are shared between projects")


class GP_OT_generate_library_thumbs(bpy.types.Operator):
    """Gera thumbnails para todas as poses da biblioteca atual"""
    bl_idname = "gp.generate_library_thumbs"
    bl_label = "Generate All Thumbnails for Library"
    bl_description = "Generate thumbnails for all poses in current library"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        library = GPLibrary()
        current_lib = getattr(context.scene, 'gp_current_library', None)
        
        if not current_lib:
            self.report({'WARNING'}, "No library selected")
            return {'CANCELLED'}
        
        poses = library.get_poses(library_name=current_lib)
        
        if not poses:
            self.report({'WARNING'}, f"No poses found in '{current_lib}'")
            return {'CANCELLED'}
        
        library_info = library.libraries.get(current_lib, {})
        gp_object_name = library_info.get('object_name')
        
        success_count = 0
        for pose in poses:
            thumb_filename = f"{current_lib}_frame_{pose.frame_number:03d}.png"
            thumb_path = library.thumbnails_path / thumb_filename
            
            if not thumb_path.exists():
                success = library.generate_thumbnail_for_frame(pose.frame_number, thumb_path, gp_object_name)
                if success:
                    pose.thumbnail_path = str(thumb_path.relative_to(library.project_path))
                    success_count += 1
        
        library._save_index()
        invalidate_library_previews()
        
        self.report({'INFO'}, f"Generated {success_count}/{len(poses)} thumbnails")
        
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        return {'FINISHED'}


# ===========================================================================
# PROPRIEDADES DA CENA
# ===========================================================================
def register_properties():
    """Registra propriedades para a cena"""
    bpy.types.Scene.gp_current_library = bpy.props.StringProperty(
        name="Current Library",
        description="Currently selected library",
        default=""
    )
    
    bpy.types.Scene.gp_grid_columns = bpy.props.IntProperty(
        name="Grid Columns",
        description="Number of columns in gallery grid",
        default=4,
        min=2,
        max=8,
        step=1
    )

def unregister_properties():
    """Remove propriedades da cena"""
    if hasattr(bpy.types.Scene, 'gp_current_library'):
        del bpy.types.Scene.gp_current_library
    if hasattr(bpy.types.Scene, 'gp_grid_columns'):
        del bpy.types.Scene.gp_grid_columns
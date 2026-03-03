"""
Copyright (C) 2023 Rapadura Atômica Ltda.
Created by Kayo Rodrigues & Rapadura Atômica
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

bl_info = {
    "name": "Bone Node View (Vertex Groups)",
    "author": "Rapadura Estudio LTDA",
    "description": "Visualiza hierarquia de bones e conexões com objetos via vertex groups",
    "blender": (4, 0, 0),
    "version": (1, 2, 0),
    "category": "Animation",
    "location": "Node Editor > Bone Node View",
}

import bpy
from bpy.types import NodeTree, Node, NodeSocket, Operator, Panel, Menu, PropertyGroup
from bpy.props import StringProperty, BoolProperty, FloatVectorProperty, CollectionProperty, PointerProperty, EnumProperty, FloatProperty
from mathutils import Vector
import nodeitems_utils
from nodeitems_utils import NodeCategory, NodeItem

# =============================================================================
# PROPERTIES
# =============================================================================

class BoneNodeAttachment(PropertyGroup):
    """Registro de um objeto anexado a um bone via vertex group"""
    object_name: StringProperty()
    bone_name: StringProperty()
    armature_name: StringProperty()
    influence: FloatProperty(name="Influence", default=1.0, min=0, max=1)

class BoneNodeProperties(PropertyGroup):
    """Propriedades da cena"""
    active_armature: StringProperty(
        name="Active Armature",
        description="Armature para visualizar os bones"
    )
    
    # Filtros
    show_only_selected: BoolProperty(
        name="Show Only Selected Bones",
        description="Mostrar apenas bones selecionados",
        default=False
    )
    show_mesh_objects: BoolProperty(
        name="Show Mesh Objects",
        description="Mostrar objetos malha conectados via vertex groups",
        default=True
    )
    show_grease_pencil: BoolProperty(
        name="Show Grease Pencil",
        description="Mostrar objetos Grease Pencil conectados via vertex groups",
        default=True
    )
    show_empties: BoolProperty(
        name="Show Empties",
        description="Mostrar empties conectados via vertex groups",
        default=False
    )
    
    # Opções de visualização
    min_influence: FloatProperty(
        name="Min Influence",
        description="Influência mínima para considerar conexão",
        default=0.1,
        min=0,
        max=1,
        precision=2
    )
    
    layout_direction: EnumProperty(
        name="Layout Direction",
        items=[
            ('HORIZONTAL', "Horizontal", "Organizar horizontalmente"),
            ('VERTICAL', "Vertical", "Organizar verticalmente"),
        ],
        default='HORIZONTAL'
    )

# =============================================================================
# NODE TREE
# =============================================================================

class BoneNodeTree(NodeTree):
    """Árvore de nós para visualização de bones"""
    bl_idname = "BoneNodeTreeType"
    bl_label = "Bone Node View"
    bl_icon = 'BONE_DATA'

class BoneNodeSocket(NodeSocket):
    """Socket para conexão entre nós"""
    bl_idname = "BoneNodeSocketType"
    bl_label = "Bone Socket"

    def draw(self, context, layout, node, text):
        layout.label(text=text)

    def draw_color(self, context, node):
        return (0.6, 0.6, 0.6, 1.0)

# =============================================================================
# BONE NODE
# =============================================================================

class BoneNode(Node):
    """Nó representando um bone da armature"""
    bl_idname = "BoneNodeType"
    bl_label = "Bone"
    bl_icon = 'BONE_DATA'
    bl_width_default = 280

    # Propriedades do bone
    armature_name: StringProperty()
    bone_name: StringProperty()
    
    # UI
    show_children: BoolProperty(default=True)
    show_objects: BoolProperty(default=True)
    show_vertex_groups: BoolProperty(default=False)

    def init(self, context):
        self.inputs.new("BoneNodeSocketType", "Parent")
        self.outputs.new("BoneNodeSocketType", "Children")
        self.use_custom_color = True
        self.color = (0.3, 0.6, 0.9)
        self.custom_color = (0.3, 0.6, 0.9, 1.0)

    def draw_buttons(self, context, layout):
        props = context.scene.bonenode_props
        armature = bpy.data.objects.get(self.armature_name)
        
        if not armature or armature.type != 'ARMATURE':
            layout.label(text=f"⚠ Armature not found", icon='ERROR')
            return
        
        bone = armature.data.bones.get(self.bone_name)
        if not bone:
            layout.label(text=f"⚠ Bone not found", icon='ERROR')
            return
        
        # HEADER
        box = layout.box()
        row = box.row()
        
        # Ícone baseado no tipo
        if bone.parent:
            row.label(text="", icon='BONE_DATA')
        else:
            row.label(text="", icon='GROUP_BONE')
        
        row.label(text=self.bone_name)
        
        # Botão para selecionar bone
        op = row.operator("bonenode.select_bone", text="", icon='RESTRICT_SELECT_OFF')
        op.armature_name = self.armature_name
        op.bone_name = self.bone_name
        
        # HIERARCHY INFO
        info_box = box.box()
        
        # Parent info
        if bone.parent:
            row = info_box.row()
            row.label(text=f"← Parent: {bone.parent.name}", icon='LINKED')
        else:
            row = info_box.row()
            row.label(text="← Root Bone", icon='GROUP_BONE')
        
        # Children count
        children = [b for b in armature.data.bones if b.parent == bone]
        if children:
            row = info_box.row()
            row.label(text=f"→ {len(children)} child bones", icon='FORWARD')
        
        # VERTEX GROUPS (Objetos influenciados)
        objects_box = layout.box()
        objects_box.label(text="📦 Influenced Objects:", icon='OUTLINER_OB_MESH')
        
        # Buscar objetos que têm vertex group com este bone
        influenced_objs = []
        
        for obj in bpy.data.objects:
            if obj.type not in ['MESH', 'GREASEPENCIL', 'EMPTY']:
                continue
            
            # Filtrar por tipo
            if obj.type == 'MESH' and not props.show_mesh_objects:
                continue
            if obj.type == 'GREASEPENCIL' and not props.show_grease_pencil:
                continue
            if obj.type == 'EMPTY' and not props.show_empties:
                continue
            
            # Verificar se tem vertex group com nome do bone
            if obj.vertex_groups:
                for vg in obj.vertex_groups:
                    if vg.name == self.bone_name:
                        # Calcular influência média (simplificado)
                        influenced_objs.append({
                            'obj': obj,
                            'vg': vg,
                            'influence': 1.0  # Poderia calcular média real
                        })
                        break
        
        if influenced_objs:
            for item in influenced_objs:
                obj = item['obj']
                
                row = objects_box.row(align=True)
                
                # Ícone baseado no tipo
                if obj.type == 'MESH':
                    row.label(text="", icon='MESH_DATA')
                elif obj.type == 'GREASEPENCIL':
                    row.label(text="", icon='GREASEPENCIL')
                else:
                    row.label(text="", icon='EMPTY_DATA')
                
                row.label(text=obj.name)
                
                # Botão para selecionar
                op = row.operator("bonenode.select_object", text="", icon='RESTRICT_SELECT_OFF')
                op.object_name = obj.name
                
                # Botão para mostrar vertex groups
                op = row.operator("bonenode.show_vertex_groups", text="", icon='GROUP_VERTEX')
                op.object_name = obj.name
                op.bone_name = self.bone_name
        else:
            objects_box.label(text="  (no vertex group influence)", icon='BLANK1')
        
        # ARMATURE MODIFIERS (objetos com armature modifier)
        if props.show_mesh_objects:
            mod_box = layout.box()
            mod_box.label(text="⚙️ Armature Modifiers:", icon='MOD_ARMATURE')
            
            mod_objs = []
            for obj in bpy.data.objects:
                if obj.type == 'MESH':
                    for mod in obj.modifiers:
                        if mod.type == 'ARMATURE' and mod.object == armature:
                            mod_objs.append(obj)
                            break
            
            if mod_objs:
                for obj in mod_objs[:5]:  # Limitar a 5 para não poluir
                    row = mod_box.row(align=True)
                    row.label(text=f"  • {obj.name}")
                    op = row.operator("bonenode.select_object", text="", icon='RESTRICT_SELECT_OFF')
                    op.object_name = obj.name
            else:
                mod_box.label(text="  (none)", icon='BLANK1')

    def draw_label(self):
        return f"🦴 {self.bone_name}"

# =============================================================================
# OBJECT NODE (para representar objetos influenciados)
# =============================================================================

class ObjectNode(Node):
    """Nó representando um objeto influenciado por bones"""
    bl_idname = "ObjectNodeType"
    bl_label = "Object"
    bl_icon = 'MESH_DATA'
    bl_width_default = 200

    object_name: StringProperty()
    
    def init(self, context):
        self.inputs.new("BoneNodeSocketType", "Bones")
        self.use_custom_color = True
        self.color = (0.8, 0.8, 0.2)
        self.custom_color = (0.8, 0.8, 0.2, 1.0)

    def draw_buttons(self, context, layout):
        obj = bpy.data.objects.get(self.object_name)
        
        box = layout.box()
        row = box.row()
        
        # Ícone baseado no tipo
        if obj and obj.type == 'MESH':
            row.label(text="", icon='MESH_DATA')
        elif obj and obj.type == 'GREASEPENCIL':
            row.label(text="", icon='GREASEPENCIL')
        else:
            row.label(text="", icon='OBJECT_DATA')
        
        row.label(text=self.object_name or "Unknown")
        
        if obj:
            op = row.operator("bonenode.select_object", text="", icon='RESTRICT_SELECT_OFF')
            op.object_name = self.object_name
            
            # Listar bones que influenciam este objeto
            if obj.vertex_groups:
                box.label(text="Vertex Groups:", icon='GROUP_VERTEX')
                for vg in obj.vertex_groups[:5]:  # Mostrar só 5
                    row = box.row(align=True)
                    row.label(text=f"  • {vg.name}")
                    
                    # Botão para selecionar o bone
                    if context.scene.bonenode_props.active_armature:
                        op = row.operator("bonenode.select_bone", text="", icon='BONE_DATA')
                        op.armature_name = context.scene.bonenode_props.active_armature
                        op.bone_name = vg.name
        else:
            box.label(text="⚠ Object missing", icon='ERROR')

    def draw_label(self):
        obj = bpy.data.objects.get(self.object_name)
        if obj:
            if obj.type == 'MESH':
                return f"📦 {self.object_name}"
            elif obj.type == 'GREASEPENCIL':
                return f"✏️ {self.object_name}"
        return f"📄 {self.object_name}"

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_node_tree():
    """Obtém ou cria a árvore de nós"""
    tree = bpy.data.node_groups.get("BoneNodeView_Tree")
    if not tree:
        tree = bpy.data.node_groups.new("BoneNodeView_Tree", "BoneNodeTreeType")
        print("[BoneNode] Created new node tree")
    return tree

def clear_node_tree():
    """Limpa a árvore de nós"""
    tree = get_node_tree()
    tree.nodes.clear()
    tree.links.clear()
    print("[BoneNode] Cleared node tree")

def get_all_bones(armature):
    """Retorna todos os bones em ordem de hierarquia"""
    bones = []
    
    def add_bone_and_children(bone):
        bones.append(bone)
        for child in bone.children:
            add_bone_and_children(child)
    
    for bone in armature.data.bones:
        if not bone.parent:
            add_bone_and_children(bone)
    
    return bones

def find_objects_influenced_by_bone(armature, bone_name, context):
    """Encontra objetos influenciados por um bone via vertex groups"""
    props = context.scene.bonenode_props
    influenced = []
    
    for obj in bpy.data.objects:
        # Filtrar por tipo
        if obj.type == 'MESH' and not props.show_mesh_objects:
            continue
        if obj.type == 'GREASEPENCIL' and not props.show_grease_pencil:
            continue
        if obj.type not in ['MESH', 'GREASEPENCIL']:
            continue
        
        # Verificar vertex groups
        if obj.vertex_groups:
            for vg in obj.vertex_groups:
                if vg.name == bone_name:
                    influenced.append(obj)
                    break
    
    return influenced

def create_bone_node(armature_name, bone_name, location=None):
    """Cria um nó para um bone"""
    tree = get_node_tree()
    
    # Verificar se já existe
    for node in tree.nodes:
        if (node.bl_idname == "BoneNodeType" and 
            node.armature_name == armature_name and 
            node.bone_name == bone_name):
            return node
    
    # Criar novo nó
    try:
        node = tree.nodes.new("BoneNodeType")
        node.armature_name = armature_name
        node.bone_name = bone_name
        
        if location:
            node.location = location
        
        return node
    except Exception as e:
        print(f"[BoneNode] Error creating bone node: {e}")
        return None

def create_object_node(obj, location=None):
    """Cria um nó para um objeto"""
    tree = get_node_tree()
    
    # Verificar se já existe
    for node in tree.nodes:
        if node.bl_idname == "ObjectNodeType" and node.object_name == obj.name:
            return node
    
    # Criar novo nó
    try:
        node = tree.nodes.new("ObjectNodeType")
        node.object_name = obj.name
        
        if location:
            node.location = location
        
        return node
    except Exception as e:
        print(f"[BoneNode] Error creating object node: {e}")
        return None

def update_node_tree(context):
    """Atualiza a árvore de nós baseado na armature atual"""
    scene = context.scene
    props = scene.bonenode_props
    
    armature = bpy.data.objects.get(props.active_armature)
    if not armature or armature.type != 'ARMATURE':
        return
    
    clear_node_tree()
    tree = get_node_tree()
    
    # Dicionário para guardar posições dos nós
    node_positions = {}
    
    # Função recursiva para criar nós de bones
    def create_bone_nodes_recursive(bone, parent_node=None, x=0, y=0, level=0):
        # Criar nó para este bone
        node = create_bone_node(armature.name, bone.name, location=(x * 300, -y * 80))
        node_positions[bone.name] = (x, y)
        
        # Conectar ao pai se existir
        if parent_node:
            tree.links.new(parent_node.outputs[0], node.inputs[0])
        
        # Processar filhos
        children = [b for b in armature.data.bones if b.parent == bone]
        for i, child in enumerate(children):
            if props.layout_direction == 'HORIZONTAL':
                child_x = x + (i - len(children)/2) * 2
                child_y = y + 2
            else:
                child_x = x + i
                child_y = y + 3
            
            create_bone_nodes_recursive(child, node, child_x, child_y, level + 1)
    
    # Encontrar bones raiz e criar nós
    root_bones = [b for b in armature.data.bones if not b.parent]
    for i, root in enumerate(root_bones):
        if props.layout_direction == 'HORIZONTAL':
            create_bone_nodes_recursive(root, None, i * 4, 0)
        else:
            create_bone_nodes_recursive(root, None, 0, i * 4)
    
    # Criar nós para objetos influenciados
    if props.show_mesh_objects or props.show_grease_pencil:
        processed_objects = set()
        
        for bone in armature.data.bones:
            bone_node = create_bone_node(armature.name, bone.name)
            if not bone_node:
                continue
            
            # Encontrar objetos influenciados por este bone
            influenced = find_objects_influenced_by_bone(armature, bone.name, context)
            
            for obj in influenced:
                if obj.name in processed_objects:
                    continue
                
                processed_objects.add(obj.name)
                
                # Posicionar objeto à direita do bone
                obj_x = node_positions.get(bone.name, (0, 0))[0] * 300 + 400
                obj_y = -node_positions.get(bone.name, (0, 0))[1] * 80
                
                obj_node = create_object_node(obj, location=(obj_x, obj_y))
                
                if obj_node:
                    # Conectar bone ao objeto
                    tree.links.new(bone_node.outputs[0], obj_node.inputs[0])

# =============================================================================
# OPERATORS
# =============================================================================

class BONENODE_OT_select_armature(Operator):
    """Seleciona uma armature para visualização"""
    bl_idname = "bonenode.select_armature"
    bl_label = "Select Armature"
    
    armature_name: StringProperty()
    
    def execute(self, context):
        context.scene.bonenode_props.active_armature = self.armature_name
        update_node_tree(context)
        return {'FINISHED'}

class BONENODE_OT_refresh(Operator):
    """Atualiza a visualização dos nós"""
    bl_idname = "bonenode.refresh"
    bl_label = "Refresh Bone View"
    
    def execute(self, context):
        update_node_tree(context)
        self.report({'INFO'}, "Bone view updated")
        return {'FINISHED'}

class BONENODE_OT_select_bone(Operator):
    """Seleciona um bone na armature"""
    bl_idname = "bonenode.select_bone"
    bl_label = "Select Bone"
    
    armature_name: StringProperty()
    bone_name: StringProperty()
    
    def execute(self, context):
        armature = bpy.data.objects.get(self.armature_name)
        if not armature:
            return {'CANCELLED'}
        
        # Selecionar armature
        bpy.ops.object.select_all(action='DESELECT')
        armature.select_set(True)
        context.view_layer.objects.active = armature
        
        # Entrar em pose mode e selecionar bone
        if context.mode != 'POSE':
            bpy.ops.object.mode_set(mode='POSE')
        
        for bone in armature.pose.bones:
            bone.bone.select = (bone.name == self.bone_name)
        
        return {'FINISHED'}

class BONENODE_OT_select_object(Operator):
    """Seleciona um objeto na viewport"""
    bl_idname = "bonenode.select_object"
    bl_label = "Select Object"
    
    object_name: StringProperty()
    
    def execute(self, context):
        obj = bpy.data.objects.get(self.object_name)
        if obj:
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
        return {'FINISHED'}

class BONENODE_OT_show_vertex_groups(Operator):
    """Mostra os vertex groups do objeto"""
    bl_idname = "bonenode.show_vertex_groups"
    bl_label = "Show Vertex Groups"
    
    object_name: StringProperty()
    bone_name: StringProperty()
    
    def execute(self, context):
        obj = bpy.data.objects.get(self.object_name)
        if obj and obj.type == 'MESH':
            # Selecionar objeto
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
            
            # Ir para aba de vertex groups
            context.area.type = 'PROPERTIES'
            context.area.spaces.active.context = 'DATA'
            
            self.report({'INFO'}, f"Showing vertex groups of {self.object_name}")
        
        return {'FINISHED'}

class BONENODE_OT_auto_layout(Operator):
    """Organiza os nós automaticamente"""
    bl_idname = "bonenode.auto_layout"
    bl_label = "Auto Layout"
    
    def execute(self, context):
        update_node_tree(context)
        return {'FINISHED'}

class BONENODE_OT_cleanup_node(Operator):
    """Remove um nó órfão"""
    bl_idname = "bonenode.cleanup_node"
    bl_label = "Cleanup Node"
    
    node_name: StringProperty()
    
    def execute(self, context):
        tree = get_node_tree()
        node = tree.nodes.get(self.node_name)
        if node:
            tree.nodes.remove(node)
        return {'FINISHED'}

class BONENODE_OT_find_vertex_group_connections(Operator):
    """Busca todas as conexões via vertex groups"""
    bl_idname = "bonenode.find_connections"
    bl_label = "Find Vertex Group Connections"
    
    def execute(self, context):
        props = context.scene.bonenode_props
        armature = bpy.data.objects.get(props.active_armature)
        
        if not armature:
            self.report({'ERROR'}, "No active armature")
            return {'CANCELLED'}
        
        connections = []
        for obj in bpy.data.objects:
            if obj.type not in ['MESH', 'GREASEPENCIL']:
                continue
            
            if obj.vertex_groups:
                for vg in obj.vertex_groups:
                    # Verificar se existe bone com este nome
                    if armature.data.bones.get(vg.name):
                        connections.append({
                            'object': obj.name,
                            'bone': vg.name
                        })
        
        self.report({'INFO'}, f"Found {len(connections)} vertex group connections")
        return {'FINISHED'}

# =============================================================================
# MENUS
# =============================================================================

class BONENODE_MT_menu(Menu):
    bl_label = "Bone View"
    bl_idname = "BONENODE_MT_menu"

    def draw(self, context):
        layout = self.layout
        layout.operator("bonenode.refresh", icon='FILE_REFRESH')
        layout.operator("bonenode.auto_layout", icon='GRID')
        layout.operator("bonenode.find_connections", icon='GROUP_VERTEX')
        layout.separator()
        
        # Lista de armatures disponíveis
        layout.label(text="Armatures:", icon='ARMATURE_DATA')
        armatures = [obj for obj in bpy.data.objects if obj.type == 'ARMATURE']
        for arm in armatures:
            op = layout.operator("bonenode.select_armature", text=arm.name)
            op.armature_name = arm.name

# =============================================================================
# PANELS
# =============================================================================

class BONENODE_PT_main_panel(Panel):
    """Painel principal na viewport 3D"""
    bl_label = "Bone Node View"
    bl_idname = "BONENODE_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Bone View"

    def draw(self, context):
        layout = self.layout
        props = context.scene.bonenode_props
        
        # Seleção de armature
        box = layout.box()
        box.label(text="Armature:", icon='ARMATURE_DATA')
        
        armatures = [obj for obj in bpy.data.objects if obj.type == 'ARMATURE']
        if armatures:
            row = box.row(align=True)
            row.prop(props, "active_armature", text="")
            row.operator("bonenode.refresh", text="", icon='FILE_REFRESH')
            
            # Stats
            if props.active_armature:
                arm = bpy.data.objects.get(props.active_armature)
                if arm:
                    box.label(text=f"Bones: {len(arm.data.bones)}")
                    
                    # Contar objetos com vertex groups
                    influenced_objs = set()
                    for obj in bpy.data.objects:
                        if obj.type in ['MESH', 'GREASEPENCIL'] and obj.vertex_groups:
                            for vg in obj.vertex_groups:
                                if arm.data.bones.get(vg.name):
                                    influenced_objs.add(obj.name)
                    
                    box.label(text=f"Influenced Objects: {len(influenced_objs)}")
        else:
            box.label(text="No armatures found", icon='ERROR')
        
        # Opções de visualização
        box = layout.box()
        box.label(text="Display Options:", icon='VIEWZOOM')
        box.prop(props, "show_mesh_objects")
        box.prop(props, "show_grease_pencil")
        box.prop(props, "show_empties")
        box.prop(props, "layout_direction")
        
        # Ações
        box = layout.box()
        box.label(text="Actions:", icon='TOOL_SETTINGS')
        box.operator("bonenode.auto_layout", icon='GRID')
        box.operator("bonenode.find_connections", icon='GROUP_VERTEX')
        
        # Abrir node editor
        box.operator("bonenode.open_node_editor", icon='NODE')

class BONENODE_PT_editor_panel(Panel):
    """Painel no Node Editor"""
    bl_label = "Bone View"
    bl_idname = "BONENODE_PT_editor_panel"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Bone View"

    @classmethod
    def poll(cls, context):
        return (context.space_data.node_tree and 
                context.space_data.node_tree.bl_idname == "BoneNodeTreeType")

    def draw(self, context):
        layout = self.layout
        props = context.scene.bonenode_props
        tree = context.space_data.node_tree
        
        # Stats
        if tree:
            bone_nodes = len([n for n in tree.nodes if n.bl_idname == "BoneNodeType"])
            object_nodes = len([n for n in tree.nodes if n.bl_idname == "ObjectNodeType"])
            
            box = layout.box()
            box.label(text=f"Total Nodes: {len(tree.nodes)}")
            box.label(text=f"  🦴 Bones: {bone_nodes}")
            box.label(text=f"  📦 Objects: {object_nodes}")
        
        # Filtros rápidos
        box = layout.box()
        box.label(text="Quick Filters:", icon='FILTER')
        box.prop(props, "show_mesh_objects", text="Meshes")
        box.prop(props, "show_grease_pencil", text="Grease Pencil")
        
        # Ações
        box = layout.box()
        box.label(text="Actions:", icon='TOOL_SETTINGS')
        box.operator("bonenode.refresh", icon='FILE_REFRESH')
        box.operator("bonenode.auto_layout", icon='GRID')

class BONENODE_OT_open_node_editor(Operator):
    """Abre o Node Editor com a visualização de bones"""
    bl_idname = "bonenode.open_node_editor"
    bl_label = "Open Bone View"
    
    def execute(self, context):
        # Procurar área de node editor
        for area in context.screen.areas:
            if area.type == 'NODE_EDITOR':
                space = area.spaces.active
                space.tree_type = "BoneNodeTreeType"
                space.node_tree = get_node_tree()
                update_node_tree(context)
                return {'FINISHED'}
        
        # Se não encontrou, criar split
        area = context.area
        if area.type == 'VIEW_3D':
            bpy.ops.screen.area_split(direction='VERTICAL', factor=0.6)
            
            for new_area in context.screen.areas:
                if new_area != area and new_area.type == 'EMPTY':
                    new_area.type = 'NODE_EDITOR'
                    space = new_area.spaces.active
                    space.tree_type = "BoneNodeTreeType"
                    space.node_tree = get_node_tree()
                    update_node_tree(context)
                    break
        
        return {'FINISHED'}

# =============================================================================
# REGISTRATION
# =============================================================================

classes = (
    # Properties
    BoneNodeAttachment,
    BoneNodeProperties,
    
    # Node system
    BoneNodeTree,
    BoneNodeSocket,
    BoneNode,
    ObjectNode,
    
    # Operators
    BONENODE_OT_select_armature,
    BONENODE_OT_refresh,
    BONENODE_OT_select_bone,
    BONENODE_OT_select_object,
    BONENODE_OT_show_vertex_groups,
    BONENODE_OT_auto_layout,
    BONENODE_OT_cleanup_node,
    BONENODE_OT_find_vertex_group_connections,
    BONENODE_OT_open_node_editor,
    
    # Menus
    BONENODE_MT_menu,
    
    # Panels
    BONENODE_PT_main_panel,
    BONENODE_PT_editor_panel,
)

def menu_func(self, context):
    self.layout.menu("BONENODE_MT_menu")

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Registrar categoria de nós
    node_categories = [
        NodeCategory("BONE_NODES", "Bone Nodes", items=[
            NodeItem("BoneNodeType", label="Bone"),
            NodeItem("ObjectNodeType", label="Object"),
        ]),
    ]
    nodeitems_utils.register_node_categories("BONE_NODE_CATEGORIES", node_categories)
    
    # Propriedades da cena
    bpy.types.Scene.bonenode_props = PointerProperty(type=BoneNodeProperties)
    bpy.types.Scene.bonenode_attachments = CollectionProperty(type=BoneNodeAttachment)
    
    # Adicionar ao menu
    bpy.types.NODE_MT_editor_menus.append(menu_func)
    
    print("[BoneNode] Registered successfully")

def unregister():
    bpy.types.NODE_MT_editor_menus.remove(menu_func)
    
    try:
        nodeitems_utils.unregister_node_categories("BONE_NODE_CATEGORIES")
    except:
        pass
    
    del bpy.types.Scene.bonenode_props
    del bpy.types.Scene.bonenode_attachments
    
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except:
            pass
    
    print("[BoneNode] Unregistered successfully")

if __name__ == "__main__":
    register()
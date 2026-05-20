bl_info = {
    "name": "Nuclear Pegs",
    "author": "Nuclear",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Nuclear",
    "description": "Sistema de Pegs para animação 2D",
    "category": "Animation",
}

import bpy
from bpy.types import Panel, Operator, PropertyGroup
from bpy.props import StringProperty, PointerProperty, EnumProperty


# ─── PROPRIEDADES GLOBAIS DA CENA ───────────────────────────────────────────

class NUCLEAR_PG_scene(PropertyGroup):
    active_rig: StringProperty(
        name="Rig Ativo",
        description="Nome da coleção do personagem ativo",
        default=""
    ) #type: ignore

    active_peg: StringProperty(
    name="Peg Ativa",
    default=""
    )

# ─── UTILITÁRIOS ─────────────────────────────────────────────────────────────

def get_rigs(context):
    """Retorna todas as coleções que contém um Empty com is_rig_root = True."""
    rigs = []
    for col in bpy.data.collections:
        for obj in col.objects:
            if obj.type == 'EMPTY' and obj.get("is_rig_root"):
                rigs.append(col)
                break
    return rigs


def get_active_rig_collection(context):
    name = context.scene.nuclear_pegs.active_rig
    return bpy.data.collections.get(name)

def get_rig_root(collection):
    """Retorna o Empty raiz de uma coleção."""
    for obj in collection.objects:
        if obj.type == 'EMPTY' and obj.get("is_rig_root"):
            return obj
    return None


def get_pegs(collection):
    """Retorna todos os Empties marcados como peg dentro da coleção."""
    return [obj for obj in collection.objects if obj.get("is_peg")]


def get_chain_above(peg):
    """Retorna a cadeia de pegs acima da peg selecionada, do topo até ela."""
    chain = []
    current = peg
    while current is not None:
        chain.append(current)
        parent = current.parent
        if parent and (parent.get("is_peg") or parent.get("is_rig_root")):
            current = parent
        else:
            break
    chain.reverse()
    return chain


# ─── OPERADOR: REGISTRAR RIG RAIZ ────────────────────────────────────────────

class NUCLEAR_OT_register_rig(Operator):
    bl_idname = "nuclear.register_rig"
    bl_label = "Registrar Rig Raiz"
    bl_description = "Cria um Empty raiz na coleção ativa e a registra como personagem"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        col = context.collection

        if col is None:
            self.report({'ERROR'}, "Nenhuma coleção ativa.")
            return {'CANCELLED'}

        # Verifica se já existe um rig raiz nessa coleção
        for obj in col.objects:
            if obj.get("is_rig_root"):
                self.report({'WARNING'}, "Essa coleção já possui um Rig raiz.")
                return {'CANCELLED'}

        # Cria o Empty raiz
        bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0))
        root = context.active_object
        root.name = f"Root_{col.name}"
        root["is_rig_root"] = True

        # Garante que está na coleção correta
        for c in root.users_collection:
            c.objects.unlink(root)
        col.objects.link(root)

        # Define como rig ativo na cena
        context.scene.nuclear_pegs.active_rig = col.name

        self.report({'INFO'}, f"Rig raiz criado em: {col.name}")
        return {'FINISHED'}


# ─── PAINEL PRINCIPAL ─────────────────────────────────────────────────────────

class NUCLEAR_PT_main(Panel):
    bl_label = "Nuclear Pegs"
    bl_idname = "NUCLEAR_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Nuclear"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = scene.nuclear_pegs

        # ── Seleção de personagem ──
        layout.label(text="Personagem:")
        rigs = get_rigs(context)

        if rigs:
            col_box = layout.box()
            for col in rigs:
                row = col_box.row()
                is_active = (col.name == props.active_rig)
                op = row.operator(
                    "nuclear.set_active_rig",
                    text=col.name,
                    depress=is_active
                )
                op.rig_name = col.name
        else:
            layout.label(text="Nenhum personagem registrado.", icon='INFO')

        layout.operator("nuclear.register_rig", icon='ARMATURE_DATA')
        layout.separator()

        # ── Hierarquia de pegs ──
        active_col = get_active_rig_collection(context)
        if active_col:
            root = get_rig_root(active_col)
            if root:
                layout.label(text="Hierarquia:")
                box = layout.box()
                draw_peg_tree(box, root, 0, props.active_peg)

            layout.separator()
            layout.label(text="Operadores:")
            layout.operator("nuclear.create_peg", icon='ADD')
            layout.operator("nuclear.link_drawing", icon='LINKED')


# ─── OPERADORES ─────────────────────────────────────────────

class NUCLEAR_OT_set_active_rig(Operator):
    bl_idname = "nuclear.set_active_rig"
    bl_label = "Definir Rig Ativo"
    bl_options = {'REGISTER', 'UNDO'}

    rig_name: StringProperty() #type: ignore

    def execute(self, context):
        context.scene.nuclear_pegs.active_rig = self.rig_name
        return {'FINISHED'}

class NUCLEAR_OT_create_peg(Operator):
    bl_idname = "nuclear.create_peg"
    bl_label = "Criar Peg"
    bl_description = "Cria uma nova Peg na coleção do personagem ativo"
    bl_options = {'REGISTER', 'UNDO'}

    peg_name: StringProperty(name="Nome da Peg", default="Peg_Nova")
    parent_peg_name: StringProperty(name="Peg Pai", default="")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "peg_name")

        col = get_active_rig_collection(context)
        if col:
            pegs = get_pegs(col)
            root = get_rig_root(col)
            layout.label(text="Peg Pai:")
            layout.prop_search(self, "parent_peg_name", context.scene, "objects")

    def execute(self, context):
        col = get_active_rig_collection(context)
        if not col:
            self.report({'ERROR'}, "Nenhum personagem ativo.")
            return {'CANCELLED'}

        # Cria o Empty da peg
        bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0))
        peg = context.active_object
        peg.name = self.peg_name
        peg["is_peg"] = True

        # Garante que está na coleção correta
        for c in peg.users_collection:
            c.objects.unlink(peg)
        col.objects.link(peg)

        # Define o pai
        parent_obj = bpy.data.objects.get(self.parent_peg_name)
        if parent_obj and (parent_obj.get("is_peg") or parent_obj.get("is_rig_root")):
            peg.parent = parent_obj
            peg.matrix_parent_inverse = parent_obj.matrix_world.inverted()
        else:
            # Se nenhum pai válido, sobe para o root
            root = get_rig_root(col)
            if root:
                peg.parent = root
                peg.matrix_parent_inverse = root.matrix_world.inverted()

        self.report({'INFO'}, f"Peg '{self.peg_name}' criada.")
        return {'FINISHED'}

class NUCLEAR_OT_link_drawing(Operator):
    bl_idname = "nuclear.link_drawing"
    bl_label = "Vincular Drawing"
    bl_description = "Vincula o objeto selecionado na viewport como Drawing da Peg ativa"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        col = get_active_rig_collection(context)
        if not col:
            self.report({'ERROR'}, "Nenhum personagem ativo.")
            return {'CANCELLED'}

        props = context.scene.nuclear_pegs
        peg = bpy.data.objects.get(props.active_peg)

        if not peg or not peg.get("is_peg"):
            self.report({'ERROR'}, "Nenhuma Peg ativa selecionada no painel.")
            return {'CANCELLED'}

        selected = [
            obj for obj in context.selected_objects
            if obj != peg and not obj.get("is_peg") and not obj.get("is_rig_root")
        ]

        if not selected:
            self.report({'ERROR'}, "Selecione ao menos um objeto na viewport para vincular.")
            return {'CANCELLED'}

        for obj in selected:
            obj["is_drawing"] = True
            obj.parent = peg
            obj.matrix_parent_inverse = peg.matrix_world.inverted()

            # Garante que está na coleção do personagem
            if obj.name not in col.objects:
                col.objects.link(obj)

        self.report({'INFO'}, f"{len(selected)} drawing(s) vinculado(s) à '{peg.name}'.")
        return {'FINISHED'}

class NUCLEAR_OT_set_active_peg(Operator):
    bl_idname = "nuclear.set_active_peg"
    bl_label = "Definir Peg Ativa"
    bl_options = {'REGISTER', 'UNDO'}

    peg_name: StringProperty()

    def execute(self, context):
        context.scene.nuclear_pegs.active_peg = self.peg_name

        # Seleciona o Empty na viewport também
        obj = bpy.data.objects.get(self.peg_name)
        if obj:
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj

        return {'FINISHED'}


def draw_peg_tree(layout, obj, depth, active_peg_name):
    """Recursivo: desenha a árvore de pegs com indentação."""
    for child in obj.children:
        if child.get("is_peg"):
            row = layout.row()
            # Indentação visual por profundidade
            row.separator(factor=depth * 2.0)
            is_active = (child.name == active_peg_name)
            op = row.operator(
                "nuclear.set_active_peg",
                text=child.name,
                icon='EMPTY_AXIS',
                depress=is_active
            )
            op.peg_name = child.name

            # Mostra drawings filhos
            for drawing in child.children:
                if drawing.get("is_drawing"):
                    row2 = layout.row()
                    row2.separator(factor=(depth + 1) * 2.0)
                    row2.label(text=drawing.name, icon='MESH_PLANE')

            # Desce recursivamente
            draw_peg_tree(layout, child, depth + 1, active_peg_name)

# ─── REGISTRO ────────────────────────────────────────────────────────────────

classes = [
    NUCLEAR_PG_scene,
    NUCLEAR_OT_register_rig,
    NUCLEAR_OT_set_active_rig,
    NUCLEAR_OT_create_peg,
    NUCLEAR_OT_link_drawing,
    NUCLEAR_OT_set_active_peg,
    NUCLEAR_PT_main,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.nuclear_pegs = PointerProperty(type=NUCLEAR_PG_scene)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.nuclear_pegs

if __name__ == "__main__":
    register()
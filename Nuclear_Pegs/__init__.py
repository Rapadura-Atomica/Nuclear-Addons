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
            rig_names = [col.name for col in rigs]
            col_box = layout.box()
            for name in rig_names:
                row = col_box.row()
                is_active = (name == props.active_rig)
                op = row.operator(
                    "nuclear.set_active_rig",
                    text=name,
                    depress=is_active
                )
                op.rig_name = name
        else:
            layout.label(text="Nenhum personagem registrado.", icon='INFO')

        layout.separator()
        layout.operator("nuclear.register_rig", icon='ARMATURE_DATA')


# ─── OPERADOR: DEFINIR RIG ATIVO ─────────────────────────────────────────────

class NUCLEAR_OT_set_active_rig(Operator):
    bl_idname = "nuclear.set_active_rig"
    bl_label = "Definir Rig Ativo"
    bl_options = {'REGISTER', 'UNDO'}

    rig_name: StringProperty() #type: ignore

    def execute(self, context):
        context.scene.nuclear_pegs.active_rig = self.rig_name
        return {'FINISHED'}


# ─── REGISTRO ────────────────────────────────────────────────────────────────

classes = [
    NUCLEAR_PG_scene,
    NUCLEAR_OT_register_rig,
    NUCLEAR_OT_set_active_rig,
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
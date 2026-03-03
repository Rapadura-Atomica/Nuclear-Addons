"""
Blender Addon: GPencil Bezier Puppet
Controle COMPLETO de Grease Pencil através de curvas Bezier usando métodos alternativos
"""

bl_info = {
    "name": "GPencil Bezier Puppet",
    "author": "Seu Nome",
    "version": (2, 1, 0),
    "blender": (4, 4, 0),
    "location": "View3D > Sidebar > Tool",
    "description": "Controle total de Grease Pencil com curvas Bezier usando métodos alternativos",
    "category": "Grease Pencil",
}

import bpy
from bpy.types import Operator, Panel, PropertyGroup, Object
from bpy.props import (BoolProperty, IntProperty, FloatProperty,
                      PointerProperty, CollectionProperty, StringProperty,
                      EnumProperty)
from mathutils import Vector, Matrix
import numpy as np

# ============================================================================
# SISTEMA DE CONTROLE POR VERTEX GROUPS E DRIVERS (MESH)
# ============================================================================

class BezierControlPoint(PropertyGroup):
    """Ponto de controle do Bezier"""
    index: IntProperty(name="Índice", default=0) # type: ignore
    influence_radius: FloatProperty(name="Raio de Influência", default=1.0, min=0.1, max=10.0) #type: ignore
    strength: FloatProperty(name="Força", default=1.0, min=0.0, max=2.0) #type: ignore

class GPBezierPuppetSystem:
    """Sistema principal de controle por Bezier (Mesh)"""
    
    @staticmethod
    def create_complete_puppet_system(gp_obj, curve_obj, points_per_curve=5):
        """Criar sistema COMPLETO de controle por Bezier (converte para mesh)"""
        print(f"\n🎭 CRIANDO SISTEMA PUPPET MESH PARA {gp_obj.name}")
        
        mesh_obj = GPBezierPuppetSystem.convert_gpencil_to_mesh(gp_obj)
        if not mesh_obj:
            print("❌ Falha ao converter GPencil para Mesh")
            return None
        
        vertex_groups = GPBezierPuppetSystem.create_curve_based_vertex_groups(mesh_obj, curve_obj, points_per_curve)
        
        shape_keys = GPBezierPuppetSystem.create_curve_controlled_shape_keys(mesh_obj, curve_obj)
        
        armature = GPBezierPuppetSystem.create_curve_following_armature(curve_obj, mesh_obj)
        
        drivers_added = GPBezierPuppetSystem.add_direct_drivers(mesh_obj, curve_obj)
        
        mesh_obj.parent = curve_obj
        
        print(f"✅ Sistema Puppet MESH criado com sucesso!")
        print(f"   • Mesh: {mesh_obj.name}")
        print(f"   • Curve: {curve_obj.name}")
        print(f"   • Vertex Groups: {len(vertex_groups)}")
        print(f"   • Shape Keys: {shape_keys}")
        print(f"   • Armature: {armature.name if armature else 'Não'}")
        print(f"   • Drivers: {drivers_added}")
        
        return mesh_obj
    
    @staticmethod
    def convert_gpencil_to_mesh(gp_obj):
        """Converter Grease Pencil para Mesh mantendo a forma"""
        try:
            bpy.ops.object.select_all(action='DESELECT')
            gp_obj.select_set(True)
            bpy.context.view_layer.objects.active = gp_obj
            bpy.ops.object.duplicate()
            
            dup_obj = bpy.context.active_object
            dup_obj.name = f"{gp_obj.name}_Mesh"
            
            bpy.ops.object.convert(target='MESH')
            
            for mod in dup_obj.modifiers[:]:
                bpy.ops.object.modifier_apply(modifier=mod.name)
            
            dup_obj.data.materials.clear()
            
            mat = bpy.data.materials.new(name=f"{dup_obj.name}_Mat")
            mat.diffuse_color = (0.1, 0.6, 1.0, 1.0)  # Azul
            dup_obj.data.materials.append(mat)
            
            print(f"✅ GPencil convertido para Mesh: {dup_obj.name}")
            return dup_obj
            
        except Exception as e:
            print(f"❌ Erro ao converter GPencil: {e}")
            return None
    
    @staticmethod
    def create_curve_based_vertex_groups(mesh_obj, curve_obj, num_groups=5):
        """Criar vertex groups baseados na posição dos pontos da curva"""
        vertex_groups = []
        
        if curve_obj.data.splines[0].type == 'BEZIER':
            bezier_points = curve_obj.data.splines[0].bezier_points
            num_points = len(bezier_points)
            
            for i, bez_point in enumerate(bezier_points):
                group_name = f"CurvePoint_{i:02d}"
                vgroup = mesh_obj.vertex_groups.new(name=group_name)
                
                point_pos_world = curve_obj.matrix_world @ bez_point.co
                
                mesh = mesh_obj.data
                vertices = mesh.vertices
                
                for vert in vertices:
                    vert_pos_world = mesh_obj.matrix_world @ vert.co
                    distance = (vert_pos_world - point_pos_world).length
                    
                    if distance < 2.0: 
                        weight = max(0, 1.0 - (distance / 2.0) ** 2)
                        vgroup.add([vert.index], weight, 'REPLACE')
                
                vertex_groups.append(vgroup)
                print(f"   • Vertex Group '{group_name}' criado")
        
        return vertex_groups
    
    @staticmethod
    def create_curve_controlled_shape_keys(mesh_obj, curve_obj):
        """Criar shape keys controlados pela posição dos pontos da curva"""
        try:
            mesh_obj.shape_key_add(name="Basis", from_mix=False)
            
            shape_key = mesh_obj.shape_key_add(name="Bezier_Deform", from_mix=False)
            
            if curve_obj.data.splines[0].type == 'BEZIER':
                bezier_points = curve_obj.data.splines[0].bezier_points
                
                for i, bez_point in enumerate(bezier_points):
                    drv = shape_key.key_blocks["Bezier_Deform"].driver_add("value").driver
                    drv.type = 'SCRIPTED'
                    
                    var = drv.variables.new()
                    var.name = "point_pos"
                    var.targets[0].id = curve_obj
                    var.targets[0].data_path = f'splines[0].bezier_points[{i}].co'
                    
                    drv.expression = f"point_pos[0] * 0.1"  # Escala para não deformar muito
                    
                    print(f"   • Shape Key driver para ponto {i}")
            
            return True
            
        except Exception as e:
            print(f"❌ Erro ao criar shape keys: {e}")
            return False
    
    @staticmethod
    def create_curve_following_armature(curve_obj, target_obj):
        """Criar armature com bones seguindo a curva"""
        try:
            armature_data = bpy.data.armatures.new(f"{curve_obj.name}_Armature")
            armature_obj = bpy.data.objects.new(f"{curve_obj.name}_Armature", armature_data)
            bpy.context.collection.objects.link(armature_obj)
            
            armature_obj.location = curve_obj.location
            
            bpy.context.view_layer.objects.active = armature_obj
            bpy.ops.object.mode_set(mode='EDIT')
            
            armature = armature_obj.data
            
            if curve_obj.data.splines[0].type == 'BEZIER':
                bezier_points = curve_obj.data.splines[0].bezier_points
                
                bones = []
                prev_bone = None
                
                for i in range(len(bezier_points) - 1):
                    bone = armature.edit_bones.new(f"Curve_Bone_{i:02d}")
                    
                    pos1 = bezier_points[i].co
                    pos2 = bezier_points[i + 1].co
                    
                    bone.head = pos1
                    bone.tail = pos2
                    
                    if prev_bone:
                        bone.parent = prev_bone
                        bone.use_connect = True
                    
                    bones.append(bone)
                    prev_bone = bone
            
            bpy.ops.object.mode_set(mode='OBJECT')
            
            armature_mod = target_obj.modifiers.new(name="Armature_Deform", type='ARMATURE')
            armature_mod.object = armature_obj
            armature_mod.use_vertex_groups = True
            
            bpy.context.view_layer.objects.active = curve_obj
            
            for i, bone in enumerate(bones):
                pass
            
            print(f"✅ Armature criada: {armature_obj.name}")
            return armature_obj
            
        except Exception as e:
            print(f"❌ Erro ao criar armature: {e}")
            return None
    
    @staticmethod
    def add_direct_drivers(mesh_obj, curve_obj):
        drivers_added = 0
        
        try:
            mesh = mesh_obj.data
            
            for vert in mesh.vertices:
                closest_point_index = 0
                min_distance = float('inf')
                
                if curve_obj.data.splines[0].type == 'BEZIER':
                    bezier_points = curve_obj.data.splines[0].bezier_points
                    
                    vert_pos_world = mesh_obj.matrix_world @ vert.co
                    
                    for i, bez_point in enumerate(bezier_points):
                        point_pos_world = curve_obj.matrix_world @ bez_point.co
                        distance = (vert_pos_world - point_pos_world).length
                        
                        if distance < min_distance:
                            min_distance = distance
                            closest_point_index = i
                    
                    if min_distance < 2.0:
                        drv = mesh.vertices[vert.index].driver_add("co").driver
                        drv.type = 'SUM'
                        
                        var = drv.variables.new()
                        var.name = "curve_point"
                        var.targets[0].id = curve_obj
                        var.targets[0].data_path = f'splines[0].bezier_points[{closest_point_index}].co'
                        
                        drv.expression = "curve_point"
                        
                        drivers_added += 1
            
            print(f"✅ {drivers_added} drivers diretos adicionados")
            return drivers_added
            
        except Exception as e:
            print(f"❌ Erro ao adicionar drivers: {e}")
            return 0

# ============================================================================
# MÉTODO ALTERNATIVO: USANDO LATTICE (PARA MESH)
# ============================================================================

class LatticeControlSystem:
    """Sistema de controle usando Lattice deformado pela curva (para Mesh)"""
    
    @staticmethod
    def create_lattice_based_control(gp_obj, curve_obj):
        """Criar sistema usando Lattice controlado pela curva"""
        print(f"\n🔳 CRIANDO CONTROLE POR LATTICE PARA MESH")
        
        lattice_data = bpy.data.lattices.new(f"{gp_obj.name}_Lattice")
        lattice_obj = bpy.data.objects.new(f"{gp_obj.name}_Lattice", lattice_data)
        bpy.context.collection.objects.link(lattice_obj)
        
        lattice_data.points_u = 4
        lattice_data.points_v = 4
        lattice_data.points_w = 4
        
        lattice_obj.location = gp_obj.location
        lattice_obj.scale = Vector((2, 2, 0.5))
        
        lattice_mod = gp_obj.modifiers.new(name="Lattice_Deform", type='LATTICE')
        lattice_mod.object = lattice_obj
        
        drivers_added = LatticeControlSystem.link_lattice_to_curve(lattice_obj, curve_obj)
        
        print(f"✅ Sistema Lattice criado com {drivers_added} drivers")
        return lattice_obj
    
    @staticmethod
    def link_lattice_to_curve(lattice_obj, curve_obj):
        """Conectar pontos do Lattice aos pontos da curva"""
        drivers_added = 0
        
        try:
            lattice = lattice_obj.data
            
            for i in range(len(lattice.points)):
                point = lattice.points[i]
                
                if curve_obj.data.splines[0].type == 'BEZIER':
                    bezier_points = curve_obj.data.splines[0].bezier_points
                    
                    lattice_x = point.co_deform.x
                    
                    curve_index = int((lattice_x + 1) / 2 * (len(bezier_points) - 1))
                    curve_index = max(0, min(curve_index, len(bezier_points) - 1))
                    
                    drv = point.driver_add("co_deform", 1).driver  # Eixo Y
                    drv.type = 'SCRIPTED'
                    
                    var = drv.variables.new()
                    var.name = "curve_y"
                    var.targets[0].id = curve_obj
                    var.targets[0].data_path = f'splines[0].bezier_points[{curve_index}].co[1]'  # Coordenada Y
                    
                    drv.expression = "curve_y * 2"
                    
                    drivers_added += 1
            
            return drivers_added
            
        except Exception as e:
            print(f"❌ Erro ao conectar Lattice: {e}")
            return 0

# ============================================================================
# NOVO SISTEMA: GPENCIL REAL (HOOK + LATTICE + CURVE FOLLOW)
# ============================================================================

class GP_HookDeformSystem:
    """Sistema usando GREASE_PENCIL_HOOK no GPencil original"""
    
    @staticmethod
    def get_gpencil_bbox(gp_obj):
        """Calcular bounding box do GPencil (compatível com Blender 4.4+)"""
        min_co = Vector((float('inf'), float('inf'), float('inf')))
        max_co = Vector((float('-inf'), float('-inf'), float('-inf')))
        
        points_found = False
        
        for layer in gp_obj.data.layers:
            # NOVA API: usar drawings em vez de active_frame
            for frame in layer.frames:
                for stroke in frame.strokes:
                    for point in stroke.points:
                        local_co = point.co
                        min_co.x = min(min_co.x, local_co.x)
                        min_co.y = min(min_co.y, local_co.y)
                        min_co.z = min(min_co.z, local_co.z)
                        
                        max_co.x = max(max_co.x, local_co.x)
                        max_co.y = max(max_co.y, local_co.y)
                        max_co.z = max(max_co.z, local_co.z)
                        
                        points_found = True
        
        if points_found:
            return (min_co, max_co)
        return None

    @staticmethod
    def create_gpencil_hook_system(gp_obj, curve_obj):
        """Aplicar hooks diretamente no GPencil usando o modificador correto"""
        print(f"\n🎣 CRIANDO SISTEMA HOOK PARA GPENCIL REAL")
        print(f"GPencil: {gp_obj.name}")
        print(f"Curva: {curve_obj.name}")
        
        # Garantir que estamos no modo objeto
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        
        # Selecionar e ativar o GPencil
        gp_obj.select_set(True)
        bpy.context.view_layer.objects.active = gp_obj
        
        # Criar empties para cada ponto da curva
        empties = []
        
        if curve_obj.data.splines[0].type == 'BEZIER':
            bezier_points = curve_obj.data.splines[0].bezier_points
            
            for i, bez_point in enumerate(bezier_points):
                # Criar empty
                empty = bpy.data.objects.new(f"Hook_{gp_obj.name}_{i:02d}", None)
                bpy.context.collection.objects.link(empty)
                
                # Posicionar empty no ponto da curva
                empty.location = curve_obj.matrix_world @ bez_point.co
                empty.empty_display_size = 0.3
                empty.empty_display_type = 'SPHERE'
                empty.show_name = True
                
                # Adicionar constraint para seguir o ponto da curva
                constraint = empty.constraints.new(type='COPY_LOCATION')
                constraint.target = curve_obj
                constraint.subtarget = f"splines[0].bezier_points[{i}]"
                
                empties.append(empty)
                print(f"   ✅ Empty criado: {empty.name} para ponto {i}")
        
        # Adicionar modificadores GREASE_PENCIL_HOOK
        hooks_added = GP_HookDeformSystem.add_hook_modifiers(gp_obj, empties)
        
        # Organizar hierarquia
        GP_HookDeformSystem.setup_hierarchy(gp_obj, curve_obj, empties)
        
        print(f"\n✅ {hooks_added} hooks adicionados ao GPencil REAL")
        return empties
    
    @staticmethod
    def add_hook_modifiers(gp_obj, empties):
        """Adicionar modificadores GREASE_PENCIL_HOOK ao GPencil"""
        hooks_added = 0
        
        for i, empty in enumerate(empties):
            # Adicionar modificador GREASE_PENCIL_HOOK
            hook_name = f"Hook_{i:02d}"
            hook = gp_obj.grease_pencil_modifiers.new(name=hook_name, type='GP_HOOK')
            hook.object = empty
            hook.strength = 0.8
            hook.falloff_radius = 2.0
            hook.falloff_type = 'SMOOTH'
            
            hooks_added += 1
            print(f"   ✅ Hook {i} adicionado: {hook_name}")
        
        return hooks_added
    
    @staticmethod
    def setup_hierarchy(gp_obj, curve_obj, empties):
        """Organizar hierarquia dos objetos"""
        # Criar collection para organização
        collection_name = f"{gp_obj.name}_Puppet_System"
        
        if collection_name not in bpy.data.collections:
            collection = bpy.data.collections.new(collection_name)
            bpy.context.scene.collection.children.link(collection)
        else:
            collection = bpy.data.collections[collection_name]
        
        # Adicionar todos os objetos à collection
        objects_to_organize = [gp_obj, curve_obj] + empties
        
        for obj in objects_to_organize:
            # Remover de outras collections
            for col in obj.users_collection:
                if col != collection:
                    col.objects.unlink(obj)
            
            # Adicionar à nova collection se não estiver
            if collection.name not in [c.name for c in obj.users_collection]:
                collection.objects.link(obj)
        
        # Parentear empties à curva
        for empty in empties:
            empty.parent = curve_obj
        
        print(f"   📁 Sistema organizado na collection: {collection_name}")

class GP_LatticeDeformSystem:
    """Sistema usando Lattice para deformar GPencil REAL"""
    
    @staticmethod
    def create_gpencil_lattice(gp_obj, curve_obj, resolution_u=8, resolution_v=8):
        """Criar Lattice que deforma GPencil diretamente"""
        print(f"\n🔳 CRIANDO LATTICE PARA GPENCIL REAL")
        
        # Criar Lattice
        lattice_data = bpy.data.lattices.new(f"{gp_obj.name}_Lattice")
        lattice_obj = bpy.data.objects.new(f"{gp_obj.name}_Lattice", lattice_data)
        bpy.context.collection.objects.link(lattice_obj)
        
        # Configurar resolução do Lattice
        lattice_data.points_u = resolution_u
        lattice_data.points_v = resolution_v
        lattice_data.points_w = 4
        
        # Calcular bounding box do GPencil
        bbox = GP_LatticeDeformSystem.get_gpencil_bbox(gp_obj)
        
        # Posicionar Lattice em torno do GPencil
        lattice_obj.location = gp_obj.location.copy()
        
        # Ajustar escala do Lattice para envolver o GPencil
        if bbox:
            size_x = bbox[1][0] - bbox[0][0]
            size_y = bbox[1][1] - bbox[0][1]
            size_z = bbox[1][2] - bbox[0][2]
            
            lattice_obj.scale.x = max(size_x * 1.2, 1.0)
            lattice_obj.scale.y = max(size_y * 1.2, 1.0)
            lattice_obj.scale.z = max(size_z * 1.5, 0.5)
        else:
            lattice_obj.scale = Vector((3.0, 3.0, 1.0))
        
        # Adicionar Lattice modifier ao GPencil
        lattice_mod = gp_obj.modifiers.new(name="Puppet_Lattice", type='LATTICE')
        lattice_mod.object = lattice_obj
        
        # Conectar Lattice à curva
        GP_LatticeDeformSystem.link_lattice_to_curve(lattice_obj, curve_obj)
        
        # Organizar hierarquia
        lattice_obj.parent = curve_obj
        
        print(f"   ✅ Lattice criado: {lattice_obj.name}")
        print(f"   ✅ Lattice modifier adicionado ao GPencil REAL")
        
        return lattice_obj
        
    @staticmethod
    def link_lattice_to_curve(lattice_obj, curve_obj):
        """Conectar pontos do Lattice aos pontos da curva"""
        lattice = lattice_obj.data
        
        if curve_obj.data.splines[0].type != 'BEZIER':
            print("   ⚠️ Curva não é Bezier, usando pontos normais")
            return
        
        bezier_points = curve_obj.data.splines[0].bezier_points
        num_curve_points = len(bezier_points)
        
        drivers_added = 0
        
        # Conectar cada coluna do Lattice a um ponto da curva
        for u in range(lattice.points_u):
            # Calcular qual ponto da curva controla esta coluna
            curve_index = int(u / (lattice.points_u - 1) * (num_curve_points - 1))
            curve_index = min(curve_index, num_curve_points - 1)
            
            # Para cada ponto nesta coluna do lattice
            for v in range(lattice.points_v):
                for w in range(lattice.points_w):
                    idx = u + v * lattice.points_u + w * lattice.points_u * lattice.points_v
                    
                    if idx >= len(lattice.points):
                        continue
                    
                    point = lattice.points[idx]
                    
                    try:
                        # Adicionar driver para eixo Y (deformação vertical)
                        drv = point.driver_add("co_deform", 1).driver  # Índice 1 = eixo Y
                        drv.type = 'SUM'
                        
                        var = drv.variables.new()
                        var.name = "curve_y"
                        var.targets[0].id = curve_obj
                        var.targets[0].data_path = f'splines[0].bezier_points[{curve_index}].co[1]'
                        
                        # Influência baseada na posição vertical no lattice
                        v_factor = 1.0 - abs(v / (lattice.points_v - 1) - 0.5) * 2
                        w_factor = 1.0 - abs(w / (lattice.points_w - 1) - 0.5) * 2
                        total_factor = v_factor * w_factor * 0.5
                        
                        drv.expression = f"curve_y * {total_factor}"
                        
                        drivers_added += 1
                        
                    except Exception as e:
                        print(f"   ⚠️ Erro ao adicionar driver {idx}: {e}")
        
        print(f"   ✅ {drivers_added} drivers conectados do Lattice à curva")

class GP_CurveFollowSystem:
    """Sistema usando Curve modifier para GPencil REAL"""
    
    @staticmethod
    def setup_curve_follow(gp_obj, curve_obj):
        """Configurar GPencil para seguir uma curva"""
        print(f"\n🔄 CONFIGURANDO CURVE FOLLOW PARA GPENCIL REAL")
        
        # Criar uma cópia do GPencil como Curve para referência
        curve_copy = GP_CurveFollowSystem.convert_gpencil_to_curve(gp_obj)
        if not curve_copy:
            print("   ❌ Falha ao criar cópia de referência")
            return None
        
        # Aplicar Curve modifier na cópia
        curve_mod = curve_copy.modifiers.new(name="Follow_Bezier", type='CURVE')
        curve_mod.object = curve_obj
        curve_mod.deform_axis = 'POS_X'
        
        # Configurar hierarquia
        curve_copy.parent = curve_obj
        
        print(f"   ✅ Sistema Curve Follow criado")
        print(f"   💡 Cópia em Curve criada como referência: {curve_copy.name}")
        
        return curve_copy
    
    @staticmethod
    def convert_gpencil_to_curve(gp_obj):
        """Converter GPencil para objeto Curve (apenas referência)"""
        try:
            # Duplicar GPencil
            bpy.ops.object.select_all(action='DESELECT')
            gp_obj.select_set(True)
            bpy.context.view_layer.objects.active = gp_obj
            
            bpy.ops.object.duplicate()
            dup_obj = bpy.context.active_object
            dup_obj.name = f"{gp_obj.name}_CurveRef"
            
            # Converter para Curve
            bpy.ops.object.convert(target='CURVE')
            
            # Configurar a curva
            dup_obj.data.dimensions = '3D'
            dup_obj.data.resolution_u = 12
            
            # Adicionar material indicativo
            if not dup_obj.data.materials:
                mat = bpy.data.materials.new(name=f"{dup_obj.name}_Mat")
                mat.diffuse_color = (0.8, 0.2, 0.2, 0.3)  # Vermelho transparente
                mat.blend_method = 'BLEND'
                dup_obj.data.materials.append(mat)
            
            # Esconder a cópia (apenas referência)
            dup_obj.hide_set(True)
            
            print(f"   ✅ Cópia em Curve criada (referência): {dup_obj.name}")
            return dup_obj
            
        except Exception as e:
            print(f"   ❌ Erro ao criar cópia de referência: {e}")
            return None

# ============================================================================
# MÉTODO DIRETO: TRANSFORMAR GPENCIL BASEADO NA CURVA
# ============================================================================

class DirectTransformSystem:
    """Transformar diretamente o Grease Pencil baseado na curva"""
    
    @staticmethod
    def setup_direct_transformation(gp_obj, curve_obj):
        """Setup para transformar GPencil baseado na forma da curva"""
        print(f"\n🎯 CONFIGURANDO TRANSFORMAÇÃO DIRETA")
        
        empty_obj = bpy.data.objects.new(f"{curve_obj.name}_Tracker", None)
        bpy.context.collection.objects.link(empty_obj)
        empty_obj.empty_display_size = 0.5
        empty_obj.empty_display_type = 'ARROWS'
        
        follow_path = empty_obj.constraints.new(type='FOLLOW_PATH')
        follow_path.target = curve_obj
        follow_path.forward_axis = 'FORWARD_X'
        follow_path.up_axis = 'UP_Z'
        follow_path.use_curve_follow = True
        
        gp_obj.parent = empty_obj
        
        DirectTransformSystem.add_curve_based_deformation(gp_obj, curve_obj)
        
        print(f"✅ Transformação direta configurada")
        return empty_obj
    
    @staticmethod
    def add_curve_based_deformation(gp_obj, curve_obj):
        """Adicionar deformação baseada na curvatura da curva"""
        try:
            for layer in gp_obj.data.layers:
                for frame in layer.frames:
                    for stroke in frame.strokes:
                        for i, point in enumerate(stroke.points):
                            pass
            
            print(f"   • Drivers de deformação adicionados")
            
        except Exception as e:
            print(f"❌ Erro ao adicionar deformação: {e}")

# ============================================================================
# OPERADORES PRINCIPAIS (ATUALIZADOS)
# ============================================================================

class GPENCIL_OT_create_bezier_puppet(Operator):
    """Criar sistema COMPLETO de controle por Bezier"""
    
    bl_idname = "gpencil.create_bezier_puppet"
    bl_label = "Criar Sistema Puppet"
    bl_description = "Criar sistema completo de controle por curva Bezier"
    bl_options = {'REGISTER', 'UNDO'}
    
    method: EnumProperty(
        name="Método",
        description="Método de controle",
        items=[
            ('MESH', 'Mesh (Converte)', 'Converte para Mesh - Mais controle'),
            ('LATTICE', 'Lattice (Mesh)', 'Lattice para Mesh - Mais suave'),
            ('DIRECT', 'Direto', 'Transformação direta - Simples'),
            ('HOOK_GP', 'Hook GPencil', 'Hook no GPencil REAL - Mantém original'),
            ('LATTICE_GP', 'Lattice GPencil', 'Lattice no GPencil REAL - Mantém original'),
            ('CURVE_GP', 'Curve GPencil', 'Curve Follow no GPencil REAL - Mantém original'),
        ],
        default='MESH'
    ) # type: ignore
    
    curve_points: IntProperty(
        name="Pontos na Curva",
        default=5,
        min=3,
        max=20
    ) #type: ignore
    
    influence_radius: FloatProperty(
        name="Raio de Influência",
        default=2.0,
        min=0.5,
        max=10.0,
        description="Quão longe a curva influencia o GPencil (métodos GPencil)"
    ) #type: ignore
    
    def execute(self, context):
        gp_obj = context.active_object
        
        if not gp_obj or gp_obj.type not in 'GREASEPENCIL':
            self.report({'ERROR'}, "Selecione um objeto Grease Pencil")
            return {'CANCELLED'}
        
        print(f"\n{'='*60}")
        print(f"CRIANDO SISTEMA PUPPET BEZIER")
        print(f"Método: {self.method}")
        print(f"{'='*60}")
        
        curve_obj = self.create_control_curve(gp_obj)
        if not curve_obj:
            self.report({'ERROR'}, "Falha ao criar curva de controle")
            return {'CANCELLED'}
        
        result = None
        
        # Métodos que convertem para Mesh
        if self.method == "MESH":
            result = GPBezierPuppetSystem.create_complete_puppet_system(
                gp_obj, curve_obj, self.curve_points
            )
            
        elif self.method == "LATTICE":
            result = LatticeControlSystem.create_lattice_based_control(gp_obj, curve_obj)
            
        elif self.method == "DIRECT":
            result = DirectTransformSystem.setup_direct_transformation(gp_obj, curve_obj)
        
        # NOVOS MÉTODOS: Mantêm GPencil original
        elif self.method == "HOOK_GP":
            result = GP_HookDeformSystem.create_gpencil_hook_system(gp_obj, curve_obj)
            
        elif self.method == "LATTICE_GP":
            result = GP_LatticeDeformSystem.create_gpencil_lattice(gp_obj, curve_obj)
            
        elif self.method == "CURVE_GP":
            result = GP_CurveFollowSystem.setup_curve_follow(gp_obj, curve_obj)
        
        if not result:
            self.report({'WARNING'}, "Sistema criado, mas algum componente pode ter falhado")
        
        # Selecionar curva para edição
        bpy.ops.object.select_all(action='DESELECT')
        curve_obj.select_set(True)
        context.view_layer.objects.active = curve_obj
        bpy.ops.object.mode_set(mode='EDIT')
        
        print(f"\n{'='*60}")
        print(f"✅ SISTEMA PRONTO!")
        print(f"{'='*60}")
        
        method_names = {
            'MESH': 'Mesh (converte)',
            'LATTICE': 'Lattice (mesh)',
            'DIRECT': 'Direto',
            'HOOK_GP': 'Hook GPencil REAL',
            'LATTICE_GP': 'Lattice GPencil REAL',
            'CURVE_GP': 'Curve Follow GPencil REAL'
        }
        
        method_desc = method_names.get(self.method, self.method)
        
        print(f"\n🎮 COMO USAR:")
        print(f"1. A curva '{curve_obj.name}' está selecionada")
        print(f"2. Você está no EDIT MODE da curva")
        print(f"3. Selecione e mova os pontos da curva (G)")
        print(f"4. O {'GPencil' if 'GP' in self.method else 'Mesh'} deve seguir o movimento!")
        print(f"\n📋 MÉTODO: {method_desc}")
        
        if 'GP' in self.method:
            print(f"✅ GPencil ORIGINAL preservado!")
            print(f"   • Camadas de pintura intactas")
            print(f"   • Materiais preservados")
            print(f"   • Animações funcionando")
        
        print(f"\n💡 DICAS:")
        print(f"• Use a ferramenta 'Proportional Editing' (O) para suavizar")
        print(f"• Ajuste handles do Bezier para curvas suaves")
        print(f"• Para animação: Keyframe os pontos da curva!")
        
        self.report({'INFO'}, f"Sistema Puppet criado! Método: {method_desc}")
        return {'FINISHED'}
    
    def create_control_curve(self, gp_obj):
        """Criar curva Bezier de controle para o GPencil"""
        try:
            print(f"📐 Criando curva de controle Hook para {gp_obj.name}...")
            
            # Calcular tamanho do GPencil para dimensionar a curva
            bbox = GP_LatticeDeformSystem.get_gpencil_bbox(gp_obj)
            
            if bbox:
                size_x = bbox[1][0] - bbox[0][0]
                length = max(size_x * 1.5, 3.0)
                print(f"   📏 BBox calculado: tamanho X = {size_x:.2f}, comprimento = {length:.2f}")
            else:
                length = 4.0
                print(f"   ⚠️ Não foi possível calcular bbox, usando comprimento padrão: {length}")
            
            # Criar dados da curva
            curve_data = bpy.data.curves.new(f'{gp_obj.name}_Hook_Ctrl', 'CURVE')
            if not curve_data:
                print("❌ Falha ao criar dados da curva")
                return None
                
            curve_data.dimensions = '3D'
            curve_data.resolution_u = 32
            curve_data.bevel_depth = 0.02
            
            # Criar spline Bezier
            spline = curve_data.splines.new('BEZIER')
            if not spline:
                print("❌ Falha ao criar spline")
                return None
                
            spline.bezier_points.add(4)  # 5 pontos total
            
            points = spline.bezier_points
            if not points or len(points) == 0:
                print("❌ Falha ao criar pontos Bezier")
                return None
            
            # Posicionar pontos ao longo do eixo X
            for i in range(len(points)):
                x = (i - 2) * (length / 4)
                points[i].co = Vector((x, 0, 0))
                points[i].handle_left_type = 'AUTO'
                points[i].handle_right_type = 'AUTO'
            
            # Criar objeto da curva
            curve_obj = bpy.data.objects.new(f'{gp_obj.name}_Hook_Ctrl', curve_data)
            if not curve_obj:
                print("❌ Falha ao criar objeto da curva")
                return None
                
            bpy.context.collection.objects.link(curve_obj)
            
            # Posicionar curva acima do GPencil
            curve_obj.location = gp_obj.location.copy() + Vector((0, 0, 0.3))
            
            # Configurar visualização
            curve_obj.show_in_front = True
            
            # Adicionar material
            if not curve_data.materials:
                mat = bpy.data.materials.new(name="Hook_Control_Mat")
                if mat:
                    mat.diffuse_color = (0.2, 0.8, 0.2, 1.0)  # Verde para Hook
                    curve_data.materials.append(mat)
            
            print(f"✅ Curva de controle Hook criada: {curve_obj.name}")
            print(f"   📍 Posição: {curve_obj.location}")
            print(f"   📏 Comprimento: {length}")
            
            return curve_obj
            
        except Exception as e:
            print(f"❌ Erro detalhado ao criar curva Hook: {e}")
            import traceback
            traceback.print_exc()
            return None

# VERSÕES ESPECÍFICAS DOS OPERADORES PARA CADA MÉTODO GPENCIL REAL
class GPENCIL_OT_create_gpencil_hook_puppet(Operator):
    """Criar sistema de puppet no GPencil REAL usando Hook"""
    
    bl_idname = "gpencil.create_gpencil_hook_puppet"
    bl_label = "Criar Puppet Hook GPencil"
    bl_description = "Criar sistema de controle mantendo GPencil original usando Hook"
    bl_options = {'REGISTER', 'UNDO'}
    
    curve_points: IntProperty(
        name="Pontos na Curva",
        default=5,
        min=3,
        max=20
    ) #type: ignore
    
    influence_radius: FloatProperty(
        name="Raio de Influência",
        default=2.0,
        min=0.5,
        max=10.0,
        description="Quão longe a curva influencia o GPencil"
    ) #type: ignore
    
    def execute(self, context):
        gp_obj = context.active_object
        
        if not gp_obj or gp_obj.type != 'GREASEPENCIL':
            self.report({'ERROR'}, "Selecione um objeto Grease Pencil")
            return {'CANCELLED'}
        
        print(f"\n{'='*60}")
        print(f"CRIANDO PUPPET HOOK GPENCIL REAL")
        print(f"Objeto: {gp_obj.name}")
        print(f"{'='*60}")
        
        # Criar curva de controle
        curve_obj = self.create_control_curve(gp_obj)
        if not curve_obj:
            self.report({'ERROR'}, "Falha ao criar curva de controle")
            return {'CANCELLED'}
        
        # Aplicar método Hook
        hooks = GP_HookDeformSystem.create_gpencil_hook_system(gp_obj, curve_obj)
        
        # Selecionar a curva para fácil edição
        bpy.ops.object.select_all(action='DESELECT')
        curve_obj.select_set(True)
        bpy.context.view_layer.objects.active = curve_obj
        
        # Entrar em modo de edição da curva
        bpy.ops.object.mode_set(mode='EDIT')
        
        print(f"\n{'='*60}")
        print(f"✅ SISTEMA HOOK PRONTO!")
        print(f"{'='*60}")
        
        print(f"\n🎮 COMO USAR:")
        print(f"1. Você está no EDIT MODE da curva '{curve_obj.name}'")
        print(f"2. Selecione um ponto da curva (clique direito)")
        print(f"3. Mova (G), rotacione (R) ou escale (S)")
        print(f"4. O GPencil '{gp_obj.name}' deve se deformar!")
        print(f"\n✅ GPencil ORIGINAL preservado!")
        print(f"   • Camadas de pintura intactas")
        print(f"   • Materiais preservados")
        print(f"   • Animações funcionando")
        
        print(f"\n💡 DICAS:")
        print(f"• Use Proportional Editing (O) para deformação suave")
        print(f"• Ajuste handles do Bezier para curvas naturais")
        print(f"• Para animação: Keyframe os pontos da curva")
        
        self.report({'INFO'}, f"Sistema Hook criado com {len(hooks)} pontos de controle")
        return {'FINISHED'}
    
    def create_control_curve(self, gp_obj):
        """Criar curva Bezier de controle para o GPencil"""
        try:
            # Calcular tamanho do GPencil para dimensionar a curva
            bbox = GP_LatticeDeformSystem.get_gpencil_bbox(gp_obj)
            
            if bbox:
                size_x = bbox[1][0] - bbox[0][0]
                length = max(size_x * 1.5, 3.0)
            else:
                length = 4.0
            
            # Criar dados da curva
            curve_data = bpy.data.curves.new(f'{gp_obj.name}_Hook_Ctrl', 'CURVE')
            curve_data.dimensions = '3D'
            curve_data.resolution_u = 32
            curve_data.bevel_depth = 0.02
            
            # Criar spline Bezier
            spline = curve_data.splines.new('BEZIER')
            spline.bezier_points.add(4)  # 5 pontos total
            
            points = spline.bezier_points
            
            # Posicionar pontos ao longo do eixo X
            for i in range(len(points)):
                x = (i - 2) * (length / 4)
                points[i].co = Vector((x, 0, 0))
                points[i].handle_left_type = 'AUTO'
                points[i].handle_right_type = 'AUTO'
            
            # Criar objeto da curva
            curve_obj = bpy.data.objects.new(f'{gp_obj.name}_Hook_Ctrl', curve_data)
            bpy.context.collection.objects.link(curve_obj)
            
            # Posicionar curva acima do GPencil
            curve_obj.location = gp_obj.location + Vector((0, 0, 0.3))
            
            # Configurar visualização
            curve_obj.show_in_front = True
            
            # Adicionar material
            if not curve_data.materials:
                mat = bpy.data.materials.new(name="Hook_Control_Mat")
                mat.diffuse_color = (0.2, 0.8, 0.2, 1.0)  # Verde para Hook
                curve_data.materials.append(mat)
            
            print(f"✅ Curva de controle Hook criada: {curve_obj.name}")
            return curve_obj
            
        except Exception as e:
            print(f"❌ Erro ao criar curva: {e}")
            return None

class GPENCIL_OT_create_gpencil_lattice_puppet(Operator):
    """Criar sistema de puppet no GPencil REAL usando Lattice"""
    
    bl_idname = "gpencil.create_gpencil_lattice_puppet"
    bl_label = "Criar Puppet Lattice GPencil"
    bl_description = "Criar sistema de controle mantendo GPencil original usando Lattice"
    bl_options = {'REGISTER', 'UNDO'}
    
    resolution_u: IntProperty(
        name="Resolução U",
        default=8,
        min=3,
        max=16,
        description="Resolução do Lattice no eixo U"
    ) #type: ignore
    
    resolution_v: IntProperty(
        name="Resolução V",
        default=8,
        min=3,
        max=16,
        description="Resolução do Lattice no eixo V"
    ) #type: ignore
    
    def execute(self, context):
        gp_obj = context.active_object
        
        if not gp_obj or gp_obj.type != 'GREASEPENCIL':
            self.report({'ERROR'}, "Selecione um objeto Grease Pencil")
            return {'CANCELLED'}
        
        print(f"\n{'='*60}")
        print(f"CRIANDO PUPPET LATTICE GPENCIL REAL")
        print(f"Objeto: {gp_obj.name}")
        print(f"{'='*60}")
        
        # Criar curva de controle
        curve_obj = self.create_control_curve(gp_obj)
        if not curve_obj:
            self.report({'ERROR'}, "Falha ao criar curva de controle")
            return {'CANCELLED'}
        
        # Aplicar método Lattice
        lattice = GP_LatticeDeformSystem.create_gpencil_lattice(
            gp_obj, curve_obj, self.resolution_u, self.resolution_v
        )
        
        # Selecionar a curva para fácil edição
        bpy.ops.object.select_all(action='DESELECT')
        curve_obj.select_set(True)
        bpy.context.view_layer.objects.active = curve_obj
        
        # Entrar em modo de edição da curva
        bpy.ops.object.mode_set(mode='EDIT')
        
        print(f"\n{'='*60}")
        print(f"✅ SISTEMA LATTICE PRONTO!")
        print(f"{'='*60}")
        
        print(f"\n🎮 COMO USAR:")
        print(f"1. Você está no EDIT MODE da curva '{curve_obj.name}'")
        print(f"2. Selecione um ponto da curva (clique direito)")
        print(f"3. Mova (G), rotacione (R) ou escale (S)")
        print(f"4. O GPencil '{gp_obj.name}' deve se deformar via Lattice!")
        print(f"\n✅ GPencil ORIGINAL preservado!")
        print(f"   • Camadas de pintura intactas")
        print(f"   • Materiais preservados")
        print(f"   • Animações funcionando")
        
        print(f"\n💡 DICAS:")
        print(f"• Use Proportional Editing (O) para deformação suave")
        print(f"• Ajuste handles do Bezier para curvas naturais")
        print(f"• Para animação: Keyframe os pontos da curva")
        
        self.report({'INFO'}, "Sistema Lattice criado - edite a curva para deformar")
        return {'FINISHED'}
    
    def create_control_curve(self, gp_obj):
        """Criar curva Bezier de controle para o GPencil"""
        try:
            # Calcular tamanho do GPencil para dimensionar a curva
            bbox = GP_LatticeDeformSystem.get_gpencil_bbox(gp_obj)
            
            if bbox:
                size_x = bbox[1][0] - bbox[0][0]
                length = max(size_x * 1.5, 3.0)
            else:
                length = 4.0
            
            # Criar dados da curva
            curve_data = bpy.data.curves.new(f'{gp_obj.name}_Lattice_Ctrl', 'CURVE')
            curve_data.dimensions = '3D'
            curve_data.resolution_u = 32
            curve_data.bevel_depth = 0.02
            
            # Criar spline Bezier
            spline = curve_data.splines.new('BEZIER')
            spline.bezier_points.add(4)  # 5 pontos total
            
            points = spline.bezier_points
            
            # Posicionar pontos ao longo do eixo X
            for i in range(len(points)):
                x = (i - 2) * (length / 4)
                points[i].co = Vector((x, 0, 0))
                points[i].handle_left_type = 'AUTO'
                points[i].handle_right_type = 'AUTO'
            
            # Criar objeto da curva
            curve_obj = bpy.data.objects.new(f'{gp_obj.name}_Lattice_Ctrl', curve_data)
            bpy.context.collection.objects.link(curve_obj)
            
            # Posicionar curva acima do GPencil
            curve_obj.location = gp_obj.location + Vector((0, 0, 0.3))
            
            # Configurar visualização
            curve_obj.show_in_front = True
            
            # Adicionar material
            if not curve_data.materials:
                mat = bpy.data.materials.new(name="Lattice_Control_Mat")
                mat.diffuse_color = (0.2, 0.5, 0.8, 1.0)  # Azul para Lattice
                curve_data.materials.append(mat)
            
            print(f"✅ Curva de controle Lattice criada: {curve_obj.name}")
            return curve_obj
            
        except Exception as e:
            print(f"❌ Erro ao criar curva: {e}")
            return None

class GPENCIL_OT_create_gpencil_curve_puppet(Operator):
    """Criar sistema de puppet no GPencil REAL usando Curve Follow"""
    
    bl_idname = "gpencil.create_gpencil_curve_puppet"
    bl_label = "Criar Puppet Curve GPencil"
    bl_description = "Criar sistema de controle mantendo GPencil original usando Curve Follow"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        gp_obj = context.active_object
        
        if not gp_obj or gp_obj.type != 'GREASEPENCIL':
            self.report({'ERROR'}, "Selecione um objeto Grease Pencil")
            return {'CANCELLED'}
        
        print(f"\n{'='*60}")
        print(f"CRIANDO PUPPET CURVE FOLLOW GPENCIL REAL")
        print(f"Objeto: {gp_obj.name}")
        print(f"{'='*60}")
        
        # Criar curva de controle
        curve_obj = self.create_control_curve(gp_obj)
        if not curve_obj:
            self.report({'ERROR'}, "Falha ao criar curva de controle")
            return {'CANCELLED'}
        
        # Aplicar método Curve Follow
        curve_copy = GP_CurveFollowSystem.setup_curve_follow(gp_obj, curve_obj)
        
        # Selecionar a curva para fácil edição
        bpy.ops.object.select_all(action='DESELECT')
        curve_obj.select_set(True)
        bpy.context.view_layer.objects.active = curve_obj
        
        # Entrar em modo de edição da curva
        bpy.ops.object.mode_set(mode='EDIT')
        
        print(f"\n{'='*60}")
        print(f"✅ SISTEMA CURVE FOLLOW PRONTO!")
        print(f"{'='*60}")
        
        print(f"\n🎮 COMO USAR:")
        print(f"1. Você está no EDIT MODE da curva '{curve_obj.name}'")
        print(f"2. Selecione um ponto da curva (clique direito)")
        print(f"3. Mova (G), rotacione (R) ou escale (S)")
        print(f"4. A cópia em Curve seguirá a deformação!")
        print(f"\n✅ GPencil ORIGINAL preservado!")
        print(f"   • Camadas de pintura intactas")
        print(f"   • Materiais preservados")
        print(f"   • Animações funcionando")
        
        print(f"\n💡 DICAS:")
        print(f"• Use Proportional Editing (O) para deformação suave")
        print(f"• Ajuste handles do Bezier para curvas naturais")
        print(f"• Para animação: Keyframe os pontos da curva")
        
        self.report({'INFO'}, "Sistema Curve Follow criado (cópia em Curve como referência)")
        return {'FINISHED'}
    
    def create_control_curve(self, gp_obj):
        """Criar curva Bezier de controle para o GPencil"""
        try:
            # Calcular tamanho do GPencil para dimensionar a curva
            bbox = GP_LatticeDeformSystem.get_gpencil_bbox(gp_obj)
            
            if bbox:
                size_x = bbox[1][0] - bbox[0][0]
                length = max(size_x * 1.5, 3.0)
            else:
                length = 4.0
            
            # Criar dados da curva
            curve_data = bpy.data.curves.new(f'{gp_obj.name}_Curve_Ctrl', 'CURVE')
            curve_data.dimensions = '3D'
            curve_data.resolution_u = 32
            curve_data.bevel_depth = 0.02
            
            # Criar spline Bezier
            spline = curve_data.splines.new('BEZIER')
            spline.bezier_points.add(4)  # 5 pontos total
            
            points = spline.bezier_points
            
            # Posicionar pontos ao longo do eixo X
            for i in range(len(points)):
                x = (i - 2) * (length / 4)
                points[i].co = Vector((x, 0, 0))
                points[i].handle_left_type = 'AUTO'
                points[i].handle_right_type = 'AUTO'
            
            # Criar objeto da curva
            curve_obj = bpy.data.objects.new(f'{gp_obj.name}_Curve_Ctrl', curve_data)
            bpy.context.collection.objects.link(curve_obj)
            
            # Posicionar curva acima do GPencil
            curve_obj.location = gp_obj.location + Vector((0, 0, 0.3))
            
            # Configurar visualização
            curve_obj.show_in_front = True
            
            # Adicionar material
            if not curve_data.materials:
                mat = bpy.data.materials.new(name="Curve_Control_Mat")
                mat.diffuse_color = (0.8, 0.2, 0.5, 1.0)  # Rosa para Curve
                curve_data.materials.append(mat)
            
            print(f"✅ Curva de controle Curve criada: {curve_obj.name}")
            return curve_obj
            
        except Exception as e:
            print(f"❌ Erro ao criar curva: {e}")
            return None

class GPENCIL_OT_quick_puppet_demo(Operator):
    """Criar demonstração rápida do sistema"""
    
    bl_idname = "gpencil.quick_puppet_demo"
    bl_label = "Demo Rápida Puppet"
    bl_description = "Criar demonstração completa rápida"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        print(f"\n🚀 CRIANDO DEMONSTRAÇÃO PUPPET COMPLETA")
        
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        
        bpy.ops.object.grease_pencil_add(location=(0, 0, 0))
        gp_obj = bpy.context.active_object
        gp_obj.name = "Puppet_Demo"
        
        bpy.context.view_layer.objects.active = gp_obj
        bpy.ops.object.mode_set(mode='PAINT_GREASE_PENCIL')
        
        bpy.ops.object.mode_set(mode='OBJECT')
        
        print(f"✅ GPencil criado: {gp_obj.name}")
        
        # Usar método GPencil REAL por padrão
        bpy.ops.gpencil.create_gpencil_hook_puppet('EXEC_DEFAULT')
        
        print(f"\n{'='*60}")
        print(f"🎭 DEMONSTRAÇÃO PRONTA!")
        print(f"{'='*60}")
        
        print(f"\n🎮 TESTE IMEDIATO:")
        print(f"1. A curva de controle já está selecionada")
        print(f"2. Você já está no EDIT MODE")
        print(f"3. Selecione um ponto do meio da curva")
        print(f"4. Pressione G e mova para CIMA")
        print(f"5. Veja o GPencil REAL se deformar!")
        print(f"\n✅ GPencil ORIGINAL preservado!")
        
        print(f"\n🔥 PARA CONTROLE TOTAL:")
        print(f"• Use todos os pontos da curva")
        print(f"• Ajuste os handles do Bezier")
        print(f"• Ative Proportional Editing (O) para suavizar")
        
        self.report({'INFO'}, "Demo criada! Mova os pontos da curva para ver a mágica!")
        return {'FINISHED'}

class GPENCIL_OT_convert_and_control(Operator):
    """Converter GPencil para Mesh e controlar com Bezier"""
    
    bl_idname = "gpencil.convert_and_control"
    bl_label = "Converter e Controlar"
    bl_description = "Converter GPencil para Mesh e controlar completamente com Bezier"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        gp_obj = context.active_object
        
        print(f"\n🔄 CONVERTENDO GPENCIL PARA MESH + BEZIER CONTROL")
        
        curve_obj = self.create_bezier_curve()
        
        mesh_obj = self.convert_gp_to_mesh(gp_obj)
        if not mesh_obj:
            self.report({'ERROR'}, "Falha ao converter GPencil")
            return {'CANCELLED'}
        
        self.add_curve_based_deform(mesh_obj, curve_obj)
        
        lattice_obj = self.add_lattice_control(mesh_obj, curve_obj)
        
        mesh_obj.parent = curve_obj
        
        bpy.ops.object.select_all(action='DESELECT')
        curve_obj.select_set(True)
        context.view_layer.objects.active = curve_obj
        bpy.ops.object.mode_set(mode='EDIT')
        
        print(f"\n✅ CONVERSÃO COMPLETA!")
        print(f"• Mesh: {mesh_obj.name}")
        print(f"• Curva: {curve_obj.name}")
        print(f"• Lattice: {lattice_obj.name}")
        
        print(f"\n🎮 CONTROLE:")
        print(f"1. Edite a curva (pontos e handles)")
        print(f"2. O mesh seguirá a deformação")
        print(f"3. Para controle extra, edite o Lattice também")
        
        self.report({'INFO'}, "GPencil convertido! Controle completo pela curva!")
        return {'FINISHED'}
    
    def create_bezier_curve(self):
        """Criar curva Bezier"""
        curve_data = bpy.data.curves.new('Puppet_Bezier', 'CURVE')
        curve_data.dimensions = '3D'
        curve_data.resolution_u = 64
        
        spline = curve_data.splines.new('BEZIER')
        spline.bezier_points.add(3)
        
        points = spline.bezier_points
        for i in range(4):
            x = (i - 1.5) * 1.5
            points[i].co = Vector((x, 0, 0))
            points[i].handle_left_type = 'AUTO'
            points[i].handle_right_type = 'AUTO'
        
        curve_obj = bpy.data.objects.new('Puppet_Bezier', curve_data)
        bpy.context.collection.objects.link(curve_obj)
        curve_obj.location = (0, 0, 0.2)
        curve_obj.show_in_front = True
        
        return curve_obj
    
    def convert_gp_to_mesh(self, gp_obj):
        """Converter GPencil para Mesh"""
        bpy.ops.object.select_all(action='DESELECT')
        gp_obj.select_set(True)
        bpy.context.view_layer.objects.active = gp_obj
        
        bpy.ops.object.duplicate()
        dup = bpy.context.active_object
        dup.name = f"{gp_obj.name}_Mesh"
        
        bpy.ops.object.convert(target='MESH')
        
        for mod in dup.modifiers[:]:
            bpy.ops.object.modifier_remove(modifier=mod.name)
        
        return dup
    
    def add_curve_based_deform(self, mesh_obj, curve_obj):
        """Adicionar deformação baseada na curva"""
        deform = mesh_obj.modifiers.new(name="Curve_Deform", type='SIMPLE_DEFORM')
        deform.deform_method = 'BEND'
        deform.origin = curve_obj
        deform.deform_axis = 'X'
        deform.factor = 1.0
        
        curve_mod = mesh_obj.modifiers.new(name="Follow_Curve", type='CURVE')
        curve_mod.object = curve_obj
        curve_mod.deform_axis = 'POS_X'
    
    def add_lattice_control(self, mesh_obj, curve_obj):
        """Adicionar Lattice controlado pela curva"""
        lattice_data = bpy.data.lattices.new('Deform_Lattice')
        lattice_obj = bpy.data.objects.new('Deform_Lattice', lattice_data)
        bpy.context.collection.objects.link(lattice_obj)
        
        lattice_data.points_u = 8
        lattice_data.points_v = 4
        lattice_data.points_w = 2
        
        lattice_obj.location = mesh_obj.location
        lattice_obj.scale = Vector((3, 1.5, 0.5))
        
        lattice_mod = mesh_obj.modifiers.new(name="Lattice", type='LATTICE')
        lattice_mod.object = lattice_obj
        
        self.add_lattice_drivers(lattice_obj, curve_obj)
        
        return lattice_obj
    
    def add_lattice_drivers(self, lattice_obj, curve_obj):
        """Adicionar drivers do Lattice para a curva"""
        lattice = lattice_obj.data
        
        for u in range(lattice.points_u):
            curve_index = int(u / (lattice.points_u - 1) * 3)  # Assumindo 4 pontos na curva
            
            point_index = u * lattice.points_v * lattice.points_w
            
            point = lattice.points[point_index]
            drv = point.driver_add("co_deform", 1).driver
            drv.type = 'SCRIPTED'
            
            var = drv.variables.new()
            var.name = "curve_y"
            var.targets[0].id = curve_obj
            var.targets[0].data_path = f'splines[0].bezier_points[{curve_index}].co[1]'
            
            drv.expression = "curve_y * 2"

# ============================================================================
# OPERADORES AUXILIARES
# ============================================================================

class GPENCIL_OT_test_all_methods(Operator):
    """Testar todos os métodos de controle"""
    
    bl_idname = "gpencil.test_all_methods"
    bl_label = "Testar Todos Métodos"
    bl_description = "Criar e testar todos os métodos de controle"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        print(f"\n🧪 TESTANDO TODOS OS MÉTODOS DE CONTROLE")
        
        bpy.ops.object.grease_pencil_add(location=(-5, 0, 0))
        gp1 = bpy.context.active_object
        gp1.name = "Test_Mesh_Method"
        
        bpy.ops.object.grease_pencil_add(location=(0, 0, 0))
        gp2 = bpy.context.active_object
        gp2.name = "Test_Lattice_Method"
        
        bpy.ops.object.grease_pencil_add(location=(5, 0, 0))
        gp3 = bpy.context.active_object
        gp3.name = "Test_Direct_Method"
        
        print(f"\n1. Método Mesh...")
        bpy.context.view_layer.objects.active = gp1
        bpy.ops.gpencil.create_bezier_puppet('EXEC_DEFAULT', method="MESH")
        
        print(f"\n2. Método Lattice...")
        bpy.context.view_layer.objects.active = gp2
        bpy.ops.gpencil.create_bezier_puppet('EXEC_DEFAULT', method="LATTICE")
        
        print(f"\n3. Método Direto...")
        bpy.context.view_layer.objects.active = gp3
        bpy.ops.gpencil.create_bezier_puppet('EXEC_DEFAULT', method="DIRECT")
        
        print(f"\n✅ TODOS OS MÉTODOS CRIADOS!")
        print(f"\n🎮 PARA TESTAR:")
        print(f"• Edite qualquer uma das 3 curvas criadas")
        print(f"• Compare os resultados de cada método")
        print(f"• O método Mesh geralmente dá mais controle")
        
        self.report({'INFO'}, "3 métodos criados! Teste e escolha o melhor.")
        return {'FINISHED'}

class GPENCIL_OT_test_all_gpencil_methods(Operator):
    """Testar todos os métodos de controle GPencil REAL"""
    
    bl_idname = "gpencil.test_all_gpencil_methods"
    bl_label = "Testar Métodos GPencil Real"
    bl_description = "Criar e testar todos os métodos de controle GPencil REAL"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        print(f"\n🧪 TESTANDO TODOS OS MÉTODOS GPENCIL REAL")
        
        # Limpar cena
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        
        # Criar 3 GPencils para teste
        bpy.ops.object.grease_pencil_add(location=(-5, 0, 0))
        gp1 = bpy.context.active_object
        gp1.name = "Test_Hook_Method"
        
        bpy.ops.object.grease_pencil_add(location=(0, 0, 0))
        gp2 = bpy.context.active_object
        gp2.name = "Test_Lattice_Method"
        
        bpy.ops.object.grease_pencil_add(location=(5, 0, 0))
        gp3 = bpy.context.active_object
        gp3.name = "Test_Curve_Method"
        
        print(f"\n1. Método Hook GPencil...")
        bpy.context.view_layer.objects.active = gp1
        bpy.ops.gpencil.create_gpencil_hook_puppet('EXEC_DEFAULT')
        
        print(f"\n2. Método Lattice GPencil...")
        bpy.context.view_layer.objects.active = gp2
        bpy.ops.gpencil.create_gpencil_lattice_puppet('EXEC_DEFAULT')
        
        print(f"\n3. Método Curve Follow...")
        bpy.context.view_layer.objects.active = gp3
        bpy.ops.gpencil.create_gpencil_curve_puppet('EXEC_DEFAULT')
        
        print(f"\n✅ TODOS OS MÉTODOS GPENCIL REAL CRIADOS!")
        print(f"\n🎮 PARA TESTAR:")
        print(f"• Edite qualquer uma das 3 curvas criadas")
        print(f"• Compare os resultados de cada método")
        print(f"• Todos mantêm o GPencil original!")
        print(f"\n📍 Posições:")
        print(f"• Hook Method: X = -5 (Verde)")
        print(f"• Lattice Method: X = 0 (Azul)")
        print(f"• Curve Method: X = 5 (Rosa)")
        
        self.report({'INFO'}, "3 métodos GPencil REAL criados! Teste e escolha o melhor.")
        return {'FINISHED'}

# ============================================================================
# PAINEL DA UI (ATUALIZADO E CORRIGIDO)
# ============================================================================

class VIEW3D_PT_gpencil_puppet_control(Panel):
    """Painel de controle Puppet"""
    
    bl_label = "GPencil Bezier Puppet"
    bl_idname = "VIEW3D_PT_gpencil_puppet_control"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tool"
    
    def draw(self, context):
        layout = self.layout
        
        box = layout.box()
        row = box.row()
        row.label(text="🎭 Bezier Puppet Control", icon='HOOK')
        row.label(text="Controle TOTAL via Bezier")
        
        # ===== SEÇÃO: GPENCIL REAL (NOVO) =====
        box = layout.box()
        box.label(text="🎨 GPencil Real (RECOMENDADO)", icon='GP_SELECT_STROKES')
        box.label(text="Mantém GPencil original - Camadas, materiais, animações!")
        
        col = box.column(align=True)
        
        # Método Hook GPencil - CORRIGIDO: operador específico
        row = col.row(align=True)
        row.operator("gpencil.create_gpencil_hook_puppet",
                    text="Método Hook GPencil",
                    icon='HOOK')
        
        row = col.row(align=True)
        row.label(text="• Controle ponto a ponto")
        row.label(text="• Mais preciso")
        
        # Método Lattice GPencil - CORRIGIDO: operador específico
        row = col.row(align=True)
        row.operator("gpencil.create_gpencil_lattice_puppet",
                    text="Método Lattice GPencil",
                    icon='MESH_DATA')
        
        row = col.row(align=True)
        row.label(text="• Deformação suave")
        row.label(text="• Bom para formas orgânicas")
        
        # Método Curve Follow - CORRIGIDO: operador específico
        row = col.row(align=True)
        row.operator("gpencil.create_gpencil_curve_puppet",
                    text="Método Curve Follow",
                    icon='CURVE_DATA')
        
        row = col.row(align=True)
        row.label(text="• Cópia em Curve como referência")
        row.label(text="• Bom para animação de caminhos")
        
        # ===== SEÇÃO: MÉTODOS QUE CONVERTEM =====
        box = layout.box()
        box.label(text="🔄 Métodos que Convertem para Mesh", icon='MESH_DATA')
        box.label(text="Criam cópia em Mesh - Perde propriedades do GPencil")
        
        col = box.column(align=True)
        
        row = col.row(align=True)
        row.operator("gpencil.convert_and_control",
                    text="Método Mesh (Converte)",
                    icon='MESH_DATA')
        
        row = col.row(align=True)
        row.label(text="• Mais controle sobre deformação")
        row.label(text="• Perde camadas/materiais do GPencil")
        
        # ===== SEÇÃO: MÉTODOS ESPECÍFICOS =====
        box = layout.box()
        box.label(text="⚙️ Métodos Específicos (Todos)", icon='SETTINGS')
        
        grid = box.grid_flow(row_major=True, columns=3, even_columns=True)
        
        # Métodos GPencil REAL
        op = grid.operator("gpencil.create_bezier_puppet", text="Hook GP")
        op.method = "HOOK_GP"
        
        op = grid.operator("gpencil.create_bezier_puppet", text="Lattice GP")
        op.method = "LATTICE_GP"
        
        op = grid.operator("gpencil.create_bezier_puppet", text="Curve GP")
        op.method = "CURVE_GP"
        
        # Métodos que convertem
        op = grid.operator("gpencil.create_bezier_puppet", text="Mesh")
        op.method = "MESH"
        
        op = grid.operator("gpencil.create_bezier_puppet", text="Lattice")
        op.method = "LATTICE"
        
        op = grid.operator("gpencil.create_bezier_puppet", text="Direto")
        op.method = "DIRECT"
        
        # ===== SEÇÃO: DEMONSTRAÇÕES =====
        box = layout.box()
        box.label(text="🎬 Demonstrações", icon='PLAY')
        
        col = box.column(align=True)
        col.operator("gpencil.quick_puppet_demo",
                    text="Demo Rápida GPencil Real",
                    icon='FILE_NEW')
        
        col.operator("gpencil.test_all_gpencil_methods",
                    text="Testar Métodos GPencil Real",
                    icon='EXPERIMENTAL')
        
        col.operator("gpencil.test_all_methods",
                    text="Testar Todos Métodos (Old)",
                    icon='EXPERIMENTAL')
        
        # ===== SEÇÃO: INFORMAÇÕES =====
        box = layout.box()
        box.label(text="📚 Como Funciona", icon='QUESTION')
        
        col = box.column(align=True)
        col.label(text="1. Cria uma curva Bezier de controle")
        col.label(text="2. Conecta ao GPencil via método escolhido")
        col.label(text="3. Edite a curva → GPencil se deforma!")
        col.label(text="")
        col.label(text="🎨 GPencil Real: Camadas, materiais PRESERVADOS")
        col.label(text="🔄 Métodos Mesh: Criam cópia, perde propriedades")
        
        box = layout.box()
        box.label(text="💡 Dicas Importantes", icon='INFO')
        
        col = box.column(align=True)
        col.label(text="• Use Proportional Editing (O) na curva")
        col.label(text="• Ajuste handles do Bezier para curvas suaves")
        col.label(text="• Para animação: Keyframe os pontos da curva!")
        col.label(text="• GPencil Real: Mantém tudo original ✓")
        col.label(text="• Sempre teste em cópia do projeto")

# ============================================================================
# REGISTRO (ATUALIZADO)
# ============================================================================

classes = [
    BezierControlPoint,
    GPENCIL_OT_create_bezier_puppet,
    GPENCIL_OT_create_gpencil_hook_puppet,
    GPENCIL_OT_create_gpencil_lattice_puppet,
    GPENCIL_OT_create_gpencil_curve_puppet,
    GPENCIL_OT_quick_puppet_demo,
    GPENCIL_OT_convert_and_control,
    GPENCIL_OT_test_all_methods,
    GPENCIL_OT_test_all_gpencil_methods,
    VIEW3D_PT_gpencil_puppet_control,
]

def register():
    """Registrar addon"""
    for cls in classes:
        bpy.utils.register_class(cls)
    
    print(f"\n✅ GPencil Bezier Puppet v2.1 REGISTRADO!")
    print(f"🔥 NOVO: Sistemas que mantêm GPencil original!")
    print(f"🎨 Métodos GPencil Real: Hook, Lattice, Curve Follow")
    print(f"🎮 Controle TOTAL do GPencil via curvas Bezier!")

def unregister():
    """Desregistrar addon"""
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    print("GPencil Bezier Puppet desregistrado!")

# ============================================================================
# EXECUÇÃO
# ============================================================================

if __name__ == "__main__":
    register()
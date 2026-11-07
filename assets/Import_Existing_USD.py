"""Import an existing MiEx USD into Blender without changing the Minecraft save.

Uses the user's already-installed official MiExImport.py, with narrow runtime
compatibility guards. The source importer is never overwritten.
"""
import sys
import types
import re
import time
from collections import Counter
from pathlib import Path
import traceback

import bpy
from pxr import Usd, UsdGeom
from mathutils import Vector


def log(*parts):
    print(*parts, flush=True)


def stage_report(src, variant):
    Usd.Stage.SetGlobalVariantFallbacks({'MiEx_LOD': [variant]})
    stage = Usd.Stage.Open(str(src), Usd.Stage.LoadAll)
    if stage is None:
        raise RuntimeError('Unable to open the USD stage with payloads loaded.')
    stats = Counter()
    examples = Counter()
    for prim in stage.Traverse():
        if prim.IsA(UsdGeom.Mesh):
            stats['meshes'] += 1
            path_parts = str(prim.GetPath()).split('/', 3)
            group = path_parts[2] if len(path_parts) > 2 else 'other'
            examples[group] += 1
            # OpenUSD exposes the native face count directly. Avoid returning
            # potentially millions of faceVertexCounts values into Python
            # solely to call len() on them; preserve the full terrain checks.
            mesh = UsdGeom.Mesh(prim)
            face_count = mesh.GetFaceCount() if hasattr(mesh, 'GetFaceCount') else len(mesh.GetFaceVertexCountsAttr().Get() or ())
            stats['faces'] += face_count
            # Individual block prototypes are reusable source meshes, not
            # proof of actual solid terrain in the imported world.
            if group not in ('individualBlocksBaseMeshes', 'entities', 'prototypes'):
                stats['world_mesh_faces'] += face_count
                stats['world_meshes'] += 1
        elif prim.IsA(UsdGeom.PointInstancer):
            stats['instancers'] += 1
            inst = UsdGeom.PointInstancer(prim)
            # Count prototype instances in native USD without copying the
            # potentially large protoIndices array into Python.
            if hasattr(inst, 'GetInstanceCount'):
                stats['instances'] += inst.GetInstanceCount()
            else:
                indices = inst.GetProtoIndicesAttr().Get()
                if indices is not None:
                    stats['instances'] += len(indices)
    log('USD variant:', variant, 'layers:', len(stage.GetUsedLayers()))
    log('USD mesh definitions:', stats['meshes'], 'mesh faces:', stats['faces'])
    log('USD point instancers:', stats['instancers'], 'instanced positions:', stats['instances'])
    log('USD mesh path groups:', examples.most_common(15))
    log('USD solid world mesh faces outside prototypes/entities:', stats['world_mesh_faces'])
    return stats


def load_patched_importer(src):
    """Patch two known weak points in the pinned official addon, in memory only."""
    contents = src.read_text(encoding='utf-8-sig')
    # MiEx has whitespace on blank lines between getNode and
    # getNodeIfMissing. Canonicalize blank lines in memory so strictly
    # checked source substitutions match the same official implementation.
    contents = re.sub(r'(?m)^[ \t]+$', '', contents)
    # Upstream removes material nodes while iterating the same Blender
    # collection. Clear the collection atomically so no stale USD/default
    # shader or output node can survive before the Minecraft JSON graph is
    # built. This is the full reset already intended by the original code.
    original = '''        for node in self.mat.node_tree.nodes:
            self.mat.node_tree.nodes.remove(node)'''
    safe = '''        self.mat.node_tree.nodes.clear()'''
    if contents.count(original) != 1:
        raise RuntimeError('Pinned MiEx material reset changed; refusing unverified cleanup.')
    contents = contents.replace(original, safe, 1)

    # MiEx immediately replaces Blender's USD PreviewSurface node networks
    # from the Minecraft JSON materials. Import the USD material datablocks
    # and geometry bindings, but skip this redundant temporary shader build.
    usd_import = "mtl_name_collision_mode='REFERENCE_EXISTING',import_proxy="
    if contents.count(usd_import) != 1:
        raise RuntimeError('Pinned MiEx USD material import changed; refusing unverified speedup.')
    contents = contents.replace(
        usd_import,
        "mtl_name_collision_mode='REFERENCE_EXISTING',import_usd_preview=False,import_proxy=",
        1,
    )
    # Keep the same per-polygon flat-shading flags without constructing a
    # Python pointer list for every imported face. A contiguous native bool
    # view uses one byte per flag and remains a normal foreach_set sequence.
    original = '                mesh.data.polygons.foreach_set("use_smooth", [False for _ in range(len(mesh.data.polygons))])'
    faster = '                mesh.data.polygons.foreach_set("use_smooth", memoryview(bytearray(len(mesh.data.polygons))).cast("?"))'
    if contents.count(original) != 1:
        raise RuntimeError('Pinned MiEx flat-shading assignment changed; refusing unverified buffer optimization.')
    contents = contents.replace(original, faster, 1)
    log('PERF: Skipped redundant USD PreviewSurface shader conversion; MiEx Minecraft shaders still imported.')
    original = '                        node.image = bpy.data.images.load(imagePath)'
    safe = '''                        try:
                            node.image = bpy.data.images.load(imagePath, check_existing=True)
                        except Exception as image_error:
                            print('MIEX_TEXTURE_LOAD_FAILURE:', repr(imagePath), repr(image_error), flush=True)
                            if hasattr(node, 'image'):
                                fallback = bpy.data.images.get('_MiEx_Unreadable_Texture')
                                if fallback is None:
                                    fallback = bpy.data.images.new('_MiEx_Unreadable_Texture', width=1, height=1, alpha=True)
                                    fallback.pixels[:] = (1.0, 0.0, 1.0, 1.0)
                                node.image = fallback
                            continue
                        # Blender stores color space and alpha interpretation
                        # on the shared Image datablock, not on the shader node.
                        # A custom pack may reuse one file with different
                        # interpretations. Copy only for a genuine mismatch
                        # after an image is already used elsewhere, so setting
                        # up this material cannot recolor other Minecraft
                        # materials sharing the same file.
                        attrs = data['attributes']
                        space_attr = attrs.get('colorspace_settings', {})
                        space = space_attr.get('value') if isinstance(space_attr, dict) else None
                        if isinstance(space, list):
                            color_conflict = bool(space) and node.image.colorspace_settings.name not in space
                        else:
                            color_conflict = isinstance(space, str) and node.image.colorspace_settings.name != space
                        alpha_attr = attrs.get('alpha_mode', {})
                        alpha = alpha_attr.get('value') if isinstance(alpha_attr, dict) else None
                        alpha_conflict = isinstance(alpha, str) and node.image.alpha_mode != alpha
                        if node.image.users > 1 and (color_conflict or alpha_conflict):
                            node.image = node.image.copy()'''
    if contents.count(original) != 1:
        raise RuntimeError('Existing MiExImport.py does not match expected pinned importer. Nothing was modified.')
    contents = contents.replace(original, safe, 1)
    # The upstream importer stops on the first failed material even when
    # geometry was successfully imported. Preserve every material that works.
    original = '''                self.report({'ERROR'}, f"Material failed: {key}")
                return {'CANCELLED'}'''
    safe = '''                print('MIEX_MATERIAL_FAILURE:', key, repr(e), flush=True)
                self.report({'WARNING'}, f"Material failed: {key}")
                continue'''
    if contents.count(original) != 1:
        raise RuntimeError('MiEx material handler is unfamiliar. No unverified patch attempted.')
    contents = contents.replace(original, safe, 1)
    # Blender's node collection provides name lookup. Avoid a linear scan
    # for every connection in large material graphs, retaining name truncation
    # and the original missing-node error.
    original = '''    def get_Node_By_Name(self, name:str):
        if(len(name) > 63):
            name = name[:63]
        for node in self.mat.node_tree.nodes:
            if node.name == name:
                return node
        raise Exception("Node not found: " + name)'''
    faster = '''    def get_Node_By_Name(self, name:str):
        if(len(name) > 63):
            name = name[:63]
        node = self.mat.node_tree.nodes.get(name)
        if node is not None:
            return node
        raise Exception("Node not found: " + name)'''
    if contents.count(original) != 1:
        raise RuntimeError('Pinned MiEx material node lookup changed; cannot apply verified optimization.')
    contents = contents.replace(original, faster, 1)
    # Shader input socket names are usually words like "Base Color", not
    # integers. Avoid throwing ValueError for every ordinary named socket.
    # Keep the int() fallback for signed, spaced or underscored numeric names.
    original = '''    def is_number(self, inputString:str):
        try:
            int(inputString)
            return True
        except ValueError:
            return False'''
    faster = '''    def is_number(self, inputString:str):
        if inputString.isdecimal():
            return True
        if not any(char.isdecimal() for char in inputString):
            return False
        try:
            int(inputString)
            return True
        except ValueError:
            return False'''
    if contents.count(original) != 1:
        raise RuntimeError('Pinned MiEx socket index parsing changed; refusing unverified optimization.')
    contents = contents.replace(original, faster, 1)
    # Blender's node inputs collection provides direct name lookup. Avoid
    # redundant linear scans over all sockets for every attribute assigned
    # during material graph construction.
    original = '''                    elif 'value' in attrData:
                        if hasattr(node, attrName):
                            setattr(node, attrName, attrData['value'])
                        elif attrName in node.inputs:
                            node.inputs[attrName].default_value = attrData['value']
                        elif self.is_number(attrName):
                            node.inputs[int(attrName)].default_value = attrData['value']
                        else:
                            node[attrName] = attrData['value']'''
    faster = '''                    elif 'value' in attrData:
                        if hasattr(node, attrName):
                            setattr(node, attrName, attrData['value'])
                        else:
                            input_sock = node.inputs.get(attrName)
                            if input_sock is not None:
                                input_sock.default_value = attrData['value']
                            elif self.is_number(attrName):
                                node.inputs[int(attrName)].default_value = attrData['value']
                            else:
                                node[attrName] = attrData['value']'''
    if contents.count(original) != 1:
        raise RuntimeError('Pinned MiEx material input lookup changed; refusing unverified optimization.')
    contents = contents.replace(original, faster, 1)
    # The same Minecraft material is often used by thousands of exported
    # mesh pieces with the same USD displayColor. Avoid repeatedly updating
    # the Blender material when its last assigned source RGB is identical;
    # preserve the original gamma formula and changes between different tints.
    original = '''        # Filter meshes based on import type
        for mesh in meshes:        '''
    faster = '''        # Filter meshes based on import type
        last_display_colors = {}
        for mesh in meshes:        '''
    if contents.count(original) != 1:
        raise RuntimeError('Pinned MiEx imported-mesh loop changed; refusing unverified optimization.')
    contents = contents.replace(original, faster, 1)
    original = '''                    displayColorSRGB = [ pow(displayColor[0], 1.0/2.2), 
                                            pow(displayColor[1], 1.0/2.2), 
                                            pow(displayColor[2], 1.0/2.2), 1.0 ]
                    mat.diffuse_color = displayColorSRGB'''
    faster = '''                    rgb = (displayColor[0], displayColor[1], displayColor[2])
                    mat_key = mat.as_pointer()
                    if last_display_colors.get(mat_key) != rgb:
                        displayColorSRGB = [pow(rgb[0], 1.0/2.2),
                                            pow(rgb[1], 1.0/2.2),
                                            pow(rgb[2], 1.0/2.2), 1.0]
                        mat.diffuse_color = displayColorSRGB
                        last_display_colors[mat_key] = rgb'''
    if contents.count(original) != 1:
        raise RuntimeError('Pinned MiEx displayColor conversion changed; refusing unverified speedup.')
    contents = contents.replace(original, faster, 1)
    # NodeGrid's temporary Node wrapper never reads its outputs list. Keep
    # the real Blender node sockets intact and avoid an empty Python list
    # allocation for every shader-layout wrapper.
    original = '                self.outputs : list[Node] = []'
    if contents.count(original) != 1:
        raise RuntimeError('Pinned MiEx layout wrapper changed; refusing unverified allocation cleanup.')
    contents = contents.replace(original, '', 1)
    # These private, temporary wrappers have exactly four fields. Slots avoid
    # a per-node instance dictionary; real shader nodes are never changed.
    original = '''        class Node:

            def __init__(self, node: bpy.types.Node, column:int, row:int) -> None:'''
    faster = '''        class Node:
            __slots__ = ('node', 'column', 'row', 'creation_index')

            def __init__(self, node: bpy.types.Node, column:int, row:int) -> None:'''
    if contents.count(original) != 1:
        raise RuntimeError('Pinned MiEx layout wrapper fields changed; refusing unverified storage optimization.')
    contents = contents.replace(original, faster, 1)
    # Upstream's material node layout repeatedly scans the entire NodeGrid to
    # find an already-placed node, which becomes quadratic for large graphs.
    # Cache the same Blender-unique node names; preserve all rows, columns,
    # connections, and resulting node positions.
    original = '''                self.nodes : list[Node] = []
                self.minColumn = 0
                self.maxColumn = 0'''
    faster = '''                self.nodes : list[Node] = []
                self.byName = {}
                self.columnSizes = {}
                self.columnMembers = {0: []}
                self.minColumn = 0
                self.maxColumn = 0'''
    if contents.count(original) != 1:
        raise RuntimeError('MiEx layout grid constructor changed; refusing unverified patch.')
    contents = contents.replace(original, faster, 1)
    original = '''            def getNode(self, node: bpy.types.Node) -> Node:
                for node2 in self.nodes:
                    if node2.node.name == node.name:
                        return node2
                node2 = Node(node, 0, len(self.getColumn(0)))
                self.nodes.append(node2)
                return node2

            def getNodeIfMissing(self, node: bpy.types.Node) -> Node|None:
                for node2 in self.nodes:
                    if node2.node.name == node.name:
                        return None
                node2 = Node(node, 0, len(self.getColumn(0)))
                self.nodes.append(node2)
                return node2'''
    faster = '''            def getNode(self, node: bpy.types.Node) -> Node:
                node2 = self.byName.get(node.name)
                if node2 is not None:
                    return node2
                node2 = Node(node, 0, self.columnSizes.get(0, 0))
                self.nodes.append(node2)
                self.byName[node.name] = node2
                # Match the original full-grid enumeration order exactly.
                node2.creation_index = len(self.nodes) - 1
                self.columnMembers[0].append(node2)
                self.columnSizes[0] = self.columnSizes.get(0, 0) + 1
                return node2

            def getNodeIfMissing(self, node: bpy.types.Node) -> Node|None:
                if node.name in self.byName:
                    return None
                node2 = Node(node, 0, self.columnSizes.get(0, 0))
                self.nodes.append(node2)
                self.byName[node.name] = node2
                # Match the original full-grid enumeration order exactly.
                node2.creation_index = len(self.nodes) - 1
                self.columnMembers[0].append(node2)
                self.columnSizes[0] = self.columnSizes.get(0, 0) + 1
                return node2'''
    if contents.count(original) != 1:
        raise RuntimeError('MiEx layout node lookup changed; refusing unverified patch.')
    contents = contents.replace(original, faster, 1)
    original = '''            def setColumn(self, node:Node, column: int):
                if node.column >= column:
                    return
                prevColumn = node.column
                prevRow = node.row
                node.row = len(self.getColumn(column))
                node.column = column
                for node in self.nodes:
                    if node.column == prevColumn and node.row > prevRow:
                        node.row -= 1
                self.minColumn = min(self.minColumn, column)
                self.maxColumn = max(self.maxColumn, column)'''
    faster = '''            def setColumn(self, node:Node, column: int):
                if node.column >= column:
                    return
                prevColumn = node.column
                prevRow = node.row
                newRow = self.columnSizes.get(column, 0)
                self.columnSizes[prevColumn] -= 1
                self.columnSizes[column] = newRow + 1
                node.row = newRow
                node.column = column
                oldMembers = self.columnMembers[prevColumn]
                oldMembers.remove(node)
                self.columnMembers.setdefault(column, []).append(node)
                for other in oldMembers:
                    if other.row > prevRow:
                        other.row -= 1
                self.minColumn = min(self.minColumn, column)
                self.maxColumn = max(self.maxColumn, column)'''
    if contents.count(original) != 1:
        raise RuntimeError('MiEx layout column movement changed; refusing unverified patch.')
    contents = contents.replace(original, faster, 1)
    # MiEx originally walks every shader node each time it requests a
    # column. With cached per-column membership, only relevant nodes need
    # visiting. Sort by creation index to reproduce its exact list-insert
    # ordering, including nodes moved between columns.
    original = '''            def getColumn(self, column: int) -> list[Node]:
                res : list[Node] = []
                for node in self.nodes:
                    if node.column == column:
                        res.insert(node.row, node)
                return res'''
    faster = '''            def getColumn(self, column: int) -> list[Node]:
                res : list[Node] = []
                members = self.columnMembers.get(column, ())
                for node in sorted(members, key=lambda item: item.creation_index):
                    res.insert(node.row, node)
                return res'''
    if contents.count(original) != 1:
        raise RuntimeError('Pinned MiEx material grid column lookup changed; refusing unverified patch.')
    contents = contents.replace(original, faster, 1)
    # Shared upstream branches in Minecraft shader networks may reach the same
    # node many times. A visit at the same or shallower column cannot add a new
    # placement constraint: that node and its inputs were already processed at
    # an equal or greater depth. Cache that proven deepest traversal to avoid
    # revisiting whole branches without altering node positions.
    original = '''        def placeInColumns(node: bpy.types.Node, nodeGrid: NodeGrid, column: int):
            node2 = nodeGrid.getNode(node)
            nodeGrid.setColumn(node2, column)

            for i in range(len(node.inputs)): # type: ignore
                if node.inputs[i].is_linked:
                    link : bpy.types.NodeLink = node.inputs[i].links[0]
                    placeInColumns(link.from_node, nodeGrid, column + 1)'''
    faster = '''        seen_columns = {}

        def placeInColumns(node: bpy.types.Node, nodeGrid: NodeGrid, column: int):
            name = node.name
            if seen_columns.get(name, -1) >= column:
                return
            seen_columns[name] = column
            node2 = nodeGrid.getNode(node)
            nodeGrid.setColumn(node2, column)

            for i in range(len(node.inputs)): # type: ignore
                if node.inputs[i].is_linked:
                    link : bpy.types.NodeLink = node.inputs[i].links[0]
                    placeInColumns(link.from_node, nodeGrid, column + 1)'''
    if contents.count(original) != 1:
        raise RuntimeError('Pinned MiEx graph placement traversal changed; refusing unverified patch.')
    contents = contents.replace(original, faster, 1)
    module = types.ModuleType('miex_import_compat')
    module.__file__ = str(src)
    sys.modules[module.__name__] = module
    exec(compile(contents, str(src), 'exec'), module.__dict__)
    module.register()
    log('MiEx importer: loaded the existing official script with in-memory guards; original file unchanged.')


def needs_evaluated_bounds(ob):
    """Whether an object's visible extents can differ from its stored bounds."""
    try:
        if callable(getattr(ob, 'visible_get', None)) and not ob.visible_get():
            return False
    except Exception:
        pass
    try:
        if callable(getattr(ob, 'hide_get', None)) and ob.hide_get():
            return False
    except Exception:
        pass
    if getattr(ob, 'hide_viewport', False):
        return False
    if getattr(ob, 'instance_type', 'NONE') != 'NONE':
        return True
    if getattr(ob, 'type', None) == 'POINTCLOUD':
        return len(getattr(getattr(ob, 'data', None), 'points', ())) > 0
    if any(getattr(mod, 'show_viewport', True) for mod in getattr(ob, 'modifiers', ())):
        return True
    return False


def scene_report():
    # Thousands of imported mesh objects can share a MiEx chunk/prototype
    # parent. Resolve each ancestor chain once instead of walking it again
    # for every child mesh. No object state or hierarchy is modified.
    ancestor_prototype = {}

    def is_prototype(o):
        if o.name.partition('.')[0].lower() in ('prototypes', 'individualblocksbasemeshes'):
            return True
        parent = o.parent
        if parent is None:
            return False
        pending = []
        found = False
        while parent is not None:
            key = parent.as_pointer() if hasattr(parent, 'as_pointer') else id(parent)
            cached = ancestor_prototype.get(key)
            if cached is not None:
                found = cached
                break
            pending.append(key)
            if parent.name.partition('.')[0].lower() in ('prototypes', 'individualblocksbasemeshes'):
                found = True
                break
            parent = parent.parent
        for key in pending:
            ancestor_prototype[key] = found
        return found

    counts = Counter()
    mesh_count = faces = terrain_faces = verts = cloud_count = points = geonodes = 0
    evaluate_bounds = False
    # Avoid materializing and revisiting every scene object several times.
    for o in bpy.context.scene.objects:
        o_type = o.type
        counts[o_type] += 1
        evaluate_bounds = evaluate_bounds or needs_evaluated_bounds(o)
        if o_type == 'MESH':
            mesh_count += 1
            data = o.data
            mesh_faces = len(data.polygons)
            faces += mesh_faces
            verts += len(data.vertices)
            if not is_prototype(o):
                terrain_faces += mesh_faces
        elif o_type == 'POINTCLOUD':
            cloud_count += 1
            data = o.data
            points += len(data.points)
            geonodes += sum(mod.type == 'NODES' for mod in o.modifiers)

    log('BLENDER scene object types:', dict(counts))
    log('BLENDER mesh objects:', mesh_count, 'vertices:', verts, 'faces:', faces)
    log('BLENDER mesh faces outside prototype branches:', terrain_faces)
    log('BLENDER point-cloud objects:', cloud_count, 'point positions:', points)
    log('BLENDER geometry-node modifiers on point clouds:', geonodes)
    log('BLENDER placeholder missing-texture image:', '_MiEx_Unreadable_Texture' in bpy.data.images)
    return {'meshes': mesh_count, 'faces': faces, 'terrain_faces': terrain_faces, 'clouds': cloud_count, 'points': points, 'evaluate_bounds': evaluate_bounds}


def audit_imported_textures(target):
    """Report missing external source images without modifying the scene."""
    image_nodes = sum(
        node.type == 'TEX_IMAGE'
        for material in bpy.data.materials if getattr(material, 'node_tree', None) is not None
        for node in material.node_tree.nodes
    )
    missing = []
    relative = 0
    checked = 0
    for image in bpy.data.images:
        if image.source != 'FILE' or image.packed_file:
            continue
        # Blender uses // for project-relative image paths. pathlib can
        # interpret this prefix as an absolute or UNC path, so detect the
        # documented Blender prefix before using native path semantics.
        if image.filepath.startswith('//') or not Path(image.filepath).is_absolute():
            relative += 1
            continue
        path = Path(bpy.path.abspath(image.filepath))
        checked += 1
        if not path.is_file():
            missing.append(f'{image.name}: {path}')
    fallback = '_MiEx_Unreadable_Texture' in bpy.data.images
    summary = (
        f'Image texture nodes: {image_nodes}; checked external images: {checked}; '
        f'missing: {len(missing)}; relative (not checked): {relative}; '
        f'unreadable-image fallback: {fallback}'
    )
    log('TEXTURE AUDIT:', summary)
    if missing:
        for sample in missing[:25]:
            log('MISSING TEXTURE:', sample)
    if fallback:
        log('WARNING: MiEx could not load at least one texture; see MIEX_TEXTURE_LOAD_FAILURE lines.')
    audit_path = target.with_name(target.stem + '_texture_audit.txt')
    try:
        audit_path.write_text(summary + '\n' + '\n'.join(missing) + '\n', encoding='utf-8')
        log('Texture audit saved:', audit_path)
    except OSError as exc:
        log('WARNING: Could not write optional texture audit:', repr(exc))



def is_minecraft_water_material(name):
    """Only MiEx water block texture materials, never water plants or cauldrons."""
    name = name.lower()
    return name.startswith('mat_') and (
        'water_still' in name or 'water_flow' in name
    )


def apply_minecraft_water_materials():
    """Keep MiEx's water textures, but avoid noisy dithered alpha in Blender.

    MiEx's pinned importer sets every material's deprecated blend_method to
    HASHED, which shows semi-transparent water as a speckled pixel mask in
    EEVEE, especially when zoomed out. Blender 4.2+/5.x provides BLENDED
    transparency for smooth water. Preserve the existing alpha links (which
    may contain a water texture's own opacity), biome color and UV mapping.
    """
    count = 0
    for material in bpy.data.materials:
        if not is_minecraft_water_material(material.name) or getattr(material, 'node_tree', None) is None:
            continue
        # MiEx expands the JSON node key MAT into MAT_<texture>_<hash>.
        # Use the actual node type rather than the unexpanded template key.
        shaders = [node for node in material.node_tree.nodes.values()
                   if node.type == 'BSDF_PRINCIPLED']
        if len(shaders) != 1:
            continue
        shader = shaders[0]
        alpha = shader.inputs.get('Alpha')
        roughness = shader.inputs.get('Roughness')
        if alpha is None or roughness is None:
            continue
        # Do not strip original texture alpha connections: transparency already
        # works in the user's world and would be altered by forcing 0.68.
        if not alpha.is_linked:
            alpha.default_value = 0.80
        roughness.default_value = 0.24
        specular = shader.inputs.get('Specular IOR Level')
        if specular is not None:
            specular.default_value = 0.3
        if hasattr(material, 'surface_render_method'):
            material.surface_render_method = 'BLENDED'
            if hasattr(material, 'use_transparency_overlap'):
                # Large waters often consist of many touching water faces.
                # Keeping only the closest translucent surface avoids multiple
                # overlapping blue layers and helps the forward renderer.
                material.use_transparency_overlap = False
        else:
            # Blender before the surface_render_method API; not the supported
            # version, but keep the same visible result when the fallback exists.
            material.blend_method = 'BLEND'
        # Water's original texture and biome-color shader network remain intact.
        count += 1
    log('MINECRAFT-STYLE WATER:', count,
        'water texture materials using smooth blended alpha (no dithering).')
    if count == 0:
        log('WARNING: No MiEx water materials were found; water appearance was unchanged.')
    return count


def apply_minecraft_texture_preview():
    """Opt-in Blender display preset; preserve all shader and mesh datablocks.

    Standard leaves Minecraft's existing sRGB texture palette closer to its
    ungraded colors than the default film-style AgX tone mapping. Material
    Preview evaluates MiEx's texture, biome tint and alpha shader connections.
    Disabling object outlines avoids drawing thousands of chunk silhouette edges
    and black seams along adjacent chunk blocks.
    This is an editor/display preference, not a replacement shader network.
    """
    bpy.context.scene.view_settings.view_transform = 'Standard'
    changed = 0
    for screen in bpy.data.screens:
        for area in screen.areas:
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.shading.type = 'MATERIAL'
                    if hasattr(space.shading, 'show_object_outline'):
                        space.shading.show_object_outline = False
                    changed += 1
    log('MINECRAFT TEXTURE PREVIEW: Standard color transform,',
        changed, '3D views use Material Preview with textures, tints and alpha,',
        'Large worlds may take time to compile material shaders.')
    return changed


def clear_objects():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)


def import_world(src, import_type):
    log('PHASE: Importing with MiEx option:', import_type)
    t0 = time.monotonic()
    clear_objects()
    Usd.Stage.SetGlobalVariantFallbacks({'MiEx_LOD': ['proxy' if import_type == 'proxy' else 'render']})
    result = bpy.ops.mieximport.world(filepath=str(src), import_type=import_type,
                                       max_animation_frames=1, flatten=False,
                                       hide_background='show')
    log('MiEx operator result:', result, 'elapsed:', round(time.monotonic()-t0, 2), 'seconds')
    if 'FINISHED' not in result:
        raise RuntimeError('MiEx reported a cancelled import. See errors above.')
    return scene_report()


def initial_view_distance(world_span):
    """Open near the selected area's center, not a full-world overview.

    On a large 1024-block export the old 1.35x size made the default
    viewpoint more than a thousand blocks away. Blender's Home shortcut
    remains available to frame the entire scene.
    """
    return max(12.0, min(180.0, float(world_span) * 0.30))


def frame_actual_scene(evaluate_instances=True):
    """Frame real visible geometry, including Geometry Nodes instances.

    Do not unhide hidden prototype meshes; the previous repair tool did that
    and could make disconnected objects appear to float in otherwise blank space.
    """
    bounds_min = Vector((float('inf'),) * 3)
    bounds_max = Vector((float('-inf'),) * 3)
    encountered = 0
    true_instances = 0
    if evaluate_instances:
        dg = bpy.context.evaluated_depsgraph_get()
        # A prototype may appear thousands of times. Reuse its eight corners.
        instance_corners = {}
        try:
            for instance in dg.object_instances:
                ob = instance.object
                if ob.type != 'MESH':
                    continue
                if not instance.is_instance:
                    original = getattr(ob, 'original', ob)
                    try:
                        if not original.visible_get():
                            continue
                    except Exception:
                        pass
                else:
                    true_instances += 1
                if instance.is_instance:
                    key = ob.as_pointer() if hasattr(ob, 'as_pointer') else id(ob)
                    corners = instance_corners.get(key)
                    if corners is None:
                        corners = tuple(Vector(p) for p in ob.bound_box)
                        if len(instance_corners) < 4096:
                            instance_corners[key] = corners
                else:
                    corners = (Vector(p) for p in ob.bound_box)
                # The transform is constant across these eight corners.
                # Reading RNA matrix properties repeatedly creates wrappers.
                matrix_world = instance.matrix_world
                for p in corners:
                    world_p = matrix_world @ p
                    # Read each coordinate once. Strict comparisons preserve
                    # min/max's existing behavior for ties and NaN values.
                    for axis in range(3):
                        value = world_p[axis]
                        if value < bounds_min[axis]:
                            bounds_min[axis] = value
                        if value > bounds_max[axis]:
                            bounds_max[axis] = value
                del matrix_world
                encountered += 1
        except Exception as exc:
            log('WARNING: Evaluated Geometry Nodes bounds were incomplete:', repr(exc))
    else:
        log('PHASE: Using stored mesh bounds; skipping redundant scene-wide dependency graph evaluation.')
    if not encountered:
        for ob in bpy.context.scene.objects:
            if getattr(ob, 'type', None) != 'MESH':
                continue
            if getattr(ob, 'hide_viewport', False):
                continue
            try:
                if callable(getattr(ob, 'visible_get', None)) and not ob.visible_get():
                    continue
            except Exception:
                pass
            try:
                if callable(getattr(ob, 'hide_get', None)) and ob.hide_get():
                    continue
            except Exception:
                pass
            matrix_world = ob.matrix_world
            for p in ob.bound_box:
                world_p = matrix_world @ Vector(p)
                for axis in range(3):
                    value = world_p[axis]
                    if value < bounds_min[axis]:
                        bounds_min[axis] = value
                    if value > bounds_max[axis]:
                        bounds_max[axis] = value
                del value
            del matrix_world
            encountered += 1
    if not encountered:
        log('WARNING: Unable to calculate real visible mesh bounds. Press Home to frame the scene in Blender.')
        return
    center = (bounds_min + bounds_max) * 0.5
    dimensions = bounds_max - bounds_min
    size = max(dimensions)
    focus_distance = initial_view_distance(size)
    log('VISIBLE geometry bounds center:', tuple(round(x, 2) for x in center))
    log('VISIBLE geometry dimensions:', tuple(round(x, 2) for x in dimensions))
    log('Evaluated mesh elements:', encountered, 'from node/other instances:', true_instances)
    log('INITIAL VIEW: center terrain, distance:', round(focus_distance, 2), 'units; press Home for the full-area overview.')
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                space = area.spaces.active
                space.region_3d.view_location = center
                space.region_3d.view_distance = focus_distance
                space.clip_end = max(space.clip_end, 1000.0, size * 2)
    # IMPORTANT: Never set hide_viewport or hide_set False on hidden meshes here.
    return center, dimensions


def is_conservatively_opaque_terrain_material(material):
    """Keep alpha-blended and unusual Minecraft geometry out of mesh joining."""
    name = material.name.lower()
    if 'minecraft_block_' not in name:
        return False
    if any(token in name for token in (
        'water', 'glass', 'ice', 'leaves', 'leaf', 'slime', 'honey',
        'portal', 'grass', 'vine', 'plant', 'fire', 'torch', 'banner',
        'bed', 'sign', 'shulker', 'frame', 'cobweb', 'kelp', 'coral',
        'sea_pickle', 'lantern', 'chain', 'fence', 'door', 'rail',
    )):
        return False
    return any(token in name for token in (
        'stone', 'deepslate', 'dirt', 'sand', 'gravel', 'granite',
        'diorite', 'andesite', 'bricks', 'planks', 'terracotta',
        'concrete', 'basalt', 'obsidian', 'tuff', 'netherrack',
        'blackstone', 'ore', 'copper_block', 'clay', 'mud',
        'log', 'wood', 'stripped_',
    ))


def terrain_mesh_batch_key(ob, ancestor_cache=None, opaque_mat_cache=None):
    """Identify compatible static opaque terrain faces in nearby MiEx chunks.

    No entities, instancers, water, modifiers, shared mesh data, animations,
    non-default object colors, or mixed materials. Preserve UV/color layers
    and don't merge across more than a 2x2 MiEx export-chunk neighborhood.
    """
    if ob.type != 'MESH' or not ob.visible_get() or ob.hide_get():
        return None
    if ob.hide_render or ob.hide_viewport or ob.instance_type != 'NONE':
        return None
    if ob.modifiers or ob.constraints or ob.animation_data or ob.children:
        return None
    if ob.data.users != 1 or ob.data.shape_keys is not None:
        return None
    if ob.vertex_groups or len(ob.material_slots) != 1:
        return None
    if ob.material_slots[0].link != 'DATA':
        return None
    mat = ob.material_slots[0].material
    if mat is None:
        return None
    mat_key = mat.as_pointer() if hasattr(mat, 'as_pointer') else id(mat)
    if opaque_mat_cache is not None:
        is_opaque = opaque_mat_cache.get(mat_key)
        if is_opaque is None:
            is_opaque = is_conservatively_opaque_terrain_material(mat)
            opaque_mat_cache[mat_key] = is_opaque
        if not is_opaque:
            return None
    elif not is_conservatively_opaque_terrain_material(mat):
        return None
    if getattr(mat, 'surface_render_method', 'DITHERED') == 'BLENDED':
        return None
    if tuple(ob.color) != (1.0, 1.0, 1.0, 1.0):
        return None
    # Preserve per-object metadata used by Blender/USD users.
    if len(ob.keys()) or len(ob.data.keys()):
        return None
    if ob.parent is not None:
        parent = ob.parent
        pending = []
        rejected = False
        while parent is not None:
            pkey = parent.as_pointer() if hasattr(parent, 'as_pointer') else id(parent)
            if ancestor_cache is not None and pkey in ancestor_cache:
                rejected = ancestor_cache[pkey]
                break
            pending.append(pkey)
            if parent.name.partition('.')[0].lower() in (
                'entities', 'prototypes', 'individualblocksbasemeshes', 'background'
            ):
                rejected = True
                break
            if parent.animation_data or parent.constraints or parent.hide_render:
                rejected = True
                break
            parent = parent.parent
        if ancestor_cache is not None:
            for pkey in pending:
                ancestor_cache[pkey] = rejected
        if rejected:
            return None
    # MiEx's Util.makeSafeName changes a negative '-' sign to '_'.
    # Thus chunk X=-1 Z=-2 becomes mesh_chunk__1__2_<hash> in USD.
    # Recognize both that upstream-safe form and raw signed names.
    match = re.search(r'mesh_chunk_(_?-?\d+)_(_?-?\d+)(?:_|$)', ob.name, re.I)
    # Blender's USD importer names each mesh after its texture. The chunk
    # coordinates live on its region_<n>_chunk_<x>_<z> parent instead.
    parent = ob.parent
    while match is None and parent is not None:
        match = re.fullmatch(r'region_\d+_chunk_(_?-?\d+)_(_?-?\d+)(?:\.\d+)?',
                             parent.name, re.I)
        parent = parent.parent
    if match is None:
        return None

    def coordinate(text):
        return -int(text[1:]) if text.startswith('_') else int(text)

    # These coordinates are MiEx export-chunk coordinates, not block values.
    # Batch at most nearby 2x2 chunks, not the entire 1024x1024 landscape.
    area = (coordinate(match.group(1)) // 2, coordinate(match.group(2)) // 2)
    uv = tuple((layer.name, getattr(layer, 'active_render', False)) for layer in ob.data.uv_layers)
    colors = tuple((attr.name, attr.domain, attr.data_type) for attr in ob.data.color_attributes)
    attributes = tuple((attr.name, attr.domain, attr.data_type)
                       for attr in getattr(ob.data, 'attributes', ()))
    return (area, mat_key, uv, colors, attributes)


def batch_static_terrain_meshes(max_faces=75000, max_objects=8):
    """Optional bounded Blender Join: fewer draw calls, all polygons retained.

    This changes individual terrain object boundaries/editing but should not
    change the visual result. The mode never deletes terrain faces. The
    original USD remains an untouched, fully separated source.
    """
    groups = {}
    before = 0
    ancestor_cache = {}
    opaque_mat_cache = {}
    for ob in tuple(bpy.context.scene.objects):
        key = terrain_mesh_batch_key(ob, ancestor_cache, opaque_mat_cache)
        if key is None:
            continue
        face_count = len(ob.data.polygons)
        if face_count == 0 or face_count > max_faces:
            continue
        before += 1
        groups.setdefault(key, []).append(ob)

    if not any(len(g) >= 2 for g in groups.values()):
        log('MESH BATCHING: no eligible similarly-materialed nearby meshes; '
            'no viewport speedup is expected from this option.')
        return 0

    joined = 0
    combined_faces = 0
    active_obj = bpy.context.view_layer.objects.active
    active_name = active_obj.name if active_obj is not None else None
    selected_names = tuple(ob.name for ob in bpy.context.selected_objects)
    try:
        bpy.ops.object.select_all(action='DESELECT')

        def flush(batch, face_count):
            nonlocal joined, combined_faces
            if len(batch) < 2:
                return
            for ob in batch:
                ob.select_set(True)
            active = batch[0]
            bpy.context.view_layer.objects.active = active
            outcome = bpy.ops.object.join()
            if 'FINISHED' not in outcome:
                raise RuntimeError('Blender declined a selected terrain mesh join')
            if len(active.data.polygons) != face_count:
                raise RuntimeError('Terrain batching changed polygon count; refusing the Blender file')
            joined += len(batch) - 1
            combined_faces += face_count
            active.select_set(False)

        for group in groups.values():
            # Bound individual joins to avoid expensive huge meshes that hurt
            # Blender's frustum culling despite having fewer draw calls.
            batch = []
            faces = 0
            for ob in sorted(group, key=lambda obj: obj.name):
                count = len(ob.data.polygons)
                if batch and (len(batch) >= max_objects or faces + count > max_faces):
                    flush(batch, faces)
                    batch = []
                    faces = 0
                batch.append(ob)
                faces += count
            flush(batch, faces)
    finally:
        bpy.ops.object.select_all(action='DESELECT')
        # Keep names, not object pointers: Blender invalidates the original
        # object references after joining, and the imported scene can start
        # with many selected objects.
        for name in selected_names:
            ob = bpy.context.view_layer.objects.get(name)
            if ob is not None:
                ob.select_set(True)
        if active_name:
            active = bpy.context.view_layer.objects.get(active_name)
            if active is not None:
                bpy.context.view_layer.objects.active = active
    log('MESH BATCHING:', joined, 'static terrain objects merged,',
        combined_faces, 'faces preserved in bounded batches from',
        before, 'eligible objects; original USD unchanged.')
    if joined == 0:
        log('MESH BATCHING: no eligible similarly-materialed nearby meshes; '
            'no viewport speedup is expected from this option.')
    return joined


def compact_redundant_usd_normals():
    """Opt-in removal of an unused, exact copy of native split normals.

    USD imports can retain a FLOAT_VECTOR corner attribute named normals
    alongside Blender's custom_normal storage. Keep the native normals,
    every face/UV/color and the original USD; skip edited or referenced data.
    """
    from array import array

    trees = [mat.node_tree for mat in bpy.data.materials if getattr(mat, 'node_tree', None) is not None]
    trees.extend(bpy.data.node_groups)
    for tree in trees:
        for node in tree.nodes:
            if (getattr(node, 'attribute_name', '') == 'normals' or
                    getattr(node, 'string', '') == 'normals' or
                    any(getattr(socket, 'is_linked', False)
                        for socket in node.inputs if socket.type == 'STRING') or
                    any(getattr(socket, 'default_value', None) == 'normals'
                        for socket in node.inputs if socket.type == 'STRING')):
                log('MESH MEMORY: retained named normals referenced by a shader or node group.')
                return 0

    removed = 0
    released = 0
    seen = set()
    for ob in bpy.context.scene.objects:
        if ob.type != 'MESH' or ob.modifiers or ob.animation_data:
            continue
        mesh = ob.data
        key = mesh.as_pointer() if hasattr(mesh, 'as_pointer') else id(mesh)
        if key in seen or mesh.users != 1 or mesh.shape_keys is not None or mesh.animation_data:
            continue
        seen.add(key)
        attr = mesh.attributes.get('normals')
        if (not mesh.has_custom_normals or attr is None or
                attr.domain != 'CORNER' or attr.data_type != 'FLOAT_VECTOR'):
            continue
        count = len(attr.data) * 3
        source = array('f', [0.0]) * count
        native = array('f', [0.0]) * count
        attr.data.foreach_get('vector', source)
        mesh.corner_normals.foreach_get('vector', native)
        if source != native:
            del source, native
            continue
        mesh.attributes.remove(attr)
        # source equals the native normals above, so retain it for comparison
        # and rollback, then reuse the other buffer for the post-removal read.
        # This avoids a third full corner-normal array on large meshes.
        mesh.corner_normals.foreach_get('vector', native)
        if source != native:
            # A future Blender storage change must not silently change shading.
            restored = mesh.attributes.new(name='normals', type='FLOAT_VECTOR', domain='CORNER')
            restored.data.foreach_set('vector', source)
            log('MESH MEMORY: restored normals attribute after a native-normal mismatch.')
            del source, native
            continue
        removed += 1
        released += count * source.itemsize
        del source, native
    log('MESH MEMORY:', removed, 'unused duplicate normal arrays removed;',
        released, 'attribute bytes saved; native split normals, faces, UVs and colors retained.')
    return released


def remove_unused_usd_display_colors():
    """Opt-in removal of USD preview colors unused by the Minecraft shaders.

    Keep the actual Cd biome tint, UVs and normals. Named/default color
    readers, dynamic attribute names and vertex-color viewports block this
    cleanup; edited, animated and shared meshes are left alone.
    """
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type != 'VIEW_3D':
                continue
            for space in area.spaces:
                if space.type == 'VIEW_3D' and space.shading.color_type == 'VERTEX':
                    log('MESH MEMORY: retained USD displayColor for vertex-color viewport display.')
                    return 0

    trees = [mat.node_tree for mat in bpy.data.materials if getattr(mat, 'node_tree', None) is not None]
    trees.extend(bpy.data.node_groups)
    for tree in trees:
        for node in tree.nodes:
            if (node.type == 'SCRIPT' or
                    getattr(node, 'attribute_name', '') == 'displayColor' or
                    getattr(node, 'layer_name', '') == 'displayColor' or
                    (node.type == 'VERTEX_COLOR' and not node.layer_name) or
                    getattr(node, 'string', '') == 'displayColor' or
                    any(getattr(socket, 'is_linked', False)
                        for socket in node.inputs if socket.type == 'STRING') or
                    any(getattr(socket, 'default_value', None) == 'displayColor'
                        for socket in node.inputs if socket.type == 'STRING')):
                log('MESH MEMORY: retained USD displayColor referenced by a shader or node group.')
                return 0

    removed = released = 0
    for ob in bpy.context.scene.objects:
        if (ob.type != 'MESH' or ob.modifiers or ob.animation_data or
                getattr(ob, 'mode', 'OBJECT') != 'OBJECT'):
            continue
        mesh = ob.data
        if (mesh.users != 1 or mesh.shape_keys is not None or
                mesh.animation_data or mesh.library is not None):
            continue
        attr = mesh.color_attributes.get('displayColor')
        if attr is None or attr.domain != 'CORNER' or attr.data_type != 'FLOAT_COLOR':
            continue
        released += len(attr.data) * 4 * 4
        mesh.color_attributes.remove(attr)
        removed += 1
    log('MESH MEMORY:', removed, 'unused USD displayColor preview arrays removed;',
        released, 'attribute bytes saved; Minecraft Cd biome tints retained.')
    return released


def deduplicate_exact_material_slots():
    """Remove only identical material datablock slots; zero visual change.

    MiEx and Blender Join can leave multiple slots referring to the *same*
    shader datablock. Remapping their face indices to one slot reduces
    redundant material-group submissions. Different materials are untouched.
    """
    cleaned = 0
    visited = set()
    from array import array
    for ob in bpy.context.scene.objects:
        if ob.type != 'MESH' or ob.data.users != 1:
            continue
        mesh = ob.data
        # Most MiEx terrain meshes have one material. Avoid copying their
        # material collections when there is nothing to deduplicate.
        if len(mesh.materials) < 2:
            continue
        key = mesh.as_pointer() if hasattr(mesh, 'as_pointer') else id(mesh)
        if key in visited:
            continue
        visited.add(key)
        slots = list(mesh.materials)
        if any(mat is None for mat in slots):
            continue
        unique = []
        positions = {}
        remap = []
        for mat in slots:
            key = mat.as_pointer() if hasattr(mat, 'as_pointer') else id(mat)
            if key not in positions:
                positions[key] = len(unique)
                unique.append(mat)
            remap.append(positions[key])
        if len(unique) == len(slots):
            continue
        if any(slot.link != 'DATA' for slot in ob.material_slots):
            continue
        values = array('i', [0]) * len(mesh.polygons)
        mesh.polygons.foreach_get('material_index', values)
        # Blender can retain stale face indices after a material slot was
        # removed. Preserve those meshes rather than crashing or guessing
        # which material the user intended for their unassigned faces.
        stale = False
        for i, val in enumerate(values):
            if val < 0 or val >= len(remap):
                stale = True
                break
            values[i] = remap[val]
        if stale:
            continue
        mesh.materials.clear()
        for mat in unique:
            mesh.materials.append(mat)
        mesh.polygons.foreach_set('material_index', values)
        mesh.update()
        cleaned += len(slots) - len(unique)
    log('MATERIAL DRAW GROUPS:', cleaned,
        'duplicate slots referencing the exact same material datablock removed,'
        ' without changing any mesh faces or shaders.')
    return cleaned



def clear_bulk_import_selection(min_meshes=128):
    """Avoid thousands of imported-mesh selection outlines at first open.

    Selection is an editor state, not geometry or material data. USD import may
    select everything; drawing and testing thousands of orange outlines can
    burden the viewport. Small scenes retain their initial selection.
    """
    # Blender already returns a selection snapshot. Finish counting before
    # changing selection, without copying that list into a second container.
    mesh_count = sum(
        ob.type == 'MESH' and ob.visible_get() for ob in bpy.context.selected_objects
    )
    if mesh_count < min_meshes:
        return 0
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = None
    log('VIEWPORT: cleared initial selection for', mesh_count,
        'visible imported meshes to avoid bulk outline/selection overhead; '
        'all objects remain visible and selectable.')
    return mesh_count


def hide_relationship_lines():
    for screen in getattr(bpy.data, 'screens', ()):
        for area in getattr(screen, 'areas', ()):
            for space in getattr(area, 'spaces', ()):
                if getattr(space, 'type', None) == 'VIEW_3D' and hasattr(space, 'overlay'):
                    space.overlay.show_relationship_lines = False


def hide_imported_transform_markers():
    """Hide MiEx/USD plain-axis transform markers without hiding their objects.

    USD parent transforms can appear as black crosshairs inside doors, windows,
    and other geometry. Plain-axis Empties are not rendered. Zeroing only their
    display size retains parent-child transforms, object visibility, and actual
    image/display helper Empties.
    """
    count = 0
    for ob in bpy.context.scene.objects:
        if ob.type == 'EMPTY' and ob.empty_display_type == 'PLAIN_AXES' and ob.empty_display_size > 0.0001:
            # Blender clamps display size to 0.0001. Use its supported
            # minimum instead of assigning zero, which isn't representable.
            ob.empty_display_size = 0.0001
            count += 1
    if count:
        log('VIEWPORT: hidden', count, 'USD transform-axis markers; '
            'object parenting and render geometry are unchanged.')
    return count




def avoid_drawing_unused_import_empties(min_helpers=128):
    """Skip drawing USD-only transform helpers, not any imported mesh.

    The completed fresh USD import owns the scene: no user-created helpers
    have been mixed in yet. Only do this if *all* Empties are plain axes and
    there are enough of them for draw overhead to potentially matter.
    Blender's per-3D-view object-type visibility is reversible and does not
    change individual objects, parenting, modifiers, render visibility or
    materials. Keep other Empty types visible for image/rig helpers.
    """
    helpers = [ob for ob in bpy.context.scene.objects if ob.type == 'EMPTY']
    if len(helpers) < min_helpers:
        return 0
    if any(ob.empty_display_type != 'PLAIN_AXES' or len(ob.modifiers)
           for ob in helpers):
        return 0
    changed = 0
    for screen in bpy.data.screens:
        for area in screen.areas:
            for space in area.spaces:
                if space.type == 'VIEW_3D' and space.show_object_viewport_empty:
                    space.show_object_viewport_empty = False
                    changed += 1
    if changed:
        log('VIEWPORT: disabled drawing', len(helpers),
            'imported Plain Axes Empty helpers in', changed, '3D views;',
            'all mesh geometry and Empty parent transforms are retained.',
            'Restore via Object Type Visibility > Empties.')
    return changed


def avoid_drawing_chunk_outlines(min_meshes=128, mesh_count=None):
    """Skip drawing object silhouette outlines for chunked Minecraft terrain.

    When thousands of separate chunk meshes touch edge-to-edge, Blender's
    viewport outline pass evaluates silhouette edges between adjacent chunks
    every frame. This hurts viewport FPS and causes dark seams along chunk
    borders. Reversible via Viewport Shading > Outline.
    """
    if mesh_count is None:
        mesh_count = sum(1 for ob in getattr(bpy.context.scene, 'objects', ()) if getattr(ob, 'type', None) == 'MESH')
    if mesh_count < min_meshes:
        return 0
    changed = 0
    for screen in getattr(bpy.data, 'screens', ()):
        for area in getattr(screen, 'areas', ()):
            for space in getattr(area, 'spaces', ()):
                if (getattr(space, 'type', None) == 'VIEW_3D'
                        and hasattr(space, 'shading')
                        and getattr(space.shading, 'show_object_outline', False)):
                    space.shading.show_object_outline = False
                    changed += 1
    if changed:
        log('VIEWPORT: disabled object outlines for', mesh_count,
            'chunk meshes in', changed, '3D views to improve FPS and remove chunk seams.',
            'Restore via Viewport Shading > Outline.')
    return changed


def avoid_evaluating_empty_pointclouds():
    """Skip per-frame Geometry Node modifier evaluation on empty point clouds.

    MiEx creates an animated_blocks point cloud for every chunk with an attached
    GeometryNodes modifier. Chunks with no animated blocks have 0 points and no
    children; hiding them in the viewport avoids evaluating useless modifier graphs
    every frame without affecting renders or any visible geometry.
    """
    count = 0
    for ob in getattr(bpy.context.scene, 'objects', ()):
        if (getattr(ob, 'type', None) == 'POINTCLOUD'
                and getattr(ob, 'data', None) is not None
                and hasattr(ob.data, 'points')
                and len(ob.data.points) == 0
                and len(getattr(ob, 'modifiers', ())) > 0
                and len(getattr(ob, 'children', ())) == 0):
            if not getattr(ob, 'hide_viewport', False):
                ob.hide_viewport = True
                count += 1
            for mod in getattr(ob, 'modifiers', ()):
                if getattr(mod, 'show_viewport', True):
                    try:
                        setattr(mod, 'show_viewport', False)
                    except Exception:
                        pass
    if count:
        log('VIEWPORT: skipped modifier evaluation for', count,
            'empty point-cloud objects with 0 points; geometry and renders unchanged.')
    return count


def optimize_existing_blend(target, batch_meshes=False, minecraft_view=False):
    """Optimize the Blender project already loaded by the EXE, saving a copy."""
    source = Path(bpy.data.filepath).resolve() if bpy.data.filepath else None
    if source is None or not source.is_file():
        raise RuntimeError('Open an existing .blend in Blender before optimizing.')
    if source == target or target.exists():
        raise RuntimeError('Optimization must save to a new .blend, never overwrite the original.')
    if not target.parent.is_dir():
        raise RuntimeError('The target Blender project folder does not exist.')

    meshes = tuple(ob for ob in bpy.context.scene.objects if ob.type == 'MESH')
    before_faces = sum(len(ob.data.polygons) for ob in meshes)
    if before_faces == 0:
        raise RuntimeError('This .blend has no terrain mesh faces to optimize.')

    log('OPTIMIZING EXISTING BLENDER FILE:', source)
    log('BLENDER VERSION:', bpy.app.version_string)
    log('BEFORE: mesh objects:', len(meshes), 'faces:', before_faces)
    phase_start = time.monotonic()
    cleared = clear_bulk_import_selection()
    # Large saved projects can still draw thousands of parent-child lines.
    # Like a fresh MiEx import, hide only this editor overlay; geometry,
    # material datablocks and parent relationships remain unchanged.
    if len(meshes) >= 128:
        hide_relationship_lines()
        avoid_drawing_chunk_outlines()
    hide_imported_transform_markers()
    avoid_evaluating_empty_pointclouds()
    if batch_meshes:
        compact_redundant_usd_normals()
        remove_unused_usd_display_colors()
    joined = batch_static_terrain_meshes() if batch_meshes else 0
    slots = deduplicate_exact_material_slots()
    if minecraft_view:
        apply_minecraft_texture_preview()
    after_meshes = tuple(ob for ob in bpy.context.scene.objects if ob.type == 'MESH')
    after_faces = sum(len(ob.data.polygons) for ob in after_meshes)
    if before_faces != after_faces:
        raise RuntimeError('Mesh faces changed during optimization; refusing to save.')
    log('AFTER: mesh objects:', len(after_meshes), 'faces:', after_faces)
    log('OPTIMIZED: selected outlines cleared:', cleared,
        'joined objects:', joined, 'duplicate material slots:', slots)
    log('[PERF] Existing project optimization:', round(time.monotonic() - phase_start, 2), 'seconds')

    # Preserve compressed vs uncompressed projects. Blender 3+ writes Zstd;
    # older Blender versions used gzip for compressed .blend files.
    with source.open('rb') as handle:
        signature = handle.read(4)
    compressed_source = (signature == bytes((0x28, 0xb5, 0x2f, 0xfd))
                         or signature[:2] == bytes((0x1f, 0x8b)))
    phase_start = time.monotonic()
    bpy.ops.wm.save_as_mainfile(filepath=str(target), compress=compressed_source)
    log('[PERF] Saving optimized Blender copy:', round(time.monotonic() - phase_start, 2), 'seconds')
    if not target.is_file() or target.stat().st_size == 0:
        raise RuntimeError('Blender did not save the optimized project.')
    log('OUTPUT .blend saved:', target)
    log('RESULT: EXISTING BLENDER PROJECT OPTIMIZED. Original file unchanged.')


def main():
    arguments = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    if not arguments or any(h in arguments for h in ('-h', '--help')):
        log('Usage: blender --background --python Import_Existing_USD.py -- <source.usd> <MiExImport.py> <output.blend> [--minecraft-water] [--batch-static-meshes] [--minecraft-view]')
        log('   or: blender --background --python Import_Existing_USD.py -- <target.blend> --optimize-blend [--batch-static-meshes] [--minecraft-view]')
        return
    if '--optimize-blend' in arguments:
        flags = arguments[1:]
        allowed = {'--optimize-blend', '--batch-static-meshes', '--minecraft-view'}
        if (len(arguments) < 2 or len(flags) != len(set(flags))
                or '--optimize-blend' not in flags or not set(flags) <= allowed):
            raise RuntimeError('Expected target .blend --optimize-blend [--batch-static-meshes] [--minecraft-view]')
        if Path(arguments[0]).suffix.lower() != '.blend':
            raise RuntimeError('Optimization output must be a .blend file.')
        optimize_existing_blend(Path(arguments[0]).resolve(),
                                batch_meshes='--batch-static-meshes' in flags,
                                minecraft_view='--minecraft-view' in flags)
        return
    flags = arguments[3:]
    accepted = {'--minecraft-water', '--batch-static-meshes', '--minecraft-view'}
    if len(arguments) < 3 or len(flags) != len(set(flags)) or not set(flags) <= accepted:
        raise RuntimeError('Expected: source USD, MiExImport.py, output blend file [--minecraft-water] [--batch-static-meshes] [--minecraft-view]')
    minecraft_water = '--minecraft-water' in flags
    batch_meshes = '--batch-static-meshes' in flags
    minecraft_view = '--minecraft-view' in flags
    src, importer, target = [Path(arg).resolve() for arg in arguments[:3]]
    log('BLENDER VERSION:', bpy.app.version_string)
    log('Input USD:', src)
    log('Existing importer:', importer)
    log('Target:', target)
    if not src.is_file() or not importer.is_file():
        raise RuntimeError('Main USD or existing MiExImport.py not found.')
    # Prefer render terrain; check proxy only when the render variant is empty.
    phase_start = time.monotonic()
    render = stage_report(src, 'render')
    if render['world_mesh_faces']:
        import_variant, stats = 'render', render
    else:
        # Only load the proxy variant when render contains no usable terrain.
        # An empty render stage must not prevent fallback to valid proxy meshes.
        import_variant, stats = 'proxy', stage_report(src, 'proxy')
    if stats['world_mesh_faces'] == 0:
        raise RuntimeError(
            'The USD has NO solid chunk terrain meshes in either render or proxy mode. '
            'The stage may be empty or contain only block prototypes, instances, or entities. '
            'An importer cannot recreate terrain surfaces missing from the export. '
            'Export a small region near the actual build coordinates with the revised '
            'face-only exporter (raytracing, subsets and individual-block instancing off). '
            'The original Minecraft ZIP and USD have not been changed.'
        )
    log('[PERF] USD integrity inspection:', round(time.monotonic() - phase_start, 2), 'seconds')
    log('Selected MiEx import variant:', import_variant)
    load_patched_importer(importer)
    scene = import_world(src, import_variant)
    if minecraft_water:
        apply_minecraft_water_materials()
    if stats['instancers'] and scene['clouds'] == 0 and scene['faces'] < 1000:
        raise RuntimeError('Point-instanced USD objects did not import as Blender geometry. No .blend saved.')
    if not scene['meshes'] and not scene['points']:
        raise RuntimeError('USD contained geometry but Blender did not import usable geometry. No .blend saved.')
    if stats['instances'] and scene['points'] == 0 and scene['faces'] < 1000:
        raise RuntimeError('USD included instanced positions but Blender produced no point-cloud points or significant meshes.')
    # A large source terrain must yield actual meshes, not only POINTCLOUD
    # positions. Point clouds alone were what the broken output displayed.
    if scene['terrain_faces'] < stats['world_mesh_faces'] * 0.5:
        raise RuntimeError('Blender imported less than half of the terrain faces represented in the USD. No misleading success file saved.')
    avoid_evaluating_empty_pointclouds()
    phase_start = time.monotonic()
    bounds = frame_actual_scene(scene['evaluate_bounds'])
    log('[PERF] Scene framing:', round(time.monotonic() - phase_start, 2), 'seconds')
    hide_relationship_lines()
    hide_imported_transform_markers()
    avoid_drawing_unused_import_empties()
    avoid_drawing_chunk_outlines(mesh_count=scene['meshes'])
    clear_bulk_import_selection()
    if batch_meshes:
        phase_start = time.monotonic()
        compact_redundant_usd_normals()
        remove_unused_usd_display_colors()
        batch_static_terrain_meshes()
        log('[PERF] Bounded static terrain mesh batching:',
            round(time.monotonic() - phase_start, 2), 'seconds')
    if minecraft_view:
        apply_minecraft_texture_preview()
    # Unlike mesh batching, removing repeated slots for the SAME shader
    # datablock changes no actual rendering or geometry and is safe as default.
    deduplicate_exact_material_slots()
    if scene['meshes'] > 1000:
        log('VIEWPORT NOTICE:', scene['meshes'],
            'mesh objects may limit FPS in large scenes. Optional batching'
            ' reduces draw calls only when nearby meshes use compatible materials.')
    try:
        audit_imported_textures(target)
    except Exception as exc:
        log('WARNING: Optional texture audit failed; continuing with the intact Blender scene:', repr(exc))
    phase_start = time.monotonic()
    bpy.ops.wm.save_as_mainfile(filepath=str(target), compress=False)
    log('[PERF] Saving Blender project:', round(time.monotonic() - phase_start, 2), 'seconds')
    if not target.is_file() or target.stat().st_size == 0:
        raise RuntimeError('Blender did not create the output file.')
    log('OUTPUT .blend saved:', target)
    log('OUTPUT bytes:', target.stat().st_size)
    log('IMPORTANT: Check MIEX_TEXTURE_LOAD_FAILURE and MIEX_MATERIAL_FAILURE warnings above.')
    log('RESULT: IMPORT COMPLETED AND BLENDER PROJECT SAVED. Real terrain faces verified; visual fidelity still needs checking.')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(2)

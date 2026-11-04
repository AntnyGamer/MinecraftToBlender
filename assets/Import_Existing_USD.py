"""Import an existing MiEx USD into Blender without changing the Minecraft save.

Uses the user's already-installed official MiExImport.py, with narrow runtime
compatibility guards. The source importer is never overwritten.
"""
import sys
import types
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
            faces = UsdGeom.Mesh(prim).GetFaceVertexCountsAttr().Get()
            if faces is not None:
                face_count = len(faces)
                stats['faces'] += face_count
                # Individual block prototypes are reusable source meshes, not
                # proof of actual solid terrain in the imported world.
                if group not in ('individualBlocksBaseMeshes', 'entities', 'prototypes'):
                    stats['world_mesh_faces'] += face_count
                    stats['world_meshes'] += 1
        elif prim.IsA(UsdGeom.PointInstancer):
            stats['instancers'] += 1
            inst = UsdGeom.PointInstancer(prim)
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
                            continue'''
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
    module = types.ModuleType('miex_import_compat')
    module.__file__ = str(src)
    sys.modules[module.__name__] = module
    exec(compile(contents, str(src), 'exec'), module.__dict__)
    module.register()
    log('MiEx importer: loaded the existing official script with in-memory guards; original file unchanged.')


def scene_report():
    def is_prototype(o):
        while o:
            name = o.name.partition('.')[0].lower()
            if name in ('prototypes', 'individualblocksbasemeshes'):
                return True
            o = o.parent
        return False

    counts = Counter()
    mesh_count = faces = terrain_faces = verts = cloud_count = points = geonodes = 0
    # Avoid materializing and revisiting every scene object several times.
    for o in bpy.context.scene.objects:
        counts[o.type] += 1
        if o.type == 'MESH':
            mesh_count += 1
            mesh_faces = len(o.data.polygons)
            faces += mesh_faces
            verts += len(o.data.vertices)
            if not is_prototype(o):
                terrain_faces += mesh_faces
        elif o.type == 'POINTCLOUD':
            cloud_count += 1
            points += len(o.data.points)
            geonodes += sum(mod.type == 'NODES' for mod in o.modifiers)

    log('BLENDER scene object types:', dict(counts))
    log('BLENDER mesh objects:', mesh_count, 'vertices:', verts, 'faces:', faces)
    log('BLENDER mesh faces outside prototype branches:', terrain_faces)
    log('BLENDER point-cloud objects:', cloud_count, 'point positions:', points)
    log('BLENDER geometry-node modifiers on point clouds:', geonodes)
    log('BLENDER placeholder missing-texture image:', '_MiEx_Unreadable_Texture' in bpy.data.images)
    return {'meshes': mesh_count, 'faces': faces, 'terrain_faces': terrain_faces, 'clouds': cloud_count, 'points': points}


def audit_imported_textures(target):
    """Report missing external source images without modifying the scene."""
    image_nodes = sum(
        node.type == 'TEX_IMAGE'
        for material in bpy.data.materials if material.use_nodes
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


def frame_actual_scene():
    """Frame real visible geometry, including Geometry Nodes instances.

    Do not unhide hidden prototype meshes; the previous repair tool did that
    and could make disconnected objects appear to float in otherwise blank space.
    """
    dg = bpy.context.evaluated_depsgraph_get()
    bounds_min = Vector((float('inf'),) * 3)
    bounds_max = Vector((float('-inf'),) * 3)
    encountered = 0
    true_instances = 0
    # A prototype may appear thousands of times. Its local bounding box is
    # unchanged between instances, so reuse its eight corner vectors.
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
                key = ob.as_pointer()
                corners = instance_corners.get(key)
                if corners is None:
                    corners = tuple(Vector(p) for p in ob.bound_box)
                    if len(instance_corners) < 512:
                        instance_corners[key] = corners
            else:
                corners = (Vector(p) for p in ob.bound_box)
            for p in corners:
                world_p = instance.matrix_world @ p
                for axis in range(3):
                    bounds_min[axis] = min(bounds_min[axis], world_p[axis])
                    bounds_max[axis] = max(bounds_max[axis], world_p[axis])
            encountered += 1
    except Exception as exc:
        log('WARNING: Evaluated Geometry Nodes bounds were incomplete:', repr(exc))
    if not encountered:
        for ob in bpy.context.scene.objects:
            if ob.type != 'MESH' or not ob.visible_get():
                continue
            for p in ob.bound_box:
                world_p = ob.matrix_world @ Vector(p)
                for axis in range(3):
                    bounds_min[axis] = min(bounds_min[axis], world_p[axis])
                    bounds_max[axis] = max(bounds_max[axis], world_p[axis])
            encountered += 1
    if not encountered:
        log('WARNING: Unable to calculate real visible mesh bounds. Press Home to frame the scene in Blender.')
        return
    center = (bounds_min + bounds_max) * 0.5
    dimensions = bounds_max - bounds_min
    size = max(dimensions)
    log('VISIBLE geometry bounds center:', tuple(round(x, 2) for x in center))
    log('VISIBLE geometry dimensions:', tuple(round(x, 2) for x in dimensions))
    log('Evaluated mesh elements:', encountered, 'from node/other instances:', true_instances)
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                space = area.spaces.active
                space.region_3d.view_location = center
                space.region_3d.view_distance = max(10.0, size * 1.35)
                space.clip_end = max(space.clip_end, 1000.0, size * 5)
    # IMPORTANT: Never set hide_viewport or hide_set False on hidden meshes here.


def hide_relationship_lines():
    for screen in bpy.data.screens:
        for area in screen.areas:
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.overlay.show_relationship_lines = False


def main():
    arguments = sys.argv[sys.argv.index('--') + 1:]
    if len(arguments) != 3:
        raise RuntimeError('Expected: source USD, MiExImport.py, output blend file')
    src, importer, target = [Path(arg).resolve() for arg in arguments]
    log('BLENDER VERSION:', bpy.app.version_string)
    log('Input USD:', src)
    log('Existing importer:', importer)
    log('Target:', target)
    if not src.is_file() or not importer.is_file():
        raise RuntimeError('Main USD or existing MiExImport.py not found.')
    # Prefer render terrain; check proxy only when the render variant is empty.
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
            'compatibility-first exporter (no face merging or point instancing). '
            'The original Minecraft ZIP and USD have not been changed.'
        )
    log('Selected MiEx import variant:', import_variant)
    load_patched_importer(importer)
    scene = import_world(src, import_variant)
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
    frame_actual_scene()
    hide_relationship_lines()
    try:
        audit_imported_textures(target)
    except Exception as exc:
        log('WARNING: Optional texture audit failed; continuing with the intact Blender scene:', repr(exc))
    bpy.ops.wm.save_as_mainfile(filepath=str(target), compress=False)
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

"""Exercise Blender geometry reporting/framing without requiring Blender in CI."""
import ast
import re
from collections import Counter
from pathlib import Path
from types import SimpleNamespace as NS


class SceneObjects:
    def __init__(self, objects):
        self.objects = objects
        self.iterations = 0

    def __iter__(self):
        self.iterations += 1
        if self.iterations != 1:
            raise AssertionError("scene reporting must traverse objects only once")
        return iter(self.objects)


class Vec:
    def __init__(self, values):
        self.values = list(values)

    def __getitem__(self, n):
        return self.values[n]

    def __setitem__(self, n, value):
        self.values[n] = value

    def __add__(self, other):
        return Vec(a + b for a, b in zip(self.values, other.values))

    def __sub__(self, other):
        return Vec(a - b for a, b in zip(self.values, other.values))

    def __mul__(self, scalar):
        return Vec(x * scalar for x in self.values)


class Matrix:
    def __init__(self, translation=(0, 0, 0)):
        self.translation = translation

    def __matmul__(self, vec):
        return Vec(a + b for a, b in zip(vec.values, self.translation))


class Mesh:
    type = "MESH"

    def __init__(self, name, polys, verts, parent=None, bbox=None):
        self.name = name
        self.data = NS(polygons=range(polys), vertices=range(verts))
        self.parent = parent
        self.modifiers = []
        self.original = self
        self._bbox = bbox or list(
            (x, y, z) for x in (0, 1) for y in (0, 1) for z in (0, 1)
        )
        self.bbox_reads = 0
        self.matrix_reads = 0
        self._matrix_world = Matrix()

    @property
    def matrix_world(self):
        self.matrix_reads += 1
        return self._matrix_world

    @matrix_world.setter
    def matrix_world(self, matrix):
        self._matrix_world = matrix

    @property
    def bound_box(self):
        self.bbox_reads += 1
        return self._bbox

    def visible_get(self):
        return True

    def as_pointer(self):
        return id(self)


def imported_functions(bpy, messages):
    module = ast.parse(Path("assets/Import_Existing_USD.py").read_text(encoding="utf-8"))
    functions = [node for node in module.body if isinstance(node, ast.FunctionDef)
                 and node.name in ("scene_report", "frame_actual_scene", "stage_report", "needs_evaluated_bounds", "initial_view_distance")]
    assert len(functions) == 5
    namespace = {
        "Counter": Counter, "Vector": Vec, "bpy": bpy,
        "log": lambda *args: messages.append(args),
        "float": float, "min": min, "max": max,
    }
    exec(compile(ast.Module(body=functions, type_ignores=[]), "Blender-import-functions", "exec"), namespace)
    return namespace


def test_scene_report():
    ancestor = NS(name="prototypes", parent=None, as_pointer=lambda: 111)
    solid = Mesh("terrain", 10, 23)
    prototype = Mesh("tree", 4, 8, ancestor)
    cloud = NS(type="POINTCLOUD", name="cloud", data=NS(points=range(17)),
               modifiers=[NS(type="NODES"), NS(type="SUBSURF"), NS(type="NODES")])
    scene_objects = SceneObjects([solid, prototype, cloud, NS(type="CAMERA")])
    messages = []
    bpy = NS(context=NS(scene=NS(objects=scene_objects)), data=NS(images={}))
    report = imported_functions(bpy, messages)["scene_report"]()
    assert report == {"meshes": 2, "faces": 14, "terrain_faces": 10, "clouds": 1, "points": 17, "evaluate_bounds": True}
    assert scene_objects.iterations == 1
    assert any("BLENDER geometry-node modifiers on point clouds:" in x and 2 in x
               for x in messages)


def test_shared_prototype_ancestry_is_cached():
    class Parent:
        def __init__(self, name, parent=None):
            self._name, self._parent = name, parent
            self.name_reads = 0

        @property
        def name(self):
            self.name_reads += 1
            return self._name

        @property
        def parent(self):
            return self._parent

        def as_pointer(self):
            return id(self)

    root = Parent("Minecraft_World")
    region = Parent("region_1_chunk_0_0", root)
    prototypes = Parent("prototypes", root)
    terrain = [Mesh(f"stone_{i}", 11, 22, region) for i in range(100)]
    samples = [Mesh(f"prototype_{i}", 3, 8, prototypes) for i in range(80)]
    scene = NS(context=NS(scene=NS(objects=SceneObjects(terrain+samples))),
               data=NS(images={}))
    result = imported_functions(scene, [])["scene_report"]()
    assert result["meshes"] == 180
    assert result["terrain_faces"] == 1100
    assert result["faces"] == 1340
    assert region.name_reads == 1
    assert root.name_reads == 1
    assert prototypes.name_reads == 1
    # The cache is only per-report: no persistent Blender or mesh state changes.


def test_repeated_instance_bounds():
    class Instance:
        def __init__(self, ob, is_instance, matrix):
            self.object = ob
            self.is_instance = is_instance
            self.matrix = matrix
            self.matrix_reads = 0

        @property
        def matrix_world(self):
            self.matrix_reads += 1
            return self.matrix

    proto = Mesh("prototype", 8, 8)
    local = Mesh("local", 8, 8, bbox=list((x, y, z)
                                        for x in (-2, -1) for y in (-2, -1) for z in (-2, -1)))
    instances = [
        Instance(proto, True, Matrix()),
        Instance(proto, True, Matrix((16, 0, 0))),
        Instance(local, False, Matrix()),
    ]
    space = NS(region_3d=NS(view_location=None, view_distance=None), clip_end=10)
    bpy = NS(context=NS(evaluated_depsgraph_get=lambda: NS(object_instances=instances),
                        scene=NS(objects=[proto, local])),
             data=NS(screens=[NS(areas=[NS(type="VIEW_3D", spaces=NS(active=space))])]))
    messages = []
    imported_functions(bpy, messages)["frame_actual_scene"]()
    assert proto.bbox_reads == 1, "Repeated instances should reuse the same eight bounds"
    assert all(instance.matrix_reads == 1 for instance in instances), (
        "Read each instance's own transform once, even for a shared prototype")
    center = space.region_3d.view_location.values
    assert center == [7.5, -0.5, -0.5], center
    assert abs(space.region_3d.view_distance - 12.0) < 0.00001
    assert space.clip_end == 1000
    assert any("Evaluated mesh elements:" in x and 3 in x and 2 in x for x in messages)


def test_initial_view_starts_close_to_large_terrain():
    initial_distance = imported_functions(NS(), [])["initial_view_distance"]
    assert initial_distance(1) == 12.0
    assert abs(initial_distance(256) - 76.8) < 0.001
    assert initial_distance(1024) == 180.0
    assert initial_distance(8192) == 180.0
    # A 1024-block export used to open 1382.4 units away.
    assert initial_distance(1024) < 1024 * 0.2


def test_static_scene_avoids_depsgraph():
    mesh = Mesh("static", 12, 24)
    mesh.matrix_world = Matrix((100, 2, 3))
    area = NS(type="VIEW_3D", spaces=NS(active=NS(
        region_3d=NS(view_location=None, view_distance=None), clip_end=100)))
    bpy = NS(context=NS(
        evaluated_depsgraph_get=lambda: (_ for _ in ()).throw(
            AssertionError("Static scene must not evaluate the dependency graph")),
        scene=NS(objects=[mesh])),
        data=NS(screens=[NS(areas=[area])]))
    msgs = []
    functions = imported_functions(bpy, msgs)
    functions["frame_actual_scene"](evaluate_instances=False)
    center = area.spaces.active.region_3d.view_location.values
    assert center == [100.5, 2.5, 3.5], center
    assert mesh.matrix_reads == 1, "Read a stored mesh transform once for all eight corners"
    assert any("skipping redundant scene-wide dependency graph" in " ".join(map(str, msg))
               for msg in msgs)


def test_usd_stage_mesh_grouping():
    class FakePrim:
        def __init__(self, name, kind, count):
            self.name, self.kind, self.count = name, kind, count

        def IsA(self, cls):
            return self.kind == cls.__name__

        def GetPath(self):
            return self.name

    class Mesh:
        def __init__(self, prim):
            self.prim = prim

        def GetFaceCount(self):
            return self.prim.count

        def GetFaceVertexCountsAttr(self):
            raise AssertionError("Do not fetch huge mesh count arrays into Python")

    class PointInstancer:
        def __init__(self, prim):
            self.prim = prim

        def GetInstanceCount(self):
            return self.prim.count

        def GetProtoIndicesAttr(self):
            raise AssertionError("Do not fetch a large instance-index array to count positions")

    prims = [
        FakePrim("/Root/individualBlocksBaseMeshes/very/deep/prototype", "Mesh", 10),
        FakePrim("/Root/entities/frame", "Mesh", 3),
        FakePrim("/Root/chunks/region_1/terrain/mesh", "Mesh", 7),
        FakePrim("/Root/prototypes/leaf", "Mesh", 2),
        FakePrim("/Root/chunks/region_2/terrain/mesh", "Mesh", 4),
        FakePrim("/Root/chunks/instances", "PointInstancer", 3),
    ]
    variants = []
    stage = NS(Traverse=lambda: iter(prims), GetUsedLayers=lambda: [1, 2])
    api = NS(Stage=NS(
        LoadAll=1,
        SetGlobalVariantFallbacks=lambda value: variants.append(value),
        Open=lambda _source, _mode: stage,
    ))
    messages = []
    functions = imported_functions(NS(), messages)
    functions["Usd"] = api
    functions["UsdGeom"] = NS(Mesh=Mesh, PointInstancer=PointInstancer)
    report = functions["stage_report"]("World.usd", "render")
    assert report["meshes"] == 5
    assert report["faces"] == 26
    assert report["world_mesh_faces"] == 11
    assert report["world_meshes"] == 2
    assert report["instancers"] == 1 and report["instances"] == 3
    assert variants == [{"MiEx_LOD": ["render"]}]


def test_bounds_extrema_and_nonfinite_coordinates():
    # Transformed, mirrored and imperfect bounds retain the previous min/max
    # semantics in both the evaluated-instance and stored-bounds paths.
    from math import isnan

    class Transform:
        def __matmul__(self, value):
            x, y, z = value.values
            return Vec((2*x-y, -3*y+z, -x+4*z))

    mesh = Mesh('transformed', 8, 8, bbox=[
        (-4.5, 2.0, -0.0), (3.0, -7.5, 10.0),
        (0.0, 0.0, 0.0), (float('nan'), 1.0, 2.0),
    ])
    matrix = Transform()
    mesh.matrix_world = matrix
    points = [matrix @ Vec(p) for p in mesh._bbox]
    lo = [min([float('inf')] + [p[i] for p in points if not isnan(p[i])]) for i in range(3)]
    hi = [max([float('-inf')] + [p[i] for p in points if not isnan(p[i])]) for i in range(3)]
    expected = ([.5*(a+b) for a,b in zip(lo,hi)], [b-a for a,b in zip(lo,hi)])
    for evaluated in (False, True):
        instance = NS(object=mesh, is_instance=False, matrix_world=matrix)
        bpy = NS(context=NS(scene=NS(objects=[mesh]),
                           evaluated_depsgraph_get=lambda: NS(object_instances=[instance])),
                 data=NS(screens=[]))
        actual = imported_functions(bpy, [])['frame_actual_scene'](evaluate_instances=evaluated)
        assert tuple(v.values for v in actual) == expected, (evaluated, actual, expected)


def test_chunk_name_patterns_preserve_matching():
    source = Path("assets/Import_Existing_USD.py").read_text(encoding="utf-8")
    module = ast.parse(source)
    names = {"CHUNK_MESH_PATTERN", "CHUNK_PARENT_PATTERN"}
    assignments = [node for node in module.body
                   if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id in names
                           for target in node.targets)]
    assert len(assignments) == 2
    scope = {"re": re}
    exec(compile(ast.Module(body=assignments, type_ignores=[]), "<chunk-patterns>", "exec"), scope)
    cases = (
        "mesh_chunk__1__2_stone", "mesh_chunk_10_20", "MESH_CHUNK_-2_5_x",
        "mesh_chunk_1_2_material", "mesh_chunk_empty", "stone",
        "region_1_chunk__32__1", "REGION_23_CHUNK_11_24.003",
        "region_1_chunk_1_2suffix",
    )
    legacy_mesh = r"mesh_chunk_(_?-?\\d+)_(_?-?\\d+)(?:_|$)"
    legacy_parent = r"region_\\d+_chunk_(_?-?\\d+)_(_?-?\\d+)(?:\\.\\d+)?"
    for name in cases:
        for original, replacement in (
            (re.search(legacy_mesh, name, re.I), scope["CHUNK_MESH_PATTERN"].search(name)),
            (re.fullmatch(legacy_parent, name, re.I), scope["CHUNK_PARENT_PATTERN"].fullmatch(name)),
        ):
            assert (original is None) == (replacement is None)
            if original is not None:
                assert original.span() == replacement.span()
                assert original.groups() == replacement.groups()


if __name__ == "__main__":
    test_chunk_name_patterns_preserve_matching()
    test_scene_report()
    test_shared_prototype_ancestry_is_cached()
    test_repeated_instance_bounds()
    test_initial_view_starts_close_to_large_terrain()
    test_static_scene_avoids_depsgraph()
    test_usd_stage_mesh_grouping()
    test_bounds_extrema_and_nonfinite_coordinates()
    print("Blender scene, USD grouping and repeated-instance framing checks passed.")

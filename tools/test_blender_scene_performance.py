"""Exercise Blender geometry reporting/framing without requiring Blender in CI."""
import ast
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
                 and node.name in ("scene_report", "frame_actual_scene")]
    assert len(functions) == 2
    namespace = {
        "Counter": Counter, "Vector": Vec, "bpy": bpy,
        "log": lambda *args: messages.append(args),
        "float": float, "min": min, "max": max,
    }
    exec(compile(ast.Module(body=functions, type_ignores=[]), "Blender-import-functions", "exec"), namespace)
    return namespace


def test_scene_report():
    ancestor = NS(name="prototypes", parent=None)
    solid = Mesh("terrain", 10, 23)
    prototype = Mesh("tree", 4, 8, ancestor)
    cloud = NS(type="POINTCLOUD", name="cloud", data=NS(points=range(17)),
               modifiers=[NS(type="NODES"), NS(type="SUBSURF"), NS(type="NODES")])
    scene_objects = SceneObjects([solid, prototype, cloud, NS(type="CAMERA")])
    messages = []
    bpy = NS(context=NS(scene=NS(objects=scene_objects)), data=NS(images={}))
    report = imported_functions(bpy, messages)["scene_report"]()
    assert report == {"meshes": 2, "faces": 14, "terrain_faces": 10, "clouds": 1, "points": 17}
    assert scene_objects.iterations == 1
    assert any("BLENDER geometry-node modifiers on point clouds:" in x and 2 in x
               for x in messages)


def test_repeated_instance_bounds():
    proto = Mesh("prototype", 8, 8)
    local = Mesh("local", 8, 8, bbox=list((x, y, z)
                                        for x in (-2, -1) for y in (-2, -1) for z in (-2, -1)))
    instances = [
        NS(object=proto, is_instance=True, matrix_world=Matrix()),
        NS(object=proto, is_instance=True, matrix_world=Matrix((16, 0, 0))),
        NS(object=local, is_instance=False, matrix_world=Matrix()),
    ]
    space = NS(region_3d=NS(view_location=None, view_distance=None), clip_end=10)
    bpy = NS(context=NS(evaluated_depsgraph_get=lambda: NS(object_instances=instances),
                        scene=NS(objects=[proto, local])),
             data=NS(screens=[NS(areas=[NS(type="VIEW_3D", spaces=NS(active=space))])]))
    messages = []
    imported_functions(bpy, messages)["frame_actual_scene"]()
    assert proto.bbox_reads == 1, "Repeated instances should reuse the same eight bounds"
    center = space.region_3d.view_location.values
    assert center == [7.5, -0.5, -0.5], center
    assert abs(space.region_3d.view_distance - 25.65) < 0.00001
    assert space.clip_end == 1000
    assert any("Evaluated mesh elements:" in x and 3 in x and 2 in x for x in messages)


if __name__ == "__main__":
    test_scene_report()
    test_repeated_instance_bounds()
    print("Blender model-report and repeated-instance framing checks passed.")

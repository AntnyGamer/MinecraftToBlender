"""Validate real viewport-object culling without Blender or texture changes."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS

source = Path("assets/Import_Existing_USD.py").read_text(encoding="utf-8")
module = ast.parse(source)
names = {"outside_nearby_radius", "hide_distant_meshes", "import_world"}
funcs = [node for node in module.body if isinstance(node, ast.FunctionDef)
         and node.name in names]
assert len(funcs) == 3


class Vec:
    def __init__(self, values):
        self.coords = list(values)

    def __getitem__(self, axis):
        return self.coords[axis]


class Matrix:
    def __matmul__(self, vec):
        return Vec(vec)


class Mesh:
    def __init__(self, name, lo, hi, hide_render=False, hidden=False):
        self.type = "MESH"
        self.name = name
        self.hide_render = hide_render
        self.hidden = hidden
        self.matrix_world = Matrix()
        self.bound_box = tuple((x, y, z)
                               for x in (lo[0], hi[0])
                               for y in (lo[1], hi[1])
                               for z in (lo[2], hi[2]))

    def hide_get(self):
        return self.hidden

    def hide_set(self, value):
        self.hidden = value

    def visible_get(self):
        return not self.hidden


near = Mesh("nearby terrain", (5, 5, -192), (20, 20, 192))
far = Mesh("distant terrain", (700, 700, -192), (720, 720, 192))
underground = Mesh("deep cave under center", (-30, -30, -350), (30, 30, -320))
spanning = Mesh("wide continuous terrain", (-600, -5, -100), (600, 5, 100))
invisible_render = Mesh("render-hidden prototype", (650, 650, 0), (670, 670, 10),
                        hide_render=True)
already_hidden = Mesh("originally hidden", (700, 700, 0), (710, 710, 10),
                      hidden=True)
objects = [near, far, underground, spanning, invisible_render, already_hidden]
records = []
import_calls = []
bpy = NS(
    context=NS(scene=NS(objects=objects)),
    ops=NS(mieximport=NS(world=lambda **kwargs: (
        import_calls.append(kwargs), {"FINISHED"})[1])),
    data=NS(materials=[object()], meshes=[object()]),
)
scope = {
    "bpy": bpy,
    "Vector": Vec,
    "log": lambda *args: records.append(args),
    "time": NS(monotonic=lambda: 0),
    "Usd": NS(Stage=NS(SetGlobalVariantFallbacks=lambda *_: None)),
    "clear_objects": lambda: None,
    "scene_report": lambda: {"meshes": 6},
}
exec(compile(ast.Module(body=funcs, type_ignores=[]),
             "<view-culling-test>", "exec"), scope)

# The two widest axes are used as horizontal dimensions, independent of
# whether Blender's import is Y-up or Z-up.
assert scope["outside_nearby_radius"]([700, 700, -192], [720, 720, 192],
                                      [0, 0, 0], (0, 1), 256)
assert not scope["outside_nearby_radius"]([-600, -5, -100],
                                          [600, 5, 100],
                                          [0, 0, 0], (0, 1), 256)
assert scope["hide_distant_meshes"]((Vec([0, 0, 0]), Vec([1024, 1024, 384]))) == 1
assert far.hidden
assert not near.hidden
assert not underground.hidden
assert not spanning.hidden
assert invisible_render.hide_render
assert already_hidden.hidden
assert bpy.data.materials and bpy.data.meshes  # No mesh/material deletion.
assert any("Alt+H" in " ".join(map(str, row)) for row in records)

# Users can restore the full model using Blender's Alt+H reveal-all.
far.hide_set(False)
assert not far.hidden

# No accidental terrain hiding for small regions.
assert scope["hide_distant_meshes"]((Vec([0, 0, 0]), Vec([256, 256, 384]))) == 0
assert not far.hidden
# Only the X and Z axes are horizontal in a Y-up representation.
far_xz = Mesh("distant in XZ", (700, -350, 700), (710, -300, 710))
bpy.context.scene.objects = [far_xz]
assert scope["hide_distant_meshes"]((Vec([0, 0, 0]), Vec([1024, 384, 1024]))) == 1

# MiEx's background objects must remain shown in both modes; no missing
# terrain can result from indiscriminately hiding an entire background group.
scope["import_world"]("World.usd", "render", fast_viewport=True)
scope["import_world"]("World.usd", "render", fast_viewport=False)
assert [x["hide_background"] for x in import_calls] == ["show", "show"]
assert all(x["import_type"] == "render" and x["flatten"] is False for x in import_calls)
assert all(x["max_animation_frames"] == 1 for x in import_calls)

main = next(node for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == "main")
flags = {value.value for value in ast.walk(main)
         if isinstance(value, ast.Constant) and isinstance(value.value, str)}
assert "--fast-viewport" in flags
assert "--minecraft-water" in flags
print("Nearby-only viewport hides distant objects, not geometry or render materials.")

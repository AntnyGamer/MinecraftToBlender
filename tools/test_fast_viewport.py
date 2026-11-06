"""Test safe optional mesh batching and exact material slot deduplication."""
import ast
import re
from pathlib import Path
from types import SimpleNamespace as NS

tree = ast.parse(Path("assets/Import_Existing_USD.py").read_text(encoding="utf-8"))
names = {"terrain_mesh_batch_key", "batch_static_terrain_meshes",
         "deduplicate_exact_material_slots", "is_minecraft_water_material",
         "is_conservatively_opaque_terrain_material"}
funcs = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
assert len(funcs) == len(names), "All required import-side helpers must exist"


class Mat:
    def __init__(self, name):
        self.name = name
        self.surface_render_method = "DITHERED"

    def as_pointer(self):
        return id(self)


class Polygons:
    def __init__(self, material_indices):
        self.indices = list(material_indices)

    def __len__(self):
        return len(self.indices)

    def foreach_get(self, field, values):
        assert field == "material_index"
        for i, val in enumerate(self.indices):
            values[i] = val

    def foreach_set(self, field, values):
        assert field == "material_index"
        self.indices[:] = list(values)


class Mesh:
    def __init__(self, mats, faces=20):
        self.users = 1
        self.shape_keys = None
        self.polygons = Polygons([i % len(mats) for i in range(faces)])
        self.materials = list(mats)
        self.uv_layers = [NS(name="UVMap", active_render=True)]
        self.color_attributes = []
        self.updated = 0

    def as_pointer(self):
        return id(self)

    def keys(self):
        return []

    def update(self):
        self.updated += 1


class Obj:
    def __init__(self, name, mesh, color=(1.0, 1.0, 1.0, 1.0)):
        self.name = name
        self.data = mesh
        self.type = "MESH"
        self.hide_render = self.hide_viewport = False
        self.instance_type = "NONE"
        self.modifiers = []
        self.constraints = []
        self.animation_data = None
        self.children = []
        self.vertex_groups = []
        self.material_slots = [NS(material=m, link="DATA") for m in mesh.materials]
        self.color = color
        self.parent = None
        self.selected = False

    def hide_get(self):
        return False

    def visible_get(self):
        return True

    def keys(self):
        return []

    def select_set(self, value):
        self.selected = value


stone = Mat("MAT_minecraft_block_stone_123")
water = Mat("MAT_minecraft_block_water_still_abc")
wood = Mat("MAT_minecraft_block_planks_abc")

terrain = [Obj(f"mesh_chunk_{x}_{z}_material", Mesh([stone], faces=15))
           for x in (0, 1, 2) for z in (0, 1)]
different = Obj("mesh_chunk_0_0_wood", Mesh([wood], faces=12))
water_mesh = Obj("mesh_chunk_0_0_water", Mesh([water], faces=30))
entity = Obj("item_frame_mesh_chunk_0_0", Mesh([stone], faces=6))
entity.type = "EMPTY"
complex_mesh = Obj("mesh_chunk_0_1_complex", Mesh([stone], faces=3))
complex_mesh.modifiers = [NS(type="NODES")]
all_objects = terrain + [different, water_mesh, entity, complex_mesh]


class ObjectLayer:
    def __init__(self):
        self.active = None
        self.objects = self

    def __contains__(self, name):
        return any(obj.name == name for obj in all_objects)

    def get(self, name):
        return next((obj for obj in all_objects if obj.name == name), None)


view_layer = ObjectLayer()
records = []


def deselect(action):
    assert action == "DESELECT"
    for obj in all_objects:
        obj.select_set(False)


def join():
    selected = [obj for obj in all_objects if obj.selected]
    active = view_layer.active
    assert active in selected and len(selected) >= 2
    # Mimic Blender's safe same-material join (all polygons and the active
    # material stay on the resulting mesh).
    count = sum(len(obj.data.polygons) for obj in selected)
    active.data.polygons = Polygons([0] * count)
    for obj in selected:
        if obj is not active:
            all_objects.remove(obj)
    return {"FINISHED"}


bpy = NS(context=NS(scene=NS(objects=all_objects), view_layer=view_layer,
                    selected_objects=[]),
         ops=NS(object=NS(select_all=deselect, join=join)))
scope = {"bpy": bpy, "re": re, "log": lambda *args: records.append(args)}
exec(compile(ast.Module(body=funcs, type_ignores=[]),
             "<mesh-batch-test>", "exec"), scope)
key = scope["terrain_mesh_batch_key"]
assert key(terrain[0]) == key(terrain[1])
assert key(terrain[0]) != key(terrain[4])  # adjacent 2x2 groups only
negative_chunk = Obj("mesh_chunk__1__2_material", Mesh([stone], faces=9))
assert key(negative_chunk)[0] == (-1, -1), "MiEx encodes negative '-' with '_'"
raw_negative_chunk = Obj("mesh_chunk_-1_-2_material", Mesh([stone], faces=9))
assert key(raw_negative_chunk)[0] == (-1, -1)

assert key(different) != key(terrain[0])  # different actual material
assert key(water_mesh) is None
glass_mesh = Obj("mesh_chunk_0_0_glass", Mesh([Mat("MAT_minecraft_block_glass_foo")]))
assert key(glass_mesh) is None, "Transparent glass should never be joined"
assert not scope["is_conservatively_opaque_terrain_material"](Mat("MAT_minecraft_block_ice_foo"))

assert key(entity) is None
assert key(complex_mesh) is None
nested_entity = Obj("mesh_chunk_1_0_prototype", Mesh([stone], faces=5))
nested_entity.parent = NS(name="entities", parent=None, animation_data=None,
                          constraints=[], hide_render=False)
assert key(nested_entity) is None, "Never merge meshes from the entity branch"
nested_background = Obj("mesh_chunk_1_0_background", Mesh([stone], faces=5))
nested_background.parent = NS(name="background", parent=None, animation_data=None,
                              constraints=[], hide_render=False)
assert key(nested_background) is None, "Do not merge proxy or background meshes"
actual_usd_mesh = Obj("minecraft_block_stone_df8d0afd", Mesh([stone], faces=5))
actual_usd_mesh.parent = NS(name="region_1_chunk_1_0", parent=None,
                          animation_data=None, constraints=[], hide_render=False)
assert key(actual_usd_mesh) == key(terrain[0]), "Real MiEx texture-named meshes use their chunk parent"
actual_usd_mesh.parent.parent = NS(name="entities", parent=None,
                                 animation_data=None, constraints=[], hide_render=False)
assert key(actual_usd_mesh) is None, "Parent-coordinate lookup must retain entity-branch exclusion"

before_faces = sum(len(obj.data.polygons) for obj in all_objects)
joined = scope["batch_static_terrain_meshes"]()
after_faces = sum(len(obj.data.polygons) for obj in all_objects)
assert joined == 4, (joined, records)
assert before_faces == after_faces, "Batching must not delete or duplicate polygon faces"
assert water_mesh in all_objects and different in all_objects
assert complex_mesh in all_objects
assert any("MESH BATCHING" in " ".join(map(str, row)) for row in records)

# Exact duplicate material data-block slots can be mapped to one shader
# without altering the per-polygon rendered material. Distinct slots stay.
dup = Obj("mesh_chunk_20_20_duplicate", Mesh([stone, wood, stone, wood, stone], faces=13))
all_objects.append(dup)
original_materials = [dup.data.materials[i] for i in dup.data.polygons.indices]
removed = scope["deduplicate_exact_material_slots"]()
remapped_materials = [dup.data.materials[i] for i in dup.data.polygons.indices]
assert removed == 3
assert original_materials == remapped_materials
assert dup.data.materials == [stone, wood]
assert dup.data.updated == 1

# Existing Blender projects can retain material indices whose slots were
# removed. Cleanup must leave the entire mesh intact instead of failing or
# assigning a guessed material, even after encountering earlier valid faces.
for stale_index in (2, 32767):
    stale = Obj("stale_slots", Mesh([stone, stone], faces=4))
    stale.data.polygons.indices = [1, 0, stale_index, 1]
    all_objects.append(stale)
    original_slots = list(stale.data.materials)
    original_indices = list(stale.data.polygons.indices)
    assert scope["deduplicate_exact_material_slots"]() == 0
    assert stale.data.materials == original_slots
    assert stale.data.polygons.indices == original_indices
    assert stale.data.updated == 0

# Never use approximate material similarity: different shader datablocks,
# even if they share the same name, must be retained independently.
same_name = Mat(stone.name)
nonidentical = Obj("mesh_chunk_50_50_distinct", Mesh([stone, same_name], faces=8))
all_objects.append(nonidentical)
assert scope["deduplicate_exact_material_slots"]() == 0
assert len(nonidentical.data.materials) == 2

# Most imported meshes have just one material. Their RNA material collection
# should not be iterated or copied merely to discover there is no duplicate.
class SingleSlotGuard(list):
    def __iter__(self):
        raise AssertionError("A single material slot was needlessly enumerated")


single_material = Obj("single_material_slot", Mesh([stone], faces=8))
single_material.data.materials = SingleSlotGuard([stone])
all_objects.append(single_material)
assert scope["deduplicate_exact_material_slots"]() == 0
assert single_material.data.updated == 0

src = Path("assets/Import_Existing_USD.py").read_text(encoding="utf-8")
assert "'--batch-static-meshes'" in src
assert "hide_distant_meshes(" not in src
assert "lighten_solid_viewport(" not in src
print("Bounded mesh batching and exact material dedup retain all faces and material appearances.")

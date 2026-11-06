"""Verify the in-memory MiEx shader lookup preserves Blender node names."""

import ast
from pathlib import Path
from types import SimpleNamespace


def optimized_lookup_source():
    tree = ast.parse(Path("assets/Import_Existing_USD.py").read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "load_patched_importer")
    originals = []
    optimizations = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        if not isinstance(node.value.value, str):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "original":
                if "def get_Node_By_Name" in node.value.value:
                    originals.append(node.value.value)
            if isinstance(target, ast.Name) and target.id == "faster":
                if "def get_Node_By_Name" in node.value.value:
                    optimizations.append(node.value.value)
    assert len(originals) == len(optimizations) == 1
    assert "for node in self.mat.node_tree.nodes:" in originals[0]
    assert ".get(name)" in optimizations[0]
    assert originals[0].count("name = name[:63]") == 1
    assert optimizations[0].count("name = name[:63]") == 1
    return optimizations[0]


class NodeCollection:
    def __init__(self, nodes):
        self.nodes = {n.name: n for n in nodes}
        self.lookups = []

    def get(self, name):
        self.lookups.append(name)
        return self.nodes.get(name)

    def __iter__(self):
        raise AssertionError("shader node lookup must not enumerate every node")


def test_material_lookup():
    code = optimized_lookup_source()
    scope = {}
    exec("class MaterialSetup:\n" + code + "\n", scope)
    nodes = [SimpleNamespace(name="Texture"), SimpleNamespace(name="Output")]
    long_name = "N" * 63
    nodes.append(SimpleNamespace(name=long_name))
    instance = scope["MaterialSetup"]()
    collection = NodeCollection(nodes)
    instance.mat = SimpleNamespace(node_tree=SimpleNamespace(nodes=collection))
    assert instance.get_Node_By_Name("Texture") is nodes[0]
    assert instance.get_Node_By_Name("Output") is nodes[1]
    assert instance.get_Node_By_Name(long_name + "ignored") is nodes[2]
    assert collection.lookups == ["Texture", "Output", long_name]
    try:
        instance.get_Node_By_Name("Missing")
    except Exception as exc:
        assert str(exc) == "Node not found: Missing"
    else:
        raise AssertionError("missing shader node did not report original error")


def test_redundant_preview_shaders_are_skipped():
    tree = ast.parse(Path("assets/Import_Existing_USD.py").read_text(encoding="utf-8"))
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
              and node.name == "load_patched_importer")
    # The pinned MiEx importer builds the Minecraft JSON material nodes after
    # Blender's USD reader creates the bound material datablocks. Only the
    # temporary preview shader network is skipped; not USD material binding.
    assigns = [node for node in fn.body
               if isinstance(node, ast.Assign)
               and any(isinstance(target, ast.Name) and target.id == "usd_import"
                       for target in node.targets)]
    assert len(assigns) == 1
    anchor = ast.literal_eval(assigns[0].value)
    assert anchor == "mtl_name_collision_mode='REFERENCE_EXISTING',import_proxy="
    replaced = [node for node in ast.walk(fn) if isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and "import_usd_preview=False" in node.value]
    assert len(replaced) == 1
    assert replaced[0].value == (
        "mtl_name_collision_mode='REFERENCE_EXISTING',"
        "import_usd_preview=False,import_proxy="
    )
    example = (
        "bpy.ops.wm.usd_import(filepath=filepath, import_visible_only=False, "
        "set_frame_range=False, scale=1.0/16.0, "
        + anchor
        + "bool(options['import_type'] != 'render'))"
    )
    assert example.count(anchor) == 1
    updated = example.replace(anchor, replaced[0].value, 1)
    assert "import_materials=False" not in updated
    assert "import_usd_preview=False" in updated
    assert "import_visible_only=False" in updated
    assert "mtl_name_collision_mode='REFERENCE_EXISTING'" in updated
    assert "import_proxy=bool(options['import_type'] != 'render')" in updated


def test_minecraft_shader_graph_starts_clean():
    tree = ast.parse(Path("assets/Import_Existing_USD.py").read_text(encoding="utf-8"))
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
              and node.name == "load_patched_importer")
    strings = [node for node in ast.walk(fn)
               if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
               and isinstance(node.value.value, str)]
    original = [node.value.value for node in strings
                if any(isinstance(t, ast.Name) and t.id == "original" for t in node.targets)
                and "self.mat.node_tree.nodes.remove(node)" in node.value.value]
    safe = [node.value.value for node in strings
            if any(isinstance(t, ast.Name) and t.id == "safe" for t in node.targets)
            and "self.mat.node_tree.nodes.clear()" in node.value.value]
    assert original == [
        "        for node in self.mat.node_tree.nodes:\n"
        "            self.mat.node_tree.nodes.remove(node)"
    ]
    assert safe == ["        self.mat.node_tree.nodes.clear()"]
    # The real Blender Nodes collection has a native .clear() method. Its
    # intended semantics are to discard every old USD/default shader node.
    class Nodes(list):
        def remove(self, item):
            raise AssertionError("Do not remove elements while iterating this collection")

    nodes = Nodes([SimpleNamespace(name="Old USD shader"),
                   SimpleNamespace(name="Old material output"),
                   SimpleNamespace(name="Old texture")])
    instance = SimpleNamespace(mat=SimpleNamespace(node_tree=SimpleNamespace(nodes=nodes)))
    scope = {"self": instance}
    exec(safe[0].strip(), scope)
    assert not nodes, "The new Minecraft material graph must start with no stale nodes"


def test_shared_image_color_and_alpha_are_isolated():
    import textwrap
    tree = ast.parse(Path("assets/Import_Existing_USD.py").read_text(encoding="utf-8"))
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
              and node.name == "load_patched_importer")
    safe_strings = [
        node.value.value for node in fn.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "safe" for t in node.targets)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
        and "node.image = bpy.data.images.load(imagePath, check_existing=True)" in node.value.value
    ]
    assert len(safe_strings) == 1
    # Test only the post-load sharing policy. The full upstream wrapper
    # includes an except-block 'continue' belonging to import_node's loop.
    # Executing that isolated wrapper outside its loop would be invalid Python.
    policy_start = safe_strings[0].index("                        # Blender stores")
    policy = textwrap.dedent(safe_strings[0][policy_start:])
    safe_code = compile(policy, "<shared-image>", "exec")

    class Image:
        def __init__(self, users, colorspace="sRGB", alpha="STRAIGHT"):
            self.users = users
            self.colorspace_settings = SimpleNamespace(name=colorspace)
            self.alpha_mode = alpha
            self.copy_count = 0

        def copy(self):
            self.copy_count += 1
            return Image(1, self.colorspace_settings.name, self.alpha_mode)

    def run(image, colorspace, alpha):
        class Images:
            def load(self, path, check_existing=False):
                assert path == "blocks.png"
                assert check_existing
                return image

        node = SimpleNamespace(image=image)
        data = {"attributes": {
            "colorspace_settings": {"value": colorspace},
            "alpha_mode": {"value": alpha},
        }}
        bpy = SimpleNamespace(data=SimpleNamespace(images=Images()))
        scope = {"node": node, "data": data, "imagePath": "blocks.png", "bpy": bpy}
        exec(safe_code, scope)
        return node.image

    original = Image(3)
    isolated = run(original, ["Non-Color"], "PREMUL")
    assert isolated is not original
    assert original.copy_count == 1
    isolated.colorspace_settings.name = "Non-Color"
    isolated.alpha_mode = "PREMUL"
    assert original.colorspace_settings.name == "sRGB"
    assert original.alpha_mode == "STRAIGHT"

    # Shared identical configurations continue to reuse one Image datablock
    # rather than multiplying thousands of vanilla Minecraft textures.
    original = Image(32)
    assert run(original, ["sRGB", "sRGB Encoded Rec.709 (sRGB)"], "STRAIGHT") is original
    assert original.copy_count == 0

    # A first-time image has no existing material to accidentally recolor.
    first = Image(1)
    assert run(first, "Non-Color", "STRAIGHT") is first
    assert first.copy_count == 0

    # Alpha-only differences are just as important as color-space differences.
    shared = Image(2)
    assert run(shared, ["sRGB"], "PREMUL") is not shared
    assert shared.copy_count == 1


def test_flat_shading_buffer_preserves_every_flag():
    import textwrap
    tree = ast.parse(Path("assets/Import_Existing_USD.py").read_text(encoding="utf-8"))
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
              and node.name == "load_patched_importer")
    assignments = [node.value.value for node in fn.body
                   if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                   and isinstance(node.value.value, str)
                   and any(isinstance(t, ast.Name) and t.id == "faster" for t in node.targets)
                   and 'foreach_set("use_smooth"' in node.value.value]
    assert len(assignments) == 1
    for count in (0, 1, 17, 1000000):
        class Polygons:
            def __len__(self):
                return count

            def foreach_set(self, name, values):
                assert name == "use_smooth"
                assert len(values) == count
                assert not any(values), "Every polygon must keep flat shading"
                assert values.format == "?" and values.nbytes == count
        mesh = SimpleNamespace(data=SimpleNamespace(polygons=Polygons()))
        exec(textwrap.dedent(assignments[0]), {"mesh": mesh})


if __name__ == "__main__":
    test_material_lookup()
    test_redundant_preview_shaders_are_skipped()
    test_minecraft_shader_graph_starts_clean()
    test_shared_image_color_and_alpha_are_isolated()
    test_flat_shading_buffer_preserves_every_flag()
    print("Pinned MiEx materials preserve shared-image appearance, shader reset, fast lookup and USD imports.")

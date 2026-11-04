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


if __name__ == "__main__":
    test_material_lookup()
    test_redundant_preview_shaders_are_skipped()
    print("Pinned MiEx material-node lookup and USD preview import regressions passed.")

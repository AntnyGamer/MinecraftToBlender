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


if __name__ == "__main__":
    test_material_lookup()
    print("Pinned MiEx material-node lookup regressions passed.")

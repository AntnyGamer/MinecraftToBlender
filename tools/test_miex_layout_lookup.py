"""Ensure optimized MiEx node layout lookup preserves original node order."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS

tree = ast.parse(Path("assets/Import_Existing_USD.py").read_text(encoding="utf-8"))
method = next(x for x in tree.body if isinstance(x, ast.FunctionDef)
              and x.name == "load_patched_importer")
pairs = []
original = None
for stmt in method.body:
    if not isinstance(stmt, ast.Assign) or not isinstance(stmt.value, ast.Constant):
        continue
    if not isinstance(stmt.value.value, str):
        continue
    target = stmt.targets[0]
    if not isinstance(target, ast.Name):
        continue
    if target.id == "original":
        original = stmt.value.value
    elif target.id == "faster" and original and "def getNode(self" in original:
        pairs.append((original, stmt.value.value))
        original = None
assert len(pairs) == 1, "Expected exactly one MiEx NodeGrid lookup optimization"

class Node:
    def __init__(self, node, column, row):
        self.node, self.column, self.row = node, column, row

def grid(source):
    code = ("class Grid:\n"
            "    def __init__(self):\n"
            "        self.nodes = []\n"
            "        self.byName = {}\n"
            "    def getColumn(self, column):\n"
            "        return [n for n in self.nodes if n.column == column]\n"
            + source + "\n")
    scope = {"Node": Node, "bpy": NS(types=NS(Node=object))}
    exec(code, scope)
    return scope["Grid"]()

def exercise(g):
    ordered = [NS(name=f"node_{i}") for i in range(200)]
    positions = []
    for node in ordered:
        first = g.getNode(node)
        assert g.getNode(node) is first
        assert g.getNodeIfMissing(node) is None
        positions.append((first.column, first.row))
    assert g.getNodeIfMissing(NS(name="extra")) is not None
    assert len(g.nodes) == 201
    return positions

old, fast = pairs[0]
assert exercise(grid(old)) == exercise(grid(fast))
assert "self.byName.get(node.name)" in fast
assert "self.byName[node.name] = node2" in fast
print("MiEx node-grid optimization preserves material layout and unique-node semantics.")

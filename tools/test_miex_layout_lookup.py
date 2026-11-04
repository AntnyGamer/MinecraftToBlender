"""Compare MiEx material layout's original vs accelerated node bookkeeping."""
import ast
import textwrap
from pathlib import Path
from types import SimpleNamespace as NS

tree = ast.parse(Path("assets/Import_Existing_USD.py").read_text(encoding="utf-8"))
method = next(x for x in tree.body if isinstance(x, ast.FunctionDef)
              and x.name == "load_patched_importer")
pairs = {}
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
    elif target.id == "faster" and original:
        if "def getNode(self" in original:
            pairs["nodes"] = (original, stmt.value.value)
        elif "def setColumn(self" in original:
            pairs["columns"] = (original, stmt.value.value)
        original = None
assert set(pairs) == {"nodes", "columns"}, "Expected both optimized MiEx grid functions"

class Node:
    def __init__(self, node, column, row):
        self.node, self.column, self.row = node, column, row

def grid(methods):
    code = ("class Grid:\n"
            "    def __init__(self):\n"
            "        self.nodes = []\n"
            "        self.byName = {}\n"
            "        self.columnSizes = {}\n"
            "        self.minColumn = 0\n"
            "        self.maxColumn = 0\n"
            "    def getColumn(self, column):\n"
            "        res = []\n"
            "        for node in self.nodes:\n"
            "            if node.column == column:\n"
            "                res.insert(node.row, node)\n"
            "        return res\n"
            + textwrap.indent(textwrap.dedent(methods["nodes"]), "    ") + "\n"
            + textwrap.indent(textwrap.dedent(methods["columns"]), "    ") + "\n")
    scope = {"Node": Node, "bpy": NS(types=NS(Node=object))}
    exec(code, scope)
    return scope["Grid"]()

def snapshot(g):
    return (
        [(n.node.name, n.column, n.row) for n in g.nodes],
        [[(n.node.name, n.row) for n in g.getColumn(col)]
         for col in range(6)],
        g.minColumn,
        g.maxColumn,
    )

old = grid({key: values[0] for key, values in pairs.items()})
fast = grid({key: values[1] for key, values in pairs.items()})
names = [NS(name=f"node_{i}") for i in range(400)]
for index, node in enumerate(names):
    assert old.getNodeIfMissing(node) is not None
    assert fast.getNodeIfMissing(node) is not None
    assert old.getNodeIfMissing(node) is None
    assert fast.getNodeIfMissing(node) is None
    assert old.getNode(node).node.name == fast.getNode(node).node.name
    if index % 19 == 0:
        assert snapshot(old) == snapshot(fast)

# Move nodes into successively farther columns in a way that tests original
# insertion order, variable column sizes and row compaction after each move.
for step in range(1100):
    index = (step * 137 + 19) % len(names)
    node = names[index]
    target_col = (step * 11 + index // 13) % 6
    old.setColumn(old.getNode(node), target_col)
    fast.setColumn(fast.getNode(node), target_col)
    if step % 67 == 0:
        assert snapshot(old) == snapshot(fast), f"Mismatch at move {step}"

assert snapshot(old) == snapshot(fast)
assert "self.byName.get(node.name)" in pairs["nodes"][1]
assert "self.columnSizes.get(0, 0)" in pairs["nodes"][1]
assert "self.columnSizes.get(column, 0)" in pairs["columns"][1]
print("MiEx original and accelerated 400-node, 1100-move material layouts match.")

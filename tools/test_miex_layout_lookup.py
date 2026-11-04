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
        elif "def getColumn(self" in original:
            pairs["get_column"] = (original, stmt.value.value)
        elif "def placeInColumns(" in original:
            pairs["traversal"] = (original, stmt.value.value)
        original = None
assert set(pairs) == {"nodes", "columns", "get_column", "traversal"}, "Expected all optimized MiEx grid functions"

class Node:
    def __init__(self, node, column, row):
        self.node, self.column, self.row = node, column, row

def grid(methods):
    code = ("class Grid:\n"
            "    def __init__(self):\n"
            "        self.nodes = []\n"
            "        self.byName = {}\n"
            "        self.columnSizes = {}\n"
            "        self.columnMembers = {0: []}\n"
            "        self.minColumn = 0\n"
            "        self.maxColumn = 0\n"
            + textwrap.indent(textwrap.dedent(methods["get_column"]), "    ") + "\n"
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
assert "self.columnMembers[0].append(node2)" in pairs["nodes"][1]
assert "for other in oldMembers:" in pairs["columns"][1]
assert "self.columnMembers.get(column, ())" in pairs["get_column"][1]
assert "creation_index" in pairs["get_column"][1]
assert sum(len(group) for group in fast.columnMembers.values()) == len(names)
assert all(member.column == column
           for column, group in fast.columnMembers.items() for member in group)

# In a shared directed-acyclic shader graph, the original recursion processes
# the same upstream subtrees repeatedly. Check the new deepest-column cache
# against the original traversal's exact node positions and ordering, including
# a node first reached shallowly and subsequently reached deeper.
def linked(parent):
    return NS(is_linked=True, links=[NS(from_node=parent)])

layers = [[NS(name=f"shader_{depth}_{index}", inputs=[])
           for index in range(3)] for depth in range(8)]
for level, next_level in zip(layers, layers[1:]):
    for node in level:
        node.inputs = [linked(child) for child in next_level]
root = NS(name="MaterialOutput",
          inputs=[linked(layers[-1][0])] + [linked(n) for n in layers[0]])

def traverse(methods, source):
    g = grid(methods)
    calls = [0]
    original_get = g.getNode
    def counting_get(node):
        calls[0] += 1
        return original_get(node)
    g.getNode = counting_get
    env = {"bpy": NS(types=NS(Node=object, NodeLink=object)), "NodeGrid": type(g)}
    exec(textwrap.dedent(source), env)
    env["placeInColumns"](root, g, 0)
    return g, calls[0]

old_grid, old_calls = traverse({k: v[0] for k, v in pairs.items()}, pairs["traversal"][0])
fast_grid, fast_calls = traverse({k: v[1] for k, v in pairs.items()}, pairs["traversal"][1])
assert snapshot(old_grid) == snapshot(fast_grid)
assert old_calls > fast_calls * 3, (old_calls, fast_calls)
assert "seen_columns.get(name, -1) >= column" in pairs["traversal"][1]
print(f"MiEx 8-layer shared shader graph positions match; traversal calls: {old_calls} original vs {fast_calls} cached.")
print("MiEx original and accelerated 400-node, 1100-move shader layouts match, including exact node ordering per column.")

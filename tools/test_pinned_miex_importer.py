"""Run the complete in-memory patch against the exact pinned official MiExImport.py.

This catches whitespace-sensitive patch guards without running Blender or the
untrusted downloaded add-on. A separate Blender installation is not required.
"""
import ast
import re
import sys
import types
from pathlib import Path
from urllib.request import urlopen

PINNED = (
    "https://raw.githubusercontent.com/BramStoutProductions/MiEx/"
    "631e9fc2fde8c749bf59d4c3495492e62a83ef6c/"
    "extras/Blender/BlenderAddon/MiExImport.py"
)
LOCAL = Path("assets/Import_Existing_USD.py")


def extract_patch():
    tree = ast.parse(LOCAL.read_text(encoding="utf-8"))
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef)
                    and node.name == "load_patched_importer")
    executable = ast.fix_missing_locations(
        ast.Module(body=[function], type_ignores=[]))
    namespace = {}
    exec(compile(executable, str(LOCAL), "exec"), namespace)
    return namespace["load_patched_importer"]


class Source:
    def __init__(self, contents):
        self.contents = contents

    def read_text(self, encoding):
        assert encoding == "utf-8-sig"
        return self.contents

    def __str__(self):
        return "MiExImport.py"


def patch_without_blender(function, source):
    captured = {}
    def capture_compile(contents, filename, mode):
        # Real compile checks the entire patched file's Python syntax.
        compile(contents, filename, mode)
        return contents

    def capture_exec(contents, destination):
        captured["source"] = contents
        destination["register"] = lambda: None

    # The patch function is the real function body, executed with substitute
    # compile/exec hooks that prevent executing the downloaded addon.
    env = {
        "sys": types.SimpleNamespace(modules={}),
        "types": types,
        "re": re,
        "log": lambda *args: None,
        "compile": capture_compile,
        "exec": capture_exec,
    }
    code = function.__code__
    patch = types.FunctionType(code, env)
    patch(Source(source))
    assert "source" in captured, "Patching did not reach the final compile"
    return captured["source"]


def main():
    with urlopen(PINNED, timeout=45) as response:
        raw = response.read().decode("utf-8-sig")
    assert "class NodeGrid:" in raw
    assert "getNodeIfMissing" in raw
    upstream_whitespace = ("                return node2\n"
                           "            \n"
                           "            def getNodeIfMissing")
    assert upstream_whitespace in raw, (
        "The pinned official importer no longer has the whitespace pattern "
        "that caused the user's v1.1.2 error"
    )
    function = extract_patch()
    patched = patch_without_blender(function, raw)
    assert "self.byName[node.name] = node2" in patched
    assert "self.columnMembers.get(column, ())" in patched
    assert "seen_columns.get(name, -1) >= column" in patched
    assert "import_usd_preview=False" in patched
    assert "self.mat.node_tree.nodes.clear()" in patched
    assert 'memoryview(bytearray(len(mesh.data.polygons))).cast("?")' in patched
    assert "input_sock = node.inputs.get(attrName)" in patched
    # Only the temporary layout wrapper's unused Python list is removed.
    # Actual shader node outputs/connections must still be present.
    raw_tree = ast.parse(raw)
    setup = next(n for n in raw_tree.body if isinstance(n, ast.ClassDef)
                 and n.name == "SetupMaterials")
    layout = next(n for n in setup.body if isinstance(n, ast.FunctionDef)
                  and n.name == "layoutNodes")
    outputs = [n for n in ast.walk(layout)
               if isinstance(n, ast.Attribute) and n.attr == "outputs"]
    assert len(outputs) == 1 and isinstance(outputs[0].ctx, ast.Store)
    assert 'self.outputs : list[Node] = []' not in patched
    assert 'node0.outputs[attr0], node1.inputs[attr1]' in patched
    patched_tree = ast.parse(patched)
    wrapper = next(n for n in ast.walk(patched_tree)
                   if isinstance(n, ast.ClassDef) and n.name == 'Node')
    scope = {'bpy': types.SimpleNamespace(types=types.SimpleNamespace(Node=object))}
    exec(compile(ast.Module(body=[wrapper], type_ignores=[]), '<layout-wrapper>', 'exec'), scope)
    wrapped = scope['Node'](object(), 2, 3)
    wrapped.creation_index = 4
    assert (wrapped.column, wrapped.row, wrapped.creation_index) == (2, 3, 4)
    assert not hasattr(wrapped, '__dict__'), 'Private layout wrappers should not allocate instance dictionaries'
    assert "for node2 in self.nodes:\n                    if node2.node.name == node.name" not in patched
    ast.parse(patched)

    # Indentation-only lines are formatting, not a different importer.
    compact = raw.replace(upstream_whitespace,
                          upstream_whitespace.replace("            \n", "\n"))
    assert compact != raw
    assert patch_without_blender(function, compact) == patched

    # Meaningful changes to the pinned importer still fail closed.
    changed = raw.replace("def get_Node_By_Name(self, name:str):",
                          "def get_Node_By_Name(self, name):", 1)
    try:
        patch_without_blender(function, changed)
    except RuntimeError as exc:
        assert "material node lookup changed" in str(exc)
    else:
        raise AssertionError("Unexpected import patch accepted altered code")

    changed = raw.replace(
        '[False for _ in range(len(mesh.data.polygons))]',
        '[True for _ in range(len(mesh.data.polygons))]', 1)
    assert changed != raw
    try:
        patch_without_blender(function, changed)
    except RuntimeError as exc:
        assert "flat-shading assignment changed" in str(exc)
    else:
        raise AssertionError("Flat-shading patch accepted changed source behavior")

    print("Full pinned MiEx importer patch compiled; whitespace-only lines "
          "are normalized and meaningful source mismatches remain guarded.")


if __name__ == "__main__":
    main()

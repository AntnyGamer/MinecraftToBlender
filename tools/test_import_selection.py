"""Regression-test startup selection cleanup for very large imported worlds."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS

tree = ast.parse(Path("assets/Import_Existing_USD.py").read_text(encoding="utf-8"))
method = next(x for x in tree.body
              if isinstance(x, ast.FunctionDef) and x.name == "clear_bulk_import_selection")
source_main = next(x for x in tree.body
                   if isinstance(x, ast.FunctionDef) and x.name == "main")

class Mesh:
    def __init__(self, selected=True, visible=True, kind="MESH"):
        self.type = kind
        self.selected = selected
        self.visible = visible
        self.data = NS(vertices=[1, 2], polygons=[1, 2, 3], materials=[object()])

    def visible_get(self):
        return self.visible

selected = [Mesh() for _ in range(130)] + [Mesh(kind="EMPTY")]
materials = [object()]
calls = []

def deselect(action):
    assert action == "DESELECT"
    calls.append(action)
    for ob in selected:
        ob.selected = False

view_layer = NS(objects=NS(active=selected[0]))
bpy = NS(context=NS(selected_objects=selected, view_layer=view_layer),
         ops=NS(object=NS(select_all=deselect)), data=NS(materials=materials))
scope = {"bpy": bpy, "log": lambda *args: calls.append(args)}
exec(compile(ast.Module(body=[method], type_ignores=[]), "<selected>", "exec"), scope)
clear = scope["clear_bulk_import_selection"]

# Small scenes remain selected (preserve normal Blender start/edit behavior).
assert clear(min_meshes=132) == 0
assert not calls
assert all(ob.selected for ob in selected)

# Large imports clear only the *editor's* selection, not any mesh or material.
mesh_data = tuple(ob.data for ob in selected)
assert clear() == 130
assert calls[0] == "DESELECT"
assert view_layer.objects.active is None
assert all(not ob.selected for ob in selected)
assert tuple(ob.data for ob in selected) == mesh_data
assert bpy.data.materials == materials
assert any("VIEWPORT" in str(call) for call in calls[1:])
assert any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
           and node.func.id == "clear_bulk_import_selection"
           for node in ast.walk(source_main))
print("Bulk import selection cleanup preserves mesh/material data and small-world behavior.")

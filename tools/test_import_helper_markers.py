"""Confirm imported USD helper markers are hidden without altering scene objects."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS

src = Path("assets/Import_Existing_USD.py").read_text(encoding="utf-8")
tree = ast.parse(src)
fn = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "hide_imported_transform_markers"]
assert len(fn) == 1
plain = NS(type="EMPTY", empty_display_type="PLAIN_AXES", empty_display_size=1.0, parent=None, hide_render=False)
image = NS(type="EMPTY", empty_display_type="IMAGE", empty_display_size=0.8, parent=None, hide_render=False)
mesh = NS(type="MESH", empty_display_type="PLAIN_AXES", empty_display_size=1.0, parent=plain, hide_render=False)
already = NS(type="EMPTY", empty_display_type="PLAIN_AXES", empty_display_size=0.0001, parent=plain, hide_render=False)
scene = NS(objects=[plain,image,mesh,already])
bpy = NS(context=NS(scene=scene))
events = []
scope = {"bpy":bpy,"log":lambda *parts:events.append(parts)}
exec(compile(ast.Module(body=fn,type_ignores=[]), "<USD helpers>", "exec"),scope)
hide = scope["hide_imported_transform_markers"]
assert hide() == 1
assert plain.empty_display_size == 0.0001
assert image.empty_display_size == 0.8
assert mesh.empty_display_size == 1.0
assert already.empty_display_size == 0.0001
assert mesh.parent is plain and already.parent is plain
assert not any(o.hide_render for o in scene.objects)
assert hide() == 0
assert len(events) == 1
assert "hide_imported_transform_markers()" in src
print("USD transform crosshairs hidden, geometry and parenting unchanged.")

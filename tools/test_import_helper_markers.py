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
# Test the viewport-only fast path separately. Blender's documented
# show_object_viewport_empty switch filters Empty object drawing, not meshes.
# Its scope is one SpaceView3D: no object hide_viewport or hide_render flags
# may change, and existing image/control helpers prevent auto-activation.
fast_fn = [n for n in tree.body if isinstance(n, ast.FunctionDef)
           and n.name == "avoid_drawing_unused_import_empties"]
assert len(fast_fn) == 1
fast_scope = {"log": lambda *parts: events.append(parts)}
exec(compile(ast.Module(body=fast_fn, type_ignores=[]), "<viewport-empties>", "exec"),
     fast_scope)
fast = fast_scope["avoid_drawing_unused_import_empties"]


def make_view():
    return NS(type="VIEW_3D", show_object_viewport_empty=True,
              show_object_viewport_mesh=True)


view = make_view()
another = make_view()
other_type = NS(type="IMAGE_EDITOR")
screen = NS(areas=[NS(spaces=[view, other_type]),
                   NS(spaces=[another])])
fast_bpy = NS(data=NS(screens=[screen]),
              context=NS(scene=NS(objects=[])))
fast_scope["bpy"] = fast_bpy
parent = NS(type="EMPTY", empty_display_type="PLAIN_AXES",
            empty_display_size=0.0001, modifiers=[], hide_render=False,
            hide_viewport=False)
mesh_child = NS(type="MESH", parent=parent, hide_render=False,
                hide_viewport=False)
helpers = [NS(type="EMPTY", empty_display_type="PLAIN_AXES",
              empty_display_size=0.0001, modifiers=[], hide_render=False,
              hide_viewport=False) for _ in range(127)] + [parent]
fast_bpy.context.scene.objects = helpers[:127] + [mesh_child]
assert fast() == 0 and view.show_object_viewport_empty
fast_bpy.context.scene.objects = helpers + [mesh_child]
assert fast() == 2
assert not view.show_object_viewport_empty
assert not another.show_object_viewport_empty
assert view.show_object_viewport_mesh and another.show_object_viewport_mesh
assert all(not ob.hide_render and not ob.hide_viewport for ob in helpers)
assert mesh_child.parent is parent and not mesh_child.hide_viewport
assert fast() == 0

# Blender's native Object Type Visibility dropdown can restore Empties.
view.show_object_viewport_empty = True
another.show_object_viewport_empty = True
img = NS(type="EMPTY", empty_display_type="IMAGE", modifiers=[],
         hide_render=False, hide_viewport=False)
fast_bpy.context.scene.objects = helpers + [img, mesh_child]
assert fast() == 0 and view.show_object_viewport_empty
fast_bpy.context.scene.objects = helpers + [mesh_child]
helpers[0].modifiers = [NS(type="NODES")]
assert fast() == 0 and another.show_object_viewport_empty
helpers[0].modifiers = []
assert fast() == 2
assert view.show_object_viewport_mesh

# Only the fresh import enables this viewport-only filter. Existing blend
# optimization must preserve users' custom Empty visibility preferences.
fn_by_name = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
calls = lambda name: [n for n in ast.walk(fn_by_name[name])
                      if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                      and n.func.id == "avoid_drawing_unused_import_empties"]
assert len(calls("main")) == 1
assert calls("optimize_existing_blend") == []

print("USD transform crosshairs hidden, geometry, parenting and viewport-only Empty visibility checked.")

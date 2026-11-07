"""Verify viewport FPS optimizations: chunk outline suppression and empty modifier pointcloud skipping."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS

source = Path("assets/Import_Existing_USD.py").read_text(encoding="utf-8")
tree = ast.parse(source)

# 1. Extract functions
funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
assert "avoid_drawing_chunk_outlines" in funcs, "avoid_drawing_chunk_outlines must be defined"
assert "avoid_evaluating_empty_pointclouds" in funcs, "avoid_evaluating_empty_pointclouds must be defined"

events = []
scope = {
    "log": lambda *parts: events.append(parts),
    "sum": sum,
    "hasattr": hasattr,
    "getattr": getattr,
    "len": len,
}
mod = ast.Module(body=[funcs["avoid_drawing_chunk_outlines"], funcs["avoid_evaluating_empty_pointclouds"]], type_ignores=[])
exec(compile(mod, "<viewport_fps_opts>", "exec"), scope)

avoid_outlines = scope["avoid_drawing_chunk_outlines"]
avoid_pointclouds = scope["avoid_evaluating_empty_pointclouds"]


# Test 1: avoid_drawing_chunk_outlines
def make_view(outline=True):
    return NS(type="VIEW_3D", shading=NS(show_object_outline=outline))


other_space = NS(type="IMAGE_EDITOR")
screen = NS(areas=[NS(spaces=[make_view(True), other_space]), NS(spaces=[make_view(True)])])
mock_bpy = NS(data=NS(screens=[screen]), context=NS(scene=NS(objects=[])))
scope["bpy"] = mock_bpy

# Boundary: fewer than 128 meshes -> outlines untouched
mock_bpy.context.scene.objects = [NS(type="MESH") for _ in range(127)]
assert avoid_outlines() == 0
assert screen.areas[0].spaces[0].shading.show_object_outline
assert screen.areas[1].spaces[0].shading.show_object_outline

# Boundary: exactly 128 meshes -> outlines disabled across 3D views
mock_bpy.context.scene.objects.append(NS(type="MESH"))
assert len(mock_bpy.context.scene.objects) == 128
assert avoid_outlines() == 2
assert not screen.areas[0].spaces[0].shading.show_object_outline
assert not screen.areas[1].spaces[0].shading.show_object_outline

# Idempotent: re-calling returns 0
assert avoid_outlines() == 0

# Handles missing shading or attribute gracefully
broken_space = NS(type="VIEW_3D")
screen2 = NS(areas=[NS(spaces=[broken_space])])
mock_bpy.data.screens.append(screen2)
assert avoid_outlines() == 0


# Test 2: avoid_evaluating_empty_pointclouds
def make_pc(points=0, modifiers=0, children=0, hide_viewport=False):
    return NS(
        type="POINTCLOUD",
        data=NS(points=list(range(points))),
        modifiers=[NS(type="NODES") for _ in range(modifiers)],
        children=[NS(type="MESH") for _ in range(children)],
        hide_viewport=hide_viewport,
        hide_render=False,
    )


# Object variations:
empty_with_mod = make_pc(points=0, modifiers=1, children=0)
has_points_with_mod = make_pc(points=10, modifiers=1, children=0)
empty_no_mod = make_pc(points=0, modifiers=0, children=0)
empty_with_children = make_pc(points=0, modifiers=1, children=1)
already_hidden = make_pc(points=0, modifiers=1, children=0, hide_viewport=True)
mesh_obj = NS(type="MESH", data=NS(points=[]), modifiers=[1], children=[], hide_viewport=False, hide_render=False)
empty_obj = NS(type="EMPTY", modifiers=[1], children=[], hide_viewport=False, hide_render=False)

mock_bpy.context.scene.objects = [
    empty_with_mod,
    has_points_with_mod,
    empty_no_mod,
    empty_with_children,
    already_hidden,
    mesh_obj,
    empty_obj,
]

assert avoid_pointclouds() == 1
assert empty_with_mod.hide_viewport is True
assert empty_with_mod.hide_render is False, "Render visibility must remain untouched"
assert has_points_with_mod.hide_viewport is False, "Point clouds with points must stay visible"
assert empty_no_mod.hide_viewport is False, "Point clouds without modifiers must stay visible"
assert empty_with_children.hide_viewport is False, "Point clouds with children must not be hidden"
assert mesh_obj.hide_viewport is False, "Non-pointcloud objects must stay visible"
assert empty_obj.hide_viewport is False, "Non-pointcloud objects must stay visible"

# Idempotent: re-calling returns 0
assert avoid_pointclouds() == 0


# Test 3: main() must call both optimizations
calls = lambda name, target: [n for n in ast.walk(funcs[name])
                              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                              and n.func.id == target]

assert len(calls("main", "avoid_drawing_chunk_outlines")) == 1
assert len(calls("main", "avoid_evaluating_empty_pointclouds")) == 1

print("Viewport FPS optimizations (outline suppression and empty pointcloud modifier skipping) verified.")

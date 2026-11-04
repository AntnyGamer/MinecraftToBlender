"""Regression-test the optional performance mode against mock Blender viewports."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS

source = Path("assets/Import_Existing_USD.py").read_text(encoding="utf-8")
module = ast.parse(source)
names = {"configure_fast_viewport", "import_world"}
funcs = [node for node in module.body
         if isinstance(node, ast.FunctionDef) and node.name in names]
assert len(funcs) == 2
records = []
import_calls = []
unchanged_material = object()
unchanged_mesh = object()


def viewport():
    shading = NS(type="MATERIAL", color_type="MATERIAL", light="STUDIO",
                 show_cavity=True, show_shadows=True, show_specular_highlight=True,
                 use_dof=True)
    overlay = NS(show_extras=True, show_relationship_lines=True)
    space = NS(shading=shading, overlay=overlay)
    area = NS(type="VIEW_3D", spaces=NS(active=space))
    return area, space


area, space = viewport()
other_area = NS(type="IMAGE_EDITOR", spaces=NS(active=NS()))
screen = NS(areas=[area, other_area])
bpy = NS(
    data=NS(screens=[screen], materials=[unchanged_material], meshes=[unchanged_mesh]),
    ops=NS(
        mieximport=NS(world=lambda **kwargs: (import_calls.append(kwargs), {"FINISHED"})[1]),
    ),
)
scope = {
    "bpy": bpy,
    "log": lambda *args: records.append(args),
    "time": NS(monotonic=lambda: 0),
    "Usd": NS(Stage=NS(SetGlobalVariantFallbacks=lambda *_: None)),
    "clear_objects": lambda: None,
    "scene_report": lambda: {"meshes": 5},
}
exec(compile(ast.Module(body=funcs, type_ignores=[]), "<viewport-test>", "exec"), scope)
assert scope["configure_fast_viewport"]() == 1
assert space.shading.type == "SOLID"
assert space.shading.color_type == "TEXTURE"
assert space.shading.light == "STUDIO"
assert space.shading.show_cavity is False
assert space.shading.show_shadows is False
assert space.shading.show_specular_highlight is False
assert space.shading.use_dof is False
assert space.overlay.show_extras is False
assert space.overlay.show_relationship_lines is True  # selection overlays retained
assert bpy.data.materials == [unchanged_material]
assert bpy.data.meshes == [unchanged_mesh]

scope["import_world"]("World.usd", "render", fast_viewport=True)
scope["import_world"]("World.usd", "render", fast_viewport=False)
assert import_calls[0]["hide_background"] == "hide"
assert import_calls[1]["hide_background"] == "show"
assert all(x["import_type"] == "render" and x["flatten"] is False for x in import_calls)
assert all(x["max_animation_frames"] == 1 for x in import_calls)

# Ensure both command-line flags can be passed independently or together.
main = next(node for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == "main")
string_values = {value.value for value in ast.walk(main)
                 if isinstance(value, ast.Constant) and isinstance(value.value, str)}
assert "--fast-viewport" in string_values
assert "--minecraft-water" in string_values
assert "SOLID" in {value.value for value in ast.walk(funcs[0])
                   if isinstance(value, ast.Constant) and isinstance(value.value, str)}
print("Fast viewport preserves geometry, materials, and render-time background objects.")

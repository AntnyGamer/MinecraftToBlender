"""Verify Minecraft-like preview only changes display preferences, not scene data."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS


tree = ast.parse(Path("assets/Import_Existing_USD.py").read_text(encoding="utf-8"))
fn = next(f for f in tree.body
          if isinstance(f, ast.FunctionDef) and f.name == "apply_minecraft_texture_preview")
code = compile(ast.Module(body=[fn], type_ignores=[]), "<minecraft-preview>", "exec")
messages = []


def viewport(mode, color_type):
    return NS(type="VIEW_3D", shading=NS(type=mode, color_type=color_type))


solid = viewport("SOLID", "MATERIAL")
material = viewport("MATERIAL", "MATERIAL")
camera = NS(type="IMAGE_EDITOR")
scene = NS(view_settings=NS(view_transform="AgX"), objects=[object()], world=object())
screens = [
    NS(areas=[NS(spaces=[solid, camera])]),
    NS(areas=[NS(spaces=[material])]),
]
bpy = NS(context=NS(scene=scene), data=NS(screens=screens))
ns = {"bpy": bpy, "log": lambda *args: messages.append(args)}
exec(code, ns)
original_objects = scene.objects
original_world = scene.world

assert ns["apply_minecraft_texture_preview"]() == 1
assert scene.view_settings.view_transform == "Standard"
assert solid.shading.type == "SOLID"
assert solid.shading.color_type == "TEXTURE"
assert material.shading.type == "MATERIAL"
assert material.shading.color_type == "MATERIAL"
assert camera.type == "IMAGE_EDITOR"
assert scene.objects is original_objects
assert scene.world is original_world

# Reapplying the optional preference must be safe and repeatable.
assert ns["apply_minecraft_texture_preview"]() == 1
assert solid.shading.color_type == "TEXTURE"

# These flags enable the preview through the existing EXE/import helper;
# no new user-run Blender script, migration, or extra mesh is introduced.
source = Path("assets/Import_Existing_USD.py").read_text(encoding="utf-8")
assert "'--minecraft-view' in flags" in source
assert "if minecraft_view:" in source
assert "apply_minecraft_texture_preview()" in source
assert "'--minecraft-view'" in source
print("Minecraft viewport colors and Solid textures are opt-in; material/geometry/shading modes unchanged.")

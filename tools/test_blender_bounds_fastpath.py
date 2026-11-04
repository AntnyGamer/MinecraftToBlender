"""Exercise Blender bounds fast path without importing bpy outside Blender."""
import ast
from pathlib import Path
from types import SimpleNamespace

source = Path("assets/Import_Existing_USD.py").read_text(encoding="utf-8")
tree = ast.parse(source)
func = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
            and n.name == "needs_evaluated_bounds")
module = ast.Module(body=[func], type_ignores=[])
scope = {}
exec(compile(module, "<bounds-check>", "exec"), scope)
need = scope["needs_evaluated_bounds"]

def obj(typ="MESH", instance="NONE", modifiers=(), points=()):
    return SimpleNamespace(type=typ, instance_type=instance,
                           modifiers=modifiers, data=SimpleNamespace(points=points))

assert not need(obj()), "static terrain meshes should skip the extra dependency graph walk"
assert not need(obj(typ="POINTCLOUD")), "empty point cloud should not force evaluation"
assert need(obj(modifiers=["geometry nodes"])), "modified terrain requires evaluated bounds"
assert need(obj(instance="COLLECTION")), "collection instance bounds require evaluated instances"
assert need(obj(typ="POINTCLOUD", points=[1])), "nonempty point cloud must retain evaluation"
frame = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
             and n.name == "frame_actual_scene")
assert any(isinstance(n, ast.If) and isinstance(n.test, ast.Name)
           and n.test.id == "evaluate_instances" for n in ast.walk(frame))
main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
assert any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
           and n.func.id == "frame_actual_scene" and n.args
           for n in ast.walk(main))
print("Blender bounds fast-path tests passed.")

"""Check the EXE's existing-.blend optimization path without importing Blender."""
import ast
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace as NS

source = Path("assets/Import_Existing_USD.py").read_text(encoding="utf-8")
tree = ast.parse(source)
function = next(node for node in tree.body
                if isinstance(node, ast.FunctionDef)
                and node.name == "optimize_existing_blend")

with tempfile.TemporaryDirectory() as folder:
    directory = Path(folder)
    original = directory / "MyWorld.blend"
    original.write_bytes(b"untouched original world")
    output = directory / "MyWorld_2.blend"

    mesh = NS(type="MESH", data=NS(polygons=[0, 1, 2, 3]))
    selections = []
    operations = []
    def save_mainfile(filepath, compress):
        assert not compress
        assert str(output) == filepath
        operations.append("save")
        Path(filepath).write_bytes(b"optimized test output")

    bpy = NS(
        data=NS(filepath=str(original)),
        context=NS(scene=NS(objects=[mesh])),
        ops=NS(wm=NS(save_as_mainfile=save_mainfile)),
        app=NS(version_string="5.2.3"),
    )
    def batch():
        operations.append("batch")
        return 0
    def dedup():
        operations.append("dedup")
        return 2
    def clear():
        operations.append("clear")
        return 0
    scope = {
        "bpy": bpy,
        "Path": Path,
        "time": time,
        "log": lambda *parts: None,
        "clear_bulk_import_selection": clear,
        "batch_static_terrain_meshes": batch,
        "deduplicate_exact_material_slots": dedup,
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]),
                 "<optimize>", "exec"), scope)
    optimize = scope["optimize_existing_blend"]

    optimize(output)
    assert original.read_bytes() == b"untouched original world"
    assert output.read_bytes() == b"optimized test output"
    assert operations == ["clear", "dedup", "save"]
    assert len(mesh.data.polygons) == 4

    # Optimizing compressed projects should retain their original save format,
    # avoiding unexpectedly huge expanded .blend files.
    output.unlink()
    original.write_bytes(bytes((0x1f, 0x8b)) + b"synthetic compressed blend")
    compress_modes = []
    def save_compressed(filepath, compress):
        compress_modes.append(compress)
        Path(filepath).write_bytes(b"new project")
    bpy.ops.wm.save_as_mainfile = save_compressed
    optimize(output)
    assert compress_modes == [True]
    assert original.read_bytes().startswith(bytes((0x1f, 0x8b)))

    # Blender 3+ saves compressed projects using Zstandard, not gzip.
    output.unlink()
    original.write_bytes(bytes((0x28, 0xb5, 0x2f, 0xfd)) + b"synthetic zstd blend")
    compress_modes.clear()
    optimize(output)
    assert compress_modes == [True]
    assert original.read_bytes().startswith(bytes((0x28, 0xb5, 0x2f, 0xfd)))

    # Never overwrite a previously saved output or original file.
    for existing in (original, output):
        try:
            optimize(existing)
            raise AssertionError("Overwriting an existing .blend must be rejected")
        except RuntimeError as err:
            assert "never overwrite" in str(err)

    output.unlink()
    operations.clear()
    original.write_bytes(b"untouched original world")
    bpy.ops.wm.save_as_mainfile = save_mainfile
    optimize(output, batch_meshes=True)
    assert operations == ["clear", "batch", "dedup", "save"]
    assert original.read_bytes() == b"untouched original world"

    # Reject non-terrain scenes instead of reporting a false performance win.
    bpy.context.scene.objects = []
    output.unlink()
    try:
        optimize(output)
        raise AssertionError("Empty scenes must be rejected")
    except RuntimeError as err:
        assert "no terrain mesh" in str(err)
    assert not output.exists()

assert source.count("def optimize_existing_blend(") == 1
assert "'--optimize-blend' in arguments" in source
print("Existing Blender optimization saves a separate copy and preserves the original.")

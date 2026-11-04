"""Apply the PR's Blender-side cleanups to an already exported .blend.

In Blender 5.2+, open an exported world, switch to Scripting, open this file in
the Text Editor, and choose Run Script. The original .blend is NOT overwritten.
Review the result, then use File > Save As to preserve the original.

By default this only removes exact duplicate material datablock slots and
clears excessive initial mesh selection. To opt into joining small groups of
compatible static terrain objects, change BATCH_STATIC_TERRAIN to True.
Batching can reduce object overhead but changes individual mesh editability,
may hurt object-level culling, and needs testing on a real world.
"""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import bpy


BATCH_STATIC_TERRAIN = False


def optimize_open_blend(batch=BATCH_STATIC_TERRAIN):
    # External Text Editor scripts and runpy.run_path supply __file__. A
    # Blender Text datablock may not, so fall back to its source filepath.
    script_file = globals().get("__file__", "")
    script_path = Path(script_file) if script_file else None
    if script_path is None or not script_path.is_file():
        text = getattr(bpy.context, "edit_text", None)
        if text is None:
            text = getattr(getattr(bpy.context, "space_data", None), "text", None)
        text_path = getattr(text, "filepath", "")
        script_path = Path(bpy.path.abspath(text_path)) if text_path else None
    if script_path is None or not script_path.is_file():
        raise RuntimeError(
            "Open Optimize_Existing_Blend.py from disk in Blender's Text Editor "
            "or execute it using runpy.run_path with its full file path."
        )
    source = script_path.resolve().with_name("Import_Existing_USD.py")
    if not source.is_file():
        raise FileNotFoundError(f"Blender helper is missing beside this script: {source}")

    spec = spec_from_file_location("m2b_blender_import_helpers", source)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load the existing Blender import helpers")
    helpers = module_from_spec(spec)
    spec.loader.exec_module(helpers)

    def scene_counts():
        meshes = tuple(o for o in bpy.context.scene.objects if o.type == "MESH")
        return len(meshes), sum(len(o.data.polygons) for o in meshes)

    before = scene_counts()
    selected = helpers.clear_bulk_import_selection()
    merged = helpers.batch_static_terrain_meshes() if batch else 0
    # A Join operation can create fresh repeated material slots.
    duplicates = helpers.deduplicate_exact_material_slots()
    after = scene_counts()
    if before[1] != after[1]:
        raise RuntimeError(
            f"Unexpected polygon count change: {before[1]} -> {after[1]}. "
            "The existing .blend on disk has NOT been overwritten."
        )
    print(
        "EXISTING BLEND OPTIMIZATION:",
        f"objects {before[0]} -> {after[0]};",
        f"faces {before[1]} -> {after[1]};",
        f"duplicate slots removed {duplicates};",
        f"selected meshes cleared {selected};",
        f"terrain objects joined {merged}.",
        flush=True,
    )
    print(
        "No file was saved. Check the Blender viewport and use File > Save As "
        "if you want to keep the result without replacing the original.",
        flush=True,
    )
    return {
        "mesh_objects_before": before[0],
        "mesh_objects_after": after[0],
        "polygon_count": after[1],
        "duplicate_slots": duplicates,
        "cleared_selection": selected,
        "joined_objects": merged,
    }


if __name__ == "__main__":
    optimize_open_blend()

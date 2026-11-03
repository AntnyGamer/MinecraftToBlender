# MinecraftToBlender v1.0.6

## Bedrock model and texture fixes

- **Beds:** Read Bedrock-native dye color, bed-half, and direction values when present. When world resource packs are disabled, use verified vanilla Bedrock bed texture assets from Mojang's pinned bedrock-samples revision as a fallback instead of relying on Java-edition bed images. Images are fetched on the user's PC and never bundled in the EXE. Cached verified downloads are reused; a failed download falls back to installed resources rather than blocking the export. Any verified fallback assets from an earlier export are cleaned up before Java exports or exports using custom world packs, without deleting modified files.
- **Shulker boxes:** Use Bedrock's numeric `facing_direction` when present, instead of relying solely on potentially mismatched translated direction labels.
- **Signs and hanging signs:** Restore an older Bedrock sign text representation (`Text`) when `FrontText` is absent, preserving modern Bedrock formats as-is.
- **Banners and generated entity textures:** Store MiEx-generated images with the USD export so Blender does not depend on out-of-folder generated images that may be deleted or moved.
- **Texture diagnostics:** Generate a `<project>_texture_audit.txt` alongside each imported .blend, listing missing external image files and unreadable-image placeholders without silently altering materials.

## Processing efficiency (no mesh simplification)

- Buffer EXE child-process log writes during verbose Minecraft conversions, preserving every output line in the saved log.
- Bound the EXE's UI status checks to the already-displayed log excerpt instead of lowercasing multi-megabyte MiEx responses.
- Count Blender scene meshes, faces, vertices, and point clouds in one traversal, without temporary mesh/cloud object lists.
- When exporting directly into Blender, reuse the freshly validated USD so the large materials JSON and chunk directory are not parsed twice. Manual USD imports still run complete validation.
- Reuse up to 512 sets of local bounding-box corners for repeated geometry instances while framing the scene. Mesh data, material nodes, and viewport bounds are not intentionally altered.
- Add Windows full-output logging tests and Python regression tests for scene counts and viewport framing.
- Reuse the USD chunk list already collected during export when checking real terrain faces, avoiding a second recursive folder walk.
- Validate large folders of USD layers in 128-entry batches instead of loading and sorting the entire directory when one valid layer is sufficient.
- Check materials JSON for validity without allocating per-material copies, while preserving detailed errors for corrupt files.
- Resolve shader nodes by Blender's named collection lookup instead of repeatedly iterating each material graph's entire node list. Keep the same node-name clipping and missing-node behavior.
- Avoid constructing unused subpaths during USD grouping and unused suffixes while checking Blender prototype names.
- Add tests for material lookup, USD geometry grouping, material JSON validation, and large chunk directories.

Bedrock-only model overrides are cleaned up when exporting a Java world in the same workspace. The existing source worlds, Blender auto-open setting, source resource-pack choice, geometry optimizations, and export-region borders are unchanged.

**Verification required:** This release is prepared in a PR, not published. A Windows CI build and a real Bedrock-world export with known beds, signs, banners, and shulker boxes are required before claiming the reported visual problems are fully solved.

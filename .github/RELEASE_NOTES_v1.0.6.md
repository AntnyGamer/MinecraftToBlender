# MinecraftToBlender v1.0.6

## Bedrock model and texture fixes

- **Beds:** Read Bedrock-native dye color, bed-half, and direction values when present. When world resource packs are disabled, use verified vanilla Bedrock bed texture assets from Mojang's pinned bedrock-samples revision as a fallback instead of relying on Java-edition bed images. Images are fetched on the user's PC and never bundled in the EXE. Cached verified downloads are reused; a failed download falls back to installed resources rather than blocking the export.
- **Shulker boxes:** Use Bedrock's numeric `facing_direction` when present, instead of relying solely on potentially mismatched translated direction labels.
- **Signs and hanging signs:** Restore an older Bedrock sign text representation (`Text`) when `FrontText` is absent, preserving modern Bedrock formats as-is.
- **Banners and generated entity textures:** Store MiEx-generated images with the USD export so Blender does not depend on out-of-folder generated images that may be deleted or moved.
- **Texture diagnostics:** Generate a `<project>_texture_audit.txt` alongside each imported .blend, listing missing external image files and unreadable-image placeholders without silently altering materials.

Bedrock-only model overrides are cleaned up when exporting a Java world in the same workspace. The existing source worlds, Blender auto-open setting, source resource-pack choice, geometry optimizations, and export-region borders are unchanged.

**Verification required:** This release is prepared in a PR, not published. A Windows CI build and a real Bedrock-world export with known beds, signs, banners, and shulker boxes are required before claiming the reported visual problems are fully solved.

# MinecraftToBlender v1.0.1

Small Blender viewport presentation fix for the v1 Windows release.

- **Relationship Lines are hidden by default** in every 3D Viewport stored in new Blender `.blend` projects generated through the EXE's import workflow, so parent/constraint guides no longer shoot across the imported scene.
- Door geometry, parenting, constraints, Minecraft block data, USD geometry, materials, and export quality are unchanged.
- Added Python syntax validation to the Windows build.
- Windows EXE and SHA-256 checksum are included.

The setting is applied when the app **imports and saves a Blender project** (including Export + Import). It is not embedded in export-only USD files and does not change Blender's global preferences or existing saved `.blend` files.

The missing-terrain workaround from v1.0.0 remains included. Minecraft-world visual fidelity has not been certified for every block or Bedrock version.

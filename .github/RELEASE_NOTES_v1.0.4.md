# MinecraftToBlender v1.0.4

- Restore actual stone, deepslate and other terrain faces along the sides and bottom of a selected export region, using MiEx's built-in world-boundary face handling. Real caves and openings remain intact.
- Automatically open a finished `.blend` project in Blender after **Export to Blender** or **Create Blender project** succeeds.
- Add a **Settings → Auto-open Blender** option, on by default. Its on/off state is saved between launches. Disable it to create the `.blend` without launching Blender; use **Open project** whenever you want to open it manually.
- Keep **USD only** as an export-only operation: it never starts Blender.
- Keep existing `.blend` projects and numbered Blender backups when re-exporting a world with the same name; only the previous generated USD data is replaced.
- Correct negative fractional player coordinates to their proper Minecraft block coordinates.
- Reduce world-picker repaint work to visible rows, particularly useful for large world libraries.
- Update the release workflow to publish a new v1.0.4 EXE instead of silently skipping an existing v1.0.3 release.

**Note:** These fixes affect new exports and imports. Existing `.blend` files do not regenerate terrain automatically. Minecraft-to-Blender visual fidelity still depends on MiEx and the source save; check scenes after exporting.

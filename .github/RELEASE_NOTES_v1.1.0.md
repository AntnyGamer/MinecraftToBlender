# MinecraftToBlender v1.1.0

This release adds a new **Export options** tab and completes the version display across the app and Windows executable properties.

## New features
- **Region preview:** generates a clickable top-down image from MiEx's real chunk-color samples. Smaller regions are drawn at their actual block positions; larger regions use up to 256 sampled chunk locations and are approximate. Empty or unavailable areas stay gray, and invalid MiEx responses are reported.
- **Pre-export readiness:** check the selected world's Java dimension, saved chunk availability, Java 21+, Blender version, available and installed RAM, workspace free space, and height range. Routine warnings avoid lengthy checks on the UI thread; detailed checks are cancellable.
- **Dimension selection:** choose Overworld, Nether, or End for supported Java and Bedrock worlds.
- **Export progress:** show actual operation stage, elapsed time, and periodic MiEx Java memory readings rather than estimating an unreliable percent complete.
- **Entity selection:** independently include or exclude item frames (including glow frames), paintings, armor stands, and display entities. Existing supported entity types remain enabled by default.
- **Optional safe resume:** after a *complete* successful USD export, opt in to SHA-256 checkpointing so a failed Blender import can be retried without re-exporting if world and USD inputs are unchanged. Disabled by default to avoid additional disk I/O.

## Reliability, safety, and cleanup
- Display **VERSION 1.1.0** in the UI and **Minecraft to Blender v1.1.0** in the window title, with matching **1.1.0.0** Windows EXE file/product properties. Tests check for version consistency.
- Verify that the main USD references existing, nonempty terrain chunk layers before replacing the previously completed export. Reject orphaned or missing terrain roots.
- Handle invalid/transparent preview data, empty regions, repeated previews, preview window lifetime, and world changes between preview and selection.
- Protect the original Minecraft save from overlapping workspaces, including Windows junctions and directory aliases.
- Make long file scans cancelable and present intentional cancellation without an export-failure alert.
- Keep verified resume checkpoints valid when Blender leaves import logs or .blend projects; still invalidate them when world, USD, materials, textures, or chunk files change.
- Remove unused prototype optimizer, a test-only Java region wrapper, and duplicate audit-report text.
- Reduce redundant GitHub Actions builds for superseded commits.

## Known limitations and testing
- **MiEx chunk-by-chunk recovery is not implemented.** Safe resume starts only after a fully completed and verified USD export; never combine partial MiEx output.
- A preview of a large region is **sampled**, not a complete map; previews and supported entities may vary with Java/Bedrock save and MiEx version.
- GitHub Actions exercises unit and regression tests, Python tools, PowerShell checks, and builds the Windows x64 EXE. A complete real Minecraft world export, GUI preview interaction, and detailed Blender texture/model accuracy have **not** been independently validated on the target world.
- Windows 10/11 x64, Java 21+, and Blender for auto-import are required; initial MiEx and asset installation needs internet access.

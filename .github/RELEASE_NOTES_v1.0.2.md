# Release 1.0.2

Download **MinecraftToBlender_v1.exe** below. This release introduces substantial Blender viewport performance improvements, eliminates helper crosshair visual artifacts, corrects Bedrock sign text and redstone depth fighting, and ensures reliable cold-start region previews.

**For block-model, color, sign-text, and world-data fixes, make a fresh Minecraft export.** Reopening an old USD cannot recover data omitted during its original export. Your Minecraft saves and existing Blender projects remain untouched.

## Viewport FPS optimizations (zero downside)

- **Large-world Empty helper draw suppression:** On fresh imports with 128+ plain axes Empties, Blender's native `Object Type Visibility -> Empties` is automatically toggled off for all 3D viewports. Thousands of non-geometry helper markers are bypassed during viewport rendering, reducing draw calls without altering mesh objects, parent transforms, renders, or scene coordinates.
- **Chunk-outline viewport suppression:** Disables viewport silhouette edge drawing (`show_object_outline = False`) for large scenes (128+ chunk meshes) on fresh imports, existing `.blend` optimizations, and block texture preview. Eliminates heavy silhouette edge calculations every frame and removes dark seams between adjacent chunks. Reversible at any time via **Viewport Shading -> Outline**.
- **Empty point-cloud modifier evaluation skipping:** Chunk `animated_blocks` point clouds with 0 points are hidden from viewport evaluation (`hide_viewport = True`, `modifier.show_viewport = False`), bypassing unnecessary Geometry Nodes dependency graph updates every frame.
- **Fast-path camera framing bounds:** Caches prototype bounds for instanced scenes and bypasses dependency graph traversal for viewport-hidden and modifier-disabled objects during scene camera framing.
- **USD import acceleration:** Non-throwing shader socket parsing, deduplicated material `diffuse_color` updates, and cached prototype parent classifications speed up the USD-to-Blender import process.

## Visual and accuracy fixes

- **Door and window marker suppression:** Plain Axes Empty helper markers are scaled to Blender's minimum display size (`0.0001`), preventing black crosshairs from displaying across doors, windows, and custom models in both fresh imports and optimized copies of existing `.blend` files.
- **Bedrock sign text line boundaries:** Uses native MiEx `minecraft:default` font metrics and vanilla character limits (`90` font pixels for standing/wall signs, `60` font pixels for hanging signs) instead of character counts. Preserves original font sizes, formatting codes, and multi-line layouts without text clipping or board overflow. Rebuilt Bedrock chunk reader is pinned and verified.
- **Bedrock redstone corner plane separation:** Intersecting planar variants and overlays at redstone corners are assigned distinct depth offsets, preventing coplanar z-fighting and black visual artifacts when redstone turns corners.
- **Cold-start preview batch replay:** The region preview automatically detects and retries cold-start MiEx batch misses, ensuring full rectangular chunk coverage and preventing missing northern preview rows.

## Validation and limits

GitHub Actions tests Go, Python, PowerShell, Windows executable metadata, pinned MiEx regressions, and model generation before publishing. The release workflow verifies the packaged EXE against **SHA256SUMS.txt** before making the release public.

Large-world Blender viewport FPS improvements are **not guaranteed**. Viewing performance depends heavily on scene geometry, shader complexity, and your GPU hardware.

Requires **Windows 10/11 (64-bit)**, **Java 21+**, and a supported Blender installation. The app downloads pinned MiEx/resource dependencies when required.

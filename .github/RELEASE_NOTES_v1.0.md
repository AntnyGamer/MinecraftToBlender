# Release 1.0

MinecraftToBlender is a Windows application for exporting local Minecraft Bedrock and Java Edition worlds through MiEx and opening the resulting USD worlds in Blender.

## Export and model features
- Discover Bedrock and Java worlds, their available world thumbnails and save timestamps; choose export dimensions, region size, coordinates, and Y range.
- Read-only source-world snapshot; full-detail USD export with MiEx face optimization, preserved complete output on failed replacements, export diagnostics, and a world preview.
- Minecraft Bedrock-specific bed UVs and validated vanilla Bedrock textures, shulker-box models and official texture atlases, hanging signs, banners, and item-frame fallbacks.
- Support world resource packs, selected entities, safe completed-export resume, and optional Blender import.

## Blender
- USD scene checks distinguish solid terrain meshes from empty point-instancer prototypes.
- Rebuild Minecraft textures and materials through the pinned official MiEx Blender importer, with optimizations for material node lookup/layout and deterministic image loading.
- Frame the imported world near terrain rather than starting far from the scene.
- Optional water rendering, block-texture viewport preview, and bounded mesh batching; each remains off by default because of real rendering or editability tradeoffs.
- Existing .blend optimization writes a separate project copy, retaining the original file.

## Importer crash fix
- A previous importer guard expected an entirely empty line between the pinned MiEx `getNode` methods, but the official Python source contains a whitespace-only indented line. Normalize whitespace-only lines **in memory** before checking the same exact code anchors. Never overwrite the installed official addon.
- CI now patches and compiles the **complete official MiExImport.py from its pinned upstream commit**, tests both blank-line forms, and rejects actual code changes.

## Runtime
- Memory status distinguishes Java JVM private committed memory from resident physical memory, and shows a measured JVM PID instead of presenting a small Java launcher's 10 MiB working set as the full heap.
- The model exporter is not Minecraft's renderer. Some unusual game-version or modded assets may still require visual verification in Blender. No source world is modified.

No additional settings, older-app-version migrations, or separately operated programs are required for the importer fix.

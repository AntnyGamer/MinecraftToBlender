# Release 1.0

Download **MinecraftToBlender_v1.exe** below. This replacement includes the merged Bedrock accuracy, Blender memory and region-preview fixes. Make a **fresh Bedrock export** to recover colors, patterns and entity data omitted by earlier builds.

This remains **Release 1.0** (application version 1.0.0). Its new `release-1.0-*` tag is required because GitHub permanently reserves the old immutable release tag after deletion.

## Minecraft accuracy

- Restore Bedrock bed colors, banner patterns, item-frame data, shulker facing and legacy sign text. Use matching Bedrock bed/shulker texture atlases and retain vanilla fallbacks beneath partial world resource packs.
- Export decorated pots and vanilla pottery patterns, active/inactive conduits, dragon/piglin heads and enchanting-table books. Preserve flower-pot contents, skull types and rotation, including the correct wither-skeleton texture.
- Retain armor-stand equipment, leather dye, small size and all 13 Bedrock pose presets. Remove coincident reversed armor faces that caused dark artifacts.
- Honor the world resource-pack toggle and apply Minecraft-style water and block-texture viewport options correctly. Block texture view uses textured Solid navigation; full material transparency and biome tint require material shading.
- Retain the pinned MiEx importer crash fix and fail clearly when a required generated texture is missing.

## Performance and previews

- Optional static-mesh batching reduces object overhead and removes exact unused copies of shading normals and unreferenced USD preview colors, while preserving geometry and actual biome tints. Existing Blender projects can be optimized into a separate copy.
- Request preview images in sequential groups of at most 64, retaining every requested position and its original pixels. Report incremental progress, warn on idle output and count the final response after Java exits.
- Reject a failed preview batch even if earlier batches succeeded, instead of displaying an incomplete map as a successful preview.
- Preserve source saves, existing Blender projects and the previous completed export when a replacement fails. Older export checkpoints cannot bypass the corrected pipeline.

## Validation and limits

- Windows/Linux automated checks cover Go tests/vet, PowerShell, Blender helpers and the actual pinned MiEx evaluator. CI reproduces the Bedrock reader overlay and all nine detail model definitions from pinned sources.
- A copied-world 256×256 export imported and rendered in Blender 5.2.3 with zero missing external images across 363 checked. Batched and unbatched previews returned identical image data and metadata for 128 chunks.
- A tested 11,303,330-face Blender scene retained every face and vertex while reducing mesh objects from 3,120 to 2,865 and its saved size from 3.37 GB to 2.25 GB. These are object/memory reductions; a new full-scene Material Preview FPS result has not been measured.
- Enchanting books and conduit effects use static poses. Arbitrary add-on pottery patterns, custom entities and every resource pack are not covered. The exporter approximates Minecraft rendering; unusual assets still need visual checking.

Java 21+ is required. MiEx and Minecraft texture resources are installed on demand. The release is built from the tagged source only after all build checks pass; uploaded files are downloaded again and verified against **SHA256SUMS.txt** before publication.

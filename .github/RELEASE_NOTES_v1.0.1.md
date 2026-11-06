# Release 1.0.1

Download **MinecraftToBlender_v1.exe** below. This release improves the accuracy of Java and Bedrock exports, Blender imports, and region previews, with targeted performance and memory reductions.

**For block-model, color, item-frame, and other world-data fixes, make a fresh Minecraft export.** Reopening an old USD cannot recover data its original export omitted. Your Minecraft saves and existing Blender projects remain untouched.

## Export and visual fixes

- Restore additional Java copper chest and statue variants, conduits, decorated pots, enchanting books, dragon/piglin heads, and all sixteen bed-color atlases.
- Improve Bedrock beds, colored and undyed shulker boxes, banners, item frames, signs, bells, pistons, copper chests, redstone connections, and standing copper statue geometry.
- Preserve world-specific textures, existing custom assets, and Java/Bedrock resource-pack isolation. Repair missing End portal and gateway geometry and use a verified static portal texture fallback; corrupt cached PNGs are rejected rather than silently reused.
- **Block texture view** now opens Blender in Material Preview to display shader-based textures, biome tint, and transparency. This may be slower than Solid mode for large scenes. Minecraft water/portal effects are approximations, not the game's renderer.

## Performance and reliability

- Improve Blender importer node lookups, shader layout, scene-bound framing, duplicate material-slot handling, and selection cleanup without discarding world geometry.
- Repair optional lossless USD Crate compaction when the external prototype-sharing helper is unavailable. Compaction is opt-in and changes USD storage, not face counts.
- Improve region preview layout, hover coordinates, first/last-row coverage, cache invalidation, and incomplete-response detection.
- For very large previews, retain averaged chunk colors instead of all full BGRA tiles, reuse Base64 decoding memory, and paint directly into the output pixel buffer. This saves temporary memory and per-pixel overhead without intentionally changing sampled colors.
- Keep optional mesh batching and attribute compaction opt-in; those choices can affect object editability, culling, or accessible mesh attributes.

## Validation and limits

GitHub Actions tests Go, Python, PowerShell, Windows executable metadata, pinned MiEx regressions, and model generation before publishing. The release workflow verifies the packaged EXE against **SHA256SUMS.txt** before making the release public.

Large-world Blender viewport FPS improvements are **not guaranteed**. The northern gray preview band, non-standing Bedrock copper statue poses, and unusual texture packs may still need real-world visual validation.

Requires **Windows 10/11 (64-bit)**, **Java 21+**, and a supported Blender installation. The app downloads pinned MiEx/resource dependencies when required.

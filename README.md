# MinecraftToBlender

<p align="center"><img src="branding/logo.svg" alt="MinecraftToBlender logo" width="112" height="112"></p>

**Version:** v1.0  
**Platform:** Windows 10/11 (64-bit)  
**Languages:** Go (Win32 interface), PowerShell, Python

A Windows app for exporting locally stored **Minecraft Bedrock and Java Edition** worlds through MiEx and importing the resulting USD into Blender. It can discover local worlds, show their thumbnails and last-played or last-saved dates, and copy a selected world to a working snapshot without manually creating a ZIP.

## Getting started

1. Close Minecraft to avoid copying a save while it is being written.
2. Download the Windows executable from the [latest GitHub release](https://github.com/AntnyGamer/MinecraftToBlender/releases/latest), or build it from source below.
3. Run `MinecraftToBlender_v1.exe`.
4. Choose **Select Bedrock World** or **Select Java World**. If the save is not listed, use **Choose folder** in the picker.
5. Select a world. Center X and Center Z default to **0, 0** for every selection; you can change them manually. Verify the height range and region size.
6. Optional: open **Settings** and enable **Use world resource packs** to use resource packs bundled with the selected save. It defaults to off, and MiEx only uses packs it can actually find.
7. Export to USD, or choose **Export to Blender** to create a `.blend` and open it automatically after a successful import. In **Settings**, toggle **Auto-open Blender** off if you prefer to open it manually. The preference is saved between launches.
8. Inspect the Blender scene for missing terrain, materials, item frames, or other details. A successful import is *not* a guarantee of exact visual fidelity.

### Optimize an already-exported Blender project

Use the **same MinecraftToBlender EXE**: open **Import USD**, browse to an existing `.blend` instead of a `.usd`, and select **Create / optimize project**. The EXE invokes your installed Blender in the background, performs exact duplicate-material-slot cleanup and clears excessive initial mesh selections, then saves a new numbered `.blend` copy next to the original. The original project is never overwritten, and you do not have to re-export the Minecraft world or run a separate script. **Batch meshes** in Export options is also applied to an existing `.blend` when enabled; it remains off by default because joining changes object organization and can reduce view culling. No geometry is intentionally removed, but this is not a guaranteed FPS improvement: scenes without duplicate slots or large selections may show no meaningful difference. Blender must be installed, and this procedure still loads and saves the project once. It operates on saved project files, not a currently open Blender window with unsaved changes.

**Official Bedrock shulker-box textures (automatic):** Bedrock exports use Mojang's official 64×64 shulker texture atlases where the workspace lacks an existing texture. The vanilla undyed and silver sheets are assigned to the `shulker.png` and `shulker_light_gray.png` names expected by MiEx. All 17 files are pinned to Mojang's published revision and verified by Git blob hash and image decoding; user-customized textures are never overwritten. Downloads run only for missing files and are cached, with the existing Minecraft textures retained if the official sheets cannot be downloaded. When switching to Java, only identical managed Mojang files are removed. World resource packs take priority over these vanilla fallbacks. This uses the same EXE and has no new option; an initial Bedrock export may require additional small asset downloads.

**Automatic Bedrock visual accuracy fixes:** Bedrock hanging signs now use the saved `attached_bit` state to select the correct attached-chain model, rather than relying only on Java's `attached` state. For imported custom-material textures, the Blender importer avoids modifying another material's color-space/alpha settings when a shared image file needs different interpretations; an image datablock is copied only for that genuine conflict. Normal identical texture settings still share images. These corrections require no new options and do not alter the source Minecraft world. Real world screenshots are still needed for pixel-by-pixel fidelity verification.

### Export options (v1.0)

**Bedrock rendering regression fixes:** A verified reader overlay corrects the pinned MiEx release's block-entity section bounds, which previously discarded bed colors, banner patterns and frame data at normal building heights. Bedrock banner dye order and ominous-banner layers are normalized before MiEx generates its textures. The shulker model now resolves undyed textures correctly and retains the saved facing. A texture alias supports the moved banner pole sheet. These data fixes require a **fresh Bedrock export**: an existing USD cannot recover data that was omitted. Safe resume now fingerprints the embedded pipeline, so an older export checkpoint cannot bypass these fixes. The original MiEx JAR and Minecraft save remain unchanged.

**Viewport behavior:** Block texture view switches every 3D workspace to Material Preview, including Minecraft textures, biome tint and alpha. Water now resolves MiEx's expanded shader-node names and applies blended alpha correctly in Material Preview/renders; Solid view still has its documented transparency/tint limitations. Mesh batching recognizes the actual texture-named USD meshes through their chunk parents. Combined with normal compaction, it was exercised on an 11,303,330-face scene: 255 objects combined and 392,152,992 duplicate attribute bytes removed, with every face retained. This measures object/memory reduction, not a guaranteed FPS increase in full Material Preview.

**Additional accuracy and memory fixes:** Standing and wall signs now select their correct existing models, and saved legacy sign text is normalized without inventing null fields or dropping the back side. Sign and hanging-sign direction comparisons are evaluated explicitly by the pinned MiEx parser. With **Batch meshes** enabled, Blender also removes an unused named USD normal array only when it exactly duplicates the retained native split normals. Referenced/dynamic attributes, animated/shared meshes and any differing normals are preserved. The original USD stays intact. This targets scene memory/file overhead; it does not promise an increase in Material Preview FPS.

**Partial resource packs:** Enabling world resource packs now allows MiEx to discover bundled packs; an unconditional Java CLI flag previously overrode the enabled setting. A local copied-world probe confirms the pack is absent with that flag and active above BlenderEEVEE without it. The exporter also retains the matching vanilla Bedrock bed/shulker atlases and banner-pole fallback. Previously this option removed those fallbacks even when a pack replaced only an unrelated block, allowing Java bed UVs or a missing banner pole to reappear. MiEx searches the world pack first, so custom textures still take priority. The pinned runtime regression exercises both custom texture selection and fallback selection.

**Additional Bedrock details:** Fresh exports now include decorated-pot geometry and vanilla sherd patterns, inactive/active conduits, dragon/piglin heads and the enchanting-table book. Saved flower-pot contents select the correct plant instead of a palette-only fallback. Legacy skull types and rotation are retained, including the correct wither-skeleton texture. Armor stands retain saved equipment, leather dye, all 13 Bedrock pose presets and small size; equipment shares two-sided geometry with the stand to avoid duplicate reversed faces. These models use the existing Minecraft texture installation and respect resource-pack texture priority. The book and conduit effects use static poses; live animation and player-facing behavior are not reproduced. Arbitrary add-on pot patterns and every custom entity are not covered.

**Unused USD preview colors:** With **Batch meshes** enabled, the importer/optimizer also removes `displayColor` corner arrays when no shader or node group reads them. These USD preview colors are separate from MiEx's `Cd` biome tints. Named/default color readers, dynamic string inputs, shader scripts, vertex-color viewports and edited/animated/shared meshes prevent this cleanup. Numeric texture-UV animation is retained. Removing them changes the available editable attributes; the source USD and original `.blend` remain intact. On the 11,303,330-face scene this removed another 723,413,120 attribute bytes (about 690 MiB), retaining every vertex/face and an identical SHA-256 of all `Cd` values. A smaller EEVEE before/after render was pixel-identical. Together with normal compaction, this eliminates about 1.04 GiB of attribute payload in that scene; full-scene viewport FPS has not been measured.

**Minecraft-style water (optional, Off by default):** Use the toggle in **Export options** before either **Export to Blender** or **Import USD**. The imported Blender water retains the MiEx water mesh, UV coordinates, and existing biome-tinted color textures, and switches just those water materials from MiEx's noisy hashed transparency to Blender 5.2's smoothly blended transparency. Existing texture-alpha connections remain intact, and materials with no texture alpha receive a conservative 0.80 constant opacity. This is a **Blender approximation**, not the proprietary Minecraft Bedrock/Java rendering engine: it cannot reproduce all underwater fog, real-time lighting, animated current flow, or water screen-space effects. Blended surfaces can lower Blender viewport frame rates or have depth-sorting issues on huge oceans, so the default remains Off. The toggle changes Blender shading only; USD-only exports and original world files are unaffected. Reimport an existing USD to switch the effect without re-exporting Minecraft terrain. The existing materials remain the default for all other blocks.


**Minecraft block-texture view (optional, Off by default):** The **Block texture view** button makes new Blender imports (or a new optimized copy of an existing .blend) open in **Material Preview** with the **Standard** view transform. MiEx's shader connections display block textures, biome colors and transparency. Large worlds may take time to compile shaders and render the preview. The option changes display preferences only, preserving export files, geometry, UVs and shader connections. Off leaves Blender's existing display settings unchanged (normally Solid on a fresh import).

**Optional mesh batching (Off by default):** Enable **Batch meshes** in Export options before **Export to Blender** or **Import USD**. Blender groups compatible static, opaque terrain meshes in nearby 2×2 MiEx chunk sections when those meshes share an identical material datablock, UV layers, and vertex-color layout. Joins are limited to eight objects and 75,000 polygons at a time; entities, water, modifiers, shape keys, vertex groups, animations, shared/instanced mesh data, custom USD metadata, and nonstandard object color are excluded. The entire model stays visible, and every face, UV coordinate, material and underlying Minecraft export is retained. Fewer Blender objects may improve FPS on large worlds, **but** merging changes per-object editability, selection and hierarchy, may increase the Blender-import time, and can reduce per-chunk frustum-culling effectiveness. This is why batching is opt-in rather than a no-downside default. The import log reports actual objects combined; if none qualify, there is no speed benefit.

**Large-import selection cleanup (default):** If the Blender importer initially selects 128 or more *visible meshes*, the completed .blend opens with those objects deselected, avoiding thousands of selection outlines and selection-related viewport overhead. All meshes, polygons, materials, transforms, and rendering settings are unchanged; you can select any object normally afterward. Smaller imports retain their selection state. This optimization only helps when the importer actually selects many objects; the log reports how many it cleared. The only workflow change is that the initial bulk selection is cleared.

**Exact duplicate material-slot cleanup (default):** The importer also removes slots that refer to the exact same Blender material datablock, remapping faces to the existing identical material. This does not change any rendered material, texture, face, UV or geometry, but may reduce redundant draw submissions on projects where those duplicates occur. No change is made when the materials are different, even if they look alike. The speed impact can be zero if the original meshes don't contain duplicate slots.

Use **Export options** in the sidebar to choose the Overworld, Nether or End, select whether to export item frames, paintings, armor stands and display entities, and control the optional safe resume checkpoint. All six previously supported entity types remain enabled by default.

**Preview region** requests every chunk in the selected area when it covers at most **9,216 chunks** (usually an area up to roughly 1,536×1,536 blocks). Its top-down MiEx images are placed at their exact Minecraft X/Z block coordinates, without stitching distant chunks together. This is more accurate but can take longer than sparse preview sampling on large saves. For larger areas, preview work is bounded to a maximum of 96×96 sampled chunks and the preview becomes a **coarse color overview**, not a detailed map of actual block geometry. Missing, empty, or transparent chunk images remain gray; a screenshot alone cannot establish whether those cells are unsaved terrain or a MiEx decoding failure. Click to update center X/Z; clicks from a preview of a different selected world are rejected. For improved responsiveness, chunk images are now requested from MiEx in sequential groups of at most 64. The app counts completed responses as they arrive, so preview progress describes **requested chunk positions**, not a guessed export percentage. If no group responds for 90 seconds, the activity log warns that MiEx may be stalled and suggests Cancel; this diagnostic does not automatically kill legitimately slow world reads. Splitting requests does not reduce preview resolution or skip terrain, and does not guarantee total preview time will decrease. The preview takes a read-only world snapshot and may take time on large saves; temporary preview images are removed after closing the map.

**Check readiness** reports installed Java/Blender versions, available RAM and workspace disk space, and basic region/dimension validity. Export also asks about detected warnings before starting. These are early warnings, not guarantees.

**Starting Blender viewpoint:** The imported project now opens near the middle of the selected terrain instead of framing the entire landscape from a very large distance. Zoom is bounded to 180 Blender units for large scenes, so a 1,024-block export starts noticeably closer. Press **Home** in Blender's 3D Viewport to frame the full model; this changes only your initial viewport view, not the geometry or export coordinates.

**Performance on large regions:** The pinned MiEx importer now skips Blender's redundant USD PreviewSurface node construction while keeping material bindings, because MiEx immediately builds the final Minecraft shader networks from JSON. Its shader graph layout tracks nodes by column and avoids processing shared shader branches repeatedly when their placement constraints are already satisfied. Automated comparisons confirm unchanged node ordering and positions on synthetic graphs. These are import-time optimizations, not guaranteed improvements to Blender's loaded-scene FPS. For already saved large .blend files, the EXE's optimizer also disables parent relationship-line overlays while preserving geometry and parent-child relationships. No previous-version MinecraftToBlender settings migration or compatibility layer was added, and no separate user-run script is involved.

A 1,024×1,024-block area contains 4,096 Minecraft chunks. Unlike Minecraft's distance-based runtime renderer, this exporter needs to build all selected geometry so it can be inspected from any viewpoint in Blender. MiEx already skips faces occluded by neighboring blocks and enables face merging. The importer now offers optional bounded mesh batching to reduce separate terrain objects without deleting faces, plus default exact duplicate material-slot cleanup that does not change visible surfaces. Blender's initial far-clipping distance is also kept closer to the world scale to reduce unnecessary depth-buffer range. The importer avoids an extra expensive full-scene dependency-graph evaluation when the scene consists only of static, unmodified meshes. This saves redundant import-time work but cannot make a multi-million-block scene behave like Minecraft's streaming engine. It preserves the complete model. Each export prints `[PERF]` timing lines for the snapshot, MiEx setup, Java world conversion, and USD verification/publication. The Blender log separately times USD inspection, import, bounds framing, and project saving; use these numbers to identify the actual bottleneck before changing fidelity settings. The conservative optimizer intentionally does not enable raytracing, remove caves, merge geometry subsets, or enable unsafe point-cloud instancing.

The activity area shows elapsed time and periodically reports the MiEx JVM's private committed memory and physical working set (resident RAM), with the JVM process ID. On Windows, a lightweight Java launcher may spawn a separate JVM; only verified descendant JVM processes are considered, and unavailable readings are explicitly labeled instead of showing the launcher's misleading 10 MiB. These measurements are not the maximum Java heap (-Xmx) or the total system RAM. It deliberately does **not** invent an export percentage.

**Safe resume** is off by default to avoid extra disk reads on ordinary exports. When enabled with **Export to Blender**, the app records a SHA-256 checkpoint of the complete successfully exported USD and its source world. If Blender import then fails, a retry with exactly the same inputs can skip MiEx and resume at Blender import. Modified world or USD data invalidates the checkpoint. **Interrupted MiEx chunk exports cannot currently resume midway**: MiEx experimental-34 omits disabled chunks from the generated USD root, so merging half-written layers would risk losing terrain.

**Requirements:** Java 21+ on PATH, Blender installed, and an internet connection for initial MiEx/resource downloads. The app itself has no third-party Go dependencies. Standard installation locations are searched automatically; custom locations can be selected in the interface.

### Terrain-free export diagnostics

The world picker deliberately defaults Center X and Center Z to **0, 0**.
If the world's recorded player/spawn location is outside the selected rectangle,
the app warns before exporting but does not change the coordinates. MiEx may
export empty USD layer shells if the region contains no saved terrain, or if a
Bedrock save format is unsupported. The exporter now checks that actual chunk
mesh faces were written **before** publishing or importing; a failed or empty
new export preserves the previous completed export. For a diagnostic, choose
a small region centered at a known Minecraft build/player coordinate and keep
the game closed while the snapshot is taken.

## Building

Go 1.23+ and Python 3 are required to produce a branded Windows executable. On Windows, from the repository root:

```powershell
go test ./...
python tools/generate_icons.py
go run github.com/tc-hib/go-winres@v0.3.3 make --in winres/winres.json --out rsrc --arch amd64
go build -ldflags="-H=windowsgui -s -w" -o MinecraftToBlender_v1.exe .
```

The same Windows binary can be cross-compiled on other systems:

```sh
python3 tools/generate_icons.py
go run github.com/tc-hib/go-winres@v0.3.3 make --in winres/winres.json --out rsrc --arch amd64
GOOS=windows GOARCH=amd64 go build -ldflags='-H=windowsgui -s -w' -o MinecraftToBlender_v1.exe .
```

The metadata-parser tests also run on Linux and macOS using `go test ./...`, but the Windows GUI itself requires Windows. The GitHub Actions workflow generates and embeds the icon before building the Windows EXE artifact. The vector source of truth is `branding/logo.svg`; `tools/generate_icons.py` produces a single multiresolution `winres/app.ico` (16, 24, 32, 48, 64, 128, and 256 px) using Python's standard library. The pinned `go-winres` is a build-only tool, not an application dependency. Explorer, the taskbar, Alt+Tab, the main window, and the world picker all use the embedded icon. Generated icon and `.syso` files are intentionally not checked in.

## How it works

- The executable embeds the workflow files under `assets/` and extracts them to a per-user workspace on demand.
- The importer and resources are downloaded from a pinned MiEx revision. The MiEx JAR and Blender Python importer are checked against pinned SHA-256 hashes before use. Only the verified app-managed importer is executed; nearby `MiExImport.py` files are ignored.
- Each export uses a working snapshot of the selected save. On Windows, the snapshot copy uses Robocopy with up to eight copy threads (falling back to PowerShell copying if unavailable); this may reduce preparation time for saves with many files. Close Minecraft first to avoid capturing changes during copying. A fresh temporary export directory prevents old USD chunks from contaminating the next export; the previous completed export is kept if publication fails. An interrupted replacement can be recovered from its completed backup at the next publication attempt. The original Minecraft world is not intentionally modified.
- Re-exporting the same world preserves `.blend` projects, Blender's numbered backups, and unrelated user files inside the export folder, while replacing regenerated USD files and chunk layers. Files are moved rather than copied.
- Export-region boundary faces are enabled so terrain blocks at the sides and the bottom of the selection render as solid stone, deepslate, and other real blocks, instead of being hidden by blocks outside the region. Real cave openings remain open; this does not invent new blocks. Export boundary geometry may be slightly larger.
- The converter enables MiEx's face optimizer, while disabling raytracing optimization, geometry-subset batching, and individual-block point instancing. A raytracing-enabled 1024 × 1024 Bedrock export exhausted a 24 GB Java heap, so this release avoids that path. Geometry-subset batching can also cause terrain-free layers with pinned MiEx experimental-34. This configuration has not been proven correct for every world: inspect the imported scene.
- When auto-open is enabled (the default), a completed Blender project opens in the selected Blender installation. The **Open project** button still works if auto-open is disabled or launching Blender fails. The setting is saved at `%LOCALAPPDATA%\MinecraftToBlender\preferences.json`; **USD only** never launches Blender.
- Blender projects are named for the selected world by default, e.g. `Night_Blades_Survival.blend`, and `Night_Blades_Survival_2.blend` if the first file exists. A custom **Export Name** becomes the filename; importing an existing USD uses its filename. Existing `.blend` files are preserved.
- World resource packs are **off by default**. When opted in, MiEx discovers and extracts supported resources from the world snapshot into the app workspace. An isolated pack name avoids accidentally using outdated packs. A finished preview removes its temporary extracted pack; completed exports keep their pack files because USD textures may depend on them, so workspace storage may increase. It does not modify the original save and cannot supply missing packs that aren't available to MiEx. Resource-pack ZIP/JAR entries are checked for unsafe paths before MiEx extracts them. The importer prefers the render variant when actual terrain meshes exist, falling back to proxy only when needed.
- Bedrock-only overrides retain raw bed color, half and direction, prefer the original numeric shulker facing state, and handle legacy `Text` on standing/hanging signs. Legacy front-side sign text now preserves any existing modern back-side data. Java exports explicitly remove these overrides from a reused workspace. These fixes do not replace missing block entity data.
- Legacy iron chains resolve to the available chain resource name. Copper chests have single/double models for all oxidation and wax variants, with halves chosen from saved pair coordinates. Copper golem statues have a standing geometry fallback with matching oxidation textures; non-standing Bedrock statue poses remain unverified. See the [model audit](docs/bedrock-model-audit.md) for checks and limits.
- Bedrock block entities retain already translated palette states, preserving undyed/colored shulker IDs and bell wall/ceiling attachments. Legacy beds select their dye from saved block-entity data, and piston bases use saved extension state. Redstone connections preserve corners and junctions; separated dust-overlay planes avoid coplanar flickering in Blender. These fixes require a fresh world export. End portals now have a verified official texture fallback, and End gateways have visible cube surfaces instead of an empty model. Portal surfaces use a static texture approximation; animated portal effects and gateway beams are not reproduced.
- Bedrock beds now use Mojang's **Bedrock-specific 64×64 bed atlas geometry** and matching texture sheets. The app downloads the 16 official vanilla Bedrock bed textures on the user's machine when needed, verifies their pinned hashes, and caches them. Valid custom sheets are retained; an unavailable, corrupt or incompatible texture now fails the new export rather than silently producing a black bed. When switching to Java, only hash-verified app-managed Bedrock sheets are removed. Bedrock world packs keep the vanilla fallbacks below their custom textures. World-supplied resource packs may use custom atlases that still need visual testing. Legacy `standing_sign`, `wall_sign`, `standing_banner`, `wall_banner`, `frame`, `glow_frame`, and `undyed_shulker_box` IDs have dedicated Bedrock handling. Missing generated banner/layered texture files referenced by the exported materials cause export publication to fail rather than saving a known-broken replacement.
- Large MiEx JSON diagnostics are truncated before the GUI message queue to match the existing 4,000-byte display limit; complete messages are still saved to the disk log. Bedrock world discovery avoids reading levelname.txt when valid NBT already supplies the title, and the nonmutating Blender texture audit correctly recognizes Blender `//` paths as relative without expanding them.
- The Windows world picker retains its existing thumbnail loading behavior to avoid scroll-time disk reads. Overlapping Java save-root paths are deduplicated before checking folders.
- Performance-preserving workflow changes buffer verbose child-process logs, avoid processing full MiEx diagnostic JSON in the UI, reuse scene data when counting geometry and framing repeated instances, and look up shader nodes directly by name. The exporter reuses its enumerated chunk list for terrain checks, while the EXE validates USD folders in small batches and checks material JSON without building large material maps. Combined export-and-import avoids redundant validation of the same USD; manually selected USDs still receive full validation. These default changes do **not** decimate meshes, change textures, or toggle upstream geometry optimizers. An additional opt-in, separately described above, can join suitable static terrain mesh objects.
- The final export accuracy audit reads the MiEx console log once for missing blocks, warning samples, and success status. The standard Windows log fallback appends incrementally while following output, retaining the original full-text path when needed.
- MiEx-generated banner patterns and layered textures are stored with each portable export. The Blender importer saves a `<project>_texture_audit.txt` alongside the project and warns about missing external image files. The audit cannot certify exact visual fidelity or detect every missing text mesh.
- Files under the workspace are generated by the app and should not be committed. **Do not commit world saves or downloaded game assets.**

## Project layout

| Path | Purpose |
| --- | --- |
| `main.go` | Windows app processes, export/import orchestration, logging |
| `ui.go` | Main Windows UI and console |
| `picker.go` | Minecraft-style world library UI |
| `worlds.go` | Java/Bedrock save discovery and NBT metadata reader |
| `worlds_test.go` | Save metadata and world ordering tests |
| `assets/Export_World.ps1` | MiEx export pipeline |
| `assets/Import_Existing_USD.py` | Blender USD import and terrain validation |
| `assets/` | Other optional conversion and MiEx patch helpers |

**Validation status:** CI runs the actual pinned MiEx evaluator and reader overlay against saved-data fixtures and reproduces the bundled class and detail JSONs from pinned sources. A fresh 256×256 export from a copied Bedrock save was imported and rendered in Blender 5.2.3: all 363 external images were present, including the new detail models and equipped armor stand. This checks the sampled models, not every block, custom resource pack or world. Minecraft screenshots are still needed for pixel-by-pixel comparisons.

## Known limitations

- Automatic discovery is not guaranteed for every custom launcher or alternate drive. Use **Choose folder** when necessary.
- Console progress uses real elapsed time, stage messages and periodic Java memory readings; the exporter does not provide a reliable percentage.
- Some Bedrock blocks, modded Java models, materials, or item frames may not render perfectly in Blender. Large exports may use significant CPU, RAM, and storage.
- Windows GUI behavior and complete Java/Bedrock-to-Blender conversions still need end-to-end testing with real saves. Syntax, unit tests, and successful compilation are not a substitute.
- The app uses third-party MiEx tools but **does not bundle Mojang world content or a MiEx JAR**.

## License and notices

The app's source is available under [MIT](LICENSE). MiEx is a separate project licensed under BSD-3-Clause; see [third-party notices](assets/THIRD_PARTY_NOTICES.txt). Minecraft and Blender belong to their respective owners. This project is not affiliated with Mojang, Microsoft, or Blender Foundation.

## Diagnosing missing Bedrock terrain

If MiEx exports only entities without actual terrain, the app now asks MiEx
itself to read a small sample of 25 chunk locations from the selected region.
The console reports **MiEx selected world** and **MiEx chunk probe** before
any resulting USD is accepted.

- **Wrong selected world:** world loading/snapshot configuration failed.
- **Zero loaded probe chunks:** look for `Chunk section format not supported`
  or LevelDB read errors in `AppTools/MiEx_Work/miex_console.log` and
  `AppTools/MiEx_Work/miex_stderr.log`. Zero samples alone does not prove the
  entire region is empty.
- **Some loaded chunks but no terrain USD:** chunk decoding worked in at least
  part of the region, but the subsequent mesh/material/export stage failed. In
  experimental-34, geometry-subset batching can also discard terrain during USD
  conversion; this app disables that setting, pending a real-save retest.

The app cannot determine the exact reason from an importer traceback alone.
The MiEx log or a representative copy of the world is required to confirm
which stage is failing; the original Minecraft save is never modified.

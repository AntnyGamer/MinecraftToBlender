# MinecraftToBlender

<p align="center"><img src="branding/logo.svg" alt="MinecraftToBlender logo" width="112" height="112"></p>

**Version:** v1.0.7  
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

### Export options (feature branch)

Use **Export options** in the sidebar to choose the Overworld, Nether or End, select whether to export item frames, paintings, armor stands and display entities, and control the optional safe resume checkpoint. All six previously supported entity types remain enabled by default.

**Preview region** samples up to 16×16 actual chunk images through MiEx. When the selected region fits within the sample grid, it scales the real block positions precisely; larger regions show an **approximate sampled** map, not a complete terrain survey. Unavailable chunks remain gray, including entirely unexplored regions. Click to update center X/Z; clicks from a preview of a different selected world are rejected. The preview takes a read-only world snapshot and may take time on large saves; temporary preview images are removed after closing the map.

**Check readiness** reports installed Java/Blender versions, available RAM and workspace disk space, and basic region/dimension validity. Export also asks about detected warnings before starting. These are early warnings, not guarantees.

The activity area shows elapsed time and Java working-set memory measurements when MiEx reports them; it deliberately does **not** invent an export percentage.

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
- When no world resource pack is selected, a Bedrock export can download 16 vanilla bed images from a pinned `Mojang/bedrock-samples` revision into the user's MiEx workspace. Each image is verified against its Git blob hash, cached, and never bundled in the executable. Existing nonmatching bed-texture files are preserved with a warning rather than overwritten. Failed downloads warn and fall back to existing textures; the optional network attempt is bounded. When switching to Java or world resource packs, only unchanged, verified fallback files are removed, leaving custom textures intact.
- Large MiEx JSON diagnostics are truncated before the GUI message queue to match the existing 4,000-byte display limit; complete messages are still saved to the disk log. Bedrock world discovery avoids reading levelname.txt when valid NBT already supplies the title, and the nonmutating Blender texture audit correctly recognizes Blender `//` paths as relative without expanding them.
- The Windows world picker retains its existing thumbnail loading behavior to avoid scroll-time disk reads. Overlapping Java save-root paths are deduplicated before checking folders.
- Performance-preserving workflow changes buffer verbose child-process logs, avoid processing full MiEx diagnostic JSON in the UI, reuse scene data when counting geometry and framing repeated instances, and look up shader nodes directly by name. The exporter reuses its enumerated chunk list for terrain checks, while the EXE validates USD folders in small batches and checks material JSON without building large material maps. Combined export-and-import avoids redundant validation of the same USD; manually selected USDs still receive full validation. These changes do **not** decimate meshes, merge terrain, change textures, or toggle upstream geometry optimizers.
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

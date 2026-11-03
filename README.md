# MinecraftToBlender

<p align="center"><img src="branding/logo.svg" alt="MinecraftToBlender logo" width="112" height="112"></p>

**Version:** v1  
**Platform:** Windows 10/11 (64-bit)  
**Languages:** Go (Win32 interface), PowerShell, Python, Java patch utility

A Windows app for exporting locally stored **Minecraft Bedrock and Java Edition** worlds through MiEx and importing the resulting USD into Blender. It can discover local worlds, show their thumbnails and last-played or last-saved dates, and copy a selected world to a working snapshot without manually creating a ZIP.

## Getting started

1. Close Minecraft to avoid copying a save while it is being written.
2. Download a built Windows executable from the repository's Actions artifacts (when CI has run), or build it from source below.
3. Run `MinecraftToBlender_v1.exe`.
4. Choose **Select Bedrock World** or **Select Java World**. If the save is not listed, use **Choose folder** in the picker.
5. Select a world. Center X and Center Z default to **0, 0** for every selection; you can change them manually. Verify the height range and region size.
6. Optional: open **Settings** and enable **Use world resource packs** to use resource packs bundled with the selected save. It defaults to off, and MiEx only uses packs it can actually find.
7. Export to USD, or choose **Export to Blender** to create a `.blend` and open it automatically after a successful import. In **Settings**, toggle **Auto-open Blender** off if you prefer to open it manually. The preference is saved between launches.
8. Inspect the Blender scene for missing terrain, materials, item frames, or other details. A successful import is *not* a guarantee of exact visual fidelity.

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
- Each export uses a working snapshot of the selected save. A fresh temporary export directory prevents old USD chunks from contaminating the next export; the previous completed export is kept if publication fails. The original Minecraft world is not intentionally modified.
- Export-region boundary faces are enabled so terrain blocks at the sides and the bottom of the selection render as solid stone, deepslate, and other real blocks, instead of being hidden by blocks outside the region. Real cave openings remain open; this does not invent new blocks. Export boundary geometry may be slightly larger.
- The converter disables MiEx geometry-subset batching, face merging, and individual-block point instancing by default. In pinned MiEx experimental-34, subset batching writes merged meshes under names that do not match the root-mesh index used by USD conversion, yielding terrain-free layers. Disabling batching may increase object counts; real-world performance has not yet been benchmarked.
- When auto-open is enabled (the default), a completed Blender project opens in the selected Blender installation. The **Open project** button still works if auto-open is disabled or launching Blender fails. The setting is saved at `%LOCALAPPDATA%\\MinecraftToBlender\\preferences.json`; **USD only** never launches Blender.
- Blender projects are named for the selected world by default, e.g. `Night_Blades_Survival.blend`, and `Night_Blades_Survival_2.blend` if the first file exists. A custom **Export Name** becomes the filename; importing an existing USD uses its filename. Existing `.blend` files are preserved.
- World resource packs are **off by default**. When opted in, MiEx discovers and extracts supported resources from the world snapshot into the app workspace. An isolated pack name avoids accidentally using outdated packs; this may increase workspace storage. It does not modify the original save and cannot supply missing packs that aren't available to MiEx. Resource-pack ZIP/JAR entries are checked for unsafe paths before MiEx extracts them. The importer prefers the render variant when actual terrain meshes exist, falling back to proxy only when needed.
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
- Console progress is based on stages and actual log activity; the exporter does not provide a reliable percentage.
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

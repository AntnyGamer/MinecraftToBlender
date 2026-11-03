# MinecraftToBlender v1.0.2

This release adds opt-in world resource packs and improves model fidelity while updating the Windows build dependencies.

### Changes

- Added **Use world resource packs: Off/On** in Settings, **off by default**. With the option on, MiEx can discover and extract resources supplied with a Minecraft world snapshot to improve texture/model fidelity. The original world is never modified.
- Changed Blender import preference to **Render** when a render variant contains terrain meshes, falling back to Proxy when render terrain is missing. This preserves the intended detailed render variant even if a proxy happens to have more faces.
- Updated GitHub Actions checkout, setup-go and upload-artifact to their reviewed, SHA-pinned major versions from Dependabot.
- Preserved the v1.0.1 relationship-lines display fix, original terrain validation and safe snapshot/export behavior.

### Important limitations

The world resource packs option does not download missing packs or guarantee compatibility with every custom model; enabling it can increase export time/storage and change the output to match the selected world's resources. MiEx does not recreate Minecraft's full in-game water renderer, including all reflections, transparency and underwater effects. World-export visuals still require checking in Blender, and neither custom resource packs nor every Bedrock block model have been tested end-to-end in this release.

### Requirements

Windows 10/11 x64, Java 21+ on PATH, Blender installed, and internet access for initial MiEx resources. The GitHub release contains the Windows executable and a SHA-256 checksum.

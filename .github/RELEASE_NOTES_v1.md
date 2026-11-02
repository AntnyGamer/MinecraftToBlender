# MinecraftToBlender v1.0

First downloadable Windows release of the Minecraft-to-Blender exporter.

### Included

- Windows 10/11 x64 app for converting locally stored Minecraft Bedrock and Java world saves to MiEx USD and importing them into Blender.
- A workaround for missing terrain from a mesh-name mismatch in the pinned MiEx geometry-subset batching path.
- Read-only world snapshots, 25-chunk diagnostic sampling, terrain-mesh validation, and protection of prior completed exports when a new export fails.
- Small performance improvements to export process monitoring, Blender USD validation, and GitHub Actions setup.
- SHA-256 checksum file for the downloadable EXE.

### Requirements

Java 21 or newer, Blender installed, and internet access on first run to obtain pinned MiEx resources.

### Verification and known limitations

Windows build, PowerShell validation, Go tests, and static source investigation passed. The terrain workaround has **not yet been verified against the original affected Minecraft world end-to-end**, and complex Bedrock block models, item frames, textures, and materials may still require visual checking after importing. This is a v1 release, not a certification of perfect export fidelity.

No game binaries, proprietary Minecraft assets, or users' Minecraft saves are included in the downloadable EXE.

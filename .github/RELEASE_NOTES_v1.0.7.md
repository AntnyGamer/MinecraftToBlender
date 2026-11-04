# MinecraftToBlender v1.0.7

## Reliability and export performance
- Keep MiEx's face optimizer enabled with 16×16-Minecraft-chunk export sections, following a successful face-only world export test.
- Disable MiEx raytracing optimization, raytracing mesh subsets, geometry-subset batching, and individual-block point instancing. A previous raytracing-enabled 1024×1024 Bedrock export exhausted a 24 GB Java heap while merging meshes.
- Detect Java `OutOfMemoryError` during export, stop the failed Java process, report the issue clearly, and preserve the last completed export rather than publishing partial output.
- Speed up preparing world snapshots on Windows with an eight-thread Robocopy path and PowerShell fallback. Benefits depend on the world's files and disk.
- Stream very large MiEx diagnostics to disk without the previous 8 MB per-line reader limit; keep the app's visible log bounded.
- Improve success auditing to distinguish a successful world-loading command from a successful final export.
- Preserve Blender projects, backups, and unrelated user files when replacing a generated USD export.

## Interface and repository
- Remove the unused hidden native progress control, dead UI state, and the unwanted “Detailed conversion log” subtitle. Keep the custom-drawn activity indicator and logging.
- Update Blender import diagnostics and documentation to reflect the actual optimizer configuration.
- Remove superseded release-note documents from the active source tree; historical releases and repository history remain available.

## Testing and limitations
- GitHub Actions builds and unit/regression tests cover Windows packaging, PowerShell export helpers, snapshot copying, export audits, and handling of extremely long log lines.
- A full 1024×1024 Bedrock world export and visual inspection in Blender have **not** been independently repeated for this build. Face optimization is not guaranteed to preserve every model perfectly; inspect exported terrain and textures.
- Requires Windows 10/11 x64, Java 21+, Blender for automatic import, and an internet connection for initial pinned MiEx/resource downloads.

# Release 1.0.4

This maintenance release retains the MinecraftToBlender v1 interface and export behavior while simplifying preview chunk calculations and hardening the build and test pipeline.

## Changes

- Reuse integer floor division for preview chunk boundaries, including negative world coordinates, instead of repeated floating-point conversions.
- Extract the existing Windows integration validation from the workflow into a reusable PowerShell script, with a local temporary-directory fallback.
- Update the Go build compiler to 1.27.4 and pin GitHub Actions to verified release commits.
- Keep Windows **FileVersion** and **ProductVersion** synchronized at **1.0.4.0**, while the application manifest **assembly identity stays fixed at 1.0.0.0**.

## Compatibility and verification

No existing Minecraft saves or Blender projects are intentionally modified. Export results and preview quality should remain unchanged; these changes do not add new rendering features. Safe-resume checkpoints are version-sensitive and may require re-export after the update.

The build pipeline verifies Go tests, Python/PowerShell regressions, the compiled Windows executable, file/product version metadata, and the fixed application assembly identity. As always, verify Minecraft visual fidelity against the original game where accuracy matters.

Requires Windows 10/11 (64-bit), Java 21+, and a supported Blender installation.

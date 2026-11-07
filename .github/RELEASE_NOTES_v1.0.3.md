# Release 1.0.3

Download **MinecraftToBlender_v1.exe** below. This release introduces Bedrock sign multi-line text wrapping with formatting code preservation, Bedrock block entity parsing optimizations, importer command-line handling robustness, and static analysis compliance for continuous integration.

**For block-model, color, sign-text, and world-data fixes, make a fresh Minecraft export.** Reopening an old USD cannot recover data omitted during its original export. Your Minecraft saves and existing Blender projects remain untouched.

## Bedrock sign multi-line wrapping and text formatting

- **Multi-line word wrapping:** Sign text that exceeds vanilla sign widths (90 font pixels for standing/wall signs, 60 font pixels for hanging signs) now wraps cleanly across lines instead of clipping or overflowing the board.
- **Formatting code preservation:** Text color, bold, and style formatting codes (`§a`, `§l`, etc.) are tracked and carried over across wrapped lines, matching in-game text styling.
- **Whitespace and layout fidelity:** Consecutive spaces, indentation, and explicit line breaks (`\n`, `\r\n`) are preserved up to the 4-line vanilla limit.

## Importer and UI improvements

- **Blender importer argument handling:** The Python importer `Import_Existing_USD.py` now tolerates direct invocation without the `--` separator flag, preventing unhandled exceptions when called programmatically.
- **Win32 resource cleanup:** Zeroes GDI+ token and font handles on dialog destruction to ensure safe idempotence across multiple world picker sessions.
- **Go vet compliance:** Corrects pointer dereferencing patterns in Win32 owner-drawn button painting and window minimum size enforcement, satisfying Go vet `unsafeptr` static analysis without runtime overhead.

## Validation and limits

GitHub Actions tests Go, Python, PowerShell, Windows executable metadata, pinned MiEx regressions, and model generation before publishing. The release workflow verifies the packaged EXE against **SHA256SUMS.txt** before making the release public.

Requires **Windows 10/11 (64-bit)**, **Java 21+**, and a supported Blender installation. The app downloads pinned MiEx/resource dependencies when required.

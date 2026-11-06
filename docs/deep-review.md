# Deep review of PR 25

The 2026-11-06 review starts at `34a7c7c` and covers the PR's preview changes,
reader/model patches, resource preparation, Blender import changes, cache
integrity, file preservation and storage conversion.

## Confirmed issues corrected

| Issue | Reproduction | Correction |
| --- | --- | --- |
| A rising redstone connection becomes flat when the opposite arm is present. | The actual MiEx connection engine returned `east=side` for a wire with an eastern upward connection and western flat connection. | Endpoint-completion rules now require the opposite arm to be absent, preserving existing `up` states. |
| Updated Java model/texture assets can reuse an older retry checkpoint. Preview images also omit export-asset identity. | Changing a Java model in a synthetic embedded filesystem left the old pipeline hash unchanged. | Include both Java and Bedrock export assets in the retry digest and preview-cache version. Blender-only changes still permit reuse; unavailable pipeline identity disables reuse. |
| Existing Java bed image paths are accepted without checking usable image data. | A truncated PNG passed preparation when the other atlas files were already present. | Validate the selected overlay/base atlas before accepting it. Keep custom and HD images intact; reject corrupt/incompatible images and directories that shadow the image path. |

These tests failed before their respective corrections. The new native redstone
regression covers all 256 combinations of absent/flat/rising/descending wire
neighbors and 32 repeater/comparator orientations. It runs against the pinned
MiEx JAR in CI. Atlas tests cover corrupt overlay/base images, a valid 128×128
custom PNG, source-byte preservation, lower-priority images and directory paths.

## Complete-path checks

- Rebuilt the reader class and all 13 generated Java/Bedrock model JSON files;
  every output matched its bundled bytes.
- Reran native Java/Bedrock model regressions, including the 128 Java statue
  pose/facing/material cases, saved dyes, bell attachments, piston state,
  chest halves/pair coordinates and conduit activation thresholds.
- Exported an 80×80 Java fixture and a 64×64 copied Bedrock save with custom
  world resource packs enabled. Both exported material files referenced the
  exact custom bed PNG bytes. Complete source-fixture digests were unchanged.
- Imported both exports with texture view disabled and enabled, then saved and
  reopened them in Blender 5.2.3. Enabled: ten Material Preview views and Standard
  transform. Disabled: the factory nine Solid/one Material Preview views and AgX.
- The Java imports retained 16,370 faces and 56 external images; Bedrock imports
  retained 69,597 faces and 223 external images. No images were missing.
  Bedrock batching and existing-project optimization retained the same face
  count. Optimizing the existing project preserved the source `.blend` hash.
- Ran the real MiEx preview sampler and the application's Go PNG decoder:
  25 chunk coordinates returned 23 visible images. The northern saved-terrain
  row remained present, and the temporary preview resource pack was removed.
- Reran Python regressions, Windows PowerShell 5 installation/progress/launch
  checks, Go tests and the Windows executable build.

The earlier [performance and Crate comparisons](blender-performance-audit.md)
include scene-data equality, zero-pixel-difference renders, identical canonical
USD layer data and unchanged source exports. This review preserves those
performance changes and existing optional cleanup settings.

The checks cover the stated fixtures and paths. They do not certify every
historical save version, custom pack or animated game effect. The existing
[Java](java-model-audit.md) and [Bedrock](bedrock-model-audit.md) model limits
remain documented.

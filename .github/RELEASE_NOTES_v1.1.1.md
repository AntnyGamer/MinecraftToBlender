# MinecraftToBlender v1.1.1

## Corrections
- Correct preview geography: complete chunk coverage and exact Minecraft block positions for regions up to 9,216 chunks. Very large previews use bounded coarse-color sampling instead of stitching unrelated block images together.
- Hide readiness and export subprocess console flashes; improve MiEx Java working-set reporting so unavailable measurements are not displayed as false zero GiB readings.
- Fix version-label clipping and make the MINECRAFT / TO BLENDER header more consistent.
- Improve legacy Bedrock support: undyed shulkers, standing/wall sign aliases, numeric sign orientations, legacy standing/wall banners, and frame block fallback to MiEx's actual item-frame entity model.
- Preserve the Java-compatible bed texture atlas instead of installing Bedrock sheets over UV geometry built for Java assets. Remove only hash-verified obsolete managed files; leave user-custom textures intact.
- Add explicit MiEx export-as-block entity selection, block-entity diagnostics, and generated material texture reference checks that prevent publishing a known-incomplete export.
- Expand Windows/Go/Python validation for new behaviors.

## Limitations
These fixes have not yet been visually confirmed with a complete user Bedrock world imported into Blender. A passing automated build cannot guarantee the accuracy of all models, material UVs, or sign text. MiEx's pinned experimental release may still have Bedrock compatibility limitations. Source world data is left unchanged; previous completed exports are preserved on failed replacements.

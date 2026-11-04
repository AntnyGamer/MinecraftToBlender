# MinecraftToBlender v1.1.1

## Corrections
- Correct preview geography: complete chunk coverage and exact Minecraft block positions for regions up to 9,216 chunks. Very large previews use bounded coarse-color sampling instead of stitching unrelated block images together.
- Hide readiness and export subprocess console flashes; improve MiEx Java working-set reporting so unavailable measurements are not displayed as false zero GiB readings.
- Fix version-label clipping and make the MINECRAFT / TO BLENDER header more consistent.
- Improve legacy Bedrock support: undyed shulkers, standing/wall sign aliases, numeric sign orientations, legacy standing/wall banners, and frame block fallback to MiEx's actual item-frame entity model.
- Correct Bedrock bed body and four leg UV islands to match Mojang's official 64×64 Bedrock atlas. Re-enable 16 pinned, hash-verified Bedrock texture sheets for default exports, preserve valid custom sheets, and reject missing/corrupt textures rather than generating black beds. Switching to Java or explicitly enabled world resource packs removes only matching app-managed sheets.
- Add explicit MiEx export-as-block entity selection, block-entity diagnostics, and generated material texture reference checks that prevent publishing a known-incomplete export.
- Expand Windows/Go/Python validation for new behaviors.

## Optional Minecraft-style water
- Add an Off-by-default toggle that switches water materials from MiEx's noisy hashed/dithered alpha to Blender 5.2 smooth `BLENDED` transparency. Preserve Minecraft water geometry, UVs, biome color, water textures and existing alpha links; set modest constant alpha only when no image alpha connection exists. Disable layered translucency overlap to reduce multiple overlapping blue faces. This is intended to reduce pixelated holes at a distance; it cannot repair missing mesh faces, and blended water may sort or render more slowly on very large worlds.
- This is not Minecraft's rendering engine and does not offer identical refraction, underwater effects or animated flowing water.

## Performance
- Speed Blender's MiEx material-node layout by replacing repeated linear name searches with a stable dictionary, retaining identical node positions; add a 200-node regression check.
- Skip redundant dependency-graph evaluation when framing static, modifier-free meshes in Blender; retain evaluated bounds for instances, Geometry Nodes and other modifiers.
- Report export and Blender preparation/import phase timings to distinguish slow snapshot copying, Java meshing, scene setup and saving.
- MiEx already skips occluded neighboring block faces and runs its face optimizer; this change does not claim Minecraft-style chunk streaming or reduce scene fidelity.

- Focus the initial Blender viewport close to the selected terrain, rather than placing the viewer 1.35 times the model's full extent away; Home still frames the entire region.

## Limitations
These fixes have not yet been visually confirmed with a complete user Bedrock world imported into Blender. A passing automated build cannot guarantee the accuracy of all models, material UVs, or sign text. MiEx's pinned experimental release may still have Bedrock compatibility limitations. Source world data is left unchanged; previous completed exports are preserved on failed replacements.

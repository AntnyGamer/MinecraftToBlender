# Java model audit

The audit evaluates 12,434 Java block states with the pinned MiEx runtime and
the cached Java 26.1.2 resources. It checks generated faces and texture paths;
these checks alone cannot certify rendered parity. Before the Java repairs,
303 states were flagged. Afterwards, 60 remain: 243 flags were resolved and
no ordinary `minecraft:` texture references were missing.

| Family | Confirmed fault | Correction |
| --- | --- | --- |
| Eight copper chest variants | Vanilla block models contain only particle textures and produce no faces. | Share the chest geometry already verified for Bedrock, retaining Java `type` and facing states. |
| Eight copper statue variants | Particle-only block models produce no faces. | Separate Java standing, sitting, running and star poses, cardinal directions and oxidation atlases. |
| Decorated pots | Particle-only block model produces no faces. | Share the pot model, including the Java saved sherd list. |
| Conduits | Particle-only block model produces no faces. | Restore the model and derive Java activation from water and frame blocks. Bedrock retains its saved activation field. |
| Dragon and piglin heads, floor and wall | These newer IDs have no native MiEx geometry. | Supply the four missing IDs, retaining native Java handling for the other skull and player-head types. |
| Legacy `chain` | Current resources contain `iron_chain` instead. | Add an alias only when the legacy definition is absent; preserve existing custom definitions. |
| Sixteen bed colors | The pinned exporter expects `entity/bed/*.png`; recent decomposed bed textures do not satisfy those paths. | Restore the original Java atlases instead of using incompatible Bedrock sheets. |
| End portals and gateways | Missing texture path and empty gateway model. | Share the existing static portal fallback. Minecraft's animated shader and gateway beams are not reproduced. |

The remaining 60 flags are 32 procedural banner texture names, 16 invisible
light states, seven intentionally non-meshed IDs, three invalid young
pitcher-crop upper halves, and water/lava cases that require a world context.
Procedural banner names are resolved during export, not by the isolated model
audit. A remaining flag is not by itself evidence of an incorrect display.

## Independent reference checks

`DumpJavaStatues.java` invokes the official Java 26.1.2 model factories and
bakes their quads with the native renderer's root/facing transforms. It requires
Java 25, the client JAR and its normal dependencies, and rejects any client
whose SHA-1 differs from `4e618f09a0c649dde3fdf829df443ce0b8831e65`.
Only numeric geometry/UV facts and fingerprints are checked in.

All four poses in all four directions match the native reference's vertices,
UVs and face winding, allowing for native float rounding. CI runs 128
pose/facing/material cases through the actual pinned MiEx evaluator. The
sitting pose has 66 quads; the other poses have 54. Java's slight head-cube
inflation and pose transforms differ from the Bedrock standing model, so the
editions use separate generated definitions.

The conduit regression checks complete/incomplete surrounding water with
0, 15, 16 and 42 frame blocks, including inactive, active and open-eye states.
Geometry/UVs for equivalent activation states match the existing Bedrock
model. The exported conduit rotation, book movement and portal effects remain
static approximations of animated game rendering.

## Texture and cache handling

Java beds reuse a matching installed 26.1.2 client when available. Otherwise,
the first missing-atlas repair downloads the official 38,113,927-byte client
temporarily, verifies its SHA-1, extracts the sixteen explicitly named PNGs,
verifies their individual SHA-256 hashes and dimensions, and removes the
download. Existing base/overlay atlases retain priority. All needed images
are validated before publication; a failed download or corrupt atlas cannot
silently become a black bed.

The app now prepares `BlenderEEVEE_java` and `BlenderEEVEE_bedrock` separately.
Switching editions cannot replace the bed sheets referenced by an earlier
export. The previous `BlenderEEVEE` folder stays intact for older projects;
only hash-verified fallback images/templates are reused from it. World
resource packs, when enabled, retain higher priority.

PowerShell 5 tests cover atlas validation, corrupt extraction, repeated runs,
custom textures, legacy chain resources and edition switching. CI reproduces
both generated Java JSON files from their numeric inputs. No world saves,
client JARs or texture images are bundled in the repository.

A synthetic 80×80 Java region was exported through the complete application
script and imported into Blender 5.2.3, including all statue poses/materials,
single/double copper chests, sixteen bed colors, floor/wall heads, saved pot
patterns, two patterned banners, portals, a book, legacy chains, and conduits
with 16/42-block frames. All 56 referenced external images were present and
16,370 mesh faces imported. Rendered views confirmed the sampled appearances.
A separate 64×64 copied Bedrock save also exported/imported successfully, with
223 external images checked and none missing. These fixtures do not cover all
custom worlds, all historical save versions or pixel parity with Minecraft.

# Bedrock model audit

The audit builds geometry using the pinned MiEx runtime and the cached Java
resources, starting with each Bedrock translation rule's required and optional
input states. It checks visible face counts and external texture references.
It does not certify rendered parity or the correctness of every translated state.

The initial pass checked 15,273 distinct translated states and flagged 138
empty-model candidates. The fixes below remove 67 of those flags:

| Family | Confirmed fault | Correction |
| --- | --- | --- |
| Legacy `chain` (three axes) | The newer resource cache has `iron_chain`; the old name produces zero faces. | Resolve to `iron_chain` only when the legacy resource is absent and the modern resource exists. Existing legacy/custom definitions retain priority. |
| Eight copper chest variants (four directions) | Vanilla block models contain only a particle texture. The translator also assigns every chest `type=right`, and the reader excludes copper chests from pair handling. | Adapt MiEx's chest geometry, choose the correct oxidation atlas, default to single, and determine double halves from adjacent saved pair coordinates. |
| Eight copper statue variants (four directions) | Vanilla block models contain only a particle texture and produce zero faces. | Restore the official standing mesh, cardinal facing and oxidation texture. Non-standing Bedrock pose metadata remains unverified. |

After canonicalizing duplicate legacy/modern chain states, the repeat pass checks
15,270 distinct states and flags 71 candidates across 39 source families. None
belong to the three repaired families. Remaining candidates include intentionally
invisible blocks, wall states that require neighboring blocks, and invalid young
pitcher-crop upper halves; they are not all confirmed defects.

## Reproducible checks

- `MiExBedrockRegression.java` checks all copper chest variants, halves and
  directions, including pair coordinates crossing chunk boundaries and negative
  coordinates. It also tests chain selection with old, new and custom resources.
- Every vertex/UV tuple of the generated standing statue matches MiEx's native
  reader of the [pinned Mojang geometry](https://github.com/Mojang/bedrock-samples/blob/15701fa9c13923f12662984c32c124327e40e3d3/resource_pack/models/entity/copper_golem.geo.json).
- All four cached Java copper-golem textures have pixel-identical RGBA data to
  the corresponding official Bedrock sample atlases, despite different PNG bytes.
- Geometry inputs are hash-pinned and generated JSON is reproduced in CI.
- The [official Bedrock block registry](https://github.com/Mojang/bedrock-samples/blob/15701fa9c13923f12662984c32c124327e40e3d3/metadata/vanilladata_modules/mojang-blocks.json)
  lists cardinal direction for copper statues, with no palette pose property.
  A verified block-entity fixture is needed before claiming non-standing pose parity.

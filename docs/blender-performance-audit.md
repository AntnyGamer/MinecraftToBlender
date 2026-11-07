# Blender import memory audit

The first comparison starts at `b54c283`, using Blender 5.2.3 LTS on Windows.
The accepted changes reduce temporary Python allocations while retaining the
same scene data and settings. They apply to new imports and to the existing
optional normal-compaction pass. They do not claim a loaded-viewport FPS gain.

## Accepted changes

| Operation | Before | After | Verification |
| --- | --- | --- | --- |
| Upstream optional flat-shading assignment | A Python list containing one `False` reference per face | A contiguous Boolean memoryview with one zero byte per face | Every flag remains false, including empty meshes. The patch requires an exact match against the pinned importer. This app currently uses `flatten=False`, so its normal imports do not execute this branch. |
| Verify redundant named corner normals before/after removal | Three full float buffers | Two buffers; reuse the native-normal buffer for the post-removal read | Keep the original source buffer for comparison and exact rollback. The existing eligibility checks and opt-in setting are unchanged. Release both buffers before the next mesh. |

## Isolated measurements

**Scope correction:** the flat-shading benchmark exercises the upstream add-on's
optional branch. The application passes `flatten=False`; these numbers do not
represent a speed or memory improvement in the application's normal imports.

Flat shading used an actual Blender mesh with 1,000,000 polygons, alternating
the tested assignments over seven samples. The list's median was 0.158 seconds;
the Boolean view's median was 0.116 seconds (about 26% faster for this operation).
The list's Python storage was 8,448,728 bytes; the new underlying buffer stores
1,000,000 bytes, plus a small bytearray/view header (about 88% less buffer
storage). Reading back the flags verified identical flat shading.

Normal compaction used 1,000,000 triangles / 3,000,000 corners with native custom
normals and an identical named `normals` attribute. Python `tracemalloc` measured
108,001,328 bytes of peak scratch allocation before and 72,001,424 bytes after
(about 33% less, saving approximately 34.3 MiB on this fixture). Elapsed times
were 1.163 and 1.158 seconds; this does not establish a timing improvement.
Both versions removed the same 36,000,000-byte redundant attribute and retained
the exact native-normal hash. This change does not make more attributes
eligible for removal or enable compaction by default.

These are step-specific measurements from one machine. Python scratch memory
does not represent all Blender memory, and elapsed times vary by system.

## Automatic improvements in the follow-up pass

Compared with `2fd42c2`, these changes run on the normal import path without
enabling cleanup or changing scene data:

| Operation | Change | Blender 5.2.3 measurement |
| --- | --- | --- |
| Scene framing | Read each object/instance's transform once for its eight corners, releasing it before the next object. Each instance still uses its own transform. | 9,801 Geometry Nodes instances: median 0.103 → 0.080 seconds across seven alternating samples (about 22% faster). Exact bounds and peak Python scratch memory (1,258,788 bytes) were identical. |
| Shader layout | Remove an unused empty Python list from each temporary layout wrapper. Real shader output sockets and links are retained. | 402 nodes / 798 links: peak Python scratch memory 346,512 → 320,936 bytes (about 7% lower), identical node positions. Timing was effectively unchanged at about 0.52 seconds. |
| Startup selection counting | Count Blender's selection snapshot directly before changing selection, avoiding a second container. Keep the same 128-visible-mesh threshold and deselection behavior. | 10,000 selected mesh objects: peak Python scratch memory 165,216 → 85,712 bytes (about 48% lower). Both returned 10,000 and produced the same deselection/active-object state. Timing was effectively unchanged at about 0.084 seconds. |

These are small import steps; the percentages do not apply to total import time
or memory, and do not imply a loaded-viewport FPS improvement. The existing
normal/preview-color cleanup and mesh joining remain opt-in because they remove
attributes or change object boundaries and editing behavior. Buffer reuse is
automatic whenever normal compaction runs.

## Import and appearance checks

A 64×64-block USD fixture was imported with the baseline and candidate helpers,
with mesh batching and block-texture view enabled. Each saved project contained
866 objects, 534 mesh datablocks, 64,569 mesh faces and 228 materials. Both
uncompressed files were 25,190,880 bytes. Full process times were approximately
4.2 seconds each; no end-to-end timing gain was established on this small world.

Mesh content including attributes and native normals matched as a multiset;
material nodes, connections, defaults, locations, texture references, object
transforms, hierarchy and visibility matched. Blender assigns suffixes to some
duplicate mesh names in varying order: a repeat baseline import showed the same
variation, so content comparison normalizes those mesh names. An EEVEE render
at 480×360 with 16 samples and identical camera/environment settings had zero
pixel difference. This checks the sampled scene, rather than certifying every
world or custom pack.

The follow-up pass repeated the import/render comparison against `2fd42c2`
with batching disabled, exercising the normal import path. Both projects were
31,073,710 bytes with the same object/mesh/face/material counts, matching content
and a zero-pixel-difference EEVEE render. Full process times were 4.01 and 4.05
seconds; no total-import timing improvement was established on this small scene.

Automated regressions cover the generated Boolean flags and buffer format,
the complete pinned importer patch and mismatch guards, and normal preservation
for referenced, distinct, animated or shared data, including mismatch rollback:

```sh
python tools/test_miex_material_lookup.py
python tools/test_pinned_miex_importer.py
python tools/test_redundant_normals.py
python tools/test_blender_scene_performance.py
python tools/test_import_selection.py
python tools/test_miex_layout_lookup.py
```

## Changes excluded under the no-tradeoff constraint

An incoming-link cache reduced layout time on a 402-node / 798-link material
graph from roughly 0.53 to 0.14 seconds, but increased measured Python scratch
memory from 346,512 to 510,024 bytes. It was excluded because that exchanges
memory for speed.

No additional file-size reduction was accepted in this pass. Scene compression,
broader geometry/attribute cleanup and combining independently editable data
would require a save/load or editing tradeoff. Existing optional cleanup remains
optional; the saved scene's storage size is unchanged by these buffer changes.

## Further pass against `e3b85be`

Two more changes run automatically during normal imports, without changing
saved geometry, shader graphs, named attributes, object boundaries or settings:

| Operation | Change | Blender 5.2.3 measurement |
| --- | --- | --- |
| Scene framing | Read each coordinate once and update extrema only when needed, replacing repeated Python `min`/`max` calls. Equal values and NaNs retain their previous behavior. | 9,801 instances, seven alternating samples: median 0.0844 → 0.0607 seconds (about 28% faster for framing). Bounds and peak Python scratch memory (1,258,788 bytes) matched exactly. |
| Temporary shader-layout wrappers | Use four fixed Python slots instead of a dictionary on each private wrapper. Real Blender nodes and sockets are unchanged. | 402 nodes / 798 links: peak Python scratch memory 320,936 → 301,704 bytes (about 6% lower), with identical node positions. Twenty alternating samples had nearly equal median times, 0.565 and 0.563 seconds; no timing gain is claimed. |

Full baseline/candidate imports retained 298 scene objects, 248 mesh datablocks,
69,505 mesh faces and 223 materials. Both `.blend` files were 29,046,730 bytes;
full process times were 4.46 and 4.55 seconds, so this fixture establishes no
total-import speed gain. Mesh attributes/native normals, object content and
transforms, material graphs, image references and viewport settings matched.
As in the earlier comparison, duplicate USD object-name suffixes were normalized;
a repeated baseline independently exhibited that existing assignment variation.
An EEVEE render at 480×360 and 16 samples had zero pixel difference.

### Existing compact-USD path repaired

The `Export_World.ps1 -CompactUSD` converter imported an unbundled
`Optimize_USD_Prototypes` helper before starting Crate conversion, causing the
entire operation to stop with `ModuleNotFoundError`. It now proceeds with the
existing lossless Crate conversion when that optional helper is absent. If the
helper is present, its existing behavior remains supported. Unrelated import
errors still propagate. This does not add a prototype-sharing implementation.

| Fixture | USD bytes before | USD bytes after | Saving |
| --- | ---: | ---: | ---: |
| Java visual fixture | 2,390,152 | 880,501 | 63.2% |
| Bedrock visual fixture | 9,769,498 | 3,859,554 | 60.5% |

OpenUSD reopened every layer and produced exactly the same canonical layer
data before/after conversion, including authored values, types and references.
All ten layers matched. The other 57 Java / 224 Bedrock files were byte-identical,
and the source comparison exports stayed unchanged. Automated tests retain the
smaller-only replacement rule, repeated-run behavior and present-helper path.
Compaction keeps its existing opt-in activation and conversion work; these
storage figures apply to USD files, not saved `.blend` projects.

## Further pass: Viewport FPS, modifier evaluation and modern Blender compatibility

Four additional refinements run automatically during imports and existing project optimizations:

| Operation | Change | Rationale and Verification |
| --- | --- | --- |
| Evaluated bounds fast-path | Skip scene-wide dependency graph evaluation when modified objects have viewport evaluation disabled (`show_viewport = False`), are hidden in viewport (`hide_viewport = True`), or are invisible in the active view layer (`hide_get() == True` / `visible_get() == False`). | When viewport evaluation is disabled on all modifiers of an object or it is hidden in the view layer, its visible viewport extents cannot differ from stored bounds. Automated unit test `test_blender_bounds_fastpath.py` verifies active, disabled, view-layer hidden, and collection-hidden modifier cases. |
| Empty point-cloud modifier disabling | Also disable modifier viewport evaluation (`show_viewport = False`) on empty point clouds that were already hidden, and invoke this before dependency graph evaluation during scene framing. | Catches empty point clouds in previously saved or user-toggled projects where an empty point cloud was hidden but its Geometry Nodes modifier graph still evaluated. Bypasses redundant modifier execution before Blender builds the depsgraph for scene framing. Unit test `test_viewport_fps_optimizations.py` validates both unhidden and pre-hidden objects. |
| Modern Blender material compatibility | Replace deprecated `Material.use_nodes` property accesses with `getattr(material, 'node_tree', None) is not None` across texture audit, water materials, normal compaction, and display color cleanup. | Eliminates `DeprecationWarning: 'Material.use_nodes' is expected to be removed in Blender 6.0` on Blender 5.2+ while preserving exact material node-tree filtering. Verified on Blender 5.2.3 LTS. |
| Scene framing instance cache | Increase the cached prototype instance bounding box corners capacity from 512 to 4,096 instances. | Avoids thrashing and recalculating corner tuples for scenes with hundreds of instanced prototype collections (e.g. Night Blades Survival with 844 collection instances). Retains exact visible extents framing. |
| Batch hierarchy & material caching | Cache evaluated parent ancestry decisions and opaque material checks during static mesh batching with safe duck-typed ID fallback. | Eliminates quadratic parent hierarchy traversal across thousands of chunk meshes and redundant string parsing for material classification. Verified in `test_fast_viewport.py` and real Blender export tests. |
| Single-pass material slot remapping | Perform in-place face material remapping in a single pass with early loop termination on stale face indices. | Halves the iteration and array scanning passes over per-polygon face arrays while strictly preserving face assignments and skipping corrupted meshes safely. |
| Reusable scene mesh counting | Accept precomputed mesh counts in `avoid_drawing_chunk_outlines()` when available from previous scene reporting. | Eliminates redundant full scene traversals during post-import viewport setup while maintaining zero-argument backwards compatibility. |



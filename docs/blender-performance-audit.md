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

# Blender import memory audit

The comparison starts at `b54c283`, using Blender 5.2.3 LTS on Windows.
The accepted changes reduce temporary Python allocations while retaining the
same scene data and settings. They apply to new imports and to the existing
optional normal-compaction pass. They do not claim a loaded-viewport FPS gain.

## Accepted changes

| Operation | Before | After | Verification |
| --- | --- | --- | --- |
| Set every imported polygon to flat shading | A Python list containing one `False` reference per face | A contiguous Boolean memoryview with one zero byte per face | Every flag remains false, including empty meshes. The patch requires an exact match against the pinned importer. |
| Verify redundant named corner normals before/after removal | Three full float buffers | Two buffers; reuse the native-normal buffer for the post-removal read | Keep the original source buffer for comparison and exact rollback. The existing eligibility checks and opt-in setting are unchanged. Release both buffers before the next mesh. |

## Isolated measurements

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

Automated regressions cover the generated Boolean flags and buffer format,
the complete pinned importer patch and mismatch guards, and normal preservation
for referenced, distinct, animated or shared data, including mismatch rollback:

```sh
python tools/test_miex_material_lookup.py
python tools/test_pinned_miex_importer.py
python tools/test_redundant_normals.py
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

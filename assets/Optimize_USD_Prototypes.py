"""Lossless-intent sharing of byte-identical USD mesh prototypes.

Operates on NEW MiEx export root layers, not on Minecraft block data.
Every replacement is checked using composed OpenUSD attributes and relationships
before the root layer is changed. Only meshes beneath
/world/individualBlocksBaseMeshes are eligible, and only *identical full USD
prim definitions* are shared. No polygon, UV or material is simplified.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re

_SCOPE = '    def Scope "individualBlocksBaseMeshes"'
_PARENT = re.compile(r'(?m)^ {8}def Xform "([A-Za-z_][A-Za-z_0-9]*)"\(')
_MESH = re.compile(r'(?m)^ {12}def Mesh "([A-Za-z_][A-Za-z_0-9]*)"\(')
_END_MESH = re.compile(r'(?m)^ {12}\}\s*$')


def build_deduplicated_layer(source: str):
    """Return (candidate, list of (duplicate, canonical), number of unique meshes).

    This textual pass is *never* sufficient to accept an edit: an OpenUSD
    composition-level check also runs before installation.
    """
    scope_pos = source.find(_SCOPE)
    if scope_pos < 0:
        return source, [], 0
    scope_end = source.find('\n    }', scope_pos)
    if scope_end < 0:
        raise ValueError('Cannot locate the individual-block prototype scope end')
    scope = source[scope_pos:scope_end]
    parents = list(_PARENT.finditer(scope))
    meshes = list(_MESH.finditer(scope))
    seen = {}
    replacements = []
    duplicate_pairs = []
    parent_index = -1
    for match in meshes:
        while parent_index + 1 < len(parents) and parents[parent_index + 1].start() < match.start():
            parent_index += 1
        if parent_index < 0:
            raise ValueError('Mesh found without a parent Xform')
        parent = parents[parent_index].group(1)
        mesh_name = match.group(1)
        ending = _END_MESH.search(scope, match.end())
        if ending is None:
            raise ValueError('Unterminated prototype Mesh: ' + mesh_name)
        end = ending.end()
        text = scope[match.start():end]
        # Whole prim definition including name, metadata, geometry, primvars,
        # shader binding and content. Identical bytes are a strict gate.
        key = hashlib.sha256(text.encode('utf-8')).digest()
        path = f'/world/individualBlocksBaseMeshes/{parent}/{mesh_name}'
        if key not in seen:
            seen[key] = (text, path)
            continue
        first_text, canonical_path = seen[key]
        if text != first_text:
            continue  # Guard against theoretical SHA collision.
        # A reference to a Mesh prim with the exact same authored data.
        # `instanceable` lets supporting USD importers share mesh data.
        replacement = (
            '            def Mesh "' + mesh_name + '"(\n'
            '                prepend references = <' + canonical_path + '>\n'
            '                instanceable = true\n'
            '            )\n\n'
            '            {\n            }'
        )
        replacements.append((match.start(), end, replacement))
        duplicate_pairs.append((path, canonical_path))

    if not replacements:
        return source, [], len(seen)
    chunks = []
    previous = 0
    for start, end, replacement in replacements:
        if start < previous:
            raise ValueError('Overlapping USD prototype definitions')
        chunks.extend([scope[previous:start], replacement])
        previous = end
    chunks.append(scope[previous:])
    candidate = source[:scope_pos] + ''.join(chunks) + source[scope_end:]
    return candidate, duplicate_pairs, len(seen)


# The original MiEx writer emits one PointInstancer per chunk even if there
# are no individual blocks inside it. This exact empty form authors no faces,
# positions, instances, materials or relationships to real geometry.
_EMPTY_INSTANCER = re.compile(
    r'(?m)^ {12}def PointInstancer "individual_blocks"\(\s*'
    r'kind = "subcomponent"\s*\)\s*\{\s*'
    r'rel prototypes = \[\]\s*'
    r'point3f\[\] positions = \[\]\s*'
    r'int\[\] protoIndices = \[\]\s*\}\s*'
)


def remove_empty_instancers(source: str):
    """Remove only MiEx's exact, property-free, zero-instance declarations."""
    return _EMPTY_INSTANCER.subn('', source)


def _snapshot(prim):
    if not prim or not prim.IsValid():
        return None
    attributes = tuple(sorted((a.GetName(), str(a.GetTypeName()), repr(a.Get()))
                              for a in prim.GetAttributes()))
    relationships = tuple(sorted((r.GetName(), tuple(str(p) for p in r.GetTargets()))
                                 for r in prim.GetRelationships()))
    return prim.GetTypeName(), attributes, relationships


def optimize_and_validate(root_path: Path):
    """Safely replace redundant Mesh specs, or leave the original intact."""
    from pxr import Usd  # Existing Blender OpenUSD runtime; not a new add-on.

    root_path = Path(root_path)
    raw = root_path.read_bytes()
    if not raw.startswith(b'#usda'):
        return 'Prototype sharing: skipped (root USD is not ASCII).'
    source = raw.decode('utf-8')
    candidate, duplicates, unique = build_deduplicated_layer(source)
    candidate, empty_instancers = remove_empty_instancers(candidate)
    if not duplicates and not empty_instancers:
        return f'Prototype sharing: no duplicates found ({unique} distinct mesh definitions).'

    candidate_path = root_path.with_name('._MiEx_v1_prototypes_candidate.usda')
    if candidate_path.exists():
        candidate_path.unlink()
    try:
        candidate_path.write_text(candidate, encoding='utf-8', newline='')
        # Do not load heavy terrain payloads to validate a small root-layer edit.
        baseline = Usd.Stage.Open(str(root_path), Usd.Stage.LoadNone)
        proposed = Usd.Stage.Open(str(candidate_path), Usd.Stage.LoadNone)
        if baseline is None or proposed is None:
            raise ValueError('OpenUSD could not open both root stages')
        for duplicate, canonical in duplicates:
            before = _snapshot(baseline.GetPrimAtPath(duplicate))
            after = _snapshot(proposed.GetPrimAtPath(duplicate))
            if before is None or before != after:
                raise ValueError('Composed mesh changed at ' + duplicate)
            if _snapshot(proposed.GetPrimAtPath(canonical)) is None:
                raise ValueError('Missing canonical geometry at ' + canonical)
        # Removed instancers are provably inert: the exact three USD arrays
        # above are empty and the prim contains no other data or children.
        # The duplicate Mesh check compares all resulting composed attrs/UVs.
        del baseline, proposed
        bytes_saved = len(raw) - candidate_path.stat().st_size
        if bytes_saved <= 0:
            return 'Prototype sharing: skipped (would not reduce root layer size).'
        os.replace(candidate_path, root_path)
        return (f'Prototype sharing: {len(duplicates)} byte-identical mesh definitions '
                f'now internally referenced ({unique} unique originals); '
                f'{empty_instancers} empty PointInstancers removed; '
                f'ASCII root reduced by {bytes_saved:,} bytes. '
                'All composed meshes, UVs, vertex data and material links checked by OpenUSD.')
    finally:
        if candidate_path.exists():
            candidate_path.unlink()

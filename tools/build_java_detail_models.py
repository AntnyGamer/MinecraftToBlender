"""Generate Java statue poses and conduit activation from pinned geometric facts.

Reference: official Java 26.1.2 client SHA1
4e618f09a0c649dde3fdf829df443ce0b8831e65 (CopperGolemModel,
CopperGolemStatueBlockRenderer and ConduitBlockEntity). No images are bundled.
"""
import argparse
import copy
import json
import math
from pathlib import Path

from build_bedrock_detail_models import cube, write
from java_statue_parts import PARTS


def quaternion(rx, ry, rz):
    sx, sy, sz = (math.sin(v/2) for v in (rx, ry, rz))
    cx, cy, cz = (math.cos(v/2) for v in (rx, ry, rz))
    values = [sx*cy*cz-cx*sy*sz, cx*sy*cz+sx*cy*sz,
              cx*cy*sz-sx*sy*cz, cx*cy*cz+sx*sy*sz]
    # MiEx's expression parser does not interpret scientific notation as a
    # numeric literal. Keep tiny quaternion components in decimal notation.
    return [format(v, '.12f') if 0 < abs(v) < .0001 else v for v in values]


def java_cube(origin, size, uv, inflate):
    element = cube(origin, [origin[i]+size[i] for i in range(3)], uv, [64, 64], inflate=inflate)
    faces = element['faces']
    result = {'up': faces['down'], 'down': faces['up']}
    for direction, source in (('west', 'west'), ('east', 'east'), ('north', 'south'), ('south', 'north')):
        face = copy.deepcopy(faces[source])
        u0, v0, u1, v1 = face['uv']
        face['uv'] = [u1, v1, u0, v0]
        result[direction] = face
    element['faces'] = result
    return element


def statues(assets):
    doc = copy.deepcopy(json.loads((assets/'Bedrock_Copper_Statues.json').read_text()))
    h = doc['handler']
    h['variables'].append("pose = thisBlock.state.pose != null ? thisBlock.state.pose : 'standing'")
    h.pop('elements')
    h['transform'] = {'pivot': [0, 0, 0], 'rotate': [0, 'rotY', 0], 'translate': [8, 0, 8]}
    h['children'] = []
    for name, rows in PARTS.items():
        root = {'condition': "pose == '"+name+"'",
                'transform': {'pivot': [0, 0, 0], 'quaternion': [0, 0, 1, 0]}, 'children': []}
        parts = {'': root}
        for path, pose, cubes in rows:
            part = {'transform': {'pivot': [0, 0, 0], 'translate': list(pose[:3]),
                                  'quaternion': quaternion(*pose[3:])}, 'elements': [], 'children': []}
            for origin, size, uv, inflate in cubes:
                part['elements'].append(java_cube(origin, size, uv, inflate))
            parts[path] = part
            parts[path.rsplit('/', 1)[0]]['children'].append(part)
        h['children'].append(root)
    return doc


def conduits(assets):
    doc = copy.deepcopy(json.loads((assets/'Bedrock_Conduits.json').read_text()))
    old = doc['handler']
    # Java computes activation from surrounding water/frame blocks instead of
    # persisting Bedrock's Active field. Match its 3x3x3 water test and >=16
    # accepted frame blocks; retain the frame count for the existing eye model.
    water = []
    for x in (-1, 0, 1):
        for y in (-1, 0, 1):
            for z in (-1, 0, 1):
                if (x, y, z) == (0, 0, 0):
                    continue
                water += [f"waterBlock = Block.getBlockRelative({x}, {y}, {z})",
                          "active = active && ((waterBlock.name == 'minecraft:water') || "
                          "(waterBlock.name == 'minecraft:bubble_column') || "
                          "(waterBlock.state.waterlogged == true))"]
    frame = old[2].pop('variables')
    doc['handler'] = [
        {'variables': ['active = thisBlock.state.waterlogged == true']},
        {'condition': 'active', 'variables': water},
        {'condition': 'active', 'variables': frame+['active = frameCount >= 16']},
        old[1], old[2],
    ]
    return doc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, default=Path('assets'))
    parser.add_argument('--output', type=Path, default=Path('assets'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    write(args.output, 'Java_Copper_Statues.json', statues(args.assets))
    write(args.output, 'Java_Conduits.json', conduits(args.assets))


if __name__ == '__main__':
    main()

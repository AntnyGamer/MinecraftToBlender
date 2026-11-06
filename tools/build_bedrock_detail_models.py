"""Reproduce the Bedrock detail overrides from geometric facts and pinned MiEx.

Geometry/UV reference: Mojang client 26.1.2 SHA1
4e618f09a0c649dde3fdf829df443ce0b8831e65 (DecoratedPotRenderer,
ConduitRenderer, PiglinHeadModel). Dragon geometry and the base skull/armor
models use the BSD-licensed pinned MiEx source. No texture images are bundled.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile
import urllib.request

MIEX_REVISION='631e9fc2fde8c749bf59d4c3495492e62a83ef6c'
POSE_URL='https://raw.githubusercontent.com/Mojang/bedrock-samples/15701fa9c13923f12662984c32c124327e40e3d3/resource_pack/animations/armor_stand.animation.json'
PINS={
    'blockstates/chest.json':'7d30ec21d1e56ba181d9ba96a6c7a37874fcd03d4470df9df1ce0733d21fa408',
    'blockstates/skull.json':'26a12e4ab979c8d99ace0747518c9843976d5723095ab90b21472e52125f2e4f',
    'entities/armor_stand.json':'19d749f5c30007e2e90c8823f0dc3dd913d15bce6667227689878506b169733d',
    'attachments/boots.json':'6d1698973511b4a2d8987ab08ece702840d35f171cece425af2b9202436fff31',
    'attachments/chestplate.json':'bb82803728cfc7cd48e672bd5811e8706443d995749175772be664daac613b87',
    'attachments/helmet.json':'bfee2a8c419172bc3177b1f032ee5e5388ca2f9e696cf6e51f5034a6ed4de990',
    'attachments/leggings.json':'c03ca17c27f5b1c38f6a85293396ac05c25a076c6c6828ad44d7f7d67fc6a5df',
}
POSE_SHA256='aadf88fda50a36a1d174e16f28269b0eccd97fb082017e7f86cf804829e812fc'
COPPER_GEOMETRY_URL='https://raw.githubusercontent.com/Mojang/bedrock-samples/15701fa9c13923f12662984c32c124327e40e3d3/resource_pack/models/entity/copper_golem.geo.json'
COPPER_GEOMETRY_SHA256='9dd2bc04eb9c9cb87d6787c82c207aa0acc444a24ab8dd3fc212681cc5f731dc'


def verified(data, sha):
    data=data.replace(b'\r\n',b'\n').rstrip()+b'\n'
    if hashlib.sha256(data).hexdigest()!=sha:raise ValueError('Unrecognized pinned model reference')
    return data


def cube(lo, hi, uv, atlas, texture='texture', inflate=0, directions=None):
    x, y, z = (hi[i] - lo[i] for i in range(3))
    u, v = uv
    boxes = {'up': [u+z,v,u+z+x,v+z], 'down': [u+z+x,v+z,u+z+x+x,v],
             'west': [u,v+z,u+z,v+z+y], 'south': [u+z,v+z,u+z+x,v+z+y],
             'east': [u+z+x,v+z,u+z+x+z,v+z+y],
             'north': [u+z+x+z,v+z,u+z+x+z+x,v+z+y]}
    return {'from': [n-inflate for n in lo], 'to': [n+inflate for n in hi],
            'faces': {d: {'uv': [a*16/atlas[i%2] for i,a in enumerate(b)],
                           'texture': "'#"+texture+"'"}
                      for d,b in boxes.items() if directions is None or d in directions}}


def write(root, name, value):
    (root / name).write_text(json.dumps(value, indent=4) + '\n', encoding='utf-8', newline='\n')


def skulls(source):
    doc = json.loads((source/'blockstates/skull.json').read_text())
    doc['blocks'] = ['minecraft:'+n for n in doc['blocks']]
    doc['blocks'] += ['minecraft:'+n for n in ('dragon_head','dragon_wall_head','piglin_head','piglin_wall_head')]
    h = doc['handler']
    h['variables'] = [v.replace("thisBlock.state.rotation != null ?", "((!isWall) && (thisBlock.state.rotation != null)) ?")
                        .replace("thisBlock.name.contains('skeleton') ?", "((thisBlock.name.contains('skeleton')) && (!thisBlock.name.contains('wither_skeleton'))) ?")
                        .replace("thisBlock.name.contains('player') || thisBlock.name.contains('zombie')", "(thisBlock.name.contains('player')) || (thisBlock.name.contains('zombie'))")
                      for v in h['variables']]
    h['variables'] += ["texture = thisBlock.name.contains('dragon') ? 'minecraft:entity/enderdragon/dragon' : texture",
                       "texture = thisBlock.name.contains('piglin') ? 'minecraft:entity/piglin/piglin' : texture"]
    h['children'] = [{'condition': "(!thisBlock.name.contains('dragon')) && (!thisBlock.name.contains('piglin'))",
                      'children': h['children']}]
    # MiEx's native dragon head was registered without its namespace and was
    # therefore bypassed. Preserve its seven textured components.
    parts=[([-8,0,-8],[8,16,8],[7,12.125,11,14.125],0,0),
           ([-6,4,6],[6,9,22],[11,11.9375,14.5,13.25],0,0),
           ([-6,-1.5,5.5],[6,2.5,21.5],[11,10.6875,14.5,11.9375],-10,0),
           ([3,9,18],[5,11,22],[7,15.625,7.75,16],0,0),
           ([-5,9,18],[-3,11,22],[7,15.625,7.75,16],0,180),
           ([3,16,-4],[5,20,2],[0,15.375,1,16],0,0),
           ([-5,16,-4],[-3,20,2],[3,15.375,4,16],0,0)]
    for wall in (False,True):
        children=[]
        for lo,hi,uv,rx,ry in parts:
            element={'from':[lo[0]*.75+8,lo[1]*.75+(4 if wall else 0),lo[2]*.75+(6 if wall else 9.5)],
                     'to':[hi[0]*.75+8,hi[1]*.75+(4 if wall else 0),hi[2]*.75+(6 if wall else 9.5)],
                     'entityUVs':[uv[0],16-uv[3],uv[2],16-uv[1]],'texture':"'#texture'"}
            pivot=[(element['from'][i]+element['to'][i])/2 for i in range(3)]
            children.append({'transform':{'pivot':pivot,'rotate':[rx,ry,0]},'elements':[element]})
        h['children'].append({'condition':"(thisBlock.name.contains('dragon')) && "+('isWall' if wall else '(!isWall)'), 'children':children})
        # Head, snout, tusks and separate tilted ears use the 64x64 piglin sheet.
        oy = 4 if wall else 0
        oz = 4 if wall else 8
        pieces=[cube([3,oy,oz-4],[13,oy+8,oz+4],[0,0],[64,64]),
                cube([6,oy,oz+4],[10,oy+4,oz+5],[31,1],[64,64]),
                cube([5,oy,oz+4],[6,oy+2,oz+5],[2,4],[64,64]),
                cube([10,oy,oz+4],[11,oy+2,oz+5],[2,0],[64,64])]
        ears=[]
        for x,angle,uv in ((3.5,-30,[51,6]),(12.5,30,[39,6])):
            lo=[x-1 if angle<0 else x,oy+1,oz-2];hi=[lo[0]+1,oy+6,oz+2]
            ears.append({'transform':{'pivot':[x,oy+6,oz],'rotate':[0,0,angle]},
                         'elements':[cube(lo,hi,uv,[64,64])]})
        h['children'].append({'condition':"(thisBlock.name.contains('piglin')) && "+('isWall' if wall else '(!isWall)'), 'elements':pieces,'children':ears})
    return doc


def copper_chests(source):
    doc = json.loads((source/'blockstates/chest.json').read_text(encoding='utf-8'))
    doc['blocks'] = ['minecraft:'+wax+stage+'copper_chest'
                     for wax in ('','waxed_') for stage in ('','exposed_','weathered_','oxidized_')]
    doc['defaultTexture'] = 'minecraft:entity/chest/copper'
    variables = doc['handler']['variables']
    variables[:] = [v for v in variables if not v.startswith('texBasename =')]
    variables += ["texBasename = 'copper'",
                  "texBasename = thisBlock.name.contains('exposed_') ? 'copper_exposed' : texBasename",
                  "texBasename = thisBlock.name.contains('weathered_') ? 'copper_weathered' : texBasename",
                  "texBasename = thisBlock.name.contains('oxidized_') ? 'copper_oxidized' : texBasename"]
    return doc


def copper_statues(geometry):
    # Bedrock's registry has only cardinal direction for these blocks; saved
    # non-standing poses need a verified block-entity field mapping. Restore
    # the official standing geometry rather than dropping the block entirely.
    elements=[]
    model=geometry['minecraft:geometry'][0]
    for bone in model['bones']:
        assert not bone.get('rotation'), 'Standing reference unexpectedly rotated'
        for part in bone.get('cubes',[]):
            assert not part.get('rotation') and not part.get('mirror')
            x,y,z=part['origin'];sx,sy,sz=part['size']
            # Match MiEx's native Bedrock model reader's X reflection.
            lo=[8-x-sx,y,8+z];hi=[8-x,y+sy,8+z+sz]
            elements.append(cube(lo,hi,part['uv'],[64,64],inflate=part.get('inflate',0)))
    variables=["rotY = 0.0", "rotY = thisBlock.state.facing == 'east' ? 90.0 : rotY",
               "rotY = thisBlock.state.facing == 'south' ? 180.0 : rotY",
               "rotY = thisBlock.state.facing == 'west' ? 270.0 : rotY", "stage = ''",
               "stage = thisBlock.name.contains('exposed_') ? '_exposed' : stage",
               "stage = thisBlock.name.contains('weathered_') ? '_weathered' : stage",
               "stage = thisBlock.name.contains('oxidized_') ? '_oxidized' : stage"]
    return {'blocks':['minecraft:'+wax+stage+'copper_golem_statue'
                      for wax in ('','waxed_') for stage in ('','exposed_','weathered_','oxidized_')],
            'defaultTexture':'minecraft:entity/copper_golem/copper_golem',
            'handler':{'variables':variables,
                       'textures':{'texture':"'minecraft:entity/copper_golem/copper_golem' + stage"},
                       'transform':{'rotate':[0,'rotY',0]},'elements':elements}}


def decorated_pot():
    variables=["rotY = 0.0", "rotY = thisBlock.state.facing == 'east' ? 90.0 : rotY",
               "rotY = thisBlock.state.facing == 'south' ? 180.0 : rotY", "rotY = thisBlock.state.facing == 'west' ? 270.0 : rotY",
               "sherds = thisBlock.state.sherds != null ? thisBlock.state.sherds : thisBlock.state.shards"]
    textures={'base': "'minecraft:entity/decorated_pot/decorated_pot_base'"}
    for i,side in enumerate(('back','left','right','front')):
        variables += [f"{side} = sherds != null ? sherds[{i}] : null",
                      f"{side} = {side} != null ? {side}.replace('_pottery_shard', '_pottery_sherd') : 'minecraft:brick'",
                      f"{side} = {side}.startsWith('minecraft:') ? {side}.substring(10) : 'brick'",
                      f"{side} = {side}.endsWith('_pottery_sherd') ? {side}.replace('_pottery_sherd', '_pottery_pattern') : 'decorated_pot_side'"]
        textures[side]="'minecraft:entity/decorated_pot/' + "+side
    faces={d:{'uv':[1,0,15,16],'texture':"'#"+s+"'"} for d,s in zip(('north','east','west','south'),('back','left','right','front'))}
    # Neck is rotated from Mojang's downwards model Y, including its UVs.
    neck={'transform':{'pivot':[0,0,0],'rotate':[180,0,0],'translate':[0,37,16]},
          'elements':[cube([4,17,4],[12,20,12],[0,0],[32,32],'base',-.1),
                      cube([5,20,5],[11,21,11],[0,5],[32,32],'base',.2)]}
    cap=cube([1,16,1],[15,16,15],[-14,13],[32,32],'base',directions=('up',))
    bottom=cube([1,0,1],[15,0,15],[-14,13],[32,32],'base',directions=('down',))
    return {'blocks':['minecraft:decorated_pot'],'doubleSided':True,
            'defaultTexture':'minecraft:entity/decorated_pot/decorated_pot_side',
            'handler':{'variables':variables,'textures':textures,'transform':{'rotate':[0,'rotY',0]},
                       'elements':[{'from':[1,0,1],'to':[15,16,15],'faces':faces},cap,bottom], 'children':[neck]}}


def conduit():
    frames=[]
    for x in range(-2,3):
        for y in range(-2,3):
            for z in range(-2,3):
                if ((x==0 and (abs(y)==2 or abs(z)==2)) or (y==0 and (abs(x)==2 or abs(z)==2)) or (z==0 and (abs(x)==2 or abs(y)==2))):frames.append((x,y,z))
    assert len(frames)==42
    variables=['frameCount = 0']
    for x,y,z in frames:
        variables += [f'frameBlock = Block.getBlockRelative({x}, {y}, {z}).name',
                      "frameCount = frameCount + (((frameBlock == 'minecraft:prismarine') || (frameBlock == 'minecraft:prismarine_bricks') || (frameBlock == 'minecraft:dark_prismarine') || (frameBlock == 'minecraft:sea_lantern')) ? 1 : 0)"]
    return {'blocks':['minecraft:conduit'],'isLocationDependent':True,'doubleSided':True,
            'defaultTexture':'minecraft:entity/conduit/base','handler':[
                {'variables':["active = thisBlock.state.Active == 1"]},
                {'condition':'!active','textures':{'texture':"'minecraft:entity/conduit/base'"},'elements':[cube([5,5,5],[11,11,11],[0,0],[32,16])]},
                {'condition':'active','variables':variables,
                 'textures':{'texture':"'minecraft:entity/conduit/cage'",'wind':"'minecraft:entity/conduit/wind'",'eye':"frameCount >= 42 ? 'minecraft:entity/conduit/open_eye' : 'minecraft:entity/conduit/closed_eye'"},
                 'elements':[cube([4,4,4],[12,12,12],[0,0],[32,16]),
                             cube([0,0,0],[16,16,16],[0,0],[64,32],'wind'),
                             {'from':[4,4,8.01],'to':[12,12,8.01],'faces':{'south':{'uv':[0,0,8,8],'texture':"'#eye'"}}}]}]}


def armor(source, poses):
    doc=json.loads((source/'entities/armor_stand.json').read_text())
    # Attachments already use two-sided faces. Keep that representation for
    # the whole model instead of making coincident reverse-face duplicates.
    doc['doubleSided']=True
    h=doc['handler'][0]
    h['variables']=[re.sub(r'\(\(thisEntity.state.Pose != null\) && \(thisEntity.state.Pose\.(\w+) != null\)\)',
                          r'(thisEntity.state.Pose != null ? (thisEntity.state.Pose.\1 != null) : false)',
                          v.replace('thisEntity.state.small == 1','thisEntity.state.Small == 1')) for v in h['variables']]
    h['variables'] += ["poseIndex = thisEntity.state.Pose != null ? (thisEntity.state.Pose.PoseIndex != null ? thisEntity.state.Pose.PoseIndex : -1) : -1"]
    names=['default','no','solemn','athena','brandish','honor','entertain','salute','riposte','zombie','cancan_a','cancan_b','hero']
    parts={'body':'Body','head':'Head','leftarm':'LeftArm','rightarm':'RightArm','leftleg':'LeftLeg','rightleg':'RightLeg'}
    for i,name in enumerate(names):
        bones=poses['animations']['animation.armor_stand.'+name+'_pose']['bones']
        for bone,field in parts.items():
            for axis,raw in zip('XYZ',bones[bone]['rotation']):
                m=re.fullmatch(r'-this\s*(?:([+-])\s*([0-9.]+))?',raw)
                if not m:raise ValueError(raw)
                angle=(float(m[2])*(-1 if m[1]=='-' else 1)) if m[2] else 0.0
                # MiEx's built-in model uses Java's head/limb axes.
                if axis in 'XY':angle=-angle
                if angle==0:angle=0.0
                var=field[0].lower()+field[1:]+'Rot'+axis
                h['variables'].append(f'{var} = ((poseIndex == {i}) ? (thisEntity.state.Pose.{field} == null) : false) ? {angle} : {var}')
    def visit(node):
        if isinstance(node,list):
            for child in node:visit(child)
        elif isinstance(node,dict):
            if node.get('name') in ('leftarm','rightarm'):
                left=node['name']=='leftarm'
                slot='offhand' if left else 'mainhand'
                node['children'].append({'condition':f'thisEntity.state.equipment != null ? (thisEntity.state.equipment.{slot} != null) : false',
                    'transform':{'translate':[2 if left else 14,13,8]},
                    'generators':[{'type':'item','args':{'id':f'thisEntity.state.equipment.{slot}.id',
                        'properties':f'thisEntity.state.equipment.{slot}',
                        'displayContext':"'thirdperson_lefthand'" if left else "'thirdperson_righthand'"}}]})
            for child in node.values():visit(child)
    visit(h)
    return doc


def enchanting_table():
    # A static open book uses the real cover/page geometry. The live game's
    # page animation, bobbing and player-facing direction are not saved state.
    angle=1.25
    pieces=[]
    definitions=[([-6,-5,-.005],[0,5,0],[0,0],180+math.degrees(angle),[0,0,-1]),
                 ([0,-5,-.005],[6,5,0],[16,0],-math.degrees(angle),[0,0,1]),
                 ([-1,-5,0],[1,5,0],[12,0],90,[0,0,0]),
                 ([0,-4,-.99],[5,4,.01],[0,10],math.degrees(angle),[math.sin(angle),0,0]),
                 ([0,-4,-.01],[5,4,.99],[12,10],-math.degrees(angle),[math.sin(angle),0,0])]
    for lo,hi,uv,rot,offset in definitions:
        pieces.append({'transform':{'pivot':[0,0,0],'rotate':[0,rot,0],'translate':offset},
                       'elements':[cube(lo,hi,uv,[64,32])]})
    return {'blocks':['minecraft:enchanting_table'],'defaultTexture':'minecraft:block/enchanting_table_top',
        'handler':[{'generators':[{'type':'model','args':{'model':"'minecraft:block/enchanting_table'"}}]},
                   {'textures':{'texture':"'minecraft:entity/enchantment/enchanting_table_book'"},
                    'transform':{'pivot':[0,0,0],'rotate':[0,0,80],'translate':[8,14,8]},'children':pieces}]}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--miex-source',type=Path)
    p.add_argument('--poses',type=Path)
    p.add_argument('--copper-golem-geometry',type=Path)
    p.add_argument('--output',type=Path,default=Path('assets'))
    a=p.parse_args()
    with tempfile.TemporaryDirectory() as temp:
        source=Path(temp)
        for path,sha in PINS.items():
            local=a.miex_source/'builtin_files/base_resource_pack/builtins/minecraft'/path if a.miex_source else None
            url=f'https://raw.githubusercontent.com/BramStoutProductions/MiEx/{MIEX_REVISION}/builtin_files/base_resource_pack/builtins/minecraft/{path}'
            data=local.read_bytes() if local else urllib.request.urlopen(url,timeout=45).read()
            target=source/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(verified(data,sha))
        pose_data=a.poses.read_bytes() if a.poses else urllib.request.urlopen(POSE_URL,timeout=45).read()
        poses=json.loads(verified(pose_data,POSE_SHA256))
        copper_data=a.copper_golem_geometry.read_bytes() if a.copper_golem_geometry else urllib.request.urlopen(COPPER_GEOMETRY_URL,timeout=45).read()
        copper_geometry=json.loads(verified(copper_data,COPPER_GEOMETRY_SHA256))
        a.output.mkdir(exist_ok=True,parents=True)
        write(a.output,'Bedrock_Skulls.json',skulls(source))
        write(a.output,'Bedrock_Copper_Chests.json',copper_chests(source))
        write(a.output,'Bedrock_Copper_Statues.json',copper_statues(copper_geometry))
        write(a.output,'Bedrock_Decorated_Pots.json',decorated_pot())
        write(a.output,'Bedrock_Conduits.json',conduit())
        write(a.output,'Bedrock_Enchanting_Table.json',enchanting_table())
        write(a.output,'Bedrock_Armor_Stand.json',armor(source,poses))
        for name in ('boots','chestplate','helmet','leggings'):
            raw=(source/'attachments'/f'{name}.json').read_text()
            count=len(re.findall(r'\? Textures.intToRGB\(10511680\) : null',raw))
            assert count>0,name
            raw=raw.replace('? Textures.intToRGB(10511680) : null','? Textures.intToRGB(10511680) : tint')
            write(a.output,'Bedrock_Armor_'+name.title()+'.json',json.loads(raw))


if __name__=='__main__':main()

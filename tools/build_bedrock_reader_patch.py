"""Reproduce the bundled, narrowly patched class from the pinned MiEx source.

The original BSD-licensed source and JAR stay unchanged. Requires JDK 21+ only
when developing/rebuilding; the shipped app installs the compiled overlay.
"""
import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile
import urllib.request

REVISION = '631e9fc2fde8c749bf59d4c3495492e62a83ef6c'
SOURCE_SHA256 = 'c062682289fdff1b4f5ca6327febac9bf5a4f54ee4e795d7857591ea5e353ee6'
SOURCE_PATH = 'src/nl/bramstout/mcworldexporter/world/bedrock/ChunkBedrock.java'
CLASS_PATH = 'nl/bramstout/mcworldexporter/world/bedrock/ChunkBedrock.class'

NORMALIZE_BANNER = '''
    // Bedrock palette translations cannot see the block entity's dye/patterns.
    // Normalize them here, before registering the final block. Keep MiEx's
    // separate banner models so generated-texture extraData is preserved.
    private static String normalizeBedrockBanner(String name, NbtTagCompound tag) {
        NbtTag baseTag = tag.get("Base");
        if(baseTag == null || !name.endsWith("banner")) return name;
        String[] colors = {"white", "orange", "magenta", "light_blue", "yellow", "lime", "pink", "gray", "light_gray", "cyan", "purple", "blue", "brown", "green", "red", "black"};
        int color = Math.max(0, Math.min(15, 15 - baseTag.asInt()));
        NbtTag type = tag.get("Type");
        if(type != null && type.asInt() == 1) {
            // Bedrock stores the ominous pattern as Type=1 rather than a list.
            color = 0;
            String[] names = {"mr", "bs", "cs", "bo", "ms", "hh", "mc", "bo"};
            int[] dyes = {9, 8, 7, 8, 15, 8, 8, 15};
            NbtTag[] patterns = new NbtTag[names.length];
            for(int i = 0; i < names.length; ++i) {
                NbtTagCompound pattern = NbtTagCompound.newInstance("");
                pattern.addElement(NbtTagString.newInstance("Pattern", names[i]));
                pattern.addElement(NbtTagInt.newInstance("Color", dyes[i]));
                patterns[i] = pattern;
            }
            tag.addElement(NbtTagList.newInstance("Patterns", patterns));
        } else {
            NbtTag list = tag.get("Patterns");
            if(list instanceof NbtTagList) {
                for(NbtTag value : ((NbtTagList) list).getData()) {
                    if(!(value instanceof NbtTagCompound)) continue;
                    NbtTagCompound pattern = (NbtTagCompound) value;
                    NbtTag dye = pattern.get("Color");
                    if(dye != null) pattern.addElement(NbtTagInt.newInstance("Color", 15 - dye.asInt()));
                }
            }
        }
        return "minecraft:" + colors[color] + (name.contains("wall") ? "_wall_banner" : "_banner");
    }

    // Older Bedrock signs store front text at the root. Do not synthesize
    // null fields in expression dictionaries or discard a modern back side.
    private static void normalizeBedrockSign(String name, NbtTagCompound tag) {
        if(!name.contains("sign") || tag.get("FrontText") != null || tag.get("Text") == null) return;
        NbtTagCompound front = NbtTagCompound.newInstance("FrontText");
        for(String field : new String[]{"Text", "SignTextColor", "IgnoreLighting", "HideGlowOutline"}) {
            NbtTag value = tag.get(field);
            if(value != null) front.addElement(value.copy());
        }
        tag.addElement(front);
    }

'''

NORMALIZE_DETAILS = '''
    // Palette blocks have already been translated to Java state names. Running
    // the Bedrock translator again turns undyed shulkers white and wall bells
    // into floor bells. Beds need their block-entity dye before choosing an ID.
    private static String translateBedrockPalette(String name, NbtTagCompound tag, BlockTranslatorManager translator) {
        String mapped = translator.map(name, tag);
        return name.equals("minecraft:bed") || name.equals("minecraft:undyed_shulker_box") ? name : mapped;
    }

    private static void mergeBedrockBlockEntity(NbtTagCompound entity, NbtTagCompound palette) {
        // Preserve saved block-entity fields; palette state supplies orientation
        // and attachment, but must not overwrite dye or piston animation state.
        for(int i = 0; i < palette.getSize(); ++i) {
            NbtTag value = palette.get(i);
            if(entity.get(value.getName()) == null) entity.addElement(value.copy());
        }
    }

    // Palette-only translations cannot inspect the saved contents of a pot.
    private static String normalizeBedrockDetails(String name, NbtTagCompound tag, BlockTranslatorManager translator) {
        if(name.equals("minecraft:bed")) {
            NbtTag dye = tag.get("color");
            if(dye == null) dye = tag.get("Color");
            if(dye != null && dye.asInt() >= 0 && dye.asInt() < 16) {
                String[] colors = {"white", "orange", "magenta", "light_blue", "yellow", "lime", "pink", "gray", "light_gray", "cyan", "purple", "blue", "brown", "green", "red", "black"};
                name = "minecraft:" + colors[dye.asInt()] + "_bed";
            }
        }
        if(name.equals("minecraft:piston") || name.equals("minecraft:sticky_piston")) {
            NbtTag state = tag.get("State");
            if(state != null) tag.addElement(NbtTagString.newInstance("extended",
                state.asInt() == 1 || state.asInt() == 2 ? "true" : "false"));
        }
        NbtTag plantTag = tag.get("PlantBlock");
        NbtTag entityId = tag.get("id");
        boolean flowerPotEntity = entityId != null && entityId.asString().equalsIgnoreCase("FlowerPot");
        if((plantTag instanceof NbtTagCompound || flowerPotEntity) && (name.contains("potted_") || name.equals("minecraft:flower_pot"))) {
            NbtTagCompound plant = plantTag instanceof NbtTagCompound ? (NbtTagCompound) plantTag : null;
            NbtTag plantName = plant == null ? null : plant.get("name");
            NbtTag statesTag = plant == null ? null : plant.get("states");
            NbtTagCompound states = statesTag instanceof NbtTagCompound ?
                (NbtTagCompound) statesTag.copy() : NbtTagCompound.newInstance("");
            String mapped = plantName == null ? "minecraft:air" : translator.map(plantName.asString(), states);
            states.free();
            String shortName = mapped.startsWith("minecraft:") ? mapped.substring(10) : "";
            String allowed = "|oak_sapling|spruce_sapling|birch_sapling|jungle_sapling|acacia_sapling|dark_oak_sapling|cherry_sapling|pale_oak_sapling|mangrove_propagule|fern|dandelion|poppy|blue_orchid|allium|azure_bluet|red_tulip|orange_tulip|white_tulip|pink_tulip|oxeye_daisy|cornflower|lily_of_the_valley|wither_rose|red_mushroom|brown_mushroom|dead_bush|cactus|bamboo|azalea_bush|flowering_azalea_bush|crimson_fungus|warped_fungus|crimson_roots|warped_roots|torchflower|open_eyeblossom|closed_eyeblossom|golden_dandelion|poplar_sapling|";
            if(shortName.equals("azalea")) shortName = "azalea_bush";
            if(shortName.equals("flowering_azalea")) shortName = "flowering_azalea_bush";
            return !shortName.isEmpty() && allowed.contains("|" + shortName + "|") ?
                "minecraft:potted_" + shortName : "minecraft:flower_pot";
        }
        if(name.endsWith("_head") || name.endsWith("_skull")) {
            NbtTag type = tag.get("SkullType");
            if(tag.get("miex_legacy_skull") != null && type != null && type.asInt() >= 0 && type.asInt() <= 6) {
                String[] heads = {"skeleton_skull", "wither_skeleton_skull", "zombie_head", "player_head", "creeper_head", "dragon_head", "piglin_head"};
                String head = heads[type.asInt()];
                if(name.contains("_wall_")) head = head.replace("_skull", "_wall_skull").replace("_head", "_wall_head");
                name = "minecraft:" + head;
            }
            NbtTag angle = tag.get("Rotation");
            if(angle != null) tag.addElement(NbtTagString.newInstance("rotation",
                Integer.toString(Math.floorMod(Math.round(angle.asFloat() / 22.5f), 16))));
        }
        return name;
    }

    private static void copyBedrockEquipment(NbtTagCompound source, NbtTagCompound equipment, String slot) {
        if(equipment.get(slot) != null) return;
        NbtTag itemName = source.get("Name");
        if(itemName == null || itemName.asString().isEmpty() || itemName.asString().equals("minecraft:air")) return;
        NbtTag count = source.get("Count");
        if(count != null && count.asInt() <= 0) return;
        NbtTagCompound item = (NbtTagCompound) source.copy();
        item.setName(slot);
        item.addElement(NbtTagString.newInstance("id", itemName.asString()));
        NbtTag itemTag = item.get("tag");
        if(itemTag instanceof NbtTagCompound) {
            NbtTag dye = ((NbtTagCompound) itemTag).get("customColor");
            if(dye != null && item.get("customColor") == null) item.addElement(dye.copy());
        }
        equipment.addElement(item);
    }

    private static void normalizeBedrockArmorStand(String id, NbtTagCompound tag) {
        if(!id.equals("minecraft:armor_stand")) return;
        NbtTag old = tag.get("equipment");
        NbtTagCompound equipment = old instanceof NbtTagCompound ? (NbtTagCompound) old.copy() : NbtTagCompound.newInstance("equipment");
        String[] lists = {"Armor", "Mainhand", "Offhand"};
        String[][] slots = {{"head", "chest", "legs", "feet", "body"}, {"mainhand"}, {"offhand"}};
        for(int i = 0; i < lists.length; ++i) {
            NbtTag list = tag.get(lists[i]);
            if(!(list instanceof NbtTagList)) continue;
            NbtTagList values = (NbtTagList) list;
            for(int j = 0; j < Math.min(values.getSize(), slots[i].length); ++j)
                if(values.get(j) instanceof NbtTagCompound) copyBedrockEquipment((NbtTagCompound) values.get(j), equipment, slots[i][j]);
        }
        tag.addElement(equipment);
    }
'''


def patch_source(data):
    data = data.replace(b'\r\n', b'\n')
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        raise RuntimeError('Unrecognized MiEx Bedrock reader; refusing to patch')
    text = data.decode('utf-8')
    replacements = {
        'import nl.bramstout.mcworldexporter.nbt.NbtTagCompound;':
            'import nl.bramstout.mcworldexporter.nbt.NbtTagCompound;\n'
            'import nl.bramstout.mcworldexporter.nbt.NbtTagInt;\n'
            'import nl.bramstout.mcworldexporter.nbt.NbtTagList;',
        'if(blockEntitySectionY < blocks.length)':
            'if(blockEntitySectionY >= 0 && blockEntitySectionY < blocks[0].length)',
        'if(blockEntitySectionY < 0 || blockEntitySectionY >= blocks.length)':
            'if(blockEntitySectionY < 0 || blockEntitySectionY >= blocks[0].length)',
        'blockEntity.addAllElements(currentBlock.getProperties());': '''int savedShulkerFacing = -1;
                    if(blockEntityName.equalsIgnoreCase("ShulkerBox") && blockEntity.get("facing") != null)
                        savedShulkerFacing = blockEntity.get("facing").asInt();
                    mergeBedrockBlockEntity(blockEntity, currentBlock.getProperties());
                    if(savedShulkerFacing >= 0 && savedShulkerFacing <= 5)
                        blockEntity.addElement(NbtTagInt.newInstance("facing_direction", savedShulkerFacing));''',
        'blockEntityName = blockTranslatorManager.map(blockEntityName, blockEntity);':
            'if(currentBlockId <= 0) blockEntityName = blockTranslatorManager.map(blockEntityName, blockEntity);\n'
            '                    blockEntityName = normalizeBedrockBanner(blockEntityName, blockEntity);\n'
            '                    normalizeBedrockSign(blockEntityName, blockEntity);\n'
            '                    blockEntityName = normalizeBedrockDetails(blockEntityName, blockEntity, blockTranslatorManager);',
        'blockName = blockTranslatorManager.map(blockName, blockProperties);':
            'if(blockName.equals("minecraft:skull")) blockProperties.addElement(NbtTagInt.newInstance("miex_legacy_skull", 1));\n'
            '                            blockName = translateBedrockPalette(blockName, blockProperties, blockTranslatorManager);',
        'Entity entity = EntityRegistry.getEntity(identifierTag.getData(), data);':
            'normalizeBedrockArmorStand(identifierTag.getData(), data);\n'
            '            Entity entity = EntityRegistry.getEntity(identifierTag.getData(), data);',
        'Entity entity = EntityRegistry.getEntity(name, entityTag);':
            'normalizeBedrockArmorStand(name, entityTag);\n'
            '                Entity entity = EntityRegistry.getEntity(name, entityTag);',
        '\t@Override\n\tprotected void _loadEntities() throws Exception {':
            NORMALIZE_BANNER + NORMALIZE_DETAILS + '\t@Override\n\tprotected void _loadEntities() throws Exception {',
    }
    for old, new in replacements.items():
        if text.count(old) != 1:
            raise RuntimeError('Unexpected pinned Bedrock reader code: ' + old)
        text = text.replace(old, new, 1)
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jar', type=Path, required=True)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--javac', default='javac')
    parser.add_argument('--output', type=Path, default=Path('assets/Bedrock_ChunkReader.class'))
    args = parser.parse_args()
    data = args.source.read_bytes() if args.source else urllib.request.urlopen(
        f'https://raw.githubusercontent.com/BramStoutProductions/MiEx/{REVISION}/{SOURCE_PATH}', timeout=45).read()
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        src = root / 'ChunkBedrock.java'
        src.write_text(patch_source(data), encoding='utf-8', newline='\n')
        subprocess.run([args.javac, '--release', '21', '-encoding', 'UTF-8',
                        '-cp', str(args.jar.resolve()), '-d', str(root), str(src)], check=True)
        args.output.write_bytes((root / CLASS_PATH).read_bytes())
    print('Bedrock reader SHA256:', hashlib.sha256(args.output.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()

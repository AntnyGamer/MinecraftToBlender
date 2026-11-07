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
    private static final String[] BEDROCK_DYE_COLORS = {"white", "orange", "magenta", "light_blue", "yellow", "lime", "pink", "gray", "light_gray", "cyan", "purple", "blue", "brown", "green", "red", "black"};
    private static final String[] BEDROCK_OMNIOUS_NAMES = {"mr", "bs", "cs", "bo", "ms", "hh", "mc", "bo"};
    private static final int[] BEDROCK_OMNIOUS_DYES = {9, 8, 7, 8, 15, 8, 8, 15};
    private static final NbtTagList BEDROCK_OMNIOUS_PATTERNS = createBedrockOmniousPatterns();
    private static final String[] BEDROCK_SIGN_SIDES = {"FrontText", "BackText"};
    private static final String[] BEDROCK_SIGN_LEGACY_FIELDS = {"Text", "SignTextColor", "IgnoreLighting", "HideGlowOutline"};

    private static NbtTagList createBedrockOmniousPatterns() {
        NbtTag[] patterns = new NbtTag[BEDROCK_OMNIOUS_NAMES.length];
        for(int i = 0; i < BEDROCK_OMNIOUS_NAMES.length; ++i) {
            NbtTagCompound pattern = NbtTagCompound.newInstance("");
            pattern.addElement(NbtTagString.newInstance("Pattern", BEDROCK_OMNIOUS_NAMES[i]));
            pattern.addElement(NbtTagInt.newInstance("Color", BEDROCK_OMNIOUS_DYES[i]));
            patterns[i] = pattern;
        }
        return NbtTagList.newInstance("Patterns", patterns);
    }

    private static String normalizeBedrockBanner(String name, NbtTagCompound tag) {
        NbtTag baseTag = tag.get("Base");
        if(baseTag == null || !name.endsWith("banner")) return name;
        int color = Math.max(0, Math.min(15, 15 - baseTag.asInt()));
        NbtTag type = tag.get("Type");
        if(type != null && type.asInt() == 1) {
            // Bedrock stores the ominous pattern as Type=1 rather than a list.
            color = 0;
            tag.addElement(BEDROCK_OMNIOUS_PATTERNS.copy());
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
        return "minecraft:" + BEDROCK_DYE_COLORS[color] + (name.contains("wall") ? "_wall_banner" : "_banner");
    }

    // Older Bedrock signs store front text at the root. Do not synthesize
    // null fields in expression dictionaries or discard a modern back side.
    // MiEx's text mesh creator uses the active font's character widths in
    // eighths of a Minecraft font pixel, with a one-pixel inter-character gap.
    // Vanilla signs are limited to 90 pixels per line (60 on hanging signs).
    // Word-wrap across up to 4 lines when text exceeds the line width, preserving
    // color codes and styling across wrapped lines, and breaking long unbroken
    // sequences without dropping characters.
    private static String fitBedrockSignLine(String line,
            nl.bramstout.mcworldexporter.resourcepack.Font font, float widthLimit) {
        if(line.isEmpty()) return line;
        StringBuilder kept = new StringBuilder(line.length());
        float width = 0f;
        boolean bold = false;
        for(int offset = 0; offset < line.length();) {
            int cp = line.codePointAt(offset);
            if(cp == 167 && offset + 1 < line.length()) {
                int codeIndex = offset + 1;
                if(line.charAt(codeIndex) == '#') {
                    int end = Math.min(line.length(), codeIndex + 7);
                    kept.append(line, offset, end);
                    offset = end;
                    bold = false;
                    continue;
                }
                boolean undo = line.charAt(codeIndex) == '!';
                if(undo && codeIndex + 1 < line.length()) codeIndex++;
                char code = Character.toLowerCase(line.charAt(codeIndex));
                if(code == 'l') bold = !undo;
                else if(code != 'm' && code != 'n' && code != 'o') bold = false;
                kept.append(line, offset, codeIndex + 1);
                offset = codeIndex + 1;
                continue;
            }
            float charWidth = 0.625f;
            if(font != null) {
                nl.bramstout.mcworldexporter.resourcepack.Font.Character glyph =
                    font.getCharacterInfo(cp);
                if(glyph != null) charWidth = glyph.getWidth();
            }
            float advance = charWidth + (bold ? 0.125f : 0f) +
                (width > 0f ? 0.125f : 0f);
            if(width + advance > widthLimit + 0.000001f) break;
            width += advance;
            kept.appendCodePoint(cp);
            offset += Character.charCount(cp);
        }
        return kept.toString();
    }

    private static float measureBedrockSignTextWidth(String text,
            nl.bramstout.mcworldexporter.resourcepack.Font font) {
        if(text == null || text.isEmpty()) return 0f;
        float width = 0f;
        boolean bold = false;
        for(int offset = 0; offset < text.length();) {
            int cp = text.codePointAt(offset);
            if(cp == 167 && offset + 1 < text.length()) {
                int codeIndex = offset + 1;
                if(text.charAt(codeIndex) == '#') {
                    offset = Math.min(text.length(), codeIndex + 7);
                    bold = false;
                    continue;
                }
                boolean undo = text.charAt(codeIndex) == '!';
                if(undo && codeIndex + 1 < text.length()) codeIndex++;
                char code = Character.toLowerCase(text.charAt(codeIndex));
                if(code == 'l') bold = !undo;
                else if(code != 'm' && code != 'n' && code != 'o') bold = false;
                offset = codeIndex + 1;
                continue;
            }
            float charWidth = 0.625f;
            if(font != null) {
                nl.bramstout.mcworldexporter.resourcepack.Font.Character glyph =
                    font.getCharacterInfo(cp);
                if(glyph != null) charWidth = glyph.getWidth();
            }
            float advance = charWidth + (bold ? 0.125f : 0f) +
                (width > 0f ? 0.125f : 0f);
            width += advance;
            offset += Character.charCount(cp);
        }
        return width;
    }

    private static String getBedrockSignFormattingPrefix(String text, String initial) {
        String color = "";
        boolean bold = false, italic = false, underline = false, strikethrough = false, obfuscated = false;
        String combined = (initial != null && !initial.isEmpty()) ? (initial + text) : text;
        for(int i = 0; i < combined.length();) {
            int cp = combined.codePointAt(i);
            if(cp == 167 && i + 1 < combined.length()) {
                int codeIndex = i + 1;
                if(combined.charAt(codeIndex) == '#') {
                    int end = Math.min(combined.length(), codeIndex + 7);
                    color = combined.substring(i, end);
                    bold = italic = underline = strikethrough = obfuscated = false;
                    i = end;
                    continue;
                }
                boolean undo = combined.charAt(codeIndex) == '!';
                if(undo && codeIndex + 1 < combined.length()) codeIndex++;
                char c = Character.toLowerCase(combined.charAt(codeIndex));
                if(c == 'l') bold = !undo;
                else if(c == 'o') italic = !undo;
                else if(c == 'n') underline = !undo;
                else if(c == 'm') strikethrough = !undo;
                else if(c == 'k') obfuscated = !undo;
                else if(c == 'r') {
                    color = "";
                    bold = italic = underline = strikethrough = obfuscated = false;
                } else {
                    color = "§" + c;
                    bold = italic = underline = strikethrough = obfuscated = false;
                }
                i = codeIndex + 1;
                continue;
            }
            i += Character.charCount(cp);
        }
        StringBuilder sb = new StringBuilder();
        if(!color.isEmpty()) sb.append(color);
        if(bold) sb.append("§l");
        if(italic) sb.append("§o");
        if(underline) sb.append("§n");
        if(strikethrough) sb.append("§m");
        if(obfuscated) sb.append("§k");
        return sb.toString();
    }

    private static String appendBedrockWordOrBreak(String candidate, StringBuilder curLine,
            List<String> result, nl.bramstout.mcworldexporter.resourcepack.Font font,
            float widthLimit, String activePrefix) {
        while(!candidate.isEmpty() && result.size() < 4) {
            String part = fitBedrockSignLine(candidate, font, widthLimit);
            if(part.isEmpty() && !candidate.isEmpty()) {
                int cp = candidate.codePointAt(0);
                part = candidate.substring(0, Character.charCount(cp));
            }
            candidate = candidate.substring(part.length());
            if(candidate.isEmpty()) {
                curLine.append(part);
                break;
            }
            result.add(part);
            if(result.size() >= 4) break;
            activePrefix = getBedrockSignFormattingPrefix(part, activePrefix);
            candidate = activePrefix.isEmpty() ? candidate : (activePrefix + candidate);
        }
        return activePrefix;
    }

    private static List<String> wrapBedrockSignLines(String text,
            nl.bramstout.mcworldexporter.resourcepack.Font font, float widthLimit) {
        List<String> result = new ArrayList<String>(4);
        String[] paragraphs = text.split("\\\\r?\\\\n|\\\\r", -1);
        for(String para : paragraphs) {
            if(result.size() >= 4) break;
            if(para.isEmpty()) {
                result.add("");
                continue;
            }
            if(measureBedrockSignTextWidth(para, font) <= widthLimit + 0.000001f) {
                result.add(para);
                continue;
            }
            String[] words = para.split(" ", -1);
            StringBuilder curLine = new StringBuilder();
            String activePrefix = "";
            for(int i = 0; i < words.length; i++) {
                String word = words[i];
                if(word.isEmpty()) {
                    String test = curLine.toString() + " ";
                    if(measureBedrockSignTextWidth(test, font) <= widthLimit + 0.000001f) {
                        curLine.append(' ');
                    }
                    continue;
                }
                if(curLine.length() == 0 || (curLine.length() > 0 && curLine.charAt(curLine.length() - 1) == ' ' && curLine.toString().trim().isEmpty())) {
                    String candidate = curLine.length() == 0 ? (activePrefix.isEmpty() ? word : (activePrefix + word)) : (curLine.toString() + word);
                    if(curLine.length() > 0 && curLine.toString().trim().isEmpty()) {
                        curLine.setLength(0);
                    }
                    if(measureBedrockSignTextWidth(candidate, font) <= widthLimit + 0.000001f) {
                        curLine.append(candidate);
                    } else {
                        activePrefix = appendBedrockWordOrBreak(candidate, curLine, result, font, widthLimit, activePrefix);
                    }
                } else {
                    boolean endsWithSpace = curLine.charAt(curLine.length() - 1) == ' ';
                    String test = endsWithSpace ? (curLine.toString() + word) : (curLine.toString() + " " + word);
                    if(measureBedrockSignTextWidth(test, font) <= widthLimit + 0.000001f) {
                        if(!endsWithSpace) curLine.append(' ');
                        curLine.append(word);
                    } else {
                        String lineToAdd = curLine.toString();
                        while(lineToAdd.endsWith(" ")) lineToAdd = lineToAdd.substring(0, lineToAdd.length() - 1);
                        result.add(lineToAdd);
                        if(result.size() >= 4) {
                            curLine.setLength(0);
                            break;
                        }
                        activePrefix = getBedrockSignFormattingPrefix(lineToAdd, activePrefix);
                        curLine.setLength(0);
                        String candidate = activePrefix.isEmpty() ? word : (activePrefix + word);
                        if(measureBedrockSignTextWidth(candidate, font) <= widthLimit + 0.000001f) {
                            curLine.append(candidate);
                        } else {
                            activePrefix = appendBedrockWordOrBreak(candidate, curLine, result, font, widthLimit, activePrefix);
                        }
                    }
                }
            }
            if(curLine.length() > 0 && result.size() < 4) {
                String lineToAdd = curLine.toString();
                while(lineToAdd.endsWith(" ")) lineToAdd = lineToAdd.substring(0, lineToAdd.length() - 1);
                result.add(lineToAdd);
            }
        }
        return result;
    }

    private static void fitBedrockSignSide(NbtTagCompound tag,
            nl.bramstout.mcworldexporter.resourcepack.Font font, float widthLimit) {
        NbtTag text = tag.get("Text");
        if(text == null || !(text instanceof NbtTagString)) return;
        String original = text.asString();
        if(original.isEmpty()) return;
        List<String> wrapped = wrapBedrockSignLines(original, font, widthLimit);
        if(wrapped.isEmpty()) return;
        if(wrapped.size() == 1 && original.equals(wrapped.get(0))) return;
        StringBuilder formatted = new StringBuilder(original.length() + 8);
        for(int i = 0; i < wrapped.size(); i++) {
            if(i > 0) formatted.append('\\n');
            formatted.append(wrapped.get(i));
        }
        if(!original.contentEquals(formatted))
            tag.addElement(NbtTagString.newInstance("Text", formatted.toString()));
    }

    private static void normalizeBedrockSign(String name, NbtTagCompound tag) {
        if(!name.contains("sign") && !name.contains("Sign")) return;
        if(tag.get("FrontText") == null && tag.get("BackText") == null && tag.get("Text") == null) return;
        if(tag.get("FrontText") == null && tag.get("Text") != null) {
            NbtTagCompound front = NbtTagCompound.newInstance("FrontText");
            for(String field : BEDROCK_SIGN_LEGACY_FIELDS) {
                NbtTag value = tag.get(field);
                if(value != null) front.addElement(value.copy());
            }
            tag.addElement(front);
        }
        nl.bramstout.mcworldexporter.resourcepack.Font font =
            nl.bramstout.mcworldexporter.resourcepack.ResourcePacks.getFont("minecraft:default");
        float limit = (name.contains("hanging_sign") || name.contains("hangingsign") || name.contains("HangingSign")) ? 60f / 8f : 90f / 8f;
        for(String side : BEDROCK_SIGN_SIDES) {
            NbtTag value = tag.get(side);
            if(value instanceof NbtTagCompound)
                fitBedrockSignSide((NbtTagCompound) value, font, limit);
        }
        if(tag.get("Text") instanceof NbtTagString)
            fitBedrockSignSide(tag, font, limit);
    }

'''

NORMALIZE_DETAILS = '''
    // Palette blocks have already been translated to Java state names. Running
    // the Bedrock translator again turns undyed shulkers white and wall bells
    // into floor bells. Beds need their block-entity dye before choosing an ID.
    private static final String[] BEDROCK_SKULL_HEADS = {"skeleton_skull", "wither_skeleton_skull", "zombie_head", "player_head", "creeper_head", "dragon_head", "piglin_head"};
    private static final String BEDROCK_ALLOWED_PLANTS = "|oak_sapling|spruce_sapling|birch_sapling|jungle_sapling|acacia_sapling|dark_oak_sapling|cherry_sapling|pale_oak_sapling|mangrove_propagule|fern|dandelion|poppy|blue_orchid|allium|azure_bluet|red_tulip|orange_tulip|white_tulip|pink_tulip|oxeye_daisy|cornflower|lily_of_the_valley|wither_rose|red_mushroom|brown_mushroom|dead_bush|cactus|bamboo|azalea_bush|flowering_azalea_bush|crimson_fungus|warped_fungus|crimson_roots|warped_roots|torchflower|open_eyeblossom|closed_eyeblossom|golden_dandelion|poplar_sapling|";
    private static final String[] BEDROCK_ARMOR_STAND_LISTS = {"Armor", "Mainhand", "Offhand"};
    private static final String[][] BEDROCK_ARMOR_STAND_SLOTS = {{"head", "chest", "legs", "feet", "body"}, {"mainhand"}, {"offhand"}};

    private static String translateBedrockPalette(String name, NbtTagCompound tag, BlockTranslatorManager translator) {
        String mapped = translator.map(name, tag);
        if(mapped.equals("minecraft:chain") &&
           nl.bramstout.mcworldexporter.resourcepack.ResourcePacks.getBlockStateHandler(mapped) == null &&
           nl.bramstout.mcworldexporter.resourcepack.ResourcePacks.getBlockStateHandler("minecraft:iron_chain") != null)
            mapped = "minecraft:iron_chain";
        // The upstream copper-chest mappings default every block to a right
        // half. Pair coordinates are available only on the block entity.
        if(isCopperChest(mapped)) tag.addElement(NbtTagString.newInstance("type", "single"));
        return name.equals("minecraft:bed") || name.equals("minecraft:undyed_shulker_box") ? name : mapped;
    }

    private static boolean isCopperChest(String name) {
        if(!name.contains("copper_chest")) return false;
        if(name.startsWith("minecraft:waxed_")) name = "minecraft:" + name.substring(16);
        return name.equals("minecraft:copper_chest") || name.equals("minecraft:exposed_copper_chest") ||
               name.equals("minecraft:weathered_copper_chest") || name.equals("minecraft:oxidized_copper_chest");
    }

    private static void normalizeBedrockChest(String name, NbtTagCompound tag, int x, int z) {
        if(!isCopperChest(name) && !name.equals("minecraft:chest") && !name.equals("minecraft:trapped_chest")) return;
        String type = "single";
        NbtTag pairX = tag.get("pairx"), pairZ = tag.get("pairz"), facing = tag.get("facing");
        if(pairX != null && pairZ != null && facing != null) {
            int dx = pairX.asInt() - x, dz = pairZ.asInt() - z;
            String direction = facing.asString();
            if(dz == 0 && Math.abs(dx) == 1 && (direction.equals("north") || direction.equals("south")))
                type = (dx > 0) == direction.equals("north") ? "left" : "right";
            if(dx == 0 && Math.abs(dz) == 1 && (direction.equals("east") || direction.equals("west")))
                type = (dz > 0) == direction.equals("east") ? "left" : "right";
        }
        tag.addElement(NbtTagString.newInstance("type", type));
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
                name = "minecraft:" + BEDROCK_DYE_COLORS[dye.asInt()] + "_bed";
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
            if(shortName.equals("azalea")) shortName = "azalea_bush";
            if(shortName.equals("flowering_azalea")) shortName = "flowering_azalea_bush";
            return !shortName.isEmpty() && BEDROCK_ALLOWED_PLANTS.contains("|" + shortName + "|") ?
                "minecraft:potted_" + shortName : "minecraft:flower_pot";
        }
        if(name.endsWith("_head") || name.endsWith("_skull")) {
            NbtTag type = tag.get("SkullType");
            if(tag.get("miex_legacy_skull") != null && type != null && type.asInt() >= 0 && type.asInt() <= 6) {
                String head = BEDROCK_SKULL_HEADS[type.asInt()];
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
        for(int i = 0; i < BEDROCK_ARMOR_STAND_LISTS.length; ++i) {
            NbtTag list = tag.get(BEDROCK_ARMOR_STAND_LISTS[i]);
            if(!(list instanceof NbtTagList)) continue;
            NbtTagList values = (NbtTagList) list;
            for(int j = 0; j < Math.min(values.getSize(), BEDROCK_ARMOR_STAND_SLOTS[i].length); ++j)
                if(values.get(j) instanceof NbtTagCompound) copyBedrockEquipment((NbtTagCompound) values.get(j), equipment, BEDROCK_ARMOR_STAND_SLOTS[i][j]);
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
    if text.count('// Special code for chests') != 1:
        raise RuntimeError('Unexpected pinned Bedrock chest reader')
    start = text.index('// Special code for chests')
    end = text.index('blockId = BlockRegistry.getIdForName(blockEntityName, blockEntity, 0, charBuffer);', start)
    text = text[:start] + ('normalizeBedrockChest(blockEntityName, blockEntity, '
                          'blockEntityX + chunkX * 16, blockEntityZ + chunkZ * 16);\n\t\t\t\t\t') + text[end:]
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

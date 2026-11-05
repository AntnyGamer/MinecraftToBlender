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
                    blockEntity.addAllElements(currentBlock.getProperties());
                    if(savedShulkerFacing >= 0 && savedShulkerFacing <= 5)
                        blockEntity.addElement(NbtTagInt.newInstance("facing_direction", savedShulkerFacing));''',
        'blockEntityName = blockTranslatorManager.map(blockEntityName, blockEntity);':
            'blockEntityName = blockTranslatorManager.map(blockEntityName, blockEntity);\n'
            '                    blockEntityName = normalizeBedrockBanner(blockEntityName, blockEntity);\n'
            '                    normalizeBedrockSign(blockEntityName, blockEntity);',
        '\t@Override\n\tprotected void _loadEntities() throws Exception {':
            NORMALIZE_BANNER + '\t@Override\n\tprotected void _loadEntities() throws Exception {',
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

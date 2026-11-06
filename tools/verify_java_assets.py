"""Validate Java model outputs, official atlas pins and edition isolation."""
import json
import re
from pathlib import Path

from build_java_detail_models import conduits, statues


def main():
    assets = Path('assets')
    for name, build in (('Java_Copper_Statues.json', statues),
                        ('Java_Conduits.json', conduits)):
        actual = json.loads((assets / name).read_text())
        assert actual == build(assets), name
        assert actual['blocks'] and actual['handler'], name
    manifest = json.loads((assets / 'Java_Bed_Textures.json').read_text())
    assert manifest['version'] == '26.1.2'
    assert manifest['client_sha1'] == '4e618f09a0c649dde3fdf829df443ce0b8831e65'
    assert manifest['client_url'] == (
        'https://piston-data.mojang.com/v1/objects/' + manifest['client_sha1'] + '/client.jar')
    colors = 'white orange magenta light_blue yellow lime pink gray light_gray cyan purple blue brown green red black'.split()
    entries = manifest['textures']
    assert len(entries) == 16
    assert {entry['file'] for entry in entries} == {color + '.png' for color in colors}
    assert all(re.fullmatch(r'[0-9a-f]{64}', entry['sha256']) for entry in entries)
    assert len({entry['sha256'] for entry in entries}) == 16
    exporter = (assets / 'Export_World.ps1').read_text()
    helper = (assets / 'Bedrock_Assets.ps1').read_text()
    assert "$exporterPackName = 'BlenderEEVEE_' + $Edition.ToLowerInvariant()" in exporter
    assert "$script:miexExporterPackName = $exporterPackName" in exporter
    assert exporter.count("resourcePacks=@($exporterPackName,'base_resource_pack')") == 2
    assert 'Set-SharedBlockModels $miexDir $base $Edition' in exporter
    assert 'Ensure-JavaBedTextures $miexDir $javaBedTextureManifest' in exporter
    assert 'Ensure-LegacyChainModel $miexDir' in exporter
    for name in ('Java_Copper_Statues.json', 'Java_Conduits.json'):
        assert name in helper
    assert "'^minecraft:(dragon|piglin)(_wall)?_head$'" in helper
    # Preparation destinations use the edition root; the remaining legacy
    # path is read only, for reusing verified cached images/templates.
    assert "Join-Path $miexDir 'resources/BlenderEEVEE/" not in helper
    print('Java model outputs, official bed atlas pins and edition isolation validated.')


if __name__ == '__main__':
    main()

"""Static checks for Bedrock-only MiEx asset overrides and upstream pins."""
import json
import re
from pathlib import Path

ASSETS = Path("assets")


def load(name):
    return json.loads((ASSETS / name).read_text(encoding="utf-8"))


def text_of(obj):
    return json.dumps(obj, ensure_ascii=False)


def check_block_names(doc):
    assert doc["blocks"]
    assert all(name.startswith("minecraft:") for name in doc["blocks"]), doc["blocks"]


def main():
    for name in ("Bedrock_Beds.json", "Bedrock_Shulkers.json",
                 "Bedrock_Signs.json", "Bedrock_Hanging_Signs.json"):
        check_block_names(load(name))

    beds = load("Bedrock_Beds.json")
    assert "minecraft:bed" in beds["blocks"]
    bed_text = text_of(beds)
    for field in ("thisBlock.state.color", "thisBlock.state.Color",
                  "thisBlock.state.head_piece_bit", "thisBlock.state.direction"):
        assert field in bed_text, field

    # Mojang's 64x64 Bedrock geometry.bed atlas has a single 32-pixel
    # body: head uses texel rows 6..22 and foot 22..38, unlike Java's
    # separated foot UVs (old row 28..44). Leg islands are rows 38..50.
    head, foot = ({c["condition"].split("'")[1]: c
                   for c in beds["handler"]["children"]}[p]
                  for p in ("head", "foot"))
    assert head["elements"][0]["faces"]["up"]["uv"] == [1.5, 1.5, 5.5, 5.5]
    assert foot["elements"][0]["faces"]["up"]["uv"] == [1.5, 5.5, 5.5, 9.5]
    assert head["elements"][0]["faces"]["east"]["uv"] == [5.5, 1.5, 7, 5.5]
    assert foot["elements"][0]["faces"]["east"]["uv"] == [5.5, 5.5, 7, 9.5]
    for part, leg_y in ((head, 44), (foot, 38)):
        for offset, leg in zip((0, 12), part["elements"][1:]):
            assert leg["faces"]["up"]["uv"] == [
                (offset + 3)/4, leg_y/4, (offset + 6)/4, (leg_y + 3)/4]
            assert leg["faces"]["north"]["uv"] == [
                (offset + 3)/4, (leg_y + 3)/4,
                (offset + 6)/4, (leg_y + 6)/4]
            assert all("rotation" not in face for face in leg["faces"].values())

    shulkers = load("Bedrock_Shulkers.json")
    shulker_text = text_of(shulkers)
    assert "minecraft:shulker_box" in shulkers["blocks"]
    assert "thisBlock.state.facing_direction != null" in shulker_text
    for direction in range(6):
        assert f"bedrockFacing == {direction}" in shulker_text
    assert "bedrockFacing == 1 ? 0.0" in shulker_text

    # Legacy Bedrock names really appear in the user's saved block palette.
    # Missing them used to bypass otherwise correct model overrides.
    assert "minecraft:undyed_shulker_box" in shulkers["blocks"]
    assert "type == 'undyed'" in shulker_text
    signs = load("Bedrock_Signs.json")
    assert {"minecraft:standing_sign", "minecraft:wall_sign"} <= set(signs["blocks"])
    assert "ground_sign_direction" in text_of(signs)
    assert "facing_direction" in text_of(signs)

    # Bedrock hanging signs use attached_bit, not Java's attached state.
    # The attached model has the joined/single-point chain arrangement.
    hanging = load("Bedrock_Hanging_Signs.json")
    variables = hanging["handler"][0]["variables"]
    attached = [value for value in variables if value.startswith("attached = ")]
    assert attached == ["attached = thisBlock.state.attached_bit == true"]
    # Pinned MiEx's ExprParser cannot parse nested == in the true arm of
    # the previous ternary expression: it aborts resource pack initialization.
    assert all(" ? " not in line for line in attached)
    assert "attachedName = attached ? '_attached' : ''" in variables
    assert any("attachedName + '_rot_'" in value for value in variables)

    # These names aren't recognized by MiEx's Java-era banner builtin map.
    # Delegate to the actual builtin to retain patterns and vanilla UVs.
    banners = load("Bedrock_Legacy_Banners.json")
    assert {"minecraft:wall_banner", "minecraft:standing_banner"} <= set(banners["blocks"])
    assert banners["handler"]["generators"][0]["type"] == "block"
    assert "Patterns" in text_of(banners) and "bannerName" in text_of(banners)
    frame_fallback = load("Bedrock_Frame_Blocks.json")
    assert {"minecraft:frame", "minecraft:glow_frame"} <= set(frame_fallback["blocks"])
    assert frame_fallback["handler"]["generators"][0]["type"] == "entity"
    assert "thisBlock.state" in text_of(frame_fallback)

    for name in ("Bedrock_Signs.json", "Bedrock_Hanging_Signs.json"):
        doc = load(name)
        assert doc["blocks"], name
        sign_text = text_of(doc)
        assert "signText" in sign_text, name
        # Native reader normalization preserves optional fields and both sides;
        # expression dictionaries with missing/null values are unsafe in MiEx.
        assert '"state": "thisBlock.state"' in sign_text, name
        assert "'BackText':" not in sign_text, name

    manifest = load("Bedrock_Bed_Textures.json")
    assert manifest["source"] == "Mojang/bedrock-samples"
    assert re.fullmatch(r"[0-9a-f]{40}", manifest["revision"])
    assert manifest["folder"] == "resource_pack/textures/entity/bed"
    entries = manifest["textures"]
    assert len(entries) == 16
    assert {e["to"] for e in entries} == {
        f"{color}.png" for color in (
            "white", "orange", "magenta", "light_blue", "yellow", "lime",
            "pink", "gray", "light_gray", "cyan", "purple", "blue",
            "brown", "green", "red", "black"
        )
    }
    for entry in entries:
        for key in ("from", "to"):
            assert re.fullmatch(r"[a-z_]+\.png", entry[key]), entry
        assert re.fullmatch(r"[0-9a-f]{40}", entry["git_blob_sha1"]), entry

    # Mojang Bedrock's shulker sheets are 64x64 like the existing MiEx
    # model, but its silver/undyed filenames differ from MiEx's Java paths.
    shulker_manifest = load("Bedrock_Shulker_Textures.json")
    assert shulker_manifest["source"] == manifest["source"]
    assert shulker_manifest["revision"] == manifest["revision"]
    assert shulker_manifest["folder"] == "resource_pack/textures/entity/shulker"
    shulker_sheets = shulker_manifest["textures"]
    assert len(shulker_sheets) == 17
    assert len({entry["from"] for entry in shulker_sheets}) == 17
    assert len({entry["to"] for entry in shulker_sheets}) == 17
    assert {entry["to"] for entry in shulker_sheets} == {
        "shulker.png", "shulker_light_gray.png",
        *(f"shulker_{color}.png" for color in (
            "white", "orange", "magenta", "light_blue", "yellow", "lime",
            "pink", "gray", "cyan", "purple", "blue", "brown",
            "green", "red", "black"
        ))
    }
    mapping = {entry["from"]: entry["to"] for entry in shulker_sheets}
    assert mapping["shulker_silver.png"] == "shulker_light_gray.png"
    assert mapping["shulker_undyed.png"] == "shulker.png"
    for entry in shulker_sheets:
        assert re.fullmatch(r"shulker_[a-z_]+\.png", entry["from"])
        assert re.fullmatch(r"shulker(?:_[a-z_]+)?\.png", entry["to"])
        assert re.fullmatch(r"[0-9a-f]{40}", entry["git_blob_sha1"])

    exporter = (ASSETS / "Export_World.ps1").read_text(encoding="utf-8")
    assert "$env:MIEX_STORE_GEN_TEX_IN_EXPORT='1'" in exporter
    for name in ("Bedrock_Beds.json", "Bedrock_Shulkers.json",
                 "Bedrock_Signs.json", "Bedrock_Hanging_Signs.json"):
        assert name in exporter
    assert "Bedrock_Assets.ps1" in exporter
    assert "'Bedrock_Legacy_Banners.json' = 'legacy_banners.json'" in exporter
    assert "'Bedrock_Frame_Blocks.json' = 'frame_blocks.json'" in exporter
    assert "-Name 'exportEntityAsBlocks'" in exporter
    assert "entities=$true" in exporter
    for name in ("Bedrock_Skulls.json", "Bedrock_Decorated_Pots.json", "Bedrock_Conduits.json", "Bedrock_Enchanting_Table.json", "Bedrock_Copper_Chests.json", "Bedrock_Copper_Statues.json"):
        detail = load(name)
        check_block_names(detail)
        assert name in exporter
    assert "Set-BedrockDetailModels $miexDir $base $Edition" in exporter
    assert "Remove-ManagedBedrockBedTextures $miexDir $bedTextureManifest" in exporter
    # The source Bedrock sheets must be present: removing them previously
    # produced black beds because the referenced material had no usable PNG.
    assert "Ensure-BedrockBedTextures $miexDir $bedTextureManifest" in exporter
    assert "Ensure-BedrockShulkerTextures $miexDir $shulkerTextureManifest" in exporter
    assert "Remove-ManagedBedrockShulkerTextures $miexDir $shulkerTextureManifest" in exporter
    helper = (ASSETS / "Bedrock_Assets.ps1").read_text(encoding="utf-8")
    portals = load("Bedrock_End_Portals.json")
    check_block_names(portals)
    assert set(portals["blocks"]) == {"minecraft:end_portal", "minecraft:end_gateway"}
    assert "Bedrock_End_Portals.json" in exporter
    assert "Ensure-BedrockPortalTexture $miexDir $Edition" in exporter
    assert "Set-BedrockStateCorrections $miexDir $base $Edition" in exporter
    assert "7b4dbaf59ac9a115c7b6af2a1cfdbd110470255a" in helper
    connections = load("Bedrock_Block_Connections.json")[0]
    assert set(connections) == {"mappings"}  # MiEx silently ignores 'translations'.
    rules = connections["mappings"]["redstone_wire"]
    for check, action in rules[0]["connections"].items():
        assert len(action["blockState"]) == 1, check  # Never add an opposite arm at a corner.
    assert "function Test-BedrockBedAtlas" in helper
    assert "function Ensure-BedrockBedTextures" in helper
    assert "function Ensure-BedrockShulkerTextures" in helper
    assert "function Remove-ManagedBedrockShulkerTextures" in helper
    assert "Bedrock bed texture(s) missing, corrupt" in helper
    assert "[System.IO.File]::WriteAllText($frameStatePath, '{\"variants\":{}}'" not in exporter
    print("Bedrock override JSONs, Mojang texture pins, and export wiring validated.")


if __name__ == "__main__":
    main()

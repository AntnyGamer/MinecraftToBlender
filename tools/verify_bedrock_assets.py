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

    shulkers = load("Bedrock_Shulkers.json")
    shulker_text = text_of(shulkers)
    assert "minecraft:shulker_box" in shulkers["blocks"]
    for direction in range(6):
        assert f"thisBlock.state.facing_direction == {direction}" in shulker_text

    # Legacy Bedrock names really appear in the user's saved block palette.
    # Missing them used to bypass otherwise correct model overrides.
    assert "minecraft:undyed_shulker_box" in shulkers["blocks"]
    assert "type == 'undyed'" in shulker_text
    signs = load("Bedrock_Signs.json")
    assert {"minecraft:standing_sign", "minecraft:wall_sign"} <= set(signs["blocks"])
    assert "ground_sign_direction" in text_of(signs)
    assert "facing_direction" in text_of(signs)

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
        assert "thisBlock.state.Text" in sign_text, name
        assert "thisBlock.state.FrontText" in sign_text, name
        # Legacy front text can coexist with a modern back-text compound.
        # The fallback must not drop the other side of the sign.
        assert "'BackText': thisBlock.state.BackText" in sign_text, name

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

    exporter = (ASSETS / "Export_World.ps1").read_text(encoding="utf-8")
    assert "$env:MIEX_STORE_GEN_TEX_IN_EXPORT='1'" in exporter
    for name in ("Bedrock_Beds.json", "Bedrock_Shulkers.json",
                 "Bedrock_Signs.json", "Bedrock_Hanging_Signs.json"):
        assert name in exporter
    assert "Ensure-BedrockBedTextures" in exporter
    assert "Bedrock_Assets.ps1" in exporter
    assert "'Bedrock_Legacy_Banners.json' = 'legacy_banners.json'" in exporter
    assert "'Bedrock_Frame_Blocks.json' = 'frame_blocks.json'" in exporter
    assert "-Name 'exportEntityAsBlocks'" in exporter
    assert "entities=$true" in exporter
    assert "Remove-ManagedBedrockBedTextures $miexDir $bedTextureManifest" in exporter
    # The previously copied Bedrock atlas has incompatible UVs for the
    # pinned Java-style bed model. Do not reinstall it over the Java base.
    assert "Ensure-BedrockBedTextures $miexDir $bedTextureManifest" not in exporter
    assert "[System.IO.File]::WriteAllText($frameStatePath, '{\"variants\":{}}'" not in exporter
    print("Bedrock override JSONs, Mojang texture pins, and export wiring validated.")


if __name__ == "__main__":
    main()

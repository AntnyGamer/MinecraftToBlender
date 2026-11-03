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

    for name in ("Bedrock_Signs.json", "Bedrock_Hanging_Signs.json"):
        doc = load(name)
        assert doc["blocks"], name
        sign_text = text_of(doc)
        assert "signText" in sign_text, name
        assert "thisBlock.state.Text" in sign_text, name
        assert "thisBlock.state.FrontText" in sign_text, name

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
    print("Bedrock override JSONs, Mojang texture pins, and export wiring validated.")


if __name__ == "__main__":
    main()

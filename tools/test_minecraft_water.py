"""Validate opt-in, material-only Minecraft-style water in Blender imports."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS


def load_water_helpers():
    tree = ast.parse(Path("assets/Import_Existing_USD.py").read_text(encoding="utf-8"))
    names = {"is_minecraft_water_material", "apply_minecraft_water_materials"}
    helpers = [node for node in tree.body if isinstance(node, ast.FunctionDef)
               and node.name in names]
    assert len(helpers) == 2
    scope = {"log": lambda *args: None}
    exec(compile(ast.Module(body=helpers, type_ignores=[]), "<water>", "exec"), scope)
    return scope


class Links:
    def __init__(self):
        self.removed = []

    def remove(self, link):
        self.removed.append(link)


class Input:
    def __init__(self, value, links=()):
        self.default_value = value
        self.links = list(links)
        self.is_linked = bool(links)


def make_material(name, node_type="BSDF_PRINCIPLED", linked_alpha=True):
    color = Input([0.12, 0.20, 0.75, 1.0], links=["biome tinted color"])
    alpha = Input(1.0, links=["existing texture alpha"] if linked_alpha else [])
    rough = Input(0.5)
    specular = Input(0.5)
    shader = NS(type=node_type, inputs={
        "Base Color": color, "Alpha": alpha, "Roughness": rough,
        "Specular IOR Level": specular,
    })
    links = Links()
    material = NS(name=name, use_nodes=True,
                  surface_render_method="DITHERED",
                  use_transparency_overlap=True,
                  blend_method="HASHED",
                  node_tree=NS(nodes={"MAT": shader}, links=links))
    return material, shader, links


def main():
    helpers = load_water_helpers()
    is_water = helpers["is_minecraft_water_material"]
    assert is_water("MAT_minecraft_block_water_still_3ccabe12")
    assert is_water("MAT_minecraft_block_water_flow_71ac88b0")
    assert not is_water("MAT_minecraft_block_seagrass_124")
    assert not is_water("MAT_minecraft_block_water_cauldron_456")
    assert not is_water("MAT_minecraft_block_water_bucket_333")
    assert not is_water("MAT_minecraft_block_lava_still_333")
    water, shader, links = make_material("MAT_minecraft_block_water_still_abcdef")
    flowing, flow_shader, _ = make_material("MAT_minecraft_block_water_flow_abc", linked_alpha=False)
    transparent, _, _ = make_material("MAT_minecraft_block_water_flow", "BSDF_GLASS")
    grass, grass_shader, grass_links = make_material("MAT_minecraft_block_grass_block")
    helpers["apply_minecraft_water_materials"].__globals__["bpy"] = NS(
        data=NS(materials=[water, flowing, transparent, grass]))
    assert helpers["apply_minecraft_water_materials"]() == 2
    assert water.surface_render_method == "BLENDED"
    assert flowing.surface_render_method == "BLENDED"
    assert water.use_transparency_overlap is False
    assert flowing.use_transparency_overlap is False
    assert water.blend_method == "HASHED"  # Modern API supersedes this deprecated attribute.
    assert grass.surface_render_method == "DITHERED"
    assert shader.inputs["Base Color"].links == ["biome tinted color"]
    assert shader.inputs["Base Color"].default_value == [0.12, 0.20, 0.75, 1.0]
    assert shader.inputs["Alpha"].default_value == 1.0
    assert shader.inputs["Alpha"].links == ["existing texture alpha"]
    assert flow_shader.inputs["Alpha"].default_value == 0.80
    assert links.removed == []  # Original material connections must never be broken.
    assert shader.inputs["Roughness"].default_value == 0.24
    assert shader.inputs["Specular IOR Level"].default_value == 0.3
    assert grass_shader.inputs["Alpha"].default_value == 1.0
    assert grass_links.removed == []
    print("Blended water preserves texture/biome alpha and leaves unrelated materials unchanged.")


if __name__ == "__main__":
    main()

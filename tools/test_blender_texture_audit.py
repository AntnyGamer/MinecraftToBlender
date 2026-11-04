"""Verify texture diagnostics skip unnecessary relative-path expansion."""
import ast
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS


class Images:
    def __init__(self, data):
        self.data = data

    def __iter__(self):
        return iter(self.data)

    def __contains__(self, name):
        return any(item.name == name for item in self.data)


def test_texture_audit_path_resolution():
    tree = ast.parse(Path("assets/Import_Existing_USD.py").read_text(encoding="utf-8"))
    selected = [node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == "audit_imported_textures"]
    assert len(selected) == 1
    with TemporaryDirectory() as temp:
        folder = Path(temp)
        existing = folder / "existing.png"
        existing.write_bytes(b"existing")
        missing = folder / "missing.png"
        image = lambda name, path, packed=False: NS(
            name=name, filepath=str(path), source="FILE", packed_file=packed)
        images = Images([
            image("relative", "textures/stone.png"),
            image("blender_relative", "//textures/entity/bed/red.png"),
            image("available", existing),
            image("missing", missing),
            image("embedded", folder / "packed.png", packed=True),
            NS(name="_MiEx_Unreadable_Texture", filepath="", source="GENERATED", packed_file=False),
        ])
        calls = []
        logs = []
        bpy = NS(
            data=NS(images=images, materials=[
                NS(use_nodes=True, node_tree=NS(nodes=[
                    NS(type="TEX_IMAGE"), NS(type="BSDF_PRINCIPLED"), NS(type="TEX_IMAGE")
                ])),
                NS(use_nodes=False, node_tree=None),
            ]),
            path=NS(
                is_rel=lambda p: p.startswith("//"),
                abspath=lambda p: calls.append(p) or p,
            ),
        )
        namespace = dict(bpy=bpy, Path=Path, log=lambda *a: logs.append(a))
        exec(compile(ast.Module(body=selected, type_ignores=[]), "texture_audit", "exec"), namespace)
        target = folder / "World.blend"
        namespace["audit_imported_textures"](target)
        assert calls == [str(existing), str(missing)], calls
        audit = (folder / "World_texture_audit.txt").read_text(encoding="utf-8")
        assert "Image texture nodes: 2" in audit
        assert "checked external images: 2" in audit
        assert "missing: 1" in audit
        assert "relative (not checked): 2" in audit
        assert "unreadable-image fallback: True" in audit
        assert f"missing: {missing}" in audit
        assert all("relative" not in str(a) or "relative (not checked)" in str(a) for a in logs)


if __name__ == "__main__":
    test_texture_audit_path_resolution()
    print("Texture audit relative/absolute path regression passed.")

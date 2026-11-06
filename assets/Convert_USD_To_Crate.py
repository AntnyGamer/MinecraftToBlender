"""Minecraft to Blender v1 - lossless USD prototype sharing and Crate conversion.

Run via an installed Blender executable after MiEx export. The exact authored
mesh geometry, materials, texture paths and Minecraft block data are preserved;
only redundant mesh specifications and empty instancers are optimized.
Crate conversion is reversible via usdcat.
"""
import gc
import os
import sys
import pathlib
import traceback


def main():
    argv = sys.argv
    if "--" not in argv:
        raise RuntimeError("Pass -- EXPORT_DIRECTORY REPORT_PATH EXPORT_USD_FILENAME")
    args = argv[argv.index("--") + 1:]
    if len(args) != 3:
        raise RuntimeError("Expected export directory, report path and root USD filename")
    folder, report_file = pathlib.Path(args[0]).resolve(), pathlib.Path(args[1]).resolve()
    root_name = pathlib.Path(args[2]).name
    if not root_name.endswith(".usd"):
        raise RuntimeError("Expected a .usd root filename")
    if not folder.is_dir():
        raise RuntimeError("Export directory not found")
    from pxr import Sdf

    # Reuse existing Blender/OpenUSD startup: no extra Blender process, add-on,
    # or reload of MiEx terrain chunks. Blender --python may not add the script's
    # own folder to sys.path, so make the companion module lookup explicit.
    script_folder = str(pathlib.Path(__file__).resolve().parent)
    if script_folder not in sys.path:
        sys.path.insert(0, script_folder)
    try:
        from Optimize_USD_Prototypes import optimize_and_validate
    except ModuleNotFoundError as error:
        if error.name != 'Optimize_USD_Prototypes':
            raise
        optimize_and_validate = None
    prototype_summary = 'Prototype sharing: helper unavailable; original specifications retained.'
    prototype_root = folder / root_name
    if optimize_and_validate is not None and prototype_root.is_file():
        try:
            prototype_summary = optimize_and_validate(prototype_root)
        except Exception as error:
            # Reject the candidate if it cannot be proven equivalent. The source
            # root layer remains untouched and normal Crate conversion proceeds.
            prototype_summary = 'Prototype sharing rejected (root unchanged): ' + str(error)
    print(prototype_summary, flush=True)

    files = sorted(folder.rglob("*.usd"), key=lambda p: (p.name == root_name, str(p)))
    if not files:
        raise RuntimeError("No USD files to convert")
    original_bytes, result_bytes, converted, existing, small, not_smaller = 0, 0, 0, 0, 0, 0
    for path in files:
        before = path.stat().st_size
        original_bytes += before
        with path.open("rb") as f:
            signature = f.read(8)
        if signature == b"PXR-USDC":
            result_bytes += before
            existing += 1
            continue
        if not signature.startswith(b"#usda"):
            raise RuntimeError("Unknown USD format: " + str(path))
        # Keep tiny, human-readable interface layers as ASCII. Try Crate on
        # 64 KiB+ geometry layers and install it only if it is actually smaller.
        # This expands the number of medium-size mesh files eligible for
        # lossless Crate, without increasing any individual layer's disk size.
        if before < 64 * 1024:
            small += 1
            result_bytes += before
            continue
        # The .usd extension accepts either ascii or Crate binary: references
        # from the root layer continue working without path rewrites.
        dst = path.with_name(path.name + ".crate_temp.usd")
        try:
            if dst.exists():
                dst.unlink()
            layer = Sdf.Layer.FindOrOpen(str(path))
            if layer is None:
                raise RuntimeError("Cannot parse source layer " + str(path))
            ok = layer.Export(str(dst), args={"format": "usdc"})
            if not ok:
                raise RuntimeError("Sdf.Layer.Export returned false for " + str(path))
            with dst.open("rb") as f:
                magic = f.read(8)
            if magic != b"PXR-USDC":
                raise RuntimeError("Destination is not Crate binary: " + str(path))
            check = Sdf.Layer.FindOrOpen(str(dst))
            if check is None:
                raise RuntimeError("Cannot re-open binary layer: " + str(path))
            # Verify prim specs and relative sublayer references remained intact.
            if [p.name for p in check.rootPrims] != [p.name for p in layer.rootPrims]:
                raise RuntimeError("Root prim names changed during conversion: " + str(path))
            if list(check.subLayerPaths) != list(layer.subLayerPaths):
                raise RuntimeError("Sublayer paths changed during conversion: " + str(path))
            del check, layer
            gc.collect()
            new_size = dst.stat().st_size
            if new_size >= before:
                not_smaller += 1
                result_bytes += before
                continue
            os.replace(dst, path)
            result_bytes += new_size
            converted += 1
            if converted % 10 == 0:
                print("Crate converted", converted, "USD layers", flush=True)
        finally:
            if dst.exists():
                dst.unlink()

    saved = original_bytes - result_bytes
    percent = saved / original_bytes * 100 if original_bytes else 0
    summary = (f"Crate conversion OK: {converted} layers converted, {existing} already binary, "
               f"{small} small ASCII retained, {not_smaller} without size savings; "
               f"bytes {original_bytes:,} -> {result_bytes:,} "
               f"({percent:.1f}% smaller). All .usd paths preserved.")
    report_file.write_text(prototype_summary + "\n" + summary + "\n", encoding="utf-8")
    print(summary, flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)

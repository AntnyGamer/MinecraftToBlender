"""Rasterize the SVG logo to a multiresolution Windows ICO without dependencies."""

from pathlib import Path
import struct
import xml.etree.ElementTree as ET
import zlib

ROOT = Path(__file__).resolve().parents[1]
SIZES = (16, 24, 32, 48, 64, 128, 256)
SVG = "{http://www.w3.org/2000/svg}"


def rgb(element):
    value = element.attrib["fill"].lstrip("#")
    return tuple(bytes.fromhex(value))


def polygon_contains(x, y, points):
    inside = False
    px, py = points[-1]
    for qx, qy in points:
        if (qy > y) != (py > y) and x < (px - qx) * (y - qy) / (py - qy) + qx:
            inside = not inside
        px, py = qx, qy
    return inside


def render(size, rect, faces):
    samples = 8 if size <= 24 else 4
    rx, ry, rw, rh, radius, bg = rect
    pixels = bytearray()
    for y in range(size):
        pixels.append(0)  # PNG filter: None
        for x in range(size):
            sums = [0, 0, 0]
            opaque = 0
            for sy in range(samples):
                py = 128 * (y + (sy + 0.5) / samples) / size
                for sx in range(samples):
                    px = 128 * (x + (sx + 0.5) / samples) / size
                    if not (rx <= px < rx + rw and ry <= py < ry + rh):
                        continue
                    cx = min(max(px, rx + radius), rx + rw - radius)
                    cy = min(max(py, ry + radius), ry + rh - radius)
                    if (px - cx) ** 2 + (py - cy) ** 2 > radius ** 2:
                        continue
                    color = bg
                    for points, fill in faces:
                        if polygon_contains(px, py, points):
                            color = fill
                    opaque += 1
                    for i in range(3):
                        sums[i] += color[i]
            if opaque:
                pixels.extend(round(value / opaque) for value in sums)
                pixels.append(round(255 * opaque / (samples * samples)))
            else:
                pixels.extend((0, 0, 0, 0))
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    header = struct.pack(">2I5B", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(pixels, 9)) + chunk(b"IEND", b"")


def main():
    root = ET.parse(ROOT / "branding" / "logo.svg").getroot()
    box = root.find(SVG + "rect")
    rect = (*(float(box.attrib[k]) for k in ("x", "y", "width", "height", "rx")), rgb(box))
    faces = []
    for element in root.findall(SVG + "polygon"):
        points = [tuple(map(float, item.split(","))) for item in element.attrib["points"].split()]
        faces.append((points, rgb(element)))
    out = ROOT / "winres"
    out.mkdir(exist_ok=True)
    images = [(size, render(size, rect, faces)) for size in SIZES]
    # An ICO stores a separate raster for each size; Windows picks the closest.
    offset = 6 + 16 * len(images)
    entries = []
    for size, data in images:
        entries.append(struct.pack("<4B2H2I", size % 256, size % 256, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    (out / "app.ico").write_bytes(struct.pack("<3H", 0, 1, len(images)) + b"".join(entries) + b"".join(data for _, data in images))


if __name__ == "__main__":
    main()

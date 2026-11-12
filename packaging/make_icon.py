"""Draw the app icon (stdlib only) and write packaging/icon.ico (PNG-in-ICO, 16-256 px).

A dark rounded square with a gold ring and a shop-bag-like diamond, in the web UI colors.
"""
from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

BG = (17, 19, 26)
GOLD = (224, 178, 90)
GOLD_DARK = (150, 112, 44)


def _pixel(x: float, y: float, n: int) -> tuple[int, int, int, int]:
    """Colour at (x, y) in a unit square, anti-aliased by the caller via supersampling."""
    r = 0.2  # corner radius of the background square
    dx, dy = max(abs(x - 0.5) - (0.5 - r), 0), max(abs(y - 0.5) - (0.5 - r), 0)
    if dx * dx + dy * dy > r * r:
        return (0, 0, 0, 0)
    d = math.hypot(x - 0.5, y - 0.5)
    if 0.30 <= d <= 0.38:                       # ring
        return (*GOLD, 255)
    if abs(x - 0.5) + abs(y - 0.53) <= 0.17:    # diamond
        return (*(GOLD if y < 0.53 else GOLD_DARK), 255)
    if abs(x - 0.5) <= 0.035 and 0.18 <= y <= 0.3:  # little stem on top of the ring
        return (*GOLD, 255)
    return (*BG, 255)


def render(n: int, ss: int = 4) -> bytes:
    rows = []
    for j in range(n):
        row = bytearray([0])  # PNG filter type 0
        for i in range(n):
            acc = [0, 0, 0, 0]
            for sj in range(ss):
                for si in range(ss):
                    p = _pixel((i + (si + 0.5) / ss) / n, (j + (sj + 0.5) / ss) / n, n)
                    for k in range(4):
                        acc[k] += p[k] if k == 3 else p[k] * p[3]
            a = acc[3]
            row += bytes([int(acc[0] / a) if a else 0, int(acc[1] / a) if a else 0,
                          int(acc[2] / a) if a else 0, a // (ss * ss)])
        rows.append(bytes(row))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    ihdr = struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


def write_ico(path: Path, sizes=(16, 24, 32, 48, 64, 128, 256)) -> None:
    images = [render(n) for n in sizes]
    out = bytearray(struct.pack("<HHH", 0, 1, len(images)))
    offset = 6 + 16 * len(images)
    for n, png in zip(sizes, images):
        out += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
    for png in images:
        out += png
    path.write_bytes(out)


if __name__ == "__main__":
    here = Path(__file__).parent
    write_ico(here / "icon.ico")
    (here / "icon-256.png").write_bytes(render(256))
    print("icon.ico written")

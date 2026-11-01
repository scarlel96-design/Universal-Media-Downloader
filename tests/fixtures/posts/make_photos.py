"""Write the fixed image bytes used by the WO-01 fixtures.

The files are deterministic. Re-running this script produces the same bytes.
"""

from __future__ import annotations

import base64
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from umd.download.images import sniff_image  # noqa: E402

PHOTOS = Path(__file__).resolve().parent / "photos"


def png(color: tuple[int, int, int], width: int = 2, height: int = 2) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def gif(color: tuple[int, int, int]) -> bytes:
    red, green, blue = color
    return (
        b"GIF89a"
        + struct.pack("<HH", 1, 1)
        + bytes([0x80, 0x00, 0x00, red, green, blue, 0x00, 0x00, 0x00])
        + b"!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
    )


# Qt-decodable fixtures. The two JPEGs and the two WebP files differ on purpose.
_JPEG_400 = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcUFhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYaKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAARCAAGAAgDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDLooorgPnD/9k="
)
_JPEG_1200 = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcUFhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYaKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAARCAAIAAwDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDhqKKK5j5o/9k="
)
_WEBP_200 = base64.b64decode("UklGRjgAAABXRUJQVlA4ICwAAADQAQCdASoGAAQAAUAmJaACdLoB+AADsAD+7U3f/ILlhdcjX/jdkKh9lAAAAA==")
_WEBP_800 = base64.b64decode("UklGRjQAAABXRUJQVlA4ICgAAABwAQCdASoKAAgAAUAmJaACdAFAAAD+pNYwmknR/8Wh/bz/g1tKAAAA")


def ensure() -> None:
    PHOTOS.mkdir(parents=True, exist_ok=True)
    files = {
        "coast.png": png((32, 96, 160), 8, 6),
        "logo.png": png((20, 40, 80), 12, 4),
        "nav-icon.png": png((10, 10, 10), 2, 2),
        "lake-400.jpg": _JPEG_400,
        "lake-1200.jpg": _JPEG_1200,
        "lazy.png": png((180, 90, 40), 6, 6),
        "panel.png": png((220, 180, 40), 4, 4),
        "dot.png": png((0, 0, 0), 1, 1),
        "thumb.png": png((90, 90, 90), 3, 3),
        "original.png": png((40, 140, 90), 8, 8),
        "pic-200.webp": _WEBP_200,
        "pic-800.webp": _WEBP_800,
        "pic-fallback.png": png((120, 60, 140), 5, 5),
        "related.png": png((160, 40, 40), 6, 4),
        "ad.png": png((200, 80, 20), 7, 3),
        "avatar.png": png((80, 50, 30), 3, 3),
        "tracker.gif": gif((1, 1, 1)),
        "widget.png": png((70, 110, 150), 5, 4),
        "tiny.png": png((30, 30, 30), 2, 2),
        "twin.png": png((255, 0, 64), 8, 6),
    }
    for name, data in files.items():
        kind = sniff_image(data[:16])
        if kind is None:
            raise RuntimeError(f"{name} has no image signature")
        (PHOTOS / name).write_bytes(data)


if __name__ == "__main__":
    ensure()
    print(f"wrote {PHOTOS}")

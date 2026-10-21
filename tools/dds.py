"""Minimal writer for uncompressed 32-bit BGRA .dds textures (what Clausewitz games load)."""
import struct


def write_dds(path, width, height, pixels):
    """pixels: list of (r, g, b, a) floats in 0..1, row-major, top row first."""
    flags = 0x1 | 0x2 | 0x4 | 0x8 | 0x1000  # CAPS | HEIGHT | WIDTH | PITCH | PIXELFORMAT
    header = struct.pack(
        "<4s7I44x",  # magic, size, flags, height, width, pitch, depth, mipmaps, 11 reserved dwords
        b"DDS ", 124, flags, height, width, width * 4, 0, 0,
    )
    pixel_format = struct.pack(
        "<2I4s5I",
        32, 0x41, b"\0\0\0\0", 32,  # size, RGB | ALPHAPIXELS, no fourcc, 32 bpp
        0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000,
    )
    caps = struct.pack("<5I", 0x1000, 0, 0, 0, 0)

    data = bytearray()
    for r, g, b, a in pixels:
        data += bytes((_byte(b), _byte(g), _byte(r), _byte(a)))

    with open(path, "wb") as f:
        f.write(header + pixel_format + caps + data)


def _byte(v):
    return max(0, min(255, round(v * 255)))

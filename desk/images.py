"""Read image dimensions without third-party packages (PNG, JPEG, ICO)."""
import struct


def size(path):
    """Return (width, height, format) or None if the file is not a readable image."""
    try:
        with open(path, "rb") as f:
            head = f.read(32)
            if head[:8] == b"\x89PNG\r\n\x1a\n":
                w, h = struct.unpack(">II", head[16:24])
                return w, h, "png"
            if head[:2] == b"\xff\xd8":
                f.seek(2)
                while True:
                    marker = f.read(2)
                    if len(marker) < 2 or marker[0] != 0xFF:
                        return None
                    if 0xC0 <= marker[1] <= 0xCF and marker[1] not in (0xC4, 0xC8, 0xCC):
                        f.read(3)
                        h, w = struct.unpack(">HH", f.read(4))
                        return w, h, "jpg"
                    length = struct.unpack(">H", f.read(2))[0]
                    f.seek(length - 2, 1)
            if head[:4] == b"\x00\x00\x01\x00":
                w, h = head[6] or 256, head[7] or 256
                return w, h, "ico"
    except OSError:
        return None
    return None

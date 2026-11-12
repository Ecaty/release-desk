"""Small image toolkit without third-party packages: PNG read/write, area resize, crop, alpha compositing,
baseline JPEG and PNG-in-ICO writers. Images are RGBA, 8 bits per channel, rows top to bottom."""
import math
import struct
import zlib

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class Image:
    def __init__(self, width, height, data=None):
        self.width, self.height = width, height
        self.data = bytearray(data) if data is not None else bytearray(width * height * 4)
        if len(self.data) != width * height * 4:
            raise ValueError("pixel data does not match the size")

    def row(self, y):
        start = y * self.width * 4
        return self.data[start:start + self.width * 4]

    def has_alpha(self):
        return self.data[3::4] != b"\xff" * (self.width * self.height)


# PNG --------------------------------------------------------------------------------------------------------

def _paeth_row(raw, prior, bpp):
    out = bytearray(raw)
    for i in range(len(out)):
        a = out[i - bpp] if i >= bpp else 0
        b = prior[i]
        c = prior[i - bpp] if i >= bpp else 0
        p = a + b - c
        pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
        out[i] = (out[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
    return out


def _unfilter(kind, raw, prior, bpp):
    if kind == 0:
        return bytearray(raw)
    if kind == 2:
        return bytearray((x + y) & 255 for x, y in zip(raw, prior))
    if kind == 1:
        out = bytearray(raw)
        for i in range(bpp, len(out)):
            out[i] = (out[i] + out[i - bpp]) & 255
        return out
    if kind == 3:
        out = bytearray(raw)
        for i in range(len(out)):
            left = out[i - bpp] if i >= bpp else 0
            out[i] = (out[i] + ((left + prior[i]) >> 1)) & 255
        return out
    if kind == 4:
        return _paeth_row(raw, prior, bpp)
    raise ValueError(f"unknown PNG filter {kind}")


def read_png(path):
    with open(path, "rb") as f:
        blob = f.read()
    if blob[:8] != PNG_SIGNATURE:
        raise ValueError("not a PNG file")
    pos, idat, palette, trns = 8, [], None, None
    while pos < len(blob):
        length, kind = struct.unpack(">I4s", blob[pos:pos + 8])
        chunk = blob[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", chunk)
        elif kind == b"PLTE":
            palette = chunk
        elif kind == b"tRNS":
            trns = chunk
        elif kind == b"IDAT":
            idat.append(chunk)
        elif kind == b"IEND":
            break
    if interlace:
        raise ValueError("interlaced PNG is not supported; save it without interlacing")
    if depth not in (8, 16) and not (color == 3 and depth in (1, 2, 4)):
        raise ValueError(f"PNG bit depth {depth} is not supported")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    bits = channels * depth
    stride, bpp = (width * bits + 7) // 8, max(1, bits // 8)
    raw = zlib.decompress(b"".join(idat))
    rows, prior = [], bytearray(stride)
    for y in range(height):
        start = y * (stride + 1)
        prior = _unfilter(raw[start], raw[start + 1:start + 1 + stride], prior, bpp)
        rows.append(prior)
    data = bytearray(width * height * 4)
    for y, row in enumerate(rows):
        if depth == 16:
            row = row[0::2]
        out = y * width * 4
        if color == 6:
            data[out:out + width * 4] = row
        elif color == 2:
            data[out:out + width * 4:4] = row[0::3]
            data[out + 1:out + width * 4:4] = row[1::3]
            data[out + 2:out + width * 4:4] = row[2::3]
            data[out + 3:out + width * 4:4] = b"\xff" * width
        elif color == 0:
            for c in range(3):
                data[out + c:out + width * 4:4] = row
            data[out + 3:out + width * 4:4] = b"\xff" * width
        elif color == 4:
            for c in range(3):
                data[out + c:out + width * 4:4] = row[0::2]
            data[out + 3:out + width * 4:4] = row[1::2]
        else:
            per = 8 // depth
            mask = (1 << depth) - 1
            for x in range(width):
                index = (row[x // per] >> ((per - 1 - x % per) * depth)) & mask
                p = out + x * 4
                data[p:p + 3] = palette[index * 3:index * 3 + 3]
                data[p + 3] = trns[index] if trns and index < len(trns) else 255
    if trns and color in (0, 2) and len(trns) >= (2 if color == 0 else 6):
        key = bytes(trns[1::2][:3]) * (3 if color == 0 else 1)
        for p in range(0, len(data), 4):
            if data[p:p + 3] == key:
                data[p + 3] = 0
    return Image(width, height, data)


def _chunk(kind, body):
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)


def png_bytes(image, alpha=None):
    alpha = image.has_alpha() if alpha is None else alpha
    w = image.width
    lines = []
    for y in range(image.height):
        row = image.row(y)
        if not alpha:
            rgb = bytearray(w * 3)
            rgb[0::3], rgb[1::3], rgb[2::3] = row[0::4], row[1::4], row[2::4]
            row = rgb
        lines.append(b"\x00" + bytes(row))
    header = struct.pack(">IIBBBBB", w, image.height, 8, 6 if alpha else 2, 0, 0, 0)
    return PNG_SIGNATURE + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(b"".join(lines), 9)) + _chunk(b"IEND", b"")


def write_png(image, path, alpha=None):
    with open(path, "wb") as f:
        f.write(png_bytes(image, alpha))


# Geometry ---------------------------------------------------------------------------------------------------

def crop(image, x, y, w, h):
    if x < 0 or y < 0 or x + w > image.width or y + h > image.height:
        raise ValueError("crop outside the image")
    out = Image(w, h)
    for row in range(h):
        src = ((y + row) * image.width + x) * 4
        out.data[row * w * 4:(row + 1) * w * 4] = image.data[src:src + w * 4]
    return out


def _weights(src, dst, start=0.0, span=None):
    """Area-average contributions of source samples to each output sample (box filter when shrinking,
    linear interpolation when enlarging)."""
    span = src if span is None else span
    scale = span / dst
    table = []
    for i in range(dst):
        if scale >= 1:
            lo, hi = start + i * scale, start + (i + 1) * scale
            first, last = int(math.floor(lo)), int(math.ceil(hi))
            parts = []
            for s in range(max(0, first), min(src, last)):
                cover = min(hi, s + 1) - max(lo, s)
                if cover > 0:
                    parts.append((s, cover / scale))
        else:
            centre = start + (i + 0.5) * scale - 0.5
            left = int(math.floor(centre))
            t = centre - left
            a, b = min(max(left, 0), src - 1), min(max(left + 1, 0), src - 1)
            parts = [(a, 1 - t), (b, t)] if a != b else [(a, 1.0)]
        table.append(parts)
    return table


def resize(image, width, height, box=None):
    """Resample `box` (x, y, w, h in source pixels, fractional allowed) of the image to width × height.
    Colour is averaged with alpha weighting so transparent edges keep no dark fringe."""
    bx, by, bw, bh = box or (0, 0, image.width, image.height)
    cols = _weights(image.width, width, bx, bw)
    rows = _weights(image.height, height, by, bh)
    sw = image.width
    src = image.data
    # Premultiplied channels, one flat list per channel.
    a_all = list(src[3::4])
    planes = [[v * a for v, a in zip(src[c::4], a_all)] for c in range(3)] + [a_all]
    used = sorted({s for parts in rows for s, _ in parts})
    horizontal = {}
    for y in used:
        base = y * sw
        lines = []
        for plane in planes:
            line = plane[base:base + sw]
            lines.append([sum(line[s] * w for s, w in parts) for parts in cols])
        horizontal[y] = lines
    out = Image(width, height)
    data = out.data
    for oy, parts in enumerate(rows):
        acc = [[0.0] * width for _ in range(4)]
        for s, w in parts:
            lines = horizontal[s]
            for c in range(4):
                a, line = acc[c], lines[c]
                for x in range(width):
                    a[x] += line[x] * w
        alpha = acc[3]
        base = oy * width * 4
        for x in range(width):
            av = alpha[x]
            p = base + x * 4
            if av <= 0:
                data[p:p + 4] = b"\x00\x00\x00\x00"
                continue
            data[p] = min(255, int(acc[0][x] / av + 0.5))
            data[p + 1] = min(255, int(acc[1][x] / av + 0.5))
            data[p + 2] = min(255, int(acc[2][x] / av + 0.5))
            data[p + 3] = min(255, int(av + 0.5))
    return out


def cover(image, width, height, focus=(0.5, 0.5), zoom=1.0):
    """Scale to fill width × height (cropping the overflow), keeping the focus point (0..1 of the source)
    as close to the centre as the edges allow. zoom > 1 crops tighter."""
    scale = max(width / image.width, height / image.height) * max(1.0, zoom)
    bw, bh = width / scale, height / scale
    bx = min(max(focus[0] * image.width - bw / 2, 0), image.width - bw)
    by = min(max(focus[1] * image.height - bh / 2, 0), image.height - bh)
    if abs(scale - 1) < 1e-9 and bx == int(bx) and by == int(by):
        return crop(image, int(bx), int(by), width, height)
    return resize(image, width, height, (bx, by, bw, bh))


def contain(image, width, height):
    """Scale to fit inside width × height, keeping the aspect ratio."""
    scale = min(width / image.width, height / image.height)
    w, h = max(1, round(image.width * scale)), max(1, round(image.height * scale))
    return image if (w, h) == (image.width, image.height) else resize(image, w, h)


def trim(image):
    """Crop away fully transparent borders."""
    alpha = image.data[3::4]
    w = image.width
    rows = [y for y in range(image.height) if any(alpha[y * w:(y + 1) * w])]
    if not rows:
        return image
    cols = [x for x in range(w) if any(alpha[x::w])]
    return crop(image, cols[0], rows[0], cols[-1] - cols[0] + 1, rows[-1] - rows[0] + 1)


def paste(base, top, x, y):
    """Alpha-composite `top` onto `base` at x, y (clipped)."""
    bw = base.width
    for ty in range(max(0, -y), min(top.height, base.height - y)):
        for tx in range(max(0, -x), min(top.width, bw - x)):
            t = (ty * top.width + tx) * 4
            a = top.data[t + 3]
            if not a:
                continue
            b = ((ty + y) * bw + tx + x) * 4
            if a == 255:
                base.data[b:b + 4] = top.data[t:t + 4]
                continue
            ba = base.data[b + 3]
            out_a = a + ba * (255 - a) / 255
            for c in range(3):
                base.data[b + c] = int((top.data[t + c] * a + base.data[b + c] * ba * (255 - a) / 255) / out_a + 0.5)
            base.data[b + 3] = int(out_a + 0.5)


def flatten(image, background=(0, 0, 0)):
    """Opaque copy over a solid colour (JPEG has no alpha)."""
    out = Image(image.width, image.height)
    d, s = out.data, image.data
    for p in range(0, len(s), 4):
        a = s[p + 3]
        for c in range(3):
            d[p + c] = (s[p + c] * a + background[c] * (255 - a) + 127) // 255
        d[p + 3] = 255
    return out


# ICO --------------------------------------------------------------------------------------------------------

def _dib(image):
    """32-bit BGRA bitmap entry (bottom-up, with an empty AND mask) for small icon sizes."""
    w, h = image.width, image.height
    header = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    rows = []
    for y in range(h - 1, -1, -1):
        row = image.row(y)
        bgra = bytearray(row)
        bgra[0::4], bgra[2::4] = row[2::4], row[0::4]
        rows.append(bytes(bgra))
    mask = b"\x00" * (((w + 31) // 32) * 4 * h)
    return header + b"".join(rows) + mask


def ico_bytes(images):
    """Windows icon, largest first: 256 px as PNG (the Vista+ convention), smaller sizes as 32-bit bitmaps."""
    images = sorted(images, key=lambda i: -i.width)
    blobs = [png_bytes(i, alpha=True) if i.width >= 256 else _dib(i) for i in images]
    out = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    for image, blob in zip(images, blobs):
        out += struct.pack("<BBBBHHII", image.width % 256, image.height % 256, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    return out + b"".join(blobs)


# JPEG (baseline, 4:4:4, standard Huffman tables) -------------------------------------------------------------

_ZIGZAG = [0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5, 12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6, 7, 14,
           21, 28, 35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51, 58, 59, 52, 45, 38, 31, 39, 46, 53,
           60, 61, 54, 47, 55, 62, 63]
_LUMA_Q = [16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55, 14, 13, 16, 24, 40, 57, 69, 56, 14, 17, 22, 29,
           51, 87, 80, 62, 18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92, 49, 64, 78, 87, 103, 121,
           120, 101, 72, 92, 95, 98, 112, 100, 103, 99]
_CHROMA_Q = [17, 18, 24, 47, 99, 99, 99, 99, 18, 21, 26, 66, 99, 99, 99, 99, 24, 26, 56, 99, 99, 99, 99, 99, 47, 66, 99, 99,
             99, 99, 99, 99] + [99] * 32
_DC_L = ([0, 1, 5, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0], list(range(12)))
_DC_C = ([0, 3, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0], list(range(12)))
_AC_L = ([0, 2, 1, 3, 3, 2, 4, 3, 5, 5, 4, 4, 0, 0, 1, 0x7D], [
    0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06, 0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32,
    0x81, 0x91, 0xA1, 0x08, 0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72, 0x82, 0x09, 0x0A, 0x16,
    0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28, 0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
    0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69,
    0x6A, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89, 0x8A, 0x92, 0x93, 0x94,
    0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3, 0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
    0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9, 0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8,
    0xD9, 0xDA, 0xE1, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8,
    0xF9, 0xFA])
_AC_C = ([0, 2, 1, 2, 4, 4, 3, 4, 7, 5, 4, 4, 0, 1, 2, 0x77], [
    0x00, 0x01, 0x02, 0x03, 0x11, 0x04, 0x05, 0x21, 0x31, 0x06, 0x12, 0x41, 0x51, 0x07, 0x61, 0x71, 0x13, 0x22, 0x32, 0x81,
    0x08, 0x14, 0x42, 0x91, 0xA1, 0xB1, 0xC1, 0x09, 0x23, 0x33, 0x52, 0xF0, 0x15, 0x62, 0x72, 0xD1, 0x0A, 0x16, 0x24, 0x34,
    0xE1, 0x25, 0xF1, 0x17, 0x18, 0x19, 0x1A, 0x26, 0x27, 0x28, 0x29, 0x2A, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44,
    0x45, 0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68,
    0x69, 0x6A, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78, 0x79, 0x7A, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89, 0x8A, 0x92,
    0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3, 0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4,
    0xB5, 0xB6, 0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9, 0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6,
    0xD7, 0xD8, 0xD9, 0xDA, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8,
    0xF9, 0xFA])
_COS = [[math.cos((2 * x + 1) * u * math.pi / 16) * (math.sqrt(0.5) if u == 0 else 1) / 2 for x in range(8)] for u in range(8)]


def _codes(spec):
    counts, symbols = spec
    table, code, k = {}, 0, 0
    for length in range(1, 17):
        for _ in range(counts[length - 1]):
            table[symbols[k]] = (code, length)
            code += 1
            k += 1
        code <<= 1
    return table


def _scaled(table, quality):
    scale = 5000 / quality if quality < 50 else 200 - quality * 2
    return [min(255, max(1, (q * scale + 50) // 100)) for q in table]


class _Bits:
    def __init__(self):
        self.out, self.acc, self.n = bytearray(), 0, 0

    def put(self, code, length):
        self.acc = (self.acc << length) | code
        self.n += length
        while self.n >= 8:
            self.n -= 8
            byte = (self.acc >> self.n) & 255
            self.out.append(byte)
            if byte == 255:
                self.out.append(0)
        self.acc &= (1 << self.n) - 1

    def flush(self):
        if self.n:
            self.put((1 << (8 - self.n)) - 1, 8 - self.n)


def _magnitude(v):
    size = abs(v).bit_length()
    return size, (v if v >= 0 else v + (1 << size) - 1)


def jpeg_bytes(image, quality=92):
    image = flatten(image) if image.has_alpha() else image
    w, h = image.width, image.height
    qt = [_scaled(_LUMA_Q, quality), _scaled(_CHROMA_Q, quality)]
    dc, ac = [_codes(_DC_L), _codes(_DC_C)], [_codes(_AC_L), _codes(_AC_C)]
    planes = [[0.0] * (w * h) for _ in range(3)]
    s = image.data
    for i in range(w * h):
        r, g, b = s[i * 4], s[i * 4 + 1], s[i * 4 + 2]
        planes[0][i] = 0.299 * r + 0.587 * g + 0.114 * b - 128
        planes[1][i] = -0.168736 * r - 0.331264 * g + 0.5 * b
        planes[2][i] = 0.5 * r - 0.418688 * g - 0.081312 * b
    bits, previous = _Bits(), [0, 0, 0]
    for by in range(0, h, 8):
        for bx in range(0, w, 8):
            for comp in range(3):
                plane, table = planes[comp], 0 if comp == 0 else 1
                block = [plane[min(by + y, h - 1) * w + min(bx + x, w - 1)] for y in range(8) for x in range(8)]
                rows = [[sum(block[y * 8 + x] * _COS[u][x] for x in range(8)) for u in range(8)] for y in range(8)]
                coeff = [sum(rows[y][u] * _COS[v][y] for y in range(8)) for v in range(8) for u in range(8)]
                q = [int(round(coeff[z] / qt[table][z])) for z in _ZIGZAG]
                diff = q[0] - previous[comp]
                previous[comp] = q[0]
                size, value = _magnitude(diff)
                bits.put(*dc[table][size])
                if size:
                    bits.put(value, size)
                run = 0
                for k in range(1, 64):
                    if q[k] == 0:
                        run += 1
                        continue
                    while run > 15:
                        bits.put(*ac[table][0xF0])
                        run -= 16
                    size, value = _magnitude(q[k])
                    bits.put(*ac[table][(run << 4) | size])
                    bits.put(value, size)
                    run = 0
                if run:
                    bits.put(*ac[table][0x00])
    bits.flush()

    def segment(marker, body):
        return bytes([0xFF, marker]) + struct.pack(">H", len(body) + 2) + body

    out = b"\xff\xd8" + segment(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
    for i, table in enumerate(qt):
        out += segment(0xDB, bytes([i]) + bytes(table[z] for z in _ZIGZAG))
    out += segment(0xC0, struct.pack(">BHHB", 8, h, w, 3) + bytes([1, 0x11, 0, 2, 0x11, 1, 3, 0x11, 1]))
    for cls, index, spec in ((0, 0, _DC_L), (1, 0, _AC_L), (0, 1, _DC_C), (1, 1, _AC_C)):
        out += segment(0xC4, bytes([(cls << 4) | index]) + bytes(spec[0]) + bytes(spec[1]))
    out += segment(0xDA, bytes([3, 1, 0x00, 2, 0x11, 3, 0x11, 0, 63, 0]))
    return out + bytes(bits.out) + b"\xff\xd9"


def write_jpeg(image, path, quality=92):
    with open(path, "wb") as f:
        f.write(jpeg_bytes(image, quality))

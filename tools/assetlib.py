"""Shared asset formats for the XYBOTS editable pipeline (import, build, verify).

Every asset is described by a `Source` (address and length inside the tape image, MSX/build/images/game_0300_FFFE.bin)
and has two converters: `to_files` (import, one time) and `from_files` (build, every time, reads the EDITED files).
Nothing here regenerates art from the original on a normal build.

Colour convention of all 1 bpp PNGs: palette index 0 = background (dark grey 30,30,30), index 1 = set pixel (white).
The original data has no colour; colour is decided by the engine (TMS colour table) at run time.
"""
import hashlib
import json
import pathlib
import re
import xml.etree.ElementTree as ET

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
IMAGE_PATH = ROOT / "build/images/game_0300_FFFE.bin"
IMAGE_BASE = 0x0300
ASSETS = ROOT / "assets"
RAW = ROOT / "build/original_raw"
PALETTE = [(30, 30, 30), (255, 255, 255)]


def load_image():
    return IMAGE_PATH.read_bytes()


def rd(img, addr, n):
    assert IMAGE_BASE <= addr and addr + n <= IMAGE_BASE + len(img), hex(addr)
    return img[addr - IMAGE_BASE:addr - IMAGE_BASE + n]


def sha(b):
    return hashlib.sha256(b).hexdigest()


# ---------------------------------------------------------------------------------------------- 1 bpp PNG helpers
def bits_to_pixels(data, bpr, rows):
    """`rows` rows of `bpr` bytes, MSB = leftmost pixel -> list of rows of 0/1."""
    out = []
    for r in range(rows):
        row = []
        for b in data[r * bpr:(r + 1) * bpr]:
            row += [(b >> (7 - i)) & 1 for i in range(8)]
        out.append(row)
    return out


def pixels_to_bits(pix, x0, y0, bpr, rows):
    out = bytearray()
    for r in range(rows):
        for c in range(bpr):
            v = 0
            for i in range(8):
                v = (v << 1) | (1 if pix[y0 + r][x0 + c * 8 + i] else 0)
            out.append(v)
    return bytes(out)


def save_1bpp(path, pix, w, h):
    im = Image.new("P", (w, h), 0)
    im.putpalette([c for rgb in PALETTE for c in rgb] + [0] * (256 * 3 - 6))
    px = im.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = pix[y][x]
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, optimize=False)


def load_1bpp(path):
    """Read an indexed PNG; every non-zero index counts as a set pixel (the editing tool may re-map colours)."""
    im = Image.open(path)
    if im.mode != "P":
        raise ValueError("%s must be an indexed (palette) PNG, got %s" % (path, im.mode))
    w, h = im.size
    px = im.load()
    return [[1 if px[x, y] else 0 for x in range(w)] for y in range(h)], w, h


def blank(w, h):
    return [[0] * w for _ in range(h)]


def blit(dst, src, x0, y0):
    for y, row in enumerate(src):
        for x, v in enumerate(row):
            dst[y0 + y][x0 + x] = v


# ---------------------------------------------------------------------------------------------- catalogs
def sprite_catalog():
    """177 sprites from the analysts' source headers: [(id, addr, bytes_per_row, rows)], contiguous 0303h-219Fh."""
    items = {}
    pat = re.compile(r"^;\s*-+\s*(spr_[0-9A-F]{4}):\s*(\d+) byte\(s\)/row x (\d+) rows")
    alias = re.compile(r"^(spr_[0-9A-F]{4})\s+equ\s+0x[0-9A-Fa-f]{4}\s*;\s*(\d+) byte\(s\)/row x (\d+) rows")
    for f in sorted((ROOT / "MSX/src/game").glob("game_*.asm")):
        for ln in f.read_text().splitlines():
            m = pat.match(ln) or alias.match(ln)
            if m:
                items[m.group(1)] = (int(m.group(1)[4:], 16), int(m.group(2)), int(m.group(3)))
    cat = sorted((a, n, bpr, rows) for n, (a, bpr, rows) in items.items())
    pos = 0x0303
    for a, n, bpr, rows in cat:
        assert a == pos, "sprite catalog gap/overlap at %04X (expected %04X)" % (a, pos)
        pos += bpr * rows
    assert len(cat) == 177 and pos == 0x21A0, (len(cat), hex(pos))
    return [(n, a, bpr, rows) for a, n, bpr, rows in cat]


# tile sets: (id, address, count, description)
TILESETS = [
    ("tiles_main", 0x751C, 235, "3D-view cell tiles 8x8 (bank used by sub_7CB5/sub_A2E3, patchable base 751Ch)"),
    ("tiles_boss", 0x4B14, 53, "alternate cell tile bank 4B14h used by the boss/special rooms (sub_3039)"),
    ("font", 0x7094, 65, "text font, ZX style, glyph(c) = 6F94h + 8*c for c = 20h..60h (draw_glyph_fb_2x, glyph_to_vram)"),
    ("ui_glyphs", 0x3EB4, 8, "minimap wall patterns 3EB4h (4), markers 3ED4h/3EDCh (2), arrows 3EE4h/3EECh (2)"),
]
# small bitmaps: (id, address, count, bytes_per_row, rows, description)
SMALL = [
    ("digits", 0x2A95, 10, 1, 5, "HUD digit font 4x5 pixels in the HIGH nibble (draw_digit)"),
    ("icons", 0x2E29, 33, 1, 11, "HUD item icons 8x11 (hud_draw_icon)"),
    ("signs", 0xB469, 3, 3, 11, "DANGER side signs 24x11: right B469h, left B48Ah, rear B4ABh (blit_sign)"),
]
HUD = (0xEB00, 32, 96)   # frame buffer as loaded: HUD/top-half picture 256x96 (sent to VRAM 0000h by sub_7DDB at init)
LEVEL_TABLE = 0x3E2E
LEVELS_START, LEVELS_END = 0x4DCC, 0x6E12   # records tile this range exactly (var_6E12 follows)
N_LEVELS = 52


# ---------------------------------------------------------------------------------------------- sprites
SPR_CELL_W, SPR_CELL_H, SPR_COLS = 24, 40, 12
SPR_PAD = 2


def sprites_import(img, out):
    cat = sprite_catalog()
    rows_n = (len(cat) + SPR_COLS - 1) // SPR_COLS
    W = SPR_COLS * (SPR_CELL_W + SPR_PAD) + SPR_PAD
    H = rows_n * (SPR_CELL_H + SPR_PAD) + SPR_PAD
    pix = blank(W, H)
    meta = []
    for i, (name, addr, bpr, rows) in enumerate(cat):
        x = SPR_PAD + (i % SPR_COLS) * (SPR_CELL_W + SPR_PAD)
        y = SPR_PAD + (i // SPR_COLS) * (SPR_CELL_H + SPR_PAD)
        blit(pix, bits_to_pixels(rd(img, addr, bpr * rows), bpr, rows), x, y)
        meta.append({"id": name, "addr": "%04X" % addr, "bytes_per_row": bpr, "rows": rows, "x": x, "y": y})
    save_1bpp(out / "sprites/sprites.png", pix, W, H)
    (out / "sprites/sprites.json").write_text(json.dumps(
        {"format": "1bpp, bit7 = leftmost pixel, no mask; geometry is fixed by the engine's descriptor records "
                   "(MSX/doc/analysis/data-g.md): edit pixels only, sizes cannot change",
         "sprites": meta}, indent=1) + "\n")


def sprites_build(ed):
    meta = json.loads((ed / "sprites/sprites.json").read_text())["sprites"]
    pix, W, H = load_1bpp(ed / "sprites/sprites.png")
    patches = {}
    for s in meta:
        patches[int(s["addr"], 16)] = pixels_to_bits(pix, s["x"], s["y"], s["bytes_per_row"], s["rows"])
    return patches


# ---------------------------------------------------------------------------------------------- tilesets (8x8, TSX)
def tileset_import(img, out, tid, addr, count, desc, columns=16):
    rows_n = (count + columns - 1) // columns
    W, H = columns * 8, rows_n * 8
    pix = blank(W, H)
    for t in range(count):
        blit(pix, bits_to_pixels(rd(img, addr + 8 * t, 8), 1, 8), (t % columns) * 8, (t // columns) * 8)
    save_1bpp(out / ("tiles/%s.png" % tid), pix, W, H)
    ts = ET.Element("tileset", version="1.10", tiledversion="1.10.2", name=tid, tilewidth="8", tileheight="8",
                    tilecount=str(count), columns=str(columns))
    props = ET.SubElement(ts, "properties")
    ET.SubElement(props, "property", name="address", value="%04X" % addr)
    ET.SubElement(props, "property", name="description", value=desc)
    ET.SubElement(ts, "image", source="%s.png" % tid, width=str(W), height=str(H))
    ET.indent(ts)
    (out / ("tiles/%s.tsx" % tid)).write_bytes(ET.tostring(ts, xml_declaration=True, encoding="UTF-8") + b"\n")


def tileset_build(ed, tid, addr, count, columns=16):
    pix, W, H = load_1bpp(ed / ("tiles/%s.png" % tid))
    out = bytearray()
    for t in range(count):
        out += pixels_to_bits(pix, (t % columns) * 8, (t // columns) * 8, 1, 8)
    return {addr: bytes(out)}


# ---------------------------------------------------------------------------------------------- small bitmaps
def small_import(img, out, sid, addr, count, bpr, rows, desc):
    cw = bpr * 8
    W = count * (cw + 1) + 1
    H = rows + 2
    pix = blank(W, H)
    meta = []
    for i in range(count):
        data = rd(img, addr + i * bpr * rows, bpr * rows)
        blit(pix, bits_to_pixels(data, bpr, rows), 1 + i * (cw + 1), 1)
        meta.append({"index": i, "addr": "%04X" % (addr + i * bpr * rows), "x": 1 + i * (cw + 1), "y": 1})
    save_1bpp(out / ("ui/%s.png" % sid), pix, W, H)
    (out / ("ui/%s.json" % sid)).write_text(json.dumps(
        {"description": desc, "bytes_per_row": bpr, "rows": rows, "count": count, "items": meta}, indent=1) + "\n")


def small_build(ed, sid):
    meta = json.loads((ed / ("ui/%s.json" % sid)).read_text())
    pix, W, H = load_1bpp(ed / ("ui/%s.png" % sid))
    bpr, rows = meta["bytes_per_row"], meta["rows"]
    patches = {}
    data = bytearray()
    base = int(meta["items"][0]["addr"], 16)
    for it in meta["items"]:
        data += pixels_to_bits(pix, it["x"], it["y"], bpr, rows)
    patches[base] = bytes(data)
    if sid == "digits":   # only the high nibble is used by the engine: keep the low nibble of the original clear
        patches[base] = bytes(b & 0xF0 for b in patches[base])
    return patches


# ---------------------------------------------------------------------------------------------- HUD picture
def hud_import(img, out):
    addr, bpr, rows = HUD
    save_1bpp(out / "ui/hud_top.png", bits_to_pixels(rd(img, addr, bpr * rows), bpr, rows), bpr * 8, rows)


def hud_build(ed):
    addr, bpr, rows = HUD
    pix, W, H = load_1bpp(ed / "ui/hud_top.png")
    assert (W, H) == (bpr * 8, rows), "hud_top.png must be %dx%d" % (bpr * 8, rows)
    return {addr: pixels_to_bits(pix, 0, 0, bpr, rows)}


# ---------------------------------------------------------------------------------------------- levels (TMX)
CELL = 16


def cells_tileset(out):
    """256 tiles 16x16: the two hex digits of the cell byte (object nibble left, passage nibble right)."""
    digits = [bits_to_pixels(bytes(b & 0xF0 for b in _DIGIT_ROWS[d]), 1, 5) for d in range(16)]
    W = 16 * CELL
    pix = blank(W, W)
    for v in range(256):
        tx, ty = (v % 16) * CELL, (v // 16) * CELL
        for k, nib in enumerate((v >> 4, v & 15)):
            g = digits[nib]
            for y in range(5):
                for x in range(4):
                    if g[y][x]:
                        for dy in range(2):
                            for dx in range(2):
                                pix[ty + 3 + y * 2 + dy][tx + 1 + k * 8 + x * 2 + dx] = 1
        for i in range(CELL):   # cell border so that neighbours are distinguishable
            pix[ty][tx + i] = 1 if v >> 4 else pix[ty][tx + i]
            pix[ty + CELL - 1][tx + i] = 1 if v >> 4 else pix[ty + CELL - 1][tx + i]
    save_1bpp(out / "levels/cells.png", pix, W, W)
    ts = ET.Element("tileset", version="1.10", tiledversion="1.10.2", name="cells", tilewidth="16", tileheight="16",
                    tilecount="256", columns="16")
    p = ET.SubElement(ts, "properties")
    ET.SubElement(p, "property", name="meaning",
                  value="tile id = cell byte; high nibble = object code (FD10h table -> actor type; 0Fh warp pad, 0Eh exit pad), "
                        "low nibble = passage bits; gid = id + 1")
    ET.SubElement(ts, "image", source="cells.png", width=str(W), height=str(W))
    ET.indent(ts)
    (out / "levels/cells.tsx").write_bytes(ET.tostring(ts, xml_declaration=True, encoding="UTF-8") + b"\n")


_DIGIT_ROWS = None


def level_records(img):
    ptrs = [rd(img, LEVEL_TABLE + 2 * i, 2) for i in range(N_LEVELS)]
    ptrs = [p[0] | p[1] << 8 for p in ptrs]
    recs = []
    for i, p in enumerate(ptrs):
        w, h = rd(img, p, 2)
        cells = rd(img, p + 2, w * h)
        t = p + 2 + w * h
        start, style, n = rd(img, t, 3)
        pairs = rd(img, t + 3, 2 * n)
        end = t + 3 + 2 * n
        nxt = ptrs[i + 1] if i + 1 < N_LEVELS else LEVELS_END
        assert end == nxt, "level %d record end %04X != next %04X" % (i, end, nxt)
        recs.append({"index": i, "addr": p, "w": w, "h": h, "cells": cells, "start": start, "style": style,
                     "pairs": [(pairs[2 * k], pairs[2 * k + 1]) for k in range(n)]})
    assert ptrs[0] == LEVELS_START
    return recs


def level_import(img, out):
    global _DIGIT_ROWS
    _DIGIT_ROWS = [rd(img, 0x2A95 + 5 * d, 5) for d in range(10)] + [b"\xe0\xa0\xe0\xa0\xa0"] * 6
    # hex digits A-F are not in the game font: simple 4x5 shapes drawn here (tileset artwork only)
    hexf = {10: (0x40, 0xA0, 0xE0, 0xA0, 0xA0), 11: (0xC0, 0xA0, 0xC0, 0xA0, 0xC0), 12: (0x60, 0x80, 0x80, 0x80, 0x60),
            13: (0xC0, 0xA0, 0xA0, 0xA0, 0xC0), 14: (0xE0, 0x80, 0xC0, 0x80, 0xE0), 15: (0xE0, 0x80, 0xC0, 0x80, 0x80)}
    for d, rows in hexf.items():
        _DIGIT_ROWS[d] = bytes(rows)
    cells_tileset(out)
    for r in level_records(img):
        w, h, e = r["w"], r["h"], (16 - r["h"]) >> 1
        m = ET.Element("map", version="1.10", tiledversion="1.10.2", orientation="orthogonal", renderorder="right-down",
                       width=str(w), height=str(h), tilewidth="16", tileheight="16", infinite="0", nextlayerid="3",
                       nextobjectid=str(len(r["pairs"]) * 2 + 2))
        pr = ET.SubElement(m, "properties")
        for k, v, t in (("level", r["index"], "int"), ("start_x", r["start"] >> 4, "int"), ("start_y", r["start"] & 15, "int"),
                        ("style", r["style"], "int"),
                        ("note", "start_x/start_y: raw start room (the loader adds (16-h)/2 to y); style 0..3 selects the "
                                 "entry sub-positions at 3EA4h; warp objects: pairs of pads (source -> destination); "
                                 "cell layer = cell bytes (see cells.tsx)", "string")):
            ET.SubElement(pr, "property", name=k, type=t, value=str(v))
        ET.SubElement(m, "tileset", firstgid="1", source="cells.tsx")
        lay = ET.SubElement(m, "layer", id="1", name="cells", width=str(w), height=str(h))
        data = ET.SubElement(lay, "data", encoding="csv")
        rows = []
        for y in range(h):
            rows.append(",".join(str(r["cells"][x * h + y] + 1) for x in range(w)))
        data.text = "\n" + ",\n".join(rows) + "\n"
        og = ET.SubElement(m, "objectgroup", id="2", name="warps")
        oid = 1
        for k, (s, d) in enumerate(r["pairs"]):
            for role, val in (("src", s), ("dst", d)):
                x, y = val >> 4, (val & 15) - e
                ob = ET.SubElement(og, "object", id=str(oid), name="warp%d_%s" % (k, role), type="warp",
                                   x=str(x * CELL), y=str(y * CELL), width=str(CELL), height=str(CELL))
                pp = ET.SubElement(ob, "properties")
                ET.SubElement(pp, "property", name="pair", type="int", value=str(k))
                ET.SubElement(pp, "property", name="role", value=role)
                oid += 1
        ET.indent(m)
        (out / ("levels/level_%02d.tmx" % r["index"])).write_bytes(ET.tostring(m, xml_declaration=True, encoding="UTF-8") + b"\n")


def level_parse(path):
    m = ET.parse(path).getroot()
    w, h = int(m.get("width")), int(m.get("height"))
    props = {p.get("name"): p.get("value") for p in m.find("properties")}
    txt = m.find("layer/data").text
    gids = [int(v) for v in txt.replace("\n", "").split(",") if v.strip()]
    assert len(gids) == w * h, "%s: layer has %d cells, expected %d" % (path, len(gids), w * h)
    cells_rm = [g - 1 for g in gids]
    for c in cells_rm:
        assert 0 <= c <= 255, "%s: gid out of range" % path
    cells = bytearray(w * h)   # column-major in the game
    for y in range(h):
        for x in range(w):
            cells[x * h + y] = cells_rm[y * w + x]
    e = (16 - h) >> 1
    pairs = {}
    for ob in m.find("objectgroup"):
        pp = {p.get("name"): p.get("value") for p in ob.find("properties")}
        k = int(pp["pair"])
        x, y = int(ob.get("x")) // CELL, int(ob.get("y")) // CELL
        assert 0 <= x < w and 0 <= y < h, "%s: warp object outside the map" % path
        pairs.setdefault(k, {})[pp["role"]] = (x << 4) | (y + e)
    plist = [(pairs[k]["src"], pairs[k]["dst"]) for k in sorted(pairs)]
    start = (int(props["start_x"]) << 4) | int(props["start_y"])
    return {"w": w, "h": h, "cells": bytes(cells), "start": start, "style": int(props["style"]), "pairs": plist,
            "index": int(props["level"])}


def levels_build(ed):
    """Repack all records in order; returns patches for the records and for the pointer table 3E2Eh."""
    recs = [level_parse(ed / ("levels/level_%02d.tmx" % i)) for i in range(N_LEVELS)]
    body = bytearray()
    ptrs = []
    for r in recs:
        ptrs.append(LEVELS_START + len(body))
        body += bytes((r["w"], r["h"])) + r["cells"] + bytes((r["start"], r["style"], len(r["pairs"])))
        for s, d in r["pairs"]:
            body += bytes((s, d))
    cap = LEVELS_END - LEVELS_START
    assert len(body) <= cap, "level data is %d bytes, at most %d fit before var_6E12" % (len(body), cap)
    body += bytes(cap - len(body))   # padding (unused bytes after the last record)
    table = b"".join(bytes((p & 255, p >> 8)) for p in ptrs)
    return {LEVELS_START: bytes(body), LEVEL_TABLE: table}


# ---------------------------------------------------------------------------------------------- everything
def all_builds(ed=ASSETS):
    patches = {}
    patches.update(sprites_build(ed))
    for tid, addr, count, _ in TILESETS:
        patches.update(tileset_build(ed, tid, addr, count))
    for sid, *_ in SMALL:
        patches.update(small_build(ed, sid))
    patches.update(hud_build(ed))
    patches.update(levels_build(ed))
    return patches


# ---------------------------------------------------------------------------------------------- V9990 palette
def palette_bin(ed=ASSETS):
    """192 bytes (64 entries x R,G,B, 5 bits) for v9_palette; validated so that no channel exceeds 31."""
    d = json.loads((ed / "palette.json").read_text())
    sp = d["sub_palettes"]
    assert len(sp) == 4 and all(len(s) == 16 for s in sp), "palette.json needs 4 sub-palettes of 16 colours"
    out = bytearray()
    for s in sp:
        for r, g, b in s:
            assert 0 <= r <= 31 and 0 <= g <= 31 and 0 <= b <= 31, "palette channel out of range (0-31)"
            out += bytes((r, g, b))
    return bytes(out)

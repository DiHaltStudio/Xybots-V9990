#!/usr/bin/env python3
"""Art of the BP6 prototype: editable sheets (V9990-B1_BP6/assets) <-> VRAM atlases (V9990-B1_BP6/build/assets4).

Palette: ONE 64-colour palette (assets/palette.json, 5 bits per channel) shared by every colour sheet; pixel indices 0-63, 0 = transparent
          in sprites. Entries 0-15 are also the TMS colours the HUD / text variants are rendered with. The build refuses a sheet whose
          palette differs from palette.json: edit the palette in the sprite or tile sheet and run `make palette-from-sprites` /
          `make palette-from-tiles` (tools/palette_sync.py) to copy it to palette.json and to all the other colour sheets.
          Both players use the same atlases and colours (no player-2 tint), except player 2's own character (sprites_p2.png).
import  : ONE-TIME conversion of the baseline 1 bpp art (V9990-P1/assets) into indexed PNGs (refuses to overwrite, --force resets):
            sprites/sprites.png   same layout as the 1 bpp sheet (sprites.json copied): outline pixels = ink (4, dark blue), the solid
                                  silhouette between the first and last outline pixel of each row = paper (14, grey), elsewhere 0 = transparent
            tiles/tiles_main.png, tiles/tiles_boss.png (+ .tsx): set pixels = ink, clear pixels = paper (tiles are opaque)
            ui/signs.png + signs.json: the 3 DANGER signs 24x11 (opaque)
build   : sheets -> build/assets4/: sprites.bin + sprpos.bin (sprites packed into 256-pixel lines, skyline packing; per sprite atlas x and
          line), tiles.bin (128 lines: main, main mirrored; 32 tiles per row), boss.bin (64 lines: Master
          Xybot room direct, mirrored), signs_markers.bin, sprtab.bin
          (179 x 3 bytes: RAM address lo, hi, rows << 2 | bytes_per_row - 1), palette.bin (64 x RGB), layout.json, hero_p2.bin,
          scene_0..3.bin + scene_pal.bin (level scenery, tools/scenes.py).
          Player 2's character: sprites/sprites_p2.png (same layout as sprites.png; only the 40 player frames, sprite bank 18C2h-219Fh,
          are used) -> hero_p2.bin, the same band as the first hero_lines lines of sprites.bin (the player frames are packed first).
          Pixel format: 8 bits per pixel, 256 bytes per line (BP6). Deterministic.
Usage: assets4.py import [--force] | build
"""
import json
import pathlib
import shutil
import sys

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import assetlib as A  # noqa: E402

B = ROOT
import os
ASSETS = pathlib.Path(os.environ.get("XY_ASSETS4", B / "assets"))          # env overrides: the edit test works on temporary copies
OUT = pathlib.Path(os.environ.get("XY_ASSETS4_OUT", B / "build/assets4"))
INK, PAPER = 4, 14
SPR_COLS, SPR_CELL_W, SHELF_H = 10, 24, 40
TILE_SETS = (("tiles_main", 253), ("tiles_boss", 128))
LINE = 128


NCOL = 64                       # BP6: one 64-colour palette (5 bits per channel) shared by every colour sheet


def read_palette(ed=ASSETS):
    """assets/palette.json -> 64 [r, g, b] (0-31). The P1-era format (sub_palettes, 16 colours) is accepted and padded with black."""
    d = json.loads((ed / "palette.json").read_text())
    cols = d["colours"] if "colours" in d else d["sub_palettes"][0]
    return [list(c) for c in cols] + [[0, 0, 0]] * (NCOL - len(cols))


def write_palette(pal5, ed=ASSETS):
    (ed / "palette.json").write_text(json.dumps({
        "format": "BP6: 64 colours, RGB 5 bits per channel (0-31), shared by sprites, tiles, signs and HUD panel tiles. Pixel index 0 = "
                  "transparent in sprites. Entries 0-15 are also the TMS colour indices the HUD and text variants are rendered with. "
                  "Edit the palette in a sheet and run `make palette-from-sprites` / `make palette-from-tiles` (tools/palette_sync.py).",
        "colours": pal5}, indent=None).replace("], [", "],\n  [") + "\n")


def palette_rgb(ed=ASSETS):
    return [(r * 255 // 31, g * 255 // 31, b * 255 // 31) for r, g, b in read_palette(ed)]


def save_4bpp(path, pix, w, h, pal):
    im = Image.new("P", (w, h), 0)
    im.putpalette([c for rgb in pal for c in rgb] + [0] * ((256 - len(pal)) * 3))
    px = im.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = pix[y][x]
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, optimize=False)


def load_4bpp(path, check_palette=True):
    """Indexed PNG -> rows of indices (0-63). A colour sheet must carry the shared palette (assets/palette.json)."""
    im = Image.open(path)
    if im.mode != "P":
        raise ValueError("%s must be an indexed (palette) PNG, got %s" % (path, im.mode))
    w, h = im.size
    px = im.load()
    pix = [[px[x, y] for x in range(w)] for y in range(h)]
    bad = {v for row in pix for v in row if v >= NCOL}
    if bad:
        raise ValueError("%s uses palette indices above %d: %s" % (path, NCOL - 1, sorted(bad)))
    if check_palette:
        used = sorted({v for row in pix for v in row})
        raw = (im.getpalette() or []) + [0] * (NCOL * 3)
        ref = palette_rgb()
        diff = [i for i in used if i != 0 and [round(raw[i * 3 + c] * 31 / 255) for c in range(3)] != list(read_palette()[i])]
        if diff:
            raise ValueError("%s: palette entries %s differ from assets/palette.json - run `make palette-from-sprites` or "
                             "`make palette-from-tiles` to share one palette (first: index %d is %s here, %s in palette.json)"
                             % (path, diff, diff[0], tuple(raw[diff[0] * 3:diff[0] * 3 + 3]), ref[diff[0]]))
    return pix, w, h


# ---------------------------------------------------------------------------------------------- import
def silhouette(rows1):
    """1 bpp rows -> 4 bpp rows: outline = INK, solid fill between the first and last outline pixel of the row = PAPER, else 0."""
    out = []
    for r in rows1:
        s = [i for i, v in enumerate(r) if v]
        o = [0] * len(r)
        if s:
            for i in range(s[0], s[-1] + 1):
                o[i] = PAPER
            for i in s:
                o[i] = INK
        out.append(o)
    return out


def do_import(force):
    if any(ASSETS.glob("*/*")) and not force:
        sys.exit("V9990-B1/assets already contains files; refusing to overwrite (use --force to reset to the generated art).")
    src = A.ASSETS
    pal = palette_rgb(src)
    meta = json.loads((src / "sprites/sprites.json").read_text())
    pix1, W, H = A.load_1bpp(src / "sprites/sprites.png")
    pix = [[0] * W for _ in range(H)]
    for s in meta["sprites"]:
        x, y, w, h = s["x"], s["y"], s["bytes_per_row"] * 8, s["rows"]
        A.blit(pix, silhouette([pix1[y + r][x:x + w] for r in range(h)]), x, y)
    save_4bpp(ASSETS / "sprites/sprites.png", pix, W, H, pal)
    meta["format"] = ("4 bpp indexed PNG (palette = sub-palette 0 of palette.json); index 0 = transparent; geometry is fixed by the engine's "
                      "descriptor records: edit pixels only, sizes cannot change. Generated from the 1 bpp original with a solid silhouette "
                      "(ADR-011)")
    (ASSETS / "sprites/sprites.json").write_text(json.dumps(meta, indent=1) + "\n")
    for tid, count in TILE_SETS:
        p1, w, h = A.load_1bpp(src / ("tiles/%s.png" % tid))
        pix = [[INK if v else PAPER for v in row] for row in p1]
        save_4bpp(ASSETS / ("tiles/%s.png" % tid), pix, w, h, pal)
        shutil.copy(src / ("tiles/%s.tsx" % tid), ASSETS / ("tiles/%s.tsx" % tid))
    p1, w, h = A.load_1bpp(src / "ui/signs.png")
    save_4bpp(ASSETS / "ui/signs.png", [[INK if v else PAPER for v in row] for row in p1], w, h, pal)
    shutil.copy(src / "ui/signs.json", ASSETS / "ui/signs.json")
    shutil.copy(src / "palette.json", ASSETS / "palette.json")
    print("imported 4 bpp sheets into", ASSETS)


# ---------------------------------------------------------------------------------------------- build
def pack(pix, w, h):
    """rows of indices -> bytes, BP6 prototype: 8 bits per pixel, exactly w bytes per row (256 per VRAM line)."""
    out = bytearray()
    for y in range(h):
        out += bytes(pix[y][:w])
    return bytes(out)


def sheet(name):
    return load_4bpp(ASSETS / name)


TILE_SET_BASES = {"tiles_main": (0, 64), "tiles_boss": (0, 32)}   # (direct, mirrored) line of each set in its atlas: tiles.bin (main, 128
                                                                 # lines), boss.bin (Master Xybot room, 64 lines; placed by hud4.py)


HERO = (0x18C2, 0x21A0)          # sprite bank range of the player characters' frames (descriptor 99A4h of the player types 1/23): 40 frames


def is_hero(s):
    return HERO[0] <= int(s["addr"], 16) < HERO[1]


def pack_sprites(meta):
    """Skyline packing of the 179 sprites into 256-pixel lines (8-pixel columns; tallest first, each at the lowest top, leftmost on
    ties). The player characters' frames are packed first, alone, in lines 0..hero_lines-1: player 2's own copy of that band
    (sprites_p2.png) is a separate atlas the runtime reads at the same x and line offset. Returns [(x, y)] (original order), lines
    used, hero_lines."""
    sky = [0] * 32                                    # first free line of each 8-pixel column
    pos = [None] * len(meta)
    hero_lines = 0
    for group in (True, False):
        if not group:
            hero_lines = max(sky)
            sky = [hero_lines] * 32                    # nothing else inside the hero band
        order = sorted((i for i in range(len(meta)) if is_hero(meta[i]) == group),
                       key=lambda i: (-meta[i]["rows"], -meta[i]["bytes_per_row"], i))
        _skyline(meta, order, sky, pos)
    return pos, max(sky), hero_lines


def _skyline(meta, order, sky, pos):
    for i in order:
        wc, h = meta[i]["bytes_per_row"], meta[i]["rows"]
        best = None
        for c in range(33 - wc):
            y = max(sky[c:c + wc])
            if best is None or y < best[0]:
                best = (y, c)
        y, c = best
        for k in range(c, c + wc):
            sky[k] = y + h
        pos[i] = (c * 8, y)


def do_build():
    """BP6 prototype: one atlas of each kind for both players (no player-2 tint: the art has 64 colours), sprites packed, 8 bits
    per pixel."""
    OUT.mkdir(parents=True, exist_ok=True)
    meta = json.loads((ASSETS / "sprites/sprites.json").read_text())["sprites"]
    assert len(meta) == 179                                     # 177 of the original bank + the exit's own far frames 21A0h, 21A3h
    tab = bytearray()
    for s in meta:
        a = int(s["addr"], 16)
        assert 1 <= s["bytes_per_row"] <= 3 and 1 <= s["rows"] <= 63
        tab += bytes((a & 255, a >> 8, (s["rows"] << 2) | (s["bytes_per_row"] - 1)))
    (OUT / "sprtab.bin").write_bytes(bytes(tab))
    pos, lines, hero_lines = pack_sprites(meta)
    pix, W, H = sheet("sprites/sprites.png")
    p2 = ASSETS / "sprites/sprites_p2.png"
    if not p2.exists():
        sys.exit("%s is missing: player 2's character frames (same layout as sprites.png, only the %d player frames are used)"
                 % (p2, sum(1 for s in meta if is_hero(s))))
    pix2, W2, H2 = load_4bpp(p2)
    assert (W2, H2) == (W, H), "sprites_p2.png must have the size of sprites.png (%dx%d)" % (W, H)
    atlas = [[0] * 256 for _ in range(lines)]
    hero2 = [[0] * 256 for _ in range(hero_lines)]
    pt = bytearray()
    for i, s in enumerate(meta):
        ax, ay = pos[i]
        pt += bytes((ax, ay & 255, ay >> 8))
        for r in range(s["rows"]):
            row = pix[s["y"] + r][s["x"]:s["x"] + s["bytes_per_row"] * 8]
            atlas[ay + r][ax:ax + len(row)] = row
            if is_hero(s):
                hero2[ay + r][ax:ax + len(row)] = pix2[s["y"] + r][s["x"]:s["x"] + s["bytes_per_row"] * 8]
    (OUT / "sprites.bin").write_bytes(pack(atlas, 256, lines))
    (OUT / "hero_p2.bin").write_bytes(pack(hero2, 256, hero_lines))   # player 2's character: same x / line offset as in sprites.bin
    (OUT / "sprpos.bin").write_bytes(bytes(pt))                 # per sprite: atlas x, atlas line (word, from VR_SPR_Y)
    for tid, count in TILE_SETS:
        nl = 128 if tid == "tiles_main" else 64
        tl = [[0] * 256 for _ in range(nl)]
        tp, W, H = sheet("tiles/%s.png" % tid)
        for mirror, base in zip((False, True), TILE_SET_BASES[tid]):
            for t in range(count):
                for r in range(8):
                    row = tp[(t // 16) * 8 + r][(t % 16) * 8:(t % 16) * 8 + 8]
                    if mirror:
                        row = row[::-1]
                    tl[base + (t >> 5) * 8 + r][(t & 31) * 8:(t & 31) * 8 + 8] = row
        (OUT / ("tiles.bin" if tid == "tiles_main" else "boss.bin")).write_bytes(pack(tl, 256, nl))
    import scenes                                               # level scenery (ADR-025): scene_<n>.bin + scene_pal.bin
    scenes.scene_bins(OUT)
    with open(OUT / "tiles.bin", "rb") as fh:
        assert fh.read(0x8000) == (OUT / "scene_0.bin").read_bytes(), "scene A must be the main set of tiles.bin"
    signs = json.loads((ASSETS / "ui/signs.json").read_text())
    sp, W, H = sheet("ui/signs.png")
    st = [[0] * 256 for _ in range(16)]
    for it in signs["items"]:
        for r in range(signs["rows"]):
            row = sp[it["y"] + r][it["x"]:it["x"] + signs["bytes_per_row"] * 8]
            st[r][it["index"] * 24:it["index"] * 24 + len(row)] = row
    img = A.load_image()
    mk = [[0] * 256 for _ in range(16)]
    for (x, y) in ((0, 0), (1, 0), (1, 1), (0, 1)):
        mk[y][x] = 14
    for (x, y) in ((0, 0), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1), (0, 1)):
        mk[y + 1][8 + x + 1] = 14
    for d in range(4):
        rows = A.bits_to_pixels(A.rd(img, 0x3EE4 + 8 * d, 8), 1, 8)
        for y in range(8):
            for x in range(8):
                if rows[y][x]:
                    mk[y][16 + 8 * d + x] = 14
    marker_art = ASSETS / "hud/markers.png"
    if marker_art.exists():
        painted, mw, mh = load_4bpp(marker_art)
        assert (mw, mh) == (48, 8), "hud/markers.png must be 48x8 (cross, ring, four arrows)"
        for y in range(8):
            mk[y][:48] = painted[y]
    (OUT / "signs_markers.bin").write_bytes(pack(st, 256, 16) + pack(mk, 256, 16))   # signs (16 lines) then markers (16 lines)
    (OUT / "palette.bin").write_bytes(bytes(c for col in read_palette() for c in col))   # 64 x (r, g, b), 5 bits
    layout = {"sprite_lines": lines, "hero_lines": hero_lines, "tile_lines": 128, "boss_lines": 64, "tile_set_bases": TILE_SET_BASES, "pixel": "8 bpp (BP6), 256 bytes per line"}
    (OUT / "layout.json").write_text(json.dumps(layout, indent=1) + "\n")
    print("built %s (BP6): sprites packed in %d lines (player characters in lines 0-%d, player 2's copy %d lines), tiles 128 + boss 64 lines, "
          "64-colour palette" % (OUT, lines, hero_lines - 1, hero_lines))


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("import", "build"):
        sys.exit(__doc__)
    if sys.argv[1] == "import":
        do_import("--force" in sys.argv)
    else:
        do_build()

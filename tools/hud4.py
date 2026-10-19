#!/usr/bin/env python3
"""HUD art of the B1 port (ADR-016): panel as a TMX of coloured 4 bpp tiles; font, HUD digits, item icons and minimap glyphs as shape
sheets rendered into one pre-coloured VRAM variant per colour byte (no colour expansion at run time: every HUD element is an LMMM copy).

import  : ONE-TIME creation of V9990-B1/assets/hud/ from the baseline 1 bpp art (V9990-P1/assets) - refuses to overwrite, --force resets:
            hud_tiles.png / hud_tiles.tsx : the unique 8x8 cells of the start-up HUD picture (tape image at EB00h as sent by copy_fb_to_vram_top)
                                            coloured with the colour table left by init_screen_colours (6F33h), 4 bpp, 16 tiles per row
            hud.tmx                        : 32 x 12 map of those tiles (layer "panel"): the picture the panel starts from
            font.png, digits.png, icons.png, ui_glyphs.png : glyph SHAPES, 2-colour indexed PNGs (0 = paper, anything else = ink); layouts:
                                            font 16 glyphs per row (codes 20h..60h), digits 4x5 in a row, icons 8x11 in a row (1 px gaps as in
                                            the P1 sheets), ui glyphs 8x8 in a row (walls none/W/N/WN, markers ring/squares, arrows)
            colours.json                   : the colour bytes (TMS ink<<4 | paper) each sheet is pre-rendered in
          A variant can be hand-painted: hud/variants/<sheet>_<CC>.png (same layout, 4 bpp) replaces the generated one.
build   : -> build/assets4/: hud_tiles.bin (atlas, 32 tiles per 256-pixel row), hud_map.bin (384 tile numbers), font_v.bin, digits_v.bin,
          icons_v.bin, ui_v.bin (variants one after the other), hud.inc (VRAM Y bases, sizes and colour -> variant tables for the runtime),
          and vtext.bin (ADR-018, uploaded at VT_Y0 = 2608 right after the sign and marker atlases): the viewport fonts as coloured
          4 bpp tiles - vfont8 (bold 8x8, shop texts; tile 65 = the shop stripes) and vfont16 (bold 8x16, PRESS FIRE / GAME OVER /
          banners), one variant per colour byte in colours.json - and vrec.bin after the record layer: the record atlas (see below) and the palette (192 bytes).
Viewport font sheets (editable, created from font.png on the first build when missing): hud/vfont8.png (8x8 shapes, 16 per row, glyph
g = code - 20h, 65 = stripes), hud/vfont16.png (8x16 shapes, same layout). variants/vfont8_<CC>.png etc. replace a generated variant.
Record (ADR-018): per viewport cell line 2 bytes (source, source line): source 00h-40h = vfont8 glyph, 80h-C0h = vfont16 glyph, EEh =
stripes, FFh = blank. The runtime writes it in VRAM with copies from the record atlas (slot s = 16 entries (source, 0..15), 64 pixels;
slots 0-64 vfont8, 65-129 vfont16; 4 slots per line) and reads it back to redraw a cell from the tiles when its colour changes.
Pixel format as assets4.py: 2 pixels per byte, high nibble first, 128 bytes per line.
"""
import json
import os
import pathlib
import shutil
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import assetlib as A  # noqa: E402
import assets4 as A4  # noqa: E402

B = ROOT
HUD = pathlib.Path(os.environ.get("XY_ASSETS4", B / "assets")) / "hud"
OUT = pathlib.Path(os.environ.get("XY_ASSETS4_OUT", B / "build/assets4"))
Y0 = 3264                      # first free VRAM line after the HUD image (3072) and the viewport background (3168)
MAP_LINE = 4093                # the 384-byte HUD map is uploaded at linear address MAP_LINE * 128 and read back by hk_top_copy

# initial colour table of the top half: init_hardware F1 everywhere, then init_screen_colours (6F33h): all 79h -> 4F, columns 8-23 47h -> F1,
# player-1 panel rows 0-2 cols 0-7 3Ah -> 6E with rows 0-1 cols 1-6 7Ah -> 9F, player-2 panel cols 24-31 3Ch -> CE / 7Ch -> 3F
def init_colours():
    c = [[0x4F] * 32 for _ in range(12)]
    for r in range(12):
        for k in range(8, 24):
            c[r][k] = 0xF1
    for base, dim, bright in ((0, 0x6E, 0x9F), (24, 0xCE, 0x3F)):
        for r in range(3):
            for k in range(8):
                c[r][base + k] = dim
        for r in range(2):
            for k in range(1, 7):
                c[r][base + k] = bright
    return c


def shape_sheet(path):
    pix, w, h = A.load_1bpp(path)
    return pix


def do_import(force):
    if HUD.exists() and any(HUD.iterdir()) and not force:
        sys.exit("V9990-B1/assets/hud already exists; refusing to overwrite (use --force to reset).")
    HUD.mkdir(parents=True, exist_ok=True)
    pal = A4.palette_rgb(B / "assets")
    pic, w, h = A.load_1bpp(A.ASSETS / "ui/hud_top.png")
    col = init_colours()
    tiles, index, tmap = [], {}, []
    for r in range(12):
        for k in range(32):
            cb = col[r][k]
            ink, paper = cb >> 4, cb & 15
            t = tuple(tuple(ink if pic[r * 8 + y][k * 8 + x] else paper for x in range(8)) for y in range(8))
            if t not in index:
                index[t] = len(tiles)
                tiles.append(t)
            tmap.append(index[t])
    n = len(tiles)
    cols = 16
    rows = (n + cols - 1) // cols
    sheet = [[0] * (cols * 8) for _ in range(rows * 8)]
    for i, t in enumerate(tiles):
        for y in range(8):
            sheet[(i // cols) * 8 + y][(i % cols) * 8:(i % cols) * 8 + 8] = list(t[y])
    A4.save_4bpp(HUD / "hud_tiles.png", sheet, cols * 8, rows * 8, pal)
    ts = ET.Element("tileset", version="1.10", tiledversion="1.10.2", name="hud_tiles", tilewidth="8", tileheight="8",
                    tilecount=str(n), columns=str(cols))
    ET.SubElement(ts, "image", source="hud_tiles.png", width=str(cols * 8), height=str(rows * 8))
    ET.indent(ts)
    (HUD / "hud_tiles.tsx").write_bytes(ET.tostring(ts, xml_declaration=True, encoding="UTF-8") + b"\n")
    m = ET.Element("map", version="1.10", tiledversion="1.10.2", orientation="orthogonal", renderorder="right-down", width="32", height="12",
                   tilewidth="8", tileheight="8", infinite="0", nextlayerid="2", nextobjectid="1")
    props = ET.SubElement(m, "properties")
    ET.SubElement(props, "property", name="description", value="HUD / top half of the screen as the game starts (panels, labels, empty "
                  "minimap window). Digits, icons, texts and the minimap are drawn over it at run time by the V9990 (ADR-016).")
    ET.SubElement(m, "tileset", firstgid="1", source="hud_tiles.tsx")
    lay = ET.SubElement(m, "layer", id="1", name="panel", width="32", height="12")
    data = ET.SubElement(lay, "data", encoding="csv")
    data.text = "\n" + ",\n".join(",".join(str(tmap[r * 32 + k] + 1) for k in range(32)) for r in range(12)) + "\n"
    ET.indent(m)
    (HUD / "hud.tmx").write_bytes(ET.tostring(m, xml_declaration=True, encoding="UTF-8") + b"\n")
    shutil.copy(A.ASSETS / "tiles/font.png", HUD / "font.png")
    shutil.copy(A.ASSETS / "ui/digits.png", HUD / "digits.png")
    shutil.copy(A.ASSETS / "ui/digits.json", HUD / "digits.json")
    shutil.copy(A.ASSETS / "ui/icons.png", HUD / "icons.png")
    shutil.copy(A.ASSETS / "ui/icons.json", HUD / "icons.json")
    shutil.copy(A.ASSETS / "tiles/ui_glyphs.png", HUD / "ui_glyphs.png")
    marquee = [0x11, 0x41, 0x61, 0xD1, 0xC1, 0x71, 0xA1, 0xE1]      # title marquee: ZX ink 0..7 on black through zx_attr_to_msx
    (HUD / "colours.json").write_text(json.dumps({
        "comment": "colour bytes (TMS ink<<4 | paper) each shape sheet is pre-rendered in; a colour the game uses that is missing here is "
                   "drawn with the FIRST variant of the sheet (the test harness reports such misses)",
        "font": [0xF1, 0x4F, 0x6E, 0x9F, 0xCE, 0x3F] + marquee,
        "digits": [0x4F, 0x6E, 0x9F, 0xCE, 0x3F, 0xF1],
        "icons": [0x4F],
        "ui_glyphs": [0xF1]}, indent=1) + "\n")
    print("imported HUD assets into %s: %d unique panel tiles" % (HUD, n))


# ------------------------------------------------------------------------------------------------ build
def glyphs(sheet):
    """(width, height, list of glyph pixel rows) for each shape sheet."""
    if sheet == "font":
        pix = shape_sheet(HUD / "font.png")
        return 8, 8, [[pix[(g // 16) * 8 + y][(g % 16) * 8:(g % 16) * 8 + 8] for y in range(8)] for g in range(65)]
    if sheet == "ui_glyphs":
        pix = shape_sheet(HUD / "ui_glyphs.png")
        return 8, 8, [[pix[y][g * 8:g * 8 + 8] for y in range(8)] for g in range(8)]
    meta = json.loads((HUD / ("%s.json" % sheet)).read_text())
    pix = shape_sheet(HUD / ("%s.png" % sheet))
    w = 4 if sheet == "digits" else 8
    return w, meta["rows"], [[pix[it["y"] + y][it["x"]:it["x"] + w] for y in range(meta["rows"])] for it in meta["items"]]


def glyphs_fb():
    """The 65 bold glyphs of the frame-buffer texts as 8 row bytes each (MSB = left pixel): hud/font_fb.png when it exists (drawn
    shapes, same layout as font.png), else the original rule of glyph_fb_small_draw / draw_glyph_fb_2x applied to font.png: g | g >> 1."""
    over = HUD / "font_fb.png"
    pix = shape_sheet(over if over.exists() else HUD / "font.png")
    out = []
    for g in range(65):
        rows = []
        for y in range(8):
            v = 0
            for x in range(8):
                v = (v << 1) | (1 if pix[(g // 16) * 8 + y][(g % 16) * 8 + x] else 0)
            rows.append(v if over.exists() else (v | (v >> 1)))
        out.append(rows)
    return out


VSHEETS = (("vfont8", 8, 66), ("vfont16", 16, 65))   # (sheet, glyph height, glyphs); vfont8 glyph 65 = the shop stripes tile


def vfont_sheet(name, h, n):
    """Shapes of a viewport font sheet (created from font.png with the original bold rule g | g >> 1 when missing)."""
    path = HUD / ("%s.png" % name)
    if not path.exists():
        bold = glyphs_fb()
        pix = [[0] * 128 for _ in range(5 * h)]
        for g in range(n):
            for y in range(h):
                v = bold[g][y * 8 // h] if g < 65 else (0xFF if y % 2 == 0 else 0x00)
                for x in range(8):
                    pix[(g // 16) * h + y][(g % 16) * 8 + x] = (v >> (7 - x)) & 1
        A.save_1bpp(path, pix, 128, 5 * h)
        print("created %s (bold font, editable)" % path)
    pix = shape_sheet(path)
    return [[pix[(g // 16) * h + y][(g % 16) * 8:(g % 16) * 8 + 8] for y in range(h)] for g in range(n)]


def render_variant(sheet, cb, w, h, gl, per_row, transparent_paper):
    """One variant: glyphs per_row per 256-pixel line group; ink = cb >> 4, paper = cb & 15 (0 when transparent)."""
    over = HUD / "variants" / ("%s_%02X.png" % (sheet, cb))
    rows = (len(gl) + per_row - 1) // per_row
    img = [[0] * 256 for _ in range(rows * h)]
    if over.exists():
        pix, ow, oh = A4.load_4bpp(over)
        for y in range(min(oh, rows * h)):
            img[y][:min(ow, 256)] = pix[y][:min(ow, 256)]
        return img
    ink, paper = cb >> 4, (0 if transparent_paper else cb & 15)
    for g, rws in enumerate(gl):
        x0, y0 = (g % per_row) * w, (g // per_row) * h
        for y in range(h):
            for x in range(w):
                img[y0 + y][x0 + x] = ink if rws[y][x] else paper
    return img


# BP6 prototype VRAM map (8 bpp: 256 bytes per line, lines 0-2047). Pages 0-211, 256-467, 512-723; the gaps between them hold the small
# data; the rest follows VR_HUD / VR_BG.
# Single HUD (split screen): VR_HUD and the two display buffers of the viewports share the 256-line block 3 (R#18 is latched once per
# frame; only R#17 changes, in display line 95): HUD 768-863, buffer A 864-959, buffer B 981-1076. The display is 212 lines high, so
# display lines 192-211 show the 20 lines that follow the displayed buffer: each buffer is followed by a black guard strip (960-979,
# 1077-1096); without it the bottom band alternated between buffer B and the font atlas at every flip (visible jitter under the
# viewports). The R#17 write restarts the display in the middle of line 95, whose rest then shows the line before the buffer: for A that
# is the last HUD line itself, for B line 980 holds a copy of it (hk_hud_line_copy).
BG_Y, REC_Y, RA_Y, PAL_LINE = 0, 96, 120, 137    # viewport background, text record 24 lines, record atlas 17 lines, palette
SCR_Y, MAP_LINE, VF8FB_Y = 138, 146, 148         # scratch cell, hud.tmx map (384 bytes), vfont8 in F0h (24 lines)
SIGN_Y, MARK_Y = 172, 188                        # signs 16 lines, minimap markers 16 lines (assets4 signs_markers.bin)
TILES_Y, SPR_Y = 204, 364                        # tiles 160 lines, packed sprites (279 lines -> 642)
HUD_Y, VPA_Y, VPB_Y, HI_Y = 768, 864, 981, 1097  # HUD, display buffers + black guards, then fonts and HUD atlases
GUARD = 20                                        # display lines 192-211
MAPC_LINES = 104                                  # clean minimap image (the window x 64..191 of VR_HUD without the blinking markers,
MAPC_Y = 2048 - MAPC_LINES                        # ADR-054): 96 lines + room for a marker box that reaches below line 95


def scene_store(boss_y, end_line):
    """Level scenery without CPU uploads during the game (ADR-025 amendment): every 8 x 8 tile that differs between the 4 scenes
    (ids that change in any scene, direct and mirrored, deduplicated) is kept in free VRAM rows; a scene change copies its tiles into
    the main atlas with LMMM 8 x 8 (hk_scene_copy). Free rows: the 32 lines between the main atlas and the sprites, the empty rows of
    boss.bin, the rows after the high area.
    ROM (fixed banks, layout.asm SCENE_BANK): the store stream from bank SCN_SBANK = SCENE_BANK (uploaded at boot by stage B through
    hk_store_tab, its second VRAM table), the copy lists in bank SCN_LBANK = SCENE_BANK + 4 (per scene 8-byte entries SX, SY, DX, DY
    words, ended by an entry of FFh bytes). Writes scene_store.bin, scene_list.bin, scene_store_tab.inc; returns inc lines."""
    import re
    scene_bank = int(re.search(r"^SCENE_BANK\s+equ\s+(\d+)", (B / "src/layout.asm").read_text(), re.M).group(1))
    tiles_lines = 128
    scenes = [(OUT / ("scene_%d.bin" % n)).read_bytes() for n in range(4)]
    ntiles = A4.TILE_SETS[0][1]

    def tile(b, base, t):
        x, y = (t & 31) * 8, base + (t >> 5) * 8
        return b"".join(b[(y + r) * 256 + x:(y + r) * 256 + x + 8] for r in range(8))
    changing = [t for t in range(ntiles) if any(tile(sc, h, t) != tile(scenes[0], h, t) for sc in scenes[1:] for h in (0, 64))]
    rows = list(range(TILES_Y + tiles_lines, SPR_Y - 7, 8))
    boss = (OUT / "boss.bin").read_bytes()
    rows += [boss_y + 8 * r for r in range(len(boss) // 2048) if not any(boss[r * 2048:(r + 1) * 2048])]
    rows += list(range(end_line, MAPC_Y - 7, 8))              # the last MAPC_LINES lines are the clean minimap image (ADR-054)
    slots, store = {}, []
    lists = bytearray()
    word = lambda v: bytes([v & 255, v >> 8])  # noqa: E731
    for sc in scenes:
        for t in changing:
            for h in (0, 64):
                px = tile(sc, h, t)
                if px not in slots:
                    assert len(store) < len(rows) * 32, "scene store: more than %d distinct tiles (free VRAM rows)" % (len(rows) * 32)
                    slots[px] = len(store)
                    store.append(px)
                i = slots[px]
                lists += word((i & 31) * 8) + word(rows[i // 32]) + word((t & 31) * 8) + word(TILES_Y + h + (t >> 5) * 8)
        lists += b"\xff" * 8
    used = rows[:(len(store) + 31) // 32]
    runs = []
    for y in used:                                                  # contiguous rows -> one piece
        if runs and y == runs[-1][-1] + 8:
            runs[-1].append(y)
        else:
            runs.append([y])
    import itertools

    def npieces(order):                                             # stage B pieces of an order (cut at every 16 KiB bank boundary)
        pos, n = 0, 0
        for r in order:
            end = pos + len(r) * 2048
            n += (end - 1) // 0x4000 - pos // 0x4000 + 1
            pos = end
        return n
    order = min(itertools.permutations(runs), key=npieces)        # few runs: the order with the fewest pieces
    stream, tab = bytearray(), []
    for run in order:
        data = bytearray(len(run) * 2048)
        for i, px in enumerate(store):
            y = rows[i // 32]
            if y in run:
                o = (y - run[0]) * 256 + (i & 31) * 8
                for r in range(8):
                    data[o + r * 256:o + r * 256 + 8] = px[r * 8:r * 8 + 8]
        va, k = run[0] * 256, 0
        while k < len(data):                                        # stage B pieces never cross a 16 KiB bank
            pos = len(stream)
            n = min(len(data) - k, 0x4000 - pos % 0x4000)
            tab.append((va + k, n, scene_bank + pos // 0x4000, 0x4000 + pos % 0x4000))
            stream += data[k:k + n]
            k += n
    assert len(stream) <= 4 * 0x4000 and len(lists) <= 0x4000
    (OUT / "scene_store.bin").write_bytes(bytes(stream))
    (OUT / "scene_list.bin").write_bytes(bytes(lists))
    inc = ["; generated by hud4.py scene_store: stage B's second VRAM table (the scene store), entries as vram_chunks.inc"]
    for va, n, bank, src in tab:
        inc += ["        dw 0x%04x" % (va & 0xFFFF), "        db %d" % (va >> 16), "        dw 0x%04x" % n, "        db %d" % bank,
                "        dw 0x%04x" % src]
    inc += ["        db 0,0,0", "        dw 0", "        db 0", "        dw 0          ; end, no next table"]
    (OUT / "scene_store_tab.inc").write_text("\n".join(inc) + "\n")
    lsz = len(lists) // 4
    print("scene store: %d changing ids, %d distinct tiles in %d of %d free rows (%d pieces); copy lists %d bytes" % (
        len(changing), len(store), len(used), len(rows), len(tab), len(lists)))
    return ["SCN_SBANK       equ %d          ; scene store stream (uploaded at boot)" % scene_bank,
            "SCN_LBANK       equ %d          ; scene copy lists: scene n at SCN_LIST + n * SCN_LSZ (page 1)" % (scene_bank + 4),
            "SCN_LIST        equ 0x4000", "SCN_LSZ         equ %d" % lsz]


def do_build():
    OUT.mkdir(parents=True, exist_ok=True)
    cols = json.loads((HUD / "colours.json").read_text())
    lay = json.loads((OUT / "layout.json").read_text())
    inc = ["; generated by V9990-B1_BP6/tools/hud4.py build - VRAM map of the BP6 prototype (8 bpp, 256 bytes per line)"]
    tables = ["; generated by V9990-B1_BP6/tools/hud4.py build - colour byte of each pre-rendered variant (index = variant)"]
    # Optional BP6 HUD geometry: the game still calls the hooks with its MSX coordinates.
    layout_file = HUD / "layout.json"
    layout = json.loads(layout_file.read_text()) if layout_file.exists() else {
        "digits": [], "slot_x": [7, 17, 27, 37, 48, 12, 22, 32, 42, 12, 22, 32, 43],
        "slot_y": [48] * 5 + [63] * 4 + [78] * 4,
        "slot_paper": 15, "minimap_ink": 15, "minimap_paper": 1}
    assert len(layout["slot_x"]) == len(layout["slot_y"]) == 13
    assert all(0 <= layout[key] < 64 for key in ("slot_paper", "minimap_ink", "minimap_paper"))
    assert all(0 <= x <= 55 for x in layout["slot_x"])
    assert all(0 <= y <= 85 for y in layout["slot_y"])
    for field in layout["digits"]:
        assert 0 <= field["source_y"] < 92 and 0 <= field["y"] <= 91
        assert -63 <= field["x_shift"] <= 63
    inc += ["HUD_SLOT_PAPER equ %d" % layout["slot_paper"],
            "HUD_MAP_INK equ %d" % layout["minimap_ink"], "HUD_MAP_PAPER equ %d" % layout["minimap_paper"]]
    positions = [v for f in layout["digits"] for v in (f["source_y"], f["y"], f["x_shift"] & 255)] + [255]
    tables += ["hud_digit_positions:", "        db " + ",".join(str(v) for v in positions),
               "hud_slot_x:", "        db " + ",".join(str(v) for v in layout["slot_x"]),
               "hud_slot_y:", "        db " + ",".join(str(v) for v in layout["slot_y"])]
    files = []
    tsb = lay["tile_set_bases"]
    hero2_y = SPR_Y + lay["sprite_lines"]                 # player 2's character band right after the sprite atlas
    boss_y = hero2_y + lay["hero_lines"]                  # Master Xybot room atlas: after player 2's band, below the HUD block
    assert boss_y + lay["boss_lines"] <= HUD_Y, "sprites / boss room atlas overlap the HUD block"
    assert VPB_Y == VPA_Y + 96 + GUARD + 1 and HI_Y == VPB_Y + 96 + GUARD and VPB_Y - 1 - HUD_Y <= 255, "split-screen block layout"
    inc += ["VR_HUD_Y        equ %d" % HUD_Y, "VR_BG_Y         equ %d" % BG_Y, "VR_TILES_Y      equ %d" % TILES_Y,
            "VR_VPA_Y        equ %d          ; display buffer A (viewports), R#17 = VR_VPA_R17 at line 96" % VPA_Y,
            "VR_VPB_Y        equ %d          ; display buffer B, R#17 = VR_VPB_R17" % VPB_Y,
            "VR_VPA_R17      equ %d          ; R#17 written in line 95: line 96 shows buffer line 0" % (VPA_Y - 1 - HUD_Y),
            "VR_VPB_R17      equ %d" % (VPB_Y - 1 - HUD_Y),
            "VR_SPLIT_LINES  equ %d          ; HUD + buffers + black guards, cleared at boot" % (HI_Y - HUD_Y),
            "TS_MAIN         equ %d" % tsb["tiles_main"][0], "TS_MAIN_M       equ %d" % tsb["tiles_main"][1],
            "TS_BOSS         equ %d          ; boss.bin (Master Xybot room) at VR_BOSS_Y, relative to VR_TILES_Y" % (boss_y - TILES_Y + tsb["tiles_boss"][0]),
            "TS_BOSS_M       equ %d" % (boss_y - TILES_Y + tsb["tiles_boss"][1]), "VR_BOSS_Y       equ %d" % boss_y,
            "VR_SPR_Y        equ %d          ; packed sprites, %d lines (position table sprpos.bin)" % (SPR_Y, lay["sprite_lines"]),
            "VR_HERO2_Y      equ %d          ; player 2's character frames: same x / line as sprite lines 0..HERO_LINES-1" % hero2_y,
            "HERO_LINES      equ %d" % lay["hero_lines"],
            "VR_SIGN_Y       equ %d" % SIGN_Y, "VR_MARK_Y       equ %d" % MARK_Y, "VR_SCR_Y        equ %d" % SCR_Y,
            "VR_MAPC_Y       equ %d          ; clean minimap image: window line y at VR_MAPC_Y + y (no blinking markers, ADR-054)" % MAPC_Y,
            "VR_REC_Y        equ %d          ; record: half h, cell row r at line VR_REC_Y + h * 12 + r, column c at x = (c & 15) * 16 + 2 * line" % REC_Y,
            "VR_RA_Y         equ %d          ; record atlas: slot s at x = (s & 7) * 32, y + (s >> 3); entry of line l at + 2 * l" % RA_Y,
            "VR_PAL_ADDR     equ %d" % (PAL_LINE * 256),
            "HUD_MAP_LINE    equ %d          ; hud.tmx tile numbers (384 bytes) at linear VRAM address HUD_MAP_LINE * 256" % MAP_LINE]
    files += [("tiles.bin", TILES_Y), ("sprites.bin", SPR_Y), ("hero_p2.bin", hero2_y), ("boss.bin", boss_y), ("signs_markers.bin", SIGN_Y)]
    # record atlas + palette
    ra = bytearray(17 * 256)
    for slot in range(130):
        src = slot if slot < 65 else 0x80 + slot - 65
        for ln in range(16):
            o = (slot >> 3) * 256 + (slot & 7) * 32 + 2 * ln
            ra[o], ra[o + 1] = src, ln
    (OUT / "vrec.bin").write_bytes(bytes(ra) + (OUT / "palette.bin").read_bytes())
    files.append(("vrec.bin", RA_Y))
    # canonical F0 fonts
    g8 = vfont_sheet("vfont8", 8, 66)
    (OUT / "vf8fb.bin").write_bytes(A4.pack(render_variant("vfont8", 0xF0, 8, 8, g8, 32, False), 256, 24))
    files.append(("vf8fb.bin", VF8FB_Y))
    inc.append("VR_VF8_FB_Y     equ %d" % VF8FB_Y)
    # high area after the sprites: vfont16 F0, viewport font variants, HUD atlases
    y = HI_Y
    hi = bytearray()
    g16 = vfont_sheet("vfont16", 16, 65)
    hi += A4.pack(render_variant("vfont16", 0xF0, 8, 16, g16, 32, False), 256, 48)
    inc.append("VR_VF16_FB_Y    equ %d" % y)
    y += 48
    for name, h, n, gl in (("vfont8", 8, 66, g8), ("vfont16", 16, 65, g16)):
        vlines = ((n + 31) // 32) * h
        for cb in cols[name]:
            hi += A4.pack(render_variant(name, cb, 8, h, gl, 32, False), 256, vlines)
        tag = {"vfont8": "VF8", "vfont16": "VF16"}[name]
        inc += ["VR_%s_Y%s equ %d" % (tag, " " * (7 - len(tag)), y), "%s_VL%s equ %d" % (tag, " " * (9 - len(tag)), vlines),
                "%s_NV%s equ %d" % (tag, " " * (9 - len(tag)), len(cols[name]))]
        tables += ["hud_%s_cols:" % name, "        db " + ",".join("0x%02x" % c for c in cols[name])]
        y += vlines * len(cols[name])
    tmx = ET.parse(HUD / "hud.tmx").getroot()
    tmap = [int(v) - 1 for v in tmx.find("layer/data").text.replace("\n", "").split(",") if v.strip()]
    assert len(tmap) == 384 and all(0 <= v < 256 for v in tmap), "hud.tmx must be 32x12 with at most 256 tiles"
    tp, tw, th = A4.load_4bpp(HUD / "hud_tiles.png")
    n = (tw // 8) * (th // 8)
    lines = ((n + 31) // 32) * 8
    atlas = [[0] * 256 for _ in range(lines)]
    for i in range(n):
        for yy in range(8):
            atlas[(i // 32) * 8 + yy][(i % 32) * 8:(i % 32) * 8 + 8] = tp[(i // (tw // 8)) * 8 + yy][(i % (tw // 8)) * 8:(i % (tw // 8)) * 8 + 8]
    hi += A4.pack(atlas, 256, lines)
    (OUT / "hud_map.bin").write_bytes(bytes(tmap))
    inc.append("VR_HUDT_Y       equ %d          ; panel tile atlas: tile t at x = (t & 31) * 8, y = VR_HUDT_Y + (t >> 5) * 8" % y)
    y += lines
    for sheet, per_row, transparent in (("font", 32, False), ("digits", 64, False), ("icons", 32, True), ("ui_glyphs", 32, True)):
        w, h, gl = glyphs(sheet)
        extra = []
        if sheet == "font":
            gl, extra = gl[:64], gl[64:]              # the 65th glyph (code 60h) of every variant shares one row (VR_FONTX_Y): 2 rows a
        vlines = ((len(gl) + per_row - 1) // per_row) * h    # variant instead of 3 (14 x 8 lines saved for the clean minimap image, ADR-054)
        for cb in cols[sheet]:
            hi += A4.pack(render_variant(sheet, cb, w, h, gl, per_row, transparent), 256, vlines)
        tag = {"font": "FONT", "digits": "DIG", "icons": "ICON", "ui_glyphs": "UIG"}[sheet]
        inc += ["VR_%s_Y%s equ %d" % (tag, " " * (7 - len(tag)), y), "%s_VL%s equ %d" % (tag, " " * (9 - len(tag)), vlines),
                "%s_NV%s equ %d          ; variants (colour bytes in hud_%s_cols)" % (tag, " " * (9 - len(tag)), len(cols[sheet]), sheet)]
        y += vlines * len(cols[sheet])
        if extra:
            row = [[0] * 256 for _ in range(h)]
            for v, cb in enumerate(cols[sheet]):
                img = render_variant(sheet, cb, w, h, extra, 1, transparent)
                for yy in range(h):
                    row[yy][v * w:(v + 1) * w] = img[yy][:w]
            hi += A4.pack(row, 256, h)
            inc.append("VR_%sX_Y%s equ %d          ; glyph 64 (code 60h) of variant v at x = 8 * v" % (tag, " " * (6 - len(tag)), y))
            y += h
        tables += ["hud_%s_cols:" % sheet, "        db " + ",".join("0x%02x" % c for c in cols[sheet])]
    # Shop presentation: one 128x96 navy panel and one inactive-player invitation.
    # These are editable assets; the normal build needs neither arcade ROMs nor MAME.
    shop = A4.ASSETS / "shop"
    room, rw, rh = A4.load_4bpp(shop / "panel.png")
    invite, iw, ih = A4.load_4bpp(shop / "invite.png")
    assert (rw, rh) == (iw, ih) == (128, 96), "shop panels must be 128x96"
    # Keep the game's established large font and leave eight clear lines between the two prompt lines.
    for label, top in (("PRESS FIRE", 24), ("TO START", 48)):
        left = (128 - len(label) * 8) // 2
        for n, char in enumerate(label):
            for yy, row in enumerate(g16[ord(char) - 32]):
                for xx, pixel in enumerate(row):
                    if pixel:
                        invite[top + yy][left + n * 8 + xx] = 15
    inc.append("VR_SHOP_Y       equ %d          ; navy panel at x=0, invitation at x=128, 96 lines" % y)
    hi += A4.pack([room[r] + invite[r] for r in range(96)], 256, 96)
    y += 96
    inc.append("VR_SHOPFONT_Y   equ %d          ; existing MSX vfont8, white/black then yellow/black, 24 lines each" % y)
    for colour in (0xF0, 0xB0):
        hi += A4.pack(render_variant("vfont8", colour, 8, 8, g8, 32, False), 256, 24)
        y += 24
    (OUT / "hi.bin").write_bytes(bytes(hi))
    files.append(("hi.bin", HI_Y))
    assert y <= 2048, "VRAM overflow: the high area ends at line %d (2048 available)" % y
    inc += scene_store(boss_y, y)
    (OUT / "hud.inc").write_text("\n".join(inc) + "\n")
    (OUT / "hud_tables.inc").write_text("\n".join(tables) + "\n")
    (OUT / "hud_files.json").write_text(json.dumps({"files": files, "map": ["hud_map.bin", MAP_LINE], "end_line": y}, indent=1) + "\n")
    top = boss_y + lay["boss_lines"]
    free = (HUD_Y - top) + (2048 - y)
    print("BP6 single-HUD VRAM: 0-%d data, 768-1096 HUD + 2 buffers + guards, 1097-%d atlases; %d lines free (%d KiB) before the scene store"
          % (top - 1, y - 1, free, free // 4))


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("import", "build"):
        sys.exit(__doc__)
    if sys.argv[1] == "import":
        do_import("--force" in sys.argv)
    else:
        do_build()

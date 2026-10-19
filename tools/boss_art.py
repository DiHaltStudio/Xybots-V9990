#!/usr/bin/env python3
"""Master Xybot room (2026-10-06): a picture after the arcade instead of the original 29-tile machine.

  boss_art.py            ONE-TIME: draw the room (128 x 96, symmetric), cut it into tiles -> assets/tiles/tiles_boss.png (128 x 64,
                         up to 128 tiles) + assets/tiles/boss_room.json (the 12 x 16 tile map of 4BFCh); build/views/boss_preview.png
  boss_art.py --cut      re-cut an edited picture assets/tiles/boss_room.png (128 x 96 indexed, shared palette) into tiles + map

The game copies the map at 4BFCh into the viewport (spawn_master_xybot) and mirrors it for player 1; the renderer draws columns 0-7 of
a half with the mirrored atlas. A symmetric picture therefore needs only its right half (8 x 12 cells): map[r][8 + k] = map[r][7 - k] =
tile of cell (r, k). The six boss parts (type 18h actors, sprites 18AAh-18BAh) stand in a row at y 35-41, x 36-90: the mouth with its
yellow teeth is drawn there. Colours: shared palette entries that the level scenes do not change.
patch_boss_map(img) installs the map (build_b1.py, all_views.py).
"""
import json
import pathlib
import sys

from PIL import Image, ImageDraw

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import assets4 as A4  # noqa: E402

PICTURE = A4.ASSETS / "tiles/boss_room.png"
MAPF = A4.ASSETS / "tiles/boss_room.json"
SHEET = A4.ASSETS / "tiles/tiles_boss.png"
BOSS_MAP = 0x4BFC

BLACK, NAVY, DBLUE, BLUE, LBLUE, CYAN, PALE = 0, 52, 21, 22, 23, 56, 30
TEAL, YELLOW, GREEN, DGREEN, MAGENTA, WINE, PLUM, DPLUM = 57, 11, 3, 12, 13, 26, 24, 28
RED, SALMON, DRED, VIOLET, WHITE = 33, 6, 34, 4, 15
BRIGHT, LILAC, ORANGE, GOLD = 7, 5, 19, 16


def sym(points):
    """Polygon given by its right half (x >= 64), mirrored to a closed symmetric outline."""
    right = list(points)
    left = [(127 - x, y) for x, y in reversed(right)]
    return right + left


def draw():
    """The room after the arcade (right half drawn, mirrored): circuit-board walls, a purple machine with magenta cables on each
    side, the long cyan face (forehead grilles, V brows, slanted green eyes, dark nose, mouth of yellow teeth, lined jaw), red floor."""
    im = Image.new("P", (128, 96), BLACK)
    d = ImageDraw.Draw(im)
    # circuit traces on the dark wall
    for y0, x0, x1, yb in ((5, 100, 127, 14), (16, 104, 127, 26), (70, 98, 127, 78), (60, 116, 127, 66)):
        d.line((x0, y0, x1, y0), fill=DBLUE)
        d.line((x0, y0, x0, yb), fill=DBLUE)
        d.point((x0, yb), fill=BRIGHT)
    for x in range(102, 127, 6):
        d.point((x, 9), fill=TEAL)
        d.point((x + 2, 74), fill=TEAL)
    # magenta cables from the ceiling into the machine and down to the floor
    for k, col in ((0, MAGENTA), (3, WINE)):
        d.line((96 + k, 0, 99 + k, 12, 103 + k, 22, 105 + k, 30), fill=col, width=2)
        d.line((110 + k, 66, 108 + k, 74, 111 + k, 82), fill=col, width=2)
    # purple machine
    d.rounded_rectangle((99, 30, 127, 64), radius=5, fill=VIOLET, outline=DPLUM)
    d.rectangle((101, 32, 127, 37), fill=LILAC)
    d.line((101, 38, 127, 38), fill=PLUM)
    for x in range(103, 127, 6):
        d.ellipse((x, 42, x + 4, 50), fill=PLUM, outline=LILAC)
    d.rectangle((101, 54, 127, 58), fill=BLUE)
    d.line((101, 56, 127, 56), fill=BRIGHT)
    d.rectangle((106, 64, 116, 82), fill=PLUM)
    d.line((108, 64, 108, 82), fill=MAGENTA)
    # face: long shield, darker sides
    face = [(64, 0), (91, 0), (98, 9), (100, 22), (98, 34), (94, 46), (89, 58), (81, 70), (72, 79), (64, 81)]
    d.polygon(face, fill=BLUE, outline=NAVY)
    d.polygon([(64, 0), (86, 0), (92, 9), (93, 22), (91, 34), (87, 46), (82, 58), (75, 69), (64, 77)], fill=CYAN)
    # forehead: band with two grilles, central ridge
    d.rectangle((64, 1, 93, 11), fill=BLUE)
    for gx in (69, 80):
        d.rectangle((gx, 3, gx + 7, 9), fill=NAVY)
        for x in range(gx + 1, gx + 7, 2):
            d.line((x, 4, x, 8), fill=BRIGHT)
    d.line((64, 12, 93, 12), fill=NAVY)
    d.rectangle((64, 12, 65, 22), fill=BLUE)
    # brow (V towards the centre), eye, cheekbone highlight
    d.polygon([(64, 19), (71, 22), (93, 16), (95, 20), (73, 26), (64, 24)], fill=DBLUE)
    d.polygon([(72, 26), (91, 21), (92, 24), (76, 29)], fill=GREEN, outline=DGREEN)
    d.line((76, 27, 89, 24), fill=PALE)
    d.line((77, 31, 93, 27), fill=BRIGHT)
    # nose
    d.polygon([(64, 23), (66, 23), (69, 32), (64, 33)], fill=NAVY)
    d.point((67, 31), fill=PALE)
    # mouth: dark, yellow teeth over an orange gum (the six boss parts open here, y 35-41)
    d.rectangle((64, 34, 94, 46), fill=BLACK, outline=NAVY)
    for x in range(66, 93, 5):
        d.rectangle((x, 35, x + 3, 43), fill=YELLOW)
        d.line((x, 43, x + 3, 43), fill=GOLD)
    d.line((65, 45, 93, 45), fill=ORANGE)
    # jaw lines and chin plate
    for top, bot in (((72, 47), (66, 74)), ((80, 47), (70, 70)), ((89, 47), (77, 66))):
        d.line(top + bot, fill=BLUE)
    d.rectangle((64, 62, 67, 77), fill=PALE)
    d.line((64, 78, 72, 78), fill=NAVY)
    # floor: red-orange platform with dark rings
    d.rectangle((0, 82, 127, 95), fill=ORANGE)
    d.line((0, 82, 127, 82), fill=RED)
    d.ellipse((6, 84, 121, 100), outline=DRED)
    d.ellipse((30, 87, 97, 97), outline=DRED)
    # mirror: the right half wins
    px = im.load()
    for y in range(96):
        for x in range(64):
            px[x, y] = px[127 - x, y]
    return im


def cut(im):
    px = im.load()
    tiles, ids, cells = [], {}, [[0] * 8 for _ in range(12)]
    for r in range(12):
        for k in range(8):
            t = tuple(px[64 + k * 8 + x, r * 8 + y] for y in range(8) for x in range(8))
            if t not in ids:
                ids[t] = len(tiles)
                tiles.append(t)
            cells[r][k] = ids[t]
    if len(tiles) > 128:
        sys.exit("the picture needs %d tiles, the boss atlas holds 128" % len(tiles))
    sheet = Image.new("P", (128, 64), 0)
    sheet.putpalette(im.getpalette())
    sp = sheet.load()
    for n, t in enumerate(tiles):
        for i, v in enumerate(t):
            sp[(n % 16) * 8 + i % 8, (n // 16) * 8 + i // 8] = v
    sheet.save(SHEET, optimize=False)
    room = [[cells[r][c - 8] if c >= 8 else cells[r][7 - c] for c in range(16)] for r in range(12)]
    MAPF.write_text(json.dumps({"format": "tile map of the Master Xybot room (4BFCh, 12 x 16, player 2 orientation; tools/boss_art.py)",
                                "map": room}, indent=None).replace("], [", "],\n  [") + "\n")
    print("%d tiles -> %s, map -> %s" % (len(tiles), SHEET.relative_to(A4.ASSETS), MAPF.relative_to(A4.ASSETS)))


def patch_boss_map(img):
    room = json.loads(MAPF.read_text())["map"]
    img[BOSS_MAP:BOSS_MAP + 192] = bytes(t for row in room for t in row)


def preview(im):
    rgb = A4.palette_rgb()
    out = Image.new("RGB", (128, 96))
    out.putdata([tuple(rgb[v]) for v in im.getdata()])
    dst = A4.OUT.parent / "views/boss_preview.png"
    dst.parent.mkdir(parents=True, exist_ok=True)
    out.resize((512, 384), Image.NEAREST).save(dst)
    print("preview", dst)


def main():
    if "--cut" in sys.argv:
        im = Image.open(PICTURE)
    else:
        im = draw()
        pal = []
        for c in A4.palette_rgb():
            pal += list(c)
        im.putpalette(pal + [0] * (768 - len(pal)))
        im.save(PICTURE, optimize=False)
    cut(im)
    preview(im)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Level scenery (ADR-025): 4 scenes, each a corridor tile sheet with its own colours, chosen by the level (scene = level index & 3:
levels 1, 5, 9 ... scene A, 2, 6 ... B, 3, 7 ... C, 4, 8 ... D). Boss rooms keep tiles_boss.

assets/scenes/scenes.json   the scene palette entries (15 entries of the shared palette used ONLY by the corridor tiles; each scene sets
                            its own colours there) and the 4 scenes: name + sheet. Scene A is tiles/tiles_main.png (its colours are those
                            of palette.json); the others are assets/scenes/scene_?.png, 128 x 128 indexed PNGs with the same tile ids,
                            geometry and wall_panels.json as tiles_main. In a scene sheet only the scene entries may differ from
                            palette.json. Edit them in any paint program keeping the palette indices (a scene's colours = its PNG palette).

  scenes.py remap             ONE-TIME (done 2026-10-05): tiles_main.png pixels that used entries shared with sprites / HUD are moved
                              to scene entries of the same colour, so that a scene can change every corridor colour
  scenes.py create            ONE-TIME: scene_b/c/d.png = tiles_main.png pixels with the colour sets of RECIPES (refuses to overwrite)
  scenes.py preview           build/views/scenes.png: a few typical views in every scene (`make scenes`)

assets4.py build calls load_scenes(): build/assets4/scene_<n>.bin (main atlas, direct + mirrored, 32 KiB) and scene_pal.bin (per scene
64 bytes: 15 x (R#14 palette pointer = entry * 4, R, G, B)), placed by build_b1.py in the last 6 ROM banks (SCENE_BANK, layout.asm).
"""
import json
import pathlib
import sys

from PIL import Image

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import assets4 as A4  # noqa: E402

CONF = A4.ASSETS / "scenes/scenes.json"
REMAP = {18: 20, 21: 32, 53: 38, 55: 39, 58: 42, 59: 43, 60: 45, 61: 48}     # shared entry -> scene entry (remap)

# Colour sets (5 bits per channel) of the scenes, by role. Scene entry -> role (after the remap):
ROLE = {44: "floor0", 38: "floor1", 63: "floor2", 39: "floor3", 20: "floor4", 62: "floord",
        51: "wallL", 42: "wall0", 54: "wall1", 43: "wall2", 47: "wall3",
        48: "acc0", 45: "acc1", 40: "acc2", 32: "acc3"}
RECIPES = {
    # arcade level 8: pale pink floor and ceiling, mauve walls with a light blue hexagon bar
    "b": {"floor0": (31, 24, 23), "floor1": (28, 20, 19), "floor2": (23, 16, 16), "floor3": (17, 12, 12), "floor4": (10, 7, 7),
          "floord": (25, 17, 16), "wallL": (24, 20, 26), "wall0": (20, 15, 21), "wall1": (17, 13, 19), "wall2": (14, 11, 16),
          "wall3": (11, 8, 13), "acc0": (19, 25, 31), "acc1": (16, 22, 28), "acc2": (13, 18, 24), "acc3": (10, 14, 19)},
    # arcade level 10: terracotta floor, dark brown ceiling, light grey walls with a dark slate key (meander)
    "c": {"floor0": (26, 12, 8), "floor1": (22, 10, 6), "floor2": (17, 8, 5), "floor3": (12, 6, 4), "floor4": (7, 3, 2),
          "floord": (19, 8, 5), "wallL": (30, 31, 31), "wall0": (27, 28, 28), "wall1": (23, 24, 25), "wall2": (19, 20, 21),
          "wall3": (14, 15, 16), "acc0": (8, 11, 12), "acc1": (7, 9, 10), "acc2": (6, 8, 9), "acc3": (5, 6, 7)},
    # arcade level 13: mint floor and ceiling, pale blue walls with a thick orange zigzag outlined in dark blue
    "d": {"floor0": (17, 28, 22), "floor1": (13, 24, 19), "floor2": (10, 19, 15), "floor3": (7, 14, 11), "floor4": (4, 8, 6),
          "floord": (11, 21, 16), "wallL": (29, 31, 31), "wall0": (25, 28, 30), "wall1": (21, 24, 27), "wall2": (17, 20, 23),
          "wall3": (12, 15, 18), "acc0": (30, 13, 4), "acc1": (26, 11, 3), "acc2": (21, 9, 3), "acc3": (15, 7, 2)},
}


def conf():
    return json.loads(CONF.read_text())


def to8(c5):
    return [v * 255 // 31 for v in c5]


def load_scenes():
    """[(name, pixel rows 128 x 128, {entry: (r, g, b) 5 bits})] for the 4 scenes. Checks every sheet against palette.json outside
    the scene entries."""
    c = conf()
    entries = c["entries"]
    pal5 = A4.read_palette()
    out = []
    for sc in c["scenes"]:
        path = A4.ASSETS / sc["sheet"]
        im = Image.open(path)
        if im.mode != "P" or im.size != (128, 128):
            raise ValueError("%s must be a 128 x 128 indexed PNG" % path)
        pix = A4.load_4bpp(path, check_palette=False)[0]
        raw = im.getpalette() + [0] * 192
        own = {e: tuple(round(raw[e * 3 + k] * 31 / 255) for k in range(3)) for e in entries}
        used = {v for row in pix for v in row}
        bad = [i for i in sorted(used) if i not in entries and i != 0
               and [round(raw[i * 3 + k] * 31 / 255) for k in range(3)] != list(pal5[i])]
        if bad:
            raise ValueError("%s: palette entries %s are not scene entries and differ from palette.json" % (path, bad))
        if sc["sheet"] == "tiles/tiles_main.png":
            own = {e: tuple(pal5[e]) for e in entries}
        out.append((sc["name"], pix, own))
    return out


def scene_image(sc):
    """The game image (RAM, as the build patches it) with the panels of scene `sc` (scenes.json entry)."""
    sys.path.insert(0, str(A4.ROOT / "tools"))
    import corec_viewsim as V
    from wall_art import patch_wall_shapes
    img = bytearray(V.IMG)
    patch_wall_shapes(img, sc.get("panels"))
    return img


def scene_bins(outdir):
    """scene_<n>.bin (32 KiB: 64 lines direct + 64 lines mirrored, as the main set in tiles.bin) and scene_pal.bin (SCENE_PAL = SCENE_BANK + 5):
    0000h per scene 64 bytes of palette records, 0100h + scene * 0800h the scene's panel bytes (wall_art.PANEL_LO..PANEL_HI)."""
    from wall_art import PANEL_LO, PANEL_HI
    pal = bytearray(0x100 + 4 * 0x800)
    for n, ((name, pix, own), sc) in enumerate(zip(load_scenes(), conf()["scenes"])):
        tl = [[0] * 256 for _ in range(128)]
        for mirror, base in ((False, 0), (True, 64)):
            for t in range(A4.TILE_SETS[0][1]):
                for r in range(8):
                    row = pix[(t // 16) * 8 + r][(t % 16) * 8:(t % 16) * 8 + 8]
                    tl[base + (t >> 5) * 8 + r][(t & 31) * 8:(t & 31) * 8 + 8] = row[::-1] if mirror else row
        (outdir / ("scene_%d.bin" % n)).write_bytes(A4.pack(tl, 256, 128))
        rec = bytearray()
        for e in conf()["entries"]:
            rec += bytes([e * 4]) + bytes(own[e])
        pal[n * 64:n * 64 + len(rec)] = rec
        pal[0x100 + n * 0x800:0x100 + n * 0x800 + PANEL_HI - PANEL_LO] = scene_image(sc)[PANEL_LO:PANEL_HI]
    (outdir / "scene_pal.bin").write_bytes(bytes(pal))


def cmd_remap():
    c = conf()
    if c.get("remapped"):
        sys.exit("already remapped")
    p = A4.ASSETS / "tiles/tiles_main.png"
    im = Image.open(p)
    pal = im.getpalette()
    for old, new in REMAP.items():
        pal[new * 3:new * 3 + 3] = pal[old * 3:old * 3 + 3]
    im.putpalette(pal)
    im.putdata([REMAP.get(v, v) for v in im.getdata()])
    im.save(p, optimize=False)
    c["remapped"] = "2026-10-05"
    CONF.write_text(json.dumps(c, indent=1) + "\n")
    print("tiles_main.png remapped; now run: python3 tools/palette_sync.py assets/tiles/tiles_main.png")


def cmd_create():
    c = conf()
    src = Image.open(A4.ASSETS / "tiles/tiles_main.png")
    for sc in c["scenes"][1:]:
        key = sc["sheet"][-5]
        p = A4.ASSETS / sc["sheet"]
        if p.exists():
            sys.exit("%s exists" % p)
        im = src.copy()
        pal = im.getpalette()
        for e, role in ROLE.items():
            pal[e * 3:e * 3 + 3] = to8(RECIPES[key][role])
        im.putpalette(pal)
        im.save(p, optimize=False)
        print("created", p.relative_to(A4.ASSETS))


def cmd_preview():
    """A few typical views of level 1 in every scene, built by the game's own view builder with the scene's panels."""
    sys.path.insert(0, str(A4.ROOT / "tools"))
    import corec_viewsim as V
    import all_views as AV
    views = [(0x78, 2), (0x87, 0), (0x06, 1), (0x25, 0), (0x46, 1)]
    rgb = A4.palette_rgb()
    sc = 2
    scenes = load_scenes()
    out = Image.new("RGB", (len(views) * (128 * sc + 6), len(scenes) * (96 * sc + 6)), (255, 255, 255))
    orig = V.IMG
    for j, ((name, pix, own), scf) in enumerate(zip(scenes, conf()["scenes"])):
        col = list(rgb)
        for e, c5 in own.items():
            col[e] = tuple(to8(c5))
        V.IMG = AV.IMG = bytes(scene_image(scf))
        maze, _ = AV.maze_of(V.IMG[0x3E2E] | V.IMG[0x3E2F] << 8)
        for i, (pos, f) in enumerate(views):
            cells = V.build_view(maze, 0, pos, f)[0]
            im = Image.new("RGB", (128, 96))
            for r in range(12):
                for cc in range(16):
                    t = cells[r][cc]
                    for y in range(8):
                        for x in range(8):
                            im.putpixel((cc * 8 + x, r * 8 + y), col[pix[(t // 16) * 8 + y][(t % 16) * 8 + (7 - x if cc < 8 else x)]])
            out.paste(im.resize((128 * sc, 96 * sc), Image.NEAREST), (i * (128 * sc + 6), j * (96 * sc + 6)))
    V.IMG = AV.IMG = orig
    dst = A4.OUT.parent / "views/scenes.png"
    dst.parent.mkdir(parents=True, exist_ok=True)
    out.save(dst)
    print("preview", dst)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"remap": cmd_remap, "create": cmd_create, "preview": cmd_preview}.get(cmd, lambda: sys.exit(__doc__))()

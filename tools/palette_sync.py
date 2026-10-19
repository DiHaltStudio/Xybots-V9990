#!/usr/bin/env python3
"""BP6: one 64-colour palette shared by every colour sheet (sprites, tiles, signs, HUD panel tiles).

Usage: palette_sync.py <source.png>
  Takes the first 64 palette entries of the indexed PNG <source.png>, reduces them to the V9990's 5 bits per channel, writes them to
  assets/palette.json (the palette the build uploads) and puts the same palette (expanded back to 8 bits, i.e. exactly the colours the
  V9990 shows) into every colour sheet listed in SHEETS, the source included. Pixel indices are never touched: only the palette changes.
  Shape sheets (font, digits, icons, ui glyphs, vfont8/16: 0 = paper, anything else = ink) have no colours and are left alone.
Make targets: `make palette-from-sprites` (source assets/sprites/sprites.png), `make palette-from-tiles` (assets/tiles/tiles_main.png).
"""
import json
import pathlib
import sys

from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import assets4 as A4  # noqa: E402

# colour sheets that must share the palette (globs relative to assets/)
SHEETS = ("sprites/*.png", "tiles/*.png", "ui/*.png", "hud/hud_tiles.png", "hud/markers.png", "hud/variants/*.png",
          "shop/panel.png", "shop/invite.png")


def colour_sheets():
    seen = []
    for pat in SHEETS:
        for p in sorted(A4.ASSETS.glob(pat)):
            if p not in seen:
                seen.append(p)
    return seen


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    src = pathlib.Path(sys.argv[1])
    im = Image.open(src)
    if im.mode != "P":
        sys.exit("%s must be an indexed (palette) PNG, got %s" % (src, im.mode))
    raw = (im.getpalette() or []) + [0] * (A4.NCOL * 3)
    pal5 = [[round(raw[i * 3 + c] * 31 / 255) for c in range(3)] for i in range(A4.NCOL)]
    A4.write_palette(pal5)
    rgb = A4.palette_rgb()
    for p in colour_sheets():
        sheet = Image.open(p)
        if sheet.mode != "P":
            sys.exit("%s must be an indexed (palette) PNG, got %s" % (p, sheet.mode))
        sheet.putpalette([c for col in rgb for c in col] + [0] * ((256 - A4.NCOL) * 3))
        sheet.save(p, optimize=False)
        print("palette synced:", p.relative_to(A4.ASSETS))
    print("assets/palette.json <- %s (%d colours, 5 bits per channel)" % (src, A4.NCOL))


if __name__ == "__main__":
    main()

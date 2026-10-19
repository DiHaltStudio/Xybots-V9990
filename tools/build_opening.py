#!/usr/bin/env python3
"""Opening picture (title cover) of the BP6 ROM: shown once at power-on in V9990 mode B3 (512 x 424 interlaced, BD8 = 256 fixed RGB332
colours) until a fire key / joystick button is pressed, then the game boots as usual. Same method as the Sol Negro port.

  build_opening.py convert   ONE-TIME: assets/opening.png (512 x 424, any RGB or indexed PNG) -> assets/opening-b3.png, the editable
                             preview in the fixed RGB332 palette (colour = GGG RRR BB, nearest value of the 3-3-2 bits)
  build_opening.py build     assets/opening-b3.png -> build/opening-b3.bin (217,088 bytes, one byte per pixel, line y at y * 512);
                             refuses a preview whose pixels are not exact RGB332 colours (edit opening.png and `convert` again, or
                             paint in the preview with the fixed 256-colour palette it carries)
Run by tools/build_b1.py. The bitmap goes into 14 ROM banks after the game data; src/rom/opening.asm uploads it to VRAM 00000h.

Before the picture, the DiHalt logo (assets/dihalt_logo-b1.png, 256 x 212 indexed PNG, at most 16 colours; the same file as the
Pinball Dreams port, pinballdreams_v9990/pdmsx_b2pb6/ref/) is shown for 4 seconds in mode B1 (4 bpp): build_logo() packs it to
build/dihalt-logo.bin (2 pixels per byte, the left one in the high nibble, line y at y * 128) and returns its palette.
"""
import pathlib
import sys

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/opening.png"
PREVIEW = ROOT / "assets/opening-b3.png"
WIDTH, HEIGHT = 512, 424
LOGO = ROOT / "assets/dihalt_logo-b1.png"


def rgb332(r, g, b):
    return (((g * 7 + 127) // 255) << 5) | (((r * 7 + 127) // 255) << 2) | ((b * 3 + 127) // 255)


def palette():
    pal = []
    for code in range(256):
        pal.extend((((code >> 2) & 7) * 255 // 7, ((code >> 5) & 7) * 255 // 7, (code & 3) * 255 // 3))
    return pal


def convert(source=SOURCE, preview=PREVIEW):
    src = Image.open(source)
    if src.size != (WIDTH, HEIGHT):
        sys.exit("%s: expected %dx%d, got %s" % (source, WIDTH, HEIGHT, src.size))
    src = src.convert("RGB")
    px = src.load()
    out = Image.new("P", (WIDTH, HEIGHT))
    out.putdata([rgb332(*px[x, y]) for y in range(HEIGHT) for x in range(WIDTH)])
    out.putpalette(palette())
    out.save(preview, optimize=False)
    print("B3 / BD8 preview: %s -> %s" % (source.name, preview.name))


def build(preview=PREVIEW, bitmap=None):
    bitmap = pathlib.Path(bitmap or ROOT / "build/opening-b3.bin")
    im = Image.open(preview)
    if im.size != (WIDTH, HEIGHT) or im.mode not in ("RGB", "P"):
        sys.exit("%s: expected %dx%d RGB / indexed PNG, got %s %s" % (preview, WIDTH, HEIGHT, im.size, im.mode))
    im = im.convert("RGB")
    data = bytearray(WIDTH * HEIGHT)
    for i, (r, g, b) in enumerate(im.getdata()):
        code = rgb332(r, g, b)
        c = (((code >> 2) & 7) * 255 // 7, ((code >> 5) & 7) * 255 // 7, (code & 3) * 255 // 3)
        if (r, g, b) != c:
            sys.exit("%s: pixel %d,%d is RGB %s, not a fixed RGB332 colour; run `build_opening.py convert` again from opening.png"
                     % (preview, i % WIDTH, i // WIDTH, (r, g, b)))
        data[i] = code
    bitmap.parent.mkdir(parents=True, exist_ok=True)
    bitmap.write_bytes(data)
    return bitmap


def build_logo(source=LOGO, bitmap=None):
    """DiHalt logo -> (bitmap path, palette: 16 x (R, G, B) of 5 bits, backdrop colour). The colours are numbered in order of first
    appearance, so the top-left pixel's colour is 0 (the border)."""
    bitmap = pathlib.Path(bitmap or ROOT / "build/dihalt-logo.bin")
    im = Image.open(source)
    if im.mode != "P" or im.size != (256, 212):
        sys.exit("%s: expected a 256x212 indexed PNG, got %s %s" % (source, im.size, im.mode))
    raw = list(im.getdata())
    used = sorted(set(raw), key=raw.index)
    if len(used) > 16:
        sys.exit("%s: %d colours, B1 4 bpp allows 16" % (source, len(used)))
    remap = {c: i for i, c in enumerate(used)}
    data = [remap[v] for v in raw]
    bitmap.parent.mkdir(parents=True, exist_ok=True)
    bitmap.write_bytes(bytes((data[i] << 4) | data[i + 1] for i in range(0, len(data), 2)))
    full = im.getpalette()
    pal = [round(v * 31 / 255) for c in used for v in full[c * 3:c * 3 + 3]]
    return bitmap, pal + [0] * (48 - len(pal)), data[0]


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("convert", "build"):
        sys.exit(__doc__)
    if sys.argv[1] == "convert":
        convert()
    else:
        print("B3 / BD8 bitmap: %s" % build())

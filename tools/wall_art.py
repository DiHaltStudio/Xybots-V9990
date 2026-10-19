"""Shared tile placement for the ROM and Tiled wall views."""
import json
import os
from pathlib import Path


MAX_TILES = 253                     # tiles_main ids 0-252 (FDh / FFh are VT_STATIC / VT_UNKNOWN in HK_VT)


PANEL_LO, PANEL_HI = 0x8223, 0x8749   # the 36 panels and their decoration records (1318 bytes): copied per level scene (ADR-025)


def patch_wall_shapes(img, scene_panels=None):
    """Install the coordinated wall panels, view template and door decorations (assets/tiles/wall_panels.json) without changing table sizes.
    scene_panels: a scene's own panels (assets/scenes/scene_?.json, same format, "panels" only) instead of those of wall_panels.json.

    Each panel row, template row and decoration lands on a fixed screen row, so the ids there choose a tone per zone (tools/zone_tones.py)."""
    assets = Path(os.environ.get("XY_ASSETS4", Path(__file__).resolve().parents[1] / "assets"))
    meta = json.loads((assets / "tiles/wall_panels.json").read_text())
    panels, decos, template = meta["panels"], meta["decorations"], meta["template"]
    if scene_panels:
        panels = json.loads((assets / scene_panels).read_text())["panels"]
    if set(panels) != {str(s) for s in range(36)} or set(decos) != set(panels):
        raise ValueError("Expected all 36 wall panels and decorations")
    if len(template) != 12 or any(len(row) != 16 for row in template):
        raise ValueError("Expected a 16 x 12 view template")
    ok = range(MAX_TILES)
    for seg in range(36):
        ptr = int.from_bytes(img[0x8193 + 2 * seg:0x8195 + 2 * seg], "little")
        width = img[ptr]
        rows = panels[str(seg)]
        if len(rows) != 12 or any(len(row) != width for row in rows):
            raise ValueError("Unexpected dimensions for wall panel %d" % seg)
        if any(tile not in ok for row in rows for tile in row):
            raise ValueError("Invalid tile in wall panel %d" % seg)
        img[ptr + 1:ptr + 1 + 12 * width] = bytes(tile for row in rows for tile in row)
        q = ptr + 1 + 12 * width                       # door-decoration record: offset, kind, 0-4 tiles
        count = {0: 0, 1: 1, 2: 2, 3: 2}.get(img[q + 1], 4)
        tiles = decos[str(seg)]
        if len(tiles) != count or any(tile not in ok for tile in tiles):
            raise ValueError("Unexpected decoration tiles for wall panel %d" % seg)
        img[q + 2:q + 2 + count] = bytes(tiles)
    if any(tile not in ok for row in template for tile in row):
        raise ValueError("Invalid tile in the view template")
    img[0x7E5D:0x7E5D + 192] = bytes(tile for row in template for tile in row)
    return len(panels)

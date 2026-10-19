#!/usr/bin/env python3
"""Re-implementation of the XYBOTS software 3D view builder (sub_8749 and helpers) for verification.

Usage: corec_viewsim.py RAM_DUMP.bin [player]      (64 KiB memory dump, e.g. openMSX 'save_debuggable memory')

Static tables come from MSX/build/images/ram_after_load.bin (the tape image); the maze map F800h, the player
records (9A10h/9A20h) and the results (cell map 7F6Eh, occupancy words 8A6Fh/8A87h, visible list 88A6h/88BAh,
frame buffer EB00h) come from the dump.  It rebuilds them from the maze and compares byte for byte.

Model (see MSX/doc/analysis/core-c.md):
  * position byte = (y << 4) | x, additions are nibble-wise modulo 16 (add_pos);
  * facing 0..3 selects a 4-line-group template (8A9Fh/8AC3h/8AE7h/8B0Bh; facing 1 -> 8AE7h, facing 2 -> 8AC3h),
  * per template line: BIT opcode (46h bit0 / 4Eh bit1), cell step, next-line step; segments/line from 8A61h,
    (column, segment) pairs from 8B7Fh; wall shape = 8193h[seg] (width, 12*width tiles, decoration record),
    occupancy mask = 81DBh[seg];
  * visible list = 20 cells built from 8B2Fh (+20*facing), cells whose columns are all occluded become FFh.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
IMG = (ROOT / 'build/images/ram_after_load.bin').read_bytes()


def w16(a):
    return IMG[a] | IMG[a + 1] << 8


def add_pos(l, a):
    return (((l & 0xF0) + (a & 0xF0)) & 0xF0) | (((l & 0x0F) + (a & 0x0F)) & 0x0F)


def build_view(ram, player, pos, facing):
    """Return (cell map rows for the player's 16 columns, 12 occupancy words, visible list of 20 positions)."""
    off = 0x10 * player
    cmap = [[None] * 32 for _ in range(12)]
    for r in range(12):
        for c in range(16):
            cmap[r][c + off] = IMG[0x7E5D + r * 16 + c]
    b, c = pos >> 4, pos & 15
    start = {0: ((b - 3) & 15, (c - 4) & 15, 0x8A9F), 1: ((b - 4) & 15, (c + 4) & 15, 0x8AE7),
             2: ((b + 4) & 15, (c + 4) & 15, 0x8AC3), 3: ((b + 4) & 15, (c - 3) & 15, 0x8B0B)}
    y, x, tpl = start[facing]
    m = (y << 4) | x
    counts = IMG[0x8A61:0x8A61 + 12]
    iy = 0x8B7F
    occ = [0] * 12
    for line in range(12):
        bitn = (IMG[tpl] >> 3) & 7
        step = IMG[tpl + 1]
        for _ in range(counts[line]):
            col, seg = IMG[iy], IMG[iy + 1]
            iy += 2
            cell = ram[0xF800 + m]
            if cell & (1 << bitn):
                occ[line] |= w16(0x81DB + 2 * seg)
                p = w16(0x8193 + 2 * seg)
                wd = IMG[p]
                for r in range(12):
                    for k in range(wd):
                        cmap[r][col + off + k] = IMG[p + 1 + r * wd + k]
                q = p + 1 + 12 * wd
                if cell & (1 << (bitn + 4)):
                    o, kind = IMG[q], IMG[q + 1]
                    q += 2
                    d = col + off + o

                    def put(i, t):
                        cmap[i // 32][i % 32] = t
                    if kind == 1:
                        put(d, IMG[q])
                    elif kind == 2:
                        put(d, IMG[q]); put(d + 1, IMG[q + 1])
                    elif kind == 3:
                        put(d, IMG[q]); put(d + 32, IMG[q + 1])
                    elif kind >= 4:
                        put(d, IMG[q]); put(d + 1, IMG[q + 1]); put(d + 32, IMG[q + 2]); put(d + 33, IMG[q + 3])
            m = add_pos(m, step)
        m = add_pos(m, IMG[tpl + 2])
        tpl += 3
    # visible list
    lst, cur = [], pos
    for i in range(20):
        cur = add_pos(cur, IMG[0x8B2F + 20 * facing + i])
        lst.append(cur)
    cum, acc = [], 0
    for j in range(11):
        acc |= occ[11 - j]
        cum.append(acc)
    vis = list(lst)
    for i in range(20):
        if i == 18:
            continue
        j = (IMG[0x93B3 + i] - 1) // 2
        mask = (IMG[0x8868 + 2 * i] << 8) | IMG[0x8868 + 2 * i + 1]
        if cum[j] & mask >= mask:
            vis[i] = 0xFF
    return cmap, occ, vis


def frame_from_cellmap(ram, player):
    """Expected frame buffer bytes for the player's 16x12 viewport (mirrored left half)."""
    rev = [int('{:08b}'.format(i)[::-1], 2) for i in range(256)]
    out = {}
    off = 0x10 * player
    for r in range(12):
        for c in range(16):
            t = ram[0x7F6E + r * 32 + off + c]
            for k in range(8):
                v = IMG[0x751C + 8 * t + k]
                out[0xEB00 + r * 256 + k * 32 + off + c] = rev[v] if c < 8 else v
    return out


def main():
    ram = pathlib.Path(sys.argv[1]).read_bytes()
    player = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    rec = 0x9A10 + 0x10 * player
    pos, facing = ram[rec], ram[rec + 4]
    cmap, occ, vis = build_view(ram, player, pos, facing)
    off = 0x10 * player
    bad = sum(1 for r in range(12) for c in range(16) if cmap[r][c + off] != ram[0x7F6E + r * 32 + off + c])
    occ_ram = [ram[0x8A6F + 24 * player + 2 * i] | ram[0x8A70 + 24 * player + 2 * i] << 8 for i in range(12)]
    vis_ram = list(ram[0x88A6 + 20 * player:0x88A6 + 20 * player + 20])
    exp = frame_from_cellmap(ram, player)
    fbbad = sum(1 for a, v in exp.items() if ram[a] != v)
    print('player', player, 'pos %02X facing %d' % (pos, facing))
    print('cell map mismatches :', bad, '/ 192')
    print('occupancy words     :', 'OK' if occ == occ_ram else 'MISMATCH')
    print('visible list        :', 'OK' if vis == vis_ram else 'MISMATCH')
    print('frame buffer vs map :', fbbad, 'mismatching bytes of', len(exp), '(dumps taken before sub_7CB5 ran, or with sprites drawn afterwards, mismatch here)')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Build the MSX1 + V9990 B1 ROM: V9990-B1/build/xybots.rom.

Steps (SJASM 0.42c for all assembly):
  1. assemble the baseline LOADER and GAME sources and require byte identity with the tape extraction;
  2. apply the V9990 patch manifest to the game image (PATCHES below; every patch states the original bytes it replaces and the
     build fails if the image differs), optionally overlay edited assets (build_assets.py output);
  3. assemble the hook runtime (V9990-B1/src/hk_runtime.asm, org HK_BASE in the never-accessed zone C125h-EAFFh);
  4. pack pieces into ASCII16 banks (a piece never crosses a bank, at most 4 KiB: the boot buffer is 4 KiB), write chunks.inc /
     rom_data.inc, assemble stage B and the ROM.
Run from anywhere: python3 V9990-B1/tools/build_b1.py [--assets] [--out ROM]
"""
import argparse
import os
import shutil
import hashlib
import json
import math
import pathlib
import re
import struct
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import build_opening  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
V = ROOT
MSXB = ROOT / "build"
AUDIO = pathlib.Path(os.environ.get("XYBOTS_ARCADE_AUDIO", ROOT / "original/audio"))
ROMB = V / "build/rom"
DATA_START = 0x0800
MAX_PIECE = 0x1000
SKIP_LO, SKIP_HI = 0xC125, 0xEB00    # never-accessed zone: not stored (docs: memory-map.md)
HK_BASE = 0xC400
HK_LIMIT = 0xDFC0
STACK_RESIDUE = {a: 0xFF for a in (0x2E2, 0x2E3, 0x2E6, 0x2E7, 0x2EA, 0x2EB, 0x2EE, 0x2EF, 0x2F2, 0x2F3, 0x2F6, 0x2F7, 0x2FA, 0x2FB)}
STACK_RESIDUE[0x2FE] = 0xCB          # tape-run stack residue, evidence MSX/doc/evidence/tape_run_stack_residue.md


def sjasm(src, out, sym=False):
    r = subprocess.run(["sjasm"] + (["-s"] if sym else []) + [str(src), str(out)], capture_output=True, text=True, cwd=ROOT)
    if r.returncode != 0 or not pathlib.Path(out).exists() or "rror" in r.stdout:
        sys.exit("sjasm failed for %s:\n%s%s" % (src, r.stdout, r.stderr))


class Image:
    """The 64 KiB RAM picture of the game entry state: loader area 0000h-02FFh + game 0300h-FFFEh."""

    def __init__(self, loader, game):
        self.b = bytearray(0x10000)
        self.b[0:0x300] = loader
        self.b[0x300:0xFFFF] = game
        self.log = []

    def patch(self, addr, expect, new, why):
        cur = bytes(self.b[addr:addr + len(expect)])
        if cur != bytes(expect):
            sys.exit("patch %04X (%s): image has %s, manifest expects %s" % (addr, why, cur.hex(" "), bytes(expect).hex(" ")))
        assert len(new) == len(expect), "patch %04X changes the length" % addr
        self.b[addr:addr + len(new)] = new
        self.log.append((addr, bytes(expect), bytes(new), why))


def word(v):
    return bytes((v & 255, v >> 8))


# RST vectors used by the shims (page 0 RAM: bytes of the tape loader copy, never used by the game); the entry addresses are
# the fixed jump table at the start of the hook runtime (layout.asm)
RST_OUT98, RST_OUT99, RST_IN98, RST_IRQ, RST_WP1, RST_WP2 = 0x08, 0x10, 0x18, 0x20, 0x28, 0x30
ENT = {RST_OUT98: HK_BASE + 15, RST_OUT99: HK_BASE + 18, RST_IN98: HK_BASE + 21, RST_IRQ: HK_BASE + 24,
       RST_WP1: HK_BASE + 27, RST_WP2: HK_BASE + 30}
RST_OPCODE = {0x08: 0xCF, 0x10: 0xD7, 0x18: 0xDF, 0x20: 0xE7, 0x28: 0xEF, 0x30: 0xF7}
# Canonical read-modify-write routines of the minimap (one byte read then written): (write pair first OUT (99h), second OUT (99h)).
# Their read pair, IN A,(98h) and data OUT (98h),A stay un-shimmed; see hk_shims.asm. Each entry is verified against the image.
CANON_WRITE_PAIRS = [(0x3A0C, 0x3A11), (0x3A88, 0x3A8D), (0x3ABB, 0x3AC0), (0x3B5A, 0x3B5F), (0x3B80, 0x3B85), (0x3BC6, 0x3BCB),
                     (0x3BF0, 0x3BF3), (0xB8B0, 0xB8B5), (0xB8E1, 0xB8E6), (0xB913, 0xB918), (0xB96D, 0xB972), (0xB93F, 0xB944)]
CANON_UNSHIMMED = [0x39FD, 0x3A02, 0x3A07, 0x3A14, 0x3A78, 0x3A7D, 0x3A82, 0x3A90, 0x3AAB, 0x3AB0, 0x3AB5, 0x3AC3, 0x3B49, 0x3B4E,
                   0x3B54, 0x3B62, 0x3B6F, 0x3B74, 0x3B7A, 0x3B88, 0x3BB5, 0x3BBA, 0x3BC0, 0x3BCE, 0x3BDE, 0x3BE1, 0x3BE7, 0x3BF6,
                   0xB8A1, 0xB8A6, 0xB8AB, 0xB8B8, 0xB8D1, 0xB8D6, 0xB8DB, 0xB8EB, 0xB903, 0xB908, 0xB90D, 0xB91D, 0xB95D, 0xB962,
                   0xB967, 0xB977, 0xB92F, 0xB934, 0xB939, 0xB949]
# Not shimmed: the frame-buffer copy loops (7D9Bh-7DDEh) run at full speed; the hook replaces their effect (later milestones).
NO_SHIM = range(0x7D9B, 0x7DDF)
# Unreached but almost certainly code (minimap_plot_up, documented in game_B000.asm: "LIKELY code, no caller found"): these
# VDP instructions are patched too so that the shims see them if a path ever runs them.


_INSN = None


def trace_insns():
    """Decoded game instructions (recursive tracer + evidence entry points), cached."""
    global _INSN
    if _INSN is None:
        sys.path.insert(0, str(ROOT / "tools"))
        import z80trace
        mem = (MSXB / "images/ram_after_load.bin").read_bytes()
        ent = [0x300]
        for f in ("entry_points.txt", "entry_points_dynamic.txt"):
            for line in (ROOT / "tools/original" / f).read_text().splitlines():
                c = line.split("#")[0].split()
                if c:
                    ent.append(int(c[0], 16))
        _INSN = z80trace.trace(mem, ent)[0]
    return _INSN


def vdp_sites():
    """Addresses of OUT (98h),A / OUT (99h),A / IN A,(98h) in the decoded game code, from the recursive tracer + evidence files."""
    insn = trace_insns()
    s = {"out98": [], "out99": [], "in98": []}
    skip = set(NO_SHIM) | set(CANON_UNSHIMMED) | {x for pair in CANON_WRITE_PAIRS for x in pair}
    for a, i in insn.items():
        if a < 0x300 or a in skip:
            continue
        for key, text in (("out98", "out (0x98),a"), ("out99", "out (0x99),a"), ("in98", "in a,(0x98)")):
            if i.text.startswith(text):
                s[key].append(a)
    return {k: sorted(v) for k, v in s.items()}


def entry_hook(img, addr, expect, ent, why):
    if expect is None:
        expect = bytes(img.b[addr:addr + 3])    # routine replaced entirely: any first 3 bytes (branch targets are still checked)
    """Replace the first instructions of a game routine (bytes `expect`) by JP ent (+ NOP padding). The hook executes the replaced
    instructions itself. Fails if any decoded jump/call/jr targets the interior of the replaced bytes."""
    insn = trace_insns()
    for a, i in insn.items():
        if i.target is not None and addr < i.target < addr + len(expect):
            sys.exit("entry hook %04X (%s): %04X targets %04X inside the replaced bytes" % (addr, why, a, i.target))
    img.patch(addr, expect, bytes((0xC3, ent & 255, ent >> 8)) + bytes(len(expect) - 3), why)


def apply_patches(img):
    """The V9990 patch manifest. Each entry: address, original bytes, new bytes, purpose."""
    img.patch(0xC0DE, b"\xe2", b"\x82", "TMS R1 in the init table C0DDh: display off (bit 6) and TMS interrupt off (bit 5); the V9990 is the frame clock (ADR-008)")
    img.patch(0xBE39, b"\x03\xbe", word(HK_BASE + 3), "main loop end (BE38h jp z,main_loop) -> hook runtime hk_end_loop")
    for site, why in ((0xBDF5, "init (BDF4h)"), (0x281A, "shop (2819h)"), (0xBE19, "main loop (BE18h): actors are still in the frame buffer here, redraw_dirty_tiles at BE28h erases them")):
        img.patch(site, b"\x9b\x7d", word(HK_BASE + 6), "call copy_fb_to_vram_bottom at %s -> hk_present" % why)
    img.patch(0xBDB3, b"\xdb\x7d", word(HK_BASE + 12), "init: call copy_fb_to_vram_top (BDB2h) -> hk_top_copy (marks the 384 top cells dirty)")
    img.patch(0x7C76, b"\xdb\x99", bytes((RST_OPCODE[RST_IRQ], 0x00)), "IM 1 handler: IN A,(99h) (TMS status) -> RST 20h = acknowledge the V9990 vertical interrupt")
    for vec, ent in ENT.items():
        img.patch(vec, bytes(img.b[vec:vec + 3]), bytes((0xC3, ent & 255, ent >> 8)), "RST %02Xh stub: JP into the hook runtime" % vec)
    for site in (0x309A, 0xB64D, 0xAFFA, 0xBE6B):   # 3099h, B64Ch, AFF9h and the main path BE6Ah (call nz)
        img.patch(site, b"\xb5\x7c", word(HK_BASE + 33), "call render_cellmaps (7CB5h) -> hk_render: the cache learns which viewport halves were re-rendered")
    entry_hook(img, 0x37B2, b"\x21\x00\xeb", HK_BASE + 39, "clear_viewport_fb entry -> hk_clearvp (viewport becomes blank static cells)")
    entry_hook(img, 0x294C, b"\x3e\xff\x0e\x30", HK_BASE + 42, "fill_stripes entry -> hk_stripes (shop stripes)")
    entry_hook(img, 0x2FBD, b"\x3a\x12\x6e", HK_BASE + 45, "game_reset entry -> hk_greset (frame buffer zeroed)")
    entry_hook(img, 0x3F90, b"\x7b\xd9\x11\x94\x6f", HK_BASE + 48, "glyph_fb_small_draw entry -> hk_glyph1 (8-line glyph into the frame buffer)")
    entry_hook(img, 0x400A, b"\x7b\xd9\x11\x94\x6f", HK_BASE + 51, "draw_glyph_fb_2x entry -> hk_glyph2 (16-line glyph into the frame buffer)")
    entry_hook(img, 0x8E5F, b"\x32\xd3\x8e", HK_BASE + 54, "blit_sprite_2cells entry -> hk_blit1: the sprite is drawn by the V9990 from the 4 bpp atlas (ADR-011)")
    entry_hook(img, 0x8BCF, b"\x87\x32\x58\x8c", HK_BASE + 57, "blit_sprite_3cells entry -> hk_blit2")
    entry_hook(img, 0x8F1D, b"\xdd\xe5\x87\x87", HK_BASE + 60, "blit_sprite_4cells entry -> hk_blit3")
    for ptr, orig, new, rec in ((0xBD74, 0x1224, 0x21A0, "far"), (0xBD84, 0x121E, 0x21A3, "mid-far")):
        img.patch(ptr, word(orig) * 4, word(new) * 4, "level exit sprite set (BD6Ch), %s record: own frame %04Xh instead of the teleporter's "
                  "%04Xh (sprites.json; the pointer is only a key of the sprite table, the RAM there is never read)" % (rec, new, orig))
    entry_hook(img, 0x9D7E, b"\x3e\x06\x32\x0a\x92", HK_BASE + 63, "draw_all_actors entry -> hk_prepare (the draw page gets its background before the sprites)")
    entry_hook(img, 0xB40E, b"\xf5\xe5\x46", HK_BASE + 66, "blit_sign_bitmap entry -> hk_sign: DANGER signs drawn by the V9990 from the 4 bpp sign atlas (ADR-012)")
    entry_hook(img, 0x40B6, b"\x3e\x01\x32\xfe\x40", HK_BASE + 69, "print_string entry -> hk_print: unchanged frame-buffer texts are not reprinted (ADR-013)")
    entry_hook(img, 0x398F, b"\xdd\x7e\x00", HK_BASE + 72, "draw_actor_marker entry -> hk_marker: minimap markers XOR-drawn by the V9990 (ADR-013), the TMS minimap keeps only the walls")
    entry_hook(img, 0x3941, b"\x3a\xa0\x72", HK_BASE + 75, "minimap_actors entry -> hk_minimap: first call of a pass undoes the page's old markers and runs; the second (erase) call returns")
    entry_hook(img, 0xBEE9, b"\xcd\x1e\xbf", HK_BASE + 78, "input_player1 entry -> hk_input1: cursors / SPACE / Z X turn, joystick A (ADR-015)")
    entry_hook(img, 0xBF42, b"\x3e\x0f\xd3", HK_BASE + 81, "input_player2 entry -> hk_input2: joystick B, button B + left/right turns (ADR-015)")
    entry_hook(img, 0x9698, b"\x11\xb2\x96", HK_BASE + 84, "sub_9698 entry -> hk_ctrl: turn keys, no FIRE + LEFT/RIGHT turn (ADR-015)")
    entry_hook(img, 0xAC5D, b"\xdd\x7e\x0a", HK_BASE + 123, "l_AC5D (damage of a shot to a player) -> hk_cheat_hit: no damage while hk_cheat <> 0 (HK_CHEAT)")
    entry_hook(img, 0xB0EE, b"\xfd\x7e\x04", HK_BASE + 126, "l_B0EE (contact damage of an enemy that ran into a player) -> hk_cheat_bump: no energy loss while hk_cheat <> 0 (HK_CHEAT)")
    for addr, off, name in ((0xC04A, 87, "init_hardware"), (0x3F57, 90, "glyph_to_vram"), (0x2B89, 93, "draw_digit"),
                            (0x2CED, 96, "hud_clear_slot"), (0x2D88, 99, "hud_draw_icon"), (0x3AD8, 102, "reveal_cell"),
                            (0x3A61, 105, "open_west_door"), (0x3A97, 108, "open_north_door"), (0x30F9, 111, "minimap_wipe"),
                            (0x7F1D, 117, "set_view_colours"), (0x2243, 120, "st_waiting drawing tail")):
        entry_hook(img, addr, None, HK_BASE + off, "%s entry -> V9990 HUD / minimap hook (ADR-016: no TMS)" % name)
    entry_hook(img, 0x2FF3, bytes.fromhex("2100eb010c003e0132a672af320722"), HK_BASE + 114,
               "game_reset 2FF3h-3001h (frame-buffer fill setup + var_72A6 / shop_mask stores) -> hk_greset_tail: the stores, no CPU fill (ADR-017)")
    for a, i in sorted(trace_insns().items()):   # single HUD (split screen): the line interrupt must be served at once
        if a >= 0x300 and i.text == "di" and img.b[a] == 0xF3:
            img.patch(a, b"\xf3", b"\x00", "DI -> NOP: it only protected TMS address pairs (no TMS any more); the V9990 line interrupt at display line 96 switches the split screen")
    # Keep the original EI/HALT at 394Bh/394Ch: the minimap rebuild runs
    # after this IRQ wait, before the HUD is scanned again.
    img.patch(0xBE29, b"\xe3\xa2", word(HK_BASE + 9), "main loop: call redraw_dirty_tiles (BE28h) -> hk_nop: nothing writes the overlay map any more (actors and signs are native)")
    sites = vdp_sites()
    for key, opc, vec, pair in (("out98", 0xD3, RST_OUT98, 0x98), ("out99", 0xD3, RST_OUT99, 0x99), ("in98", 0xDB, RST_IN98, 0x98)):
        for a in sites[key]:
            img.patch(a, bytes((opc, pair)), bytes((RST_OPCODE[vec], 0x00)), "%s -> RST %02Xh" % (key, vec))
    for a in CANON_UNSHIMMED:   # sanity: these stay untouched but must really be VDP port accesses of the canonical routines
        assert bytes(img.b[a:a + 2]) in (b"\xd3\x98", b"\xd3\x99", b"\xdb\x98"), "canonical site %04X is not a VDP access" % a
    for first, second in CANON_WRITE_PAIRS:
        img.patch(first, b"\xd3\x99", bytes((RST_OPCODE[RST_WP1], 0x00)), "write pair of a canonical minimap RMW routine: first byte -> RST 28h")
        img.patch(second, b"\xd3\x99", bytes((RST_OPCODE[RST_WP2], 0x00)), "write pair: second byte -> RST 30h (marks the cell)")
    return sites


def apply_wall_panel_palette_fix(img):
    from wall_art import patch_wall_shapes
    changed = patch_wall_shapes(img.b)
    print("wall art: %d coordinated wall panels installed" % changed)
    from boss_art import patch_boss_map
    before = bytes(img.b[0x4BFC:0x4CBC])
    patch_boss_map(img.b)
    img.log.append((0x4BFC, before, bytes(img.b[0x4BFC:0x4CBC]), "Master Xybot room tile map (tools/boss_art.py)"))


# Dead code of the game image (ADR-022): bodies of routines the port replaced, never executed (coverage: recorded play, forced states,
# bot), no live instruction jumps into them or names an address inside them (checked again below on every build). The first bytes of a
# hooked routine (its JP into the runtime) and the operands other code still patches (7D02h-7D03h, 7D33h-7D34h, A2FAh-A2FBh, 3BA0h-3BA1h,
# 3BB0h) are outside; the check below counts a named address and the byte after it (16-bit stores).
DEAD_FREE = [(0x98E1, 0x992B), (0x7CB8, 0x7CD1), (0x7CD5, 0x7CF6), (0x7D04, 0x7D29), (0x7D35, 0x7D9A), (0x7D9E, 0x7DDA), (0x8E62, 0x8ECB),
             (0x8BD2, 0x8C4F), (0x8F20, 0x8FF3), (0xB411, 0xB44E), (0xA2E6, 0xA2F9), (0xA2FC, 0xA3A7), (0xA1F6, 0xA219),
             (0xC04D, 0xC0B2), (0x3F5A, 0x3F7C), (0x2B8C, 0x2BF9), (0x2CF0, 0x2D87), (0x2D8B, 0x2DAB), (0x3ADB, 0x3B9F),
             (0x3BB2, 0x3BD3), (0x3A64, 0x3A96), (0x3A9A, 0x3AC6), (0x30FC, 0x311E), (0x3992, 0x39C2), (0x7F20, 0x7F6D),
             (0x37B5, 0x37CC), (0x294F, 0x2969),
             (0xBEEC, 0xBF1D), (0xBF45, 0xBF65),   # input_player1's keyboard scan, input_player2's body (replaced by entry hooks, ADR-015)
             (0x6E14, 0x6EE2)]                     # the ZX Spectrum tape loader left in the image (game_6000.asm: unreachable; 6E13h is the
                                                   # second byte of the var_6E12 reference for the checker, ADR-054)


def place_dead_code_blocks(img, out, symtext):
    """The runtime binary is the main part (HK_BASE..hk_end) followed by the blocks hk_segN..hk_segN_end (hk_segs.asm, in order).
    Each block must lie inside one DEAD_FREE range and no live instruction may reach or name its bytes; it is patched into the game
    image. Returns the main part."""
    order = [int(n) for n in re.findall(r"^hk_seg(\d+):", (V / "src/hk_segs.asm").read_text(), re.M)]
    assert order == sorted(order), "hk_segs.asm: the blocks hk_segN must appear in increasing N (the binary holds them in source order)"
    sym = {m.group(1): int(m.group(2), 16) for m in re.finditer(r"^([a-z_0-9]+): equ 0*([0-9A-Fa-f]+)h", symtext, re.M)}
    main_len = sym["hk_end"] - HK_BASE
    blocks, n = [], 1
    while "hk_seg%d" % n in sym:
        blocks.append((sym["hk_seg%d" % n], sym["hk_seg%d_end" % n]))
        n += 1
    dead = set()
    for a, b in DEAD_FREE:
        dead.update(range(a, b + 1))
    live_refs = set()
    for p, i in trace_insns().items():
        if p in dead:
            continue
        if i.target is not None:
            live_refs.add(i.target)
        for x in re.findall(r"0x([0-9a-fA-F]{4})\b", i.text):
            live_refs.update((int(x, 16), int(x, 16) + 1))   # a 16-bit load / store also touches the next byte
    off = main_len
    for a, b in blocks:
        assert any(lo <= a and b - 1 <= hi for lo, hi in DEAD_FREE), "block %04X-%04X is not inside a dead range" % (a, b - 1)
        hit = sorted(x for x in live_refs if a <= x < b)
        assert not hit, "block %04X-%04X is referenced by live code at %s" % (a, b - 1, " ".join("%04X" % x for x in hit))
        img.patch(a, bytes(img.b[a:b]), out[off:off + b - a], "dead code %04X-%04X -> hook routines (hk_segs.asm, ADR-022)" % (a, b - 1))
        off += b - a
    assert off == len(out), "runtime output %d bytes, main %d + blocks %d" % (len(out), main_len, off - main_len)
    print("dead-code blocks: %d, %d bytes placed in the game image" % (len(blocks), off - main_len))
    return out[:main_len]


def coalesce_vram(vsegs, a4):
    """Boot VRAM files that are separated by small gaps that no other file covers become one file (gaps zero-filled): fewer stage B
    table entries (8 bytes each, the table shares C200h-C3FFh with the stage B code). Upload order is kept for the files not merged."""
    spans = sorted((va, va + f.stat().st_size, f) for f, va in vsegs)
    covered = lambda a, b, own: any(lo < b and a < hi for lo, hi, f in spans if f not in own)  # noqa: E731
    out, groups = [], []
    for lo, hi, f in spans:
        g = groups[-1] if groups else None
        if g and 0 <= lo - g[1] <= 0x1000 and g[1] - g[0] + (hi - g[1]) <= 0x4000 and not covered(g[1], lo, g[2] + [f]):
            g[1] = max(g[1], hi)
            g[2].append(f)
        else:
            groups.append([lo, hi, [f]])
    merged = {}
    for lo, hi, files in groups:
        if len(files) > 1:
            blob = bytearray(hi - lo)
            for f in files:
                va = next(v for x, v in vsegs if x == f)
                blob[va - lo:va - lo + f.stat().st_size] = f.read_bytes()
            name = a4 / ("boot_%05x.bin" % lo)
            name.write_bytes(bytes(blob))
            for f in files:
                merged[f] = (name, lo)
    done = set()
    for f, va in vsegs:
        if f in merged:
            if merged[f][0] not in done:
                done.add(merged[f][0])
                out.append(merged[f])
        else:
            out.append((f, va))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets", action="store_true", help="overlay the edited assets (V9990-P1/build/assets/patches.json)")
    ap.add_argument("--patches", help="patches.json from build_assets.py to overlay instead of the default (edit test)")
    ap.add_argument("--workdir", help="build in DIR/{src,build/rom} instead of the project tree (edit test); implies --out DIR/build/xybots.rom")
    ap.add_argument("--loop-frames", type=int, help="override HK_LOOP_FRAMES (with --workdir only): game-speed measurements")
    ap.add_argument("--cheat", type=int, help="override HK_CHEAT (with --workdir only): immunity tests")
    ap.add_argument("--out")
    args = ap.parse_args()
    global ROMB
    SRCV, BUILDV = V, V / "build"
    if args.workdir:
        wd = pathlib.Path(args.workdir)
        shutil.rmtree(wd, ignore_errors=True)
        shutil.copytree(V / "src", wd / "src", ignore=shutil.ignore_patterns("*.rom", "*.lst"))
        if args.loop_frames is not None:
            lay = wd / "src/layout.asm"
            lay.write_text(re.sub(r"HK_LOOP_FRAMES  equ \d+", "HK_LOOP_FRAMES  equ %d" % args.loop_frames, lay.read_text()))
        if args.cheat is not None:
            lay = wd / "src/layout.asm"
            lay.write_text(re.sub(r"HK_CHEAT        equ \d+", "HK_CHEAT        equ %d" % args.cheat, lay.read_text()))
        SRCV, BUILDV = wd, wd / "build"
        ROMB = BUILDV / "rom"
    if not args.out:
        args.out = str(BUILDV / "xybots.rom")
    ROMB.mkdir(parents=True, exist_ok=True)
    release_version = (V / "VERSION").read_text().strip()
    if not re.fullmatch(r"\d+\.\d+", release_version):
        sys.exit("VERSION must contain a release number such as 1.01")
    (ROMB / "version.inc").write_text('        db "XYBOTS V9990 v%s",13,10\n' % release_version)
    for tool in ("assets4.py", "hud4.py"):
        r = subprocess.run([sys.executable, str(V / "tools" / tool), "build"], capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit("%s build failed:\n%s%s" % (tool, r.stdout, r.stderr))
    if args.workdir:
        shutil.rmtree(BUILDV / "assets4", ignore_errors=True)
        shutil.copytree(os.environ.get("XY_ASSETS4_OUT", V / "build/assets4"), BUILDV / "assets4")
    loader_bin, game_bin, hk_bin = ROMB / "loader.bin", ROMB / "game.bin", ROMB / "hk_runtime.bin"
    shutil.copyfile(MSXB / "images/loader.bin", loader_bin)
    shutil.copyfile(MSXB / "images/game_0300_FFFE.bin", game_bin)
    low = bytearray(loader_bin.read_bytes())
    for a, v in STACK_RESIDUE.items():
        low[a] = v
    img = Image(bytes(low), game_bin.read_bytes())
    if args.assets and not args.patches:
        sys.exit("--assets requires --patches FILE")
    if args.patches:
        for a, h in json.loads(pathlib.Path(args.patches).read_text()).items():
            d = bytes.fromhex(h)
            img.b[int(a, 16):int(a, 16) + len(d)] = d
        print("edited assets applied")
    sites = apply_patches(img)
    apply_wall_panel_palette_fix(img)

    a4out = pathlib.Path(os.environ.get("XY_ASSETS4_OUT", V / "build/assets4"))
    pal = (a4out / "palette.bin").read_bytes()
    assert len(pal) == 192
    # the sprite table and, right after it (HK_BOOTPAL), the palette: one boot piece (stage B has no room for another); hk_boot moves
    # the table to HK_SPRTAB and sends the palette to the V9990
    (ROMB / "sprtab.bin").write_bytes((a4out / "sprtab.bin").read_bytes() + pal)
    sjasm(SRCV / "src/hk_runtime.asm", hk_bin, sym=True)   # also writes hk_runtime.sym next to the binary (profiling scripts)
    hk = place_dead_code_blocks(img, hk_bin.read_bytes(), hk_bin.with_suffix(".sym").read_text())
    lvl = int(re.search(r"^hk_scene_lvl: equ 0*([0-9A-Fa-f]+)h", hk_bin.with_suffix(".sym").read_text(), re.M).group(1), 16)
    img.patch(0x3024, b"\x77\x3c", word(lvl), "start_level: call load_level (3023h) -> hk_scene_lvl: the level's scenery first (ADR-025)")
    snd = int(re.search(r"^hk_snd: equ 0*([0-9A-Fa-f]+)h", hk_bin.with_suffix(".sym").read_text(), re.M).group(1), 16)
    img.patch(0x7C89, b"\x31\x41", word(snd), "IM 1 handler: call sound_tick (7C88h) -> hk_snd: Moonsound music when present (feature/music)")
    drain = int(re.search(r"^hk_cheat_drain: equ 0*([0-9A-Fa-f]+)h", hk_bin.with_suffix(".sym").read_text(), re.M).group(1), 16)
    entry_hook(img, 0xAD9F, b"\xdd\x35\x04", drain, "sub_AD81: dec (ix+4) (energy drain with time) -> hk_cheat_drain: no drain while hk_cheat <> 0 (HK_CHEAT)")
    pause = int(re.search(r"^hk_pause_wait: equ 0*([0-9A-Fa-f]+)h", hk_bin.with_suffix(".sym").read_text(), re.M).group(1), 16)
    img.patch(0x9783, bytes.fromhex("3e1dcd76bfc03e2acd76bf20"), bytes.fromhex("cd8a97c0c3") + word(pause) + bytes.fromhex("3e25c376bf"),
              "pause_check: H pauses / U resumes -> P pauses and P resumes: call 978Ah (ld a,25h = P / jp key_test), ret nz, jp hk_pause_wait "
              "(waits for the release, the next press and its release; ADR-037)")
    cred = int(re.search(r"^hk_credit_use: equ 0*([0-9A-Fa-f]+)h", hk_bin.with_suffix(".sym").read_text(), re.M).group(1), 16)
    img.patch(0x32B8, bytes.fromhex("35286a"), b"\xcd" + word(cred),
              "st_died: dec (hl) / jr z,l_3325 (consume a credit) -> call hk_credit_use: kept while hk_credinf <> 0 (F1 + fire on the opening, ADR-038)")
    gate = int(re.search(r"^hk_prep_gate: equ 0*([0-9A-Fa-f]+)h", hk_bin.with_suffix(".sym").read_text(), re.M).group(1), 16)
    img.patch(0x281C, bytes.fromhex("3a0722"), b"\xcd" + word(gate),
              "st_prepare_level: ld a,(shop_mask) (then and a / ret nz) -> call hk_prep_gate: also keep displaying while the partner is in PREPARE "
              "and has not printed its text yet (the last one out of the shop saw his shop until the end, ADR-050)")
    bend = int(re.search(r"^hk_boss_end: equ 0*([0-9A-Fa-f]+)h", hk_bin.with_suffix(".sym").read_text(), re.M).group(1), 16)
    img.patch(0x38A9, b"\xcd\x0e\x33", b"\xcd" + word(bend),
              "boss_fight_controls (victory): call boss_end_reset -> call hk_boss_end: deferred while the partner still fights its Master Xybot (ADR-051)")
    died = int(re.search(r"^hk_died_boss: equ 0*([0-9A-Fa-f]+)h", hk_bin.with_suffix(".sym").read_text(), re.M).group(1), 16)
    img.patch(0x32EC, bytes.fromhex("3aa072a7c8"), b"\xcd" + word(died) + b"\xc8\x00",
              "st_died: ld a,(var_72A0) / and a / ret z -> call hk_died_boss / ret z: the same, and a deferred boss_end_reset done when the last "
              "fighter dies (ADR-051; the ret z was lost at first: every death outside a fight ran the boss end, four levels down and a reset, ADR-054)")
    zap = int(re.search(r"^hk_zap_red: equ 0*([0-9A-Fa-f]+)h", hk_bin.with_suffix(".sym").read_text(), re.M).group(1), 16)
    img.patch(0x97C8, bytes.fromhex("3e12cdae98060a7610fd"), b"\xcd" + word(zap) + bytes(7),
              "l_97A5 (special attack): ld a,12h / call sub_98AE / 10 x HALT (red viewport) -> call hk_zap_red: the viewport's half of both "
              "display buffers filled red for 10 V9990 frames (ADR-039)")
    img.patch(0x98AA, b"\xcd\xae\x98", b"\xfb\x00\x00",
              "l_97A5 end: call sub_98AE (viewport colour table back to the player colour, 1536 shimmed OUTs) -> ei: the colour never changed "
              "(hk_zap_red paints the buffers), and the shimmed writes delayed the next frame by ~0.25 s (ADR-039)")
    hk_bin = ROMB / "hk_main.bin"
    hk_bin.write_bytes(hk)
    (ROMB / "loader_ram.bin").write_bytes(bytes(img.b[0:0x300]))
    (ROMB / "game_patched.bin").write_bytes(bytes(img.b[0x300:0xFFFF]))
    assert HK_BASE + len(hk) <= HK_LIMIT, "hook runtime is %d bytes, at most %d fit" % (len(hk), HK_LIMIT - HK_BASE)
    sprtab_n = (ROMB / "sprtab.bin").stat().st_size             # sprite table + palette
    assert 0xEB00 + sprtab_n <= 0xF700

    # (file, offset in file, destination, length)
    segs = [(ROMB / "loader_ram.bin", 0, 0x0000, 0x0300),
            (ROMB / "game_patched.bin", 0, 0x0300, SKIP_LO - 0x0300),
            (ROMB / "game_patched.bin", SKIP_HI - 0x0300, SKIP_HI, 0xFFFF - SKIP_HI),
            (ROMB / "sprtab.bin", 0, 0xEB00, sprtab_n),   # the unused CPU frame buffer (ADR-017): sprite table (hk_boot moves it to
                                                          # HK_SPRTAB), then the palette (HK_BOOTPAL)
            (hk_bin, 0, HK_BASE, len(hk))]   # LAST: its end (DA00h-DAFFh) lies in the transfer buffer DA00h-E9FFh, which no later piece
                                             # may reuse; its pieces copy downwards (destination below the source), so they are safe
    pieces = []
    for f, off, dest, n in segs:
        done = 0
        while done < n:
            k = min(MAX_PIECE, n - done)
            pieces.append((f, off + done, dest + done, k))
            done += k
    pos = DATA_START
    placed = []
    for f, off, dest, k in pieces:
        if pos % 0x4000 + k > 0x4000:
            pos = (pos // 0x4000 + 1) * 0x4000
        placed.append((f, off, dest, k, pos))
        pos += k
    # 4 bpp atlases (tools/assets4.py build) -> VRAM at boot: (file, vram address, length), split into <= 16 KiB pieces in whole banks
    A4 = pathlib.Path(os.environ.get("XY_ASSETS4_OUT", V / "build/assets4"))
    hudf = json.loads((A4 / "hud_files.json").read_text())
    vsegs = [(A4 / f, y * 256) for f, y in hudf["files"]] + [(A4 / hudf["map"][0], hudf["map"][1] * 256)]   # BP6: 256 bytes per line
    vsegs = coalesce_vram(vsegs, A4)
    vplaced = []
    pos = (pos + 0x3FFF) // 0x4000 * 0x4000
    for f, va in vsegs:
        n = f.stat().st_size
        pos = (pos + 0x3FFF) // 0x4000 * 0x4000     # every file starts on a bank: its 16 KiB pieces never cross one
        done = 0
        while done < n:
            k = min(0x4000, n - done)
            vplaced.append((f, done, va + done, k, pos))
            pos += k
            done += k
    # opening picture (tools/build_opening.py): 512 x 424 bytes in whole banks after the game data, uploaded by src/rom/opening.asm
    opening_bin = build_opening.build(bitmap=BUILDV / "opening-b3.bin")
    opn = opening_bin.stat().st_size
    pos = (pos + 0x3FFF) // 0x4000 * 0x4000
    open_bank, open_banks, open_pos = pos // 0x4000, (opn + 0x3FFF) // 0x4000, pos
    assert open_bank + open_banks <= 256, "opening does not fit in 256 ROM banks"
    open_last_blocks = (opn - (open_banks - 1) * 0x4000 + 255) // 256
    pos += opn
    # DiHalt logo (tools/build_opening.py build_logo): 256 x 212 at 4 bpp in whole banks after the opening picture, shown first by
    # src/rom/opening.asm in mode B1 with the palette of logo_pal.inc
    logo_bin, logo_pal, logo_backdrop = build_opening.build_logo(bitmap=BUILDV / "dihalt-logo.bin")
    lgn = logo_bin.stat().st_size
    pos = (pos + 0x3FFF) // 0x4000 * 0x4000
    logo_bank, logo_banks = pos // 0x4000, (lgn + 0x3FFF) // 0x4000
    logo_last_blocks = (lgn - (logo_banks - 1) * 0x4000 + 255) // 256
    pos += lgn
    (ROMB / "opening.inc").write_text("; generated by build_b1.py: opening bitmap and DiHalt logo in the ROM\nOPEN_BANK        equ %d\n"
                                      "OPEN_BANKS       equ %d\nOPEN_LAST_BLOCKS equ %d\nLOGO_BANK        equ %d\nLOGO_BANKS       equ %d\n"
                                      "LOGO_LAST_BLOCKS equ %d\nLOGO_BACKDROP    equ %d\n" % (
                                          open_bank, open_banks, open_last_blocks, logo_bank, logo_banks, logo_last_blocks, logo_backdrop))
    (ROMB / "logo_pal.inc").write_text("; generated by build_b1.py: DiHalt logo palette, 16 x (R, G, B) of 5 bits\n" + "".join(
        "        db %s\n" % ",".join("%d" % v for v in logo_pal[k:k + 3]) for k in range(0, 48, 3)))
    sjasm(SRCV / "src/rom/opening.asm", ROMB / "opening.bin", sym=True)
    # level scenery (ADR-025): fixed banks at the end of the ROM (the runtime is assembled before the other banks are known)
    scene_bank = int(re.search(r"^SCENE_BANK\s+equ\s+(\d+)", (SRCV / "src/layout.asm").read_text(), re.M).group(1))
    assert pos <= scene_bank * 0x4000, "ROM data reaches the scenery banks (SCENE_BANK %d)" % scene_bank
    assert (A4 / "scene_store.bin").stat().st_size <= 4 * 0x4000 and (A4 / "scene_list.bin").stat().st_size <= 0x4000
    assert (A4 / "scene_pal.bin").stat().st_size == 0x2100
    rom_size = (scene_bank + 6) * 0x4000         # + the effect banks (below): 2 MiB with the power-of-two padding
    # Moonsound music (feature/music): fixed banks MUSIC_BANK.. (music.inc), each = player (src/rom/opl4_player.asm) + stream data
    minc = (SRCV / "src/music.inc").read_text()
    music_bank = int(re.search(r"^MUSIC_BANK\s+equ\s+(\d+)", minc, re.M).group(1))
    music_banks = int(re.search(r"^MUSIC_BANKS\s+equ\s+(\d+)", minc, re.M).group(1))
    music_data = int(re.search(r"^MUSIC_DATA\s+equ\s+0x([0-9a-fA-F]+)", minc, re.M).group(1), 16)
    assert pos <= music_bank * 0x4000 and music_bank + music_banks <= scene_bank, "ROM data reaches the music banks"
    import opl4_stream
    # the voices (ADR-027): (sample 8-bit 22050 / 11025 / 7350 Hz, song, frame of its stream, wave channel); the arcade ones recorded in
    # MAME, at 7350 Hz (ADR-034: they hold almost nothing above 3.5 kHz, the arcade's samples are about 7 kHz)
    import wave
    LOGO_LEN = 10.0                             # the logo song (see the songs below): 10.0 s, five bars of 120 BPM (dihalt34.mid, ADR-049)
    LOGO_VOICE = round((6.5 - 0.12) * 50)       # its voices (assets/voices/logo_voces.wav, the user's set of voices, ADR-049): the first
                                                # word 0.12 s into the sample at 6.5 s, a little after the arpeggio (the repeats) starts at
                                                # 6.0 s (user); it ends at 8.5 s, before the logo's end
    rnd_ch = int(re.search(r"^VOICE_RND_CH\s+equ\s+(\d+)", minc, re.M).group(1))
    voices = [("logo_voces_11k.wav", "logo", LOGO_VOICE, 23),             # the logo's voices (tone 384, part 0, copied before the logo;
                                                                          # replaces "DiHalt Studio", ADR-034, unused since ADR-049)
              ("intro_voz1_7k.wav", "menu", 219, 23), ("intro_voz2_7k.wav", "menu", 432, 22),       # 4.38 s / 8.63 s into the arcade intro
              ("level_voz3_7k.wav", "level", 0, rnd_ch),                  # at the start of the game, with the level song: the
              ("level_voz4_7k.wav", "level", None, None),                 # player adds 0-3 to this key-on's tone number (ms_rnd), so
              ("level_voz5_7k.wav", "level", None, None),                 # one of these four (tones 387-390, consecutive) plays at
              ("level_voz6_7k.wav", "level", None, None),                 # random, as in the arcade (ADR-031: the user's recordings)
              # the Master Xybot (ADR-032; arcade sound codes D3h / D7h / D6h, recorded in MAME; nothing above 3.5 kHz: 7350 Hz): at the
              # start of the fight with its song; when a part is destroyed / the last one (the player's ms_bossv: tones 392-394 / 395)
              ("boss_voz_inicio_7k.wav", "boss", 0, 22),
              ("boss_voz_impacto_7k.wav", "boss", None, None),
              ("boss_voz_impacto2_7k.wav", "boss", None, None),     # two more hits (arcade codes DBh / DCh, user's choice): the
              ("boss_voz_impacto3_7k.wav", "boss", None, None),     # player keys one of the three at random (tones 392-394)
              ("boss_voz_fin_7k.wav", "boss", None, None)]
    voice_bank = int(re.search(r"^VOICE_BANK\s+equ\s+(\d+)", minc, re.M).group(1))
    voice_banks = int(re.search(r"^VOICE_BANKS\s+equ\s+(\d+)", minc, re.M).group(1))
    assert [k for k, v in enumerate(voices) if v[0].startswith("level_voz")] == [3, 4, 5, 6], "the start voices: tones 387-390"
    assert [v[0] for v in voices].index("boss_voz_impacto3_7k.wav") == [v[0] for v in voices].index("boss_voz_impacto_7k.wav") + 2
    for sym, name in (("VOICE_TONE_HIT", "boss_voz_impacto_7k.wav"), ("VOICE_TONE_DIE", "boss_voz_fin_7k.wav")):
        assert 384 + [v[0] for v in voices].index(name) == int(re.search(r"^%s\s+equ\s+(\d+)" % sym, minc, re.M).group(1)), sym
    # sample rate -> (octave, F-number): 44100 x 2^(oct-1) x (1 + F / 1024); 7350 Hz: the player's VOICE_7K_R20 / R38 (music.inc)
    pitch = {22050: (0, 0), 11025: (-1, 0), 7350: (-2, 341)}
    voice_ram = 0x200000 + int(re.search(r"^VOICE_RAM\s+equ\s+0x([0-9a-fA-F]+)", minc, re.M).group(1), 16)
    headers, extra, voice_len = b"", {"logo": {}, "level": {}, "menu": {}, "boss": {}}, []
    parts = [b"", b""]                          # samples copied at the first ms_open (the logo song's voice), the others when fire
                                                # is pressed on the opening picture
    # the logo song's instruments in the RAM (ADR-049; midi2wave.py --map track=ram:<name>): the waveforms of instruments created for
    # the SCC (assets/music/scc_waves.json, 32 samples looped, played on the OPL4) and a dry snare (tools/drum_synth.py); first in
    # part 0 (copied with the tone headers before the logo); their tone headers after the effects' (tones ram_tone..)
    ram_ins = []
    LOGO_DRUMS = ()
    for name, w in json.loads((V / "assets/music/scc_waves.json").read_text())["waves"].items():
        assert len(w) == 32
        ram_ins.append((name, bytes(v & 0xFF for v in w), 0, 32 * 261.6256, False))     # loop from 0: the rate plays MIDI note 60
    for name in ("scc00", "scc23", "scc03"):    # "dark" copies (<name>_osc): the first two harmonics only, the same RMS: the logo's
        w = json.loads((V / "assets/music/scc_waves.json").read_text())["waves"][name]    # instruments open from them (ADR-049)
        co = [sum(v * complex(math.cos(2 * math.pi * h * i / 32), -math.sin(2 * math.pi * h * i / 32)) for i, v in enumerate(w))
              for h in (1, 2)]
        d = [sum(2 * (c * complex(math.cos(2 * math.pi * h * i / 32), math.sin(2 * math.pi * h * i / 32))).real / 32
                 for h, c in zip((1, 2), co)) for i in range(32)]
        k = math.sqrt(sum(v * v for v in w) / max(1e-9, sum(v * v for v in d)))
        d = [max(-127, min(127, round(v * k))) for v in d]
        ram_ins.append((name + "_osc", bytes(v & 0xFF for v in d), 0, 32 * 261.6256, False))
    with wave.open(str(V / "assets/music/ruido_loop_44k.wav")) as w:   # white noise looped (tools/drum_synth.py --noise): the
        assert w.getsampwidth() == 1 and w.getnchannels() == 1 and w.getframerate() == 44100   # logo's push (ADR-049)
        pcm = bytes((b - 128) & 0xFF for b in w.readframes(w.getnframes()))
    ram_ins.append(("ruido", pcm, 0, 44100, True))
    for name in LOGO_DRUMS:                     # one shots (loop on the silent tail): caja_seca (the dry snare), golpe_scc (a low hit of
                                                # SCC instruments); none for now (the user: the logo song without a snare)
        with wave.open(str(V / ("assets/music/%s_22k.wav" % name))) as w:
            assert w.getsampwidth() == 1 and w.getnchannels() == 1 and w.getframerate() == 22050
            pcm = bytes((b - 128) & 0xFF for b in w.readframes(w.getnframes()))
        ram_ins.append((name, pcm + b"\0" * 16, len(pcm), 22050, True))
    ram_addr = []
    for name, pcm, loop, rate, fixed in ram_ins:
        ram_addr.append(voice_ram + len(parts[0]))
        parts[0] += pcm
    for k, (name, song, frame, ch) in enumerate(voices):
        with wave.open(str(AUDIO / "voices" / name)) as w:
            rate = w.getframerate()
            assert w.getsampwidth() == 1 and w.getnchannels() == 1 and rate in pitch, name
            pcm = bytes((b - 128) & 0xFF for b in w.readframes(w.getnframes())) + b"\0" * 16   # signed; silent tail (the chip loops)
        n = len(pcm) - 16
        assert len(pcm) < 0x10000, "a tone is at most 65535 samples"
        voice_len.append((name, n * 22050 // rate))
        part = 0 if song == "logo" else 1
        assert part or not parts[1], "the intro's voices come first"
        if part:
            parts[0] += b"\0" * (-len(parts[0]) % 256)
        a = voice_ram + len(parts[0]) + len(parts[1])
        end = (n + 15) ^ 0xFFFF
        headers += bytes([a >> 16 & 0x3F, a >> 8 & 255, a & 255, n >> 8, n & 255, end >> 8, end & 255,
                          0x00, 0xF0, 0x00, 0x0F, 0x00])   # 8-bit; loop on the tail; AR 15, D1R 0, DL 0, D2R 0, RR 15
        parts[part] += pcm
        tone = 384 + k
        # key off, F-number bits 6-0 + wave number bit 8, wave number (loads the header), octave + F-number bits 9-7 (octave 0 = 22050
        # Hz; -1 = 11025 Hz; -2 and F 341 = 7348 Hz), TL 0, key on, centre
        octave, fnum = pitch[rate]
        for fr in (() if frame is None else frame if isinstance(frame, tuple) else (frame,)):     # a tuple: the same voice at several frames
            extra[song].setdefault(fr, []).extend([(0x68 + ch, 0x00), (0x20 + ch, (fnum & 0x7F) << 1 | tone >> 8),
                                                   (0x08 + ch, tone & 255), (0x38 + ch, (octave & 15) << 4 | fnum >> 7),
                                                   (0x50 + ch, 0x01), (0x68 + ch, 0x80)])
    parts = [p + b"\0" * (-len(p) % 256) for p in parts]
    # the arcade effects (ADR-044, music.inc): 22050 Hz, tones FX_TONE.. after the voices, samples at FX_RAM + 100h.. (ms_fxstep copies
    # them while the opening picture is shown, only with more than 128 KiB of Moonsound RAM), in ROM banks FX_BANK.. after the scenery
    fx_names = ["disparo", "disparo_doble", "impacto", "impacto_doble", "moneda", "llave", "energia", "salida", "teletransporte"]
    fx_tone = int(re.search(r"^FX_TONE\s+equ\s+(\d+)", minc, re.M).group(1))
    fx_bank = int(re.search(r"^FX_BANK\s+equ\s+(\d+)", minc, re.M).group(1))
    fx_ram = int(re.search(r"^FX_RAM\s+equ\s+0x([0-9a-fA-F]+)", minc, re.M).group(1), 16)
    assert fx_tone == 384 + len(voices) and fx_bank == scene_bank + 6, "FX_TONE after the voices, FX_BANK after the scenery"
    fx = b""
    for name in fx_names:
        with wave.open(str(AUDIO / "sfx" / (name + "_22k.wav"))) as w:
            assert w.getsampwidth() == 1 and w.getnchannels() == 1 and w.getframerate() == 22050, name
            pcm = bytes((b - 128) & 0xFF for b in w.readframes(w.getnframes())) + b"\0" * 16
        n = len(pcm) - 16
        assert len(pcm) < 0x10000, "a tone is at most 65535 samples"
        a = fx_ram + 0x100 + len(fx)
        end = (n + 15) ^ 0xFFFF
        headers += bytes([a >> 16 & 0x3F, a >> 8 & 255, a & 255, n >> 8, n & 255, end >> 8, end & 255, 0x00, 0xF0, 0x00, 0x0F, 0x00])
        fx += pcm + b"\0" * (-len(pcm) % 256)
    ram_tone = 384 + len(voices) + len(fx_names)
    ram = {}
    for k, ((name, pcm, loop, rate, fixed), a) in enumerate(zip(ram_ins, ram_addr)):
        end = (len(pcm) - 1) ^ 0xFFFF
        headers += bytes([a >> 16 & 0x3F, a >> 8 & 255, a & 255, loop >> 8, loop & 255, end >> 8, end & 255, 0x00, 0xF0, 0x00, 0x0F, 0x00])
        ram[name] = dict(tone=ram_tone + k, rate=rate, fixed=fixed, rr=6 if not fixed else 15)
    ram["ruido_t"] = dict(ram["ruido"], rate=44100 / 4, fixed=False)   # the noise by key: MIDI 60 two octaves down (the push's glide)
    assert voice_ram + len(parts[0]) + len(parts[1]) <= 0x220000
    fx_blocks = len(fx) // 256
    fx_banks = (len(fx) + 0x3FFF) // 0x4000
    assert voice_ram + len(parts[0]) + len(parts[1]) <= fx_ram and fx_ram + 0x100 + len(fx) <= 0x2A0000, "the effects: after the voices, within 640 KiB"
    (ROMB / "fx.inc").write_text("; generated by build_b1.py: the arcade effects (ADR-044)\nFX_BLOCKS       equ %d\nFX_END          equ 0x%06x\n" % (
        fx_blocks, fx_ram + 0x100 + len(fx) - 1))
    sjasm(SRCV / "src/rom/opl4_player.asm", ROMB / "opl4_player.bin")
    player = (ROMB / "opl4_player.bin").read_bytes()
    assert len(player) <= music_data - 0x4000
    assert len(headers) <= 0x600 and voice_ram + len(parts[0]) + len(parts[1]) <= 0x220000, "the voices exceed 128 KiB of Moonsound RAM"
    voice = struct.pack("<H", len(headers)) + headers + struct.pack("<HH", len(parts[0]) // 256, len(parts[1]) // 256)
    voice += b"\0" * (-len(voice) % 256) + parts[0] + parts[1]      # the samples from a 256-byte boundary (ms_blocks)
    assert len(voice) <= voice_banks * 0x4000 and pos <= voice_bank * 0x4000 and voice_bank + voice_banks <= music_bank
    # songs (music.inc SONG_*): (name, OPL4 writes, first bank symbol, voice key-ons, loop point in frames of 50 Hz)
    #   logo:  assets/music/logo.mid (the user's song4.mid, composed in GarageBand: piano, strings, guitarra "Hard Rock") on the
    #          wave part with the GM instruments of the YRW801 ROM (tools/midi2wave.py; the guitar as GM 30 Distortion Guitar, the
    #          track's program), while the DiHalt logo is shown (opening.asm LOGO_MS_FRAMES; ADR-033); strings and guitar start
    #          one bar later in the MIDI (beat 4): moved one bar earlier, so that the three tracks start together (user); the song
    #          then ends at 4.75 s (the strings), LOGO_LEN 6.0 s (three bars) leaves their release ringing; "DiHalt Studio" (LOGO_VOICE)
    #          Now (ADR-049) assets/music/dihalt34.mid, the user's second fanfare (GarageBand, 7 tracks, 5 bars, 10.0 s): the GM
    #          programs of the MIDI (the track names would give nylon guitar / grand piano), its pitch bend at the start (guitar1)
    #          played; at most 18 of the 22 wave channels at once. logo.mid stays in assets/music to compare (LOGO_MID)
    #   level: the arcade "04 Music 1" (YM2151; the user's choice for the odd levels) translated to the FM part
    #          (tools/opm2opl3.py), loop at 1.37 s of 56.40 s (the VGM's loop point), with the
    #          arcade "01 Player 1 Coin" at its start (the game starts: OPM channel 0, which the song does not use)
    #   level2: the arcade "07 Music 4" (YM2151) the same way, loop at 11.22 s of 52.36 s (the VGM's loop point), no jingle; the two
    #          level songs alternate (level index even, levels 1, 3...: level; odd, levels 2, 4...: level2); "06 Music 3"
    #          (assets/music/level2_arcade.vgz) is no longer used
    #   shop:  the arcade "09 Shop" (YM2151, 31.5 s, no loop point in the VGM: the whole song loops) the same way, while player 1 is
    #          in the shop or on PREPARE TO ENTER LEVEL (actor states 20h / 21h)
    #   boss:  the arcade "08 Master Xybots" (YM2151, 22.3 s, loop at 1.12 s from the VGM) the same way, in the Master Xybot fight; his voice D3h at its start (ADR-032)
    #   menu:  the arcade "03 Intro" (YM2151) translated to the FM part; its echo channels 5 and 6 on 2-operator channels;
    #          4.5 dB quieter, so that its two voices stand out
    import opm2opl3
    import midi2wave
    LOGO_MID = "dihalt34.mid"
    # dihalt34's arrangements (ADR-049): LOGO_VERSION picks one. Against the user's GarageBand render (dihalt3 .wav; the MIDI has no
    # track volumes) the guitars and pianos fade while held as there (about 6 dB a second); the RAM instruments: the waveforms of
    # instruments created for the SCC, OPL4 PCM tones (assets/music/scc_waves.json; auditions "ondas SCC/onda NN.wav"); no snare (user: LOGO_DROP; it was
    # the ROM kit's Electric Snare, notemap 38 -> 40, or ram:golpe_scc / ram:caja_seca with LOGO_DRUMS); boost -9 (10 by default): the
    # RAM waveforms are full scale, the song at the level of the game's songs; the tremolo after the second melody (the final A4 / E5
    # from 4.88 s, 5.9 Hz, 5.9 dB) and the crescendo into it (the doublings enter 9 dB down at 2.6 s and grow to 4.4 s): user
    MELODY = ("guitar1", "guitar2", "piano1", "piano2")
    LOGO_VERSIONS = {
        # "scc": kept by the user ("esta version esta bastante bien vamos a guardarla")
        "scc": dict(maps={"guitar1": "ram:scc00", "guitar2": "ram:scc27", "piano1": "ram:scc22", "piano2": "ram:scc39",
                          "strings": "ram:scc23", "bass": "ram:scc03"},
                    gain={"strings": -10, "bass": -6, "guitar1": 2, "guitar2": -4, "piano1": -4, "piano2": -4}),
        # "distorsion": the first and second melody (the four melody tracks) on the ROM's GM 30 Distortion Guitar, the rest as "scc"
        "distorsion": dict(maps={"guitar1": "30", "guitar2": "30", "piano1": "30", "piano2": "30",
                                 "strings": "ram:scc23", "bass": "ram:scc03"},
                           gain={"strings": -10, "bass": -6, "guitar1": 14, "guitar2": 14, "piano1": 14, "piano2": 14}),
    }                                           # the ROM guitar 12 dB up (the doublings 18): quieter than the full-scale RAM waveforms
    # "scc_mejorada" (user: "haz todos estos cambios ... si luego no nos gusta volvemos al estado anterior"): "scc" plus stereo (the
    # fifth guitar2 to the left, the echo to the right), a Konami echo of the melody (guitar1 an eighth later, 9 dB down), a chorus
    # (guitar1 again 8 cents up, 6 dB down, to the left), a light vibrato with the final chord's tremolo, the octave track piano1 as
    # an arpeggio over the final chord (A4 E5 A5 E5 in semiquavers), a closing hit at 9.0 s (an A / E chord of every track, held to
    # the logo's end, fading with the tremolo), the fourth below (piano2) left out, the strings an octave up (they sat on the bass's E3)
    LOGO_VERSIONS["scc_mejorada"] = dict(
        maps=dict(LOGO_VERSIONS["scc"]["maps"], eco="ram:scc00", coro="ram:scc00"),
        gain=dict(LOGO_VERSIONS["scc"]["gain"], eco=2 - 9, coro=2 - 6, guitar2=-1, piano1=-1),   # the doublings 3 dB up: the echo
                                                # and the chorus fill the first melody too (else +1.2 dB to the second)
        copies={"eco": ("guitar1", 0.5), "coro": ("guitar1", 0)}, detune={"coro": 8},
        pan={"guitar2": 3, "eco": 13, "coro": 4}, vibrato=1, drop=["piano2"], transpose={"strings": 12},
        arp={"piano1": (12, 0.25, [0, 7, 12, 7], 0.5, 19.5)},   # from 6.0 s in semiquavers (user: later; then "mas repeticiones
                                                # como antes", "alguna repeticion mas"): to 9.75 s (was the held notes' end, 8.88 s),
                                                # 0.5 dB quieter a note (1 and 2: the added ones hardly heard; was 2.5)
        # the start: a push (user: "algo que empuja ... como sube el volumen para luego normalizarse", like the arcade's partial
        # energy sound, code 78h: -36 -25 -18 -13 -9 -6 -4 -2 -1 0 dB by 40 ms): that curve over the first 0.5 s, 4 dB over the
        # level at 0.55 s, back to it at 1.5 s (was a straight 15 dB fade in over 1.5 s)
        fade_in=[(0.12 + t, d) for t, d in ((0, -36), (0.04, -25), (0.08, -18), (0.12, -13), (0.16, -9), (0.2, -6), (0.24, -4),
                                            (0.28, -2), (0.32, -1), (0.44, 0), (0.55, 4), (1.5, 0))],   # from the first notes (0.12 s)
        # and its sound (user: "no es solo cuestion del volumen tambien del efecto"): code 78h is bright white noise rising (spectral
        # centroid 11 kHz, flatness 0.8, no pitch), so the push has a noise of its own: "empuje", the looped noise (ruido), 0.12-0.6 s
        # on that curve, cut at its top as the arcade's
        # then (user: "seria algo como en el video en el segundo 15": a Dolby trailer, 15.0-16.3 s a riser getting louder and
        # brighter, above 4 kHz 55 -> 79 dB, centroid 75 -> 440 Hz): the noise 0.12-0.9 s, louder all the way and played two octaves
        # down at first, gliding up to its own rate (ruido_t: the noise with key scaling, sweep -24): it opens as it grows
        envelope={"empuje": [(0.12, -30), (0.3, -18), (0.5, -10), (0.7, -4), (0.9, 0)]},
        sweep={"empuje": -24},
        final_decay=12,                         # every track of the final chord 12 dB a second (user: "que descienda el volumen
                                                # algo mas rapido"; guitars / pianos had 6, strings and bass none)
        # the closing chord on tracks of its own (cierre_*, their instruments as the tracks they double), 9.25-9.9 s, fading 24 dB a
        # second (user: "lo empezaria un poco mas tarde y le iria haciendo un fadding"); its key offs inside the song (at 10.0 s they
        # were dropped and a note on channel 17-20, which ms_stop leaves to the effects, sounded on: the check below)
        extra={"empuje": [(0.24, 1.56, 60, 127)]} or {t: [(18.5, 1.3, n, 110) for n in ns] for t, ns in (("cierre_mel", (69, 76)), ("cierre_oct", (81,)),
                                                                 ("cierre_cuerdas", (45, 52)), ("cierre_bajo", (45,)))},
        closing_decay=0)                        # the closing chord left out (user: "el cierre lo quitaria"; it had 45 dB a second:
                                                # 24 was not heard as a fade); the push's noise instead (below)
    LOGO_VERSIONS["scc_mejorada"]["maps"].update(cierre_mel="ram:scc00", cierre_oct="ram:scc22", cierre_cuerdas="ram:scc23",
                                                 cierre_bajo="ram:scc03")
    LOGO_VERSIONS["scc_mejorada"]["gain"].update(cierre_mel=2, cierre_oct=-1, cierre_cuerdas=-10, cierre_bajo=-6, empuje=-12)
    LOGO_VERSIONS["scc_mejorada"]["maps"]["empuje"] = "ram:ruido_t"
    LOGO_VERSIONS["scc_mejorada"]["gain"]["empuje"] = -9
    # the instruments open while the start rises (user: "ese efecto whoosh se le podria poner al propio instrumento solo mientras
    # esta subiendo para despues tener su timbre normal"): no filter in the OPL4, so a crossfade: the notes starting before 0.9 s
    # of guitar1 / strings / bass also on their dark waveform (copies <track>_osc, scc00 / 23 / 03 _osc), from full to -40 dB at
    # 0.9 s (-3 dB at 0.5 s), while the normal ones come from -24 dB to their level (-3 dB at 0.5 s); both on the push curve
    v = LOGO_VERSIONS["scc_mejorada"]
    push = v["fade_in"]
    def curve_sum(a, b):
        ts = sorted({t for t, _ in a} | {t for t, _ in b})
        at = lambda c, t: c[0][1] if t <= c[0][0] else c[-1][1] if t >= c[-1][0] else next(
            d0 + (d1 - d0) * (t - t0) / (t1 - t0) for (t0, d0), (t1, d1) in zip(c, c[1:]) if t0 <= t <= t1)
        return [(t, at(a, t) + at(b, t)) for t in ts]
    for tr, wav in (("guitar1", "scc00"), ("strings", "scc23"), ("bass", "scc03")):
        v["copies"][tr + "_osc"] = (tr, 0, 0.9)
        v["maps"][tr + "_osc"] = "ram:%s_osc" % wav
        v["gain"][tr + "_osc"] = v["gain"][tr]
        v["envelope"][tr + "_osc"] = curve_sum(push, [(0.12, 0), (0.5, -3), (0.9, -40)])   # -3 dB each at 0.5 s: the sum keeps the
        v["envelope"][tr] = curve_sum(push, [(0.12, -24), (0.5, -3), (0.9, 0)])           # level (straight lines: 8 dB down mid-way)
    v["transpose"]["strings_osc"] = v["transpose"]["strings"]
    # "scc_mejorada_cuerdas" (user: try the strings, an octave up, louder and fading slower in the final chord; else back to
    # "scc_mejorada"): strings +6 dB (-4), in the final chord 6 dB a second (the others 12)
    import copy
    LOGO_VERSIONS["scc_mejorada_cuerdas"] = v2 = copy.deepcopy(v)
    v2["gain"].update(strings=-4, strings_osc=-4)
    v2["final_decay_tracks"] = {"strings": 6}
    # "scc_mejorada_bajo_rom" (user: "podriamos probar el bajo de la rom del opl4 ... un bajo seco"): "scc_mejorada_cuerdas" with the
    # bass on the ROM's GM 33 Fingered Bass (it decays by itself, D1R 6 / D2R 4, and its release is short, RR 9; Picked Bass holds
    # at DL 11), no dark copy (bass_osc: for the RAM waveforms only), the bass on the push curve alone
    LOGO_VERSIONS["scc_mejorada_bajo_rom"] = v3 = copy.deepcopy(v2)
    v3["maps"]["bass"] = "33"
    for d in ("copies", "maps", "gain", "envelope"):
        v3[d].pop("bass_osc", None)
    v3["envelope"]["bass"] = list(push)
    v3["gain"]["bass"] = 6                     # the ROM sample is quieter than the full-scale RAM waveforms
    # its final E3 (5.12-8.25 s) on the RAM bass waveform scc03 (user: "el bajo al final no tiene tremolo": the ROM sample dies away
    # in its recording, the tremolo was hardly heard; `hold`, no envelope decay, did not help): the copy "bass_final" from 4.8 s,
    # the ROM bass before it
    v3["copies"]["bass_final"] = ("bass", 0)
    v3["window"] = {"bass": (0, 4.8), "bass_final": (4.8, 99)}
    v3["maps"]["bass_final"] = "ram:scc03"
    v3["gain"]["bass_final"] = -6
    LOGO_VERSION = "scc_mejorada_bajo_rom"      # "scc_mejorada_cuerdas": the strings louder, kept; "scc": the kept one (the user: "queda mejor la version scc" than "distorsion");
                                                # "scc_mejorada": the improved one, kept
    LOGO_DROP = ["snare"]
    if LOGO_MID == "logo.mid":
        logo = midi2wave.convert(V / "assets/music/logo.mid", maps={"guitarra": "30"}, shift={"strings": -4, "guitarra": -4})
    else:
        ver = LOGO_VERSIONS[LOGO_VERSION]
        logo_trace = []
        mel = MELODY + tuple(ver.get("copies", ()))
        logo = midi2wave.convert(V / "assets/music" / LOGO_MID, ram=ram, drum_ring=0, maps=ver["maps"], gain=ver["gain"], boost=-9,
                                 drop=LOGO_DROP + ver.get("drop", []),
                                 tremolo={t: (4.8, 5, 5, ver.get("vibrato", 0)) for t in mel + ("bass", "bass_final") + tuple(ver.get("extra", {}))},
                                 ramp={t: (2.6, 4.4, -9) for t in MELODY[1:]},
                                 decay=dict({t: 6 for t in mel}, **{t: ver.get("closing_decay", 0) for t in ver.get("extra", {})},
                                            **({t: (ver.get("final_decay_tracks", {}).get(t, ver["final_decay"]), 4.8)
                                                for t in mel + ("strings", "bass", "bass_final")} if "final_decay" in ver else {})),
                                 sweep=ver.get("sweep"),
                                 copies=ver.get("copies"), detune=ver.get("detune"), pan=ver.get("pan"), arp=ver.get("arp"),
                                 extra=ver.get("extra"), transpose=ver.get("transpose"), fade_in=ver.get("fade_in"),
                                 envelope=ver.get("envelope"), hold=ver.get("hold"), window=ver.get("window"), trace=logo_trace)
        print("music: logo version %r" % LOGO_VERSION)
    logo = (logo[0], int(LOGO_LEN * 44100))
    if LOGO_MID != "logo.mid":                  # the same arrangement as a Furnace module, to study / edit it (tools/midi2fur.py)
        import midi2fur
        import opm2opl4_fur
        src = {name: (pcm[:loop] if fixed and loop else pcm, rate, None if fixed and loop else (0, len(pcm)))   # one shots:
               for name, pcm, loop, rate, fixed in ram_ins}
        src["ruido_t"] = (src["ruido"][0], ram["ruido_t"]["rate"], (0, len(src["ruido"][0])))
        rows, instruments, names, smps, hz, length = midi2fur.from_trace(logo_trace, src, logo[1])
        if LOGO_VOICE is not None:              # the logo's voices (voices[0]) on a channel of their own: a sample at its own rate (C-4 =
            with wave.open(str(AUDIO / "voices" / voices[0][0])) as w:   # its rate), keyed at the stream frame LOGO_VOICE as the game
                vpcm = bytes((b - 128) & 0xFF for b in w.readframes(w.getnframes()))
                vrate = w.getframerate()
            smps.append(dict(name="logo_voces", data=vpcm, rate=vrate, loop=None))
            instruments.append(dict(name="voces (logo)", sample=len(smps) - 1, mp=(15, 0, 0, 0, 15, 0, 0, 0, 0)))
            names.append(("voces 1", "voc1"))
            rows[(int(round(LOGO_VOICE / 50 * hz)), opm2opl4_fur.PCM0 + len(names) - 1)] = dict(
                note=60 + 48, ins=len(instruments) - 1, vol=127, fx=[(0xE5, 0x80), (0x08, 0xFF)])
        opm2opl4_fur.write_fur(ROMB / "logo.fur", "DiHalt logo: dihalt34 %s (OPL4)" % LOGO_VERSION, rows, instruments, hz, 64,
                               end=length, names=names, author="DiHalt", samples=smps, fx_cols=3, highlight=(16, 64),
                               comment="build_b1.py LOGO_VERSION %r: the logo song as the game plays it (tools/midi2wave.py trace, "
                                       "tools/midi2fur.py from_trace); RAM waveforms of instruments created for the SCC, ADR-049." % LOGO_VERSION)
        print("music: logo as a Furnace module: %s (%d channels, %d instruments, %d samples)" % (
            ROMB / "logo.fur", len(names), len(instruments), len(smps)))
        import mwm_export                       # and as a MoonBlaster for Moonsound song (DIHALT34.MWM + .MWK)
        mwm, mwk, rep = mwm_export.export(logo_trace, src, logo[1], "DIHALT34", "DiHalt logo - dihalt34 %s (OPL4)" % LOGO_VERSION)
        (ROMB / "DIHALT34.MWM").write_bytes(mwm)
        (ROMB / "DIHALT34.MWK").write_bytes(mwk)
        print("music: logo as an MBWave song: %s (%d bytes) + .MWK (%d bytes): %s" % (ROMB / "DIHALT34.MWM", len(mwm), len(mwk), rep[0]))
        import vgm_export                       # and as a VGM (YMF278B): the game's writes and the RAM it needs
        ram_img = bytearray(voice_ram - 0x200000 + len(parts[0]))
        ram_img[:len(headers)] = headers        # the tone headers (200000h..) and part 0 of the voices: the logo's RAM instruments and
        ram_img[voice_ram - 0x200000:] = parts[0]   # its voices, as the first ms_open copies them
        voice_w = [(fr * 882, 2, r, v) for fr, ws in sorted(extra["logo"].items()) for r, v in ws]   # the voices' key-ons (50 Hz frames)
        vgm = vgm_export.export(logo[0] + voice_w, logo[1], ram_img, "DiHalt logo - dihalt34 %s" % LOGO_VERSION)
        (ROMB / "dihalt34.vgm").write_bytes(vgm)
        print("music: logo as a VGM: %s (%d bytes, %.1f s, RAM image %d bytes)" % (ROMB / "dihalt34.vgm", len(vgm), logo[1] / 44100, len(ram_img)))
        EXPORT = BUILDV / "export/logo"           # the exports kept in the project (ADR-049): Furnace, MBWave, VGM
        EXPORT.mkdir(parents=True, exist_ok=True)
        for f in ("logo.fur", "DIHALT34.MWM", "DIHALT34.MWK", "dihalt34.vgm"):
            shutil.copyfile(ROMB / f, EXPORT / ("dihalt34.fur" if f == "logo.fur" else f))
    keyed = {}
    for t, port, r, v in sorted(w for w in logo[0] if w[0] < logo[1]):
        if port == 2 and 0x68 <= r < 0x80:
            keyed[r - 0x68] = bool(v & 0x80)
    assert not any(keyed.values()), "the logo song leaves wave channel(s) %s keyed on at its end" % [c for c, k in keyed.items() if k]
    hi = {}                                     # the tones the logo song loads: wave number = bit 0 of 20h (bit 8) + 08h
    tones = set()
    for t, port, r, v in logo[0]:
        if port == 2 and 0x20 <= r < 0x38:
            hi[r - 0x20] = v & 1
        elif port == 2 and 0x08 <= r < 0x20:
            tones.add(hi.get(r - 0x08, 0) << 8 | v)
    print("music: logo tones: RAM %s, ROM %s" % (sorted(x for x in tones if x >= 384), sorted(x for x in tones if x < 384) or "none"))
    logo_frames = int(re.search(r"^LOGO_MS_FRAMES\s+equ\s+(\d+)\*60", (SRCV / "src/rom/opening.asm").read_text(), re.M).group(1)) * 50
    assert logo[1] <= logo_frames * 44100 // 50, "the logo song is longer than the logo (opening.asm LOGO_MS_FRAMES)"
    songs = [("logo", logo[:2], "SONG_LOGO", extra["logo"], None),
             ("level", opm2opl3.convert(AUDIO / "music/level1_arcade.vgz", also=[AUDIO / "music/start_coin_arcade.vgz"])[:2], "SONG_LEVEL", extra["level"], int(round(1.37 * 50))),
             ("level2", opm2opl3.convert(AUDIO / "music/level_arcade.vgz")[:2], "SONG_LEVEL2", {}, int(round(11.22 * 50))),
             ("menu", opm2opl3.convert(AUDIO / "music/intro_arcade.vgz", two_op=[5, 6], atten=4.5)[:2], "SONG_MENU", extra["menu"], None),
             ("shop", opm2opl3.convert(AUDIO / "music/shop_arcade.vgz")[:2], "SONG_SHOP", {}, 0),
             ("boss", opm2opl3.convert(AUDIO / "music/boss_arcade.vgz")[:2], "SONG_BOSS", extra["boss"], int(round(1.12 * 50)))]
    # the songs one after another from MUSIC_DATA of MUSIC_BANK (a song goes on at MUSIC_DATA of the next bank: FDh); the player's
    # song table MS_SONGS (music.inc) gets (bank, address) of each song's start, by its SONG_* number. A song that would run past the
    # last music bank starts instead in the extra music banks after the effects (MUSIC2: FX_BANK + the effect banks, ADR-049; the
    # 2 MiB ROM has room there; every music bank holds the player, so any bank number works)
    music2 = fx_bank + fx_banks
    per_bank = 0x8000 - music_data
    ms_songs = int(re.search(r"^MS_SONGS\s+equ\s+0x([0-9a-fA-F]+)", minc, re.M).group(1), 16) - 0x4000
    songs_max = int(re.search(r"^SONGS_MAX\s+equ\s+(\d+)", minc, re.M).group(1))
    table = bytearray(3 * songs_max)
    bank_data, b = {music_bank: bytearray()}, music_bank
    for name, (writes, total), sym, ex, loop in songs:
        num = int(re.search(r"^%s\s+equ\s+(\d+)" % sym, minc, re.M).group(1))
        assert num < songs_max
        if per_bank - len(bank_data[b]) < 256:              # too little room left: the next bank
            b += 1
            bank_data[b] = bytearray()
        stream, n_in, n_out, frames = opl4_stream.build(writes, total, per_bank, ex, loop, first=per_bank - len(bank_data[b]))
        if b < music_bank + music_banks <= b + len(stream) - 1:   # does not fit the music banks: on in the extra ones
            b = max(music2, max(bank_data) + 1)
            bank_data[b] = bytearray()
            stream, n_in, n_out, frames = opl4_stream.build(writes, total, per_bank, ex, loop, first=per_bank)
        start = (b, music_data + len(bank_data[b]))
        table[3 * num:3 * num + 3] = struct.pack("<BH", *start)
        used = []
        for k, chunk in enumerate(stream):
            if k:
                b += 1
                bank_data[b] = bytearray()
            assert b < music_bank + music_banks or music2 <= b < 128, "the songs do not fit the music banks (at %s)" % name
            bank_data[b] += chunk
            used.append(b)
        print("music: %s %d frames (%.1f s)%s, %d OPL4 writes, %d bytes from bank %d %04Xh, bank(s) %s" % (
            name, frames, frames / 50, "" if loop is None else ", loop at %.2f s" % (loop / 50), n_out,
            sum(len(c) for c in stream), start[0], start[1], ", ".join(map(str, used))))
    assert player[ms_songs:ms_songs + len(table)] == bytes(len(table)), "MS_SONGS is not the empty song table of the player"
    player = player[:ms_songs] + bytes(table) + player[ms_songs + len(table):]
    music_imgs = {}
    for b, d in bank_data.items():
        img_b = player + b"\xff" * (music_data - 0x4000 - len(player)) + bytes(d)
        (ROMB / ("music_%d.bin" % b)).write_bytes(img_b + b"\xff" * (0x4000 - len(img_b)))
        music_imgs[b] = ROMB / ("music_%d.bin" % b)
    extra_music = sorted(k for k in bank_data if k >= music2)
    print("music: banks %d-%d%s, %d bytes free in the last one" % (
        music_bank, max(k for k in bank_data if k < music2), ", %d-%d" % (extra_music[0], extra_music[-1]) if extra_music else "",
        per_bank - len(bank_data[b])))

    chunks = ["; generated by V9990-B1/tools/build_b1.py: dest, length, bank, source address in the 4000h window"]
    data = ["; generated by V9990-B1/tools/build_b1.py: ROM data pieces", "        ds 0x4000+0x%04x-$,0xff" % DATA_START]
    cur, bank = DATA_START, 0
    for f, off, dest, k, p in placed:
        if p // 0x4000 != bank:
            data += ["        ds 0x8000-$,0xff", "        org 0x4000"]
            bank, cur = p // 0x4000, (p // 0x4000) * 0x4000
        if p > cur:
            data.append("        ds %d,0xff" % (p - cur))
        data.append('        incbin "%s",0x%x,0x%x    ; ROM %05x bank %d -> RAM %04x' % (f.name, off, k, p, bank, dest))
        cur = p + k
        chunks += ["        dw 0x%04x,0x%04x" % (dest, k), "        db %d" % bank, "        dw 0x%04x" % (0x4000 + p % 0x4000)]
    store_tab = int(re.search(r"^hk_store_tab: equ 0*([0-9A-Fa-f]+)h", (ROMB / "hk_runtime.sym").read_text(), re.M).group(1), 16)
    vchunks = ["; generated by V9990-B1/tools/build_b1.py: vram address lo.w, bits 18-16.b, length.w, bank.b, source address in the 4000h window",
               "HK_STORE_TAB    equ 0x%04x          ; the scene store table (hk_segs.asm), stage B's second VRAM table" % store_tab]
    for f, off, va, k, p in vplaced:
        if p // 0x4000 != bank:
            data += ["        ds 0x8000-$,0xff", "        org 0x4000"]
            bank, cur = p // 0x4000, (p // 0x4000) * 0x4000
        if p > cur:
            data.append("        ds %d,0xff" % (p - cur))
        data.append('        incbin "../assets4/%s",0x%x,0x%x    ; ROM %05x bank %d -> VRAM %05x' % (f.name, off, k, p, bank, va))
        cur = p + k
        vchunks += ["        dw 0x%04x" % (va & 0xFFFF), "        db %d" % (va >> 16), "        dw 0x%04x" % k, "        db %d" % bank, "        dw 0x%04x" % (0x4000 + p % 0x4000)]
    for b in range(open_banks):                 # opening bitmap: one full bank per incbin
        data += ["        ds 0x8000-$,0xff", "        org 0x4000"]
        n = min(0x4000, opn - b * 0x4000)
        data.append('        incbin "../opening-b3.bin",0x%x,0x%x    ; bank %d: opening bitmap' % (b * 0x4000, n, open_bank + b))
    for b in range(logo_banks):                 # DiHalt logo: one full bank per incbin
        data += ["        ds 0x8000-$,0xff", "        org 0x4000"]
        n = min(0x4000, lgn - b * 0x4000)
        data.append('        incbin "../dihalt-logo.bin",0x%x,0x%x    ; bank %d: DiHalt logo' % (b * 0x4000, n, logo_bank + b))
    data.append("        ds 0x8000-$,0xff")
    for k in range(0, len(voice), 0x4000):
        (ROMB / ("voice_%d.bin" % (k // 0x4000))).write_bytes(voice[k:k + 0x4000])
    print("voices: %d (%.2f s), %d bytes from bank %d, %d bytes of Moonsound RAM free" % (
        len(voices), sum(w[1] for w in voice_len) / 22050, len(voice), voice_bank, 0x220000 - voice_ram - len(parts[0]) - len(parts[1])))
    for b in range(logo_bank + logo_banks, scene_bank):         # empty banks up to the scenery, the music and voice banks among them
        kv = b - voice_bank
        if 0 <= kv * 0x4000 < len(voice):
            data += ["        org 0x4000", '        incbin "voice_%d.bin"    ; bank %d: voice samples' % (kv, b), "        ds 0x8000-$,0xff"]
        elif b in music_imgs:
            data += ["        org 0x4000", '        incbin "%s"    ; bank %d: Moonsound player + music stream' % (music_imgs[b].name, b)]
        else:
            data += ["        org 0x4000", "        ds 0x4000,0xff"]
    store = (A4 / "scene_store.bin").stat().st_size        # banks SCENE_BANK..+3: scene store (stage B, hk_store_tab), +4: copy lists
    for b in range(4):
        data += ["        org 0x4000"]
        if b * 0x4000 < store:
            data.append('        incbin "../assets4/scene_store.bin",0x%x,0x%x    ; bank %d: scene store' % (
                b * 0x4000, min(0x4000, store - b * 0x4000), scene_bank + b))
        data.append("        ds 0x8000-$,0xff")
    data += ["        org 0x4000", '        incbin "../assets4/scene_list.bin"    ; bank %d: scene copy lists (hk_scene_copy)' % (scene_bank + 4),
             "        ds 0x8000-$,0xff"]
    data += ["        org 0x4000", '        incbin "../assets4/scene_pal.bin"    ; bank %d: scene palettes and panels' % (scene_bank + 5),
             "        ds 0x8000-$,0xff"]
    for k in range(fx_banks):                   # the arcade effects (ADR-044): banks FX_BANK.., 256-byte blocks from 8000h (page 2 window)
        (ROMB / ("fx_%d.bin" % k)).write_bytes(fx[k * 0x4000:(k + 1) * 0x4000])
        data += ["        org 0x4000", '        incbin "fx_%d.bin"    ; bank %d: effect samples' % (k, fx_bank + k), "        ds 0x8000-$,0xff"]
    rom_size += fx_banks * 0x4000
    for k in extra_music:                       # the extra music banks (ADR-049), right after the effects
        assert k == fx_bank + fx_banks + extra_music.index(k)
        data += ["        org 0x4000", '        incbin "%s"    ; bank %d: Moonsound player + music stream' % (music_imgs[k].name, k)]
        rom_size += 0x4000
    print("effects: %d (%.2f s), %d blocks in banks %d-%d, at %06Xh of the Moonsound RAM" % (
        len(fx_names), len(fx) / 22050, fx_blocks, fx_bank, fx_bank + fx_banks - 1, fx_ram + 0x100))
    (ROMB / "vram_chunks.inc").write_text("\n".join(vchunks) + "\n")
    (ROMB / "chunks.inc").write_text("\n".join(chunks) + "\n")
    (ROMB / "rom_data.inc").write_text("\n".join(data) + "\n")

    sjasm(SRCV / "src/rom/stage_b_b1.asm", ROMB / "stage_b.bin")
    rom = pathlib.Path(args.out)
    sjasm(SRCV / "src/rom/xybots_b1_rom.asm", rom)
    r = rom.read_bytes()
    assert len(r) == rom_size, "ROM size %d, expected %d" % (len(r), rom_size)
    p2 = 0x10000
    while p2 < len(r):
        p2 *= 2
    r += b"\xff" * (p2 - len(r))                 # MegaROM size = power of two
    rom.write_bytes(r)
    print("ROM %s: %d bytes (%d banks), sha256 %s" % (rom, len(r), len(r) // 0x4000, hashlib.sha256(r).hexdigest()))
    print("hook runtime: %d bytes (C400h-%04Xh, limit %04Xh); stage B %d bytes; %d pieces" % (
        len(hk), HK_BASE + len(hk) - 1, HK_LIMIT - 1, (ROMB / "stage_b.bin").stat().st_size, len(placed)))
    print("patches: %d (VDP shims: out98 %d, out99 %d, in98 %d)" % (len(img.log), len(sites["out98"]), len(sites["out99"]), len(sites["in98"])))
    (BUILDV / "patch_manifest.json").write_text(json.dumps(
        [{"addr": "%04X" % a, "expected": e.hex(), "new": n.hex(), "why": w} for a, e, n, w in img.log], indent=1) + "\n")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""OPL4 (YMF278B) register writes -> the Moonsound music stream of the ROM (feature/music, ADR-027).

  opl4_stream.py <song.vgm> <out.bin> [--max N]     N = bytes available per ROM bank for the stream (default 16384 - player)

Sources: the wave part of a VGM exported by Furnace (`furnace -vgmout`, VGM port 2: MSX ports 7Eh / 7Fh; the player sets the chip up
itself: FM register 105h NEW2, wave register 02h, mix F8h / F9h, so those writes and the FM writes of that VGM are dropped), or the FM
writes made by tools/opm2opl3.py (arrays 0 / 1: ports C4h/C5h and C6h/C7h). The writes are grouped into frames of 50 Hz (the V9990
vertical interrupt of the port), in order. A write that repeats the value a register already holds is dropped, except the wave
registers that trigger something when written: wave number (08h-1Fh: loads the tone header) and key on / damp / reset (68h-7Fh).

Stream format (read by src/rom/opl4_player.asm), per frame: FM entries, then one wave entry that ends the frame:
  00h-3Fh  n: n wave writes (register, value), then the frame ends
  40h-5Fh  n - 40h FM writes of array 0 (register, value); the frame goes on
  60h-7Fh  n - 60h FM writes of array 1; the frame goes on
  80h-FBh  wait: this frame and the next (b - 80h) frames have no writes
  FCh      loop point (same frame): from the end the song jumps back here without a pause; the FM registers are written again here
           with their values at that point
  FDh      the stream continues at the start of the data in the next ROM bank (same frame)
  FEh      end of the song (back to the loop point; without one the player pauses and starts again)
More than 63 wave writes in a frame go on in the next frames.
"""
import argparse
import pathlib
import struct

FRAME = 44100 / 50
TRIGGER = set(range(0x08, 0x20)) | set(range(0x68, 0x80))


def wave_writes(path):
    """[(sample time, 2, register, value)] of the wave part of a VGM (port 2), and its length in samples."""
    d = pathlib.Path(path).read_bytes()
    assert d[:4] == b"Vgm ", "not a VGM"
    start = 0x34 + struct.unpack_from("<I", d, 0x34)[0]
    t, i, out = 0, start, []
    while i < len(d):
        c = d[i]
        if c == 0xD0:
            if d[i + 1] == 2:
                out.append((t, 2, d[i + 2], d[i + 3]))
            i += 4
        elif c == 0x61:
            t += struct.unpack_from("<H", d, i + 1)[0]; i += 3
        elif c == 0x62:
            t += 735; i += 1
        elif c == 0x63:
            t += 882; i += 1
        elif 0x70 <= c <= 0x7F:
            t += (c & 15) + 1; i += 1
        elif c == 0x67:
            i += 7 + struct.unpack_from("<I", d, i + 3)[0]
        elif c == 0x66:
            break
        else:
            raise ValueError("VGM command %02X at %X" % (c, i))
    return out, t


def build(writes, total, per_bank, extra=None, loop=None, first=None):
    """writes: [(sample time 44.1 kHz, port 0/1 FM array / 2 wave, register, value)], total: song length in samples.
    extra: {frame: [(register, value), ...]} wave writes after the song's writes of that frame (the voices).
    loop: the frame the song loops back to from its end (None: no loop, the player pauses and restarts).
    first: room in the first bank (the song starts after another one there; default per_bank)."""
    state, frames, reset, snap = {}, {}, loop is not None, None
    fm_state = {}
    for t, port, r, v in writes:
        f = int(round(t / FRAME))
        if reset and f >= loop:
            snap = dict(fm_state)                    # the FM registers at the loop point: written again there (from the end the song
            state, reset = {}, False                 # comes back with other values); every register is written once more after it
        if port == 2 and r in (0x02, 0xF8, 0xF9):
            continue                                 # set up by the player
        if not (port == 2 and r in TRIGGER) and state.get((port, r)) == v:
            continue
        state[(port, r)] = v
        if port < 2:
            fm_state[(port, r)] = v
        frames.setdefault(f, []).append((port, r, v))
    if reset:
        snap = dict(fm_state)
    if snap:
        frames[loop] = [(p, r, v) for (p, r), v in sorted(snap.items())] + frames.get(loop, [])
    for f, w in (extra or {}).items():
        frames.setdefault(f, []).extend((2, r, v) for r, v in w)
    last = int(round(total / FRAME))
    entries, f, carry = [], 0, []
    while f <= last or carry:
        if f == loop:
            entries.append(b"\xFC")
        ws = frames.get(f, [])
        if ws or carry:
            for port, code in ((0, 0x40), (1, 0x60)):
                fm = [(r, v) for p, r, v in ws if p == port]
                for k in range(0, len(fm), 31):
                    part = fm[k:k + 31]
                    entries.append(bytes([code + len(part)]) + bytes(x for rv in part for x in rv))
            w = carry + [(r, v) for p, r, v in ws if p == 2]
            entries.append(bytes([min(len(w), 63)]) + bytes(x for rv in w[:63] for x in rv))
            carry = w[63:]
            f += 1
            continue
        run = 1
        while f + run <= last and not frames.get(f + run) and run < 0x7C and f + run != loop:
            run += 1
        entries.append(bytes([0x80 + run - 1]))
        f += run
    entries.append(b"\xFE")
    banks, cur = [], bytearray()
    room = per_bank if first is None else first
    for e in entries:
        if len(cur) + len(e) + 1 > room:              # keep 1 byte for FDh
            cur.append(0xFD)
            banks.append(bytes(cur))
            cur, room = bytearray(), per_bank
        cur += e
    banks.append(bytes(cur))
    return banks, len(writes), sum(len(fr) for fr in frames.values()), last


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("vgm")
    ap.add_argument("out")
    ap.add_argument("--max", type=int, default=16384 - 0x200)
    a = ap.parse_args()
    w, total = wave_writes(a.vgm)
    banks, n_in, n_out, frames = build(w, total, a.max)
    out = pathlib.Path(a.out)
    out.write_bytes(b"".join(banks))
    (out.with_suffix(".banks")).write_text(" ".join(str(len(b)) for b in banks) + "\n")
    print("%s: %d wave writes -> %d kept, %d frames (%.1f s), %d bytes in %d bank(s)" % (
        out, n_in, n_out, frames, frames / 50, sum(len(b) for b in banks), len(banks)))


if __name__ == "__main__":
    main()

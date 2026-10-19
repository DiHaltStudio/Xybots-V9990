#!/usr/bin/env python3
"""Analysis of a YM2151 (OPM) VGM/VGZ, the arcade Xybots music (feature/music): notes per channel, FM instruments, timing.

  opm_analyze.py <song.vgz> [--out DIR]     report on stdout + DIR/report.json; DIR/patch_<n>.wav: every instrument rendered
                                            (one note, C4 and C2) with vgm2wav, to listen and to choose an OPL4 ROM (GM) instrument

YM2151 registers used: 08h key on (bits 0-2 channel, 3-6 operator mask), 0Fh noise, 18h/19h LFO, 20h-27h RL/FB/CON, 28h-2Fh KC
(octave, note code), 30h-37h KF, 38h-3Fh PMS/AMS, 40h-FFh operator parameters (DT1/MUL, TL, KS/AR, AMS-EN/D1R, DT2/D2R, D1L/RR;
operator slot s of channel c at 40h + 8*s + c, slots M1 C1 M2 C2 = 0 2 1 3 in register order M1, M2, C1, C2).
An instrument = channel registers 20h (FB/CON, without RL), 38h and the operator registers without the TLs (the arcade driver scales
every TL with the note volume); the pitch reported is the sounding one (key code times the MUL of the last carrier). Carriers per algorithm: CON 0-3 C2; 4 C1 C2; 5-6 M2 C1 C2; 7 all four.
"""
import argparse
import collections
import gzip
import json
import pathlib
import struct
import subprocess
import sys

NOTE_CODE = {0: 1, 1: 2, 2: 3, 4: 4, 5: 5, 6: 6, 8: 7, 9: 8, 10: 9, 12: 10, 13: 11, 14: 12}   # KC note code -> semitone above C (C# = 1)
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
CARRIERS = {0: [3], 1: [3], 2: [3], 3: [3], 4: [1, 3], 5: [2, 1, 3], 6: [2, 1, 3], 7: [0, 1, 2, 3]}   # slot index in register order
# register order of the 4 operators: 40h+c (M1), 48h+c (M2), 50h+c (C1), 58h+c (C2) -> index 0..3


def load(path):
    d = pathlib.Path(path).read_bytes()
    if d[:2] == b"\x1f\x8b":
        d = gzip.decompress(d)
    assert d[:4] == b"Vgm ", "not a VGM"
    ver = struct.unpack_from("<I", d, 8)[0]
    start = 0x40 if ver < 0x150 else 0x34 + struct.unpack_from("<I", d, 0x34)[0]
    clock = struct.unpack_from("<I", d, 0x30)[0]
    return d, start, clock


def events(d, start):
    """[(sample time, reg, value)] of the YM2151 writes."""
    t, i, out = 0, start, []
    while i < len(d):
        c = d[i]
        if c == 0x54:
            out.append((t, d[i + 1], d[i + 2])); i += 3
        elif c == 0x61:
            t += struct.unpack_from("<H", d, i + 1)[0]; i += 3
        elif c == 0x62:
            t += 735; i += 1
        elif c == 0x63:
            t += 882; i += 1
        elif 0x70 <= c <= 0x7F:
            t += (c & 15) + 1; i += 1
        elif c == 0x66:
            break
        elif c == 0x67:
            n = struct.unpack_from("<I", d, i + 3)[0]; i += 7 + n
        elif 0x30 <= c <= 0x3F or c in (0x4F, 0x50):
            i += 2
        elif 0x40 <= c <= 0x5F or 0xA0 <= c <= 0xBF:
            i += 3
        elif 0xC0 <= c <= 0xDF:
            i += 4
        elif 0xE0 <= c <= 0xFF:
            i += 5
        else:
            raise ValueError("VGM command %02X at %X" % (c, i))
    return out, t


def kc_to_midi(kc, kf):
    """YM2151 key code (octave 0-7, note code) + fraction -> MIDI note (float). KC octave o note C# = MIDI 12*(o+1)+1 + 12 ... tuned so
    that KC 4Ah (octave 4, A) = A4 = MIDI 69 at the 3.58 MHz clock."""
    octave, code = (kc >> 4) & 7, kc & 15
    semi = NOTE_CODE.get(code, None)
    if semi is None:
        return None
    return 12 * (octave + 1) + semi + 12 * 0 + (kf >> 2) / 64.0 + (69 - (12 * 5 + 9))


def analyse(path):
    d, start, clock = load(path)
    ev, total = events(d, start)
    regs = [0] * 256
    notes = []                          # dict per note
    active = {}                         # channel -> note being played
    for t, r, v in ev:
        regs[r] = v
        if r == 0x08:
            ch, mask = v & 7, (v >> 3) & 15
            if mask and ch not in active:
                con = regs[0x20 + ch] & 7
                car = CARRIERS[con]
                ops = [[regs[base + 8 * s + ch] for base in (0x40, 0x60, 0x80, 0xA0, 0xC0, 0xE0)] for s in range(4)]
                # the arcade driver scales every TL with the note volume: the timbre is the patch without any TL; the modulator TLs
                # of the first note (relative to the loudest carrier) are kept apart for rendering
                patch = (regs[0x20 + ch] & 0x3F, regs[0x38 + ch]) + tuple(tuple(o[k] for k in range(6) if k != 1) for o in ops)
                mod_tl = tuple(ops[s][1] & 0x7F for s in range(4))
                tl = min(ops[s][1] & 0x7F for s in car)
                midi = kc_to_midi(regs[0x28 + ch], regs[0x30 + ch])
                mul = (ops[car[-1]][0] & 15) or 0.5
                if midi is not None:
                    import math
                    midi += 12 * math.log2(mul)               # sounding pitch: KC times the carrier's MUL
                active[ch] = dict(ch=ch, t=t, patch=patch, midi=midi, tl=tl, mod_tl=mod_tl, mask=mask, noise=bool(regs[0x0F] & 0x80) and ch == 7,
                                  pan=regs[0x20 + ch] >> 6)
            elif not mask and ch in active:
                n = active.pop(ch)
                n["dur"] = t - n["t"]
                notes.append(n)
    for ch, n in active.items():
        n["dur"] = total - n["t"]
        notes.append(n)
    notes.sort(key=lambda n: n["t"])
    return dict(clock=clock, total=total, notes=notes, regs_lfo=(regs[0x18], regs[0x19], regs[0x1B]))


def name(m):
    if m is None:
        return "?"
    k = int(round(m))
    return "%s%d" % (NAMES[k % 12], k // 12 - 1)


def render_patch(patch, clock, path, mod_tl, midi_notes=(60, 36)):
    """A VGM with the patch on channel 0, one note per entry of midi_notes (1 s on, 0.4 s off), rendered by vgm2wav."""
    fbcon, pmsams = patch[0], patch[1]
    con = fbcon & 7
    car = CARRIERS[con]
    cmd = bytearray()
    w = lambda r, v: cmd.extend((0x54, r, v))   # noqa: E731
    w(0x20, 0xC0 | fbcon)
    w(0x38, pmsams)
    for s in range(4):
        vals = list(patch[2 + s])
        vals.insert(1, 0x00 if s in car else mod_tl[s])   # carriers at full volume, modulators as in the song
        for k, base in enumerate((0x40, 0x60, 0x80, 0xA0, 0xC0, 0xE0)):
            w(base + 8 * s, vals[k])
    for m in midi_notes:
        o = m // 12 - 1 - 0
        semi = m % 12
        # inverse of kc_to_midi: semitone above C -> note code; C is note code 14 of the octave below
        code = {v: k for k, v in NOTE_CODE.items()}
        if semi == 0:
            kc = ((o - 1) & 7) << 4 | 14
        else:
            kc = (o & 7) << 4 | code[semi]
        w(0x28, kc)
        w(0x30, 0)
        w(0x08, 0x78)
        cmd.extend((0x61, 0x44, 0xAC))                 # 1 s
        w(0x08, 0x00)
        cmd.extend((0x61, 0xA0, 0x44))                 # 0.4 s
    cmd.append(0x66)
    hdr = bytearray(0x100)
    hdr[0:4] = b"Vgm "
    struct.pack_into("<I", hdr, 0x08, 0x171)
    struct.pack_into("<I", hdr, 0x18, int(44100 * 1.4 * len(midi_notes)))
    struct.pack_into("<I", hdr, 0x30, clock)
    struct.pack_into("<I", hdr, 0x34, 0x100 - 0x34)
    data = hdr + cmd
    struct.pack_into("<I", data, 4, len(data) - 4)
    vgm = path.with_suffix(".vgm")
    vgm.write_bytes(data)
    subprocess.run(["vgm2wav", str(vgm), str(path)], capture_output=True)
    vgm.unlink()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("vgm")
    ap.add_argument("--out", default="build/music/opm_analysis")
    a = ap.parse_args()
    res = analyse(a.vgm)
    sr = 44100
    notes = res["notes"]
    print("%s: YM2151 clock %d, %.1f s, %d notes" % (a.vgm, res["clock"], res["total"] / sr, len(notes)))
    patches = []
    for n in notes:
        if n["patch"] not in patches:
            patches.append(n["patch"])
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rep = {"seconds": res["total"] / sr, "channels": {}, "patches": []}
    print("\nchannels:")
    for ch in range(8):
        cn = [n for n in notes if n["ch"] == ch]
        if not cn:
            continue
        ms = [n["midi"] for n in cn if n["midi"] is not None]
        used = collections.Counter(patches.index(n["patch"]) for n in cn)
        durs = sorted(n["dur"] / sr for n in cn)
        info = dict(notes=len(cn), range=[name(min(ms)), name(max(ms))] if ms else None, patches=dict(used),
                    median_dur=durs[len(durs) // 2], first=cn[0]["t"] / sr, last=(cn[-1]["t"] + cn[-1]["dur"]) / sr,
                    tl=[min(n["tl"] for n in cn), max(n["tl"] for n in cn)], noise=any(n["noise"] for n in cn))
        rep["channels"][ch] = info
        print("  ch%d: %3d notes, %-8s, patches %s, median %.3f s, %.1f-%.1f s, carrier TL %d-%d%s" % (
            ch, info["notes"], "-".join(info["range"]) if info["range"] else "", dict(used), info["median_dur"], info["first"],
            info["last"], info["tl"][0], info["tl"][1], ", NOISE" if info["noise"] else ""))
    print("\ninstruments (FB/CON, operators: DT1MUL KSAR AMD1R DT2D2R D1LRR [TL of modulators]):")
    for i, p in enumerate(patches):
        users = sorted({n["ch"] for n in notes if n["patch"] == p})
        cnt = sum(1 for n in notes if n["patch"] == p)
        fb, con = (p[0] >> 3) & 7, p[0] & 7
        print("  #%d: CON %d FB %d PMS/AMS %02X, %d notes on channels %s" % (i, con, fb, p[1], cnt, users))
        rep["patches"].append(dict(index=i, con=con, fb=fb, pmsams=p[1], ops=[list(o) for o in p[2:]], notes=cnt, channels=users))
        for s_, o in enumerate(p[2:]):
            print("      op%d %s" % (s_, " ".join("%02X" % v for v in o)))
        first = next(n for n in notes if n["patch"] == p)
        car = CARRIERS[con]
        loud = min(first["mod_tl"][c] for c in car)
        render_patch(p, res["clock"], out / ("patch_%d.wav" % i), tuple(max(0, v - loud) if k not in car else 0 for k, v in enumerate(first["mod_tl"])))
    # polyphony and timing
    starts = sorted(n["t"] for n in notes)
    gaps = collections.Counter(round((b - a) / sr * 50) for a, b in zip(starts, starts[1:]) if b > a)
    poly = 0
    edges = sorted([(n["t"], 1) for n in notes] + [(n["t"] + n["dur"], -1) for n in notes])
    cur = 0
    for _, e in edges:
        cur += e
        poly = max(poly, cur)
    print("\nmax simultaneous notes: %d; most common gaps between note starts (in 1/50 s): %s" % (poly, gaps.most_common(6)))
    rep["max_polyphony"] = poly
    rep["gaps_50hz"] = gaps.most_common(10)
    rep["notes"] = [dict(ch=n["ch"], t=round(n["t"] / sr, 4), dur=round(n["dur"] / sr, 4), note=name(n["midi"]),
                         midi=None if n["midi"] is None else round(n["midi"], 2), patch=patches.index(n["patch"]), tl=n["tl"])
                    for n in notes]
    (out / "report.json").write_text(json.dumps(rep, indent=1) + "\n")
    print("\nwritten", out / "report.json", "and", len(patches), "patch WAVs")


if __name__ == "__main__":
    main()

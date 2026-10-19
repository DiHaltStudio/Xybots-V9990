#!/usr/bin/env python3
"""YM2151 (OPM) VGM/VGZ -> Furnace module for the OPL4 (YMF278B) PCM channels with YRW801 ROM (General MIDI) instruments
(feature/music). The module needs the Furnace build with OPL4 ROM instruments (ourown_furnace, `romIns` in the MP feature) and the
YRW801 ROM set in Settings > Emulation > Sample ROMs.

  opm2opl4_fur.py <song.vgz> <out.fur> [--hz 48] [--rows 128] [--map 0=82,1=51,2=40,3=90]

Channel k of the YM2151 plays on PCM channel k+1 (Furnace channel 18+k). Every note keeps its time (rounded to the row rate), its
sounding pitch (key code, fraction as E5xx, the carrier's MUL), its volume (the carrier TL; OPM steps are 0.75 dB, OPL4 PCM 0.375 dB)
and the stereo position of its channel (08xy). The FM timbres found by opm_analyze.py become ROM instruments: --map timbre=GM program
(1-128, as in the Furnace menu; 129 = drum kit). Default map: the proposal of doc/MUSIC_INTRO_ANALYSIS.md.
"""
import argparse
import math
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import opm_analyze as O  # noqa: E402

FUR_VERSION = 228
OPL4, OPL4_CHANNELS, PCM0 = 0xAE, 42, 18
INS_MULTIPCM = 28
GM_NAMES = {34: "Electric Bass (finger)", 119: "Synth Drum", 40: "Synth Bass 2", 51: "Synth Strings 1", 82: "Lead 2 (sawtooth)", 90: "Pad 2 (warm)", 39: "Synth Bass 1",
            63: "Synth Brass 1", 85: "Lead 5 (charang)", 95: "Pad 7 (halo)", 129: "Drum kit"}
NOTE_OFF = 180


class W:
    def __init__(self):
        self.b = bytearray()

    def u8(self, v): self.b.append(v & 255)
    def u16(self, v): self.b += struct.pack("<H", v & 0xFFFF)
    def s16(self, v): self.b += struct.pack("<h", v)
    def u32(self, v): self.b += struct.pack("<I", v & 0xFFFFFFFF)
    def f32(self, v): self.b += struct.pack("<f", v)
    def ascii(self, s): self.b += s.encode("ascii")
    def string(self, s): self.b += s.encode("utf-8") + b"\0"
    def pos(self): return len(self.b)
    def patch32(self, at, v): struct.pack_into("<I", self.b, at, v)

    def block(self, code):
        self.ascii(code)
        self.u32(0)
        return self.pos() - 4

    def end(self, at):
        self.patch32(at, self.pos() - at - 4)

    def feature(self, code, data):
        self.ascii(code)
        self.u16(len(data))
        self.b += data


def build_rows(notes, patches, hz, sr=44100):
    """{(row, channel): dict(note, ins, vol, fx[])} from the analysed notes."""
    rows = {}
    last_end = {}
    pan_done = {}
    loud = min(n["tl"] for n in notes)
    for n in sorted(notes, key=lambda n: n["t"]):
        ch = PCM0 + n["ch"]
        r0 = round(n["t"] * hz / sr)
        r1 = max(r0 + 1, round((n["t"] + n["dur"]) * hz / sr))
        if n["midi"] is None:
            continue
        base = math.floor(n["midi"] + 1e-6)
        frac = round((n["midi"] - base) * 128)
        if frac >= 128:
            base, frac = base + 1, frac - 128
        cell = rows.setdefault((r0, ch), {"fx": []})
        cell["note"] = base + 48                      # Furnace: C-4 = 108 = MIDI 60
        cell["ins"] = patches.index(n["patch"])
        cell["vol"] = max(0, min(127, 127 - 2 * (n["tl"] - loud)))
        cell["fx"] = [(0xE5, 128 + frac)]
        if pan_done.get(ch) != n["pan"]:
            cell["fx"].append((0x08, {1: 0xF0, 2: 0x0F, 3: 0xFF}.get(n["pan"], 0xFF)))
            pan_done[ch] = n["pan"]
        off = rows.get((r1, ch))
        if off is None or "note" not in off:
            rows.setdefault((r1, ch), {"fx": []}).setdefault("note", NOTE_OFF)
        last_end[ch] = r1
    # a note that starts where the previous one would be switched off replaces the off
    return rows


AUTHOR = "Earl Vickers, Hal Canon, Brad Fuller (Atari 1987)"
COMMENT = "Xybots arcade intro: YM2151 VGM converted to OPL4 PCM with YRW801 ROM instruments by tools/opm2opl4_fur.py."


def write_fur(path, title, rows, instruments, hz, pattern_rows, end=None, names=None, author=AUTHOR, comment=COMMENT, highlight=(4, 16),
              samples=(), fx_cols=2):
    """end: seconds where the song stops (FF00); None: 1.5 s after the last row (the arcade intro). A looping song ends exactly at the
    length of its VGM: the game's player jumps from there to the loop point (tools/opl4_stream.py).
    names: [(name, short name)] of the PCM channels used, from PCM 1 (default: 8 channels "OPM 1".. / "O1".., the YM2151's).
    instruments: (name, GM program 1-129) of the ROM, or dict(name, rom (GM 0-128) or sample (index), mp (AR, D1R, DL, D2R, RR, RC,
    LFO, VIB, AM)); samples: dict(name, data (signed 8-bit bytes), rate (C-4), loop (start, end) or None); fx_cols: effect columns."""
    names = names or [("OPM %d" % (k + 1), "O%d" % (k + 1)) for k in range(8)]
    last = max(r for r, c in rows)
    end_row = last + int(round(1.5 * hz)) if end is None else int(round(end * hz))
    rows.setdefault((end_row, PCM0), {"fx": []})["fx"].append((0xFF, 0x00))      # stop the song
    if end_row % pattern_rows == 0 and (end_row - 1, PCM0) not in rows:   # an end on a pattern's first row: on the row before it,
        rows[(end_row - 1, PCM0)] = rows.pop((end_row, PCM0))              # no empty last pattern (playing again from there was silent)
        end_row -= 1
    orders = end_row // pattern_rows + 1
    chans = list(range(PCM0, PCM0 + len(names)))
    f = W()
    f.ascii("-Furnace module-")
    f.u16(FUR_VERSION); f.u16(0); f.u32(32); f.u32(0); f.u32(0)
    info = f.block("INFO")
    f.u8(0); f.u8(1); f.u8(1); f.u8(1)               # time base, speeds 1/1, arpeggio speed
    f.f32(hz)
    f.u16(pattern_rows); f.u16(orders)
    f.u8(highlight[0]); f.u8(highlight[1])           # highlights
    f.u16(len(instruments)); f.u16(0); f.u16(len(samples))   # instruments, wavetables, samples
    f.u32(orders * len(chans))                       # patterns
    for i in range(32):
        f.u8(OPL4 if i == 0 else 0)
    for i in range(32):
        f.u8(64 if i == 0 else 0)                    # chip volume
    for i in range(32):
        f.u8(0)                                      # chip panning
    flag_ptr = f.pos()
    for i in range(32):
        f.u32(0)
    f.string(title); f.string(author)
    f.f32(440.0)
    for i in range(20):
        f.u8(0)
    ins_ptr = f.pos()
    for i in instruments:
        f.u32(0)
    smp_ptr = f.pos()
    for i in samples:
        f.u32(0)
    pat_ptr = f.pos()
    for i in range(orders * len(chans)):
        f.u32(0)
    for ch in range(OPL4_CHANNELS):                  # order table: pattern o of every channel in order o
        for o in range(orders):
            f.u8(o)
    for ch in range(OPL4_CHANNELS):                  # effect columns
        f.u8(fx_cols if ch in chans else 1)
    for ch in range(OPL4_CHANNELS):
        f.u8(3)                                      # channel shown
    for ch in range(OPL4_CHANNELS):
        f.u8(0)                                      # not collapsed
    for ch in range(OPL4_CHANNELS):
        f.string(names[ch - PCM0][0] if ch in chans else "")
    for ch in range(OPL4_CHANNELS):
        f.string(names[ch - PCM0][1] if ch in chans else "")
    f.string(comment)
    f.f32(1.0)
    for i in range(28):
        f.u8(0)
    f.u16(1); f.u16(1)                               # virtual tempo
    f.string(""); f.string("")
    f.u8(0); f.u8(0); f.u8(0); f.u8(0)               # subsongs, reserved
    f.string("MSX + Moonsound (OPL4)")
    for i in range(5):
        f.string("")
    f.f32(1.0); f.f32(0.0); f.f32(0.0)               # chip volume / panning / front-rear
    f.u32(0); f.u8(1)                                # patchbay: automatic
    for i in range(8):
        f.u8(0)
    f.u8(1); f.u8(1)
    for i in range(15):
        f.u8(0)
    f.u8(0)                                          # grooves
    dir_ptr = f.pos()
    f.u32(0); f.u32(0); f.u32(0)
    f.end(info)
    for i in range(3):
        f.patch32(dir_ptr + 4 * i, f.pos())
        d = f.block("ADIR")
        f.u32(0)
        f.end(d)
    f.patch32(flag_ptr, f.pos())
    fl = f.block("FLAG")
    f.string("ramSize=1\n")                          # 2 MB RAM at most: the YRW801 ROM stays mapped
    f.end(fl)
    for i, ins in enumerate(instruments):
        if not isinstance(ins, dict):
            ins = dict(name=ins[0], rom=ins[1] - 1, mp=(15, 15, 0, 0, 15, 15, 0, 0, 0))   # the ROM region overrides the envelope
        f.patch32(ins_ptr + 4 * i, f.pos())
        b = f.block("INS2")
        f.u16(FUR_VERSION); f.u16(INS_MULTIPCM)
        nm = W(); nm.string(ins["name"])
        f.feature("NA", bytes(nm.b))
        mp = W()
        for v in ins["mp"]:                          # ar d1r dl d2r rr rc lfo vib am
            mp.u8(v)
        mp.u8(8)                                     # flags: level direct
        if ins.get("rom") is not None:
            mp.s16(ins["rom"])                       # romIns: 0-127 GM program, 128 drum kit
            mp.u8(0)                                 # romLayer
        f.feature("MP", bytes(mp.b))
        if ins.get("sample") is not None:
            sm = W()
            sm.u16(ins["sample"]); sm.u8(2); sm.u8(0)   # initial sample, flags: use sample, wave length
            f.feature("SM", bytes(sm.b))
        f.ascii("EN")
        f.end(b)
    for i, sp in enumerate(samples):
        f.patch32(smp_ptr + 4 * i, f.pos())
        b = f.block("SMP2")
        f.string(sp["name"])
        f.u32(len(sp["data"])); f.u32(int(sp["rate"])); f.u32(int(sp["rate"]))
        f.u8(8); f.u8(0); f.u8(0); f.u8(0)           # 8-bit PCM, loop forward, flags
        lp = sp.get("loop")
        f.u32(lp[0] if lp else 0xFFFFFFFF); f.u32(lp[1] if lp else 0xFFFFFFFF)
        f.u32(1); f.u32(0); f.u32(0); f.u32(0)       # present in the memory of chip 0
        f.b += bytes(sp["data"])
        f.end(b)
    k = 0
    for ch in chans:
        for o in range(orders):
            f.patch32(pat_ptr + 4 * k, f.pos())
            k += 1
            b = f.block("PATN")
            f.u8(0); f.u8(ch); f.u16(o); f.string("")
            for lr in range(pattern_rows):
                cell = rows.get((o * pattern_rows + lr, ch))
                if not cell or not (cell["fx"] or "note" in cell or "ins" in cell or "vol" in cell):   # (a volume alone is a change)
                    f.u8(0)
                    continue
                mask = (1 if "note" in cell else 0) | (2 if "ins" in cell else 0) | (4 if "vol" in cell else 0)
                fx = cell["fx"][:fx_cols]
                emask = 0
                if fx:
                    mask |= 8 | 16
                for e in range(1, len(fx)):
                    emask |= 3 << (e * 2)
                    mask |= 32
                f.u8(mask)
                if mask & 32:
                    f.u8(emask)
                if "note" in cell:
                    f.u8(cell["note"])
                if "ins" in cell:
                    f.u8(cell["ins"])
                if "vol" in cell:
                    f.u8(cell["vol"])
                for c, v in fx:
                    f.u8(c); f.u8(v)
            f.u8(255)
            f.end(b)
    pathlib.Path(path).write_bytes(bytes(f.b))
    return orders


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("vgm")
    ap.add_argument("out")
    ap.add_argument("--hz", type=float, default=48.0, help="rows per second (48: a semiquaver of the 144 BPM intro = 5 rows)")
    ap.add_argument("--rows", type=int, default=128)
    ap.add_argument("--map", default="0=82,1=51,2=40,3=90")
    ap.add_argument("--end", choices=("auto", "vgm"), default="auto",
                    help="auto: 1.5 s after the last note (the intro); vgm: at the VGM length (a looping song)")
    a = ap.parse_args()
    res = O.analyse(a.vgm)
    notes = res["notes"]
    patches = []
    for n in notes:
        if n["patch"] not in patches:
            patches.append(n["patch"])
    gm = {int(k): int(v) for k, v in (x.split("=") for x in a.map.split(","))}
    instruments = [("timbre %d: GM %d %s" % (i, gm[i], GM_NAMES.get(gm[i], "")), gm[i]) for i in range(len(patches))]
    rows = build_rows(notes, patches, a.hz)
    end = res["total"] / 44100 if a.end == "vgm" else None
    orders = write_fur(a.out, pathlib.Path(a.vgm).stem + " (OPL4)", rows, instruments, a.hz, a.rows, end)
    print("%s: %d notes, %d instruments %s, %d orders of %d rows at %g Hz" % (
        a.out, len(notes), len(instruments), [n for n, _ in instruments], orders, a.rows, a.hz))


if __name__ == "__main__":
    main()

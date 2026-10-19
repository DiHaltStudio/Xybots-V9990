#!/usr/bin/env python3
"""MIDI song (GarageBand, one MIDI track per instrument) -> Furnace module for the OPL4 (YMF278B) PCM channels with the YRW801 ROM
(General MIDI) instruments, to edit the song in Furnace (ADR-049). The same instruments as the game plays it (tools/midi2wave.py:
--map like there, else the track's MIDI instrument name / keywords / program; MIDI channel 10 the drum kit). Needs the Furnace build
with OPL4 ROM instruments (`romIns`, see tools/opm2opl4_fur.py) and yrw801.rom in Settings > Emulation > Sample ROMs.

  midi2fur.py <song.mid> <out.fur> [--map track=instrument,...] [--rows-per-beat 16]

Each track gets as many PCM channels as notes it plays at once (named after the track). Rows: --rows-per-beat per quarter note (16:
a semiquaver = 4 rows; at 120 BPM 32 rows a second), one bar of 4/4 per pattern. Every note keeps its row, its velocity as the volume
(the loudest note of each track 127, the steps of tools/midi2wave.py) and its key (Furnace C-4 = MIDI 60). Pitch bend (the MPK
mini's joystick, over the track's bend range): within the note, legato (EA01 .. EA00) with the bent key plus the fine pitch E5xx
(80 = none, 128 units a semitone) on each row the bend changes. FF00 at the end of the song.
"""
import argparse
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import smf  # noqa: E402
import yrw801 as Y  # noqa: E402
import midi2wave as M  # noqa: E402
import opm2opl4_fur as F  # noqa: E402


def key(pitch):
    """sounding pitch (fractional MIDI note) -> (Furnace note, E5xx value)."""
    base = math.floor(pitch + 1e-6)
    frac = round((pitch - base) * 128)
    if frac >= 128:
        base, frac = base + 1, frac - 128
    return base + 48, 128 + frac


def convert(path, maps=None, rows_per_beat=16):
    """-> (rows {(row, channel): cell}, instruments [(name, GM 1-129)], channel names, rows per second, length in seconds, report)."""
    song = smf.read(path)
    div = song["division"]
    hz = rows_per_beat * 1e6 / song["tempos"][0][1]
    assert len({u for t, u in song["tempos"]}) == 1, "one tempo only"
    row = lambda t: int(round(t * rows_per_beat / div))
    rows, instruments, names, rep = {}, [], [], []
    for tr in song["tracks"]:
        if not tr["notes"]:
            continue
        ins = M.pick(tr, maps or {})
        gm = ins + 1                                    # Furnace's menu: 1-128, 129 = drum kit
        if (Y.NAMES[ins], gm) not in instruments:
            instruments.append((Y.NAMES[ins], gm))
        ii = instruments.index((Y.NAMES[ins], gm))
        vmax = max(n[4] for n in tr["notes"])
        rng = M.bend_range(tr)
        bends = [(row(t), v * rng / 8192) for t, ch, v in tr["bends"]]
        pool, free, bent = [], [], 0                    # the track's channels, the row each one is free from; notes bent
        for t0, t1, ch, n, vel in tr["notes"]:
            r0, r1 = row(t0), max(row(t0) + 1, row(t1))
            k = next((k for k in range(len(pool)) if free[k] <= r0), None)
            if k is None:
                pool.append(F.PCM0 + len(names))
                names.append(("%s %d" % (tr["name"], len(pool)), "%s%d" % (tr["name"][:3], len(pool))))
                free.append(0)
                k = len(pool) - 1
            c = pool[k]
            free[k] = r1
            b0 = next((b for r, b in reversed(bends) if r <= r0), 0.0)
            bend = {}
            for r, b in bends:                          # the last value of each row while the note is held
                if r0 < r < r1:
                    bend[r] = b
            bent += bool(bend or b0)
            note, fine = key(n + b0)
            cell = rows.setdefault((r0, c), {"fx": []})
            cell.update(note=note, ins=ii, vol=max(0, 127 - M.att_of(max(1, round(vel * 127 / vmax)))))
            cell["fx"] = [(0xEA, 1), (0xE5, fine)] if bend else [(0xE5, fine)]
            for r, b in sorted(bend.items()):
                bn, bf = key(n + b)
                last = r == max(bend)
                rows[(r, c)] = {"note": bn, "fx": [(0xE5, bf), (0xEA, 0)] if last else [(0xE5, bf)]}
            off = rows.get((r1, c))
            if off is None or "note" not in off:
                rows.setdefault((r1, c), {"fx": []}).setdefault("note", F.NOTE_OFF)
        rep.append("track %r: %s (GM %d), %d notes, PCM channel(s) %s%s" % (
            tr["name"], Y.NAMES[ins], gm, len(tr["notes"]), [p - F.PCM0 + 1 for p in pool],
            ", pitch bend on %d note(s) (range %g semitones)" % (bent, rng) if bent else ""))
    length = smf.seconds(song, song["length"])
    return rows, instruments, names, hz, length, rep


def furnace_vol(att, ins, note):
    """The volume column value that gives attenuation att in Furnace's OPL4 PCM: a RAM sample 127 - att; a ROM instrument goes
    through its region's tone attenuation and volume factor and 8 steps louder there (DivPlatformOPL::pcmTL), so the inverse."""
    if isinstance(ins, str):
        return max(0, min(127, 127 - att))
    rg = Y.regions(ins, int(round(note)))[0]

    def tl(vol):
        a = 0x7F - vol + rg[7]
        a = 0x7F - (0x7F - a) * rg[8] // 0xFE - 8
        return max(0, min(0x7F, a))
    return min(range(1, 128), key=lambda v: (abs(tl(v) - att), -v))


def from_trace(trace, sources, total, rows_per_beat=16, bpm=120.0, sr=44100):
    """The arrangement as the game plays it (ADR-049): tools/midi2wave.py convert(..., trace=[]) gives a dict per note (track,
    times, pitch and its changes, instrument, levels, pan, LFO, envelope); sources: {RAM instrument name: (signed 8-bit bytes,
    C-4 rate, (loop start, end) or None)}. -> (rows, instruments, channel names, samples, rows per second, length in seconds).
    Each track gets a channel per note at once; a note: its key + E5xx, its instrument (one per sample / ROM program, LFO, AM,
    envelope: e.g. "scc00 + tremolo"), its level as the volume (127 - attenuation in 0.375 dB steps) and every level change on its
    row (fades, decay, crossfades), the pan as 08xy when it changes, a pitch change (bend, glide) as legato EA01 .. EA00 with
    key + E5xx on each row; a note off at its end."""
    hz = rows_per_beat * bpm / 60
    row = lambda t: int(round(t / sr * hz))
    rows, instruments, keys, names, samples, smp_index = {}, [], {}, [], [], {}
    pools, chan_pan = {}, {}
    for nt in sorted(trace, key=lambda d: (d["t0"], d["track"])):
        ins, lfo, am, env = nt["ins"], nt["lfo"], nt["am"], tuple(nt["env"])
        key_ins = (ins, lfo, am, env)
        if key_ins not in keys:
            mp = (env[0] >> 4, env[0] & 15, env[1] >> 4, env[1] & 15, env[2] & 15, env[2] >> 4, lfo >> 3 & 7, lfo & 7, am)
            label = ("%s" % ins if isinstance(ins, str) else "GM %d %s" % (ins, Y.NAMES[ins])) + (" + tremolo" if am else "")
            d = dict(name=label, mp=mp)
            if isinstance(ins, str):
                if ins not in smp_index:
                    data, rate, loop = sources[ins]
                    smp_index[ins] = len(samples)
                    samples.append(dict(name=ins, data=data, rate=rate, loop=loop))
                d["sample"] = smp_index[ins]
            else:
                d["rom"] = ins
            keys[key_ins] = len(instruments)
            instruments.append(d)
        pool = pools.setdefault(nt["track"], [])
        r0, r1 = row(nt["t0"]), max(row(nt["t0"]) + 1, row(nt["t1"]))
        c = next((ch for ch, free in pool if free <= r0), None)
        if c is None:
            c = F.PCM0 + len(names)
            names.append(("%s %d" % (nt["track"], len(pool) + 1), "%s%d" % (nt["track"][:3], len(pool) + 1)))
            pool.append([c, 0])
        next(p for p in pool if p[0] == c)[1] = r1
        note, fine = key(nt["note"])
        fx = [(0xE5, fine)]
        p = nt["pan"]
        if chan_pan.get(c) != p:
            chan_pan[c] = p
            if p == 0:
                v = 0xFF
            elif p < 8:
                v = 0xF0 | max(0, 15 - 2 * p)                        # to the left: the right quieter
            else:
                v = max(0, 15 - 2 * (16 - p)) << 4 | 0x0F            # to the right: the left quieter
            fx.append((0x08, v))
        pitches = [(row(t), q) for t, q in nt["pitches"] if r0 < row(t) < r1]
        if pitches:
            fx.append((0xEA, 1))
        rows[(r0, c)] = dict(note=note, ins=keys[key_ins], vol=furnace_vol(nt["levels"][0][1], ins, nt["note"]), fx=fx)
        for t, a in nt["levels"][1:]:
            r = row(t)
            if r0 < r < r1:
                rows.setdefault((r, c), {"fx": []})["vol"] = furnace_vol(a, ins, nt["note"])
        last = {}
        for r, q in pitches:
            last[r] = q
        for r in sorted(last):
            bn, bf = key(last[r])
            cell = rows.setdefault((r, c), {"fx": []})
            cell["note"] = bn
            cell["fx"] = [(0xE5, bf)] + ([(0xEA, 0)] if r == max(last) else [])
        off = rows.get((r1, c))
        if off is None or "note" not in off:
            rows.setdefault((r1, c), {"fx": []}).setdefault("note", F.NOTE_OFF)
    assert len(names) <= 24, "more than the 24 PCM channels of the OPL4: %d" % len(names)
    return rows, instruments, names, samples, hz, total / sr


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mid")
    ap.add_argument("out")
    ap.add_argument("--map", default="", help="track=instrument,... (GM program 0-127 or part of its name, as midi2wave.py)")
    ap.add_argument("--rows-per-beat", type=int, default=16)
    a = ap.parse_args()
    rows, instruments, names, hz, length, rep = convert(a.mid, M.parse_map(a.map), a.rows_per_beat)
    bar = 4 * a.rows_per_beat
    orders = F.write_fur(a.out, pathlib.Path(a.mid).stem + " (OPL4)", rows, instruments, hz, bar, end=length, names=names,
                         author="DiHalt", comment="%s converted to OPL4 PCM with YRW801 ROM instruments by tools/midi2fur.py." %
                         pathlib.Path(a.mid).name, highlight=(a.rows_per_beat, bar))
    print("\n".join(rep))
    print("%s: %d PCM channels, %d instruments, %d orders of %d rows at %g Hz, %.2f s" % (
        a.out, len(names), len(instruments), orders, bar, hz, length))


if __name__ == "__main__":
    main()

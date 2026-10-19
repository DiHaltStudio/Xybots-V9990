#!/usr/bin/env python3
"""Standard MIDI File reader (formats 0 and 1), no dependencies (feature/music: songs composed in GarageBand for the OPL4).

  smf.py <song.mid>      summary: tempo, tracks, notes per track (range, count, start / end), channels, programs

read(path) -> dict(division, tempos [(tick, us per quarter)], tracks [dict(name, instrument, notes [(start tick, end tick, channel,
note, velocity)], programs {channel: program}, controls [(tick, channel, controller, value)], bends [(tick, channel, -8192..8191)])],
length tick). seconds(song, tick) converts a tick with the tempo map.
"""
import pathlib
import struct
import sys


def _vlq(d, i):
    v = 0
    while True:
        b = d[i]
        i += 1
        v = v << 7 | (b & 0x7F)
        if not b & 0x80:
            return v, i


def read(path):
    d = pathlib.Path(path).read_bytes()
    assert d[:4] == b"MThd", "not a MIDI file"
    fmt, ntrk, div = struct.unpack(">HHH", d[8:14])
    assert not div & 0x8000, "SMPTE time division not supported"
    i = 8 + struct.unpack(">I", d[4:8])[0]
    tempos, tracks, length = [], [], 0
    for _ in range(ntrk):
        assert d[i:i + 4] == b"MTrk"
        n = struct.unpack(">I", d[i + 4:i + 8])[0]
        j, end, t, status = i + 8, i + 8 + n, 0, 0
        tr = dict(name="", instrument="", notes=[], programs={}, controls=[], bends=[])
        on = {}
        while j < end:
            dt, j = _vlq(d, j)
            t += dt
            b = d[j]
            if b == 0xFF:
                typ = d[j + 1]
                ln, j = _vlq(d, j + 2)
                data = d[j:j + ln]
                j += ln
                if typ == 0x03:
                    tr["name"] = data.decode("latin-1")
                elif typ == 0x04:
                    tr["instrument"] = data.decode("latin-1")
                elif typ == 0x51:
                    tempos.append((t, int.from_bytes(data, "big")))
                elif typ == 0x2F:
                    break
                continue
            if b in (0xF0, 0xF7):
                ln, j = _vlq(d, j + 1)
                j += ln
                continue
            if b & 0x80:
                status = b
                j += 1
            hi, ch = status & 0xF0, status & 15
            if hi in (0xC0, 0xD0):
                a = d[j]
                j += 1
                if hi == 0xC0:
                    tr["programs"][ch] = a
                continue
            a, v = d[j], d[j + 1]
            j += 2
            if hi == 0x90 and v:
                on.setdefault((ch, a), []).append((t, v))
            elif hi == 0x80 or hi == 0x90:
                if on.get((ch, a)):
                    t0, vel = on[(ch, a)].pop(0)
                    tr["notes"].append((t0, t, ch, a, vel))
            elif hi == 0xB0:
                tr["controls"].append((t, ch, a, v))
            elif hi == 0xE0:
                tr["bends"].append((t, ch, (v << 7 | a) - 8192))
        for (ch, a), lst in on.items():
            for t0, vel in lst:
                tr["notes"].append((t0, t, ch, a, vel))
        tr["notes"].sort()
        length = max(length, t)
        tracks.append(tr)
        i = end
    return dict(format=fmt, division=div, tempos=sorted(tempos) or [(0, 500000)], tracks=tracks, length=length)


def seconds(song, tick):
    """Tick -> seconds with the tempo map."""
    s, last_t, us = 0.0, 0, 500000
    for t, u in song["tempos"]:
        if t >= tick:
            break
        s += (t - last_t) * us / 1e6 / song["division"]
        last_t, us = t, u
    return s + (tick - last_t) * us / 1e6 / song["division"]


NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def note_name(n):
    return "%s%d" % (NAMES[n % 12], n // 12 - 1)


def main():
    s = read(sys.argv[1])
    print("format %d, %d ticks per quarter, tempo %s, length %.2f s" % (
        s["format"], s["division"], ", ".join("%.1f BPM at tick %d" % (60e6 / u, t) for t, u in s["tempos"]),
        seconds(s, s["length"])))
    for k, tr in enumerate(s["tracks"]):
        ns = tr["notes"]
        if not ns:
            print("track %d %r: no notes" % (k, tr["name"]))
            continue
        poly = max(sum(1 for b in ns if b[0] <= a[0] < b[1]) for a in ns)
        bends = [b for b in tr["bends"] if b[2]]
        print("track %d %r (%s): %d notes, %s-%s, channels %s, programs %s, %.2f-%.2f s, at most %d at once%s" % (
            k, tr["name"], tr["instrument"], len(ns), note_name(min(n[3] for n in ns)), note_name(max(n[3] for n in ns)),
            sorted({n[2] for n in ns}), tr["programs"], seconds(s, ns[0][0]), seconds(s, max(n[1] for n in ns)), poly,
            ", pitch bend %.2f-%.2f s" % (seconds(s, bends[0][0]), seconds(s, bends[-1][0])) if bends else ""))


if __name__ == "__main__":
    main()

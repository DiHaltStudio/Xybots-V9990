#!/usr/bin/env python3
"""The logo song as a MoonBlaster for Moonsound (MBWave) song: <name>.MWM + its wave kit <name>.MWK (ADR-049), from the same trace
as the Furnace module (tools/midi2wave.py convert(..., trace=[])). The format as read by RoboPlay / libmoonsound (mwm_parser.c,
mwm2wav.c: the MBWave replayer), checked against the example songs:

  MWM "MBMS" 10h 08h (play mode), header (278 bytes: song length, loop position, stereo[24], tempo, base frequency, detune[24],
  modulation[3][16], start waves[24], wave numbers[48], wave volumes[48], song name[50], kit name[8]), position table, pattern
  offsets (file position of each pattern's data - 9), one block (size, number of patterns, data), 00 00 00. A pattern is 16 steps;
  a step is FFh (empty) or the event of channel 0, a 24-bit mask and the events of channels 1-23 and the command channel. Events:
  1-96 note (1 = C1 = MIDI 24), 97 off, 98-145 wave change (slot 0-47: its number and volume), 146-177 volume 0-31 (TL 4 x (31 -
  v): 1.5 dB steps), 178-192 stereo, 193-211 note link -9..+9 (the pitch without a new key on), 212.. pitch bend, 231.. detune.
  One event per channel and step.
  MWK "MBMS" 10h 0Dh: total sample size (3 bytes), number of own waves, tone info[64] (bit 0 used, bits 2-1 frequency table: 1 =
  "PC", index 48 = 22050 Hz, a semitone an index), own waves (transpose, 8 x (next patch note, tone, tone note)), per used tone a
  13-byte header (2 bytes, loop, end ^ FFFFh, LFO/VIB, AR/D1R, DL/D2R, RC/RR, AM: the OPL4 tone header; length) and its 8-bit
  samples.

Timing: 50 Hz, 3 ticks a step = a step a 1/32 note at 125 BPM (the song's 120 BPM does not divide the 50 / 60 Hz ticks: 4 %
faster, 9.6 s). The waveforms (32 samples) are stretched to 63 (nearest sample: their steps stay) so that the "PC" table plays them
in tune: tone note 7 (3.8 cents); the noise as it is (tone note 0: MIDI 60 = 11025 Hz). A wave per sample and LFO (the tremolo in
its tone header); the ROM's Fingered Bass is MBWave wave 40. Levels -> volume events in the channel's free steps (before a note,
or after it when the step before is taken); pitch changes -> note links; a channel's fine pitch (the chorus) -> its detune.
"""
import math
import struct

SR = 44100
WAVE_ROM = {33: 40}                                     # GM program -> MBWave ROM wave (Fingered Bass)
NOTE_OFF, WAVE_CHANGE, VOLUME, NOTE_LINK = 97, 98, 146, 193


def stretch(data, n):
    """A loop of len(data) samples -> n samples, nearest (the waveform keeps its steps)."""
    return bytes(data[int(i * len(data) / n)] for i in range(n))


def export(trace, sources, total, name, title, step_s=0.0625, tempo=3, base_freq=1):
    """-> (MWM bytes, MWK bytes, report lines). sources as for midi2fur.from_trace."""
    step = lambda t: int(round(t / SR / step_s))
    # waves: one per (instrument, LFO byte, AM, envelope); own ones get a tone each
    waves, tones, wave_of = [], [], {}
    for nt in trace:
        k = (nt["ins"], nt["lfo"], nt["am"], tuple(nt["env"]))
        if k in wave_of:
            continue
        ins = nt["ins"]
        if isinstance(ins, str):
            data, rate, loop = sources[ins]
            if loop and loop[1] - loop[0] == 32:                # a waveform: 63 samples, tone note 7
                pcm, tn, lp = stretch(data, 63), 7, 0
            else:                                               # the noise (11025 Hz at MIDI 60 = index 36: tone note 0)
                assert abs(rate - 11025) < 1, (ins, rate)
                pcm, tn, lp = bytes(data), 0, 0 if loop else len(data) - 1
            env = nt["env"]
            tones.append(dict(name=ins, pcm=pcm, loop=lp, lfo=nt["lfo"], am=nt["am"], env=env))
            waves.append(dict(name=ins + (" trem" if nt["am"] else ""), own=len(tones) - 1, tone_note=tn))
        else:
            assert ins in WAVE_ROM, "no MBWave wave for GM %d" % ins
            waves.append(dict(name="ROM %d" % WAVE_ROM[ins], rom=WAVE_ROM[ins]))
        wave_of[k] = len(waves) - 1
    assert len(waves) <= 48 and len(tones) <= 64
    own = [w for w in waves if "own" in w]
    for k, w in enumerate(own):
        w["number"] = 176 + k
    for w in waves:
        w.setdefault("number", w.get("rom"))
    # channels: per track, a channel per note at once (on steps)
    chans, pools = [], {}
    notes = sorted(trace, key=lambda d: (d["t0"], d["track"]))
    for nt in notes:
        s0, s1 = step(nt["t0"]), max(step(nt["t0"]) + 1, step(nt["t1"]))
        pool = pools.setdefault(nt["track"], [])
        c = next((c for c in pool if chans[c]["free"] <= s0), None)
        if c is None:
            chans.append(dict(track=nt["track"], free=0, notes=[]))
            c = len(chans) - 1
            pool.append(c)
        chans[c]["free"] = s1
        chans[c]["notes"].append((s0, s1, nt))
    assert len(chans) <= 24, "more than 24 channels: %d" % len(chans)
    n_steps = step(total) + 1
    grid = [[0] * 25 for _ in range(n_steps + 16)]
    vol_of = lambda att: max(0, min(31, 31 - int(round(att / 4))))
    hdr_stereo, hdr_detune, start = [0] * 24, [0] * 24, [0] * 24
    lost = 0
    for c, ch in enumerate(chans):
        first = ch["notes"][0][2]
        p = first["pan"]
        hdr_stereo[c] = p                               # the panpot as the chip's (0 centre, 1-7 left, 9-15 right)
        frac = first["note"] - math.floor(first["note"] + 1e-6)
        if frac > 0.5:
            frac -= 1
        cents = frac * 100
        hdr_detune[c] = max(-7, min(7, int(round(1536 * (2 ** (cents / 1200) - 1) / 2))))   # 2 F-number units a step (mid octave)
        cur_wave = wave_of[(first["ins"], first["lfo"], first["am"], tuple(first["env"]))]
        start[c] = cur_wave + 1
        cur_vol = 31                                    # the wave's volume 0: full
        prev_start = -1

        def put(s, ev, lo, hi):
            for t in range(s, lo - 1, -1) if hi is None else range(s, hi + 1):
                if lo <= t < len(grid) and not grid[t][c]:
                    grid[t][c] = ev
                    return t
            return None
        for i, (s0, s1, nt) in enumerate(ch["notes"]):
            w = wave_of[(nt["ins"], nt["lfo"], nt["am"], tuple(nt["env"]))]
            v0 = vol_of(nt["levels"][0][1])
            if w != cur_wave:                           # the wave change before the note (it sets the volume to the wave's: full)
                if put(s0 - 1, WAVE_CHANGE + w, prev_start + 1, None) is not None:
                    cur_wave, cur_vol = w, 31
                else:
                    lost += 1
            assert not grid[s0][c], (c, s0)
            m = int(round(nt["note"])) if abs(nt["note"] - round(nt["note"])) < 0.3 else int(math.floor(nt["note"]))
            ev_note = max(1, min(96, m - 23))
            if v0 != cur_vol:                           # its volume: the step before, else the step after its key on
                if put(s0 - 1, VOLUME + v0, prev_start + 1, None) is not None:
                    cur_vol = v0
            grid[s0][c] = ev_note
            if v0 != cur_vol and put(s0 + 1, VOLUME + v0, s0 + 1, min(s0 + 2, s1 - 1)) is not None:
                cur_vol = v0
            # its level changes and pitch changes on the following steps
            lv = [(step(t), a) for t, a in sorted(nt["levels"][1:], key=lambda x: x[0])]   # in time order: the last one of a step
            pt = [(step(t), q) for t, q in sorted(nt["pitches"], key=lambda x: x[0])]      # counts (not the highest)
            cur_pitch, last_link = ev_note, False
            for s in range(s0 + 1, s1):
                if grid[s][c]:
                    continue
                pq = [q for t, q in pt if t <= s]
                target = max(1, min(96, int(round(pq[-1])) - 23)) if pq else cur_pitch
                la = [a for t, a in lv if t <= s]
                v = vol_of(la[-1]) if la else cur_vol
                # one event a step: a pitch change and a level change both due take turns (the link catches up, up to 9
                # semitones: the noise's glide and its rising level both get through)
                if target != cur_pitch and not (v != cur_vol and last_link):
                    d = max(-9, min(9, target - cur_pitch))
                    grid[s][c] = NOTE_LINK + 9 + d
                    cur_pitch += d
                    last_link = True
                elif v != cur_vol:
                    grid[s][c] = VOLUME + v
                    cur_vol = v
                    last_link = False
            nxt = ch["notes"][i + 1][0] if i + 1 < len(ch["notes"]) else None
            if nxt != s1:
                put(s1, NOTE_OFF, s1, (nxt - 1) if nxt else s1 + 3)
            prev_start = s0
    # patterns of 16 steps, the song as one position per pattern (no loop)
    pats = []
    for p0 in range(0, n_steps, 16):
        b = bytearray()
        for s in range(p0, p0 + 16):
            ev = grid[s] if s < len(grid) else [0] * 25
            if not any(ev):
                b.append(0xFF)
                continue
            b.append(ev[0])
            mask = 0
            for k in range(1, 25):
                if ev[k]:
                    mask |= 1 << (24 - k)
            b += bytes([mask >> 16 & 255, mask >> 8 & 255, mask & 255])
            b += bytes(ev[k] for k in range(1, 25) if ev[k])
        pats.append(bytes(b))
    n_pat = len(pats)
    hdr = bytearray()
    hdr += bytes([n_pat - 1, 255])                      # song length (positions - 1), loop position: none
    hdr += bytes(hdr_stereo)
    hdr += bytes([tempo, base_freq])
    hdr += bytes(d & 255 for d in hdr_detune)
    mod = [0, 1, 2, 1, 0, 0xFF, 0xFE, 0xFF, 10] + [0] * 7    # three modulation waves (unused): a small vibrato, end 10
    hdr += bytes(mod) * 3
    hdr += bytes(start)
    hdr += bytes((waves[k]["number"] if k < len(waves) else 0) for k in range(48))
    hdr += bytes(48)                                    # wave volumes: 0 = full
    hdr += title.encode("latin-1")[:50].ljust(50)
    hdr += name.upper().encode("latin-1")[:8].ljust(8)
    assert len(hdr) == 278
    mwm = bytearray(b"MBMS\x10\x08") + hdr + bytes(range(n_pat))
    base = len(mwm) + 2 * n_pat + 3
    offs, o = [], base - 9
    for p in pats:
        offs.append(o)
        o += len(p)
    mwm += struct.pack("<%dH" % n_pat, *offs)
    data = b"".join(pats)
    mwm += struct.pack("<HB", len(data), n_pat) + data + b"\0\0\0"
    # the wave kit
    info = bytearray(64)
    body = bytearray()
    for k, t in enumerate(tones):
        info[k] = 0x03                                  # used, "PC" frequency table, 8-bit
        n = len(t["pcm"])
        end = (n - 1) ^ 0xFFFF
        e = t["env"]
        body += bytes([0, 0, t["loop"] >> 8, t["loop"] & 255, end >> 8, end & 255, t["lfo"], e[0], e[1], e[2], t["am"], n & 255, n >> 8])
        body += t["pcm"]
    patches = bytearray()
    for w in own:
        patches += bytes([1, 96, w["own"], w["tone_note"]]) + bytes(21)
    total_size = sum(len(t["pcm"]) for t in tones)
    mwk = bytearray(b"MBMS\x10\x0D") + bytes([total_size & 255, total_size >> 8 & 255, total_size >> 16]) + bytes([len(own)])
    mwk += info + patches + body
    rep = ["%d channels, %d waves (%d own, %d tones), %d patterns, %d events lost (no free step)" % (
        len(chans), len(waves), len(own), len(tones), n_pat, lost)]
    rep += ["  ch %2d %-12s wave %-14s pan %2d detune %+d" % (c, ch["track"], waves[start[c] - 1]["name"], hdr_stereo[c], hdr_detune[c])
            for c, ch in enumerate(chans)]
    return bytes(mwm), bytes(mwk), rep

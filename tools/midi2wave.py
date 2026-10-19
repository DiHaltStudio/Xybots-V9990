#!/usr/bin/env python3
"""MIDI song (e.g. GarageBand, one MIDI track per instrument) -> writes for the wave part of the Moonsound: the General MIDI
instruments of its YRW801 ROM, no sample RAM (feature/music, ADR-027). Like the Linux OPL4 driver plays a note.

  midi2wave.py <song.mid> [--map track=instrument,...] [--transpose track=semitones,...] [--quantize 16] [--gain track=dB,...]
               [--drop track,...] [--notes track=from:to/from:to,...] [--sweep track=semitones,...] [--shift track=beats,...]

Instrument: a GM program number (0-127) or (part of) its name, as in tools/yrw801.py NAMES. A track without --map gets the GM
instrument whose name matches the MIDI instrument name of the track (GarageBand writes e.g. "Fingerstyle Bass"), else by keywords
(bass / bajo -> Fingered Bass, guitar / guitarra -> Nylon Guitar, piano -> Acoustic Grand Piano), else the program of the track.
A track on MIDI channel 10 plays the GM drum kit (GM drum note numbers: 36 kick, 38 snare, 42 hi-hat...; the ROM has notes 24-82,
57 sounds from 32 samples), its hits ring at least 0.5 s.
Notes play as written (an octave down for the bass made it inaudible, 55-82 Hz; --transpose bajo=-12 if wanted). Velocities are
scaled so that the loudest note of each track is 127 (the dynamics stay). Wave channels 0-21 (22 and 23 play the voices); instruments
with two layers take two channels per note. --quantize N: note starts to the nearest 1/N note.
Instruments in the Moonsound RAM (ADR-049): --map track=ram:<name> plays the tone convert() gets as ram[<name>] (e.g. a 32-sample
waveform of an instrument created for the SCC, looped, or a one-shot drum sample) instead of the ROM.
Pitch bend (e.g. the MPK mini's joystick) is played: the note's pitch follows it, one new pitch per 50 Hz frame at most, over the
bend range of the track (RPN 0, else the GM default of 2 semitones). Modulation (CC 1) is not played.
"""
import argparse
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import smf  # noqa: E402
import yrw801 as Y  # noqa: E402

SR = 44100
CHANNELS = 22
FRAME = SR / 50
FM_FS = 33868800 / 684                                  # sample rate of the FM part of the OPL4 (measured, tools/opm2opl3.py)
# FM timbres for --fm (2-operator channel of the FM part, array 0): register values of the modulator / carrier and C0h (feedback)
FM_TIMBRES = {
    "zap": dict(mod=(0x21, 0x10, 0xF2, 0x0F, 0), car=(0x21, 0x00, 0xF4, 0x2A, 0), c0=0x3C),      # bright: feedback 6
    "zap_metal": dict(mod=(0x23, 0x14, 0xF2, 0x0F, 0), car=(0x21, 0x00, 0xF4, 0x2A, 0), c0=0x38), # modulator x3: metallic
    "pew": dict(mod=(0x21, 0x3F, 0xF0, 0x0F, 0), car=(0x21, 0x00, 0xF4, 0x2A, 0), c0=0x30),      # no modulation: a pure tone
}
DRUMS = 128                                             # the Drum Kit "instrument" of tools/yrw801.py: one region per GM drum note
DRUM_RING = SR // 2                                     # drum hits sound at least this long (GarageBand writes very short notes)


def att_of(v):
    """MIDI volume / velocity 0-127 -> attenuation in 0.375 dB steps (about 6.7 dB per halving, as the driver's table)."""
    return 127 if v <= 0 else int(round(18.5 * math.log2(127 / v)))


def pitch_regs(note, region):
    """-> (octave register 4 bits, F-number 10 bits) for MIDI note (may be fractional) with the region's tuning."""
    pitch = int((note - 60) * 128 * region[4] // 100) + (60 << 7) + region[3]
    pitch = max(0, min(0x5FFF, pitch))
    octave = pitch // 0x600 - 8
    fn = int(round(1024 * (2 ** ((pitch % 0x600) / 1536) - 1)))
    if fn >= 1024:
        fn, octave = 0, octave + 1
    return octave & 15, fn


def fm_block(f):
    """frequency -> (block, F-number) of the FM part."""
    for b in range(8):
        fn = int(round(f * 2 ** (20 - b) / FM_FS))
        if fn < 1024:
            return b, fn
    return 7, 1023


def fm_writes(fm_notes):
    """(start, end, note, timbre, gain, sweep) -> FM writes (time, 0, register, value), a new pitch every frame while a sweep."""
    out, free = [(0, 1, 0x04, 0x00)] if fm_notes else [], [0, 0, 0]    # 104h: channels 0-2 2-operator (an FM song may leave 4-op)
    for t0, t1, n, tb, g, sw in sorted(fm_notes, key=lambda x: x[0]):
        ch = min(range(3), key=lambda k: free[k])
        free[ch] = t1 + FRAME
        out.append((max(0, int(t0 - FRAME)), 0, 0xB0 + ch, 0))                      # key off a frame before
        for op, regs in ((ch, tb["mod"]), (ch + 3, tb["car"])):
            v20, v40, v60, v80, ve0 = regs
            if op == ch + 3:
                v40 = min(63, max(0, v40 - g // 2))                                      # gain: 0.375 dB steps -> 0.75 dB
            out += [(t0, 0, 0x20 + op, v20), (t0, 0, 0x40 + op, v40), (t0, 0, 0x60 + op, v60), (t0, 0, 0x80 + op, v80),
                    (t0, 0, 0xE0 + op, ve0)]
        out.append((t0, 0, 0xC0 + ch, tb["c0"]))
        steps = max(1, int((t1 - t0) // FRAME))
        for k in range(steps + 1):
            f = 440 * 2 ** ((n - 69 - (sw * k / steps if sw else 0)) / 12)
            b, fn = fm_block(f)
            tk = t0 + int(k * FRAME)
            out += [(tk, 0, 0xA0 + ch, fn & 255), (tk, 0, 0xB0 + ch, 0x20 | b << 2 | fn >> 8)]
        out.append((t1, 0, 0xB0 + ch, 0))
    return out


def ram_region(ins):
    """A RAM instrument (dict: tone, rate = sample rate that plays MIDI note 60 (or every note: fixed), fixed, rr, att) as a region
    of tools/yrw801.py: pitch offset from the rate (44100 x 2^(octave-1) x (1 + F/1024)); no key scaling for a fixed one; AR 15,
    no decay (the level holds while keyed: decay= does the fading), RC 0 / RR its release."""
    p = 8 * 0x600 + 0x600 * (math.log2(ins["rate"] / 44100) + 1)
    off = int(round(p - (60 << 7)))
    return (0, 127, ins["tone"], off, 0 if ins.get("fixed") else 100, 0, 0, ins.get("att", 0), 0xFE, 0, 0xF0, 0x00, ins.get("rr", 6), 0)


def regions(ins, note):
    return [ram_region(ins)] if isinstance(ins, dict) else Y.regions(ins, note)


def ins_name(ins):
    return "RAM %s" % ins["name"] if isinstance(ins, dict) else "%s (GM %d)" % (Y.NAMES[ins], ins)


def bend_range(tr):
    """The track's pitch bend range in semitones: RPN 0 (CC 101 / 100 = 0, then data entry CC 6), else the GM default 2."""
    rpn, rng = [None, None], 2.0
    for t, ch, a, v in tr["controls"]:
        if a in (101, 100):
            rpn[a == 100] = v
        elif a == 6 and rpn == [0, 0]:
            rng = float(v)
    return rng


def pick(tr, maps, ram=None):
    name = tr["name"]
    if maps.get(name, "").startswith("ram:"):
        return dict(ram[maps[name][4:]], name=maps[name][4:])
    if 9 in {n[2] for n in tr["notes"]} and name not in maps:
        return DRUMS                                    # MIDI channel 10: the GM drum kit, whatever GarageBand calls its kit
    if name in maps:
        v = maps[name]
        return int(v) if v.isdigit() else Y.find(v)
    inst = tr["instrument"].lower()
    for k, n in enumerate(Y.NAMES[:128]):
        if inst and (n.lower() in inst or inst in n.lower()):
            return k
    low = name.lower() + " " + inst
    for keys, n in ((("bass", "bajo"), "Fingered Bass"), (("guitar", "guitarra"), "Nylon Guitar"), (("piano",), "Acoustic Grand")):
        if any(k in low for k in keys):
            return Y.find(n)
    return next(iter(tr["programs"].values()), 0)


def convert(path, maps=None, transpose=None, quantize=0, volume=127, boost=10, gain=None, drop=(), notemap=None, sweep=None, repeat=None, fm=None, shift=None, decay=None, drum_ring=DRUM_RING / SR, ram=None, tremolo=None, ramp=None, pan=None, copies=None,
            detune=None, arp=None, extra=None, fade_in=None, envelope=None, hold=None, window=None, trace=None):
    """-> (writes [(sample time, 2, register, value)], length in samples, report lines).
    volume: MIDI channel volume (127 = none taken off); boost: 0.375 dB steps louder (the driver's volume_boost);
    gain: {track: dB} louder (+) or quieter (-) than the others, clamped at the chip's full level; drop: tracks left out;
    notemap: {track: {MIDI note: note it plays}} (e.g. another drum of the kit), before the transposition;
    sweep: {track: semitones} each note of the track glides that far (down if > 0) frame by frame while it is held (a laser);
    repeat: {track: [bar, ...]} the notes of the first bar the track plays in are copied into those bars (bars from 0, 4/4);
    fm: {track: FM_TIMBRES name} the track plays on the FM part instead (2-operator channels 0-2 of array 0, one note at a time each;
    with its sweep: a laser); gain there in carrier level steps of 0.75 dB;
    shift: {track: beats} the track's notes move that many quarter notes later (< 0: earlier; e.g. -4: one bar of 4/4 earlier);
    decay: {track: dB per second} each note of the track gets quieter while it is held (the ROM samples of a guitar / an electric
    piano hold their level while keyed; GarageBand's die away): its level register, a step of 0.375 dB when due; or (dB per
    second, from seconds): only the notes starting from then;
    drum_ring: seconds a drum hit sounds at least (0.5; 0: as long as its MIDI note, then the sample's release: a tight kit);
    ram: {name: dict(tone, rate, fixed, rr, att)} the instruments in the Moonsound RAM that --map track=ram:<name> plays (ram_region);
    tremolo: {track: (from seconds, LFO 0-7, AM 0-7)} the track's notes from that time on with the chip's tremolo: register 80h LFO
    frequency (bits 5-3: 0.17 / 2.0 / 3.2 / 4.2 / 5.2 / 5.9 / 6.2 / 7.1 Hz), E0h AM depth (bits 2-0: 0 / 1.8 / 2.9 / 3.7 / 4.4 / 5.9 /
    7.4 / 11.9 dB); the LFO restarts at each key on;
    ramp: {track: (from seconds, to seconds, dB)} a crescendo: the track's notes starting at `from` get that much gain more (< 0:
    quieter), the later ones less, linearly to none at `to`;
    tremolo's tuple may have a 4th value: the vibrato depth (register 80h bits 2-0, at the same LFO frequency);
    pan: {track: 0-15} the chip's panpot (0 centre, 1-7 to the left: the right 3 dB quieter a step, 9-15 to the right: 9 = the left
    21 dB quieter .. 15 = 3 dB; 8 silent);
    copies: {new track: (track, beats later[, until seconds])} a copy of a track (its notes and bends; with `until` only the notes
    starting before then), e.g. an echo; gain / pan / ... by its name;
    detune: {track: cents} the track's notes that much higher (a detuned copy: a chorus);
    arp: {track: (from beats, step beats, [semitones], dB a note, until beats)} from `from` on the track's notes become an
    arpeggio: the lowest note sounding at `from` (or the next one) plus the offsets in turn, a note a step, each the given dB quieter
    than the one before (a fade), to `until` or else the end of the last of those notes (notes held over `from` end there; the later
    ones are dropped);
    extra: {track: [(beat, length in beats, MIDI note, velocity)]} notes added to the track (a new track if no such one: its
    instrument by --map, its gain, decay ... by its name);
    fade_in: (seconds, dB) every note is that much quieter at the song's start, less and less to none at `seconds`; or a curve
    [(seconds, dB), ...] (dB < 0 quieter, > 0 louder, linear between the points, the last one's after it); the level register
    follows while a note is held;
    envelope: {track: curve} such a curve for the track's notes instead of fade_in's;
    hold: {track: from seconds} the track's notes from then on without the sample's own decay (D1R 0, DL 0, D2R 0: the level
    holds while keyed; decay= does the fading; a sample whose recording dies away still does);
    window: {track: (from seconds, until seconds)} only the track's notes starting in that time (e.g. with a copy of the track on
    another instrument for the rest);
    trace: a list that gets a dict per note as played (track, times, pitch, instrument, levels, pan, LFO, envelope): what
    tools/midi2fur.py needs to write the same arrangement as a Furnace module."""
    song = smf.read(path)
    div = song["division"]
    maps, transpose, gain, notemap, sweep = maps or {}, transpose or {}, gain or {}, notemap or {}, sweep or {}
    repeat, fm, shift, decay, tremolo, ramp = repeat or {}, fm or {}, shift or {}, decay or {}, tremolo or {}, ramp or {}
    pan, detune, arp, extra = pan or {}, detune or {}, arp or {}, extra or {}
    byname = {tr["name"]: tr for tr in song["tracks"]}
    for name, ns in extra.items():                                                  # added notes (a new track if needed)
        if name not in byname:
            byname[name] = dict(name=name, instrument="", notes=[], programs={}, controls=[], bends=[])
            song["tracks"].append(byname[name])
        ch0 = byname[name]["notes"][0][2] if byname[name]["notes"] else 0
        byname[name]["notes"] = sorted(byname[name]["notes"] + [(int(round(b * div)), int(round((b + ln) * div)), ch0, n, vel)
                                                                for b, ln, n, vel in ns])
    for new, spec in (copies or {}).items():
        of, beats = spec[:2]
        d = int(round(float(beats) * div))
        src_tr = byname[of]
        keep = (lambda t0: smf.seconds(song, t0) < spec[2]) if len(spec) > 2 else (lambda t0: True)
        song["tracks"].append(dict(src_tr, name=new, notes=[(t0 + d, t1 + d, ch, n, vel) for t0, t1, ch, n, vel in src_tr["notes"]
                                                            if keep(t0)],
                                   bends=[(t + d, ch, v) for t, ch, v in src_tr["bends"]]))
    fm_notes = []
    notes = []                                          # (start, end, note, velocity, instrument)
    rep = []
    for tr in song["tracks"]:
        if not tr["notes"] or tr["name"] in drop:
            continue
        ins = pick(tr, maps, ram)
        g = int(round(float(gain.get(tr["name"], 0)) / 0.375))
        bass = not isinstance(ins, dict) and "Bass" in Y.NAMES[ins]
        tp = int(transpose.get(tr["name"], 0))
        ring = int(drum_ring * SR) if not isinstance(ins, dict) and ins == DRUMS else 0
        nmap = notemap.get(tr["name"], {})
        sw = float(sweep.get(tr["name"], 0))
        dk_spec = decay.get(tr["name"], 0)                                          # dB/s, or (dB/s, from seconds)
        dk_rate, dk_from = (dk_spec, 0) if not isinstance(dk_spec, (tuple, list)) else dk_spec
        trem = tremolo.get(tr["name"])
        rp = ramp.get(tr["name"])
        pn = pan.get(tr["name"])
        env_tr = (envelope or {}).get(tr["name"])
        dt = float(detune.get(tr["name"], 0)) / 100
        vmax = max(n[4] for n in tr["notes"])
        src = list(tr["notes"])
        if tr["name"] in (window or {}):
            w0, w1 = window[tr["name"]]
            src = [x for x in src if w0 <= smf.seconds(song, x[0]) < w1]
            if not src:
                continue
        if tr["name"] in arp:                                                       # the arpeggio
            frm, step, offs = arp[tr["name"]][:3]
            fade = arp[tr["name"]][3] if len(arp[tr["name"]]) > 3 else 0
            until = arp[tr["name"]][4] if len(arp[tr["name"]]) > 4 else None
            f0, st = int(round(frm * div)), int(round(step * div))
            over = [x for x in src if x[1] > f0]                                    # held over `from` or later
            if over:
                held = [x for x in over if x[0] < f0]
                first = min(held, key=lambda x: x[3]) if held else over[0]
                a0, end, ch0, n0, v0 = max(f0, first[0]), max(x[1] for x in over), first[2], first[3], first[4]
                if until is not None:
                    end = int(round(until * div))
                src = [(t0, min(t1, f0), ch, n, vel) for t0, t1, ch, n, vel in src if t0 < f0] + [
                    (t, min(t + st, end), ch0, n0 + offs[k % len(offs)], max(1, round(v0 * 10 ** (-fade * k / 20))))
                    for k, t in enumerate(range(a0, end, st))]
        if tr["name"] in repeat:
            bar = div * 4
            first = src[0][0] // bar
            pattern = [x for x in src if x[0] // bar == first]
            src = sorted(src + [(t0 + (b - first) * bar, t1 + (b - first) * bar, ch, n, vel)
                                for b in repeat[tr["name"]] for t0, t1, ch, n, vel in pattern])
        sh = int(round(float(shift.get(tr["name"], 0)) * div))
        assert all(x[0] + sh >= 0 for x in src), "shift: %s would start before the song" % tr["name"]
        rng = bend_range(tr)
        bends = [(int(smf.seconds(song, max(0, t + sh)) * SR), v * rng / 8192) for t, ch, v in tr["bends"]]
        assert not (bends and sw and any(b for t, b in bends)), "%s: pitch bend and --sweep together" % tr["name"]
        for t0, t1, ch, n, vel in src:
            t0, t1 = t0 + sh, t1 + sh
            if quantize:
                q = div * 4 // quantize
                d = t1 - t0
                t0 = round(t0 / q) * q
                t1 = t0 + max(q // 2, d)
            s0 = int(smf.seconds(song, t0) * SR)
            if tr["name"] in fm:
                fm_notes.append((s0, int(smf.seconds(song, t1) * SR), n + tp, FM_TIMBRES[fm[tr["name"]]], g, sw))
                continue
            e0 = max(s0 + ring, int(smf.seconds(song, t1) * SR))
            b0 = next((b for t, b in reversed(bends) if t <= s0), 0.0)       # the bend at the key on, then its changes while held
            bend = [(t, b) for t, b in bends if s0 < t < e0]
            lfo = (trem[1], trem[2], trem[3] if len(trem) > 3 else 0) if trem and s0 >= trem[0] * SR else (None, None, None)
            hd = tr["name"] in (hold or {}) and s0 >= hold[tr["name"]] * SR
            tm = lfo + (pn, hd) if lfo[0] is not None or pn is not None or hd else None   # (LFO, AM, vibrato, panpot, hold)
            gn = g
            if rp and s0 < rp[1] * SR:                                              # the crescendo: from rp[2] dB to none
                k = max(0.0, (s0 / SR - rp[0]) / (rp[1] - rp[0]))
                gn = g + int(round(float(rp[2]) * (1 - k) / 0.375))
            dk = float(dk_rate) if s0 >= dk_from * SR else 0.0
            notes.append((s0, e0, nmap.get(n, n) + tp + dt, min(127, max(1, round(vel * 127 / vmax))), ins, gn, sw, b0, bend, dk, tm,
                          tuple(env_tr) if env_tr else None, tr["name"]))
        rep.append("track %r: %s, transpose %+d, gain %+.1f dB, %d notes" % (
            tr["name"], "FM %s" % fm[tr["name"]] if tr["name"] in fm else ins_name(ins), tp, g * 0.375, len(src)))
    notes.sort(key=lambda x: x[:4] + (x[4]["tone"] if isinstance(x[4], dict) else x[4],) + x[5:7] + (x[12],))   # (RAM: its tone)
    curves = {}
    writes = []
    free_at = [0] * CHANNELS                            # sample time a channel is free from (its note off + 1 frame)
    clamped = 0
    curve0 = [] if not fade_in else fade_in if isinstance(fade_in[0], (tuple, list)) else [(0, -fade_in[1]), (fade_in[0], 0)]

    def fin(t, curve):
        """The fade in (or a track's envelope) at sample time t: attenuation steps (< 0: louder)."""
        t /= SR
        if not curve:
            return 0
        if t >= curve[-1][0]:
            return int(round(-curve[-1][1] / 0.375))
        for (ta, da), (tb, db) in zip(curve, curve[1:]):
            if t < tb:
                return int(round(-(da + (db - da) * (t - ta) / (tb - ta)) / 0.375))
        return 0
    for t0, t1, n, vel, ins, g, sw, b0, bend, dk, tm, env_n, tname in notes:
        cv = list(env_n) if env_n else curve0
        traced = False
        for region in regions(ins, n):
            if tm and tm[0] is not None:                                            # the tremolo: LFO frequency, AM depth, vibrato
                region = region[:9] + (region[9] & 0xC0 | tm[0] << 3 | tm[2],) + region[10:13] + (region[13] & 0xF8 | tm[1],)
            if tm and tm[3] is not None:                                            # the panpot
                region = region[:5] + (tm[3],) + region[6:]
            if tm and tm[4]:                                                        # hold: no decay of its own (AR kept)
                region = region[:10] + (region[10] & 0xF0, 0x00) + region[12:]
            c = min(range(CHANNELS), key=lambda k: (free_at[k] > t0, free_at[k]))
            if free_at[c] > t0:                         # all busy: cut the oldest note one frame before this one
                writes = [w for w in writes if not (w[2] == 0x68 + c and w[0] >= t0 - FRAME and not w[3] & 0x80)]
                writes.append((max(0, int(t0 - FRAME)), 2, 0x68 + c, 0))
            tone = region[2]
            octave, fn = pitch_regs(n + b0, region)
            att = region[7] + att_of(volume) + att_of(vel)
            att = 0x7F - (0x7F - att) * region[8] // 0xFE - boost - g
            clamped += att < 0
            att = max(0, min(0x7E, att))
            pan = region[5] & 15
            a_on = max(0, min(0x7E, att + fin(t0, cv)))
            f_lo = (fn << 1) & 0xFE | tone >> 8
            writes += [(t0, 2, 0x20 + c, f_lo), (t0, 2, 0x08 + c, tone & 255),          # wave number: loads the tone header
                       (t0, 2, 0x68 + c, 0x20 | pan),                                      # LFO reset, pan
                       (t0, 2, 0x38 + c, octave << 4 | fn >> 7), (t0, 2, 0x20 + c, f_lo),
                       (t0, 2, 0x50 + c, a_on << 1 | 1),                                   # level, direct
                       (t0, 2, 0x80 + c, region[9]), (t0, 2, 0x98 + c, region[10]), (t0, 2, 0xB0 + c, region[11]),
                       (t0, 2, 0xC8 + c, region[12]), (t0, 2, 0xE0 + c, region[13]),
                       (t0, 2, 0x68 + c, 0x80 | pan),                                      # key on
                       (t1, 2, 0x68 + c, pan)]                                             # key off: the region's release
            steps = int((t1 - t0) // FRAME) if sw else 0
            for k in range(1, steps + 1):                                          # the glide: a new pitch every frame
                o2, f2 = pitch_regs(n - sw * k / steps, region)
                tk = int(t0 + k * FRAME) - 1
                writes += [(tk, 2, 0x38 + c, o2 << 4 | f2 >> 7), (tk, 2, 0x20 + c, (f2 << 1) & 0xFE | tone >> 8)]
            last = {}
            for tb, b in bend:                                                      # the bend: the last value of each frame
                last[int((tb - t0) // FRAME)] = (tb, b)
            for tb, b in last.values():
                o2, f2 = pitch_regs(n + b, region)
                writes += [(tb, 2, 0x38 + c, o2 << 4 | f2 >> 7), (tb, 2, 0x20 + c, (f2 << 1) & 0xFE | tone >> 8)]
            now = a_on
            levels = [(t0, a_on)]
            for k in range(1, int((t1 - t0) // FRAME)):                             # the decay / fade in: one step when due, at a frame
                a2 = max(0, min(0x7E, att + int(dk * k * FRAME / SR / 0.375) + fin(t0 + k * FRAME, cv)))
                if a2 != now:
                    now = a2
                    writes.append((int(t0 + k * FRAME) - 1, 2, 0x50 + c, a2 << 1 | 1))
                    levels.append((int(t0 + k * FRAME) - 1, a2))
            if trace is not None and not traced:                                    # (a ROM instrument's first layer only)
                traced = True
                pitches = [(int(t0 + k * FRAME) - 1, n - sw * k / steps) for k in range(1, steps + 1)] if sw else []
                pitches += [(tb, n + b) for tb, b in last.values()]
                trace.append(dict(track=tname, t0=t0, t1=t1, note=n + b0, pitches=sorted(pitches), levels=levels,
                                  ins=ins["name"] if isinstance(ins, dict) else ins, pan=pan, lfo=region[9], am=region[13] & 7,
                                  env=region[10:13]))
            free_at[c] = t1 + FRAME
    writes += fm_writes(fm_notes)
    writes.sort(key=lambda w: w[0])                     # stable: the order of each note's writes stays
    total = int(smf.seconds(song, song["length"]) * SR)
    if clamped:
        rep.append("%d note(s) at the chip's full level: less gain than asked" % clamped)
    return writes, total, rep


def parse_map(s):
    return {k: v for k, v in (x.split("=", 1) for x in s.split(",") if x)} if s else {}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mid")
    ap.add_argument("--map", default="")
    ap.add_argument("--transpose", default="")
    ap.add_argument("--quantize", type=int, default=0)
    ap.add_argument("--gain", default="", help="track=dB,...")
    ap.add_argument("--drop", default="", help="track,... left out")
    ap.add_argument("--notes", default="", help="track=from:to/from:to,... e.g. bateria=38:36/39:38")
    ap.add_argument("--sweep", default="", help="track=semitones,... (glide down while held)")
    ap.add_argument("--shift", default="", help="track=beats,... (< 0: earlier)")
    a = ap.parse_args()
    w, total, rep = convert(a.mid, parse_map(a.map), parse_map(a.transpose), a.quantize, gain=parse_map(a.gain),
                            drop=[x for x in a.drop.split(",") if x],
                            notemap={k: dict(map(int, p.split(":")) for p in v.split("/")) for k, v in parse_map(a.notes).items()},
                            sweep=parse_map(a.sweep), shift=parse_map(a.shift))
    print("\n".join(rep))
    print("%d wave writes, %.2f s" % (len(w), total / SR))


if __name__ == "__main__":
    main()

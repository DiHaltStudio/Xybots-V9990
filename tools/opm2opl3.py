#!/usr/bin/env python3
"""YM2151 (OPM) VGM/VGZ -> writes for the FM part of the Moonsound (YMF278B: an OPL3, 4-operator channels) (feature/music, ADR-027).

  opm2opl3.py <song.vgz> <out.vgm> [--fs 49516]     a YMF278B VGM (FM only) to listen to / render with vgm2wav

The arcade FM timbres are translated register by register instead of being replaced by ROM (GM) instruments. Every OPM channel in use
gets a 4-operator OPL3 channel (6 at most); after each group of OPM writes the OPL3 registers that changed are written.

  algorithm  OPM CON 0-3 (chains)  -> OPL3 FM-FM (op1..op4 = M1 C1 M2 C2; CON 1-3 approximated as a chain)
             OPM CON 4 (2 x 2)     -> OPL3 FM-AM ... (M1->C1) + (M2->C2), exact
             OPM CON 5-7           -> OPL3 AM-AM: M2 + (M1->C1) + C2 (CON 6 exact but the feedback moves to M2)
  operators  MUL x DT2 factor -> the nearest OPL3 multiplier (0.5, 1-10, 12, 15), TL (clamped to 63: 0.75 dB steps on both), AR/D1R halved (OPM rates count twice as
             fine), D1L = SL, KS >= 2 -> KSR, AMS-EN -> AM, PMS -> VIB; DT1 and the OPM LFO shape are dropped
  envelope   OPL3 has no second decay (D2R): D2R = 0 -> sustained (EGT 1); else EGT 0 and RR := D2R/2 while the key is on (the
             level keeps falling after D1L), RR := the OPM RR at key off (the release)
  pitch      the OPM key code + fraction as a frequency, then F-number / block for the OPL3 sample rate --fs
  stereo     OPM R/L bits -> OPL3 CHB / CHA

Returns / writes [(sample time 44.1 kHz, array 0/1, register, value)]; the game's stream (tools/opl4_stream.py) takes the same list.
"""
import argparse
import math
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import opm_analyze as O  # noqa: E402

MULT_VALUE = {0: 0.5, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8, 9: 9, 10: 10, 12: 12, 15: 15}   # OPL3 MULT code -> factor
DT2 = [1.0, 1.41, 1.57, 1.73]                                           # OPM DT2: the operator frequency times this


def mult(mul, dt2):
    """OPM MUL (0 = 0.5) and DT2 -> the OPL3 MULT code of the nearest factor."""
    f = (mul or 0.5) * DT2[dt2]
    return min(MULT_VALUE, key=lambda c: abs(math.log(MULT_VALUE[c] / f)))
SLOT = [0x00, 0x01, 0x02, 0x08, 0x09, 0x0A, 0x10, 0x11, 0x12]           # operator offset of the first operator of OPL3 channel 0-8
M1, M2, C1, C2 = 0, 1, 2, 3                                             # OPM operator index (register order)
# OPM CON -> (OPL3 CNT of the first pair, CNT of the second pair, OPM operators as op1..op4)
ALG = {0: (0, 0, (M1, C1, M2, C2)), 1: (0, 0, (M1, C1, M2, C2)), 2: (0, 0, (M1, C1, M2, C2)), 3: (0, 0, (M1, C1, M2, C2)),
       4: (0, 1, (M1, C1, M2, C2)), 5: (1, 1, (M2, M1, C1, C2)), 6: (1, 1, (M2, M1, C1, C2)), 7: (1, 1, (M1, M2, C1, C2))}


def rate(r5):
    """OPM 5-bit rate (AR, D1R, D2R) -> OPL3 4-bit rate (half; never 0 when the OPM rate is not 0)."""
    return 0 if r5 == 0 else max(1, min(15, (r5 + 1) // 2))


def opm_freq(kc, kf, clock):
    midi = O.kc_to_midi(kc, kf)
    if midi is None:
        return None
    return 440.0 * 2 ** ((midi - 69) / 12) * clock / 3579545


def fnum_block(f, fs):
    """Frequency -> (F-number 10 bits, block 0-7): f = fnum * fs / 2^(20 - block)."""
    for block in range(8):
        fn = round(f * 2 ** (20 - block) / fs)
        if fn < 1024:
            return max(0, fn), block
    return 1023, 7


class Conv:
    def __init__(self, clock, fs, two_op=(), atten=0.0):
        self.clock, self.fs = clock, fs
        self.atten = int(round(atten / 0.75))  # extra TL steps on the carriers (the song quieter, e.g. under the voices)
        self.opm = [0] * 256
        self.key = [False] * 8
        self.two_op = set(two_op)           # OPM channels played on 2-operator OPL3 channels (6, 7, 8 of each array)
        self.slot = {}                      # OPM channel -> 4-op channel 0-5 (or 2-op channel 0-5 for the two_op ones)
        self.slot2 = {}
        self.out = {}                       # (array, reg) -> value written
        self.writes = []

    def w(self, t, a, r, v):
        if self.out.get((a, r)) != v:
            self.out[(a, r)] = v
            self.writes.append((t, a, r, v))

    def chan(self, ch):
        if ch in self.two_op:
            if ch not in self.slot2:
                assert len(self.slot2) < 6, "more than 6 OPM channels on 2-operator OPL3 channels"
                self.slot2[ch] = len(self.slot2)
            return self.slot2[ch]
        if ch not in self.slot:
            assert len(self.slot) < 6, "more than 6 OPM channels: not enough 4-operator OPL3 channels (two_op= for the others)"
            self.slot[ch] = len(self.slot)
        return self.slot[ch]

    def update(self, t, ch):
        """Write the OPL3 registers of OPM channel ch from the OPM state."""
        j = self.chan(ch)
        arr, c = j // 3, j % 3
        r = self.opm
        rl_fb_con = r[0x20 + ch]
        con, fb = rl_fb_con & 7, (rl_fb_con >> 3) & 7
        pms, ams = (r[0x38 + ch] >> 4) & 7, r[0x38 + ch] & 3
        cnt1, cnt2, ops = ALG[con]
        on = self.key[ch]
        places = [(c, 0), (c, 1), (c + 3, 0), (c + 3, 1)]               # (OPL3 channel, operator 0/1 of it)
        if ch in self.two_op:                                           # 2 operators: M1 (feedback) -> the last carrier; CON 7 all carriers
            c = 6 + j % 3
            places = [(c, 0), (c, 1)]
            ops = (M1, C2)
            cnt1 = 1 if con == 7 else 0
        if ch in self.two_op:
            carriers = {1} if cnt1 == 0 else {0, 1}
        else:
            carriers = {(0, 0): {3}, (0, 1): {1, 3}, (1, 0): {0, 3}, (1, 1): {0, 2, 3}}[(cnt1, cnt2)]
        for k, op in enumerate(ops):
            base = lambda reg: r[reg + 8 * op + ch]
            dt_mul, tl, ks_ar, ame_d1r, dt2_d2r, d1l_rr = (base(x) for x in (0x40, 0x60, 0x80, 0xA0, 0xC0, 0xE0))
            d2r = dt2_d2r & 31
            egt = 1 if d2r == 0 else 0
            rr = d1l_rr & 15
            if on and d2r:
                rr = rate(d2r)                                          # second decay while the key is on
            och, oo = places[k]
            off = SLOT[och] + 3 * oo
            am = 1 if (ame_d1r & 0x80) and ams else 0
            vib = 1 if pms else 0
            ksr = 1 if (ks_ar >> 6) >= 2 else 0
            self.w(t, arr, 0x20 + off, am << 7 | vib << 6 | egt << 5 | ksr << 4 | mult(dt_mul & 15, dt2_d2r >> 6))
            self.w(t, arr, 0x40 + off, min(63, (tl & 127) + (self.atten if k in carriers else 0)))
            self.w(t, arr, 0x60 + off, rate(ks_ar & 31) << 4 | rate(ame_d1r & 31))
            self.w(t, arr, 0x80 + off, (d1l_rr >> 4) << 4 | rr)
            self.w(t, arr, 0xE0 + off, 0)                               # sine
        pan = ((rl_fb_con >> 6) & 1) << 4 | ((rl_fb_con >> 7) & 1) << 5  # L -> CHA, R -> CHB
        self.w(t, arr, 0xC0 + c, pan | fb << 1 | cnt1)
        if ch not in self.two_op:
            self.w(t, arr, 0xC0 + c + 3, pan | cnt2)
        f = opm_freq(r[0x28 + ch], r[0x30 + ch], self.clock)
        fn, block = fnum_block(f, self.fs) if f else (0, 0)
        self.w(t, arr, 0xA0 + c, fn & 255)
        self.w(t, arr, 0xB0 + c, (0x20 if on else 0) | block << 2 | fn >> 8)

    def run(self, ev):
        touched = set()
        last_t = None
        for t, reg, v in ev + [(None, None, None)]:
            if t != last_t and touched:
                for ch in sorted(touched):
                    self.update(last_t, ch)
                touched = set()
            if t is None:
                break
            last_t = t
            self.opm[reg] = v
            if reg == 0x08:
                ch = v & 7
                self.key[ch] = bool((v >> 3) & 15)
                touched.add(ch)
            elif 0x20 <= reg < 0x40:
                touched.add(reg & 7)
            elif reg >= 0x40:
                touched.add(reg & 7)
        return self.writes


def convert(path, fs=33868800 / 684, also=(), two_op=(), atten=0.0):
    """also: more YM2151 VGMs played at the same time from the start (e.g. a jingle), on OPM channels the song does not use.
    two_op: OPM channels for 2-operator OPL3 channels (a song with more than 6 channels: e.g. the echo channels of the intro).
    atten: dB less on every carrier (the song under voices).
    path: a YM2151 VGM/VGZ, or (events [(sample time, reg, value)], length in samples, clock) as tools/midi2opm.py makes them."""
    if isinstance(path, tuple):
        ev, total, clock = path[0], path[1], path[2]
    else:
        d, start, clock = O.load(path)
        ev, total = O.events(d, start)
    for other in also:
        d2, s2, c2 = O.load(other)
        ev2, t2 = O.events(d2, s2)
        used1 = {v & 7 for t, r, v in ev if r == 0x08 and (v >> 3) & 15}
        used2 = {v & 7 for t, r, v in ev2 if r == 0x08 and (v >> 3) & 15}
        assert not used1 & used2, "%s uses OPM channels of the song: %s" % (other, sorted(used1 & used2))
        ev2 = [e for e in ev2 if e[1] >= 0x20 and (e[1] & 7) in used2 or e[1] == 0x08 and (e[2] & 7) in used2]
        ev = sorted(ev + ev2, key=lambda e: e[0])           # stable: the song's writes first at equal times
        total = max(total, t2)
    cv = Conv(clock, fs, two_op, atten)
    # channels that ever key on (only those get an OPL3 channel)
    used = sorted({v & 7 for t, r, v in ev if r == 0x08 and (v >> 3) & 15})
    for ch in used:
        cv.chan(ch)
    ev = [e for e in ev if e[1] == 0x08 and (e[2] & 7) in used or e[1] != 0x08 and (e[1] < 0x20 or (e[1] & 7) in used)]
    mask = 0
    for ch, j in cv.slot.items():
        mask |= 1 << j                                                  # 4-op enable: bits 0-2 array 0, 3-5 array 1
    head = [(0, 1, 0x05, 0x03), (0, 1, 0x04, mask), (0, 0, 0xBD, 0x00)]   # NEW/NEW2, 4-operator channels, no rhythm
    return head + cv.run(ev), total, cv.slot


def write_vgm(path, writes, total):
    body = bytearray()
    t = 0
    for wt, a, r, v in writes:
        dt = wt - t
        while dt > 0:
            n = min(dt, 65535)
            body += b"\x61" + struct.pack("<H", n)
            dt -= n
        t = wt
        body += bytes([0xD0, a, r, v])
    if total > t:
        dt = total - t
        while dt > 0:
            n = min(dt, 65535)
            body += b"\x61" + struct.pack("<H", n)
            dt -= n
    body += b"\x66"
    hdr = bytearray(0x100)
    hdr[0:4] = b"Vgm "
    struct.pack_into("<I", hdr, 0x08, 0x171)
    struct.pack_into("<I", hdr, 0x18, total)
    struct.pack_into("<I", hdr, 0x34, 0x100 - 0x34)
    struct.pack_into("<I", hdr, 0x60, 33868800)                          # YMF278B
    data = hdr + body
    struct.pack_into("<I", data, 0x04, len(data) - 4)
    pathlib.Path(path).write_bytes(bytes(data))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("vgm")
    ap.add_argument("out")
    ap.add_argument("--two-op", default="", help="OPM channels on 2-operator channels, e.g. 5,6")
    ap.add_argument("--fs", type=float, default=33868800 / 684, help="FM sample rate of the F-number formula (YMF278B: 33.8688 MHz / 684 = 49516 Hz)")
    a = ap.parse_args()
    writes, total, slot = convert(a.vgm, a.fs, two_op=[int(x) for x in a.two_op.split(',') if x])
    write_vgm(a.out, writes, total)
    print("%s: %d FM writes, %.1f s, OPM channels -> 4-op channels %s" % (a.out, len(writes), total / 44100, slot))


if __name__ == "__main__":
    main()

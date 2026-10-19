#!/usr/bin/env python3
"""Voice recording (any WAV, e.g. MAME -wavwrite cut in Audacity) -> 8-bit unsigned mono 22050 Hz (or --rate 11025 / 7350) WAV for the Moonsound (ADR-027).

  voice_prep.py <in.wav> <out_22k.wav> [--drive 1.5] [--rate 22050] [--trim A:B] [--fade 0.3] [--peak P]

ffmpeg resamples (low-pass 10 kHz); the voice is peak-normalised and pushed through a soft limiter (tanh, --drive = gain into it):
louder against the music without hard clipping. --drive 1 = plain peak normalisation. --trim A:B keeps seconds A-B of the input,
--fade S fades the last S seconds out (after --trim: a cut in a reverb tail). --peak P scales by 1 / P (P = a peak of the input, full
scale 1) instead of the file's own peak: the same P for a set of sounds keeps their levels relative to one another (the effects, ADR-044)."""
import argparse
import math
import subprocess
import wave

import numpy as np


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inp")
    ap.add_argument("out")
    ap.add_argument("--drive", type=float, default=1.5)
    ap.add_argument("--rate", type=int, default=22050, choices=(7350, 11025, 22050))
    ap.add_argument("--trim", default="")
    ap.add_argument("--fade", type=float, default=0)
    ap.add_argument("--peak", type=float, default=0)
    a = ap.parse_args()
    raw = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", a.inp, "-af", "lowpass=f=%d" % (a.rate * 10 // 22),
                          "-ar", str(a.rate), "-ac", "1", "-f", "f32le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, "<f4").astype(float)
    if a.trim:
        t0, t1 = (float(v) for v in a.trim.split(":"))
        x = x[int(t0 * a.rate):int(t1 * a.rate)].copy()
    if a.fade:
        n = int(a.fade * a.rate)
        x[-n:] *= np.linspace(1, 0, n)
    x /= a.peak or max(1e-9, np.abs(x).max())
    y = np.tanh(a.drive * x) / math.tanh(a.drive) * 0.98
    b = np.clip(np.round(y * 127) + 128, 1, 255).astype(np.uint8)
    with wave.open(a.out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(a.rate)
        w.writeframes(b.tobytes())
    rms = np.sqrt(((b.astype(float) - 128) ** 2).mean())
    print("%s: %.2f s, rms %.1f dBFS" % (a.out, len(b) / a.rate, 20 * math.log10(rms / 128)))


if __name__ == "__main__":
    main()

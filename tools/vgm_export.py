#!/usr/bin/env python3
"""The logo song as a VGM file for the YMF278B (OPL4, Moonsound) (ADR-049): the same register writes the game's player plays (the
logo's tools/midi2wave.py writes, at their 44100 Hz times, not rounded to the game's 50 Hz frames), after the game's set-up (FM
register 105h := 03h: NEW2; wave register 02h := 10h: the RAM's tone headers at 200000h; F8h / F9h := 00h: FM and wave mix at full
level), with the Moonsound RAM it needs as a data block (type 87h: YMF278B RAM image: the tone headers from 200000h and the logo's
RAM instruments). The YRW801 ROM is not in the file: a player brings its own (libvgm / VGMPlay: yrw801.rom).

VGM 1.71: header 100h bytes (YMF278B clock 33868800 at 60h), data from 100h: 67h 66h 87h <size> <RAM size> <start> <data>,
D0h pp aa dd (port 0 / 1 FM arrays, 2 wave), 61h nnnn waits, 66h end; a GD3 tag.
"""
import struct

CLOCK = 33868800


def gd3(title, author, system="MSX + Moonsound (OPL4)", notes=""):
    fields = [title, "", "", "", system, "", author, "", "2026", "tools/vgm_export.py", notes]
    data = b"".join(f.encode("utf-16-le") + b"\0\0" for f in fields)
    return b"Gd3 " + struct.pack("<II", 0x100, len(data)) + data


def export(writes, total, ram, title, author="DiHalt", ram_size=0x200000):
    """writes [(sample time, port, register, value)], total samples, ram: bytes from 200000h (the RAM image). -> VGM bytes."""
    body = bytearray()
    blk = struct.pack("<II", ram_size, 0) + bytes(ram)
    body += b"\x67\x66\x87" + struct.pack("<I", len(blk)) + blk
    for port, reg, val in ((1, 0x05, 0x03), (2, 0x02, 0x10), (2, 0xF8, 0x00), (2, 0xF9, 0x00)):
        body += bytes([0xD0, port, reg, val])
    now = 0
    for t, port, reg, val in sorted(writes, key=lambda w: w[0]):
        t = min(int(t), total)
        while t > now:
            n = min(65535, t - now)
            body += b"\x61" + struct.pack("<H", n)
            now += n
        body += bytes([0xD0, port, reg & 0xFF, val & 0xFF])
    while total > now:
        n = min(65535, total - now)
        body += b"\x61" + struct.pack("<H", n)
        now += n
    body += b"\x66"
    tag = gd3(title, author)
    hdr = bytearray(0x100)
    hdr[0:4] = b"Vgm "
    struct.pack_into("<I", hdr, 0x08, 0x171)
    struct.pack_into("<I", hdr, 0x18, total)
    struct.pack_into("<I", hdr, 0x34, 0x100 - 0x34)
    struct.pack_into("<I", hdr, 0x60, CLOCK)
    struct.pack_into("<I", hdr, 0x14, 0x100 + len(body) - 0x14)
    out = bytes(hdr) + bytes(body) + tag
    out = bytearray(out)
    struct.pack_into("<I", out, 0x04, len(out) - 4)
    return bytes(out)

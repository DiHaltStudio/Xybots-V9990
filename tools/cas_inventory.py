#!/usr/bin/env python3
"""Inventory the blocks of an MSX .CAS image (Phase 0 evidence tool).

Usage: cas_inventory.py MSX/original/XYBOTS.CAS [--extract DIR]

Reports, for every CAS block: file offset, length, kind (ASCII/BIN/BASIC
file header or raw data block) and a SHA-256 prefix. For a BIN header the
following data block is decoded as BLOAD start/end/exec. With --extract the
raw block bodies are written to DIR (generated output; keep under MSX/build/).
Read-only with respect to the CAS file.
"""
import argparse
import hashlib
import pathlib

HEADER = bytes([0x1F, 0xA6, 0xDE, 0xBA, 0xCC, 0x13, 0x7D, 0x74])
TAGS = {b"\xd0" * 10: "BIN", b"\xd3" * 10: "BASIC", b"\xea" * 10: "ASCII"}


def split_blocks(data):
    """CAS blocks are 8-byte aligned and each starts with HEADER."""
    pos = [i for i in range(0, len(data) - 7, 8) if data[i:i + 8] == HEADER]
    pos.append(len(data))
    return [(pos[i], data[pos[i] + 8:pos[i + 1]]) for i in range(len(pos) - 1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cas")
    ap.add_argument("--extract", metavar="DIR")
    args = ap.parse_args()

    data = pathlib.Path(args.cas).read_bytes()
    print(f"{args.cas}: {len(data)} bytes, sha256 {hashlib.sha256(data).hexdigest()}")
    out = pathlib.Path(args.extract) if args.extract else None
    if out:
        out.mkdir(parents=True, exist_ok=True)

    for n, (off, body) in enumerate(split_blocks(data)):
        kind = TAGS.get(body[:10], "DATA")
        sha = hashlib.sha256(body).hexdigest()[:12]
        note = ""
        if kind != "DATA":
            note = "name=%r" % body[10:16]
        elif n == 1 and len(body) >= 6:
            s, e, x = (body[i] | body[i + 1] << 8 for i in (0, 2, 4))
            note = "BLOAD start=%04X end=%04X exec=%04X" % (s, e, x)
        print(f"#{n} off=0x{off:05X} len={len(body):6d} {kind:5s} sha256={sha} {note}")
        if out:
            (out / f"block{n}_{kind.lower()}.bin").write_bytes(body)


if __name__ == "__main__":
    main()

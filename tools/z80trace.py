#!/usr/bin/env python3
"""Recursive-descent code tracer for the XYBOTS RAM image.

Usage: z80trace.py IMAGE.bin OUT.json [--seed ADDR ...] [--extra FILE]

IMAGE is a 64 KiB memory image (loader area + game as loaded from tape).
Follows JP/JR/DJNZ/CALL/RST edges from the seeds, never linearly sweeps.
--extra FILE: text file with one hex address per line (or "addr # comment")
adding entry points found from other evidence (tables, dynamic traces).

The JSON result holds: insn (sorted starts), lengths, targets of calls/jumps,
indirect jump sites (JP (HL)/(IX)/(IY)) and instructions that overlap another
decoded instruction (code/data or operand-entry overlap to be reviewed).
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import z80  # noqa: E402


def trace(mem, seeds):
    insn = {}
    calls, jumps, indirect = set(), set(), []
    work = list(seeds)
    seen_entry = set(seeds)
    while work:
        a = work.pop()
        while True:
            a &= 0xFFFF
            if a in insn:
                break
            i = z80.decode(mem, a)
            insn[a] = i
            nxt = a + i.length
            k, t = i.kind, i.target
            if k == "seq" or k == "halt" or k == "retc":
                a = nxt
                continue
            if k == "call":
                calls.add(t)
                if t not in seen_entry:
                    seen_entry.add(t)
                    work.append(t)
                a = nxt
                continue
            if k == "jc":
                jumps.add(t)
                if t not in seen_entry:
                    seen_entry.add(t)
                    work.append(t)
                a = nxt
                continue
            if k == "jp":
                if t is None:
                    indirect.append(a)
                else:
                    jumps.add(t)
                    if t not in seen_entry:
                        seen_entry.add(t)
                        work.append(t)
                break
            break  # ret / reti / retn
    return insn, calls, jumps, indirect


def overlaps(insn):
    """Instructions whose bytes intersect the bytes of another decoded instruction."""
    owner = {}
    out = []
    for a in sorted(insn):
        for b in range(a, a + insn[a].length):
            if b in owner and owner[b] != a:
                out.append((a, owner[b]))
                break
            owner.setdefault(b, a)
    return out


def load_extra(path):
    r = []
    for line in pathlib.Path(path).read_text().splitlines():
        line = line.split("#")[0].strip()
        if line:
            r.append(int(line, 16))
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("out")
    ap.add_argument("--seed", action="append", default=[], help="hex address")
    ap.add_argument("--extra")
    args = ap.parse_args()
    mem = pathlib.Path(args.image).read_bytes()
    assert len(mem) == 0x10000
    seeds = [int(s, 16) for s in args.seed] or [0x0300]
    if args.extra:
        seeds += load_extra(args.extra)
    insn, calls, jumps, indirect = trace(mem, seeds)
    ov = overlaps(insn)
    covered = sum(i.length for i in insn.values())
    res = {
        "seeds": seeds,
        "instructions": len(insn),
        "bytes": covered,
        "starts": sorted(insn),
        "calls": sorted(calls),
        "jumps": sorted(jumps),
        "indirect_sites": sorted(indirect),
        "overlaps": ov,
    }
    pathlib.Path(args.out).write_text(json.dumps(res))
    print("seeds:", " ".join("%04X" % s for s in seeds))
    print("instructions: %d, code bytes: %d (%.1f%% of 64K)" % (len(insn), covered, covered / 655.36))
    print("call targets: %d, jump targets: %d" % (len(calls), len(jumps)))
    print("indirect jump sites: %d: %s" % (len(indirect), " ".join("%04X" % a for a in sorted(indirect))))
    print("overlapping instruction pairs: %d" % len(ov))
    for a, b in ov[:20]:
        print("  %04X overlaps %04X" % (a, b))


if __name__ == "__main__":
    main()

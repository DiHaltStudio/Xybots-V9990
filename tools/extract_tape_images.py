#!/usr/bin/env python3
"""Extract the runtime load images of XYBOTS.CAS (Phase 0/1 evidence tool).

The tape loader (CAS block 1, BLOAD BB80h..BE80h) reads five more tape blocks
through the BIOS TAPIN routine. Each tape block on the CAS is:

    [FFh sync] [DE data bytes] [checksum] [zero padding to a multiple of 8]

where checksum = XOR of the sync byte and all data bytes (so the total XOR is 0).
Load map, taken from the loader routine at 0093h (see MSX/doc/memory-map.md):

    block 2: 1B00h bytes -> 4000h  ZX-Spectrum-format loading screen (temporary)
    block 3: 3D00h bytes -> 0300h
    block 4: 4000h bytes -> 4000h
    block 5: 4000h bytes -> 8000h
    block 6: 3FFFh bytes -> C000h  (FFFFh is never loaded)
    then JP 0300h

Outputs (generated, keep under MSX/build/):
    loader.bin          the 0300h-byte loader image (BB80h at load, runs at 0000h after LDIR)
    screen.bin          block 2 payload
    game_0300_FFFE.bin  blocks 3..6 concatenated, i.e. the RAM image 0300h..FFFEh
    ram_after_load.bin  64 KiB: loader image at 0000h-02FFh + game image (FFFFh = 00h); input of the
                        tracing tools (memory as it is right after `JP 0300h`)
"""
import argparse
import hashlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from cas_inventory import split_blocks  # noqa: E402

# (cas block index, load address, length)
TAPE_BLOCKS = [
    (2, 0x4000, 0x1B00),
    (3, 0x0300, 0x3D00),
    (4, 0x4000, 0x4000),
    (5, 0x8000, 0x4000),
    (6, 0xC000, 0x3FFF),
]


def decode_block(body, length):
    """Return the payload of one tape block after checking sync, size and XOR."""
    sync, payload, csum = body[0], body[1:1 + length], body[1 + length]
    if sync != 0xFF:
        raise ValueError("bad sync byte %02X" % sync)
    x = sync
    for v in payload:
        x ^= v
    if x != csum:
        raise ValueError("checksum mismatch: computed %02X, tape %02X" % (x, csum))
    if any(body[2 + length:]):
        raise ValueError("non-zero padding")
    return payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cas")
    ap.add_argument("outdir")
    args = ap.parse_args()

    blocks = split_blocks(pathlib.Path(args.cas).read_bytes())
    out = pathlib.Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    loader = blocks[1][1]
    start, end, execa = (loader[i] | loader[i + 1] << 8 for i in (0, 2, 4))
    assert (start, end, execa) == (0xBB80, 0xBE80, 0xBB80)
    (out / "loader.bin").write_bytes(loader[6:6 + 0x300])

    image = bytearray(0x10000)
    covered = bytearray(0x10000)
    for idx, addr, length in TAPE_BLOCKS:
        payload = decode_block(blocks[idx][1], length)
        print("block %d -> %04X..%04X  %5d bytes  sha256 %s" % (
            idx, addr, addr + length - 1, length, hashlib.sha256(payload).hexdigest()[:16]))
        if idx == 2:
            (out / "screen.bin").write_bytes(payload)
            continue  # temporary: overwritten by block 4 at 4000h
        image[addr:addr + length] = payload
        for a in range(addr, addr + length):
            assert not covered[a], "overlap at %04X" % a
            covered[a] = 1
    assert all(covered[0x0300:0xFFFF]), "gap in 0300..FFFE"
    final = bytes(image[0x0300:0xFFFF])
    (out / "game_0300_FFFE.bin").write_bytes(final)
    ram = bytearray(0x10000)
    ram[0:0x300] = (out / "loader.bin").read_bytes()
    ram[0x0300:0xFFFF] = final
    (out / "ram_after_load.bin").write_bytes(bytes(ram))
    print("game image 0300..FFFE: %d bytes sha256 %s" % (len(final), hashlib.sha256(final).hexdigest()))


if __name__ == "__main__":
    main()

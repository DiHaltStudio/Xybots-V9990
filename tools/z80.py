"""Table-driven Z80 instruction decoder used by the reconstruction tools.

decode(mem, pc) -> Insn(addr, length, text, kind, target)
  kind:   'seq'   falls through
          'jp'    unconditional jump (target may be None for JP (HL)/(IX)/(IY))
          'jc'    conditional jump/JR/DJNZ (falls through and may branch)
          'call'  CALL nn / CALL cc,nn / RST (falls through, callee = target)
          'ret'   RET / RETI / RETN (no fall through)
          'retc'  RET cc (falls through)
          'halt'  HALT (falls through; the interrupt resumes)
  target: absolute address or None
Text uses lowercase mnemonics and 0xNN / 0xNNNN literals.
Undocumented DD/FD prefixes on non-indexed opcodes decode as the plain
instruction preceded by a 1-byte prefix (text 'db 0xdd' style is NOT used):
the prefix is reported as a separate 1-byte 'nop'-like instruction.
"""
from collections import namedtuple

Insn = namedtuple("Insn", "addr length text kind target")

R8 = ["b", "c", "d", "e", "h", "l", "(hl)", "a"]
RP = ["bc", "de", "hl", "sp"]
RP2 = ["bc", "de", "hl", "af"]
CC = ["nz", "z", "nc", "c", "po", "pe", "p", "m"]
ALU = ["add a,", "adc a,", "sub ", "sbc a,", "and ", "xor ", "or ", "cp "]
ROT = ["rlc", "rrc", "rl", "rr", "sla", "sra", "sll", "srl"]


def h8(v):
    return "0x%02x" % v


def h16(v):
    return "0x%04x" % v


def s8(v):
    return v - 256 if v & 0x80 else v


def decode(mem, pc):
    def b(o):
        return mem[(pc + o) & 0xFFFF]

    def w(o):
        return b(o) | b(o + 1) << 8

    op = b(0)
    if op == 0xCB:
        return _cb(mem, pc, None)
    if op == 0xED:
        return _ed(mem, pc)
    if op in (0xDD, 0xFD):
        return _idx(mem, pc, "ix" if op == 0xDD else "iy")
    x, y, z = op >> 6, (op >> 3) & 7, op & 7
    p, q = y >> 1, y & 1

    def I(n, t, k="seq", tg=None):
        return Insn(pc, n, t, k, tg)

    if x == 0:
        if z == 0:
            if y == 0:
                return I(1, "nop")
            if y == 1:
                return I(1, "ex af,af'")
            t = (pc + 2 + s8(b(1))) & 0xFFFF
            if y == 2:
                return I(2, "djnz " + h16(t), "jc", t)
            if y == 3:
                return I(2, "jr " + h16(t), "jp", t)
            return I(2, "jr %s,%s" % (CC[y - 4], h16(t)), "jc", t)
        if z == 1:
            if q == 0:
                return I(3, "ld %s,%s" % (RP[p], h16(w(1))))
            return I(1, "add hl,%s" % RP[p])
        if z == 2:
            t = ["ld (bc),a", "ld a,(bc)", "ld (de),a", "ld a,(de)"]
            if p < 2:
                return I(1, t[p * 2 + q])
            if p == 2:
                return I(3, ("ld (%s),hl" if q == 0 else "ld hl,(%s)") % h16(w(1)))
            return I(3, ("ld (%s),a" if q == 0 else "ld a,(%s)") % h16(w(1)))
        if z == 3:
            return I(1, ("inc " if q == 0 else "dec ") + RP[p])
        if z == 4:
            return I(1, "inc " + R8[y])
        if z == 5:
            return I(1, "dec " + R8[y])
        if z == 6:
            return I(2, "ld %s,%s" % (R8[y], h8(b(1))))
        return I(1, ["rlca", "rrca", "rla", "rra", "daa", "cpl", "scf", "ccf"][y])
    if x == 1:
        if op == 0x76:
            return I(1, "halt", "halt")
        return I(1, "ld %s,%s" % (R8[y], R8[z]))
    if x == 2:
        return I(1, ALU[y] + R8[z])
    # x == 3
    if z == 0:
        return I(1, "ret " + CC[y], "retc")
    if z == 1:
        if q == 0:
            return I(1, "pop " + RP2[p])
        return [I(1, "ret", "ret"), I(1, "exx"), I(1, "jp (hl)", "jp", None),
                I(1, "ld sp,hl")][p]
    if z == 2:
        t = w(1)
        return I(3, "jp %s,%s" % (CC[y], h16(t)), "jc", t)
    if z == 3:
        if y == 0:
            t = w(1)
            return I(3, "jp " + h16(t), "jp", t)
        if y == 2:
            return I(2, "out (%s),a" % h8(b(1)))
        if y == 3:
            return I(2, "in a,(%s)" % h8(b(1)))
        return I(1, ["", "", "", "", "ex (sp),hl", "ex de,hl", "di", "ei"][y])
    if z == 4:
        t = w(1)
        return I(3, "call %s,%s" % (CC[y], h16(t)), "call", t)
    if z == 5:
        if q == 0:
            return I(1, "push " + RP2[p])
        t = w(1)
        return I(3, "call " + h16(t), "call", t)
    if z == 6:
        return I(2, ALU[y] + h8(b(1)))
    return I(1, "rst " + h8(y * 8), "call", y * 8)


def _cb(mem, pc, idx):
    """CB-prefixed; idx=(name, disp) for DDCB/FDCB (opcode after displacement)."""
    if idx is None:
        op, n, reg = mem[(pc + 1) & 0xFFFF], 2, None
    else:
        op, n = mem[(pc + 3) & 0xFFFF], 4
    x, y, z = op >> 6, (op >> 3) & 7, op & 7
    tgt = R8[z] if idx is None else "(%s%+d)" % (idx[0], s8(idx[1]))
    if idx is not None and z != 6:
        # undocumented: result also copied to register z
        extra = "," + R8[z]
    else:
        extra = ""
    if x == 0:
        t = "%s %s%s" % (ROT[y], tgt, extra)
    else:
        t = "%s %d,%s%s" % (["", "bit", "res", "set"][x], y, tgt, extra if x != 1 else "")
    return Insn(pc, n, t, "seq", None)


def _ed(mem, pc):
    op = mem[(pc + 1) & 0xFFFF]
    x, y, z = op >> 6, (op >> 3) & 7, op & 7
    p, q = y >> 1, y & 1
    w = mem[(pc + 2) & 0xFFFF] | mem[(pc + 3) & 0xFFFF] << 8
    if x == 1:
        if z == 0:
            return Insn(pc, 2, "in %s,(c)" % ("f" if y == 6 else R8[y]), "seq", None)
        if z == 1:
            return Insn(pc, 2, "out (c),%s" % ("0" if y == 6 else R8[y]), "seq", None)
        if z == 2:
            return Insn(pc, 2, ("sbc hl,%s" if q == 0 else "adc hl,%s") % RP[p], "seq", None)
        if z == 3:
            t = "ld (%s),%s" if q == 0 else "ld %s,(%s)"
            return Insn(pc, 4, (t % (h16(w), RP[p])) if q == 0 else (t % (RP[p], h16(w))),
                        "seq", None)
        if z == 4:
            return Insn(pc, 2, "neg", "seq", None)
        if z == 5:
            return Insn(pc, 2, "reti" if y == 1 else "retn", "ret", None)
        if z == 6:
            return Insn(pc, 2, "im %s" % ["0", "0", "1", "2", "0", "0", "1", "2"][y], "seq", None)
        return Insn(pc, 2, ["ld i,a", "ld r,a", "ld a,i", "ld a,r", "rrd", "rld", "nop", "nop"][y],
                    "seq", None)
    if x == 2 and z < 4 and y >= 4:
        n = ["ldi", "ldd", "ldir", "lddr", "cpi", "cpd", "cpir", "cpdr",
             "ini", "ind", "inir", "indr", "outi", "outd", "otir", "otdr"]
        return Insn(pc, 2, n[(z * 4) + (y - 4)], "seq", None)
    return Insn(pc, 2, "nop ; ed %02x" % op, "seq", None)


def _idx(mem, pc, name):
    op = mem[(pc + 1) & 0xFFFF]
    d = mem[(pc + 2) & 0xFFFF]
    if op == 0xCB:
        return _cb(mem, pc, (name, d))
    hi, lo = name + "h", name + "l"
    x, y, z = op >> 6, (op >> 3) & 7, op & 7
    p, q = y >> 1, y & 1
    m = "(%s%+d)" % (name, s8(d))
    w = mem[(pc + 2) & 0xFFFF] | mem[(pc + 3) & 0xFFFF] << 8

    def I(n, t, k="seq", tg=None):
        return Insn(pc, n, t, k, tg)

    def r(i, dd=False):
        return {4: hi, 5: lo}.get(i, R8[i])

    if op == 0x21:
        return I(4, "ld %s,%s" % (name, h16(w)))
    if op == 0x22:
        return I(4, "ld (%s),%s" % (h16(w), name))
    if op == 0x2A:
        return I(4, "ld %s,(%s)" % (name, h16(w)))
    if op == 0x23:
        return I(2, "inc " + name)
    if op == 0x2B:
        return I(2, "dec " + name)
    if op in (0x09, 0x19, 0x29, 0x39):
        return I(2, "add %s,%s" % (name, [ "bc", "de", name, "sp"][p]))
    if op == 0x34:
        return I(3, "inc " + m)
    if op == 0x35:
        return I(3, "dec " + m)
    if op == 0x36:
        return I(4, "ld %s,%s" % (m, h8(mem[(pc + 3) & 0xFFFF])))
    if op in (0x24, 0x2C):
        return I(2, "inc " + r(y))
    if op in (0x25, 0x2D):
        return I(2, "dec " + r(y))
    if op in (0x26, 0x2E):
        return I(3, "ld %s,%s" % (r(y), h8(d)))
    if x == 1 and op != 0x76:
        if z == 6:
            return I(3, "ld %s,%s" % (R8[y], m))
        if y == 6:
            return I(3, "ld %s,%s" % (m, R8[z]))
        if 4 in (y, z) or 5 in (y, z):
            return I(2, "ld %s,%s" % (r(y), r(z)))
    if x == 2:
        if z == 6:
            return I(3, ALU[y] + m)
        if z in (4, 5):
            return I(2, ALU[y] + r(z))
    if op == 0xE1:
        return I(2, "pop " + name)
    if op == 0xE5:
        return I(2, "push " + name)
    if op == 0xE3:
        return I(2, "ex (sp)," + name)
    if op == 0xE9:
        return I(2, "jp (%s)" % name, "jp", None)
    if op == 0xF9:
        return I(2, "ld sp," + name)
    # Not an indexed instruction: the prefix has no effect; report it alone.
    return I(1, "nop ; %s prefix ignored" % ("dd" if name == "ix" else "fd"))

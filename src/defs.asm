; XYBOTS V9990 B1 - hardware and layout definitions shared by every B1 build (bring-up ROM and game ROM).
; Mode: B1 (bitmap, 256x212), 4 bpp (BP4), PAL. Hardware facts: V9990-P1/doc/V9990_P1_REFERENCE.md sections 1, 7, 8 (registers and
; commands are the same in the bitmap modes), plus doc/B1_NOTES.md for what was verified for B1. Assembler: SJASM 0.42c.

; ---- MSX I/O ports
V9_VRAM         equ 0x60        ; P#0 VRAM data, auto-increment
V9_PAL          equ 0x61        ; P#1 palette data
V9_REGDATA      equ 0x63        ; P#3 register data (auto-increments the register number)
V9_REGSEL       equ 0x64        ; P#4 register select
V9_STATUS       equ 0x65        ; P#5 status (bit 6 = VR, bit 2 = TR, bit 0 = CE)
V9_INTFLAGS     equ 0x66        ; P#6 interrupt flags
V9_SYSCTRL      equ 0x67        ; P#7 system control (bit 1 = SRS reset)
V9_OUTCTL       equ 0x6F        ; board output control (gfx9000)
TMS_CTRL        equ 0x99

; ---- V9990 registers used (numbers)
R_VRAMR         equ 3           ; R#3-5 VRAM read address
R_MODE          equ 6
R_CTRL          equ 8
R_PALSEL        equ 13
R_PALPTR        equ 14
R_SCAY_LO       equ 17
R_LINT          equ 10              ; R#10-R#11 line interrupt line, R#12 its X position
R_CMD           equ 32          ; R#32..R#52: command block, R#52 = opcode (starts the command)

MODE_B1_BP6     equ 0x82        ; bitmap, 256 wide, 8 bits per pixel; R#13 PLTM = 0 -> BP6 (64-colour palette)
TIMING_PAL      equ 0x08
CTRL_DISPLAY_OFF equ 0x42       ; display off, sprites/cursor off, 512 KiB VRAM
CTRL_DISPLAY_ON equ 0xc2

; ---- command opcodes (R#52)
OP_LMMV         equ 0x20
OP_LMMM         equ 0x40
LOP_COPY        equ 0x0c        ; WC = SC
LOP_COPY_TP     equ 0x1c        ; source colour 0 not transferred

; ---- VRAM map (linear byte address = Y*128 + X/2 for a bitmap pixel (X,Y))

;==============================================================================
;  XYBOTS V9990 BP6 - core routines: B1 / BP6 initialisation, display on, command-engine wait, opaque LMMM start.
;==============================================================================

; b1_init - B1 256x212 BP6 (8 bpp, 64 colours), PAL, display OFF, no interrupts, palette offset 0, scroll 0 (page 0), backdrop colour 0.  Clobbers: AF, BC
b1_init:
        ld a,R_MODE
        out (V9_REGSEL),a
        ld a,MODE_B1_BP6
        out (V9_REGDATA),a              ; R#6
        ld a,TIMING_PAL
        out (V9_REGDATA),a              ; R#7
        ld a,CTRL_DISPLAY_OFF
        out (V9_REGDATA),a              ; R#8
        xor a
        out (V9_REGDATA),a              ; R#9 = 0: no V9990 interrupts (enabled later by the runtime)
        ld a,7
        out (V9_INTFLAGS),a
        ld a,R_PALSEL
        out (V9_REGSEL),a
        xor a
        out (V9_REGDATA),a              ; R#13 = 0: BP6, palette offset 0
        out (V9_REGDATA),a              ; R#14 = 0: palette pointer
        out (V9_REGDATA),a              ; R#15 = 0: backdrop colour = palette entry 0 (black)
        ld a,R_SCAY_LO
        out (V9_REGSEL),a
        xor a
        ld b,8
        ld c,V9_REGDATA
.zs:    out (c),a                       ; R#17..R#24 = 0 (scroll A/B, page 0)
        djnz .zs
        xor a
        out (V9_OUTCTL),a
        ret

b1_display_on:
        ld a,R_CTRL
        out (V9_REGSEL),a
        ld a,CTRL_DISPLAY_ON
        out (V9_REGDATA),a
        ret

; b1_wait_ce - wait for the command engine.  Clobbers: AF
b1_wait_ce:
        in a,(V9_STATUS)
        rrca
        jr c,b1_wait_ce
        ret

; b1_lmmm_start - opaque LMMM: R32..R43 from hk_sx, hk_sy, hk_dx, hk_dy, hk_nx, hk_ny (12 bytes), ARG 0, LOP copy, then the opcode.
;   The write mask stays FFFFh (set by hk_vp_consts / b1_cmmc_start).   Clobbers: AF, BC, HL
b1_lmmm_start:
        ld a,LOP_COPY
        ld c,0xff
        jp hk_lmmm_wm                   ; BP6 split screen: short interrupt-free register sections (hk_hud.asm)

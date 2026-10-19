;==============================================================================
;  XYBOTS V9990 B1 - VDP port shims (RST 08h/10h/18h/28h/30h -> JP into this file, see the patch manifest of build_b1.py) - ADR-016
;
;  The TMS9918 is not used any more: nothing is written to or read from ports 98h/99h. The engine's remaining VDP accesses (colour-table
;  writes of init_hardware, init_screen_colours, the title marquee, the viewport colour fills, the shop highlight, the colour rings) are
;  turned into a MODEL of the colour of every screen cell in RAM: HK_TOPCOL (HUD, rows 0-11) and HK_CELLCOL (viewports, rows 12-23). The
;  V9990 renderer takes its colours from there. Pattern-table writes have no effect: every routine that drew into the pattern table is
;  replaced by V9990 commands (hk_hud.asm, hk_sprites.asm, hk_viewport.asm).
;  The shims keep the TMS address counter in software: an address pair on port 99h sets hk_bstart (write or read form alike), every data
;  access advances it. A register write (second byte with bit 7 set) is ignored.
;==============================================================================

; ---- RST 08h replaces OUT (98h),A   In: A   Clobbers: nothing (flags preserved)
hk_out98:
        push af
        push hl
        ld (hk_tmpa),a
        ld hl,(hk_bstart)
        push hl
        inc hl
        ld (hk_bstart),hl
        pop hl                          ; HL = address of this byte
        ld a,(hk_bkind)
        cp 2
        call z,hk_colwrite              ; colour table: the model of the cell's colour
        pop hl
        pop af
        ret

; ---- RST 18h replaces IN A,(98h): nothing reads VRAM any more (the read-modify-write routines are replaced); returns 0.
hk_in98:
        push hl
        ld hl,(hk_bstart)
        inc hl
        ld (hk_bstart),hl
        pop hl
        ld a,0
        ret

; ---- RST 10h replaces OUT (99h),A   In: A   Clobbers: nothing (flags preserved)
hk_out99:
        push af
        ld (hk_tmpa),a
        ld a,(hk_latch)
        or a
        jr nz,.second
        inc a
        ld (hk_latch),a
        ld a,(hk_tmpa)
        ld (hk_lo),a                    ; first byte: kept
        pop af
        ret
.second:
        xor a
        ld (hk_latch),a
        ld a,(hk_tmpa)
        bit 7,a
        jr nz,.reg                      ; register write: ignored (no TMS)
        push hl
        and 0x3f
        ld h,a
        ld a,(hk_lo)
        ld l,a
        ld (hk_bstart),hl               ; address (write or read form)
        ld a,h
        cp 0x20
        jr c,.k0
        cp 0x38
        jr nc,.k0
        ld a,2                          ; 2000h-37FFh colour table
        jr .k
.k0:    xor a
.k:     ld (hk_bkind),a
        pop hl
.reg:   pop af
        ret

; ---- RST 20h replaces the `IN A,(99h)` at 7C76h in the game's IM 1 handler. Single HUD (split screen): the line interrupt switches R#17
;      to the displayed buffer and leaves the handler at once; the vertical interrupt counts frames and points R#17 back at VR_HUD for the
;      next frame. The main code keeps interrupts off while it writes V9990 registers (the handler changes P#4).
;      A R#17 write restarts the display in the line being drawn (openMSX: verticalOffsetA = current line), so the line it lands in
;      decides where the viewports start: the write is synchronised with the horizontal retrace flag (P#5 bit 5) and lands at the
;      start of the display part of line 95. Written on interrupt latency alone it landed in line 95 or 96 and the whole viewport block
;      jumped by one line (the user's "tiembla"). The rest of line 95 shows the line before the buffer (the last HUD line, see hud4.py).
;      The retrace wait is exact only if it starts within one line (~228 Z80 cycles) around its usual moment. When the ISR itself
;      started it, the interrupt latency (DI sections of hk_regs4 / hk_lmmv / hk_cmd_start, up to ~125 cycles) used most of that line:
;      a late entry still made the viewport jump for one frame every few seconds. Now the
;      interrupt comes 5 lines early (R#10 = HK_LI_LINE); the handler moves the line to HK_LI_SYNC (the old interrupt point, line 93
;      X unit 8) and polls the line-interrupt FLAG (P#6 bit 1): it rises at the same beam position whatever the latency, the retrace
;      wait starts HK_LI_DELAY loops after it, and R#10 goes back to HK_LI_LINE for the next frame.
;      Clobbers A only (the handler overwrites A right after).
hk_irq:
        in a,(V9_INTFLAGS)
        and 2
        jr z,.vi
        ld a,2                          ; line interrupt (HK_LI_LINE): acknowledge it
        out (V9_INTFLAGS),a
        push bc
        ld a,R_LINT
        out (V9_REGSEL),a
        ld a,HK_LI_SYNC
        out (V9_REGDATA),a              ; R#10: the flag rises again at HK_LI_SYNC (interrupts are off: no second entry)
        ld b,0                          ; (bounded: ~34 lines)
.f:     in a,(V9_INTFLAGS)
        and 2
        jr nz,.fs
        djnz .f
        jr .late                        ; the flag did not rise: entered after HK_LI_SYNC (interrupts held for lines). R#17 written now
                                        ; would restart the viewport buffer in mid-screen (the top of the room shown twice, user's
                                        ; turbo R 2026-10-19, ADR-052): this frame keeps VR_HUD and the buffer A lines that follow it
.fs:    ld a,2
        out (V9_INTFLAGS),a             ; flag down before EI
        ld b,HK_LI_DELAY
.d:     djnz .d
        ld a,R_SCAY_LO
        out (V9_REGSEL),a
        ld a,(hk_vlow)
        ld b,a
.h0:    in a,(V9_STATUS)                ; display part of line 94 (HR = 0) ...
        and 0x20
        jr nz,.h0
.h1:    in a,(V9_STATUS)                ; ... its end (HR = 1) ...
        and 0x20
        jr z,.h1
.h2:    in a,(V9_STATUS)                ; ... and the display part of line 95
        and 0x20
        jr nz,.h2
        ld a,b
.w17:   out (V9_REGDATA),a              ; R#17: line 96 on shows line 768 + hk_vlow + 1 on (buffer line 0)
.late:  ld a,R_LINT
        out (V9_REGSEL),a
        ld a,HK_LI_LINE
        out (V9_REGDATA),a              ; R#10: next frame's interrupt
        pop bc
        ld a,(hk_hic)
        inc a
        ld (hk_hic),a
        inc sp
        inc sp                          ; not back into the game's handler: sound and the rest belong to the frame interrupt
        pop af                          ; AF saved by the handler (7C75h)
        ei
        reti
.vi:    ld a,(hk_frames)
        inc a
        ld (hk_frames),a
        ld a,1
        out (V9_INTFLAGS),a             ; write 1 to VI to clear it
        ld a,R_SCAY_LO
        out (V9_REGSEL),a
        xor a
        out (V9_REGDATA),a              ; R#17 = 0: the next frame starts with VR_HUD (lines 0-95)
        ret

; ---- RST 28h / 30h: address pair of the (replaced) minimap read-modify-write routines; kept harmless.
hk_wp1:
        ld (hk_lo),a
        ret
hk_wp2:
        ret

;------------------------------------------------------------------------------
; hk_colwrite - colour byte (hk_tmpa) written to TMS colour-table address HL (2000h-37FFh): cell = (HL - 2000h) / 8. HUD cells update
; HK_TOPCOL; a viewport cell whose colour changes updates HK_CELLCOL, the tint of its half and becomes unknown in the background image.
;   Preserves BC, DE; clobbers AF, HL
;------------------------------------------------------------------------------
hk_colwrite:
        push bc
        push de
        ld a,h
        sub 0x20
        ld h,a
        srl h
        rr l
        srl h
        rr l
        srl h
        rr l                            ; HL = cell 0..767
        ld de,384
        or a
        sbc hl,de
        jr nc,.bottom
        add hl,de
        ld de,HK_TOPCOL
        add hl,de
        ld a,(hk_tmpa)
        ld (hl),a
        jr .out
.bottom:
        ld de,HK_CELLCOL
        push hl
        add hl,de
        ld a,(hk_tmpa)
        ld b,(hl)                       ; B = old colour
        cp b
        ld (hl),a
        pop hl                          ; HL = viewport cell 0..383
        jr z,.out                       ; same colour: nothing to do
        ld c,a                          ; C = new colour
        push bc
        push hl
        ld a,l
        and 16
        rrca
        rrca
        rrca
        rrca
        ld e,a
        ld d,0
        ld hl,hk_huni
        add hl,de
        ld (hl),d                       ; mixed colours: the half is not uniform text any more (ADR-020)
        inc hl
        inc hl
        ld a,(hl)
        ld (hl),d
        pop hl
        or a
        call nz,hk_half_unknown         ; it was composed canonically: recompose it in its real colours
        pop bc
        call hk_vinvalidate             ; redrawn in the background from the font tiles of the new colour (copies, ADR-021)
.out:   pop de
        pop bc
        ret

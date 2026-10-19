;==============================================================================
;  XYBOTS V9990 B1 - viewport texts from coloured font tiles (ADR-018)
;
;  The texts, blank views and shop stripes of the viewports were drawn by the engine into its CPU frame buffer (EB00h). Now:
;    - the fonts are 4 bpp coloured TILES in VRAM (tools/hud4.py, assets/hud/vfont8.png 8x8 = shop texts + stripes tile 65,
;      vfont16.png 8x16 = PRESS FIRE / GAME OVER / banners), one variant per colour byte of colours.json;
;    - every static cell of the viewport background is drawn with LMMM copies of those tiles (hk_emit_static), in the variant of the
;      cell's colour byte; blank lines are LMMV fills of the paper colour;
;    - which tile line belongs in which cell line is kept in a RECORD in VRAM (2 bytes per cell line: source, source line; source
;      00h-40h vfont8 glyph, 80h-C0h vfont16 glyph, EEh stripes, FFh blank). The engine's writers only update the record, with V9990
;      copies from the record atlas (VR_RA_Y) and fills; the cells they touch are queued, and hk_emit_static reads the record back to
;      compose the cell from the tiles in its CURRENT colour (so a later colour change, e.g. the shop highlight, redraws from tiles too).
;  Record layout: half h, cell row r, column c: line VR_REC_Y + (h * 12 + r) * 2 + ((c >> 3) & 1), bytes (c & 7) * 16 + 2 * line
;  (pixel x = (c & 7) * 32 + 4 * line: one cell line = 2 bytes = 4 pixels).
;==============================================================================

; hk_txt_dy - hk_dy = record line of cell row A (0..11), column C (0..31).   Preserves BC; clobbers AF, DE, HL
hk_txt_dy:
        ld l,a
        ld a,c
        and 16
        jr z,.h0
        ld a,12
.h0:    add a,l                         ; BP6: half * 12 + row
        ld l,a
        ld h,0
        ld de,VR_REC_Y
        add hl,de
        ld (hk_dy),hl
        ret

; hk_txt_glyph - record glyph hk_tg (0..64) of hk_tn lines (8 / 16) at cell row hk_tr, column hk_tc, first line hk_to: one LMMM per
; covered cell from the glyph's slot of the record atlas. Lines below row 11 are not recorded (the caller lets the original routine write
; its spill area).   Clobbers: all
hk_txt_glyph:
        ld a,(hk_tg)
        ld c,a
        ld a,(hk_tn)
        cp 16
        ld a,c
        jr nz,.sl
        add a,65                        ; vfont16 slots follow the 65 vfont8 slots
.sl:    ld c,a                          ; C = slot
        and 7
        rrca
        rrca
        rrca                            ; (slot & 7) * 32
        ld (hk_tsx),a
        ld a,c
        rrca
        rrca
        rrca
        and 31
        ld l,a
        ld h,0
        ld de,VR_RA_Y
        add hl,de
        ld (hk_sy),hl
        xor a
        ld (hk_ts),a                    ; glyph lines already recorded
.piece: ld a,(hk_to)
        ld b,a
        ld a,8
        sub b
        ld c,a                          ; C = lines left in this cell
        ld a,(hk_tn)
        cp c
        jr nc,.k
        ld c,a                          ; C = k = min(8 - o, n)
.k:     ld a,(hk_ts)
        add a,a
        ld b,a
        ld a,(hk_tsx)
        add a,b
        ld (hk_sx),a                    ; SX = slot x + 2 * lines recorded
        xor a
        ld (hk_sx+1),a
        ld (hk_dx+1),a
        ld (hk_nx+1),a
        ld (hk_ny+1),a
        inc a
        ld (hk_ny),a                    ; NY = 1
        ld a,c
        add a,a
        ld (hk_nx),a                    ; NX = 2k
        ld a,(hk_tc)
        and 15
        rlca
        rlca
        rlca
        rlca                            ; (c & 15) * 16
        ld b,a
        ld a,(hk_to)
        add a,a
        add a,b
        ld (hk_dx),a                    ; DX = (c & 15) * 16 + 2 * o
        push bc
        ld a,(hk_tc)
        ld c,a
        ld a,(hk_tr)
        call hk_txt_dy
        ld a,LOP_COPY
        call hk_lmmm_op
        pop bc
        ld a,(hk_ts)
        add a,c
        ld (hk_ts),a
        ld a,(hk_tn)
        sub c
        ld (hk_tn),a
        ret z                           ; every line recorded
        xor a
        ld (hk_to),a
        ld a,(hk_tr)
        inc a
        ld (hk_tr),a
        cp 12
        jr c,.piece
        ret

; hk_txt_clear_cell - record of cell HL (0..383) := blank (a glyph covers only part of a cell whose frame-buffer bytes were the tile's;
; see hk_glyph). Counted in hk_tdev.   Preserves BC, DE, HL; clobbers AF
hk_txt_clear_cell:
        call hk_tdev_inc
; hk_txt_blank_cell - the same, not counted (the deferred clear of a text screen, ADR-028)
hk_txt_blank_cell:
        push bc
        push de
        push hl
        ld a,l
        and 31
        ld c,a
        add hl,hl
        add hl,hl
        add hl,hl
        ld a,h                          ; row
        call hk_txt_dy
        ld a,c
        and 15
        rlca
        rlca
        rlca
        rlca
        ld (hk_dx),a
        xor a
        ld (hk_dx+1),a
        ld (hk_nx+1),a
        ld (hk_ny+1),a
        inc a
        ld (hk_ny),a
        ld a,16
        ld (hk_nx),a
        ld a,0xff
        call hk_lmmv_raw                ; FFh = blank
        pop hl
        pop de
        pop bc
        ret

; hk_txt_half - record of half A (0/1): D = 0 blank (FFh), D = 1 shop stripes (EEh).   Clobbers: all
hk_txt_half:
        ld hl,VR_REC_Y
        or a
        jr z,.h
        ld hl,VR_REC_Y+12
.h:     ld bc,12
        jr hk_txt_fill

; hk_txt_clear_all - the whole record := blank (boot, game_reset).   Clobbers: all
hk_txt_clear_all:
        ld hl,VR_REC_Y
        ld bc,24
        ld d,0
; hk_txt_fill - record lines HL.. (BC lines, full width): D = 0 blank, D = 1 stripes.
hk_txt_fill:
        ld (hk_dy),hl
        ld (hk_ny),bc
        ld hl,0
        ld (hk_dx),hl
        ld h,1
        ld (hk_nx),hl                   ; 256
        ld a,d
        or a
        ld a,0xff                       ; FFh = blank
        jp z,hk_lmmv_raw
        ld a,0xee                       ; EEh = stripes
        jp hk_lmmv_raw

; hk_greset_tail - replaces the frame-buffer fill at the end of game_reset (2FF3h-3001h): the stores it skipped, then return (the fill
; loop l_3002 ended with the RET of game_reset). The record was cleared at the entry (hk_greset).
hk_greset_tail:
        ld a,1
        ld (0x72a6),a                   ; var_72A6 := 1
        xor a
        ld (0x2207),a                   ; shop_mask := 0
        ld (hk_bosspend),a              ; no deferred boss reset (ADR-051)
        ret

;------------------------------------------------------------------------------
; hk_emit_static - background cell hk_vc from its record: runs of lines with the same source (consecutive source lines) become one
; LMMM of a font tile or one LMMV of the paper. Colours (ADR-020): a CANONICAL half (hk_hfb: uniform text whose colour has no font
; variant) is composed in FALLBACK_COL (white on 0) and recoloured on the draw page every pass (hk_page_recolour); otherwise the cell is
; composed in the variant of its colour byte, or, when a font lacks that colour, in FALLBACK_COL into the scratch and recoloured into
; the background (hk_recolour, 3 commands).   Clobbers: all
;------------------------------------------------------------------------------
hk_emit_static:
        ld hl,(hk_vc)
        ld a,l
        and 31
        ld c,a                          ; C = column
        add hl,hl
        add hl,hl
        add hl,hl
        ld a,h                          ; A = row
        call hk_txt_dy                  ; hk_dy = record line
        ld hl,(hk_dy)
        ld a,c
        and 15
        rlca
        rlca
        rlca
        rlca
        ld e,a                          ; BP6: address = line * 256 + (c & 15) * 16 (L = bits 15-8, H = bits 18-16)
        call b1_wait_ce
        di                              ; no line interrupt while V9990 registers are written (it changes P#4)
        ld a,R_VRAMR
        out (V9_REGSEL),a
        ld a,e
        out (V9_REGDATA),a              ; R3
        ld a,l
        out (V9_REGDATA),a              ; R4
        ld a,h
        out (V9_REGDATA),a              ; R5
        ei
        ld hl,hk_rec
        ld bc,16*256+V9_VRAM
        inir                            ; the 8 (source, line) pairs of the cell
        ld hl,(hk_vc)
        ld de,HK_CELLCOL
        add hl,de
        ld a,(hl)
        ld (hk_ecol),a
        call hk_bg_xy                   ; hk_dx / hk_dy = the cell in the background image
        ld hl,(hk_dy)
        ld (hk_ebase),hl
        ld hl,8
        ld (hk_nx),hl
        xor a
        ld (hk_efix),a                  ; 1 = composed into the scratch, recoloured into the background at the end
        call hk_shop_cell
        ld a,(hk_theme)
        or a
        jr z,.ordinary
        xor a
        jp .drawn                      ; text cache already cleared; draw the recorded letters in their shop variant
.ordinary:
        ld hl,(hk_vc)
        ld a,l
        and 16
        ld hl,hk_hfb
        jr z,.hf
        inc hl
.hf:    ld a,(hl)
        or a
        jp nz,.canon                    ; canonical half: FALLBACK_COL, the page pass recolours it
        ld a,(hk_ecol)
        call hk_ink_eq_paper
        jr nz,.visible
        ld a,(hk_ecol)
        ld hl,8
        ld (hk_ny),hl
        jp hk_lmmv                      ; ink = paper: the cell is one colour whatever the record holds
.visible:
        ld hl,hk_rec                    ; one source in every line: blank -> one fill, stripes -> one copy (no run loop)
        ld a,(hl)
        cp 0xee
        jr c,.lookup
        ld b,7
.uni:   inc hl
        inc hl
        cp (hl)
        jr nz,.lookup
        djnz .uni
        cp 0xff
        jr nz,.lookup                   ; all stripes: the general path (one run) with the lookup
        ld a,8
        ld (hk_ny),a
        xor a
        ld (hk_ny+1),a
        ld a,(hk_ecol)
        jp hk_lmmv                      ; all blank: paper
.lookup:
        ld a,(hk_ecol)                  ; variant bases of this colour: cached from the previous cell
        ld hl,hk_ecc
        cp (hl)
        jr z,.cached
        ld (hl),a
        ld hl,hud_vfont8_cols
        ld b,VF8_NV
        call hk_find
        ld de,VF8_VL
        ld hl,VR_VF8_Y
        call hk_vbase
        ld (hk_cv8),hl
        ld a,(hk_ecol)
        ld hl,hud_vfont16_cols
        ld b,VF16_NV
        call hk_find
        ld de,VF16_VL
        ld hl,VR_VF16_Y
        call hk_vbase
        ld (hk_cv16),hl
.cached:
        ld hl,(hk_cv8)
        ld (hk_ev8),hl
        ld hl,(hk_cv16)
        ld (hk_ev16),hl
        ld a,(hk_cv8+1)
        inc a
        jr z,.check                     ; vfont8 has no variant of this colour
        ld a,h
        inc a
        ld a,(hk_ecol)
        jr nz,.drawn                    ; both fonts have the colour: no source check
.check:
        ld hl,hk_rec                    ; a source whose font has no variant of this colour: FALLBACK_COL into the scratch, recolour after
        ld b,8
.chk:   ld a,(hl)
        inc hl
        inc hl
        cp 0xff
        jr z,.chk1
        cp 0xee
        jr z,.small
        bit 7,a
        ld a,(hk_ev16+1)
        jr nz,.test
.small: ld a,(hk_ev8+1)
.test:  inc a
        jr z,.scratch
.chk1:  djnz .chk
        ld a,(hk_ecol)
        jr .drawn
.scratch:
        ld a,1
        ld (hk_efix),a
        ld hl,0
        ld (hk_dx),hl
        ld hl,VR_SCR_Y
        ld (hk_ebase),hl
.canon: ld hl,VR_VF8_FB_Y
        ld (hk_ev8),hl
        ld hl,VR_VF16_FB_Y
        ld (hk_ev16),hl
        ld a,FALLBACK_COL
.drawn: ld (hk_edraw),a
        xor a
        ld (hk_ei),a
.run:   ld a,(hk_ei)
        cp 8
        jr c,.more
        ld a,(hk_efix)
        or a
        ret z
        ld hl,0                         ; scratch cell -> background cell, in the cell's colour
        ld (hk_sx),hl
        ld hl,VR_SCR_Y
        ld (hk_sy),hl
        call hk_bg_xy
        ld hl,8
        ld (hk_nx),hl
        ld (hk_ny),hl
        ld a,(hk_ecol)
        jp hk_recolour
.more:
        ld c,a                          ; C = first line of the run
        add a,a
        ld l,a
        ld h,0
        ld de,hk_rec
        add hl,de
        ld d,(hl)                       ; D = source
        inc hl
        ld e,(hl)                       ; E = source line
        ld b,1                          ; B = lines in the run
.ext:   ld a,c
        add a,b
        cp 8
        jr nc,.go
        inc hl
        ld a,(hl)
        cp d
        jr nz,.go
        inc hl
        ld a,d
        cp 0xee
        jr nc,.same                     ; stripes / blank: the source line does not matter
        ld a,e
        add a,b
        cp (hl)
        jr nz,.go
.same:  inc b
        jr .ext
.go:    ld a,c
        add a,b
        ld (hk_ei),a
        ld a,b
        ld (hk_ny),a
        xor a
        ld (hk_ny+1),a
        ld hl,(hk_ebase)
        ld a,l
        add a,c
        ld l,a
        ld (hk_dy),hl                   ; the cell's rows never cross a 256-line boundary (VR_BG_Y + 96 lines)
        ld a,(hk_theme)
        or a
        ld a,d
        jr z,.source
        cp 0xee
        jp nc,.run                     ; blank / stripes leave transparent black in the shop text cache
.source:
        ld a,d
        cp 0xff
        jr z,.blank
        cp 0xee
        jr nz,.glyph
        ld d,65                         ; stripes = tile 65 of vfont8, source line = cell line
        ld e,c
.glyph: push de
        bit 7,d
        ld hl,(hk_ev8)
        jr z,.var
        ld hl,(hk_ev16)
.var:   pop de                          ; D = source, E = source line
        ld a,d
        and 0x7f
        ld c,a                          ; C = glyph
        and 31
        add a,a
        add a,a
        add a,a
        ld (hk_sx),a                    ; x = (g & 31) * 8
        xor a
        ld (hk_sx+1),a
        ld a,c
        rlca
        rlca
        rlca
        and 3                           ; g >> 5
        bit 7,d
        jr z,.r8
        add a,a                         ; 16-line rows
.r8:    add a,a
        add a,a
        add a,a                         ; * 8
        add a,e                         ; + source line
        ld e,a
        ld d,0
        add hl,de
        ld (hk_sy),hl
        ld a,(hk_theme)
        or a
        ld a,LOP_COPY
        jr z,.copy
        ld a,LOP_COPY_TP                ; black font pixels are transparent in the shop text cache
.copy:
        call hk_lmmm_op
        jp .run
.blank: ld a,(hk_edraw)
        call hk_lmmv                    ; paper = low nibble (hk_lmmv keeps the low 4 bits)
        jp .run


;------------------------------------------------------------------------------
; helpers (ADR-019 / ADR-020)
;------------------------------------------------------------------------------
; hk_find - A = colour byte, HL = colour table of a sheet, B = variants: A = variant index, FFh when the colour has none.   Clobbers: BC, HL
hk_find:
        ld c,b
.l:     cp (hl)
        jr z,.hit
        inc hl
        djnz .l
        ld a,0xff
        ret
.hit:   ld a,c
        sub b
        ret

; hk_vbase - A = variant index (FFh none), HL = base line of the sheet, DE = lines per variant: HL = base line of the variant (FFFFh none).
hk_vbase:
        inc a
        jr z,.none
        dec a
        ret z
.m:     add hl,de
        dec a
        jr nz,.m
        ret
.none:  ld hl,0xffff
        ret

; hk_ink_eq_paper - A = colour byte: Z when ink = paper (the cell shows one colour).   Clobbers: AF, B
hk_ink_eq_paper:
        ld b,a
        rrca
        rrca
        rrca
        rrca
        xor b
        and 15
        ret

;------------------------------------------------------------------------------
; hk_recolour - the rectangle hk_sx, hk_sy (composed in FALLBACK_COL: paper 0, ink <> 0) -> hk_dx, hk_dy, hk_nx x hk_ny in colour byte A:
; fill the destination with the paper, then two transparent copies (0 = paper skipped) with write masks: set the bits of the ink, clear
; the bits the ink does not have.   Clobbers: all
;------------------------------------------------------------------------------
hk_recolour:
        ld (hk_rc1),a
        call hk_lmmv                    ; destination := paper (low nibble)
        ld a,(hk_rc1)
        rrca
        rrca
        rrca
        rrca
        and 15
        ld c,a                          ; BP6: write mask = the ink index
        ld a,LOP_TP_ONE
        call hk_lmmm_wm                 ; ink pixels := paper | ink
        ld a,(hk_rc1)
        rrca
        rrca
        rrca
        rrca
        and 15
        cpl
        ld c,a
        ld a,LOP_TP_ZERO
        jp hk_lmmm_wm                   ; ink pixels := ink




;------------------------------------------------------------------------------
; hk_svc - entry of set_view_colours (7F1Dh), replaced entirely (ADR-019): the whole viewport half of player A (0 -> half 0 with the
; attribute at 9602h, 1 -> half 1 with 9603h, A > 1 like 0) gets one colour byte. The original wrote 1536 bytes to the TMS colour table
; with the interrupts disabled; here the colour model is updated in one loop (hk_half_colour). Contract: IX preserved, interrupts
; ENABLED on return (as the original's EI), AF BC DE HL clobbered.
;------------------------------------------------------------------------------
hk_svc:
        push ix
        ld e,a
        ld a,(0x9602)
        ld d,0
        dec e
        jr nz,.p
        ld a,(0x9603)
        inc d
.p:     push de
        call 0x6fd4                     ; zx_attr_to_msx: ZX attribute -> MSX colour byte
        pop de
        ld e,a
        ld a,d
        call hk_half_colour
        ei
        pop ix
        ret

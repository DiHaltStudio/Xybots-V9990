;==============================================================================
;  XYBOTS V9990 B1 - viewports with a clean background image in VRAM (milestone 4, ADR-012)
;
;  The original rebuilds the background only when the view changes and paints the actors over it with the painter's algorithm every pass.
;  Here the background of both viewports (tiles from the cell map + text/cleared/striped cells composed from the coloured font tiles, hk_text.asm, ADR-018) is kept as a 256x96
;  image in VRAM (VR_BG_Y), updated only when something changes (render, text, colour byte, tile bank), and every pass starts by copying it
;  into the draw page with ONE LMMM; the actors (hk_sprites.asm) and the DANGER signs (hk_hooks.asm) are then drawn over it in the
;  engine's own order. Nothing is cached per page for the viewports: the page is rebuilt from the background image every pass.
;
;  Per cell: HK_VT = what the background image holds (tile id, VT_STATIC, VT_UNKNOWN); HK_VKIND = 1 when the text record decides the cell
;  (text/cleared/striped, set by the writer hooks, cleared by render_cellmaps); HK_VRAW bit 0 = static content changed since it was sent
;  (bits 5-7: glyph line offset, HK_GLY: glyph code, both used by the glyph hooks to skip reprints of the same text).
;  hk_dirtyh bit h = half h must be scanned; HK_SLIST = queued static cells (avoid a scan for a few text cells).
;==============================================================================

; hk_vp_init - boot: background unknown, both halves dirty.   Clobbers: all
hk_vp_init:
        ld hl,HK_VT
        ld de,HK_VT+1
        ld bc,383
        ld (hl),VT_UNKNOWN
        ldir
        ld hl,HK_GLY
        ld de,HK_GLY+1
        ld bc,383
        ld (hl),0xff
        ldir
        ld hl,HK_VKIND
        ld de,HK_VKIND+1
        ld bc,767                       ; HK_VKIND and HK_VRAW
        xor a
        ld (hl),a
        ldir
        ld a,3
        ld (hk_dirtyh),a
        xor a
        ld (hk_bcv),a
        ld (hk_sn),a
        ld (hk_prep),a
        ld (hk_bank),a
        ld (hk_hclr),a                  ; no text screen cleared yet (ADR-028; HK_VARS is not zeroed at boot)
        ld (hk_hpend),a
        ld hl,0x751c
        ld (hk_bankw),hl
        ret

; hk_half_unknown - the half containing cell HL: every cell unknown in the background, half dirty.   Preserves HL; clobbers AF, BC, DE
hk_half_unknown:
        push hl
        ld a,l
        and 16
        ld l,a
        ld h,0
        ld de,HK_VT
        add hl,de
        ld c,12
.r:     push hl
        ld b,16
.c:     ld (hl),VT_UNKNOWN
        inc hl
        djnz .c
        pop hl
        ld de,32
        add hl,de
        dec c
        jr nz,.r
        pop hl
        jp hk_vdirty_of

; hk_vinvalidate - cell HL (0..383): unknown in the background, its half dirty.   Preserves HL, DE; clobbers AF, BC
hk_vinvalidate:
        push hl
        push de
        ld de,HK_VT
        add hl,de
        ld (hl),VT_UNKNOWN
        pop de
        pop hl
        push de
        call hk_vdirty_of
        pop de
        ret

;------------------------------------------------------------------------------
; hk_update_bg - bring the background image up to date: tile bank change, dirty halves (full scan), queued static cells.   Clobbers: all
;------------------------------------------------------------------------------
hk_update_bg:
        call hk_clear_pending           ; deferred clears of text screens (ADR-028), then the level scenery (ADR-025) (hk_segs.asm)
        ld hl,(0x7d02)                  ; tile base pointer of the renderer: 751Ch (normal) or 4B14h (boss levels)
        ld de,(hk_bankw)
        or a
        sbc hl,de
        jr z,.bankok
        ld hl,(0x7d02)
        ld (hk_bankw),hl
        ld de,0x751c
        or a
        sbc hl,de
        ld a,0
        jr z,.b0
        inc a
.b0:    ld (hk_bank),a
        ld hl,HK_VT                     ; another tile bank: everything must be redrawn
        ld de,HK_VT+1
        ld bc,383
        ld (hl),VT_UNKNOWN
        ldir
        ld a,3
        ld (hk_dirtyh),a
.bankok:
        call hk_vp_consts
        ld a,(hk_dirtyh)
        ld c,a
        xor a
        ld (hk_dirtyh),a
        bit 0,c
        jr z,.h1
        xor a
        call hk_vp_half
.h1:    bit 1,c
        jr z,.sl
        ld a,1
        call hk_vp_half
.sl:    jp hk_static_list

; hk_vp_consts - program NX = NY = 8, ARG = 0, LOP = COPY, WM = FFFFh once per pass; FC/BC are (re)loaded on demand.
hk_vp_consts:
        call b1_wait_ce
        di                              ; no line interrupt while V9990 registers are written (it changes P#4)
        ld a,40
        out (V9_REGSEL),a
        ld a,8
        out (V9_REGDATA),a              ; R40 NX
        xor a
        out (V9_REGDATA),a              ; R41
        ld a,8
        out (V9_REGDATA),a              ; R42 NY
        xor a
        out (V9_REGDATA),a              ; R43
        out (V9_REGDATA),a              ; R44 ARG
        ld a,LOP_COPY
        out (V9_REGDATA),a              ; R45
        ld a,0xff
        out (V9_REGDATA),a              ; R46
        out (V9_REGDATA),a              ; R47
        ei
        xor a
        ld (hk_bcv),a
        ret

; hk_vp_half - A = half: scan its 12 x 16 cells into the background.   Clobbers: all
hk_vp_half:
        ld (hk_vh),a
        xor a
        ld (hk_vrow),a
.row:   ld a,(hk_vrow)
        ld l,a
        ld h,0
        add hl,hl
        add hl,hl
        add hl,hl
        add hl,hl
        add hl,hl                       ; row * 32
        ld a,(hk_vh)
        rrca
        rrca
        rrca
        rrca
        and 0x10                        ; 0 or 16
        add a,l
        ld l,a
        ld (hk_vc),hl
        ld b,16
.cell:  push bc
        call hk_vp_cell
        ld hl,(hk_vc)
        inc hl
        ld (hk_vc),hl
        pop bc
        djnz .cell
        ld a,(hk_vrow)
        inc a
        ld (hk_vrow),a
        cp 12
        jr nz,.row
        ret

; hk_static_list - send the queued static cells that are still static and pending.   Clobbers: all
hk_static_list:
        ld a,(hk_sn)
        or a
        ret z
        ld b,a
        xor a
        ld (hk_sn),a
        ld hl,HK_SLIST
.lp:    push bc
        ld e,(hl)
        inc hl
        ld d,(hl)
        inc hl
        push hl
        ld (hk_vc),de
        ld hl,HK_VKIND
        add hl,de
        ld a,(hl)
        or a
        jr z,.next                      ; re-rendered as tiles meanwhile: nothing to do (the half scan handled it)
        ld hl,HK_VRAW
        add hl,de
        bit 0,(hl)
        jr z,.next                      ; already sent (by a half scan)
        call hk_vp_cell
.next:  pop hl
        pop bc
        djnz .lp
        ret

; hk_vp_cell - background cell hk_vc: static (text record -> font tiles, hk_emit_static in hk_text.asm) when HK_VKIND, else the tile of the cell map (LMMM from the atlas);
; only sent if the background does not already hold it.   Clobbers: all
hk_vp_cell:
        ld hl,(hk_vc)
        ld de,HK_VKIND
        add hl,de
        ld a,(hl)
        or a
        jr nz,.static
        ld hl,(hk_vc)                   ; tile mode
        ld de,CELLMAP
        add hl,de
        ld a,(hl)
        ld (hk_vt),a
        ld hl,(hk_vc)
        ld de,HK_VT
        add hl,de
        cp (hl)
        ret z                           ; the background already holds this tile
        ld (hl),a
        jp hk_emit_tile
.static:
        ld hl,(hk_vc)
        ld de,HK_VRAW
        add hl,de
        bit 0,(hl)
        jr nz,.send
        ld hl,(hk_vc)
        ld de,HK_VT
        add hl,de
        ld a,(hl)
        cp VT_STATIC
        ret z                           ; unchanged and already in the background
        ld hl,(hk_vc)
        ld de,HK_VRAW
        add hl,de
.send:  res 0,(hl)
        ld hl,(hk_vc)
        ld de,HK_VT
        add hl,de
        ld (hl),VT_STATIC
        jp hk_emit_static

; hk_emit_tile - LMMM of tile hk_vt into cell hk_vc of the BACKGROUND image from the tile atlas (both players): source
; x = (t & 31)*8, y = VR_TILES_Y + set base + (t >> 5)*8, set = main / boss, direct / mirrored (columns 0-7 of a half are mirrored).
;   Clobbers: all
hk_emit_tile:
        ld a,(hk_vt)
        and 31
        add a,a
        add a,a
        add a,a
        ld (hk_sx),a
        xor a
        ld (hk_sx+1),a
        ld a,(hk_vt)
        and 0xe0
        rrca
        rrca                            ; (t >> 5) * 8
        ld l,a
        ld h,0
        ld a,(hk_bank)
        or a
        ld a,(hk_vc)
        jr nz,.boss
        and 8                           ; columns 0-7 of a half: the mirrored set
        ld de,VR_TILES_Y+TS_MAIN
        jr nz,.set
        ld de,VR_TILES_Y+TS_MAIN_M
        jr .set
.boss:  and 8
        ld de,VR_TILES_Y+TS_BOSS
        jr nz,.set
        ld de,VR_TILES_Y+TS_BOSS_M
.set:   add hl,de
        ld (hk_sy),hl
        call hk_bg_xy
        ld hl,8
        ld (hk_nx),hl
        ld (hk_ny),hl
        jp b1_lmmm_start

; hk_bg_xy - hk_dx / hk_dy = background image position of cell hk_vc.   Clobbers: AF, HL, DE
hk_bg_xy:
        ld hl,(hk_vc)
        ld a,l
        and 31
        add a,a
        add a,a
        add a,a
        ld (hk_dx),a
        xor a
        ld (hk_dx+1),a
        ld hl,(hk_vc)
        add hl,hl
        add hl,hl
        add hl,hl
        ld l,h                          ; row (cell / 32)
        ld h,0
        add hl,hl
        add hl,hl
        add hl,hl                       ; row * 8
        ld de,VR_BG_Y
        add hl,de
        ld (hk_dy),hl
        ret

;------------------------------------------------------------------------------
; hk_bg_copy - the HUD image and the viewport background image (VR_HUD + VR_BG, 256x192, contiguous) into the draw page: one opaque LMMM
; (the command engine runs it while the Z80 goes on).
;------------------------------------------------------------------------------
hk_bg_copy:
        ld hl,0
        ld (hk_sx),hl
        ld (hk_dx),hl
        ld hl,VR_BG_Y
        ld (hk_sy),hl
        ld hl,(hk_vpb)
        ld (hk_dy),hl
        ld hl,256
        ld (hk_nx),hl
        ld hl,96
        ld (hk_ny),hl                   ; single HUD: only the viewports are copied into the display buffer
        jp b1_lmmm_start

; hk_hud_line_copy - line VR_VPB_Y - 1 repeats the last HUD line (display line 95): hk_irq switches R#17 in the middle of that line,
; whose rest then shows the line before the displayed buffer (for buffer A the HUD line itself). Once per present: the markers change it.
hk_hud_line_copy:
        ld hl,0
        ld (hk_sx),hl
        ld (hk_dx),hl
        ld hl,VR_HUD_Y+95
        ld (hk_sy),hl
        ld hl,VR_VPB_Y-1
        ld (hk_dy),hl
        ld hl,256
        ld (hk_nx),hl
        ld hl,1
        ld (hk_ny),hl
        jp b1_lmmm_start

; hk_vdy - hk_dy = display buffer line of viewport line A (0..95).   Preserves BC, DE; clobbers AF, HL
hk_vdy:
        push de
        ld e,a
        ld d,0
        ld hl,(hk_vpb)
        add hl,de
        ld (hk_dy),hl
        pop de
        ret

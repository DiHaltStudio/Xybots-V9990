;==============================================================================
;  XYBOTS V9990 B1 - hooks on the engine's frame-buffer writers (entry patches / call-site patches, see build_b1.py)
;  Each hook tells the background cache what the engine is about to do to the frame buffer, executes the instructions the patch replaced
;  and continues in the original routine (or replaces it: DANGER signs). Every hook preserves all registers except where noted.
;==============================================================================

; hk_render - replaces `call render_cellmaps` (7CB5h): the halves selected in view_redraw_mask (FDEAh) are re-rendered from the cell map,
; so their cells are plain tiles again. ADR-017: the original only drew those tiles into the CPU frame buffer, which nothing reads any
; more (the background takes the tiles from the cell map and the 4 bpp atlas), so it is not called; its code is reused (ADR-022).
hk_render:
        ld a,(0xfdea)
        push af
        push bc
        push de
        push hl
        ld c,a
        bit 0,c
        jr z,.p2
        push bc                         ; hk_vclear_half clobbers BC: the mask is kept (both halves at once: mask 3)
        xor a
        call hk_vclear_half
        pop bc
.p2:    bit 1,c
        jr z,.done
        ld a,1
        call hk_vclear_half
.done:  pop hl
        pop de
        pop bc
        pop af
        ret

; hk_clearvp - entry of clear_viewport_fb (37B2h): the half selected by hud_x_offset (B1D6h: 0 or 16) becomes blank static cells; the
;  text record of the half is set to blank by the V9990 and the CPU fill is skipped (ADR-017/018).
;  Replaced instruction: ld hl,0EB00h.
hk_clearvp:
        push af
        push bc
        push de
        push hl
        ld a,(0xb1d6)
        cp 16
        ld a,0
        jr c,.h
        inc a
.h:     call hk_clear_half              ; ADR-028: a second clear of an untouched text screen is deferred (hk_segs.asm)
        pop hl
        pop de
        pop bc
        pop af
        ret

; hk_stripes - entry of fill_stripes (294Ch): HL = EB00h or EB10h, the shop stripes fill that half: recorded as stripes by the the
; V9990, the CPU fill is skipped (ADR-017).  Replaced: ld a,0FFh / ld c,30h.
hk_stripes:
        push af
        push bc
        push de
        push hl
        ld a,l
        and 16
        ld a,0
        jr z,.h
        inc a
.h:     push af
        call hk_vmark_half
        pop af
        ld d,1
        call hk_txt_half
        pop hl
        pop de
        pop bc
        pop af
        ret

; hk_greset - entry of game_reset (2FBDh): the whole frame buffer is zeroed: here the text record (the fill at the end of game_reset is
; replaced by hk_greset_tail).  Replaced instruction: ld a,(6E12h).
hk_greset:
        push bc
        push de
        push hl
        xor a
        call hk_vmark_half
        ld a,1
        call hk_vmark_half
        call hk_txt_clear_all
        pop hl
        pop de
        pop bc
        ld a,(0x6e12)
        jp 0x2fc0

; hk_glyph1 - entry of glyph_fb_small_draw (3F90h): glyph E (font code) of 8 lines at HL (frame buffer). Replaced: ld a,e / exx / ld de,6F94h.
; hk_glyph2 - entry of draw_glyph_fb_2x (400Ah): a glyph of 16 lines at HL.
; ADR-017/018: the glyph is recorded by the V9990 in the text record (hk_text.asm), not drawn into the frame buffer; the cells it covers
; become static cells of the viewport background, composed from the coloured font tiles. The original routine still runs when the glyph reaches below cell row 11 (the frame buffer's
; spill area F700h+ holds engine variables; never seen). Out (as the original): HL = start address,
; DE = glyph pointer 6F94h + 8 * E, BC = 0020h.
; The engine reprints the same text every pass: a glyph whose code, line offset and first cell equal the last print of that cell (and whose
; cell is still static) changes nothing: it is neither marked nor recorded again (ADR-019).
hk_glyph1:
        push af
        ld a,1
        ld (hk_gn),a
        jr hk_glyph
hk_glyph2:
        push af
        ld a,2
        ld (hk_gn),a
hk_glyph:
        push bc
        push de
        push hl
        xor a
        ld (hk_tspill),a
        ld a,e
        sub 0x20
        cp 65
        jr c,.gok
        call hk_tdev_inc                ; a code outside the font (never seen): drawn as a space, counted
        xor a
.gok:   ld (hk_tg),a
        ld a,e
        and 0x7f
        ld b,a                          ; B = glyph code (font code 20h-60h)
        ld a,(hk_gn)
        rrca                            ; bit 7 = 16-line glyph
        and 0x80
        or b
        ld b,a                          ; B = code | mode bit
        ld a,h
        sub 0xeb
        ld d,a                          ; D = cell row of line 0
        ld (hk_tr),a
        ld a,l
        and 31
        ld e,a                          ; E = column
        ld (hk_tc),a
        ld a,l
        and 0xe0                        ; C = line offset inside the cell row (bits 5-7)
        ld c,a
        rlca
        rlca
        rlca
        ld (hk_to),a
        ld a,d
        cp 12
        jp nc,.orig                     ; below the viewports (spill area F700h): only the original
        ld a,c
        or a
        ld a,(hk_gn)
        jr z,.sp
        inc a                           ; cell rows spanned: gn + (offset != 0)
.sp:    add a,d
        cp 13
        jr c,.nosp
        ld a,1
        ld (hk_tspill),a                ; the last lines fall into the spill area: the original runs as well
.nosp:  push de
        ld a,e
        and 16
        rrca
        rrca
        rrca
        rrca
        ld e,a
        ld d,0
        ld hl,hk_huni
        add hl,de
        ld a,(hl)
        pop de
        or a
        jr z,.mark
        ld a,e
        and 16                          ; the half's player on a panel screen (shop / PREPARE / BONUS, hk_shop_half): its text composes
        call hk_shop_half               ; over the panel in the panel's colours, including the first uniform title (ADR-051; before:
        jr nz,.mark                     ; only while shop_mask was set, so a PREPARE TO FIGHT entered without a shop came out raw)
        call hk_keep_de                 ; ADR-028: the cells are written in this pass (D = row, E = column, C = offset)
        call hk_glyph_direct            ; uniform text half (ADR-020): the glyph goes straight into the background with ONE copy of its
        jp .done                        ; tile (what the original did to its frame buffer), then it is recorded
.mark:  ld l,d
        ld h,0
        add hl,hl
        add hl,hl
        add hl,hl
        add hl,hl
        add hl,hl
        ld d,0
        add hl,de                       ; HL = cell index of line 0 (row from the address, column E); D = 0 now
        push hl
        ld de,HK_GLY
        add hl,de
        ld a,(hl)
        cp b
        jr nz,.changed
        pop hl
        push hl
        ld de,HK_VRAW
        add hl,de
        ld a,(hl)
        and 0xe0
        cp c
        jr nz,.changed
        pop hl
        push hl
        ld de,HK_VKIND
        add hl,de
        ld a,(hl)
        or a
        jr nz,.same                     ; same glyph, same offset, still static: nothing changes
.changed:
        pop hl
        push hl
        ld de,HK_GLY
        add hl,de
        ld (hl),b
        pop hl
        ; rows spanned: gn + (offset != 0)
        ld a,c
        or a
        ld a,(hk_gn)
        jr z,.al
        inc a
.al:    ld b,a
.lp:    push hl
        push bc
        ld de,HK_VKIND
        add hl,de
        ld a,(hl)
        or a
        jr nz,.st                       ; already static: its other lines are in the text record
        ld a,c
        or a
        jr z,.st                        ; offset 0: the glyph covers whole cells
        pop bc
        pop hl
        push hl
        push bc
        call hk_txt_clear_cell          ; a tile cell partly covered: the original kept the tile's bits in the other lines (never seen)
        ld de,HK_VKIND
        add hl,de
.st:    ld (hl),1
        ld de,HK_VRAW-HK_VKIND
        add hl,de
        ld a,(hl)
        and 0x1f
        or c
        or 3                            ; pending, written in this pass (bit 1, ADR-028), keep bits 2-4, offset in bits 5-7
        ld (hl),a
        pop bc
        pop hl
        push bc
        call hk_queue_static
        pop bc
        ld de,32
        add hl,de
        ld a,h
        cp 1
        jr c,.nx
        ld a,l
        cp 0x80
        jr nc,.done                     ; beyond cell 383
.nx:    djnz .lp
        jr .done
.same:  pop hl
        call hk_keep_cells              ; written in this pass (ADR-028)
        jr .rec                         ; the record already holds this glyph: nothing to copy (keeps the half's cache valid)
.done:  ld a,(hk_gn)
        add a,a
        add a,a
        add a,a
        ld (hk_tn),a                    ; 8 / 16 lines
        call hk_txt_glyph
.rec:   ld a,(hk_tspill)
        or a
        jr nz,.orig
        pop hl
        pop de
        pop bc
        pop af
        push hl
        ld l,e
        ld h,0
        add hl,hl
        add hl,hl
        add hl,hl
        ld de,0x6f94
        add hl,de
        ex de,hl                        ; DE = glyph pointer, as the original returns it
        pop hl
        ld bc,0x0020
        ret
.orig:  pop hl
        pop de
        pop bc
        pop af
        ld a,(hk_gn)
        cp 2
        ld a,e                          ; replaced instructions (ld a,e / exx / ld de,6F94h), then the original continues
        exx
        ld de,0x6f94
        jp z,0x400f                     ; draw_glyph_fb_2x
        jp 0x3f95                       ; glyph_fb_small_draw

; hk_tdev_inc - count a text-layer event that departs from the frame-buffer original (saturates at FFh; the tests require 0).
;   Clobbers: AF
hk_tdev_inc:
        ld a,(hk_tdev)
        inc a
        ret z
        ld (hk_tdev),a
        ret

; hk_queue_static - cell HL: queue it in HK_SLIST unless the list is full (then the half is scanned instead).   Preserves HL; clobbers AF, DE
hk_queue_static:
        ld a,(hk_sn)
        cp HK_SMAX
        jr nc,.full
        inc a
        ld (hk_sn),a
        dec a
        push hl
        ex de,hl                        ; DE = cell
        ld l,a
        ld h,0
        add hl,hl
        push bc
        ld bc,HK_SLIST
        add hl,bc
        pop bc
        ld (hl),e
        inc hl
        ld (hl),d
        pop hl
        ret
.full:  jp hk_vdirty_of

; hk_vdirty_of - mark the half containing cell HL dirty.   Preserves HL; clobbers AF
hk_vdirty_of:
        ld a,l
        and 16
        ld a,1
        jr z,.h0
        ld a,2
.h0:    push hl
        ld hl,hk_dirtyh
        or (hl)
        ld (hl),a
        pop hl
        ret

; hk_vmark_half - A = half: every cell of the half becomes static, pending, with no glyph memory; the half is dirty.   Clobbers: AF, BC, DE, HL
hk_vmark_half:
        ld (hk_vh),a
        call hk_hclr_reset              ; no longer a lazily clearable text screen (ADR-028)
        call hk_pcache_clear
        call hk_half_base
        ld a,12
.r:     push af
        push hl
        ld b,16
.c:     push hl
        ld de,HK_VKIND
        add hl,de
        ld (hl),1
        ld de,HK_VRAW-HK_VKIND
        add hl,de
        ld (hl),1
        ld de,HK_GLY-HK_VRAW
        add hl,de
        ld (hl),0xff
        pop hl
        inc hl
        djnz .c
        pop hl
        ld de,32
        add hl,de
        pop af
        dec a
        jr nz,.r
        ld a,(hk_vh)
        call hk_half_mode               ; blank / striped: uniform text when the colours are (ADR-020)
        jr hk_half_dirty

; hk_vclear_half - A = half: every cell of the half is a plain tile again (the renderer just drew it); the half is dirty.
;   Clobbers: AF, BC, DE, HL
hk_vclear_half:
        ld (hk_vh),a
        call hk_pcache_clear
        call hk_half_base
        ld a,12
.r:     push af
        push hl
        ld b,16
.c:     push hl
        ld de,HK_VKIND
        add hl,de
        ld (hl),0
        ld de,HK_GLY-HK_VKIND
        add hl,de
        ld (hl),0xff
        pop hl
        inc hl
        djnz .c
        pop hl
        ld de,32
        add hl,de
        pop af
        dec a
        jr nz,.r
        ld a,(hk_vh)                    ; tiles again: not uniform text, not canonical
        ld e,a
        ld d,0
        jp hk_vclear_tail               ; hk_huni / hk_hfb := 0, hk_hclr_reset, then hk_half_dirty (hk_segs.asm)
hk_half_dirty:
        ld a,(hk_vh)
        or a
        ld a,1
        jr z,.d
        ld a,2
.d:     ld hl,hk_dirtyh
        or (hl)
        ld (hl),a
        ret

; hk_half_base - HL = index of the first cell of half hk_vh (0 or 16).
hk_half_base:
        ld a,(hk_vh)
        rrca
        rrca
        rrca
        rrca
        and 0x10
        ld l,a
        ld h,0
        ret

;------------------------------------------------------------------------------
; hk_sign - entry of blit_sign_bitmap (B40Eh), replaced entirely (ADR-017): a DANGER sign (WARNING ARROWS bought, an enemy with a
; straight route LEFT / RIGHT / BEHIND the player) is copied from the 4 bpp sign atlas (VR_SIGN_Y, 24x11, both players) into the draw
; page, opaque like the original's byte stores, over the view and its actors. Nothing marks cells: the page is rebuilt every pass.
; In: HL = draw item {x column in the viewport (0..13), y line, bitmap pointer B469h right / B48Ah left / B4ABh rear}.
; Contract of the original: HL and AF preserved (BC, DE, alternates clobbered).
;------------------------------------------------------------------------------
hk_sign:
        push af
        push hl
        ld a,(hk_prep)
        or a
        jr z,.done                      ; no prepared page (should not happen)
        ld a,(hl)
        add a,a
        add a,a
        add a,a
        ld c,a                          ; C = x in the viewport (column * 8)
        inc hl
        ld a,(hl)
        cp 96
        jr nc,.done                     ; below the viewport
        ld b,a
        push hl
        call hk_vdy                     ; display buffer line
        pop hl
        inc hl
        ld a,(hl)                       ; low byte of the bitmap pointer: 69h right, 8Ah left, else rear
        ld e,0
        cp 0x69
        jr z,.ix
        ld e,24
        cp 0x8a
        jr z,.ix
        ld e,48
.ix:    ld a,e
        ld (hk_sx),a
        ld a,96
        sub b
        cp 11
        jr c,.ny
        ld a,11
.ny:    ld (hk_ny),a                    ; rows clipped at the bottom of the viewport
        ld a,128
        sub c
        cp 24
        jr c,.nx
        ld a,24
.nx:    ld (hk_nx),a                    ; columns clipped at the right edge of the viewport
        ld hl,VR_SIGN_Y
        ld a,(0xa285)                   ; column offset of the viewport being drawn: 0 / 16
        or a
        jr z,.h0
        ld a,c
        add a,128
        ld c,a
.h0:    ld (hk_sy),hl
        ld a,c
        ld (hk_dx),a
        xor a
        ld (hk_sx+1),a
        ld (hk_dx+1),a
        ld (hk_nx+1),a
        ld (hk_ny+1),a
        ld a,LOP_COPY
        call hk_lmmm_op
.done:  pop hl
        pop af
        ret

;------------------------------------------------------------------------------
; hk_print - entry of print_string (40B6h). The engine reprints static texts every pass (e.g. "PRESS FIRE / TO START" of the idle
; player). Frame-buffer modes (E = 1, 2): the key (mode, B = y, C = column, IY = string) is looked up in HK_PCACHE; a hit means the
; same text already stands at that position since the half was last cleared/re-rendered, so the print is skipped: IY is advanced
; exactly like the original (control bytes, gap 40h, budget of 16 glyphs), HL = address of the last glyph, BC preserved, A/DE clobbered.
; A miss records the key and continues into the original. VRAM modes are never cached.
; Replaced instructions: ld a,1 / ld (40FEh),a -> continue at 40BBh.
;------------------------------------------------------------------------------
hk_print:
        ld a,e
        cp 1
        jr z,.fb
        cp 2
        jr nz,.orig
.fb:    ld (hk_pk),a
        ld a,b
        ld (hk_pk+1),a
        ld a,c
        ld (hk_pk+2),a
        push iy
        pop hl
        ld (hk_pk+3),hl
        push bc
        push de
        call hk_pcache_find             ; Z = hit
        jr z,.hit
        call hk_pcache_add
        pop de
        pop bc
.orig:  ld a,1
        ld (0x40fe),a
        jp 0x40bb
.hit:   pop de
        pop bc
        ; skip the print: replicate the cursor and IY advance of print_string
        push bc
        ld a,b
        rrca
        rrca
        rrca
        and 31
        add a,0xeb
        ld h,a                          ; EB00h + (y >> 3) * 256
        ld a,b
        and 7
        rrca
        rrca
        rrca                            ; (y & 7) * 32
        add a,c
        ld l,a                          ; + column = address of the first glyph
        ld b,16                         ; glyph budget
.first: ld a,(iy+0)
        inc iy
        or a
        jr z,.end                       ; empty string
        bit 7,a
        jr nz,.first                    ; control byte (the first glyph does not count against the budget, as in the original)
.next:  ld a,(iy+0)
        inc iy
        or a
        jr z,.end
        cp 0x40
        jr z,.gap
        bit 7,a
        jr nz,.next
        dec b
        jr z,.end                       ; 17th glyph: the original stops here, IY after this byte (ADR-051: an extra decrement for the
                                        ; first glyph left IY ON the terminator of a 16-glyph string such as PREPARE TO FIGHT, so
                                        ; print_text_block read the next record one byte early: MASTER XYBOT printed in VRAM mode on the HUD)
.gap:   inc l
        jr .next
.end:   pop bc
        ret

; hk_pcache_find - entry with the same (y, column) as hk_pk: Z if it also has the same mode and string pointer; NZ otherwise (HL -> the
; entry to update when the position exists, else HL = 0).   Clobbers: AF, BC, DE, HL
hk_pcache_find:
        ld hl,HK_PCACHE
        ld b,HK_PCACHE_N
.e:     ld a,(hl)
        or a
        jr z,.n                         ; free entry
        inc hl
        ld a,(hk_pk+1)
        cp (hl)
        jr nz,.n1
        inc hl
        ld a,(hk_pk+2)
        cp (hl)
        jr nz,.n2
        dec hl
        dec hl                          ; same position: compare mode and pointer
        ld a,(hk_pk)
        cp (hl)
        jr nz,.miss
        inc hl
        inc hl
        inc hl
        ld a,(hk_pk+3)
        cp (hl)
        jr nz,.miss2
        inc hl
        ld a,(hk_pk+4)
        cp (hl)
        jr nz,.miss3
        xor a                           ; hit
        ret
.miss3: dec hl
.miss2: dec hl
        dec hl
        dec hl
.miss:  ld (hk_t0),hl                   ; the entry of this position: to be overwritten
        or 1
        ret
.n2:    dec hl
.n1:    dec hl
.n:     ld de,5
        add hl,de
        djnz .e
        ld hl,0
        ld (hk_t0),hl
        or 1
        ret

; hk_pcache_add - store hk_pk in the entry found for its position, else in the next round-robin slot.   Clobbers: AF, BC, DE, HL
hk_pcache_add:
        ld hl,(hk_t0)
        ld a,h
        or l
        jr nz,.st
        ld a,(hk_pnext)
        ld c,a
        inc a
        cp HK_PCACHE_N
        jr c,.nx
        xor a
.nx:    ld (hk_pnext),a
        ld a,c
        add a,a
        add a,a
        add a,c
        ld l,a
        ld h,0
        ld de,HK_PCACHE
        add hl,de
.st:    ex de,hl
        ld hl,hk_pk
        ld bc,5
        ldir
        ret

;==============================================================================
;  Minimap markers (ADR-013, ADR-016, ADR-054): the original XOR-plots the actor markers into the TMS pattern table twice per pass (draw at
;  BE1Bh, erase at BE31h). Here draw_actor_marker is replaced: markers that blink (type flag bit 0 clear) are collected in HK_MARK0 by the
;  first minimap_actors call of a pass (the second call, the original's erase, is skipped) and drawn by hk_mm_after (hk_segs.asm) when
;  that call returns: the boxes of the previous pass's markers and one map row are copied back from the clean image of the window
;  (VR_MAPC_Y, which gets every wall / door / wipe drawn into VR_HUD), then the new list is XORed on VR_HUD. Static markers (flag bit 0
;  set, drawn once and erased by a second call of the original) are XORed into VR_HUD and into the clean image.
;==============================================================================

; hk_minimap - entry of minimap_actors (3941h). Replaced: ld a,(72A0h). First call of the pass: empty the list and run the original;
; later calls return.
hk_minimap:
        ld a,(hk_mmdone)
        or a
        ret nz
        inc a
        ld (hk_mmdone),a
        ld a,0xff
        ld (hk_mkfirst),a
        xor a
        ld (hk_mkn),a
        ld hl,hk_mm_after
        push hl                         ; the original returns into hk_mm_after (hk_segs.asm): the window is rebuilt right after its HALT
        ld a,(0x72a0)
        jp 0x3944

; (the blinking markers are drawn by hk_mm_after, hk_segs.asm, at the end of the first minimap_actors call of the pass: ADR-054)

; hk_marker - entry of draw_actor_marker (398Fh), replaced entirely (the caller's IX = actor). Marker of the actor's type: 0,2,4,7,8,11,15,
; 16,17 cross (2x2 at x,y), 9,10 ring (3x3 around x,y), 1 player arrow (8x8 at the cell, facing (ix+4), once per pass when both players
; share a cell), others nothing. x = column*8 + fine x (top 3 bits of +1), y = row*8 + fine y (+2), as the original computes them.
hk_marker:
        ld a,(ix+3)
        cp 0x12
        ret nc
        ld hl,hk_mark_kind
        ld e,a
        ld d,0
        add hl,de
        ld a,(hl)
        or a
        ret z                           ; no marker for this type
        cp 3
        jr z,.arrow
        dec a
        ld (hk_mk),a                    ; shape 0 cross / 1 ring
        ld a,(ix+0)
        and 0x0f
        ld c,a
        ld a,(ix+1)
        and 0xe0
        or c
        rlca
        rlca
        rlca
        ld (hk_mk+1),a                  ; x (0..127)
        ld a,(ix+2)
        and 0xe0
        rlca
        rlca
        rlca
        ld c,a
        ld a,(ix+0)
        and 0xf0
        rrca
        or c
        ld (hk_mk+2),a                  ; y (0..127)
        jr .draw
.arrow: ld a,(hk_mkfirst)
        inc a
        jr z,.first                     ; no arrow drawn yet in this pass
        ld a,(0x9a10)                   ; both players in the same cell: one arrow
        ld c,a
        ld a,(0x9a20)
        cp c
        ret z
.first: xor a
        ld (hk_mkfirst),a
        ld a,(ix+4)
        and 3
        add a,2
        ld (hk_mk),a                    ; shape 2 + facing
        ld a,(ix+0)
        and 0x0f
        add a,a
        add a,a
        add a,a
        ld (hk_mk+1),a                  ; x = column * 8
        ld a,(ix+0)
        and 0xf0
        rrca
        ld (hk_mk+2),a                  ; y = row * 8
.draw:  ld a,(hk_mk+2)
        cp 96
        ret nc                          ; below the HUD: the original wrote into the frame-buffer copy area, never visible
        ld a,(ix+3)
        ld e,a
        ld d,0
        ld hl,0x99f7                    ; type flag table: bit 0 = static marker (drawn once, erased by a second call)
        add hl,de
        bit 0,(hl)
        jr z,.list
        ld a,VR_HUD_HI
        ld (hk_mkdy),a
        call hk_mark_lmmm               ; static: XOR into VR_HUD (persistent) ...
        ld a,VR_MAPC_HI
        ld (hk_mkdy),a
        jp hk_mark_lmmm                 ; ... and into the clean image, which rebuilds the window (ADR-054)
.list:  ld a,(hk_mkn)
        cp HK_MKMAX
        ret nc                          ; list full: marker dropped
        inc a
        ld (hk_mkn),a
        dec a
        add a,a
        add a,a
        ld l,a
        ld h,0
        ld de,HK_MARK0
        add hl,de
        ld a,(hk_mk)
        ld (hl),a
        inc hl
        ld a,(hk_mk+1)
        ld (hl),a
        inc hl
        ld a,(hk_mk+2)
        ld (hl),a
        ret

; hk_prep_gate - st_prepare_level's `ld a,(shop_mask)` (281Ch, followed by `and a / ret nz`: keep displaying) is `call hk_prep_gate`. The
; first player to run st_prepare after the last shopper left used to wait 50 frames and start the level before the partner's own
; st_prepare had run once: the partner (player 2, who runs after player 1 in a pass) showed his shop (** DONE **) until the end and his
; PREPARE TO ENTER LEVEL only for an instant. Now it also holds while the partner is in state 21h and has not printed yet (his viewport
; colour byte is not 3xh: st_prepare sets 39h / 3Ah when it prints).   Out: A = 0 go on, else keep displaying.   Clobbers: AF, DE, HL
hk_prep_gate:
        ld a,(0x2207)
        and a
        ret nz                          ; somebody still shops
        ld a,(0xb22d)                   ; cur_slot
        ld hl,0x9a28                    ; partner of player 1: player 2's state, colour byte 9603h
        ld de,0x9603
        and a
        jr z,.p
        ld l,0x18                       ; partner of player 2: player 1
        dec e
.p:     ld a,(hl)
        cp 0x21
        jr nz,.go
        ld a,(de)
        and 0xf0
        cp 0x30
        ld a,1
        ret nz                          ; PREPARE not printed on the partner's half yet
.go:    xor a
        ret

; hk_boss_end - boss_fight_controls' `call boss_end_reset` (38A9h, the winner of a Master Xybot fight): boss_end_reset (330Eh) puts the
; tile set back to 751Ch and clears boss_next_flag / var_72A0 / level_started for BOTH players; while the partner is still fighting its
; own Master Xybot (actor type 1, parts alive in its status +33) that broke its room (redrawn with corridor tiles) and its controls. The
; reset is deferred (hk_bosspend) until the partner wins (here again) or dies (hk_died_boss) (ADR-051).   Clobbers: AF, DE, HL
hk_boss_end:
        ld hl,0x9a23                    ; partner of player 1: player 2's actor type, its parts alive at 9648h
        ld de,0x9648
        ld a,(0xb22d)                   ; cur_slot
        or a
        jr z,.p
        ld l,0x13                       ; partner of player 2: player 1 (type 9A13h, parts 9625h)
        ld de,0x9625
.p:     ld a,(hl)
        dec a
        jr nz,.reset                    ; the partner is not in play
        ld a,(de)
        or a
        jr z,.reset                     ; its Master Xybot is already defeated
        ld a,1
        ld (hk_bosspend),a
        ret
.reset: xor a
        ld (hk_bosspend),a
        jp 0x330e

; hk_died_boss - st_died's `ld a,(var_72A0) / and a / ret z` (32ECh): outside a boss fight the dying player returns at once; in one it
; clears its viewport and its shop_mask bit (and, with nobody left, drops four levels and resets). With a reset deferred by the partner's
; win (hk_bosspend) the fight is over for both: boss_end_reset now, then the clear and the bit as the original does when the partner is
; still present, and st_died is left (ADR-051).   Out (no reset pending): A = var_72A0, Z accordingly, nothing else changed
hk_died_boss:
        ld a,(hk_bosspend)
        or a
        jr nz,.pend
        ld a,(0x72a0)
        or a
        ret
.pend:  xor a
        ld (hk_bosspend),a
        call 0x330e                     ; boss_end_reset
        call 0x37b2                     ; clear_viewport_fb (this player's half)
        ld a,(0xb22d)
        inc a
        cpl
        ld c,a
        ld a,(0x2207)
        and c
        ld (0x2207),a                   ; this player's bit out of shop_mask
        pop hl                          ; leave st_died: the partner goes on (its BONUS / shop / PREPARE)
        ret

; type -> marker kind: 0 none, 1 cross, 2 ring, 3 player arrow (marker table 3F04h)
hk_mark_kind:
        db 1,3,1,0,1,0,0,1,1,2,2,1,0,0,0,1,1,1

; hk_mark_lmmm - XOR-LMMM of marker hk_mk (shape, x, y) into the image whose Y high byte is hk_mkdy (draw page or VR_HUD): cross 2x2 at (64+x, y), ring 3x3 at (63+x, y-1), arrow 8x8
; at (64+x, y). All four edges are clipped to the minimap window, including the atlas offset at the left/top (ADR-055).   Clobbers: all
hk_mark_lmmm:
        ld a,(hk_mk)
        or a
        jr nz,.notcross
        ld hl,0                         ; source x
        ld bc,2*256+2                   ; B = width, C = height
        ld a,(hk_mk+1)
        add a,64
        ld (hk_dx),a
        ld a,(hk_mk+2)
        ld (hk_dy),a
        jr .go
.notcross:
        cp 1
        jr nz,.arrow
        ld hl,8
        ld bc,3*256+3
        ld a,(hk_mk+1)
        add a,63
        ld (hk_dx),a
        ld a,(hk_mk+2)
        or a
        jr z,.clip
        dec a
        ld (hk_dy),a
        jr .go
.clip:  ld hl,VR_MARK_Y+1               ; y-1 < 0: skip the top row of the ring
        ld (hk_sy),hl
        ld hl,8
        ld (hk_sx),hl
        xor a
        ld (hk_dy),a
        ld bc,3*256+2
        jr .go2
.arrow: sub 2
        add a,a
        add a,a
        add a,a
        add a,16
        ld l,a
        ld h,0
        ld bc,8*256+8
        ld a,(hk_mk+1)
        add a,64
        ld (hk_dx),a
        ld a,(hk_mk+2)
        ld (hk_dy),a
.go:    ld (hk_sx),hl
        ld hl,VR_MARK_Y
        ld (hk_sy),hl
.go2:   call hk_mark_clip
        xor a
        ld (hk_dx+1),a
        ld a,(hk_mkdy)
        cp VR_MAPC_HI
        jr nz,.hi
        ld a,(hk_dy)
        add a,VR_MAPC_Y & 0xff          ; the clean image: window line y at VR_MAPC_Y + y (its low byte + 96 < 256: no carry)
        ld (hk_dy),a
        ld a,VR_MAPC_HI
.hi:    ld (hk_dy+1),a
        ld a,b
        ld (hk_nx),a
        xor a
        ld (hk_nx+1),a
        ld a,c
        ld (hk_ny),a
        xor a
        ld (hk_ny+1),a
        ld a,LOP_XOR
        ld c,0xff
        jp hk_lmmm_wm

; hk_mark_clip - low-byte destination (hk_dx, hk_dy), B x C marker size, atlas origin already in hk_sx / hk_sy. Clip to x 64..191,
; y 0..95 before adding the HUD/clean-image Y base. The ring's negative top row was handled above; its negative left column must
; advance SX too. Actor coordinates were checked by hk_marker (x 0..127, y 0..95), so every intersection is nonempty. Clobbers: AF, HL
hk_mark_clip:
        ld a,(hk_dx)
        cp 64
        jr nc,.left
        inc a                           ; only a ring at x = 0 reaches column 63
        ld (hk_dx),a
        ld hl,hk_sx
        inc (hl)                        ; skip the ring's left atlas column
        dec b
.left:  neg
        add a,192
        cp b
        jr nc,.right
        ld b,a
.right: ld a,(hk_dy)
        neg
        add a,96
        cp c
        ret nc
        ld c,a
        ret

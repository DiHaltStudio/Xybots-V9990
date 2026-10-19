;==============================================================================
;  XYBOTS V9990 B1 - native actors (ADR-011): the engine's sprite blitters are replaced by V9990 copies from the 4 bpp sprite atlas.
;
;  draw_actor_sprite (9206h) still does the whole projection (which sprite frame, size class, pixel position, occlusion mask) and then
;  calls one of the three blitters with the contract documented in game_8000.asm:
;     A = pixel shift (x mod 8), B = signed first viewport column, C = top pixel row (0..103), HL = occlusion mask (bit 15 = column 0,
;     1 = hidden by a nearer wall), HL' = sprite bitmap pointer (RAM), B' = rows; width = 1/2/3 source bytes per row by entry.
;  The blitter entries are patched to jump here (build_b1.py). The hooks draw the frame into the draw page with one transparent LMMM
;  from the atlas (index 0 = transparent), then re-copy the wall tiles of the occluded columns over it (walls in front of the actor), and
;  record the covered cells in the page's rectangle list so that the next use of the page restores its background first (hk_prepare).
;  The frame buffer never receives actors any more; the engine's dirty-cell bookkeeping for actors is never reached.
;  After the hook, draw_actor_sprite only executes `pop ix / ret`: everything except SP and IX/IY may be clobbered.
;==============================================================================

hk_blit1:
        ld e,1
        jr hk_blit
hk_blit2:
        ld e,2
        jr hk_blit
hk_blit3:
        ld e,3
hk_blit:
        push ix
        push iy
        ld (hk_sshift),a
        ld a,e
        ld (hk_swid),a
        ld a,b
        ld (hk_scol),a
        ld a,c
        ld (hk_stop),a
        ld (hk_smask),hl
        exx
        ld (hk_sptr),hl
        ld a,b
        ld (hk_srows),a
        exx
        push ix                         ; IX = the actor record (draw_actor_sprite keeps it): 9A20h = player 2's character
        pop hl
        ld a,h
        cp 0x9a
        jr nz,.isp2
        ld a,l
        cp 0x20
.isp2:  ld a,0
        jr nz,.setp2
        inc a
.setp2: ld (hk_p2hero),a
        ld a,(0xa285)                   ; column offset of the viewport being drawn (draw_all_actors patches it: 0 / 16)
        or a
        ld a,0
        jr z,.h
        inc a
.h:     ld (hk_sh),a
        ld a,(hk_prep)
        or a
        jr z,.done                      ; no prepared page (should not happen): drop the sprite
        call hk_spr_lookup              ; hk_sax / hk_say from the RAM pointer; NZ = not found
        jr nz,.done
        call hk_spr_geometry            ; clipping -> hk_sx.. and the covered cells; NZ = nothing visible
        jr nz,.done
        call hk_spr_draw
        call hk_spr_occlude
.done:  pop iy
        pop ix
        ret

;------------------------------------------------------------------------------
; hk_spr_lookup - sprite table entry containing (hk_sptr): atlas x/y of the frame line the pointer points to.
;   Entry i (3 bytes): addr, rows<<2 | width-1. Atlas position of entry i: x = (i mod 10) * 24, y = VR_SPR_Y + tint*720 + (i div 10) * 40.
;   The pointer may point inside the entry (animation frame): y += (ptr - addr) / width.   Out: Z = found.   Clobbers: all
;------------------------------------------------------------------------------
hk_spr_lookup:
        ld a,(hk_sptr+1)
        cp 0x22
        jp nc,.nf                       ; outside the sprite bank 0303h-219Fh and the exit's own frames 21A0h-21A8h
        ld l,a
        ld h,0
        ld de,HK_PAGEIDX
        add hl,de
        ld c,(hl)                       ; C = entry index to start from
        ld l,c
        ld h,0
        ld d,h
        ld e,l
        add hl,hl
        add hl,de                       ; HL = index*3
        ld de,HK_SPRTAB
        add hl,de                       ; HL -> entry
.scan:  ld a,c
        cp HK_SPRTAB_N-1
        jr z,.hit                       ; last entry
        push hl
        inc hl
        inc hl
        inc hl                          ; next entry
        ld e,(hl)
        inc hl
        ld d,(hl)                       ; DE = next addr
        ld hl,(hk_sptr)
        or a
        sbc hl,de                       ; ptr - next.addr
        pop hl
        jr c,.hit                       ; ptr < next.addr: this entry
        inc hl
        inc hl
        inc hl
        inc c
        jr .scan
.hit:   ld e,(hl)
        inc hl
        ld d,(hl)
        inc hl
        ld a,(hl)                       ; rows<<2 | width-1
        and 3
        inc a
        ld b,a                          ; B = width in bytes
        ld hl,(hk_sptr)
        or a
        sbc hl,de                       ; HL = byte offset inside the entry
        ld a,l
        ld d,0                          ; D = row offset = offset / width (offset < 3*63)
.div:   sub b
        jr c,.divd
        inc d
        jr .div
.divd:  push de                         ; D = row offset; BP6: atlas position of entry C from the packing table
        ld l,c
        ld h,0
        ld e,l
        ld d,h
        add hl,hl
        add hl,de                       ; index * 3
        ld de,hk_sprpos
        add hl,de
        ld a,(hl)
        ld (hk_sax),a
        inc hl
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a                          ; atlas line of the sprite
        pop de
        ld e,d
        ld d,0
        add hl,de                       ; + row offset
        ld de,VR_SPR_Y
        ld a,(hk_p2hero)
        or a
        jr z,.base
        ld a,h
        or a
        jr nz,.base
        ld a,l
        cp HERO_LINES
        jr nc,.base                     ; not a player-character frame (they are packed in the first HERO_LINES lines)
        ld de,VR_HERO2_Y                ; player 2's character: its own frames, same x and line offset
.base:  add hl,de
        ld (hk_say),hl
        xor a                           ; Z
        ret
.nf:    or 1
        ret

;------------------------------------------------------------------------------
; hk_spr_geometry - viewport x = column*8 + shift (signed), y = top row; clip to the 128x96 viewport.
;   Sets hk_sx/hk_sy (atlas source), hk_dx/hk_dy (page destination), hk_nx/hk_ny, hk_sc0/scn/sr0/srn (cells).   Out: Z = visible.
;------------------------------------------------------------------------------
hk_spr_geometry:
        ld a,(hk_scol)
        ld c,a
        add a,a
        add a,a
        add a,a
        ld b,a
        ld a,(hk_sshift)
        add a,b
        ld (hk_sx0),a                   ; x (signed: column*8 + shift, -23..127)
        ld a,(hk_swid)
        add a,a
        add a,a
        add a,a
        ld e,a                          ; E = width in pixels
        ld a,(hk_stop)
        cp 96
        jp nc,.invisible
        ld d,a                          ; D = y
        ld a,(hk_srows)
        ld b,a                          ; B = rows
        add a,d
        cp 96
        jr c,.yok
        ld a,96
        sub d
        ld b,a                          ; clipped rows
.yok:   ld a,b
        or a
        jp z,.invisible
        ld (hk_ny),a
        xor a
        ld (hk_ny+1),a
        ld a,(hk_sax)
        ld (hk_sx),a
        ld (hk_sx+1),a                  ; (high byte set below)
        xor a
        ld (hk_sx+1),a
        ld hl,(hk_say)
        ld (hk_sy),hl
        ld a,(hk_sx0)
        bit 7,a
        jr z,.left_ok
        ; partly left of the viewport: skip -x source columns
        neg
        ld c,a                          ; C = pixels cut on the left
        ld a,(hk_sx)
        add a,c
        ld (hk_sx),a
        ld a,e
        sub c
        jp c,.invisible
        jp z,.invisible
        ld e,a
        xor a                           ; destination x = 0
.left_ok:
        ld c,a                          ; C = destination x inside the viewport
        add a,e
        jr nc,.rt
        ; x + width > 255: impossible (x <= 127, width <= 24)
.rt:    cp 129
        jr c,.right_ok
        ld a,128
        sub c
        ld e,a                          ; clipped width
.right_ok:
        ld a,e
        ld (hk_nx),a
        xor a
        ld (hk_nx+1),a
        ld a,(hk_sh)
        rrca                            ; 0 / 80h
        add a,c
        ld (hk_dx),a
        ld a,(hk_sh)
        ld (hk_dx+1),a                  ; bit 8 of x for the right viewport (128 + x >= 256 never: x < 128) -> dx high = 0
        xor a
        ld (hk_dx+1),a
        ld a,(hk_sh)
        or a
        jr z,.dxok
        ld a,(hk_dx)
        ld (hk_dx),a
.dxok:  ld a,(hk_stop)
        call hk_vdy
        ; cells covered (viewport columns): first = C/8, count = ceil((C+E)/8) - first; rows: first = y/8, count
        ld a,c
        rrca
        rrca
        rrca
        and 31
        ld (hk_sc0),a
        ld b,a
        ld a,c
        add a,e
        dec a
        rrca
        rrca
        rrca
        and 31
        sub b
        inc a
        ld (hk_scn),a
        ld a,(hk_stop)
        rrca
        rrca
        rrca
        and 31
        ld (hk_sr0),a
        ld b,a
        ld a,(hk_stop)
        ld c,a
        ld a,(hk_ny)
        add a,c
        dec a
        rrca
        rrca
        rrca
        and 31
        sub b
        inc a
        ld (hk_srn),a
        xor a                           ; Z
        ret
.invisible:
        or 1
        ret

;------------------------------------------------------------------------------
; hk_spr_draw - transparent LMMM of the clipped frame: R32-R47 from hk_sx.., LOP = copy with TP, write mask FFFFh, then the opcode.   Clobbers: all
;------------------------------------------------------------------------------
hk_spr_draw:
        jp hk_lmmm_tp                   ; sets the write mask (a recolouring command may have left a partial one, ADR-020)

;------------------------------------------------------------------------------
; hk_spr_occlude - for every covered viewport column whose mask bit is set, copy the background of the covered cell rows of that column
; back over the actor (walls in front of it): one LMMM of 8 x (rows*8) pixels from the background image.
;------------------------------------------------------------------------------
hk_spr_occlude:
        ld hl,(hk_smask)
        ld a,h
        or l
        ret z
        ld a,(hk_sc0)
        ld b,a
        inc b
.sh:    dec b
        jr z,.shd
        add hl,hl                       ; bit 15 = column hk_sc0
        jr .sh
.shd:   ld a,(hk_scn)
        ld b,a
.col:   push bc
        push hl
        add hl,hl                       ; carry = this column blocked
        jr nc,.next
        ld a,(hk_scn)
        sub b
        ld hl,hk_sc0
        add a,(hl)                      ; column = sc0 + (scn - b)
        ld l,a
        ld a,(hk_sh)
        add a,a
        add a,a
        add a,a
        add a,a                         ; half * 16
        add a,l                         ; cell column 0..31
        add a,a
        add a,a
        add a,a                         ; x = column * 8 (<= 248: fits in a byte)
        ld (hk_sx),a
        ld (hk_dx),a
        xor a
        ld (hk_sx+1),a
        ld (hk_dx+1),a
        ld a,(hk_sr0)
        add a,a
        add a,a
        add a,a
        ld l,a
        ld h,0
        ld de,VR_BG_Y
        add hl,de
        ld (hk_sy),hl                   ; background row
        ld a,(hk_sr0)
        add a,a
        add a,a
        add a,a
        call hk_vdy
        ld hl,8
        ld (hk_nx),hl
        ld a,(hk_srn)
        add a,a
        add a,a
        add a,a
        ld (hk_ny),a
        xor a
        ld (hk_ny+1),a
        call b1_lmmm_start
.next:  pop hl
        add hl,hl
        pop bc
        djnz .col
        ret

;------------------------------------------------------------------------------
; hk_prepare - entry hook of draw_all_actors (9D7Eh): bring the draw page's background up to date before the engine projects the
; actors (which the blit hooks then draw straight into the page). Replaced instructions: ld a,6 / ld (920Ah),a.   Preserves all
;------------------------------------------------------------------------------
hk_prepare:
        push af
        push bc
        push de
        push hl
        push ix
        push iy
        call hk_prepare_page
        pop iy
        pop ix
        pop hl
        pop de
        pop bc
        pop af
        ld a,6
        ld (0x920a),a
        jp 0x9d83

; hk_prepare_page - wait for the previous flip, colour rows / tints, background image up to date, background -> draw page.
hk_prepare_page:
        call hk_update_bg               ; VR_BG is never on screen: brought up to date while the display still shows the other buffer
        call hk_wait_flip
        call hk_bg_copy
        xor a
        call hk_shop_page_colour        ; canonical text halves get their colour on the page; shop art keeps its palette
        ld a,1
        call hk_shop_page_colour
        call hk_shop_present            ; purchase panel, spaced text rows and inactive partner invitation
        ld a,1
        ld (hk_prep),a
        ret

; hk_sprpos - per sprite entry: atlas x, atlas line (word, from VR_SPR_Y) of the packed sprite atlas (tools/assets4.py)
hk_sprpos:
        incbin "../build/assets4/sprpos.bin"

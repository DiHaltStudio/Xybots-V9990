; Arcade shop presentation. All prices, offered items, cursor and purchases remain in the original engine.
; shop_mask at 2207h belongs to that engine: bit 0/1 means that player is shopping.

; hk_emit_static setup: clear a text cache cell, select white or yellow variants of the existing MSX font.
; Record, hk_ebase and destination coordinates were already set by the ordinary compositor.
hk_shop_cell:
        ld hl,(hk_vc)
        ld a,l
        and 16
        call hk_shop_half                ; 0 or 16 also selects half 0/1
        ld (hk_theme),a
        ret z
        ld a,1
        ld (hk_theme),a
        ld hl,8
        ld (hk_ny),hl
        xor a
        call hk_lmmv_raw                 ; text-only cache: copied over the panel at presentation time
        ld hl,VR_SHOPFONT_Y
        ld a,(hk_ecol)
        and 15
        cp 6                            ; original red cursor paper -> yellow lettering
        jr nz,.font
        ld de,24
        add hl,de
.font:  ld (hk_ev8),hl
        ld hl,VR_VF16_FB_Y
        ld (hk_ev16),hl
        ret

; Green invitation: PRESS FIRE TO START (sub-state 1Ch) and, with its second line replaced, PRESS FIRE TO CONTINUE (1Dh, ADR-036); never
; over a partner's shop/prepare/play screen.
hk_shop_invite:
        ld a,(0x9a13)                   ; subtype is meaningful only for a state actor (type FFh)
        inc a
        jr nz,.right
        ld a,(0x9a18)
        ld hl,0
        call .which
.right: ld a,(0x9a23)
        inc a
        ret nz
        ld a,(0x9a28)
        ld hl,128
.which: cp 0x1c
        jr z,.draw
        cp 0x1d
        ret nz
        call .draw                      ; (leaves hk_dx = the half's x)
        jp hk_invite_cont
.draw:  ld (hk_dx),hl
        ld hl,128
        ld (hk_sx),hl
        ld (hk_nx),hl
        ld hl,VR_SHOP_Y
        ld (hk_sy),hl
        ld hl,(hk_vpb)
        ld (hk_dy),hl
        ld hl,96
        ld (hk_ny),hl
        jp b1_lmmm_start

; Reflow only the visible copies; the original text record and cursor addresses stay intact.
hk_shop_panel:
        ld (hk_shop_half_id),a
        call hk_shop_half               ; Z: no panel on this half
        ret z
        ld a,(hk_shop_half_id)
        rrca                            ; 0 / 80h, CY = half
        ld (hk_shop_x),a
        ld hl,0x9a18
        jr nc,.sub
        ld l,0x28
.sub:   ld a,(hl)
        cp 0x25                         ; BONUS screen (ADR-036): the navy panel, the text over it as it is, like PREPARE
        jp z,hk_shop_prep_draw
        ld a,(hk_shop_half_id)
        call hk_shop_gate               ; not shopping, or PREPARE TO ENTER LEVEL drawn (same navy panel, text not reflowed): done
        ret z
        ld a,(hk_shop_half_id)
        or a
        ld a,(0x9621)                   ; status + 29: offered item count
        ld b,0
        jr z,.count
        ld a,(0x9644)
        ld b,128
.count: ld (hk_shop_count),a
        ld a,b
        ld (hk_shop_x),a
        call hk_shop_backdrop
        call hk_half_ready              ; the menu is not fully printed yet (the previous screen's text is still in the cache): panel only
        ret nz
        ld a,(hk_shop_count)
        cp 3
        ld a,12
        jr c,.pitch
        ld a,(hk_shop_count)
        cp 4
        ld a,10
        jr c,.pitch
        ld a,8
.pitch: ld (hk_shop_pitch),a
        ld a,7
        ld (hk_shop_src),a
        ld a,8
        ld (hk_shop_dst),a
        xor a
        call hk_shop_band               ; title, with its original indentation
        ld a,23
        ld (hk_shop_src),a
        ld a,24
        ld (hk_shop_dst),a
        xor a
        ld (hk_shop_row),a
.row:   ld a,(hk_shop_count)
        ld b,a
        ld a,(hk_shop_row)
        cp b
        jr z,.done
        ld c,a
        ld a,(hk_shop_half_id)
        add a,a
        add a,a
        add a,a
        add a,c
        ld l,a
        ld h,0
        ld de,0x21a3                    ; original offered-item list
        add hl,de
        ld e,(hl)
        ld d,0
        ld hl,0x2a62                    ; original name widths
        add hl,de
        ld a,(hl)
        cp 14
        ld a,0
        jr nc,.copy                     ; longest names need the full viewport width
        ld a,4                          ; inset the price and text on ordinary rows
.copy:  call hk_shop_band
        ld hl,hk_shop_row
        inc (hl)
        ld a,(hk_shop_src)
        add a,8
        ld (hk_shop_src),a
        ld a,(hk_shop_pitch)
        ld hl,hk_shop_dst
        add a,(hl)
        ld (hl),a
        jr .row
.done:  ld a,(hk_shop_src)
        add a,8
        ld (hk_shop_src),a
        ld a,(hk_shop_dst)
        add a,8
        ld (hk_shop_dst),a
        xor a
        jp hk_shop_band                 ; DONE retains its original centered indentation

; hk_half_ready - Z when half hk_shop_half_id shows its own screen's text: not the first panel page of this screen (the player's sub-state
; is the one seen at the previous panel page of the half, hk_shop_last) and all 192 cells composed static text (HK_VT = VT_STATIC).
; Entering the shop, the first page still finds the previous screen's text, fully composed, in the cache (the engine clears it and
; prints the menu before the next page, the shop's own wait is 6 frames): without this the panel showed garbled bands of it (ADR-036).
;   Clobbers: AF, BC, DE, HL
hk_half_ready:
        ld hl,0x9a18                    ; player 1's sub-state
        ld de,hk_shop_last
        ld a,(hk_shop_half_id)
        or a
        jr z,.p
        ld l,0x28                       ; player 2's
        inc de
.p:     ld a,(de)
        cp (hl)
        ld a,(hl)
        ld (de),a
        ret nz                          ; first page of a new panel screen
        ld hl,HK_VT
        ld a,(hk_shop_half_id)
        or a
        jr z,.s
        ld l,16                         ; HK_VT is 256-aligned
.s:     ld c,12
.r:     ld b,16
.c:     ld a,(hl)
        cp VT_STATIC
        ret nz
        inc hl
        djnz .c
        ld de,16
        add hl,de
        dec c
        jr nz,.r
        xor a
        ret

; hk_invite_cont - the green invitation was just drawn at hk_dx (0 / 128): its second line becomes TO CONTINUE (ADR-036): the plain
; green band of lines 72-87 of the panel over TO START (lines 48-63), then the glyphs, transparent, from the large font in F0 (white,
; the colour the invitation's text is drawn in by tools/hud4.py).   Clobbers: all
hk_invite_cont:
        ld a,(hk_dx)
        add a,20                        ; (128 - 11 * 8) / 2
        ld c,a
        ld hl,128
        ld (hk_sx),hl
        ld (hk_nx),hl
        ld hl,VR_SHOP_Y+72
        ld (hk_sy),hl
        ld hl,(hk_vpb)
        ld de,48
        add hl,de
        ld (hk_dy),hl
        ld hl,16
        ld (hk_ny),hl
        push bc
        call b1_lmmm_start
        pop bc
        ld hl,8
        ld (hk_nx),hl
        ld hl,.txt
.g:     ld a,(hl)
        or a
        ret z
        push hl
        push bc
        sub 0x20                        ; glyph g: x = (g & 31) * 8, y = VR_VF16_FB_Y + (g >> 5) * 16
        ld b,a
        and 31
        add a,a
        add a,a
        add a,a
        ld l,a
        ld h,0
        ld (hk_sx),hl
        ld a,b
        and 32
        rrca
        ld e,a
        ld d,0
        ld hl,VR_VF16_FB_Y
        add hl,de
        ld (hk_sy),hl
        ld l,c
        ld h,0
        ld (hk_dx),hl
        call hk_lmmm_tp
        pop bc
        ld a,c
        add a,8
        ld c,a
        pop hl
        inc hl
        jr .g
.txt:   db "TO CONTINUE",0

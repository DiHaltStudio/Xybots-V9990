; XYBOTS V9990 B1 - hook routines placed in DEAD code of the game image (ADR-022). Each block is assembled at the address of a routine
; body the port replaced (never executed; nothing live jumps or points into it: checked by build_b1.py) and patched into the game
; image by the build, so no stage B chunk is needed. Blocks: hk_segN .. hk_segN_end, in this order in the assembler output.

        org 0x8f20
hk_seg1:
;------------------------------------------------------------------------------
; hk_glyph_direct - glyph hk_tg (8 lines when hk_gn = 1, 16 when 2) into the background at cell row hk_tr, column hk_tc, first line
; hk_to: ONE LMMM of the glyph tile from the font variant of the half's colour (FALLBACK_COL sheets when the half is canonical). Only
; for a uniform text half (hk_huni): there the composition of any cell from its record is exactly this copy. Lines below the viewport
; are clipped.   Clobbers: all
;------------------------------------------------------------------------------
hk_glyph_direct:
        ld a,(hk_tc)
        and 16
        rrca
        rrca
        rrca
        rrca
        ld e,a                          ; E = half
        ld d,0
        ld hl,hk_hfb
        add hl,de
        ld a,(hl)
        or a
        jr nz,.canon
        ld a,e
        rlca
        rlca
        rlca
        rlca
        ld l,a
        ld h,0
        ld de,HK_CELLCOL
        add hl,de
        ld c,(hl)                       ; C = colour byte of the half
        ld a,(hk_gn)
        cp 2
        ld a,c
        jr z,.v16
        ld hl,hud_vfont8_cols
        ld b,VF8_NV
        call hk_find
        ld de,VF8_VL
        ld hl,VR_VF8_Y
        jr .vb
.v16:   ld hl,hud_vfont16_cols
        ld b,VF16_NV
        call hk_find
        ld de,VF16_VL
        ld hl,VR_VF16_Y
.vb:    call hk_vbase
        ld a,h
        inc a
        ret z                           ; no variant (cannot happen: a half with such a colour is canonical)
        jr .base
.canon: ld a,(hk_gn)
        cp 2
        ld hl,VR_VF8_FB_Y
        jr nz,.base
        ld hl,VR_VF16_FB_Y
.base:  ld a,(hk_tg)
        ld c,a
        and 31
        add a,a
        add a,a
        add a,a
        ld (hk_sx),a                    ; x = (g & 31) * 8
        xor a
        ld (hk_sx+1),a
        ld (hk_dx+1),a
        ld (hk_nx+1),a
        ld (hk_ny+1),a
        ld a,c
        rlca
        rlca
        rlca
        and 3
        add a,a
        add a,a
        add a,a                         ; (g >> 5) * 8
        ld e,a
        ld a,(hk_gn)
        cp 2
        ld a,e
        jr nz,.r
        add a,a                         ; 16-line rows
.r:     ld e,a
        ld d,0
        add hl,de
        ld (hk_sy),hl
        ld a,(hk_tc)
        and 31
        add a,a
        add a,a
        add a,a
        ld (hk_dx),a
        ld a,(hk_tr)
        add a,a
        add a,a
        add a,a
        ld e,a
        ld a,(hk_to)
        add a,e                         ; y0 = row * 8 + line (0..95)
        ld e,a
        ld hl,VR_BG_Y
        add hl,de
        ld (hk_dy),hl
        ld a,(hk_gn)
        add a,a
        add a,a
        add a,a
        ld c,a                          ; C = 8 / 16 lines
        ld a,96
        sub e                           ; lines left in the viewport
        cp c
        jr nc,.ny
        ld c,a
.ny:    ld a,c
        ld (hk_ny),a
        ld a,8
        ld (hk_nx),a
        ld a,LOP_COPY
        jp hk_lmmm_op
; hk_cmd_start - opcode A into R#52 (starts the command).   Clobbers: AF, B   (moved here from hk_hud.asm for room, ADR-040)
hk_cmd_start:
        ld b,a
        di
        ld a,52
        out (V9_REGSEL),a
        ld a,b
        out (V9_REGDATA),a
        ei
        ret
hk_seg1_end:
        assert hk_seg1_end <= 0x8ff4

        org 0x3adb
hk_seg2:
;------------------------------------------------------------------------------
; hk_waiting - replaces the drawing tail of st_waiting (2243h-2264h; IX = actor, (ix+9) = y 10h..40h of the bouncing "WAITING...").
; User decision (ADR-021): the original printed the text into its frame buffer at the new y and cleared only one glyph, leaving a trail
; of the previous positions; here, in a uniform text half, the whole half (ADR-051: rows 2-9 before, which left the rows 1 and 10 of the
; Master Xybot BONUS text) is erased with one rectangle in the background and one in the record, then the text is printed (one tile copy
; per glyph). Other halves: the original tail.
;------------------------------------------------------------------------------
hk_waiting:
        ld a,(0xb1d6)                   ; hud_x_offset: 0 / 16
        rrca
        rrca
        rrca
        rrca
        and 1
        ld e,a
        ld d,0
        ld hl,hk_huni
        add hl,de
        ld a,(hl)
        or a
        jp z,.orig
        push de
        ld a,e
        rrca
        and 0x80
        ld (hk_dx),a                    ; x = half * 128
        xor a
        ld (hk_dx+1),a
        ld (hk_nx+1),a
        ld (hk_ny+1),a
        ld hl,VR_BG_Y
        ld (hk_dy),hl
        ld a,128
        ld (hk_nx),a
        ld a,96
        ld (hk_ny),a
        ld hl,hk_hfb
        add hl,de
        ld a,(hl)
        or a
        ld a,0                          ; canonical half: its paper is 0 in the background
        jr nz,.p
        ld a,e
        rlca
        rlca
        rlca
        rlca
        ld l,a
        ld h,0
        ld bc,HK_CELLCOL
        add hl,bc
        ld a,(hl)
.p:     call hk_lmmv                    ; background band := paper
        pop de
        ld a,e
        or a
        ld hl,VR_REC_Y
        jr z,.r
        ld hl,VR_REC_Y+12
.r:     ld (hk_dy),hl
        ld hl,0
        ld (hk_dx),hl
        ld h,1
        ld (hk_nx),hl
        ld hl,12
        ld (hk_ny),hl
        ld a,0xff
        call hk_lmmv_raw                ; record of the half := blank
        ld a,(0xb1d6)
        ld l,a
        ld h,0
        ld de,HK_GLY
        add hl,de
        ld c,12
.g:     push hl
        ld b,16
.gc:    ld (hl),0xff                    ; no glyph remembered in the band: the print draws again
        inc hl
        djnz .gc
        pop hl
        ld de,32
        add hl,de
        dec c
        jr nz,.g
        call hk_pcache_clear
        call .print
        ei
        ret
.orig:  call .print
        ld a,c
        add a,6
        ld c,a
        ld a,b
        add a,16
        ld b,a
        ld e,0x20
        call 0x3ff7                     ; glyph_fb_large: the original's blank glyph
        ei
        ret
.print: ld a,(0xb1d6)
        add a,3
        ld c,a
        ld b,(ix+9)
        ld iy,0x227b                    ; "WAITING..."
        ld e,2
        jp 0x40b6                       ; print_string (BC preserved). No DI here (the original's 2252h): it would hold the line interrupt for
                                        ; the whole print (~14 display lines) and the split screen would start the viewports late
hk_seg2_end:
        assert hk_seg2_end <= 0x3ba0

        org 0x2cf0
hk_seg3:
; hk_half_colour - half A gets colour byte E in every cell (ADR-020). A canonical half keeps its composition (the page pass recolours it:
; the colour cycles of the WAITING / bonus screens cost nothing here); otherwise the cells whose colour changes are recomposed by the
; next background update. Then hk_half_mode re-evaluates the half (a mode change recomposes it) and the tint follows.   Clobbers: all
hk_half_colour:
        ld (hk_vh),a
        ld a,e
        ld (hk_hc),a
        ld a,(hk_vh)
        ld e,a
        ld d,0
        ld hl,hk_hfb
        add hl,de
        ld a,(hl)
        ld (hk_hfbo),a                  ; canonical before the change: no per-cell invalidation
        or a
        jr z,.cells
        ; canonical half: the composition does not depend on the colour: fill the model and check the new colour is still one
        ; without a variant (the colour cycles of the bonus / WAITING screens: no scan, no redraw)
        call hk_half_base
        ld de,HK_CELLCOL
        add hl,de
        ld a,(hk_hc)
        ld c,12
.fr:    ld b,16
.fc:    ld (hl),a
        inc hl
        djnz .fc
        ld de,16
        add hl,de
        dec c
        jr nz,.fr
        ld hl,hud_vfont8_cols
        ld b,VF8_NV
        call hk_find
        inc a
        jr z,.still
        ld a,(hk_hc)
        ld hl,hud_vfont16_cols
        ld b,VF16_NV
        call hk_find
        inc a
        jr z,.still
        ld a,(hk_vh)                    ; the new colour has variants: normal composition again
        ld e,a
        ld d,0
        ld hl,hk_hfb
        add hl,de
        ld (hl),d
        call hk_half_unknown_h
.still: ret
.cells: call hk_half_base
        ld c,12
.qr:    ld b,16
.qc:    push hl
        ld de,HK_CELLCOL
        add hl,de
        ld a,(hk_hc)
        cp (hl)
        ld (hl),a
        pop hl
        jr z,.n
        ld a,(hk_hfbo)
        or a
        call z,hk_vinvalidate
.n:     inc hl
        djnz .qc
        ld de,16
        add hl,de
        dec c
        jr nz,.qr
        ld a,(hk_vh)
        call hk_half_mode
        ret
; hk_draw_icon - (moved from the runtime, ADR-036) entry of hud_draw_icon (2D88h), replaced: A = slot, E = icon 0..32. Transparent LMMM 8x11 from the icon variant of the
; cell's colour (the original ORed the icon into the area cleared by hud_clear_slot). EI at exit.
hk_draw_icon:
        push de
        call hk_slot_xy
        ld de,8*256+11
        call hk_set_dxy
        pop de
        call hk_icon_src
        call hk_lmmm_tp
        ei
        ret
hk_seg3_end:
        assert hk_seg3_end <= 0x2d88

        org 0x8bd2
hk_seg4:
;------------------------------------------------------------------------------
; hk_half_mode - half A: hk_huni = every cell static with one colour byte; hk_hfb = uniform and that colour has no variant in a viewport
; font (the half is composed canonically and recoloured on the page). A change of hk_hfb recomposes the half.   Clobbers: all
;------------------------------------------------------------------------------
hk_half_mode:
        ld (hk_vh),a
        call hk_half_base
        push hl
        ld de,HK_CELLCOL
        add hl,de
        ld e,(hl)                       ; E = colour of the first cell
        pop hl
        ld d,1                          ; D = uniform and static so far
        ld c,12
.row:   ld b,16
.cell:  push hl
        push de
        ld de,HK_CELLCOL
        add hl,de
        pop de
        ld a,(hl)
        cp e
        jr nz,.no
        push de
        ld de,HK_VKIND-HK_CELLCOL
        add hl,de
        pop de
        ld a,(hl)
        or a
        jr nz,.ok
.no:    ld d,0
.ok:    pop hl
        inc hl
        djnz .cell
        push de
        ld de,16
        add hl,de
        pop de
        dec c
        jr nz,.row
        ld a,e
        ld (hk_hc),a
        ld a,d
        or a
        jr z,.plain
        ld a,e
        ld hl,hud_vfont8_cols
        ld b,VF8_NV
        call hk_find                    ; (clobbers BC, HL)
        inc a
        jr z,.fb
        ld a,(hk_hc)
        ld hl,hud_vfont16_cols
        ld b,VF16_NV
        call hk_find
        inc a
        jr z,.fb
.plain: ld c,0                          ; C = canonical
        jr .store
.fb:    ld c,1
.store: ld b,d                          ; B = uniform, C = canonical
        ld a,(hk_vh)
        ld e,a
        ld d,0
        ld hl,hk_huni
        add hl,de
        ld (hl),b
        inc hl
        inc hl
        ld a,(hl)
        ld (hl),c
        cp c
        ret z
        jp hk_half_unknown_h            ; mode changed: recompose the half
; hk_half_unknown_h - the half hk_vh: every cell unknown in the background, half dirty.   Clobbers: all
hk_half_unknown_h:
        call hk_half_base
        jp hk_half_unknown
hk_seg4_end:
        assert hk_seg4_end <= 0x8c50

        org 0xa2fc
hk_seg5:
; hk_top_copy - replaces `call copy_fb_to_vram_top` (BDB2h, once at the engine's init): the panel of hud.tmx is composed in VR_HUD, one
; LMMM per cell from the panel tile atlas. The map (384 tile numbers) is read back from VRAM (uploaded by the boot) into HK_HUDMAP.
hk_top_copy:
        call b1_wait_ce
        di                              ; no line interrupt while V9990 registers are written (it changes P#4)
        ld a,R_VRAMR
        out (V9_REGSEL),a
        ld hl,(HUD_MAP_LINE * 256) & 0xffff
        ld a,l
        out (V9_REGDATA),a
        ld a,h
        out (V9_REGDATA),a
        ld a,(HUD_MAP_LINE * 256) >> 16
        out (V9_REGDATA),a
        ei
        ld hl,HK_HUDMAP
        ld bc,384
.rd:    in a,(V9_VRAM)
        ld (hl),a
        inc hl
        dec bc
        ld a,b
        or c
        jr nz,.rd
        ld hl,8
        ld (hk_nx),hl
        ld (hk_ny),hl
        ld hl,HK_HUDMAP
        ld c,0                          ; C = row
.row:   ld b,0                          ; B = column
.cell:  push bc
        push hl
        ld a,(hl)                       ; tile t
        ld e,a
        and 31
        add a,a
        add a,a
        add a,a
        ld (hk_sx),a
        xor a
        ld (hk_sx+1),a
        ld a,e
        and 0xe0
        rrca
        rrca                            ; (t >> 5) * 8
        ld l,a
        ld h,0
        ld de,VR_HUDT_Y
        add hl,de
        ld (hk_sy),hl
        ld a,b
        add a,a
        add a,a
        add a,a
        ld (hk_dx),a
        xor a
        ld (hk_dx+1),a
        ld a,c
        add a,a
        add a,a
        add a,a
        ld (hk_dy),a
        ld a,VR_HUD_HI
        ld (hk_dy+1),a
        call b1_lmmm_start
        pop hl
        pop bc
        inc hl
        inc b
        ld a,b
        cp 32
        jr nz,.cell
        inc c
        ld a,c
        cp 12
        jr nz,.row
        jp hk_mapc_init                 ; the minimap window of the composed HUD is the first clean image (ADR-054)
; hk_shop_prep - hk_shop_half_id = a half that hk_shop_half accepted. Z: the player is in the shop (the caller lays the menu out).
; NZ: PREPARE TO ENTER LEVEL screen, drawn (hk_shop_prep_draw).   Clobbers: all
hk_shop_prep:
        ld a,(hk_shop_half_id)
        or a
        ld a,(0x2207)
        ld b,0
        jr z,.m
        rrca
        ld b,128
.m:     and 1
        xor 1
        ret z
        ld a,b
        ld (hk_shop_x),a
        rlca                            ; 0 / 1
        ld l,a
        ld h,0
        ld de,0x9602                    ; viewport colour bytes: st_prepare sets 39h / 3Ah when it clears the shop text and prints its own
        add hl,de
        ld a,(hl)
        and 0xf0
        cp 0x30
        jp z,hk_shop_prep_draw
        xor a                           ; the shop menu is still in the text record (the passes before st_prepare runs): shop layout
        ret
hk_seg5_end:
        assert hk_seg5_end <= 0xa3a8

        org 0x7d35
hk_seg6:
; hk_page_recolour - half A: when composed canonically, recolour it from the background into the draw page (after the background copy,
; before the sprites).   Clobbers: all
hk_page_recolour:
        ld e,a
        ld d,0
        ld hl,hk_hfb
        add hl,de
        ld a,(hl)
        or a
        ret z
        ld a,e
        rrca
        and 0x80
        ld (hk_sx),a
        ld (hk_dx),a                    ; x = half * 128
        xor a
        ld (hk_sx+1),a
        ld (hk_dx+1),a
        ld (hk_nx+1),a
        ld (hk_ny+1),a
        ld hl,VR_BG_Y
        ld (hk_sy),hl
        ld hl,(hk_vpb)
        ld (hk_dy),hl
        ld a,128
        ld (hk_nx),a
        ld a,96
        ld (hk_ny),a
        ld a,e
        rrca
        rrca
        rrca
        rrca                            ; half * 16 = its first cell
        ld l,a
        ld h,0
        ld de,HK_CELLCOL
        add hl,de
        ld a,(hl)
        jp hk_recolour
; hk_clear_full - C = half, B = its bit: full clear, then the half is a text screen (hk_hclr).   Clobbers: all
hk_clear_full:
        push bc
        ld a,c
        call hk_vmark_half              ; (resets the hk_hclr bit)
        pop bc
        push bc
        ld a,c
        ld d,0
        call hk_txt_half                ; record of the half := blank
        pop bc
        ld a,(hk_hclr)
        or b
        ld (hk_hclr),a
        ret
hk_seg6_end:
        assert hk_seg6_end <= 0x7d9b

        org 0x2b8c
hk_seg7:
; hk_icon_src - E = icon: hk_sx / hk_sy of it in the icon variant selected by the colour of the destination cell (hk_dx, hk_dy).
;   Clobbers: AF, BC, DE, HL
hk_icon_src:
        push de
        ld a,(hk_dy)
        ld b,a
        ld a,(hk_dx)
        ld c,a
        call hk_topcolxy
        ld hl,hud_icons_cols
        ld b,ICON_NV
        call hk_variant
        ld l,a
        ld h,0
        add hl,hl                       ; v * 2
        ld e,l
        ld d,h
        add hl,hl
        add hl,hl
        add hl,hl                       ; v * 16
        add hl,de                       ; v * 18
        add hl,de                       ; v * 20
        add hl,de                       ; v * 22
        pop de
        ld a,e
        cp 33
        jr c,.i
        xor a
.i:     ld c,a
        cp 32
        jr c,.r0
        ld de,11
        add hl,de                       ; icons 32..: second row
.r0:    ld de,VR_ICON_Y
        add hl,de
        ld (hk_sy),hl
        ld a,c
        and 31
        add a,a
        add a,a
        add a,a
        ld (hk_sx),a
        xor a
        ld (hk_sx+1),a
        ret
; hk_shop_prep_draw - tail of hk_shop_prep (and of hk_shop_panel for a BONUS screen): the navy panel, then the half's text cache over it
; as it is, once every cell of the half is composed text (hk_half_ready, ADR-036). Returns NZ.
hk_shop_prep_draw:
        call hk_shop_backdrop           ; leaves DX = the half, DY = the draw buffer, 128 x 96
        call hk_half_ready
        jr nz,.n                        ; still being printed: the panel alone
        ld hl,(hk_dx)
        ld (hk_sx),hl
        ld l,h                          ; HL = VR_BG_Y = 0 (DX < 256)
        ld (hk_sy),hl
        call hk_lmmm_tp
.n:     or 0xff
        ret
        assert VR_BG_Y == 0
; hk_keep_de - D = cell row, E = column, C = offset bits: the cells of the glyph are written in this pass (hk_keep_cells, ADR-028).
;   Preserves all registers
hk_keep_de:
        push hl
        ld l,d
        ld h,0
        add hl,hl
        add hl,hl
        add hl,hl
        add hl,hl
        add hl,hl                       ; row * 32
        ld a,e
        add a,l
        ld l,a                          ; + column (no carry: row < 12)
        call hk_keep_cells
        pop hl
        ret
hk_seg7_end:
        assert hk_seg7_end <= 0x2bfa


        org 0x8e62
hk_seg8:
; Copy one original 8-line text band to the spaced menu. A = horizontal inset (0 or 4).
hk_shop_band:
        ld b,a
        ld a,(hk_shop_x)
        ld l,a
        ld h,0
        ld (hk_sx),hl
        add a,b
        ld l,a
        ld (hk_dx),hl
        ld a,128
        sub b
        ld l,a
        ld (hk_nx),hl
        ld a,(hk_shop_src)
        ld l,a
        ld (hk_sy),hl                   ; VR_BG_Y is zero
        ld a,(hk_shop_dst)
        ld e,a
        ld d,0
        ld hl,(hk_vpb)
        add hl,de
        ld (hk_dy),hl
        ld hl,8
        ld (hk_ny),hl
        jp hk_lmmm_tp
; A = half (0/1; any non-zero value = half 1). Return Z (A = 0) unless that player is in the shop, on the PREPARE TO ENTER LEVEL screen
; that follows it or on a BONUS screen (NZ, A = 1): all are shown on the navy panel. All are the state actor (type FFh) in sub-state
; 20h (SHOP) / 21h (PREPARE) / 25h (BONUS, ADR-036). shop_mask alone is not enough: spawn_master_xybot also sets it to hold the player
; during the Master Xybot fight, and it stays set through the BONUS screen after the boss. Other registers preserved.
hk_shop_half:
        push hl
        ld hl,0x9a18                    ; player 1: sub-state (actor +8)
        or a
        jr z,.p
        ld l,0x28                       ; player 2
.p:     ld a,(hl)
        cp 0x22
        jp z,hk_shop_lvl                ; level start: panel while the PREPARE text is still on screen
        cp 0x25
        jr z,.t                         ; 25h BONUS ...
        and 0xfe
        cp 0x20                         ; 20h SHOP or 21h PREPARE ...
        jr nz,hk_shop_no
.t:     ld a,l
        sub 5
        ld l,a
        ld a,(hl)                       ; ... of a state actor (type FFh)
        inc a
        jr nz,hk_shop_no
hk_shop_yes:
        pop hl
        or 1
        ret
hk_shop_no:
        pop hl
        xor a
        ret

; Ordinary canonical text recolouring, excluding the room's coloured background.
hk_shop_page_colour:
        push af
        call hk_shop_half
        jr z,.plain
        pop af
        ret
.plain: pop af
        jp hk_page_recolour

hk_seg8_end:
        assert hk_seg8_end <= 0x8ecc

        org 0xc04d
hk_seg9:
; Copy the navy panel into the shopping player's viewport.
hk_shop_backdrop:
        ld hl,0
        ld (hk_sx),hl
        ld a,(hk_shop_x)
        ld l,a
        ld (hk_dx),hl
        ld hl,VR_SHOP_Y
        ld (hk_sy),hl
        ld hl,(hk_vpb)
        ld (hk_dy),hl
        ld hl,128
        ld (hk_nx),hl
        ld hl,96
        ld (hk_ny),hl
        jp b1_lmmm_start
hk_shop_present:
        xor a
        call hk_shop_panel
        ld a,1
        call hk_shop_panel
        jp hk_shop_invite

; Two pixels at the viewport boundary, using the invitation panel's navy/grey
; edge. Draw after actors so the divider remains continuous for both players.
hk_view_divider:
        ld hl,128
        ld (hk_sx),hl
        dec hl
        ld (hk_dx),hl
        ld hl,VR_SHOP_Y
        ld (hk_sy),hl
        ld hl,(hk_vpb)
        ld (hk_dy),hl
        ld hl,2
        ld (hk_nx),hl
        ld hl,96
        ld (hk_ny),hl
        jp b1_lmmm_start
; hk_credit_use - st_died's `dec (hl) / jr z,l_3325` (32B8h, HL = credits 72A5h, not 0) is `call hk_credit_use` (ADR-038). Infinite
;   credits (hk_credinf <> 0, F1 + fire on the opening picture): the credit stays; otherwise the original: credits -= 1, the last one
;   -> game over path l_3325.   Out: NZ = continue at 32BBh.   Clobbers: AF (A is reloaded at 32BBh)
hk_credit_use:
        ld a,(hk_credinf)
        and a
        ret nz
        dec (hl)
        ret nz
        pop af                          ; the last credit: drop the return address, as `jr z,l_3325`
        jp 0x3325

hk_seg9_end:
        assert hk_seg9_end <= 0xc0b3

; ---- level scenery (ADR-025, tools/scenes.py) ----------------------------------------------------------------------------------------
; The corridor art of a level is scene (3E2Ch & 3): main tile atlas (direct + mirrored at VR_TILES_Y + TS_MAIN), the SCENE_COLS scene
; palette entries and the scene's panel tile ids (8223h-8748h). No CPU upload into the VRAM during the game: every tile that differs
; between the scenes is in the scene store (free VRAM rows, uploaded at boot by stage B through hk_store_tab; tools/hud4.py
; scene_store) and a scene change is a list of LMMM 8 x 8 copies from the store into the main atlas (bank SCN_LBANK). The cartridge is
; in page 1 only inside hk_romcpy (page 0), a short interrupt-free section per read: the split-screen line interrupt is never held long.
        org 0x3a64
hk_seg10:
; hk_scene_chk - first step of hk_update_bg and of start_level (hk_scene_lvl): if the level's scene is not the one in the main atlas,
; copy it there (hk_scene_copy); clearing hk_bankw then makes hk_update_bg redraw every viewport cell. Boss rooms (tile base 4B14h)
; keep their own atlas.   Clobbers: AF, BC, DE, HL
hk_scene_chk:
        ld a,(0x7d03)
        cp 0x75                         ; tile base 751Ch: the corridor tiles
        ret nz
        ld a,(0x3e2c)                   ; level index 0..50
        and 3
        ld hl,hk_scene
        cp (hl)
        ret z
        ld (hl),a
        ld hl,SCN_LIST
        ld de,SCN_LSZ
        or a
        jr z,.s
.m:     add hl,de
        dec a
        jr nz,.m
.s:     ld de,8
        ld (hk_nx),de
        ld (hk_ny),de
        jp hk_scene_copy
hk_seg10_end:
        assert hk_seg10_end <= 0x3a97
        assert SCN_LIST >= 0x4000 && SCN_LIST + 4 * SCN_LSZ <= 0x8000

        org 0xb411
hk_seg11:
; hk_store_tab - stage B's second VRAM table (read with page 1 = cartridge, so not in page 1): the scene store pieces, from the fixed
; banks SCN_SBANK.. (tools/hud4.py scene_store).
hk_store_tab:
        include "../build/assets4/scene_store_tab.inc"
hk_seg11_end:
        assert hk_seg11_end <= 0xb44f

        org 0x3992
hk_seg12:
; hk_scene_pal - the SCENE_COLS palette entries of scene hk_scene: (R#14 pointer, R, G, B) records, 64 bytes per scene in SCENE_PAL,
; read 4 bytes at a time (hk_romcpy) into the command scratch.   Clobbers: AF, BC, DE, HL
hk_scene_pal:
        ld a,(hk_scene)
        rrca
        rrca                            ; scene * 64
        ld l,a
        ld h,0x40
        ld b,SCENE_COLS
.p:     push bc
        ld de,hk_sx
        ld b,4
        ld a,SCENE_PAL
        call hk_romcpy
        push hl
        ld hl,hk_sx+1
        ld bc,3*256+V9_PAL
        di                              ; V9990 registers: no line interrupt meanwhile (it changes P#4)
        ld a,R_PALPTR
        out (V9_REGSEL),a
        ld a,(hk_sx)
        out (V9_REGDATA),a
        otir
        ei
        pop hl
        pop bc
        djnz .p
        ret
hk_seg12_end:
        assert hk_seg12_end <= 0x39c3

        org 0x3a9a
hk_seg13:
; hk_shop_lvl - tail of hk_shop_half for sub-state 22h (level start: the player may already be playing, actor type 1; the sub-state
; stays 22h through the level): the half keeps the shop panel while it is still a whole text screen (the PREPARE TO ENTER LEVEL text),
; i.e. until the level's first view is rendered. Whole: HK_VKIND set in its first cell (row 0, column 0) and its last (row 11, column 15);
; a text written during the play never covers both. In: L = low byte of the sub-state address (18h / 28h), HL pushed.
;   Out: NZ = shop panel; registers other than AF preserved
hk_shop_lvl:
        ld a,l
        and 0x20
        rrca                            ; half * 16
        ld l,a
        ld h,HK_VKIND >> 8
        ld a,(hl)
        or a
        jp z,hk_shop_no
        ld a,l
        add a,(11 * 32 + 15) & 255
        ld l,a
        ld a,h
        adc a,(11 * 32 + 15) >> 8
        ld h,a
        ld a,(hl)
        or a
        jp z,hk_shop_no
        jp hk_shop_yes
; hk_pause_wait - tail of pause_check (rewritten by build_b1.py, ADR-037): P was pressed. Wait for its release, the next press and that
; release (key_test Z = pressed; 978Ah = ld a,25h (P) / jp key_test): P pauses and P resumes.   Clobbers: AF, HL (as the original)
hk_pause_wait:
.r1:    call 0x978a
        jr z,.r1                        ; P still held (the press that paused)
.r2:    call 0x978a
        jr nz,.r2                       ; paused until P is pressed again
.r3:    call 0x978a
        jr z,.r3                        ; and released (else the next pass would pause again)
        ret
hk_seg13_end:
        assert hk_seg13_end <= 0x3ac7
        assert (HK_VKIND & 0xff) == 0


        org 0x2d8b
hk_seg14:
; hk_cheat_drain - sub_AD81's `dec (ix+4)` (AD9Fh, the energy drain with time, IX = player status block) comes here. CHEAT
; (hk_cheat <> 0): the energy stays; otherwise the original code: energy -= 1, still >= 0 returns, else the player dies (ADA3h).
hk_cheat_drain:
        ld a,(hk_cheat)
        or a
        ret nz
        dec (ix+4)
        ret p
        jp 0xada3
; hk_hclr_reset - half hk_vh is no longer a lazily clearable text screen (tiles rendered, stripes, a full clear) (ADR-028).
;   Clobbers: AF, B
hk_hclr_reset:
        ld a,(hk_vh)
        inc a
        cpl                             ; FEh / FDh
        ld b,a
        ld a,(hk_hclr)
        and b
        ld (hk_hclr),a
        ld a,(hk_hpend)
        and b
        ld (hk_hpend),a
        ret
hk_seg14_end:
        assert hk_seg14_end <= 0x2dac

        org 0x37b5
hk_seg15:
; hk_scene_redraw - FDEA (view_redraw_mask) |= the players that are PLAYING (actor type 1): their views are built again with the new
; scene's panels. A player on a text screen (BONUS, shop, prepare, continue...) is left alone: the game builds its view when the level
; starts (st_level_start), and a forced rebuild would paint a corridor over the screen.   Clobbers: AF, HL
hk_scene_redraw:
        ld hl,0xfdea
        ld a,(0x9a13)                   ; player 1 actor type
        dec a
        jr nz,.p2
        set 0,(hl)
.p2:    ld a,(0x9a23)                   ; player 2
        dec a
        ret nz
        set 1,(hl)
        ret
hk_seg15_end:
        assert hk_seg15_end <= 0x37cd

        org 0x30fc
hk_seg16:
; hk_shop_gate - the test at the start of hk_shop_panel (moved out of the full runtime). NZ: lay the shop menu out; Z: nothing more to
; do (the half is not shopping, or hk_shop_prep drew the PREPARE TO ENTER LEVEL screen).   Clobbers: all (the caller reloads A)
hk_shop_gate:
        call hk_shop_half
        ret z
        call hk_shop_prep
        jr nz,.done
        or 1
        ret
.done:  xor a
        ret
; hk_clear_half - clear_viewport_fb for half A (ADR-028): a full clear (hk_clear_full: every cell blank static, record := blank) unless
; the half is an untouched text screen (hk_hclr): then the clear is deferred (hk_hpend).   Clobbers: all
hk_clear_half:
        ld c,a
        inc a
        ld b,a                          ; B = bit of the half (1 / 2)
        ld a,(hk_hclr)
        and b
        jp z,hk_clear_full
        ld a,(hk_hpend)
        or b
        ld (hk_hpend),a
        ret
hk_seg16_end:
        assert hk_seg16_end <= 0x311f

        org 0x7f20
hk_seg17:
; hk_scene_copy - HL = the scene's copy list (SCN_LIST + scene * SCN_LSZ in bank SCN_LBANK), NX = NY = 8 (hk_scene_chk). Every 8-byte
; entry (SX, SY, DX, DY) is one LMMM 8 x 8 from the scene store into the main atlas; an entry of FFh bytes ends the list. Then the
; scene's colours and panels.   Clobbers: all
hk_scene_copy:
.e:     ld de,hk_sx
        ld b,8
        ld a,SCN_LBANK
        call hk_romcpy                  ; SX, SY, DX, DY of the entry
        ld a,(hk_dx)
        inc a
        jr z,.done                      ; FFh: end of the list
        push hl
        call b1_lmmm_start
        pop hl
        jr .e
.done:  call hk_scene_pal
        call hk_scene_panels
        ld hl,0
        ld (hk_bankw),hl                ; "another tile bank": hk_update_bg redraws everything
        ret
; hk_clear_cell - deferred clear of cell HL (ADR-028, hk_clear_walk): written in this pass (HK_VRAW bit 1) -> it has content (bit 2);
; content not written again -> blank: record := blank, no glyph memory, pending, queued.   Preserves HL, BC; clobbers AF, DE
hk_clear_cell:
        push hl
        ld de,HK_VRAW
        add hl,de
        ld a,(hl)
        bit 1,a
        jr z,.nk
        and 0xfd
        or 4
        ld (hl),a
        pop hl
        ret
.nk:    bit 2,a
        jr z,.x
        and 0xfb
        or 1
        ld (hl),a
        ld de,HK_GLY-HK_VRAW
        add hl,de
        ld (hl),0xff
        pop hl
        push hl
        call hk_txt_blank_cell
        call hk_queue_static
.x:     pop hl
        ret

hk_seg17_end:
        assert hk_seg17_end <= 0x7f6e

        org 0x7da0                      ; 7D9Eh-7D9Fh are named by live code
hk_seg18:
; hk_scene_panels - the scene's wall panels (tile ids of the 36 panels and their door records, 8223h-8748h: every scene has its own ids)
; from SCENE_PAL, 0100h + scene * 0800h, 8 bytes per call of hk_romcpy; then the views of the players who are playing are built again
; (hk_scene_redraw), so that no cell map keeps the previous scene's ids.   Clobbers: AF, BC, DE, HL
hk_scene_panels:
        ld a,(hk_scene)
        add a,a
        add a,a
        add a,a                         ; scene * 8: high byte of scene * 0800h
        add a,0x41
        ld h,a
        ld l,0
        ld de,0x8223
        ld c,(0x8749-0x8223) / 8
.l:     push bc
        ld b,8
        ld a,SCENE_PAL
        call hk_romcpy
        pop bc
        dec c
        jr nz,.l
        ld b,(0x8749-0x8223) & 7
        ld a,SCENE_PAL
        call hk_romcpy
        jp hk_scene_redraw
; hk_cellxy - (moved from the runtime, ADR-036) C = cell (row << 4 | col): C = x, B = y, NC if visible (row < 12), CY if not.   Clobbers: AF
hk_cellxy:
        ld a,c
        and 0xf0
        cp 0xc0
        ccf
        ret c                           ; row >= 12: invisible
        rrca                            ; row * 8
        ld b,a
        ld a,c
        and 15
        add a,a
        add a,a
        add a,a
        add a,64
        ld c,a
        or a                            ; NC
        ret
hk_seg18_end:
        assert hk_seg18_end <= 0x7ddb
        assert ((0x8749-0x8223) & 7) != 0

        org 0x7cb8
hk_seg19:
; hk_scene_lvl - start_level's call of load_level (3023h, A = current_level) comes here first: the new level's scene (panels included) is
; in place before the level's views are built, so that no frame shows the previous scene's ids.
hk_scene_lvl:
        push af
        call hk_scene_chk
        pop af
        jp 0x3c77                       ; load_level
; hk_pcache_clear - (moved from the runtime, ADR-036) forget every cached print (a half was cleared, striped, reset or re-rendered).   Clobbers: AF, BC, DE, HL
hk_pcache_clear:
        ld hl,HK_PCACHE
        ld de,HK_PCACHE+1
        ld bc,HK_PCACHE_N*5-1
        ld (hl),0
        ldir
        xor a
        ld (hk_pnext),a
        ret
hk_seg19_end:
        assert hk_seg19_end <= 0x7cd2

        org 0x3f5a
hk_seg20:
; hk_romcpy - B (1..255) bytes from ROM bank A, page 1 address HL, to DE (not in page 1). The cartridge is in page 1 only with
; interrupts off (the IM 1 handler and the game's stack live in page 1: no stack use meanwhile), ONE byte per interrupt-free section
; (~95 Z80 cycles): the split-screen line interrupt must be served within one display line (hk_irq), so no section may be longer than
; the register sections of hk_regs4. Every section selects the bank again: the frame interrupt may run the Moonsound player (hk_snd2),
; which leaves a music bank in page 1. Out: HL, DE advanced.   Clobbers: AF, BC
hk_romcpy:
        ld c,a
.b:     di
        ld a,(hk_romsl)
        out (0xa8),a                    ; page 1 = cartridge
        ld a,c
        ld (0x6000),a                   ; ASCII16 bank of 4000h-7FFFh
        ld a,(hl)
        ld (de),a
        ld a,(hk_ramsl)
        out (0xa8),a                    ; page 1 = RAM again
        ei
        inc hl
        inc de
        djnz .b
        ret
; hk_snd3 - end of hk_snd (page 1 = RAM again, game stack): B = ms_tick's answer
hk_snd3:
        ld a,b
        or a
        jp z,0x4131                     ; A = 0: the original PSG driver
        xor a                           ; title / attract with a Moonsound: silence, the PSG driver does not run; its mode latch is set
        ld (0x4130),a                   ; as its title tick would (snd_mode_latch := 0), so that the game start resets it (sub_44F3)
        ret
hk_seg20_end:
        assert hk_seg20_end <= 0x3f7d

; ---- deferred clear of text screens (ADR-028) ----------------------------------------------------------------------------------------
; The engine clears a player's viewport and prints its texts again every pass on the PREPARE / BONUS / CONTINUE screens (st_prepare:
; clear_viewport_fb + print_text_block). Composing the 192 blank cells and the texts again took ~0.4 s per pass and slowed the other
; player's shop. Now a clear of a half that is still the text screen of the previous clear (hk_hclr) only sets hk_hpend; the glyph hooks
; mark the cells written in the pass (HK_VRAW bit 1); at the next background update (hk_clear_pending) the cells that had content
; (bit 2) and were not written again are blanked, the written ones keep their content (bit 1 -> bit 2). Identical prints cost nothing
; in the VRAM; a dropped print blanks only its cells. The print cache is cleared at every deferred clear, so that every print passes
; through the glyph hooks (which mark the cells; an unchanged glyph records nothing).
        org 0x7cd5
hk_seg21:
; hk_clear_walk - half A: every cell of the half through hk_clear_cell (hk_hooks.asm).   Clobbers: all
hk_clear_walk:
        ld (hk_vh),a
        call hk_pcache_clear            ; every print of the next pass goes through the glyph hooks (they mark the cells)
        call hk_half_base               ; HL = first cell of the half
        ld c,12
.r:     ld b,16
        push hl
.c:     call hk_clear_cell
        inc hl
        djnz .c
        pop hl
        ld de,32
        add hl,de
        dec c
        jr nz,.r
        ret
hk_seg21_end:
        assert hk_seg21_end <= 0x7cf7

        org 0x7d04
hk_seg22:
; hk_keep_cells - HL = cell index (0..383), C = line offset bits (0 = whole cells), hk_gn = glyph height in cells: the cells the glyph
; spans are marked as written in this pass (HK_VRAW bit 1).   Preserves all registers
hk_keep_cells:
        push af
        push bc
        push de
        push hl
        ld a,c
        or a
        ld a,(hk_gn)
        jr z,.n
        inc a                           ; an offset: one more cell row
.n:     ld b,a
        ld de,HK_VRAW
        add hl,de
.l:     ld a,h
        cp (HK_VRAW + 384) >> 8
        jr nc,.x                        ; beyond cell 383
        set 1,(hl)
        ld de,32
        add hl,de
        djnz .l
.x:     pop hl
        pop de
        pop bc
        pop af
        ret
hk_seg22_end:
        assert hk_seg22_end <= 0x7d2a
        assert ((HK_VRAW + 384) & 0xff) == 0

        org 0x3bb2
hk_seg23:
; hk_clear_pending - start of hk_update_bg: the deferred clears (hk_hpend bits -> hk_clear_walk), then the level scenery.   Clobbers: all
hk_clear_pending:
        ld a,(hk_hpend)
        ld c,a
        xor a
        ld (hk_hpend),a
.h:     push af                         ; A = half
        rr c
        call c,hk_clear_walk
        pop af
        inc a
        cp 2
        jr nz,.h
        jp hk_scene_chk
hk_seg23_end:
        assert hk_seg23_end <= 0x3bd1          ; 3BD1h-3BD2h are named by live code

        org 0xa2e6
hk_seg24:
; hk_vclear_tail - end of hk_vclear_half: D = 0, E = half: not uniform text, not canonical, not a text screen; the half is dirty.
hk_vclear_tail:
        ld hl,hk_huni
        add hl,de
        ld (hl),d
        inc hl
        inc hl
        ld (hl),d
        call hk_hclr_reset
        jp hk_half_dirty
hk_seg24_end:
        assert hk_seg24_end <= 0xa2fa

; ---- Moonsound music (ADR-027, src/music.inc, src/rom/opl4_player.asm) --------------------------------------------------------------
; hk_snd / hk_snd2 switch page 1 to the music bank: they live in page 0 / 2 (hk_snd3, the end, in hk_seg20).
        org 0xa1f6
hk_seg25:
; hk_snd - the IM 1 handler's `call sound_tick` (7C88h, A = 0, every register saved, interrupts off) comes here. Without a Moonsound:
; the original PSG driver at once. Otherwise the player in the music bank runs one frame (page 1 = that bank; the game stack is in
; page 1, so a private stack in page 3 is used meanwhile) and says whether the PSG driver runs too (A = 0). ms_tick gets the game's
; sound mode (7C74h) in C and the Master Xybot fight flag (72A0h) in B: both in page 1 RAM, read before the switch.   Clobbers: all
hk_snd:
        ld a,(hk_ms_state)
        dec a
        jp z,0x4131                     ; 1: no Moonsound (A = 0, as the handler passes it)
        ld (hk_ms_sp),sp
        ld sp,hk_ms_stack
        ld a,(0x7c74)                   ; the game's sound mode (page 1 RAM, read before the switch): C for ms_tick
        ld c,a
        ld a,(0x72a0)                   ; Master Xybot fight in progress (var_72A0): B
        ld b,a
        jp hk_snd2
hk_seg25_end:
        assert hk_seg25_end <= 0xa211   ; A211h is named by live code

        org 0x294f
hk_seg26:
hk_snd2:
        ld a,(hk_romsl)
        out (0xa8),a                    ; page 1 = cartridge
        ld a,MUSIC_BANK
        ld (0x6000),a                   ; ASCII16 bank of 4000h-7FFFh: any music bank holds the player (ms_frame selects its stream bank)
        call 0x4000                     ; ms_tick
        ld b,a
        ld a,(hk_ramsl)
        out (0xa8),a                    ; page 1 = RAM (game code, stack); the bank of page 1 stays a music bank (hk_romcpy selects its own)
        ld sp,(hk_ms_sp)
        jp hk_snd3
hk_seg26_end:
        assert hk_seg26_end <= 0x296a

; ---- player 2 keyboard (ADR-037) in the bodies of the original input routines, dead since ADR-015 (input_player1's keyboard scan
; BEECh-BF1Dh; input_player2 after its entry hook BF45h-BF65h; read_joystick1 BF1Eh and the table BF66h stay) ----
        org 0xbeec
hk_seg27:
; hk_kbd2 - player 2's keys ORed into the joystick B result: B = game bits (bit 4 fire, 3 up, 2 down, 1 left, 0 right), C = turn bits
; (bit 0 left, bit 1 right). W A S D move, CTRL fires, SHIFT + A / D turns (the left / right bits then do not move; ADR-041).   Clobbers: AF, H
hk_kbd2:
        ld a,5
        call hk_kbd_row                 ; row 5: bit 4 W, bit 0 S
        bit 4,a
        jr z,.w
        set 3,b                         ; W: up
.w:     bit 0,a
        jr z,.s
        set 2,b                         ; S: down
.s:     ld a,2
        call hk_kbd_row                 ; row 2: bit 6 A
        bit 6,a
        jr z,.a
        set 1,b                         ; A: left
.a:     ld a,3
        call hk_kbd_row                 ; row 3: bit 1 D
        bit 1,a
        jr z,hk_kbd2b
        set 0,b                         ; D: right
        jp hk_kbd2b
hk_seg27_end:
        assert hk_seg27_end <= 0xbf1e

        org 0xbf45
hk_seg28:
hk_kbd2b:
        ld a,6
        call hk_kbd_row                 ; row 6: bit 0 SHIFT, bit 1 CTRL (1 = pressed)
        bit 1,a
        jr z,.nf
        set 4,b                         ; CTRL: fire
.nf:    rrca                            ; CY = SHIFT
        ret nc
        ld a,b
        and 3
        ret z                           ; no left / right
        xor 3                           ; game left (bit 1) -> turn bit 0, right (bit 0) -> turn bit 1 (both: no turn)
        or c
        ld c,a
        ld a,b
        and 0xfc
        ld b,a                          ; with SHIFT held, A / D turn instead of moving
        ret
hk_seg28_end:
        assert hk_seg28_end <= 0xbf66

        org 0x98e1                      ; 98E0h (RET) stays: the unreached ZX turn wipe calls it
hk_seg29:
; hk_zap_red - the special attack's red flash (l_97A5, ADR-039). 97C8h-97D1h (`ld a,12h / call sub_98AE` = the viewport's TMS colour
;   table painted red, then 10 HALTs) is `call hk_zap_red` + NOPs. The red of ZX attribute 12h (zx_attr_to_msx: its paper) fills this
;   viewport's half (128 x 96 at x = cur_viewport * 128) of BOTH display buffers, so it shows at once whichever buffer is displayed,
;   for 10 V9990 frames (hk_frames: in the port a HALT also ends at the line interrupt, 10 HALTs would be 5 frames). The next passes
;   copy VR_BG over it again; the original restore (98AAh) stays. Enemies are then hit and stunned by the original code (97D2h..).
;   Out: interrupts enabled (as sub_98AE).   Clobbers: AF, BC, HL
hk_zap_red:
        ld a,0x12
        call 0x6fd4                     ; zx_attr_to_msx: A = TMS ink << 4 | paper
        ld (hk_t0),a                    ; (hk_lmmv uses the low nibble: the paper)
        ld a,(0x72a7)                   ; cur_viewport 0 / 1
        rrca                            ; x = 0 / 80h
        ld (hk_dx),a
        xor a
        ld (hk_dx+1),a
        ld (hk_nx+1),a
        ld (hk_ny+1),a
        ld a,128
        ld (hk_nx),a
        ld a,96
        ld (hk_ny),a
        ld hl,VR_VPA_Y
        call .fill
        ld hl,VR_VPB_Y
        call .fill
        ei
        ld a,(hk_frames)
        add a,10
        ld b,a
.wait:  halt
        ld a,(hk_frames)
        cp b
        jr nz,.wait
        ret
.fill:  ld (hk_dy),hl
        ld a,(hk_t0)
        jp hk_lmmv
hk_seg29_end:
        assert hk_seg29_end <= 0x992c

        org 0x6e14
hk_seg30:
;------------------------------------------------------------------------------
; Minimap markers without XOR bookkeeping (ADR-054). The window x 64..191 of VR_HUD has a clean twin at VR_MAPC_Y: everything the
; game draws into the window (walls, doors, corners, the wipe, the static markers) goes into both (hk_mglyph, hk_mrect, hk_marker).
; The blinking markers are XORed on VR_HUD only; before that, the boxes they occupied at the previous pass are copied back from the
; clean image, and one map row in turn as well, so nothing that was left in the window by a lost or doubled command outlives 12
; passes (the real-machine leftovers: the XOR of a marker that was not erased, or erased twice, could never be undone).
;------------------------------------------------------------------------------
; hk_mm_after - the first minimap_actors call of a pass returns here (hk_minimap pushed this address) right after its HALT and after
; its loop collected the blinking markers in HK_MARK0 (hk_marker). The HALT ended at the line interrupt (line ~95: the HUD has just
; been scanned) or at the vertical one (the next HUD scan is more than 4 ms away): the restores and the markers below are done before
; the HUD is scanned again, so no marker is ever missing from a frame. The original's early returns (boss room, game not running)
; come here as well: the same tests leave.   Clobbers: all
hk_mm_after:
        ld a,(0x72a0)
        or a
        ret nz
        ld a,(0xb1d5)                   ; game_running
        or a
        ret z
        ld a,(hk_mkn1)                  ; 1. the boxes of the markers of the previous pass: the clean image again
        or a
        jr z,.row
        ld b,a
        ld hl,HK_MARK1
.r:     push bc
        push hl
        call hk_mark_box
        pop hl
        pop bc
        inc hl
        inc hl
        inc hl
        inc hl
        djnz .r
.row:   ld a,(hk_mrow)                  ; 2. one of the 12 map rows in turn
        inc a
        cp 12
        jr c,.rk
        xor a
.rk:    ld (hk_mrow),a
        add a,a
        add a,a
        add a,a
        ld l,a
        ld h,VR_MAPC_HI
        ld (hk_sy),hl                   ; (VR_MAPC_Y low byte is added below)
        ld a,l
        add a,VR_MAPC_Y & 0xff
        ld (hk_sy),a
        ld h,VR_HUD_HI
        ld (hk_dy),hl
        ld hl,8
        call hk_win_copy
        ld a,(hk_mkn)                   ; 3. the markers of this pass, XORed on VR_HUD
        or a
        jr z,.keep
        ld b,a
        ld hl,HK_MARK0
.d:     push bc
        push hl
        ld de,hk_mk
        ld bc,3
        ldir
        ld a,VR_HUD_HI
        ld (hk_mkdy),a
        call hk_mark_lmmm
        pop hl
        pop bc
        inc hl
        inc hl
        inc hl
        inc hl
        djnz .d
.keep:  ld a,(hk_mkn)
        ld (hk_mkn1),a
        ld hl,HK_MARK0
        ld de,HK_MARK1
        ld bc,HK_MKMAX*4
        ldir                            ; the list of the boxes to restore at the next pass
        ret

; hk_mark_box - the box of the marker entry HL (shape, x, y: cross 2x2 at x, y; ring 3x3 at x-1, y-1; arrow 8x8 at x, y) copied from
; the clean image to VR_HUD: x-1..x+8, lines y-1..y+8 clipped to the window (0..95).   Clobbers: all
hk_mark_box:
        inc hl
        ld a,(hl)                       ; x
        add a,63
        ld c,a
        ld b,0
        ld (hk_sx),bc
        ld (hk_dx),bc
        inc hl
        ld a,(hl)                       ; y
        ld c,10
        or a
        jr nz,.y
        inc a                           ; y = 0: lines 0..8
        dec c
.y:     dec a                           ; first line y - 1
        ld (hk_dy),a
        add a,VR_MAPC_Y & 0xff
        ld (hk_sy),a
        ld a,VR_MAPC_HI
        ld (hk_sy+1),a
        ld a,VR_HUD_HI
        ld (hk_dy+1),a
        ld a,(hk_dy)
        neg
        add a,96                        ; lines left in the window from y - 1
        cp c
        jr nc,.n
        ld c,a                          ; clipped at line 95 (line 96 is display buffer A)
.n:     ld hl,10
        ld (hk_nx),hl
        ld l,c
        ld (hk_ny),hl
        jp b1_lmmm_start
hk_seg30_end:
        assert hk_seg30_end <= 0x6ee3   ; 6E14h-6EE2h: the dead ZX Spectrum tape loader (game_6000.asm)

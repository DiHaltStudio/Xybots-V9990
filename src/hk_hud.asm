;==============================================================================
;  XYBOTS V9990 B1 - HUD, texts and minimap composed by the V9990 (ADR-016)
;
;  The top half of the screen is the single VR_HUD image (256x96, BP6) shown by the split-screen interrupt. It starts as hud.tmx,
;  copied with LMMM from the indexed panel atlas at the engine's init. Every engine routine that drew into the TMS pattern table
;  is replaced by V9990 commands into VR_HUD:
;    glyph_to_vram (3F57h, texts of print_string mode 0: title, HI score, marquee): LMMM 8x8 from the font variant of the cell's colour
;    draw_digit (2B89h, energy / score / keys / coins / credits): LMMM 4x5 from the digit variant of the cell's colour
;    hud_clear_slot (2CEDh) / hud_draw_icon (2D88h): LMMV 9x11 paper, then transparent LMMM 8x11 from the icon variant
;    reveal_cell (3AD8h), open_west_door (3A61h), open_north_door (3A97h), minimap_wipe (30F9h): minimap walls, doors, markers, corners
;      and the sweeping line with transparent LMMMs of the minimap glyphs and LMMV rectangles
;    init_hardware (C04Ah): only the IM 1 vector (the TMS set-up and clear are gone); the colour model starts white on black
;  Colours: the cell colour model HK_TOPCOL (hk_shims.asm) selects the pre-coloured variant (tables from hud4.py); a colour without a
;  variant uses variant 0 and is counted in hk_vmiss.
;==============================================================================

VR_HUD_HI       equ VR_HUD_Y >> 8        ; DY high byte of VR_HUD (a multiple of 256 lines), low byte = y
VR_MAPC_HI      equ VR_MAPC_Y >> 8       ; the clean minimap image (ADR-054): line y at VR_MAPC_Y + y (hk_dy_mapc / hk_mark_lmmm add the low byte)
        assert (VR_MAPC_Y & 0xff) + 103 < 256   ; a marker box reaches line y + 8 <= 103 of the image
        assert FONT_VL == 16                      ; hk_glyph_vram: v * 16

; hk_inithw - entry of init_hardware (C04Ah), replaced: IM 1 vector, colour model := F1h (the TMS clear), interrupts enabled at the end
; like the original (its VDP register loop re-enables them).
hk_inithw:
        di
        ld a,0xc3
        ld (0x0038),a
        ld hl,0x7c75
        ld (0x0039),hl                  ; 0038h: JP int_im1_handler
        ld hl,HK_TOPCOL
        ld de,HK_TOPCOL+1
        ld bc,383
        ld (hl),0xf1
        ldir
        ld hl,HK_CELLCOL
        ld de,HK_CELLCOL+1
        ld bc,383
        ld (hl),0xf1
        ldir
        ei
        ret


;------------------------------------------------------------------------------
; helpers
;------------------------------------------------------------------------------
; hk_topcolxy - B = y (0..95), C = x: A = colour byte of that HUD cell (HK_TOPCOL).   Clobbers: DE, HL
hk_topcolxy:
        ld a,b
        and 0xf8
        ld l,a
        ld h,0
        add hl,hl
        add hl,hl                       ; (y >> 3) * 32
        ld a,c
        rrca
        rrca
        rrca
        and 31
        ld e,a
        ld d,0
        add hl,de
        ld de,HK_TOPCOL
        add hl,de
        ld a,(hl)
        ret

; hk_variant - A = colour byte, HL = colour table of a sheet, B = variants: A = variant index (0 and hk_vmiss + 1 when the colour has none).
;   Clobbers: BC, HL
hk_variant:
        ld c,b
.l:     cp (hl)
        jr z,.hit
        inc hl
        djnz .l
        ld a,(hk_vmiss)
        inc a
        jr z,.sat
        ld (hk_vmiss),a
.sat:   xor a
        ret
.hit:   ld a,c
        sub b                           ; index = variants - remaining
        ret

; hk_lmmm_tp - transparent LMMM (index 0 not copied) of hk_sx..hk_ny.   Clobbers: AF, BC, HL
hk_lmmm_tp:
        ld a,LOP_COPY_TP
hk_lmmm_op:
        ld c,0xff                       ; write mask: every bit
; hk_lmmm_wm - LMMM with LOP A and write mask C (the same byte in R46 and R47: in 4 bpp one nibble value per pixel).
hk_lmmm_wm:
        push af
        ld a,c
        ld (hk_wm),a
        call b1_wait_ce
        ld hl,hk_sx
        ld a,R_CMD
        call hk_regs4
        call hk_regs4
        call hk_regs4                   ; R32..R43 from hk_sx..hk_ny
        pop af
        ld c,a
        di                              ; short sections only: the line interrupt at line 96 changes P#4 (split screen)
        ld a,44
        out (V9_REGSEL),a
        xor a
        out (V9_REGDATA),a              ; R44 ARG
        ld a,c
        out (V9_REGDATA),a              ; R45 LOP
        ld a,(hk_wm)
        out (V9_REGDATA),a              ; R46 write mask
        out (V9_REGDATA),a              ; R47
        ei
        ld a,OP_LMMM
        jp hk_cmd_start                 ; (hk_segs.asm, segment 1; this routine used to fall into it)

; hk_regs4 - registers A..A+3 := the 4 bytes at HL, in one short interrupt-free section. Out: HL += 4, A += 4.   Clobbers: BC
hk_regs4:
        di
        out (V9_REGSEL),a
        ld bc,4*256+V9_REGDATA
        otir
        ei
        add a,4
        ret

; hk_lmmv - fill hk_dx, hk_dy, hk_nx x hk_ny with colour index A (0..15).   Clobbers: AF, BC, HL
hk_lmmv:
        ld b,LOP_COPY
        jr hk_lmmv_go
; hk_lmmv_raw - fill with the byte A as it is (text record: FFh blank, EEh stripes).
hk_lmmv_raw:
        ld b,LOP_COPY
        jr hk_lmmv_rb
hk_lmmv_go:
        and 15
hk_lmmv_rb:
        ld c,a                          ; BP6: FC = the pixel byte itself
        ld a,b
        ld (hk_wm),a                    ; (scratch: the LOP)
        call b1_wait_ce
        ld hl,hk_dx
        ld a,36
        push bc
        call hk_regs4
        call hk_regs4                   ; R36..R43: DX, DY, NX, NY
        pop bc
        di
        ld a,44
        out (V9_REGSEL),a
        xor a
        out (V9_REGDATA),a              ; R44 ARG
        ld a,(hk_wm)
        out (V9_REGDATA),a              ; R45 LOP
        ld a,0xff
        out (V9_REGDATA),a              ; R46
        out (V9_REGDATA),a              ; R47
        ei
        di
        ld a,48
        out (V9_REGSEL),a
        ld a,c
        out (V9_REGDATA),a              ; R48 FC
        out (V9_REGDATA),a              ; R49
        out (V9_REGDATA),a              ; R50
        out (V9_REGDATA),a              ; R51
        ei
        ld a,OP_LMMV
        jp hk_cmd_start

; hk_set_dxy - destination (C = x, B = y) in VR_HUD, size (D = nx, E = ny).   Clobbers: AF
hk_set_dxy:
        ld a,c
        ld (hk_dx),a
        xor a
        ld (hk_dx+1),a
        ld (hk_nx+1),a
        ld (hk_ny+1),a
        ld a,b
        ld (hk_dy),a
        ld a,VR_HUD_HI
        ld (hk_dy+1),a
        ld a,d
        ld (hk_nx),a
        ld a,e
        ld (hk_ny),a
        ret

;------------------------------------------------------------------------------
; hk_glyph_vram - entry of glyph_to_vram (3F57h, also reached by glyph_cell_vram falling into it), replaced: HL = TMS write address of the
; cell (40h set), E = glyph code. Draws the 8x8 glyph opaque (the original wrote whole bytes) at (L & F8h, 8 * (H & 3Fh) + (L & 7)).
; Out as the original: HL unchanged, DE = glyph pointer 6F94h + 8 * E; C preserved.
;------------------------------------------------------------------------------
hk_glyph_vram:
        push hl
        push bc
        ld a,e
        ld (hk_gcode),a
        ld a,h
        and 0x3f
        cp 12
        jr nc,.done                     ; rows 12-23: the viewport area, which the original overwrote with the frame buffer
        add a,a
        add a,a
        add a,a
        ld b,a
        ld a,l
        and 7
        add a,b
        ld b,a                          ; B = y
        ld a,l
        and 0xf8
        ld c,a                          ; C = x
        ld de,8*256+8
        call hk_set_dxy
        call hk_topcolxy
        ld hl,hud_font_cols
        ld b,FONT_NV
        call hk_variant                 ; A = variant
        ld c,a
        ld a,(hk_gcode)
        sub 0x20
        cp 65
        jr c,.g
        xor a                           ; a code outside the font: space
.g:     cp 64
        jr nz,.n
        ld a,c                          ; glyph 64 (code 60h): the shared row VR_FONTX_Y, variant v at x = 8 * v (ADR-054)
        add a,a
        add a,a
        add a,a
        ld (hk_sx),a
        ld hl,VR_FONTX_Y
        jr .s
.n:     ld l,c
        ld h,0
        add hl,hl
        add hl,hl
        add hl,hl
        add hl,hl                       ; v * FONT_VL (16: glyphs 0-63 in 2 rows of 32)
        ld c,a
        and 0xe0
        rrca
        rrca                            ; (g >> 5) * 8
        ld e,a
        ld d,0
        add hl,de
        ld de,VR_FONT_Y
        add hl,de
        ld a,c
        and 31
        add a,a
        add a,a
        add a,a
        ld (hk_sx),a
.s:     ld (hk_sy),hl
        xor a
        ld (hk_sx+1),a
        call b1_lmmm_start
.done:  ld a,(hk_gcode)
        ld l,a
        ld h,0
        add hl,hl
        add hl,hl
        add hl,hl
        ld de,0x6f94
        add hl,de
        ex de,hl                        ; DE = glyph pointer (as the original)
        pop bc
        pop hl
        ei                              ; as the original (EI at 3F6Fh)
        ret

;------------------------------------------------------------------------------
; hk_digit - entry of draw_digit (2B89h): E = digit 0..9, B/C = original MSX y/x. Translate the field using layout.json, then copy its
; opaque 4x5 coloured variant (glyph 10 is blank for leading zeroes). Preserves IX; EI at exit keeps the split interrupt running.
;------------------------------------------------------------------------------
hk_digit:
        ld a,b
        cp 92
        jr nc,.done
        call hk_hud_digit_glyph
        push de
        call hk_hud_digit_xy
        ld de,4*256+5
        call hk_set_dxy
        call hk_topcolxy
        ld hl,hud_digits_cols
        ld b,DIG_NV
        call hk_variant
        ld l,a
        ld h,0
        ld e,l
        ld d,h
        add hl,hl
        add hl,hl
        add hl,de                       ; v * 5
        ld de,VR_DIG_Y
        add hl,de
        ld (hk_sy),hl
        pop de
        ld a,e
        cp 11                           ; glyph 10 is blank, used for leading zeroes
        jr c,.d
        xor a
.d:     add a,a
        add a,a
        ld (hk_sx),a
        xor a
        ld (hk_sx+1),a
        call b1_lmmm_start
.done:  ei                              ; (the original left DI for its TMS writes: no TMS here, and a DI would delay the split-screen interrupt)
        ret

; Keep a field's last zero visible and erase earlier leading zeroes with the blank tile.
; Calls for each field arrive left-to-right from the original decimal printing routines.
hk_hud_digit_glyph:
        ld a,b
        cp 16
        jr z,.energy
        cp 32
        jr z,.score
        cp 40
        ret nz                          ; credits: always display their one digit
        ld a,c
        and 63
        cp 15
        jr z,.reset
        cp 47
        jr z,.reset
        jr .force                       ; units of coins / keys
.energy:
        ld a,c
        and 63
        cp 8
        jr z,.reset
        cp 18
        jr z,.force
        jr .test
.score: ld a,c
        and 63
        cp 15
        jr z,.reset
        cp 45
        jr z,.force
        jr .test
.reset: xor a
        ld (hk_gcode),a
.test:  ld a,e
        or a
        jr nz,.force
        ld a,(hk_gcode)
        or a
        ret nz
        ld e,10
        ret
.force: ld a,1
        ld (hk_gcode),a
        ret

; Translate the original field coordinates using the editable HUD layout table.
; B = original y, C = original x -> B/C = display position. DE is preserved.
hk_hud_digit_xy:
        ld hl,hud_digit_positions
.next:  ld a,(hl)
        inc hl
        cp 255
        ret z
        cp b
        jr z,.found
        inc hl
        inc hl
        jr .next
.found: ld b,(hl)
        inc hl
        ld a,(hl)
        add a,c
        ld c,a
        ret

; Repaint a meter only when the player's actual energy changes. No game-state writes.
hk_hud_status:
        ld a,(0x9608)                   ; ROCK status +4
        ld b,a
        ld a,(hk_hudenergy)
        cp b
        jr z,.ace
        ld a,b
        ld (hk_hudenergy),a
        ld c,16
        call hk_energybar
.ace:   ld a,(0x962b)                   ; ACE status +4
        ld b,a
        ld a,(hk_hudenergy+1)
        cp b
        ret z
        ld a,b
        ld (hk_hudenergy+1),a
        ld c,208
; Energy A (0..125), meter x C. Saturate at 100%; width = floor(E/4) + floor(E/16).
hk_energybar:
        cp 101
        jr c,.range
        ld a,100
.range: ld e,a
        srl a
        srl a
        ld d,a
        ld a,e
        srl a
        srl a
        srl a
        srl a
        add a,d
        push af
        ld b,21
        ld de,32*256+4
        call hk_set_dxy
        xor a
        call hk_lmmv_raw
        pop af
        or a
        ret z                           ; NX=0 is a full-width command, not an empty meter
        ld (hk_nx),a
        ld a,59                         ; light blue-grey fill from the shared palette
        jp hk_lmmv_raw

;------------------------------------------------------------------------------
; hk_slot_xy - A = HUD item slot: C/B = x/y from layout.json, x + C0h for ACE.   Clobbers: AF, DE, HL
hk_slot_xy:
        ld e,a
        ld d,0
        ld hl,hud_slot_x
        add hl,de
        ld c,(hl)
        ld hl,hud_slot_y
        add hl,de
        ld b,(hl)
        ld a,(0xb22d)                   ; cur_slot: 0 = ROCK, 1 = ACE
        or a
        ret z
        set 6,c
        set 7,c
        ret

; hk_clear_slot - A = slot: fill its 9x11 area with HUD_SLOT_PAPER (BP6 indexed colour). EI at exit like the original.
hk_clear_slot:
        call hk_slot_xy
        ld de,9*256+11
        call hk_set_dxy
        ld a,HUD_SLOT_PAPER
        call hk_lmmv_raw                ; BP6 indexed paper; does not inherit the MSX white background
        ei
        ret

;------------------------------------------------------------------------------
; Minimap (window x 64..191, y 0..95; cell (row, col) at x = 64 + 8 col, y = 8 row; rows >= 12 fall in the viewport area, which the
; original overwrote with the frame buffer: not drawn). The discovered bitmap 3C51h and the wall map F800h are the engine's.
;------------------------------------------------------------------------------
; hk_discovered - C = cell: Z if it is NOT discovered (bit in 3C51h), HL = bitmap byte, A = bit mask.   Clobbers: AF, DE, HL
hk_discovered:
        push bc
        call 0x3ac7                     ; cell_bit_address: HL = byte, A = bit number
        ld b,a
        inc b
        ld a,0x80
.s:     rlca
        djnz .s                         ; A = 1 << bit
        pop bc
        ld e,a
        and (hl)
        ld a,e
        ret

; hk_mglyph - transparent LMMM of minimap glyph A (0..7: walls none/W/N/WN, marker ring, squares, arrow...) at (C, B) in the ink of the cell.
;   Clobbers: AF, DE, HL (BC preserved)
hk_mglyph:
        push bc
        push af
        ld de,8*256+8
        call hk_set_dxy
        call hk_topcolxy
        ld hl,hud_ui_glyphs_cols
        ld b,UIG_NV
        call hk_variant
        ld l,a
        ld h,0
        add hl,hl
        add hl,hl
        add hl,hl                       ; v * 8
        ld de,VR_UIG_Y
        add hl,de
        ld (hk_sy),hl
        pop af
        add a,a
        add a,a
        add a,a
        ld (hk_sx),a
        xor a
        ld (hk_sx+1),a
        call hk_lmmm_tp
        call hk_dy_mapc
        call hk_lmmm_tp                 ; the same glyph into the clean image (ADR-054)
        pop bc
        ret

; hk_mrect - LMMV at (C, B) of D x E pixels in HUD_MAP_PAPER (A = 0) or HUD_MAP_INK (A <> 0), in VR_HUD and in the clean image.   BC preserved.
hk_mrect:
        push bc
        push af
        call hk_set_dxy
        pop af
        or a
        ld a,HUD_MAP_PAPER
        jr z,.paper
        ld a,HUD_MAP_INK
.paper: push af
        call hk_lmmv_raw                ; use the same BP6 colour as the wall atlas (including door corners)
        call hk_dy_mapc
        pop af
        call hk_lmmv_raw                ; (ADR-054)
        pop bc
        ret

; hk_reveal - entry of reveal_cell (3AD8h), replaced: A = cell. Marks it discovered and draws its walls, doors, marker and corner pixel
; (same rules as the original: see reveal_cell in game_3000.asm). Out: A = cell; BC, DE, HL preserved (the original used the alternate set).
hk_reveal:
        push bc
        push de
        push hl
        ld c,a
        call hk_discovered
        jp nz,.done                     ; already discovered
        or (hl)
        ld (hl),a                       ; discovered
        ld a,c
        cp 0xc0
        jr c,.normal
        ld l,a                          ; cells C0h..CFh: bottom border of the last row when the wall map says so
        ld h,0xf8
        bit 1,(hl)
        jp z,.done
        and 15
        add a,a
        add a,a
        add a,a
        add a,64
        push bc
        ld c,a
        ld b,95
        ld de,8*256+1
        ld a,1
        call hk_mrect                   ; the original wrote FFh at VRAM 4B47h + 8 * col: line y = 95
        pop bc
        jp .done
.normal:
        ld l,c
        ld h,0xf8
        ld a,(hl)
        ld (hk_gcode),a                 ; wall flags of the cell
        push bc
        call hk_cellxy                  ; C = x, B = y
        jr c,.inv
        ld a,(hk_gcode)
        and 3
        call nz,hk_mglyph               ; walls: pattern 3EB4h + 8 * (flags & 3)
        ld a,(hk_gcode)
        ld e,a
        rrca
        rrca
        rrca
        rrca
        and e                           ; bit 0 west wall with door, bit 1 north wall with door
        ld (hk_vtmp),a
        bit 0,a
        jr z,.nwd
        inc b                           ; west door: pixels (x, y+1/3/5/7) paper
        call .dot
        inc b
        inc b
        call .dot
        inc b
        inc b
        call .dot
        inc b
        inc b
        call .dot
        dec b
        dec b
        dec b
        dec b
        dec b
        dec b
        dec b
.nwd:   ld a,(hk_vtmp)
        bit 1,a
        jr z,.nnd
        inc c                           ; north door: pixels (x+1/3/5/7, y) paper
        call .dot
        inc c
        inc c
        call .dot
        inc c
        inc c
        call .dot
        inc c
        inc c
        call .dot
        ld a,c
        sub 7
        ld c,a
.nnd:   ld a,(hk_gcode)
        and 0xc0
        jr z,.nmk
        rlca
        rlca                            ; 1..3
        add a,3                         ; glyph 4 (3ED4h), 5 (3EDCh), 6 (3EE4h)
        call hk_mglyph
.nmk:   ld a,(hk_gcode)
        and 1
        jr z,.inv
        ld a,b
        add a,8
        cp 96
        jr nc,.inv
        ld b,a
        ld de,1*256+1
        ld a,1
        call hk_mrect                   ; corner: pixel (x, y + 8) ink (row 0 of the cell below)
.inv:   pop bc
.done:  ld a,c
        pop hl
        pop de
        pop bc
        ret
.dot:   ld de,1*256+1
        xor a
        jp hk_mrect

; hk_open_west - entry of open_west_door (3A61h), replaced: A = cell. A discovered cell loses its west wall below the corner: pixels
; (x, y+1..y+7) paper. EI at exit.
hk_open_west:
        ld c,a
        call hk_discovered
        jr z,.done
        call hk_cellxy
        jr c,.done
        inc b
        ld de,1*256+7
        xor a
        call hk_mrect
.done:  ei
        ret

; hk_open_north - entry of open_north_door (3A97h), replaced: A = cell. Keeps only the corner of the north wall: pixels (x+1..x+7, y) paper.
hk_open_north:
        ld c,a
        call hk_discovered
        jr z,.done
        call hk_cellxy
        jr c,.done
        inc c
        ld de,7*256+1
        xor a
        call hk_mrect
.done:  ei
        ret

; hk_wipe - entry of minimap_wipe (30F9h), replaced: a white line sweeps down the minimap window (one line per frame, HALT) leaving it
; black. Drawn into VR_HUD (and the clean image, hk_mrect: ADR-054) and, because no page is presented during the effect, into the
; displayed page too.
hk_wipe:
        ld b,0
        ld a,1
        call .line                      ; line 0 white
        ld b,0
.lp:    push bc
        ei
        halt
        pop bc
        xor a
        call .line                      ; line y black ...
        inc b
        ld a,b
        cp 96
        jr nc,.end
        ld a,1
        call .line                      ; ... line y + 1 white
        jr .lp
.end:   ret
; .line - A = 0 paper / 1 ink: line B of the window (x 64..191) in VR_HUD and in the displayed page.   Preserves B
.line:  push bc
        push af
        ld c,64
        ld de,128*256+1
        call hk_mrect                   ; VR_HUD: the single HUD is what is on screen (split screen)
        pop af
        pop bc
        ret

; ---- clean minimap image helpers (ADR-054; the rest is hk_mm_after / hk_mark_box in hk_segs.asm, segment 30)
; hk_dy_mapc - hk_dy (a VR_HUD window line, high byte VR_HUD_HI) := the same line of the clean image.   Clobbers: AF
hk_dy_mapc:
        ld a,(hk_dy)
        add a,VR_MAPC_Y & 0xff
        ld (hk_dy),a
        ld a,VR_MAPC_HI
        ld (hk_dy+1),a
        ret

; hk_mapc_init - the clean image := the window of VR_HUD (hk_top_copy: the HUD just composed from hud.tmx).   Clobbers: all
hk_mapc_init:
        ld hl,VR_HUD_Y
        ld (hk_sy),hl
        ld hl,VR_MAPC_Y
        ld (hk_dy),hl
        ld hl,96
        jr hk_win_copy

; hk_win_copy - LMMM copy of the window (x 64..191) for HL lines: hk_sy -> hk_dy (both set by the caller).   Clobbers: AF, BC, HL
hk_win_copy:
        ld (hk_ny),hl
        ld hl,64
        ld (hk_sx),hl
        ld (hk_dx),hl
        ld hl,128
        ld (hk_nx),hl
        jp b1_lmmm_start

; colour tables of the pre-rendered variants (order = variant index), generated by hud4.py
        include "../build/assets4/hud_tables.inc"

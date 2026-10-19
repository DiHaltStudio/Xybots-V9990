;==============================================================================
;  XYBOTS V9990 B1 - hook runtime (assembled for HK_BASE, copied to RAM by the ROM boot)
;  B1 4 bpp, three pages. The engine logic is unchanged; everything the player sees is composed by the V9990 from images in VRAM (HUD,
;  viewport background, atlases of tiles, sprites, fonts, digits, icons, minimap glyphs, markers). The TMS9918 is not used (ADR-016).
;==============================================================================
        include "defs.asm"
        include "layout.asm"

        org HK_BASE
hk_entry:
        jp hk_boot                      ; +0  called by the ROM boot after the image copy, interrupts disabled
        jp hk_end_loop                  ; +3  replaces `jp z,main_loop` at BE38h
        jp hk_present                   ; +6  replaces `call 7D9Bh` (BDF4h init, BE18h main loop, 2819h shop): present now
        jp hk_nop                       ; +9  (unused)
        jp hk_top_copy                  ; +12 replaces `call 7DDBh` at BDB2h
        jp hk_out98                     ; +15  RST 08h
        jp hk_out99                     ; +18  RST 10h
        jp hk_in98                      ; +21  RST 18h
        jp hk_irq                       ; +24  RST 20h
        jp hk_wp1                       ; +27  RST 28h
        jp hk_wp2                       ; +30  RST 30h
        jp hk_render                    ; +33  replaces `call render_cellmaps`
        jp hk_nop                       ; +36  (unused)
        jp hk_clearvp                   ; +39  entry of clear_viewport_fb
        jp hk_stripes                   ; +42  entry of fill_stripes
        jp hk_greset                    ; +45  entry of game_reset
        jp hk_glyph1                    ; +48  entry of glyph_fb_small_draw
        jp hk_glyph2                    ; +51  entry of draw_glyph_fb_2x
        jp hk_blit1                     ; +54  entry of blit_sprite_2cells (1 byte per row)
        jp hk_blit2                     ; +57  entry of blit_sprite_3cells (2 bytes)
        jp hk_blit3                     ; +60  entry of blit_sprite_4cells (3 bytes)
        jp hk_prepare                   ; +63  entry of draw_all_actors
        jp hk_sign                      ; +66  entry of blit_sign_bitmap
        jp hk_print                     ; +69  entry of print_string
        jp hk_marker                    ; +72  entry of draw_actor_marker
        jp hk_minimap                   ; +75  entry of minimap_actors
        jp hk_input1                    ; +78  entry of input_player1
        jp hk_input2                    ; +81  entry of input_player2
        jp hk_ctrl                      ; +84  entry of sub_9698
        jp hk_inithw                    ; +87  entry of init_hardware
        jp hk_glyph_vram                ; +90  entry of glyph_to_vram
        jp hk_digit                     ; +93  entry of draw_digit
        jp hk_clear_slot                ; +96  entry of hud_clear_slot
        jp hk_draw_icon                 ; +99  entry of hud_draw_icon
        jp hk_reveal                    ; +102 entry of reveal_cell
        jp hk_open_west                 ; +105 entry of open_west_door
        jp hk_open_north                ; +108 entry of open_north_door
        jp hk_wipe                      ; +111 entry of minimap_wipe
        jp hk_greset_tail               ; +114 game_reset 2FF3h (frame-buffer fill skipped)
        jp hk_svc                       ; +117 entry of set_view_colours
        jp hk_waiting                   ; +120 st_waiting drawing tail (2243h)
        jp hk_cheat_hit                 ; +123 l_AC5D: a shot hit a player, damage step (CHEAT)
        jp hk_cheat_bump                ; +126 l_B0EE: a hostile mover ran into a player, contact damage (CHEAT)

hk_nop: ret

; (the palette, 64 x (R, G, B) 5 bits each from assets/palette.json, is not kept here: stage B parks it after the sprite table, at
; HK_BOOTPAL, and hk_boot sends it to the V9990 once)

;------------------------------------------------------------------------------
; hk_cheat_hit - entry of l_AC5D (`ld a,(ix+10)`, the start of the damage a shot does to player IY; the shot was destroyed just before).
;   CHEAT (hk_cheat <> 0): return at once = no damage (the same exit as "armour absorbs everything"). The time drain (sub_AD81) does not
;   pass here, so the energy still goes down. Otherwise the replaced instruction runs and the original continues at AC60h.
;------------------------------------------------------------------------------
hk_cheat_hit:
        ld a,(hk_cheat)
        or a
        ret nz
        ld a,(ix+10)
        jp 0xac60

;------------------------------------------------------------------------------
; hk_cheat_bump - entry of l_B0EE (`ld a,(iy+4)`, the contact damage of an enemy that ran into a player: energy -= 25). IY = the player's
;   status block, IX = the mover, which has just turned into an explosion (B0D3h). CHEAT: no energy loss and no death; the rest of the
;   original path (release of the item the mover carried, l_AD0C) still runs. Otherwise the replaced instruction runs and the original
;   continues at B0F1h (sub 19h).
;------------------------------------------------------------------------------
hk_cheat_bump:
        ld a,(hk_cheat)
        or a
        jp nz,0xad0c
        ld a,(iy+4)
        jp 0xb0f1

;------------------------------------------------------------------------------
; hk_boot - V9990 initialisation (the ROM boot already checked that the chip exists). Interrupts are disabled.
;------------------------------------------------------------------------------
hk_boot:
        ; sprite table FIRST: stage B left it in the unused frame buffer (BOOT_BUF, EB00h), which the initialisations below reuse (print cache at DC00h);
        ; it lives at HK_SPRTAB, over the finished stage B code. Before it, the opening's infinite-credits flag (C1F2h, under the table)
        ld a,(HK_BOOT_CREDINF)
        ld (hk_credinf),a
        ld hl,BOOT_BUF
        ld de,HK_SPRTAB
        ld bc,HK_SPRTAB_N*3
        ldir
        ; the MSX VDP (TMS9918) is silenced once and never used again (ADR-016): the BIOS left its frame interrupt enabled, and nothing
        ; acknowledges it any more. R1 := 80h (16K, display off, interrupt off), then a status read clears a pending interrupt.
        ld a,0x80
        out (TMS_CTRL),a
        ld a,0x81
        out (TMS_CTRL),a
        in a,(TMS_CTRL)
        call b1_init
        ld a,R_PALPTR                   ; palette: the 64 entries (192 bytes) go from RAM straight to the palette port (no VRAM read-back:
        out (V9_REGSEL),a               ; a real V9990 may not return consecutive VRAM reads at CPU speed)
        xor a
        out (V9_REGDATA),a
        ld hl,HK_BOOTPAL                ; parked by stage B after the sprite table; b1_init touches no RAM, so it is still intact
        ld bc,192*256+V9_PAL
        otir
        ; (single HUD: no full pages to clear; lines 0-767 hold the atlases uploaded by stage B, HUD + buffers are cleared below)
        xor a
        ld (hk_bkind),a
        ld (hk_vmiss),a
        dec a
        ld (hk_hudenergy),a
        ld (hk_hudenergy+1),a
        xor a
        ld (hk_latch),a
        ld (hk_frames),a
        ld (hk_qframes),a
        ld (hk_lpass),a
        ld (hk_bcnt),a
        ld (hk_bcnt+1),a
        ld (hk_bstale),a
        ld (hk_srcfb),a
        ld (hk_pg),a                    ; draw buffer A first; buffer B (cleared) is displayed
        ld (hk_hic),a
        ld (hk_qhi),a
        ld (hk_mkn1),a
        ld (hk_bosspend),a              ; (the boot transfer buffer left any byte here: the first death reset the level, ADR-054)
        ld hl,VR_VPA_Y
        ld (hk_vpb),hl
        ld a,HK_LOOP_FRAMES
        ld (hk_loopn),a
        ld a,HK_CHEAT
        ld (hk_cheat),a
        ld a,VR_VPB_R17
        ld (hk_vlow),a
        ld (hk_qf1),a
        ld (hk_qf2),a
        call hk_vp_init
        call hk_txt_clear_all            ; viewport text record blank (ADR-018)
        xor a
        ld (hk_tdev),a
        ld (hk_huni),a
        ld (hk_huni+1),a
        ld (hk_hfb),a
        ld (hk_hfb+1),a
        ld (hk_ecc),a
        ld hl,HK_TOPCOL                 ; colour model: white on black (the TMS clear of init_hardware)
        ld de,HK_TOPCOL+1
        ld (hl),0xf1
        ld bc,383
        ldir
        ld hl,HK_CELLCOL
        ld de,HK_CELLCOL+1
        ld (hl),0xf1
        ld bc,383
        ldir
        call hk_pcache_clear
        xor a
        ld (hk_mmdone),a
        ld (hk_mkn),a
        ld (hk_turn),a
        ld (hk_turn+1),a
        ld (hk_tcnt),a
        ld (hk_tcnt+1),a
        ld hl,0                         ; HUD, both display buffers and their guard strips black
        ld (hk_dx),hl
        ld hl,VR_HUD_Y
        ld (hk_dy),hl
        ld hl,256
        ld (hk_nx),hl
        ld hl,VR_SPLIT_LINES            ; HUD, buffers and the black guard strips under them (display lines 192-211)
        ld (hk_ny),hl
        ld a,1
        call hk_lmmv
        di
        ld a,R_SCAY_LO
        out (V9_REGSEL),a
        xor a
        out (V9_REGDATA),a              ; R#17 = 0: lines 0-95 show VR_HUD
        ld a,VR_HUD_Y >> 8
        out (V9_REGDATA),a              ; R#18 = 3: block of VR_HUD and the two buffers, no roll
        ld a,10
        out (V9_REGSEL),a
        ld a,HK_LI_LINE
        out (V9_REGDATA),a              ; R#10: line interrupt in display line HK_LI_LINE (hk_irq syncs on line 93) ...
        xor a
        out (V9_REGDATA),a              ; R#11
        ld a,8
        out (V9_REGDATA),a              ; R#12: ... at X unit 8; hk_irq then waits for line 95 (horizontal retrace flag, see there)
        ld a,9
        out (V9_REGSEL),a
        ld a,3
        out (V9_REGDATA),a              ; R#9 = 03h: vertical + line interrupts (split screen)
        ld a,7
        out (V9_INTFLAGS),a
        call b1_display_on
        call hk_build_pageidx
        jp 0x0300                       ; the tape loader ended with JP 0300h: same state, interrupts disabled (stage B is gone)

; hk_build_pageidx - HK_PAGEIDX[p] = index of the last sprite-table entry whose address high byte < p (0 for p <= 3), for p = 0..33:
; a safe starting point for the forward scan of hk_spr_lookup (the entry containing p<<8 is that one or a later one).
hk_build_pageidx:
        ld hl,HK_PAGEIDX
        ld b,34
        ld c,0                          ; C = page
.page:  push bc
        push hl
        ld hl,HK_SPRTAB+1               ; -> address high byte of entry 0
        ld d,0                          ; D = best index
        ld e,0                          ; E = current index
.e:     ld a,(hl)
        cp c
        jr nc,.stop                     ; entry address high byte >= page: stop, keep the previous one
        ld d,e
.nx:    inc e
        ld a,e
        cp HK_SPRTAB_N
        jr z,.stop
        inc hl
        inc hl
        inc hl
        jr .e
.stop:  pop hl
        pop bc
        ld (hl),d
        inc hl
        inc c
        djnz .page
        ret

;------------------------------------------------------------------------------
; hk_end_loop - replaces `jp z,main_loop` (BE38h): the pass is over (the present happened at BE18h, where the original copied the frame
; buffer: the actors are still drawn there; redraw_dirty_tiles at BE28h erases them for the next pass). Pacing: a pass takes a whole number
; of vertical blanks (hk_frames, counted by the vertical interrupt) and at least hk_loopn (HK_LOOP_FRAMES), so the game speed does not
; depend on how much work a pass has:
;   due = hk_lpass + hk_loopn: the frame count at which the next pass may start; HALT (interrupts on, the sound keeps ticking) while
;   hk_frames is 1..16 short of it. A pass that ends on time keeps the rhythm (next due = due + hk_loopn). A pass that ends late (a turn
;   redraws the whole view: ~6 frames; also a stale reference after a shop / text screen / boot) waits for the next vertical blank, so
;   passes always start on a blank, and restarts the rhythm there: no catching up.
;------------------------------------------------------------------------------
hk_end_loop:
        ei                              ; HALT needs interrupts (they are on here; cheap insurance)
        ld a,(hk_lpass)
        ld hl,hk_loopn
        add a,(hl)
        ld c,a                          ; C = frame count at which the next pass starts
.w:     ld a,(hk_frames)
        sub c                           ; A = frames - due (mod 256): 0 = on time, 1..239 late, 240..255 = still 1..16 to wait
        cp 240
        jr c,.go
        halt
        jr .w
.go:    or a
        jr z,.ontime
        ld a,(hk_frames)                ; late: continue at the next vertical blank
        ld c,a
.l:     halt
        ld a,(hk_frames)
        cp c
        jr z,.l
        ld c,a
.ontime:
        ld a,c
        ld (hk_lpass),a
        jp MAIN_LOOP

;------------------------------------------------------------------------------
; hk_present - draw everything that changed into the hidden page and queue the page flip.   Clobbers: all (IX/IY untouched)
;   1. wait until the previous flip has been latched (the page about to be drawn was the displayed one)
;   2. HUD cells written since the page was last drawn (dirty list bit of this page)
;   3. the two viewports from the frame buffer
;   4. wait for the command engine, queue the flip, swap the roles of the pages
;------------------------------------------------------------------------------
hk_present:
        ei                              ; as copy_fb_to_vram_bottom (7DA5h): the engine relies on this EI every pass (draw_digit leaves DI)
        ld a,(hk_prep)
        or a
        call z,hk_prepare_page          ; call sites without a draw_all_actors before them (init, shop): prepare now
        xor a
        ld (hk_prep),a
        xor a
        ld (hk_mmdone),a                ; the next minimap_actors call (BE1Bh) collects and draws the markers of the next picture (hk_mm_after)
        call hk_hud_status
        call hk_hud_line_copy
        call hk_view_divider
        call b1_wait_ce
        ld a,(hk_hic)
        ld (hk_qhi),a                   ; line interrupts counted when this buffer was queued
        ld a,(hk_pg)
        xor 1
        ld (hk_pg),a                    ; next draw buffer: the other one
        ld hl,VR_VPA_Y
        ld a,VR_VPB_R17                 ; the buffer just drawn is displayed from the next line interrupt on
        jr z,.a
        ld hl,VR_VPB_Y
        ld a,VR_VPA_R17
.a:     ld (hk_vlow),a
        ld (hk_vpb),hl
        ret

; hk_wait_flip - the page about to be drawn is the one queued TWO presents ago; it must no longer be displayed, i.e. the flip queued
; one present ago must have been latched. The V9990 raises the vertical interrupt at the end of the display area and latches R#18 at the
; following frame start, so two interrupts after the queue of the previous present guarantee the latch (one does not). With three pages
; a pass of two frames or more never waits here. Fallback when interrupts are off (boot): after ~2 frames of polling, wait for two
; vertical retraces by the status port (VR 1 -> 0 twice: the second display start follows a frame start after the queue).
hk_wait_flip:
        ld bc,3000
.w:     ld a,(hk_hic)                   ; single HUD: the buffer about to be drawn is free once a line interrupt has switched the
        ld hl,hk_qhi                    ; display to the buffer queued by the previous present
        cp (hl)
        ret nz
        dec bc
        ld a,b
        or c
        jr nz,.w
        ld b,2
.vr:
.b1:    in a,(V9_STATUS)                ; (fallback) wait VR = 1 ...
        bit 6,a
        jr z,.b1
.d1:    in a,(V9_STATUS)
        bit 6,a
        jr nz,.d1                       ; ... then VR = 0: a display start
        djnz .vr
        ret

        include "hk_shims.asm"
        include "hk_viewport.asm"
        include "hk_hooks.asm"
        include "hk_sprites.asm"
        include "hk_input.asm"
        include "b1_core.asm"
        include "hk_hud.asm"
        include "hk_text.asm"
        include "hk_shop.asm"

hk_end:
        assert hk_end <= HK_LIMIT
        include "hk_segs.asm"

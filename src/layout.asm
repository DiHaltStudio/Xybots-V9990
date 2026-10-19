; XYBOTS V9990 B1 - memory layout of the never-accessed zone C125h-EAFFh (docs: MSX/doc/memory-map.md, ADR-006/007/010)
;   C125h-C361h  sprite table + page index (after boot; stage B and the boot flags C1F0h/C200h-C3FFh live here during the boot)
;   C400h-DFBFh  hook runtime code + constants (this port), 7 KiB, asserted at build time; copied LAST by stage B (ADR-019)
;   E180h-E27Fh  hook variables, E280h-E2CFh print cache
;   E900h-EA7Fh  HK_TOPCOL (HUD colour model); EB00h-EC7Fh hud.tmx scratch at init (the engine's frame buffer is not drawn, ADR-017)
;   EA80h-EAFFh  HK_MARK0 blinking minimap markers (after boot; the boot stack uses EA00h-EAF0h before)
;   DA00h-E9FFh  boot transfer buffer (4 KiB) during the boot; afterwards the runtime areas below
;   EA00h-EAFFh  boot stack (top EAF0h)
HK_BASE         equ 0xc400
HK_LIMIT        equ 0xdfc0
HK_VARS         equ 0xe180              ; free after the boot (the old HK_CELLMIX area)
HK_HUDMAP       equ 0xeb00              ; 384 bytes: hud.tmx read back from VRAM by hk_top_copy (only during the engine's init): scratch in
                                        ; the engine's unused frame buffer (after hk_boot has moved the parked sprite table away)
HK_CELLCOL      equ 0xe000              ; 384 bytes: colour byte of each viewport cell (row-12)*32+col (model of the TMS colour table)
HK_VT           equ 0xe300              ; 384 bytes: what the background image holds per viewport cell: tile id, VT_STATIC, VT_UNKNOWN
HK_GLY          equ 0xe480              ; 384 bytes: glyph code last printed with the cell as its first cell (bit 7 = 16-line glyph), FFh none
HK_VKIND        equ 0xe600              ; 384 bytes: 1 = the frame buffer decides the cell (text, cleared/striped view) until the next render
HK_VRAW         equ 0xe780              ; 384 bytes: bit 0 = static content changed, not yet in the background; bits 5-7 = glyph line offset
HK_PCACHE       equ 0xe280              ; print_string cache: 16 entries x 5 bytes (mode, y, column, string pointer), 0 = free
HK_PCACHE_N     equ 16
HK_TOPCOL       equ 0xe900              ; 384 bytes: colour byte of each HUD cell (model of the TMS colour table, hk_shims.asm)
hk_topcol       equ HK_TOPCOL           ; lower-case alias for the test scripts (hk_runtime.sym)
HK_SLIST        equ 0xdfc0              ; static cells with a pending page bit in HK_VRAW (words), up to HK_SMAX
HK_SMAX         equ 32
HK_SPRTAB       equ 0xc125              ; 179 x 3 bytes (addr lo, hi, rows<<2 | bytes-1), copied here by hk_boot (stage B is dead by then)
HK_SPRTAB_N     equ 179                 ; 177 entries of the original sprite bank + 21A0h, 21A3h (the exit's own far frames, build_b1.py)
HK_PAGEIDX      equ 0xc340              ; 34 bytes: index of the sprite-table entry containing RAM address p<<8 (p = 0..33)
; ---- VRAM map (B1, 256 pixels wide: line y at y*128). Pages y 0-211 and 256-467. Atlases (4 bpp, built by tools/assets4.py):
HK_MARK0        equ 0xea80              ; per page: 32 markers x 4 bytes (shape 0 cross / 1 ring / 2+dir arrow, x, y, 0) drawn on the page
HK_MKMAX        equ 32
LOP_XOR         equ 0x06
LOP_TP_ONE      equ 0x1f                ; transparent (source 0 skipped), every written bit := 1
LOP_TP_ZERO     equ 0x10                ; transparent, every written bit := 0
VT_UNKNOWN      equ 0xff
VT_STATIC       equ 0xfd
CELLMAP         equ 0x7f6e              ; engine: per bottom cell the tile index (12 x 32)
BOOT_BUF        equ 0xeb00              ; where stage B leaves the sprite table: the unused CPU frame buffer (build_b1.py)
HK_BOOTPAL      equ BOOT_BUF+HK_SPRTAB_N*3  ; and right after it the palette (192 bytes), read once by hk_boot
MAIN_LOOP       equ 0xbe03              ; game main loop (BE03h)

; level scenery (ADR-025, tools/scenes.py, hud4.py): the scene store in banks SCENE_BANK..+3, the copy lists in SCENE_BANK+4, the scene
; palettes and panels in SCENE_PAL (per scene 64 bytes: SCENE_COLS x (R#14 pointer, R, G, B)); the last 6 banks of the 1 MiB ROM (were
; 9 with 3 empty ones: the voice banks grew, ADR-031)
        include "music.inc"
SCENE_BANK      equ 58
SCENE_PAL       equ SCENE_BANK+5
SCENE_COLS      equ 15

; hook variables (HK_VARS)
hk_scene        equ HK_VARS+0           ; scene whose main atlas and colours are in the V9990 (stage B: 0 = scene A, uploaded at boot)
hk_romsl        equ HK_VARS+1           ; slot register value with page 1 = cartridge (copied by stage B from ROM_A)
        assert hk_romsl == MS_ROMSL
hk_ramsl        equ HK_VARS+2           ; slot register value with all pages RAM (from RAM_A)
        assert hk_ramsl == MS_RAMSL
                                        ; HK_VARS+3..+31: the Moonsound player (music.inc: state, stream, private stack)
hk_hclr         equ HK_VARS+40          ; bit h: half h is a text screen cleared by clear_viewport_fb and untouched since (a second clear is
                                        ; deferred: hk_clear_half, ADR-028); cleared by hk_vmark_half / hk_vclear_half (hk_hclr_reset)
                                        ; HK_VARS+42, +44: the Moonsound player (hk_ms_boss1 / 2, music.inc)
hk_hpend        equ HK_VARS+41          ; bit h: a deferred clear of half h is pending (hk_clear_pending, at the next background update)
hk_tmpa         equ HK_VARS+32          ; shim: the byte being written
hk_latch        equ HK_VARS+33          ; shim: 0 = next OUT (99h) is the low byte, 1 = the high byte
hk_lo           equ HK_VARS+34          ; shim: held-back low byte of the TMS address pair
hk_bcnt         equ HK_VARS+35          ; 2 bytes: data-port accesses in the current burst
hk_bstart       equ HK_VARS+37          ; 2 bytes: TMS address where the current burst started
hk_bkind        equ HK_VARS+39          ; 0 ignored, 1 pattern table, 2 colour table
hk_frames       equ HK_VARS+43          ; V9990 vertical interrupt counter (incremented by the acknowledge stub)
hk_bosspend     equ HK_VARS+45          ; 1 = boss_end_reset deferred: the partner still fights its Master Xybot (hk_boss_end, ADR-051)
hk_t0           equ HK_VARS+46          ; 2 bytes scratch
hk_bstale       equ HK_VARS+64          ; 1 = the TMS bottom pattern table is older than the frame buffer (no copy since the last publish)
hk_srcfb        equ HK_VARS+65          ; 1 = hk_cell reads the 8 pattern bytes of a bottom cell from the frame buffer instead of the TMS
hk_pg           equ HK_VARS+66          ; draw page (0/1); the other page is displayed
hk_qframes      equ HK_VARS+67          ; hk_frames value when the last page flip was queued
hk_bank         equ HK_VARS+95          ; 0 = tile bank 751Ch, 1 = 4B14h
hk_bankw        equ HK_VARS+96          ; 2 bytes: tile base pointer last seen (operand at 7D02h)
hk_bcv          equ HK_VARS+99          ; 1 = hk_bcol is valid
hk_vh           equ HK_VARS+100         ; viewport half being drawn
hk_vrow         equ HK_VARS+101
hk_vc           equ HK_VARS+102         ; 2 bytes: cell index row*32+col
hk_vt           equ HK_VARS+104
hk_gn           equ HK_VARS+109         ; hook scratch: glyph height in cells
hk_sn           equ HK_VARS+120         ; entries in HK_SLIST
hk_dirtyh       equ HK_VARS+90          ; bit h = viewport half h must be scanned into the background
hk_mmdone       equ HK_VARS+167         ; 1 = minimap_actors already ran in this pass (the second call is the XOR erase: skipped)
hk_mkn          equ HK_VARS+168         ; blinking minimap markers collected in HK_MARK0
hk_vpb          equ HK_VARS+240         ; 2 bytes: VRAM line of the display buffer being drawn (single-HUD split screen)
hk_vlow         equ HK_VARS+242         ; R#17 value that the line interrupt writes: VR_VPA_R17 = buffer A, VR_VPB_R17 = buffer B (displayed buffer)
hk_hic          equ HK_VARS+243         ; line interrupts counted
hk_qhi          equ HK_VARS+244         ; hk_hic when the last buffer was queued
hk_lpass        equ HK_VARS+246         ; hk_frames (8 bit) at which the current main-loop pass was due to start (pacing)
hk_loopn        equ HK_VARS+247         ; vertical blanks per main-loop pass, initialised to HK_LOOP_FRAMES
hk_cheat        equ HK_VARS+248         ; 1 = players immune to shots (initialised to HK_CHEAT)
hk_shop_count   equ HK_VARS+249
hk_shop_pitch   equ HK_VARS+250
hk_shop_x       equ HK_VARS+251
hk_mrow         equ HK_VARS+252         ; minimap row (0..11) restored from the clean image at the last pass (hk_mm_after, ADR-054)
hk_shop_row     equ HK_VARS+252
hk_shop_src     equ HK_VARS+253
hk_shop_dst     equ HK_VARS+254
hk_shop_half_id equ HK_VARS+255
hk_shop_last    equ HK_VARS+48          ; 2 bytes: per half, the player's sub-state at the previous panel page (shop / prepare / bonus):
                                        ; the first page of a new panel screen shows the panel alone (hk_half_ready, ADR-036)
hk_mkn1         equ HK_VARS+245         ; blinking markers XORed on VR_HUD by the previous pass (their boxes are restored from the clean image first)
HK_MARK1        equ 0xec80              ; their list (in the unused frame buffer, after the init-only HUD map scratch)
hk_qf1          equ HK_VARS+174         ; hk_frames at the last present (page flip queued) and at the one before
hk_qf2          equ HK_VARS+175
hk_mkfirst      equ HK_VARS+176         ; FFh = no player arrow drawn yet in this pass (mirror of smc_39D1)
hk_mk           equ HK_VARS+177         ; marker scratch: shape, x, y (3 bytes)
hk_mkdy         equ HK_VARS+184         ; marker XOR destination: Y high byte (draw page or VR_HUD)
hk_gcode        equ HK_VARS+185         ; HUD hooks scratch: glyph code / wall flags
hk_vmiss        equ HK_VARS+186         ; colours drawn without a pre-rendered variant (test counter, saturates at FFh)
hk_vtmp         equ HK_VARS+187
hk_hudenergy    equ HK_VARS+188         ; last displayed energy of ROCK / ACE (FFh forces both meter redraws)
hk_tr           equ HK_VARS+190         ; text record (hk_text.asm): glyph cell row, column, first line, glyph index, lines left, lines drawn
hk_tc           equ HK_VARS+191
hk_to           equ HK_VARS+192
hk_tg           equ HK_VARS+193
hk_tn           equ HK_VARS+194
hk_ts           equ HK_VARS+195
hk_tsx          equ HK_VARS+196         ; glyph x in the font atlas
hk_tspill       equ HK_VARS+197         ; 1 = the glyph reaches the frame buffer's spill area: the original routine runs too
hk_wm           equ HK_VARS+199         ; write mask of hk_lmmm_wm / LOP scratch of hk_lmmv
hk_tdev         equ HK_VARS+198
hk_rec          equ HK_VARS+200         ; 16 bytes: record of the cell being composed (hk_emit_static)
hk_ei           equ HK_VARS+216         ; hk_emit_static: next line, colour byte, background y of the cell (2 bytes)
hk_ecol         equ HK_VARS+217
hk_ebase        equ HK_VARS+218
hk_ev8          equ HK_VARS+220         ; hk_emit_static: base line of the variant of the cell colour in vfont8 / vfont16 (words, FFFFh = none)
hk_ev16         equ HK_VARS+222
hk_edraw        equ HK_VARS+224         ; colour the cell is composed in (the cell colour or FALLBACK_COL)
hk_efix         equ HK_VARS+225         ; 1 = composed into the scratch, recoloured into the background at the end
hk_rc1          equ HK_VARS+226         ; hk_recolour: target colour byte
hk_hc           equ HK_VARS+227         ; hk_half_colour / hk_half_mode: colour byte
hk_hfbo         equ HK_VARS+228         ; hk_half_colour: canonical flag before the change
hk_theme        equ HK_VARS+229         ; current static cell uses the shop text cache and transparent MSX lettering
hk_huni         equ HK_VARS+230         ; 2 bytes: half 0 / 1 is uniform text (every cell static, one colour byte) (ADR-020)
hk_hfb          equ HK_VARS+232         ; 2 bytes: half 0 / 1 is composed canonically (FALLBACK_COL) and recoloured on the page
hk_ecc          equ HK_VARS+234         ; hk_emit_static cache (ADR-021): colour last looked up (00h = none), its vfont8 / vfont16 bases,
hk_cv8          equ HK_VARS+235         ; words (FFFFh = no variant)
hk_cv16         equ HK_VARS+237
hk_credinf      equ HK_VARS+239         ; <> 0 = infinite credits (F1 + fire on the opening picture; hk_boot copies HK_BOOT_CREDINF, ADR-038)
HK_BOOT_CREDINF equ 0xc1f2              ; set by the opening (src/rom/opening.asm) next to ROM_A / RAM_A; dies with the sprite table
FALLBACK_COL    equ 0xf0                ; canonical colour: white ink on paper 0 (transparent for the recolouring copies), variants VR_VF*_FB_Y         ; text events that depart from the frame-buffer original (test counter, must stay 0)
hk_turn         equ HK_VARS+180         ; 2 bytes: turn request per player from the input routines (bit 0 left, bit 1 right)
hk_tcnt         equ HK_VARS+182         ; 2 bytes: polls since the last turn while the turn key is held (0 = not held)
HK_TURN_REPEAT  equ 8                   ; polls between repeated turns while Z / X / button B + left/right is held
hk_pnext        equ HK_VARS+161         ; print cache: next entry to replace (round robin)
hk_pk           equ HK_VARS+162         ; print hook: key (mode, y, column) + string pointer (5 bytes)
hk_p2hero       equ HK_VARS+126         ; 1 while the sprite hook draws player 2's character (IX = 9A20h): its own atlas VR_HERO2_Y
hk_prep         equ HK_VARS+128         ; 1 = hk_prepare ran for the current pass (the page is ready for sprites)
hk_sx           equ HK_VARS+131         ; command scratch: SX, SY, DX, DY, NX, NY (words)
hk_sy           equ HK_VARS+133
hk_dx           equ HK_VARS+135
hk_dy           equ HK_VARS+137
hk_nx           equ HK_VARS+139
hk_ny           equ HK_VARS+141
hk_swid         equ HK_VARS+143         ; sprite hook: width in bytes (1..3)
hk_sshift       equ HK_VARS+144
hk_scol         equ HK_VARS+145         ; signed first column
hk_stop         equ HK_VARS+146         ; top pixel row (0..103)
hk_smask        equ HK_VARS+147         ; 2 bytes: occlusion mask (bit 15 = column 0)
hk_sptr         equ HK_VARS+149         ; 2 bytes: sprite RAM pointer
hk_srows        equ HK_VARS+151
hk_sax          equ HK_VARS+152         ; atlas x of the sprite (0..216)
hk_say          equ HK_VARS+153         ; 2 bytes: atlas y (absolute VRAM line)
hk_sx0          equ HK_VARS+155         ; viewport x of the sprite (signed byte)
hk_sc0          equ HK_VARS+156         ; first cell column covered (0..15), columns covered, first cell row (0..11), rows covered
hk_scn          equ HK_VARS+157
hk_sr0          equ HK_VARS+158
hk_srn          equ HK_VARS+159
hk_sh           equ HK_VARS+160         ; viewport half of the sprite (0/1)

; entry table at HK_BASE (each entry = JP): the build patches the game to jump/call these fixed addresses
        include "../build/assets4/hud.inc"

; Pacing (ADR-008): fixed delay at the end of every pass so that the main-loop period matches the tape's mean (recalibrated for B1 in
; V9990-B1/doc/validation_report.md). 26 T-states per count.
HK_LI_LINE      equ 88                  ; line interrupt (R#10): 5 lines before HK_LI_SYNC, so its latency no longer matters (ADR-040)
HK_LI_SYNC      equ 93                  ; hk_irq polls the line-interrupt flag moved to this line (X unit 8), the old interrupt point
HK_LI_DELAY     equ 7                   ; DJNZ loops between that flag and the retrace wait (calibrated in openMSX, ADR-040)
HK_CHEAT        equ 0                   ; 1 = CHEAT (tests only): the players are immune to shots (enemy and friendly fire) and to the contact
                                        ; damage of enemies that run into them, and their energy does not drain with time (sub_AD81); the
                                        ; special attack still costs energy. `make cheat` builds build/xybots-cheat.rom with 1 and leaves
                                        ; this file and the normal ROM untouched. Runtime value: hk_cheat (poke-able).
HK_LOOP_FRAMES  equ 4                   ; game speed: a main-loop pass takes this many vertical blanks (50 Hz PAL: 3 = 16.7 passes/s; the
                                        ; tape ran ~6.7 frames per pass). A pass that finishes sooner waits for the rest; one that takes
                                        ; longer starts the next pass at once (no catching up). Runtime value: hk_loopn (poke-able).

; XYBOTS BP6 - DiHalt logo and opening picture. Runs once at power-on, before stage B. First the DiHalt logo (assets/dihalt_logo-b1.png,
; build/dihalt-logo.bin, the same as the Pinball Dreams port): V9990 mode B1 (256 x 212, 4 bpp, palette 0-15 from logo_pal.inc), the
; bitmap uploaded from ROM banks LOGO_BANK.. with the display off, then shown for LOGO_FRAMES V9990 frames (60 Hz NTSC: 4 seconds), with
; a Moonsound for LOGO_MS_FRAMES (the logo song, 10 seconds); no key is read, it cannot be skipped. Then the opening picture: V9990 mode B3 (512 x 424 interlaced), BD8 = 256 fixed RGB332
; colours (pixel byte = GGG RRR BB), the bitmap (build/opening-b3.bin, tools/build_opening.py) is uploaded from consecutive ROM banks to
; VRAM 00000h, shown until fire (SPACE, joystick A or B button 1) is pressed; then the V9990 is reset and stage B (BOOT) loads the game.
; F1 held while fire is pressed: infinite credits for the whole session (CREDINF, ADR-038).
; Copied by stage A (xybots_b1_rom.asm) to OPENING in RAM: the ROM window 4000h-7FFFh changes bank while the picture is uploaded.
; Interrupts stay disabled; the BIOS is not mapped (all pages RAM except the cartridge page), so the keys are read from the hardware.
; Generated: OPEN_BANK (first bank of the bitmap), OPEN_BANKS (banks used), OPEN_LAST_BLOCKS (256-byte blocks in the last bank), the
; same LOGO_* for the logo and LOGO_BACKDROP (its border colour).
; With a Moonsound (ADR-027, ADR-033, ADR-049) the logo song (assets/music/dihalt34.mid) plays on the OPL4 while the logo is shown
; (src/rom/opl4_player.asm, ms_open, one call per 50 Hz frame: a V9990 frame starts one, one in six has none, 60 -> 50 a second): the
; first call, after the logo upload, detects the Moonsound and copies the tone headers and the logo song's voice ("DiHalt Studio",
; ADR-034) into its RAM; at the end of the logo ms_stop.
; The opening picture has no music; while it is shown the arcade effects go into the Moonsound RAM, 1 KiB at a time (ms_fxstep, only with
; more than 128 KiB of it, ADR-044); fire copies the voice samples (ms_voice2, about 2 s, the picture still shown) and the effects not
; copied yet before stage B.

        include "../defs.asm"
        include "../music.inc"
        include "../../build/rom/opening.inc"
ROM_A           equ 0xc1f0              ; slot register value with page 1 = cartridge (set by stage A)
BOOT            equ 0xc200              ; stage B
CREDINF         equ 0xc1f2              ; = HK_BOOT_CREDINF (layout.asm): <> 0 = infinite credits (F1 + fire)
OPENING         equ 0xc500              ; where this code runs (free RAM at boot, above stage B)
LOGO_FRAMES     equ 4*60                ; DiHalt logo: 4 seconds of V9990 frames (NTSC, 60 Hz)
LOGO_MS_FRAMES  equ 10*60               ; with a Moonsound: as long as the logo song (10.0 s; build_b1.py checks its length)

        org OPENING
opening:
        ld sp,0xeaf0
        ; DiHalt logo. V9990: reset, B1 256 pixels per line 4 bpp, 212 lines NTSC, display off, no interrupts, palette 0, no cursors
        ld a,2
        out (V9_SYSCTRL),a              ; SRS = 1
        xor a
        out (V9_SYSCTRL),a
        out (V9_OUTCTL),a               ; GFX9000 board output := the V9990 (see below)
        ld a,6
        out (V9_REGSEL),a
        ld hl,.lregs
        ld bc,4*256+V9_REGDATA
        otir                            ; R#6-R#9
        ld a,13
        out (V9_REGSEL),a
        ld b,8
        otir                            ; R#13-R#20 (R#14 = palette pointer 0)
        ld hl,.lpal
        ld bc,48*256+V9_PAL
        otir                            ; colours 0-15
        xor a
        out (V9_REGSEL),a
        out (V9_REGDATA),a
        out (V9_REGDATA),a
        out (V9_REGDATA),a              ; R#0-R#2: VRAM write pointer 00000h
        ld a,(ROM_A)
        out (0xa8),a                    ; page 1 = cartridge
        ld c,V9_VRAM
        ld a,LOGO_BANK
        ld d,LOGO_BANKS
.lbank: ld (0x6000),a                   ; ASCII16: bank of 4000h-7FFFh
        ld hl,0x4000
        ld e,64
        dec d
        jr nz,.lblock
        ld e,LOGO_LAST_BLOCKS           ; the last bank
.lblock:
        ld b,0
        otir                            ; 256 bytes
        dec e
        jr nz,.lblock
        inc a
        inc d
        dec d
        jr nz,.lbank
        ld a,(ROM_A)
        ld (MS_ROMSL),a                 ; for the player (stage B sets it again for the game)
        xor a
        ld (hk_ms_state),a              ; Moonsound not checked yet
        call .msbank
        call MS_OPEN                    ; detection, the tone headers and the logo song's voice (about 0.5 s)
        ld a,8
        out (V9_REGSEL),a
        ld a,0xc2
        out (V9_REGDATA),a              ; R#8: display on, cursors off
        ld de,LOGO_FRAMES
        ld a,(hk_ms_state)
        cp 2
        jr c,.lwait
        ld de,LOGO_MS_FRAMES            ; a Moonsound: the whole logo song
.lwait: in a,(V9_STATUS)                ; next V9990 frame: VR 0 -> 1
        and 0x40
        jr nz,.lwait
.lvr:   in a,(V9_STATUS)
        and 0x40
        jr z,.lvr
        ld hl,.field
        inc (hl)
        ld a,(hl)
        cp 6
        jr c,.lmus
        ld (hl),0                       ; the sixth frame: no music frame (60 frames -> 50 a second)
        jr .lnext
.lmus:  push de
        call .msbank
        call MS_OPEN                    ; one frame of the logo song (nothing without a Moonsound)
        pop de
.lnext: dec de
        ld a,d
        or e
        jr nz,.lwait
        ld a,(hk_ms_state)
        cp 2
        jr c,.pic
        call .msbank
        call MS_STOP                    ; the logo song ends with the logo
.pic:
        ; opening picture. V9990: reset, B3 512 pixels per line 8 bpp, 424 lines interlaced, display off, no interrupts, BD8 palette, black border
        ld a,2
        out (V9_SYSCTRL),a              ; SRS = 1
        xor a
        out (V9_SYSCTRL),a
        out (V9_OUTCTL),a               ; GFX9000 board output control := 0 (as b1_init does later): without it a real board keeps showing
                                        ; the MSX video and the picture is never seen (openMSX ignores the port)
        ld a,8
        out (V9_REGSEL),a
        ld a,2
        out (V9_REGDATA),a              ; R#8: display off, VRAM 512 KiB
        ld a,6
        out (V9_REGSEL),a
        ld a,0x96
        out (V9_REGDATA),a              ; R#6: B3, 512 pixels per line, 8 bits
        ld a,0x06
        out (V9_REGDATA),a              ; R#7: EO = 1, IL = 1 => 424 lines
        ld a,0x02
        out (V9_REGDATA),a              ; R#8: display still off
        xor a
        out (V9_REGDATA),a              ; R#9: no interrupts
        ld a,13
        out (V9_REGSEL),a
        ld a,0x40
        out (V9_REGDATA),a              ; R#13: BD8, 256 fixed RGB332 colours
        ld a,15
        out (V9_REGSEL),a
        xor a
        out (V9_REGDATA),a              ; R#15: border = palette entry 0
        ld a,14
        out (V9_REGSEL),a
        xor a
        out (V9_REGDATA),a              ; R#14: palette pointer = entry 0
        out (V9_PAL),a
        out (V9_PAL),a
        out (V9_PAL),a                  ; entry 0 = black (the reset leaves it white)
        xor a
        out (V9_REGSEL),a
        out (V9_REGDATA),a
        out (V9_REGDATA),a
        out (V9_REGDATA),a              ; R#0-R#2: VRAM write pointer 00000h
        ld a,(ROM_A)
        out (0xa8),a                    ; page 1 = cartridge
        ; upload: OPEN_BANKS banks through the window 4000h-7FFFh, 64 blocks of 256 bytes each (the last bank has OPEN_LAST_BLOCKS)
        ld a,OPEN_BANK
        ld d,OPEN_BANKS
.bank:  ld (.cur),a
        ld (0x6000),a                   ; ASCII16: bank of 4000h-7FFFh
        ld hl,0x4000
        ld e,64
        ld a,d
        cp 1
        jr nz,.block
        ld e,OPEN_LAST_BLOCKS
.block: ld b,0
        ld c,V9_VRAM
        otir                            ; 256 bytes
        dec e
        jr nz,.block
        ld a,(.cur)
        inc a
        dec d
        jr nz,.bank
        ld a,8
        out (V9_REGSEL),a
        ld a,0x82
        out (V9_REGDATA),a              ; R#8: display on
        ld hl,0xffff
        ld (hk_fx_left),hl              ; the effects: the Moonsound RAM not checked yet (ms_fxstep, ADR-044)
.wait:  call .fx                        ; 1 KiB of the effects into the Moonsound RAM (nothing without one or with 128 KiB, ADR-044)
        jr nz,.keys                     ; while they are copied, the keys between two calls (about 16 ms)
.vw:    in a,(V9_STATUS)                ; next V9990 field: VR 0 -> 1
        and 0x40
        jr nz,.vw
.vr:    in a,(V9_STATUS)
        and 0x40
        jr z,.vr
.keys:
        ld a,8                          ; keyboard row 8: bit 0 = SPACE (0 = pressed)
        ld b,a
        in a,(0xaa)
        and 0xf0
        or b
        out (0xaa),a
        in a,(0xa9)
        bit 0,a
        jr z,.pressed
        ld a,15                         ; joystick 1: PSG R#15 bit 6 = 0; button A = R#14 bit 4 (0 = pressed)
        out (0xa0),a
        in a,(0xa2)
        and 0xaf
        or 0x03
        out (0xa1),a
        ld a,14
        out (0xa0),a
        in a,(0xa2)
        bit 4,a
        jr z,.pressed
        ld a,15                         ; joystick 2: R#15 bit 6 = 1
        out (0xa0),a
        in a,(0xa2)
        and 0xdf
        or 0x4c
        out (0xa1),a
        ld a,14
        out (0xa0),a
        in a,(0xa2)
        bit 4,a
        jr nz,.wait
.pressed:
        in a,(0xaa)                     ; F1 held with the fire: infinite credits (ADR-038). Keyboard row 6 bit 5 = F1 (0 = pressed);
        and 0xf0                        ; the flag goes to C1F2h, where hk_boot picks it up
        or 6
        out (0xaa),a
        in a,(0xa9)
        cpl
        and 0x20
        ld (CREDINF),a                  ; 20h = infinite, 0 = normal (power-on RAM is not trusted)
        ld a,(hk_ms_state)
        cp 2
        jr c,.quiet
        call .msbank
        call MS_VOICE2                  ; the voice samples
.fxall: call .fx                        ; the rest of the effects
        jr nz,.fxall
.quiet: ld a,2
        out (V9_SYSCTRL),a              ; V9990 back to its reset state, as stage B expects it
        xor a
        out (V9_SYSCTRL),a
        jp BOOT
.fx:    call .msbank
        jp MS_FXSTEP                    ; NZ: blocks are left
.msbank: ld a,(hk_ms_state)              ; page 1 := the music bank of the stream position (the first one until it is known)
        cp 2
        ld a,MUSIC_BANK
        jr c,.b
        ld a,(hk_ms_bank)
.b:     ld (0x6000),a
        ret
.field: db 0
.cur:   db 0                            ; bank of the picture being uploaded
.lregs: db 0x81                         ; R#6: B1, 256 pixels per line, 4 bits
        db 0x00                         ; R#7: NTSC, not interlaced, 212 lines
        db 0x42                         ; R#8: display off, cursors off
        db 0x00                         ; R#9: no interrupts
        db 0x00                         ; R#13: palette 0
        db 0x00                         ; R#14: palette pointer = entry 0
        db LOGO_BACKDROP                ; R#15: border = the logo's background
        db 0x00                         ; R#16: display adjust
        db 0,0,0,0                      ; R#17-R#20: scroll A = 0, 0
.lpal:
        include "../../build/rom/logo_pal.inc"
opening_end:

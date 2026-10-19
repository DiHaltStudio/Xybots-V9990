; Moonsound (OPL4) music (feature/music, doc/MUSIC_INTRO_ANALYSIS.md): shared by the hook runtime (layout.asm) and the player in the
; ROM (src/rom/opl4_player.asm). Every music bank holds a copy of the player at 4000h and stream data from MUSIC_DATA, so the player
; keeps running when it switches to the next bank.
MUSIC_BANK      equ 52                  ; first ROM bank of the music (banks MUSIC_BANK..MUSIC_BANK+MUSIC_BANKS-1, below the scenery)
MUSIC_BANKS     equ 6
; songs: numbers into the player's song table MS_SONGS ((bank, address) of each start, filled by tools/build_b1.py, which lays the
; songs one after another from MUSIC_DATA of MUSIC_BANK; a song goes on at MUSIC_DATA of the next bank; a song that would run past
; the last one starts in the extra music banks right after the effects, FX_BANK + the effect banks: ADR-049)
SONG_LOGO       equ 0                   ; the logo song (assets/music/dihalt34.mid, GarageBand): the DiHalt logo at power-on (ADR-033, ADR-049)
SONG_LEVEL      equ 1                   ; the arcade "Music 1": in the game, levels 1, 3, 5... (level index 3E2Ch even)
SONG_LEVEL2     equ 2                   ; the arcade "Music 4": levels 2, 4, 6... (level index odd)
SONG_MENU       equ 3                   ; the arcade intro with its two voices: title / attract
SONG_SHOP       equ 4                   ; the arcade "Shop": player 1 in the shop / PREPARE TO ENTER LEVEL (actor states 20h, 21h)
SONG_BOSS       equ 5                   ; the arcade "Master Xybots": the Master Xybot fight (72A0h <> 0)
SONGS_MAX       equ 8
MS_SONGS        equ 0x400f              ; the song table in the player: SONGS_MAX x (bank, address)
MUSIC_DATA      equ 0x4800              ; stream start in every music bank (the player before it, at most 800h bytes)
MUSIC_PAUSE     equ 100                 ; frames of silence before a song without a loop point starts again (2 s at 50 Hz)
MS_OPEN         equ 0x4003              ; player entries (opl4_player.asm): ms_open, ms_stop, ms_voice2, ms_fxstep
MS_STOP         equ 0x4006
MS_VOICE2       equ 0x4009
MS_FXSTEP       equ 0x400c              ; the effects into the Moonsound RAM, a few blocks a call (opening picture, ADR-044)
; voice samples (tools/build_b1.py): banks VOICE_BANK.. from 8000h (page 2 window): the length of the tone headers (2 bytes), the tone
; headers (12 bytes each), the lengths in 256-byte blocks of the two parts of the samples (2 + 2 bytes), zeros up to a 256-byte
; boundary, the 8-bit samples: part 1 (the voice of the logo song, ADR-034), part 2 (the others). ms_voice (first ms_open, before the
; logo is shown) copies the headers (tones 384.. at 200000h) and part 1 (at 20VOICE_RAMh) into the Moonsound RAM, ms_voice2
; (fire on the opening picture) part 2 after it
VOICE_BANK      equ 44
VOICE_BANKS     equ 8                   ; banks 44-51 (the four voices of the game start, ADR-031; the Master Xybot's, ADR-032)
VOICE_RAM       equ 0x0600              ; after the 128 tone headers of the RAM (200000h-2005FFh)
VOICE_RND_CH    equ 21                  ; wave channel of the game start voice: the player adds 0-3 (R register) to its tone number, so
                                        ; one of the four voices (tones 387-390, build_b1.py) plays at random, as in the arcade
VOICE_BOSS_CH   equ 20                  ; wave channel of the Master Xybot's voices when he is hit / destroyed (ms_bossv, ADR-032)
VOICE_TONE_HIT  equ 392                 ; their tones (build_b1.py: the order of the voices; hits 392-394, one at random), 7350 Hz: octave -2,
VOICE_TONE_DIE  equ 395                 ; F-number 341 (44100 x 2^(oct-1) x (1 + F / 1024) = 7348 Hz)
VOICE_7K_R20    equ (341 & 0x7f) << 1 | 1   ; wave register 20h + ch: F-number bits 6-0, tone number bit 8 (tones 256-511)
VOICE_7K_R38    equ 0xe0 | 341 >> 7     ; 38h + ch: octave -2, F-number bits 9-7
; the arcade effects (ADR-044; tools/build_b1.py, assets/sfx/*_22k.wav, 8-bit 22050 Hz): only with more than 128 KiB of Moonsound RAM.
; Their samples sit in ROM banks FX_BANK.. (from 8000h in the page 2 window, 256-byte blocks; FX_BLOCKS in build/rom/fx.inc) and go
; to FX_RAM+100h..FX_END of the Moonsound RAM (after the voices' 128 KiB: a 640 KiB MoonSound, openMSX's, has RAM up to 29FFFFh, the
; 1-2 MiB clones up to 2FFFFFh / 3FFFFFh),
; while the opening picture is shown (ms_fxstep); FX_RAM holds the 8 bytes "XYBOTSFX" once they are all there (ms_detect looks for
; them: hk_ms_fx). Their tone headers are among the voices' (tones FX_TONE..). In the game the player (ms_fx) watches each player's
; status every frame (shots in flight, coins, keys, energy, the actor type: exit / teleport) and keys an effect on its channel; it then
; takes the PSG effect of the same kind out of the game's mailbox (747Eh) through hk_fx_mbx (code it puts in page 3 RAM).
FX_BANK         equ 64                  ; after the scenery: the ROM grows to 2 MiB
FX_RAM          equ 0x220000
FX_TONE         equ 396                 ; tones (build_b1.py: this order) shot, double shot, hit, double hit, coin, key, energy, exit, teleport
FX_SHOT         equ FX_TONE+0
FX_SHOT2        equ FX_TONE+1
FX_HIT          equ FX_TONE+2
FX_HIT2         equ FX_TONE+3
FX_COIN         equ FX_TONE+4
FX_KEY          equ FX_TONE+5
FX_ENERGY       equ FX_TONE+6
FX_EXIT         equ FX_TONE+7
FX_TELE         equ FX_TONE+8
FX_CH_SHOT      equ 17                  ; wave channels (ms_stop leaves 17-20 alone: an exit's sound goes on into the next song)
FX_CH_HIT       equ 18
FX_CH_ITEM      equ 19
MS_ROMSL        equ 0xe181              ; = hk_romsl (layout.asm): slot register value with page 1 = cartridge
MS_RAMSL        equ 0xe182              ; = hk_ramsl: slot register value with every page RAM (the mailbox helper)
; variables (HK_VARS+3..; stage B clears hk_ms_state)
hk_ms_state     equ 0xe183              ; 0 = not checked yet, 1 = no Moonsound (original PSG driver), 2 = Moonsound idle, 3 = playing
hk_ms_bank      equ 0xe184              ; ROM bank of the stream position (valid from state 2: set by ms_detect)
hk_ms_ptr       equ 0xe185              ; 2 bytes: stream position (4000h-7FFFh window)
hk_ms_wait      equ 0xe187              ; frames to wait before the next stream entry
hk_ms_sp        equ 0xe188              ; 2 bytes: the interrupted program's SP (the game stack is in page 1, switched to the ROM)
hk_ms_song      equ 0xe18a              ; number of the song playing (SONG_*, ms_start)
hk_ms_loopb     equ 0xe18b              ; bank of the loop point of the song (0 = no loop point met yet: the end pauses and restarts)
hk_ms_loopp     equ 0xe18c              ; 2 bytes: stream position of the loop point
hk_ms_stack     equ 0xe1a0
hk_ms_boss1     equ 0xe1aa              ; = HK_VARS+42: player 1's Master Xybot parts alive (9625h) in the last frame of a fight, 0 = no fight
hk_ms_boss2     equ 0xe1ac              ; = HK_VARS+44: the same for player 2 (9648h)
                                        ; (hk_ms_stack: top of the player's private stack, E18Eh-E19Fh)
; effects (ADR-044): HK_VARS+50..+63 (game) / +51..+58 (opening), HK_VARS+68..+86 the mailbox helper, +87
hk_ms_fx        equ 0xe1b2              ; = HK_VARS+50: 1 = the effects are in the Moonsound RAM (ms_detect)
hk_fx_p1        equ 0xe1b3              ; 6 bytes: player 1 in the last frame: actor type (9A13h), energy, keys, coins, shots in flight, power-up
hk_fx_p2        equ 0xe1b9              ; 6 bytes: player 2 (9A23h, status 9627h)
hk_fx_any       equ 0xe1bf              ; this frame: bit 1 shot, bit 2 hit, bit 3 item keyed (the PSG mailbox values 2, 4, 6 as bits);
                                        ; bit 4 a power-up gained, bit 5 a player in play (ms_fxp)
hk_fx_mb        equ 0xe1d7              ; = HK_VARS+87: ms_fxp: the PSG mailbox of this frame
hk_fx_left      equ 0xe1b3              ; opening: 2 bytes, blocks still to copy (FFFFh = the RAM not checked yet)
hk_fx_blk       equ 0xe1b5              ; opening: 2 bytes, next block
hk_fx_tmp       equ 0xe1b7              ; opening: 4 bytes, the bytes at 200000h during the RAM check
hk_fx_mbx       equ 0xe1c4              ; = HK_VARS+68: 19 bytes of code (ms_detect writes them): A := (747Eh), (747Eh) &= C, page 1 = RAM meanwhile

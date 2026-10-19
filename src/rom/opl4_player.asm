; XYBOTS V9990 BP6 - Moonsound (OPL4) music player (feature/music). A copy sits at 4000h of every music ROM bank (MUSIC_BANK..), the
; stream data (tools/opl4_stream.py) follows at MUSIC_DATA. Entries (jump table, same in every music bank):
;   4000h ms_tick: hk_snd (hk_segs.asm) once per frame from the IM 1 handler: page 1 = this bank, SP = private stack in page 3,
;          interrupts off. Nothing here may touch page 1 RAM.
;   4003h ms_open: the DiHalt logo (src/rom/opening.asm) once per 50 Hz frame: the logo song (ADR-033).
;   4006h ms_stop: the opening ends: key off.
;   4009h ms_voice2: the opening ends: the other voice samples into the Moonsound RAM.
;   400Ch ms_fxstep: the opening picture: a few blocks of the effects into the Moonsound RAM (ADR-044).
; Ports: C4h status (bit 0 BUSY, bit 1 LD), C6h/C7h FM register array 2, 7Eh/7Fh wave register address / data.
        include "../music.inc"
        include "../../build/rom/fx.inc"

        org 0x4000
        jp ms_tick
        jp ms_open
        jp ms_stop
        jp ms_voice2
        jp ms_fxstep
ms_songs:
        ds 3 * SONGS_MAX,0              ; (bank, address) of each song's start: filled in by tools/build_b1.py
        assert ms_songs == MS_SONGS

; ms_tick - one frame of the game: the level song on the OPL4 while a game is on (the two level songs alternate: SONG_LEVEL when the
; level index 3E2Ch, page 0 RAM, is even, SONG_LEVEL2 when it is odd; SONG_SHOP while player 1, 9A10h in page 2 RAM, is in the shop or on PREPARE) (sound mode 00h; the original plays no tune there,
; only effects, which the PSG driver goes on playing); title / attract (FFh): the menu song, the PSG driver does not run.
; In: C = the game's sound mode (7C74h), B = the Master Xybot fight flag (72A0h, <> 0: SONG_BOSS). Out: A = 0: the caller runs the original PSG driver (sound_tick, 4131h); A <> 0: it does
; not (hk_snd2 sets its mode latch instead). In a game, after the song's frame, the Master Xybot's voices (ms_bossv).   Clobbers: all
ms_tick:
        ld a,(hk_ms_state)
        or a
        jp z,ms_detect
        ld a,c
        or a
        jr z,.game
        xor a
        ld (hk_ms_boss1),a              ; no Master Xybot fight
        ld (hk_ms_boss2),a
        ld (hk_fx_p1),a                 ; no player in play (ms_fx)
        ld (hk_fx_p2),a
        ld a,SONG_MENU
        call .song
        ld b,8
.q:     ld a,b
        out (0xa0),a
        xor a
        out (0xa1),a                    ; PSG R8-R10 := 0
        inc b
        ld a,b
        cp 11
        jr nz,.q
        ld a,14                         ; PSG register 14 (joystick) selected again: a joystick read that this interrupt cut between
        out (0xa0),a                    ; its select and its read (hk_joy_read) then reads R14, not R10 = 0 (every button pressed:
        ret                             ; a game started by itself on PRESS FIRE TO START). A = 14
.game:  push bc
        ld a,b
        or a
        ld a,SONG_BOSS
        jr nz,.lv                       ; the Master Xybot fight
        ld a,(0x9a13)                   ; player 1: actor type FFh (a state actor) and state 20h SHOP / 21h PREPARE: the shop song
        inc a
        jr nz,.lvl
        ld a,(0x9a18)
        and 0xfe
        cp 0x20
        ld a,SONG_SHOP
        jr z,.lv
.lvl:   ld a,(0x3e2c)                   ; the level index: even (first, third...) SONG_LEVEL, odd SONG_LEVEL2
        rrca
        ld a,SONG_LEVEL2
        jr c,.lv
        ld a,SONG_LEVEL
.lv:    call .song
        pop bc
        ld hl,0x9625                    ; the Master Xybot's voices: player 1's parts alive (status +33, page 2 RAM)
        ld de,hk_ms_boss1
        call ms_bossv
        ld hl,0x9648                    ; player 2's
        ld de,hk_ms_boss2
        call ms_bossv
        call ms_fx
        xor a
        ret
.song:  ld b,a                          ; song A: (re)started unless it is the one playing, then one frame
        ld a,(hk_ms_state)
        cp 3
        jr nz,.new
        ld a,(hk_ms_song)
        cp b
        jp z,ms_frame
.new:   ld a,b
        call ms_start
        jp ms_frame

; ms_open - one 50 Hz frame of the DiHalt logo: the first call (before the logo is shown) detects the Moonsound and copies the tone
; headers and the samples of part 1 (the logo song's voice, ADR-034) into its RAM, the next ones play the logo song.
; In: hk_ms_state = 0 before the first call; MS_ROMSL = slot register value with page 1 = cartridge.   Clobbers: all
ms_open:
        ld a,(hk_ms_state)
        or a
        jr nz,.play
        call ms_detect
        ld a,(hk_ms_state)
        cp 2
        ret nz
        jp ms_voice
.play:  cp 2
        ret c                           ; no Moonsound
        cp 3
        ld a,SONG_LOGO
        call nz,ms_start

; ms_frame - one frame of the song playing (selects the bank of its stream position: every music bank holds this same code).
; Clobbers: all
ms_frame:
        ld a,(hk_ms_bank)
        ld (0x6000),a
        ld a,(hk_ms_wait)
        or a
        jr z,.read
        dec a
        ld (hk_ms_wait),a
        ret
.read:  ld hl,(hk_ms_ptr)
.next:  ld a,(hl)
        inc hl
        cp 0x40
        jr c,.writes
        cp 0x80
        jr c,.fm
        cp 0xfc
        jr c,.wait
        jr z,.loop
        cp 0xfe
        jr c,.bank
        ld a,(hk_ms_loopb)              ; FEh: end of the song
        or a
        jr z,.end
        ld (hk_ms_bank),a               ; back to the loop point, same frame
        ld (0x6000),a
        ld hl,(hk_ms_loopp)
        jr .next
.end:   call ms_rewind                  ; no loop point: silence, then from the start
        ld a,MUSIC_PAUSE
        ld (hk_ms_wait),a
        ret
.loop:  ld a,(hk_ms_bank)               ; FCh: the loop point (the song jumps back here from its end)
        ld (hk_ms_loopb),a
        ld (hk_ms_loopp),hl
        jr .next
.bank:  ld a,(hk_ms_bank)               ; FDh: the stream goes on in the next bank (it holds this same code at 4000h)
        inc a
        ld (hk_ms_bank),a
        ld (0x6000),a
        ld hl,MUSIC_DATA
        jr .next
.wait:  sub 0x80                        ; 80h-FBh: no writes in this frame and the next (b - 80h)
        ld (hk_ms_wait),a
        ld (hk_ms_ptr),hl
        ret
.fm:    ld c,0xc4                       ; 40h-5Fh: n - 40h FM writes of array 0 (ports C4h/C5h), 60h-7Fh: array 1 (C6h/C7h)
        bit 5,a
        jr z,.fa
        ld c,0xc6
.fa:    and 0x1f
        jr z,.next
        ld b,a
.fw:    ld d,(hl)
        inc hl
        ld e,(hl)
        inc hl
        call ms_fm
        djnz .fw
        jr .next
.writes:
        ld b,a                          ; 00h-3Fh: n wave writes (register, value), the frame ends
        or a
        jr z,.done
.w:     ld c,(hl)
        inc hl
        ld e,(hl)
        inc hl
        ld a,c
        cp 0x08+VOICE_RND_CH            ; the wave number of the game start voice: one of four at random (ADR-031)
        call z,ms_rnd
        ld a,c
        cp 0x68+VOICE_RND_CH            ; its key-on: only on the first level (the game starts), not when the song starts again
        call z,ms_vgate                 ; on level 3, 5... or back from the shop
        call ms_write
        djnz .w
.done:  ld (hk_ms_ptr),hl
        ret

; ms_bossv - the Master Xybot's voice of one player (ADR-032): a part destroyed (status +33 lower than in the last frame of the
; fight) -> one of the hit voices VOICE_TONE_HIT..+2 at random (ADR-045), the last one (+33 = 0: the fight is won; 72A0h may already be 0) -> VOICE_TONE_DIE ("I'll be back"). A
; player who dies in the fight leaves +33 as it is: no voice. Called after the song's frame (a song start keys every channel off).
; In: HL = the player's status +33, DE = its last value (hk_ms_boss1 / 2: 0 = no fight), B = 72A0h.   Clobbers: AF, C, E; keeps B, D, HL
ms_bossv:
        ld a,(de)
        or a
        jr z,.set                       ; no fight in the last frame
        ld c,a
        ld a,(hl)
        cp c
        jr nc,.set                      ; no part fewer
        or a
        ld a,VOICE_TONE_DIE & 0xff
        jr z,.key
.rnd:   ld a,r                          ; a hit: one of the three hit voices at random (R register: 0-2; 3 -> again, R has moved on)
        and 3
        cp 3
        jr z,.rnd
        add a,VOICE_TONE_HIT & 0xff
.key:   push bc
        push de
        push hl
        call ms_vkey
        pop hl
        pop de
        pop bc
.set:   ld a,b
        or a
        jr z,.st                        ; no fight now: 0
        ld a,(hl)
.st:    ld (de),a
        ret

; ms_vkey - key on the 7350 Hz voice tone 256 + A on channel VOICE_BOSS_CH (as build_b1.py writes a voice key-on).   Clobbers: AF, BC, DE, HL
ms_vkey:
        ld b,VOICE_BOSS_CH
        ld hl,VOICE_7K_R20 << 8 | VOICE_7K_R38
        jr ms_key

; ms_fxkey - key on the 22050 Hz effect tone 256 + A (octave 0, F-number 0) on channel B.   Clobbers: AF, BC, DE, HL
ms_fxkey:
        ld hl,0x0100

; ms_key - key on tone 256 + A on wave channel B, H = register 20h + ch (F-number bits 6-0, tone bit 8), L = register 38h + ch
; (octave, F-number bits 9-7): key off, the pitch, the wave number (loads the tone header), TL 0, key on in the centre.
; Clobbers: AF, C, D, E
ms_key:
        ld d,a
        ld a,0x68
        add a,b
        ld c,a
        ld e,0
        call ms_write                   ; key off
        ld a,0x20
        add a,b
        ld c,a
        ld e,h
        call ms_write
        ld a,0x08
        add a,b
        ld c,a
        ld e,d
        call ms_write                   ; the wave number (loads the tone header)
        ld a,0x38
        add a,b
        ld c,a
        ld e,l
        call ms_write
        ld a,0x50
        add a,b
        ld c,a
        ld e,0x01
        call ms_write                   ; TL 0
        ld a,0x68
        add a,b
        ld c,a
        ld e,0x80
        jp ms_write                     ; key on, centre

; ms_fx - the arcade effects in the game (ADR-044), once a frame after the song: for each player in play in this frame and the last
; one (actor type 1) a shot more in flight (status +23) keys the shot (the double one with a power-up, status +24 <> 0), a shot fewer
; with the impact request in the PSG mailbox keys the hit (a shot that only runs out of life is silent, as in the original), more
; coins (+6) / keys (+5) / energy (+4) the coin / key / energy pickup; the actor turning from 1 into 16h (the exit pad) / 0Eh (a
; teleport pad) keys the exit / teleport. Then the PSG effect of a kind keyed now is taken out of the mailbox (the PSG driver runs
; after this: an enemy's shot, an explosion, a shop purchase, the gun power-up keep their PSG sound).   Clobbers: all
ms_fx:
        ld a,(hk_ms_fx)
        or a
        ret z
        xor a
        ld (hk_fx_any),a
        ld c,0xff
        call hk_fx_mbx                  ; A = the mailbox (2 shot, 4 hit / explosion, 6 pickup / purchase)
        push af
        ld ix,0x9604                    ; player 1: status block, last frame, actor type
        ld iy,hk_fx_p1
        ld hl,0x9a13
        call ms_fxp
        pop af
        push af
        ld ix,0x9627                    ; player 2
        ld iy,hk_fx_p2
        ld hl,0x9a23
        call ms_fxp
        pop af
        ld c,a
        cp 6                            ; a pickup request with a player in play and no coin, key, gun or energy gained: an energy
        jr nz,.kinds                    ; pod taken with the energy at its cap (it adds nothing; the cheat ROM never drains it)
        ld a,(hk_fx_any)
        and 0x38
        cp 0x20
        jr nz,.kinds
        push bc
        ld a,FX_ENERGY & 0xff
        ld b,FX_CH_ITEM
        call ms_fxkey
        pop bc
        ld hl,hk_fx_any
        set 3,(hl)
.kinds: ld a,(hk_fx_any)
        bit 1,a
        jr z,.n2
        ld b,a
        ld a,c
        cp 2
        ld a,b
        jr z,.clr
.n2:    bit 2,a
        jr z,.n4
        ld b,a
        ld a,c
        cp 4
        ld a,b
        jr z,.clr
.n4:    bit 3,a
        ret z
        ld a,c
        cp 6
        ret nz
.clr:   ld c,0
        jp hk_fx_mbx                    ; the PSG effect of that kind: out

; ms_fxp - one player. In: IX = status block, IY = its record of the last frame (type, energy, keys, coins, shots, power-up), HL =
; actor type, A = the PSG mailbox. hk_fx_any: bit 5 = in play in both frames, bit 4 = power-up level up (the gun: PSG).   Clobbers: all
ms_fxp:
        ld (hk_fx_mb),a
        ld c,(hl)                       ; actor type now
        ld a,(iy+0)
        ld (iy+0),c
        cp 1
        jp nz,.store                    ; not in play in the last frame: no comparison
        ld a,c
        ld b,FX_CH_ITEM
        cp 0x16
        ld a,FX_EXIT & 0xff
        jp z,.pad
        ld a,c
        cp 0x0e
        ld a,FX_TELE & 0xff
        jp z,.pad
        ld a,c
        dec a
        jp nz,.store
        ld hl,hk_fx_any
        set 5,(hl)                      ; in play
        ld a,(ix+24)
        cp (iy+5)
        jr z,.pw
        jr c,.pw
        set 4,(hl)                      ; the gun power-up
.pw:    ld a,(ix+23)                    ; shots in flight
        cp (iy+4)
        jr z,.items
        jr c,.fewer
        ld a,(ix+24)                    ; a shot more: power-up level
        or a
        ld a,FX_SHOT & 0xff
        jr z,.shot
        ld a,FX_SHOT2 & 0xff
.shot:  ld b,FX_CH_SHOT
        call ms_fxkey
        ld hl,hk_fx_any
        set 1,(hl)
        jr .items
.fewer: ld a,(hk_fx_mb)
        cp 4
        jr nz,.items                    ; no impact: the shot ran out of life
        ld a,(ix+24)
        or a
        ld a,FX_HIT & 0xff
        jr z,.hit
        ld a,FX_HIT2 & 0xff
.hit:   ld b,FX_CH_HIT
        call ms_fxkey
        ld hl,hk_fx_any
        set 2,(hl)
.items: ld a,(ix+6)                     ; coins
        cp (iy+3)
        ld a,FX_COIN & 0xff
        call nz,.more
        ld a,(ix+5)                     ; keys
        cp (iy+2)
        ld a,FX_KEY & 0xff
        call nz,.more
        ld a,(ix+4)                     ; energy
        cp (iy+1)
        ld a,FX_ENERGY & 0xff
        call nz,.more
.store: ld a,(ix+4)
        ld (iy+1),a
        ld a,(ix+5)
        ld (iy+2),a
        ld a,(ix+6)
        ld (iy+3),a
        ld a,(ix+23)
        ld (iy+4),a
        ld a,(ix+24)
        ld (iy+5),a
        ret
.more:  ret c                           ; fewer (spent, drained): nothing
        ld b,FX_CH_ITEM
        call ms_fxkey
        ld hl,hk_fx_any
        set 3,(hl)
        ret
.pad:   call ms_fxkey
        jr .store

; ms_rnd - E += 0-3 from the refresh register R (it counts the instructions run since power-on: how long the player waited on the title).
; Clobbers: AF
ms_rnd:
        ld a,r
        and 3
        add a,e
        ld e,a
        ret

; ms_vgate - E := 0 (no key-on) unless the level index (3E2Ch, page 0 RAM: only the game's level song keys channel VOICE_RND_CH)
; is 0.   Clobbers: AF
ms_vgate:
        ld a,(0x3e2c)
        or a
        ret z
        ld e,0
        ret

; ms_write - wave register C := E.   Clobbers: AF
ms_write:
        in a,(0xc4)
        and 3                           ; BUSY or LD (a tone header is loading)
        jr nz,ms_write
        ld a,c
        out (0x7e),a
.d:     in a,(0xc4)
        and 3
        jr nz,.d
        ld a,e
        out (0x7f),a
        ret

; ms_fm - FM register D of the array at ports C, C+1 (C = C4h or C6h) := E.   Clobbers: AF
ms_fm:
        in a,(0xc4)
        rra
        jr c,ms_fm                      ; BUSY
        ld a,d
        out (c),a
.d:     in a,(0xc4)
        rra
        jr c,.d
        inc c
        out (c),e
        dec c
        ret

; ms_rewind - stream position := start of the song (hk_ms_song, from ms_songs), no loop point yet.   Clobbers: AF, DE, HL
ms_rewind:
        ld a,(hk_ms_song)
        ld l,a
        add a,a
        add a,l
        ld l,a
        ld h,0
        ld de,ms_songs
        add hl,de
        ld a,(hl)
        inc hl
        ld e,(hl)
        inc hl
        ld d,(hl)
        ld (hk_ms_bank),a
        ld (0x6000),a                   ; same code at 4000h in every music bank
        ld (hk_ms_ptr),de
        xor a
        ld (hk_ms_loopb),a
        ret

; ms_start - song A (SONG_*) from its start; any channel still sounding is keyed off first.   Clobbers: AF, BC, DE, HL
ms_start:
        ld (hk_ms_song),a
        call ms_stop
        call ms_rewind
        xor a
        ld (hk_ms_wait),a
        ld a,3
        ld (hk_ms_state),a
        ret

; ms_stop - key off the 24 wave channels (damp: fast release) and the 18 FM channels (B0h-B8h of both arrays := 0); not the channels of
; the effects and of the Master Xybot's voices, 17-20 (his "I'll be back" and the exit's sound go on while the game changes the song;
; they end by themselves).
; Clobbers: AF, BC, DE
ms_stop:
        ld c,0x68
        ld e,0x40
.k:     ld a,c
        cp 0x68+FX_CH_SHOT
        call c,ms_write
        ld a,c
        cp 0x68+VOICE_BOSS_CH+1
        call nc,ms_write
        inc c
        ld a,c
        cp 0x80
        jr nz,.k
        ld c,0xc4
        call .fm
        ld c,0xc6
        call .fm
        ld a,2
        ld (hk_ms_state),a
        ret
.fm:    ld d,0xb0
        ld e,0
.f:     call ms_fm
        inc d
        ld a,d
        cp 0xb9
        jr nz,.f
        ret

; ms_detect - first call: is there an OPL4? Port C4h reads FFh without one. With one: OPL4 mode (FM register 105h := 03h: NEW, NEW2),
; the device ID in wave register 02h (bits 7-5 = 001), then the Moonsound set-up (wave register 02h := 10h: tone headers of the ROM
; at 0, of the RAM at 200000h; F8h / F9h := 0: FM and wave mix at full level). Every wait is bounded (an unknown device may sit on C4h).
; Out: A = 0 (this frame the PSG driver runs).   Clobbers: all
ms_detect:
        ld a,1
        ld (hk_ms_state),a              ; until proven otherwise: no Moonsound
        in a,(0xc4)
        inc a
        jr z,.none
        call ms_ready
        jr nz,.none
        ld a,5
        out (0xc6),a
        call ms_ready
        jr nz,.none
        ld a,3
        out (0xc7),a
        call ms_ready
        jr nz,.none
        ld a,2
        out (0x7e),a
        call ms_ready
        jr nz,.none
        in a,(0x7f)
        and 0xe0
        cp 0x20
        jr nz,.none
        call ms_fxchk
        ld c,0x02
        ld e,0x10
        call ms_write
        ld c,0xf8
        ld e,0
        call ms_write
        inc c
        call ms_write
        ld a,MUSIC_BANK
        ld (hk_ms_bank),a               ; valid from now on (hk_snd and the opening select hk_ms_bank); no song yet
        ld a,2
        ld (hk_ms_state),a
.none:  xor a
        ret

; ms_voice - the first part of the voices (VOICE_BANK.. in the page 2 window, music.inc) into the Moonsound RAM: all the tone headers
; to 200000h (tones 384..), the samples of part 1 (the logo song's voice) to 20VOICE_RAMh. Page 2 is the cartridge meanwhile (no RAM of page 2
; is used here); the slot register is left at MS_ROMSL (page 1 = cartridge).   Clobbers: all
ms_voice:
        call ms_vsel
        ld a,0x20
        ld hl,0
        call ms_addr
        ld hl,0x8000
        ld c,(hl)
        inc hl
        ld b,(hl)
        inc hl
        ld d,VOICE_BANK
        call ms_mem                     ; the tone headers
        ld a,0x20
        ld hl,VOICE_RAM
        call ms_addr
        call ms_vlen
        ld c,(hl)
        inc hl
        ld b,(hl)                       ; BC = blocks of part 1
        ex de,hl
        call ms_blocks
        jr ms_vend

; ms_voice2 - the second part of the samples after the first one (state 2 or 3 only).   Clobbers: all
ms_voice2:
        ld a,(hk_ms_state)
        cp 2
        ret c
        call ms_vsel
        call ms_vlen
        ld c,(hl)
        inc hl
        ld b,(hl)                       ; BC = blocks of part 1
        inc hl
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a
        push hl                         ; blocks of part 2
        ex de,hl
        add hl,bc
        push hl                         ; its first block
        ld a,VOICE_RAM >> 8
        add a,c
        ld h,a
        ld a,0x20
        adc a,b
        ld l,VOICE_RAM & 0xff
        call ms_addr                    ; 20VOICE_RAMh + part 1
        pop hl
        pop bc
        call ms_blocks
ms_vend:
        ld c,0x02
        ld e,0x10                       ; back to sound generation
        call ms_write
        ld a,(MS_ROMSL)
        out (0xa8),a
        ret

; ms_vsel - page 2 := the cartridge (the slot of page 1), bank VOICE_BANK; the Moonsound in memory access mode.   Clobbers: all
; In an expanded cartridge slot (slot expander, ADR-053) the sub-slot of page 2 is whatever the BIOS left (the HB-10P leaves sub-slot 3:
; an empty one read FFh and the upload never ended): its sub-slot register FFFFh, reachable with page 3 in the cartridge slot, gets the
; sub-slot of page 1. Interrupts are off at every call (the IM 1 handler, the opening); nothing of page 3 is touched meanwhile.
ms_vsel:
        ld a,(MS_ROMSL)
        ld b,a
        and 0x0c
        ld c,a                          ; C = slot of page 1 (bits 2-3)
        add a,a
        add a,a                         ; slot of page 1 -> page 2
        ld d,a
        ld a,b
        and 0xcf
        or d
        ld e,a                          ; E = slot register with page 2 = the cartridge
        ld a,c
        rlca
        rlca
        rlca
        rlca                            ; -> page 3
        ld d,a
        ld a,e
        and 0x3f
        or d
        out (0xa8),a                    ; page 3 = the cartridge slot as well (FFFFh = its sub-slot register if expanded)
        ld a,(0xffff)
        cpl
        ld d,a                          ; D = the sub-slot register (not expanded: a ROM byte, the write below goes nowhere)
        and 0x0c
        add a,a
        add a,a
        ld h,a
        ld a,d
        and 0xcf
        or h
        ld (0xffff),a                   ; page 2 = the sub-slot of page 1
        ld a,e
        out (0xa8),a                    ; page 3 = RAM again, page 2 = the cartridge
        ld a,VOICE_BANK
        ld (0x7000),a                   ; ASCII16: bank of page 2
        ld c,0x02
        ld e,0x11                       ; memory access mode (the RAM through register 06h)
        jp ms_write

; ms_vlen - Out: HL = address of the part lengths (8002h + length of the headers), DE = block of the first sample (the headers are at
; most 600h bytes).   Clobbers: AF, BC
ms_vlen:
        ld hl,(0x8000)
        ld bc,6 + 255
        add hl,bc
        ld e,h
        ld d,0
        ld hl,(0x8000)
        ld bc,0x8002
        add hl,bc
        ret

; ms_addr - Moonsound memory address A:HL, then register 06h selected.   Clobbers: AF, C, E
ms_addr:
        ld c,0x03
        ld e,a
        call ms_write
        inc c
        ld e,h
        call ms_write
        inc c
        ld e,l
        call ms_write
.a6:    in a,(0xc4)
        and 3
        jr nz,.a6
        ld a,0x06
        out (0x7e),a
        ret

; ms_mem - BC bytes from HL (page 2 window, bank D; goes on in the next bank at C000h) into the Moonsound RAM (register 06h selected,
; the address counts up).   Out: HL after the data, D bank.   Clobbers: AF, BC
ms_mem:
.l:     in a,(0xc4)
        rra
        jr c,.l
        ld a,(hl)
        out (0x7f),a
        inc hl
        bit 6,h
        jr z,.n
        inc d                           ; HL = C000h: the next bank
        ld a,d
        ld (0x7000),a
        ld h,0x80
.n:     dec bc
        ld a,b
        or c
        jr nz,.l
        ret

; ms_blocks - BC (may be 0) 256-byte blocks of the voice data from block HL (block 0 = 8000h of bank VOICE_BANK, 64 blocks a bank) into
; the Moonsound RAM (register 06h selected). About 16 us a byte (ms_mem: about 30).   Clobbers: all
ms_blocks:
        ld a,b
        or c
        ret z
        ld a,l
        and 0x3f
        or 0x80
        ld d,a                          ; address of the block in the window
        ld a,l
        rlca
        rlca
        and 3
        ld e,a
        ld a,h
        add a,a
        add a,a
        or e
        add a,VOICE_BANK
        ld e,a                          ; its bank
        ld (0x7000),a
        ld h,d
        ld l,0
.blk:   push bc
        ld b,0
.byte:  in a,(0xc4)
        rra
        jr c,.byte
        ld a,(hl)
        out (0x7f),a
        inc hl
        djnz .byte
        pop bc
        bit 6,h
        jr z,.same
        ld h,0x80                       ; C000h: the next bank
        inc e
        ld a,e
        ld (0x7000),a
.same:  dec bc
        ld a,b
        or c
        jr nz,.blk
        ret

; ms_ready - wait until BUSY is clear, at most 256 reads. Out: Z = ready.   Clobbers: AF, B
ms_ready:
        ld b,0
.r:     in a,(0xc4)
        and 1
        ret z
        djnz .r
        or 1
        ret

;------------------------------------------------------------------------------------------------------------------------------------
; the arcade effects into the Moonsound RAM (ADR-044, music.inc)

; ms_fxchk - (ms_detect) are the effects in the Moonsound RAM: "XYBOTSFX" at FX_RAM -> hk_ms_fx := 1, else 0; no player in play yet;
; the mailbox helper into page 3 RAM (hk_fx_mbx). Leaves the Moonsound in memory access mode.   Clobbers: all
ms_fxchk:
        ld hl,ms_mbx
        ld de,hk_fx_mbx
        ld bc,ms_mbx_end-ms_mbx
        ldir
        xor a
        ld (hk_fx_p1),a
        ld (hk_fx_p2),a
        ld (hk_ms_fx),a
        ld c,0x02
        ld e,0x11
        call ms_write                   ; memory access mode
        ld a,FX_RAM >> 16
        ld hl,FX_RAM & 0xffff
        call ms_addr
        ld hl,ms_fxsig
        ld b,8
.c:     call ms_rd
        cp (hl)
        ret nz
        inc hl
        djnz .c
        ld a,1
        ld (hk_ms_fx),a
        ret
ms_fxsig:
        db "XYBOTSFX"

; ms_mbx - copied to hk_fx_mbx (page 3): the game's PSG mailbox 747Eh is in page 1, where the player's bank is. In: C = mask.
; Out: A = the mailbox before, the mailbox &= C.   Clobbers: AF, B, HL
ms_mbx:
        ld a,(MS_RAMSL)
        out (0xa8),a                    ; page 1 = RAM (the IM 1 handler: interrupts off)
        ld hl,0x747e
        ld b,(hl)
        ld a,b
        and c
        ld (hl),a
        ld a,(MS_ROMSL)
        out (0xa8),a                    ; page 1 = the music bank again
        ld a,b
        ret
ms_mbx_end:
        assert ms_mbx_end - ms_mbx <= 19

; ms_rd - the next byte of the Moonsound memory (register 06h selected, memory access mode).   Clobbers: F
ms_rd:
        in a,(0xc4)
        and 3
        jr nz,ms_rd
        in a,(0x7f)
        ret

; ms_wr - A into the Moonsound memory (register 06h selected, memory access mode).   Clobbers: F
ms_wr:
        push af
.w:     in a,(0xc4)
        and 3
        jr nz,.w
        pop af
        out (0x7f),a
        ret

; ms_fxstep - (opening picture, ADR-044) the next FX_STEP blocks of the effects into the Moonsound RAM; the first call checks the RAM
; first (ms_fxram).
; After the last block "XYBOTSFX" at FX_RAM. In: hk_fx_left = FFFFh before the first call.  Out: NZ = blocks are left.  Clobbers: all
FX_STEP         equ 4                   ; 1 KiB a call, about 16 ms
ms_fxstep:
        ld a,(hk_ms_state)
        cp 2
        jr c,.none
        ld hl,(hk_fx_left)
        ld a,h
        and l
        inc a
        call z,ms_fxram
        ld hl,(hk_fx_left)
        ld a,h
        or l
        ret z
        call ms_vsel                    ; page 2 = the cartridge, memory access mode
        ld hl,(hk_fx_blk)
        inc hl                          ; FX_RAM + 100h + block * 100h
        ld a,h
        add a,FX_RAM >> 16
        ld h,l
        ld l,0
        call ms_addr
        ld c,FX_STEP
.blk:   ld hl,(hk_fx_blk)
        ld a,l
        and 0x3f
        or 0x80
        ld d,a                          ; the block's address in the window
        add hl,hl
        add hl,hl
        ld a,h
        add a,FX_BANK
        ld (0x7000),a                   ; its bank
        ld h,d
        ld l,0
        ld b,0
.byte:  in a,(0xc4)
        rra
        jr c,.byte
        ld a,(hl)
        out (0x7f),a
        inc hl
        djnz .byte
        ld hl,(hk_fx_blk)
        inc hl
        ld (hk_fx_blk),hl
        ld hl,(hk_fx_left)
        dec hl
        ld (hk_fx_left),hl
        ld a,h
        or l
        jr z,.last
        dec c
        jr nz,.blk
        jr .end
.last:  ld a,FX_RAM >> 16
        ld hl,FX_RAM & 0xffff
        call ms_addr
        ld hl,ms_fxsig
        ld b,8
.sig:   ld a,(hl)
        call ms_wr
        inc hl
        djnz .sig
.end:   call ms_vend
        ld hl,(hk_fx_left)
        ld a,h
        or l
        ret
.none:  xor a
        ret

; ms_fxram - the RAM check: the effects go to FX_RAM+100h..FX_END only when both ends hold RAM of their own (an unexpanded MoonSound
; repeats its 128 KiB there: ms_probe). hk_fx_left := FX_BLOCKS (0: no effects), hk_fx_blk := 0.   Clobbers: all
ms_fxram:
        ld hl,0
        ld (hk_fx_left),hl
        ld (hk_fx_blk),hl
        ld c,0x02
        ld e,0x11
        call ms_write                   ; memory access mode
        ld ix,ms_probes
        ld b,3
.p:     push bc
        call ms_probe
        pop bc
        jr nz,.no
        ld de,6
        add ix,de
        djnz .p
        ld hl,FX_BLOCKS
        ld (hk_fx_left),hl
.no:    ld c,0x02
        ld e,0x10
        jp ms_write                     ; sound generation again
ms_probes:                              ; (address T, address M) pairs, 3 bytes each, bits 23-16 first
        db FX_RAM >> 16, FX_RAM >> 8 & 255, FX_RAM & 255, 0x20, 0, 0
        db FX_END >> 16, FX_END >> 8 & 255, FX_END & 255, (FX_END - 0x20000) >> 16, (FX_END - 0x20000) >> 8 & 255, FX_END & 255
        db FX_END >> 16, FX_END >> 8 & 255, FX_END & 255, (FX_END - 0x40000) >> 16, (FX_END - 0x40000) >> 8 & 255, FX_END & 255

; ms_probe - is T (IX+0..2) RAM of its own, not M (IX+3..5) again? The 4 bytes at M are kept, their complement written at T: it must
; read back there, and M must not change (else M is put back). Memory access mode.  Out: Z = yes.   Clobbers: AF, BC, DE, HL
ms_probe:
        call .m
        ld hl,hk_fx_tmp
        ld b,4
.rd:    call ms_rd
        ld (hl),a
        inc hl
        djnz .rd
        call .t
        ld hl,hk_fx_tmp
        ld b,4
.wr:    ld a,(hl)
        cpl
        call ms_wr
        inc hl
        djnz .wr
        call .t
        ld hl,hk_fx_tmp
        ld b,4
.cmp:   call ms_rd
        cpl
        cp (hl)
        ret nz                          ; no RAM at T
        inc hl
        djnz .cmp
        call .m
        ld hl,hk_fx_tmp
        ld b,4
.same:  call ms_rd
        cp (hl)
        jr nz,.mirror
        inc hl
        djnz .same
        ret                             ; Z
.mirror:
        call .m                         ; T is M again: M back as it was
        ld hl,hk_fx_tmp
        ld b,4
.put:   ld a,(hl)
        call ms_wr
        inc hl
        djnz .put
        or 1
        ret                             ; NZ
.t:     ld a,(ix+0)
        ld h,(ix+1)
        ld l,(ix+2)
        jp ms_addr
.m:     ld a,(ix+3)
        ld h,(ix+4)
        ld l,(ix+5)
        jp ms_addr

ms_end:
        assert ms_end <= MUSIC_DATA

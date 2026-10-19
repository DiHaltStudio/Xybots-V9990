;==============================================================================
;  XYBOTS V9990 B1 - controls (ADR-015, user request 2026-09-24)
;
;  Original: player 1 = joystick A, else keyboard SPACE fire / P up / L down / Z left / X right; player 2 = joystick B; a turn is FIRE held
;  with LEFT or RIGHT for 3 polls (sub_96B2 -> l_9791), the shot going off when fire is released.
;  New (ADR-037, 2026-10-15): player 1 keyboard CURSORS move, SPACE fires, N turns left, M turns right; player 2 keyboard W A S D move,
;  CTRL fires, SHIFT + A / D turns (hk_kbd2; ADR-041, was CTRL + A / D); joysticks (A player 1, B player 2): button A fires,
;  button B held with left/right turns (left/right are then not movements). Holding fire no longer stops the player: the directions keep
;  moving while the shot charges (it goes off on release, as before). FIRE + DOWN is still the special attack; P pauses and P resumes
;  (pause_check rewritten by build_b1.py, hk_pause_wait).
;  input_player1 / input_player2 are replaced (same result byte: bit 4 fire, 3 up, 2 down, 1 left, 0 right, so every caller - start,
;  continue, shop, boss fight - keeps working); the turn request is kept apart in hk_turn (bit 0 left, bit 1 right) and executed by the hook
;  of sub_9698 (the in-game controller): one 90 degree turn when the key is pressed, then one every HK_TURN_REPEAT polls while held (the
;  original turned after 3 polls of FIRE + LEFT/RIGHT and every 3 polls after that, which at the port's speed is ~7 turns per second).
;==============================================================================

; hk_input1 - entry of input_player1 (BEE9h). Out: A = game input bits (joystick A OR keyboard); hk_turn = turn request of player 1.
;   Clobbers: A, BC, DE, HL (the original clobbers A, C, DE, HL).
hk_input1:
        ld a,0x0f
        out (0xa0),a
        in a,(0xa2)
        and 0xaf                        ; R15: port 1 selected (bit 6 = 0), pin 8 low
        or 0x03                         ; pins 6/7 of port 1 high (buttons readable)
        out (0xa1),a
        call hk_joy_read                ; B = game bits, C = turn bits
        ; keyboard row 8: bit 0 SPACE, bit 4 LEFT, bit 5 UP, bit 6 DOWN, bit 7 RIGHT (active low)
        ld a,8
        call hk_kbd_row
        ld e,a                          ; E = row 8, 1 = pressed
        bit 0,e
        jr z,.nf
        set 4,b                         ; SPACE: fire
.nf:    bit 5,e
        jr z,.nu
        set 3,b                         ; UP
.nu:    bit 6,e
        jr z,.nd
        set 2,b                         ; DOWN
.nd:    bit 4,e
        jr z,.nl
        set 1,b                         ; LEFT
.nl:    bit 7,e
        jr z,.nr
        set 0,b                         ; RIGHT
.nr:    ld a,4
        call hk_kbd_row                 ; row 4: bit 3 N, bit 2 M
        bit 3,a
        jr z,.nz
        set 0,c                         ; N: turn left
.nz:    bit 2,a
        jr z,.nx
        set 1,c                         ; M: turn right
.nx:    ld a,c
        ld (hk_turn),a
        ld a,b
        ret

; hk_input2 - entry of input_player2 (BF42h): joystick B (as the original) OR the keyboard W A S D / CTRL (hk_kbd2, ADR-037).
;   Out: A = game bits; hk_turn+1 = turn request of player 2.
hk_input2:
        ld a,0x0f
        out (0xa0),a
        in a,(0xa2)
        and 0xdf                        ; R15: pin 8 of port 2 low
        or 0x4c                         ; port 2 selected (bit 6), pins 6/7 of port 2 high
        out (0xa1),a
        call hk_joy_read
        call hk_kbd2
        ld a,c
        ld (hk_turn+1),a
        ld a,b
        ret

; hk_joy_read - R14 of the selected port: bits 0 up, 1 down, 2 left, 3 right, 4 button A, 5 button B (0 = pressed).
;   Out: B = game bits (directions through the original table BF66h, A -> fire), C = turn bits (button B + left -> 1, + right -> 2; the
;   left/right bits are then removed from B).   Clobbers: AF, DE, HL
hk_joy_read:
        ld a,0x0e
        out (0xa0),a
        in a,(0xa2)
        cpl
        and 0x3f
        ld e,a                          ; E = raw, 1 = pressed
        and 0x0f
        ld l,a
        ld h,0
        ld bc,0xbf66                    ; nibble -> game direction bits (bit reversal table of the original)
        add hl,bc
        ld b,(hl)
        bit 4,e
        jr z,.na
        set 4,b                         ; button A: fire
.na:    ld c,0
        bit 5,e
        ret z                           ; button B not held
        bit 1,b
        jr z,.bl
        set 0,c                         ; B + left: turn left
.bl:    bit 0,b
        jr z,.br
        set 1,c                         ; B + right: turn right
.br:    ld a,b
        and 0xfc
        ld b,a                          ; with B held, left/right do not move
        ret

; hk_kbd_row - A = keyboard row: the row's column byte with 1 = pressed. PPI port C high nibble preserved (as key_test).   Clobbers: AF, H
hk_kbd_row:
        ld h,a
        in a,(0xaa)
        and 0xf0
        or h
        out (0xaa),a
        in a,(0xa9)
        cpl
        ret

; hk_ctrl - entry of sub_9698 (the in-game controller of player_update), replaced entirely. Reads the player's input like the original
; (fire latch address into the SMC of sub_96B2), executes a pending turn, removes the old FIRE + LEFT/RIGHT turn, then continues in
; sub_96B2 with A = input bits. A turn poll does nothing else (as in the original: turning does not move); the fire latch is untouched.
hk_ctrl:
        ld hl,0x9626                    ; fire latch of player 1 (block +34)
        ld a,(0x72a7)                   ; cur_viewport = player
        or a
        jr z,.p1
        ld hl,0x9649                    ; player 2
        ld (0x96b3),hl
        call hk_input2
        jr .got
.p1:    ld (0x96b3),hl
        call hk_input1
.got:   ld d,a                          ; D = input bits
        ld a,(0x72a7)
        ld c,a
        ld b,0
        ld hl,hk_turn
        add hl,bc
        ld a,(hl)                       ; turn request of this player
        and 3
        ld hl,hk_tcnt
        add hl,bc
        jr nz,.turning
        ld (hl),a                       ; no turn key: repeat counter := 0
        jr .react
.turning:
        ld e,a                          ; E = 1 left / 2 right (both: left wins)
        ld a,(hl)
        or a
        jr z,.now                       ; key just pressed: turn at once
        inc (hl)
        ld a,(hl)
        cp HK_TURN_REPEAT+1
        jr c,.react                     ; still held: the next turn after HK_TURN_REPEAT polls; normal controls meanwhile
.now:   ld (hl),1
        ld a,(0x72a7)
        inc a
        ld l,a
        ld a,(0xfdea)
        or l
        ld (0xfdea),a                   ; view_redraw_mask |= player + 1: the view is rebuilt
        bit 0,e
        jr z,.right
        ld a,2
        ld (0xfff3),a                   ; view_turn_state = 2 (left)
        ld a,(0xfff1)
        dec a                           ; facing - 1
        jr .set
.right: ld a,1
        ld (0xfff3),a                   ; view_turn_state = 1 (right)
        ld a,(0xfff1)
        inc a                           ; facing + 1
.set:   and 3
        ld (0xfff1),a                   ; view_facing
        ret                             ; back to player_update (as the original turn routines)
.react: ld a,d
        bit 4,a
        jr z,.go                        ; fire not held: original reaction (moves; a charged shot goes off on release)
        bit 2,a
        jr nz,.go                       ; FIRE + DOWN: the special attack (original)
        ; fire held with or without directions: keep charging the shot (the original's fire latch) AND move (the original stood still)
        ld hl,(0x96b3)                  ; fire latch of this player
        ld a,(hl)
        inc a
        jr nz,.cap
        dec a                           ; saturate at FFh
.cap:   push hl
        push af
        ld (hl),0                       ; latch 0 during the move: the no-fire path must not fire the shot now
        ld a,d
        and 0x0b                        ; up / left / right (down is the special attack)
        call 0x96b2                     ; movement exactly as without fire (nothing pressed: returns at once)
        pop af
        pop hl
        ld (hl),a                       ; latch restored and counted: the shot goes off when fire is released
        ret
.go:    jp 0x96b2

; XYBOTS MSX1 + V9990 B1 ROM - stage B: copies the game image and the V9990 hook runtime from the ROM banks to RAM, runs the V9990
; boot hook and starts the game.
; Assembled at BOOT (C200h) by MSX/tools/build_rom.py, embedded in xybots_rom.asm and copied to RAM by stage A.
;
; Memory used (all inside C125h-EAFFh, which the original image never reads or writes: data-g.md):
;   C1F0h ROM_A  slot register with page 1 = cartridge     C1F1h RAM_A  slot register with all pages = RAM
;   C200h stage B code + chunk table                        C800h-E7FFh transfer buffer (8 KiB)   EAF0h stack
; Chunk table entry (7 bytes): dest.w, length.w (0 = end), bank.b, source.w (4000h-7FFFh window address).
ROM_A           equ 0xc1f0
RAM_A           equ 0xc1f1
BUF             equ 0xda00              ; 4 KiB transfer buffer DA00h-E9FFh (V9990 layout: layout.asm)
HK_SCENE_VARS   equ 0xe180              ; = hk_scene, hk_romsl, hk_ramsl, hk_ms_state (layout.asm, music.inc): the runtime switches the scenery banks (ADR-025)

        org 0xc200
stage_b:
        ld sp,0xeaf0                    ; stack EA00h-EAF0h (below the game frame buffer at EB00h)
        ld ix,chunk_table
copy_next:
        ld c,(ix+2)
        ld b,(ix+3)
        ld a,b
        or c
        jr z,copy_done          ; length 0 = end of table
        ld a,(ROM_A)
        out (0xa8),a            ; page 1 = cartridge
        ld a,(ix+4)
        ld (0x6000),a           ; ASCII16: bank for 4000h-7FFFh
        ld l,(ix+5)
        ld h,(ix+6)
        ld de,BUF
        ldir                    ; ROM -> buffer (BC = length; 0 afterwards)
        ld a,(RAM_A)
        out (0xa8),a            ; all four pages RAM again
        ld c,(ix+2)
        ld b,(ix+3)
        ld hl,BUF
        ld e,(ix+0)
        ld d,(ix+1)
        ldir                    ; buffer -> original address
        ld bc,7
        add ix,bc
        jr copy_next
copy_done:
; VRAM pieces (4 bpp atlases): ROM bank window -> V9990 port 60h directly. Entry (8 bytes): vram address lo.w, bits 18-16.b, length.w
; (0 = end of the table; then source.w = the next table, 0 = done), bank.b, source.w. The V9990 was reset by stage A (detect); VRAM writes need no display mode.
        ld a,6
        out (0x64),a
        ld a,0x82
        out (0x63),a            ; R#6 = B1 8 bpp (BP6 prototype) NOW: the CPU VRAM address mapping depends on the display mode (bitmap modes interleave
                                ; the two halves of the VRAM); the atlases must land where the B1 command engine and the display read them
        ld a,8
        out (0x64),a
        ld a,0x02
        out (0x63),a            ; R#8 = 02h: display off, VSL = 512 KiB VRAM. After the reset VSL = 0 (smaller VRAM map): a real V9990
                                ; then stores the atlases in the wrong places (openMSX ignores VSL); Sol Negro / Spy vs Spy set it the same way
        ld ix,vram_table
vram_next:
        ld c,(ix+3)
        ld b,(ix+4)
        ld a,b
        or c
        jr nz,vram_piece
        ld l,(ix+6)                     ; end of a table: (ix+6) = the next table (the scene store, hk_store_tab), 0 = done
        ld h,(ix+7)
        ld a,h
        or l
        jr z,vram_done
        push hl
        pop ix
        jr vram_next
vram_piece:
        xor a
        out (0x64),a            ; R#0..R#2 = write address
        ld a,(ix+0)
        out (0x63),a
        ld a,(ix+1)
        out (0x63),a
        ld a,(ix+2)
        out (0x63),a
        ld a,(ROM_A)
        out (0xa8),a            ; page 1 = cartridge
        ld a,(ix+5)
        ld (0x6000),a
        ld l,(ix+6)
        ld h,(ix+7)
vram_loop:
        ld a,(hl)
        out (0x60),a
        inc hl
        dec bc
        ld a,b
        or c
        jr nz,vram_loop
        ld bc,8
        add ix,bc
        jr vram_next
vram_done:
        ld a,(RAM_A)
        out (0xa8),a
        ld hl,(ROM_A)                   ; L = ROM_A, H = RAM_A: they die with the sprite table, the runtime keeps a copy
        ld (HK_SCENE_VARS+1),hl         ; hk_romsl, hk_ramsl
        xor a
        ld (HK_SCENE_VARS),a            ; hk_scene: scene A is in the main atlas (tiles.bin)
        ld (HK_SCENE_VARS+3),a          ; hk_ms_state: Moonsound not checked yet (music.inc)
        jp 0xc400               ; hook runtime entry +0: V9990 initialisation; it moves the sprite table over this code and jumps to 0300h

chunk_table:
        include "../../build/rom/chunks.inc"
        dw 0,0                  ; terminator
vram_table:
        include "../../build/rom/vram_chunks.inc"
        db 0,0,0
        dw 0                    ; end of this table (length 0) ...
        db 0
        dw HK_STORE_TAB         ; ... next: the scene store (hk_segs.asm, in the game image copied above; tools/hud4.py scene_store)
stage_b_end:
        assert stage_b_end <= 0xc400    ; must not reach the hook runtime at C400h

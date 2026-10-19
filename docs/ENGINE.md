# Cartridge and V9990 engine

The cartridge is a 2 MiB ASCII16 MegaROM with 128 banks. The ROM loader selects RAM, installs the original game's load image from the CAS and starts the patched program. The build keeps the tape bytes external and applies each patch only where the expected original bytes match.

The hook runtime in src/ replaces the original VDP drawing paths. It uploads atlases to V9990 VRAM, composes the two player viewports, draws text and sprites, and presents the panel through a split screen. The viewports use double buffering. The minimap keeps a clean copy of its window and redraws markers from that copy, so old marker pixels are removed when players or objects move.

Graphics use V9990 bitmap mode B1, eight bits per pixel and one shared 64-colour palette. The opening image uses a separate fixed-colour bitmap. Editable sheets and conversion rules are described in [ASSETS.md](ASSETS.md).

The original MSX sound path remains available. When a Moonsound is present, the music player uses OPL4 for the adapted arcade score and voices. With more than 128 KB of sample RAM, selected arcade sound effects are loaded too. The logo composition is stored in assets/music/; the external arcade recordings needed for a complete build are listed in [BUILDING.md](BUILDING.md).

Key files:

| Path | Role |
|---|---|
| src/rom/ | Boot loader, opening and OPL4 player |
| src/hk_runtime.asm and src/hk_*.asm | Hook runtime, viewport, HUD, sprites and input |
| src/layout.asm | RAM and VRAM layout, build options |
| tools/extract_tape_images.py | Read the original CAS |
| tools/build_b1.py | Patch and pack the cartridge |
| tools/assets4.py and tools/hud4.py | Convert art to VRAM atlases |

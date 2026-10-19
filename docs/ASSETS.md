# Editable assets

The 64-colour palette in assets/palette.json is shared by sprites, tiles, signs and HUD panels. PNG sheets are indexed; their used colours must agree with the palette. Pixel index 0 is transparent for sprites. Sprite sizes and positions are fixed by the original game's descriptor records, so paint inside the existing frames.

| Path | Content |
|---|---|
| assets/sprites/ | Actor frames, player 2 frames and their layout |
| assets/tiles/ | Corridor and Master Xybot tiles, wall panels, room map |
| assets/scenes/ | Four level scenes and their palette entries |
| assets/hud/ | Panel map, fonts, digits, icons and map markers |
| assets/ui/ and assets/shop/ | Signs and shop presentation |
| assets/views/ | Sample Tiled views for editing the tile art |
| assets/opening.png and assets/opening-b3.png | Opening art and fixed-colour bitmap preview |
| assets/dihalt_logo-b1.png | Logo art |
| assets/music/ | DiHalt logo composition and its editable sound data |

The normal build reads these sources and converts them into binary VRAM atlases under build/assets4/. It does not overwrite the editable files.

Run make palette-from-sprites or make palette-from-tiles after changing a sheet's palette. The converter copies its colours to the other sheets while retaining their pixel indices. Run make opening to regenerate the fixed-colour opening preview after editing assets/opening.png.

The arcade music, voices and effects are separate external inputs under original/audio/; see [BUILDING.md](BUILDING.md). They are not part of assets/.

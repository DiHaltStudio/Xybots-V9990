# Building Xybots for V9990

## Tools

| Tool | Purpose |
|---|---|
| GNU make | Build targets |
| Python 3 with Pillow and NumPy | Image and sound conversion |
| sjasm 0.42c | Z80 assembler; sjasmplus has different syntax |
| pdflatex | Rebuild the two PDF manuals |
| zip | Package the release files |
| openMSX with its V9990 extension | Play the cartridge |
| ffmpeg | Prepare arcade voice and effect recordings with make voices / make sfx |

The ROM is a 2 MiB ASCII16 MegaROM. The game needs 64 KB of RAM and a V9990 cartridge; Moonsound is optional.

## Original inputs

Put your own MSX tape at original/XYBOTS.CAS. The build expects the 1989 tape variant with SHA-256:

~~~text
ff8ba664d740b9061e018825f155bc5c983dccbc4d55df20c98cad6c0c391a86
~~~

The cartridge also uses arcade music, voices and effects. Supply exports from your own arcade game copy under original/audio/. The music files are VGZ recordings of the YM2151 output. The voice and effect files are WAV recordings prepared for Moonsound. The names below are exact; the build reports any missing file.

~~~text
original/
  XYBOTS.CAS
  audio/
    music/
      boss_arcade.vgz
      intro_arcade.vgz
      level1_arcade.vgz
      level_arcade.vgz
      shop_arcade.vgz
      start_coin_arcade.vgz
    voices/
      logo_voces_11k.wav
      intro_voz1_7k.wav  intro_voz2_7k.wav
      level_voz3_7k.wav  level_voz4_7k.wav
      level_voz5_7k.wav  level_voz6_7k.wav
      boss_voz_inicio_7k.wav  boss_voz_impacto_7k.wav
      boss_voz_impacto2_7k.wav  boss_voz_impacto3_7k.wav
      boss_voz_fin_7k.wav
    sfx/
      disparo_22k.wav  disparo_doble_22k.wav
      impacto_22k.wav  impacto_doble_22k.wav
      moneda_22k.wav   llave_22k.wav
      energia_22k.wav  salida_22k.wav
      teletransporte_22k.wav
~~~

If you have the raw WAV recordings, place them in the same voices/ and sfx/ folders without the _7k, _11k or _22k suffix. Run make voices and make sfx to prepare the files above. These targets use ffmpeg and NumPy. The repo does not contain the recordings or the music VGZ files.

To use another location, set CAS and XYBOTS_ARCADE_AUDIO when invoking make.

## Commands

~~~sh
make                 # extract the tape and build build/xybots.rom
make manual          # rebuild docs/manual/manual-en.pdf and manual-es.pdf
make release         # generate release/xybots.rom, both PDFs and a zip
make run             # play release/xybots.rom if present, else the local build
make run-moon        # add Moonsound
make run2            # connect joystick 2
make help            # list targets
make clean           # remove build/
~~~

Make run uses a downloaded release ROM without the original files. Make, make release and a local build need the original inputs.

The build first validates the tape variant and checks the audio names. It extracts the loader and game image from the CAS, builds the art atlases from assets/, traces the original instructions, applies the V9990 patches, assembles the runtime with sjasm and packs 128 ASCII16 banks. The patches check the original bytes they replace; a different tape image stops the build.

Build outputs stay under build/. The original/ folder and generated ROM or zip files are ignored by Git. The manual PDF files under docs/manual/ are part of this repository.

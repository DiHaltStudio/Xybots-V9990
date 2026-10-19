# Xybots for MSX1 + V9990. See docs/BUILDING.md for the original inputs.
PYTHON  ?= python3
OPENMSX ?= openmsx
MACHINE ?= Sony_HB-10P
CAS     ?= original/XYBOTS.CAS
XYBOTS_ARCADE_AUDIO ?= original/audio
export XYBOTS_ARCADE_AUDIO
ROM := build/xybots.rom
RELEASE_ROM := release/xybots.rom
VERSION ?= 1.0
MANUAL_LANGS ?= en es
PLAY_ROM = $(firstword $(wildcard $(RELEASE_ROM)) $(wildcard $(ROM)))
EMU = $(OPENMSX) -machine $(MACHINE) -ext gfx9000

.DEFAULT_GOAL := rom
.PHONY: all rom inputs help run run-moon run2 run2-moon manual release clean opening palette-from-sprites palette-from-tiles voices sfx

all: rom

inputs:
	$(PYTHON) tools/check_inputs.py "$(CAS)" "$(XYBOTS_ARCADE_AUDIO)"

rom: inputs
	$(PYTHON) tools/extract_tape_images.py "$(CAS)" build/images
	$(PYTHON) tools/build_b1.py

manual:
	$(PYTHON) tools/manual_images.py docs/manual .
	cd docs/manual && for l in $(MANUAL_LANGS); do \
	  for i in 1 2; do pdflatex -interaction=nonstopmode -jobname=manual-$$l "\def\manlang{$$l}\input{manual}" >/dev/null || exit 1; done; done

release: rom manual
	mkdir -p release
	cp $(ROM) $(RELEASE_ROM)
	cp docs/manual/manual-en.pdf docs/manual/manual-es.pdf release/
	cd release && zip -q -j "xybots-v9990-$(VERSION).zip" xybots.rom manual-en.pdf manual-es.pdf

# Run the downloaded release ROM if present. Build only when neither ROM exists.
define play
	@rom="$(PLAY_ROM)"; \
	if [ -z "$$rom" ]; then $(MAKE) --no-print-directory rom || exit $$?; rom="$(ROM)"; fi; \
	$(EMU) $(1) -cart "$$rom" -romtype ASCII16 -script $(2)
endef

run:
	$(call play,,tools/run.tcl)

run-moon:
	$(call play,-ext moonsound,tools/run.tcl)

run2:
	$(call play,,tools/run2.tcl)

run2-moon:
	$(call play,-ext moonsound,tools/run2.tcl)

opening:
	$(PYTHON) tools/build_opening.py convert

palette-from-sprites:
	$(PYTHON) tools/palette_sync.py assets/sprites/sprites.png

palette-from-tiles:
	$(PYTHON) tools/palette_sync.py assets/tiles/tiles_main.png

DRIVE ?= 1.5
voices:
	@for v in intro_voz1 intro_voz2 level_voz3 level_voz4 level_voz5 level_voz6 boss_voz_inicio boss_voz_impacto boss_voz_impacto2 boss_voz_impacto3 boss_voz_fin; do \
	  $(PYTHON) tools/voice_prep.py "$(XYBOTS_ARCADE_AUDIO)/voices/$$v.wav" "$(XYBOTS_ARCADE_AUDIO)/voices/$$v"_7k.wav --rate 7350 --drive $(DRIVE) || exit $$?; done
	$(PYTHON) tools/voice_prep.py "$(XYBOTS_ARCADE_AUDIO)/voices/logo_voces.wav" "$(XYBOTS_ARCADE_AUDIO)/voices/logo_voces_11k.wav" --rate 11025 --drive $(DRIVE)

SFX = disparo:1.15 disparo_doble:0.80 impacto:0.50 impacto_doble:0.50 moneda:0.65 llave:2.00 energia:0 salida:2.65 teletransporte:1.20
sfx:
	@for e in $(SFX); do n=$$(printf '%s' "$$e" | cut -d: -f1); t=$$(printf '%s' "$$e" | cut -d: -f2); \
	  if [ "$$t" = 0 ]; then o=""; else o="--trim 0:$$t --fade 0.1"; fi; \
	  $(PYTHON) tools/voice_prep.py "$(XYBOTS_ARCADE_AUDIO)/sfx/$$n.wav" "$(XYBOTS_ARCADE_AUDIO)/sfx/$$n"_22k.wav --rate 22050 --peak 0.21 --drive $(DRIVE) $$o || exit $$?; done

clean:
	rm -rf build

help:
	@echo 'make                build build/xybots.rom from the external original inputs'
	@echo 'make run            play the release ROM, or the locally built ROM'
	@echo 'make run-moon       play with optional Moonsound audio'
	@echo 'make run2           connect the second joystick'
	@echo 'make run2-moon      second joystick and Moonsound'
	@echo 'make manual         rebuild the English and Spanish PDF manuals'
	@echo 'make voices/sfx     prepare external arcade audio recordings'
	@echo 'make release        collect ROM and manuals in release/ with a zip'
	@echo 'make clean          remove generated build files'

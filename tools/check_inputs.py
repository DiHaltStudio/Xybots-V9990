#!/usr/bin/env python3
"""Check the external original-game inputs used by the ROM build."""
import argparse
import hashlib
from pathlib import Path

CAS_SHA256 = "ff8ba664d740b9061e018825f155bc5c983dccbc4d55df20c98cad6c0c391a86"
MUSIC = (
    "boss_arcade.vgz", "intro_arcade.vgz", "level1_arcade.vgz",
    "level_arcade.vgz", "shop_arcade.vgz", "start_coin_arcade.vgz",
)
SFX = tuple(f"{name}_22k.wav" for name in (
    "disparo", "disparo_doble", "impacto", "impacto_doble", "moneda",
    "llave", "energia", "salida", "teletransporte",
))
VOICES = ("logo_voces_11k.wav",) + tuple(f"{name}_7k.wav" for name in (
    "intro_voz1", "intro_voz2", "level_voz3", "level_voz4",
    "level_voz5", "level_voz6", "boss_voz_inicio", "boss_voz_impacto",
    "boss_voz_impacto2", "boss_voz_impacto3", "boss_voz_fin",
))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cas", type=Path)
    ap.add_argument("audio", type=Path)
    args = ap.parse_args()
    if not args.cas.is_file():
        ap.error(f"missing {args.cas}; see docs/BUILDING.md")
    digest = hashlib.sha256(args.cas.read_bytes()).hexdigest()
    if digest != CAS_SHA256:
        ap.error(f"{args.cas}: wrong XYBOTS.CAS variant (SHA-256 {digest})")
    missing = [
        str(args.audio / group / name)
        for group, names in (("music", MUSIC), ("sfx", SFX), ("voices", VOICES))
        for name in names if not (args.audio / group / name).is_file()
    ]
    if missing:
        ap.error("missing external arcade audio:\n  " + "\n  ".join(missing) +
                 "\nSee docs/BUILDING.md")
    print("Original CAS and arcade audio inputs found")


if __name__ == "__main__":
    main()

"""
Bank / program map for the bundled SoundFont (Round 2 Phase D2).

The bundled `assets/soundfonts/combined.sf2` merges three banks:

  * Bank 0  — General MIDI (FluidR3_GM fallback)
  * Bank 1  — DSK Asian DreamZ (Chinese traditional instruments)
  * Bank 2  — VSCO 2 Community Edition (Western orchestra)

This module maps instrument names → (bank, program) so the MIDI
writer can emit bank-select CC0/CC32 messages before program-change
and pick the right sample set. When the bundled SF2 isn't in use,
the map returns (0, gm_program) so downstream is still correct with
a plain GM SoundFont.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# Instrument name → (bank, program) for the bundled SF2
# --------------------------------------------------------------------------

# Bank 1 (Asian DreamZ) program numbers are the SF2 authors' own
# programming, not GM. These are well-known patch slots.
_BUNDLED_MAP: dict[str, tuple[int, int]] = {
    # Chinese traditional — Bank 1
    "erhu":         (1, 5),
    "dizi":         (1, 12),
    "xiao":         (1, 13),
    "pipa":         (1, 20),
    "guzheng":      (1, 22),
    "yangqin":      (1, 24),
    "suona":        (1, 30),
    "ruan":         (1, 26),

    # Western orchestra — Bank 2
    "violin":       (2, 40),
    "viola":        (2, 41),
    "cello":        (2, 42),
    "contrabass":   (2, 43),
    "strings":      (2, 48),
    "pad":          (2, 89),
    "flute":        (2, 73),
    "piano":        (2, 0),
    "grand piano":  (2, 0),

    # Guitars / bass — Bank 0 GM (no bespoke Western samples needed)
    "acoustic guitar":  (0, 24),
    "nylon guitar":     (0, 24),
    "electric guitar":  (0, 27),
    "bass":             (0, 33),
    "electric bass":    (0, 33),
    "bass guitar":      (0, 33),

    # Drums — Bank 128 per GM2 convention for drum kits.
    "drums":       (128, 0),
    "drum kit":    (128, 0),
    "percussion":  (128, 0),
}


# --------------------------------------------------------------------------
# Lookup
# --------------------------------------------------------------------------

def resolve_bank_program(
    instrument_name: str,
    gm_program: int = 0,
    use_bundled: bool = True,
) -> tuple[int, int]:
    """Return (bank, program) for this instrument.

    Args:
        instrument_name: free-form name (case-insensitive).
        gm_program: the caller's previously-chosen GM program; used as
            the fallback when the name doesn't match any bundled slot.
        use_bundled: False → always return (0, gm_program) — safe for
            plain GM SoundFonts.

    Returns:
        (bank, program) tuple. Bank 128 is the GM-drum-kit convention.
    """
    if not use_bundled:
        return (0, gm_program)

    key = (instrument_name or "").strip().lower()

    # Exact match first.
    if key in _BUNDLED_MAP:
        return _BUNDLED_MAP[key]

    # Substring fallbacks so "Chinese Dizi" still matches "dizi".
    for name, slot in _BUNDLED_MAP.items():
        if name in key:
            return slot

    return (0, gm_program)


def bundled_instrument_names() -> list[str]:
    return sorted(_BUNDLED_MAP.keys())


__all__ = [
    "resolve_bank_program",
    "bundled_instrument_names",
]

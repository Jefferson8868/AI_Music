"""
Ornament macro registry.

High-level musical intent vocabulary the Composer/Instrumentalist LLMs use
instead of raw MIDI CC numbers. Each macro is expanded into concrete
PitchBendEvents / CCEvents / note retriggers by the performance renderer
(src/music/performance.py).

No MIDI logic here — this module is pure vocabulary + parsing.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class OrnamentSpec(BaseModel):
    name: str
    description: str  # 1-line, shown to the LLM
    takes_arg: bool = False
    arg_range: tuple[int, int] | None = None
    arg_default: int | None = None
    renders_to: list[str] = Field(default_factory=list)
    # Families: "pitch_bend", "cc1_lfo", "cc2_env", "cc11_env",
    # "retrigger", "insert_note", "duration_adjust", "velocity_adjust"


def _spec(
    name: str,
    description: str,
    renders_to: list[str],
    takes_arg: bool = False,
    arg_range: tuple[int, int] | None = None,
    arg_default: int | None = None,
) -> OrnamentSpec:
    return OrnamentSpec(
        name=name,
        description=description,
        takes_arg=takes_arg,
        arg_range=arg_range,
        arg_default=arg_default,
        renders_to=renders_to,
    )


ORNAMENT_MACROS: dict[str, OrnamentSpec] = {
    # --- Breath / air ---
    "breath_swell": _spec(
        "breath_swell",
        "Gentle breath + expression rise into the note (0.25-0.5 beats).",
        ["cc2_env", "cc11_env"],
    ),
    "breath_fade": _spec(
        "breath_fade",
        "Breath + expression fade out at the end of the note.",
        ["cc2_env", "cc11_env"],
    ),
    "flutter": _spec(
        "flutter",
        "Flutter tongue: rapid CC1 oscillation + 16th-note retriggers. Dizi/flute.",
        ["cc1_lfo", "retrigger"],
    ),
    "overblow": _spec(
        "overblow",
        "Brief pitch-sharp jolt with velocity bump (aggressive Dizi attack).",
        ["pitch_bend", "velocity_adjust"],
    ),

    # --- Pitch shaping ---
    "slide_up_from": _spec(
        "slide_up_from",
        "Portamento from a lower pitch into this note. arg=semitones (1-5).",
        ["pitch_bend"],
        takes_arg=True,
        arg_range=(1, 5),
        arg_default=2,
    ),
    "slide_down_from": _spec(
        "slide_down_from",
        "Portamento from a higher pitch into this note. arg=semitones (1-5).",
        ["pitch_bend"],
        takes_arg=True,
        arg_range=(1, 5),
        arg_default=2,
    ),
    "slide_up_to": _spec(
        "slide_up_to",
        "Bend up over the note's duration. arg=semitones (1-5).",
        ["pitch_bend"],
        takes_arg=True,
        arg_range=(1, 5),
        arg_default=2,
    ),
    "slide_down_to": _spec(
        "slide_down_to",
        "Bend down over the note's duration. arg=semitones (1-5).",
        ["pitch_bend"],
        takes_arg=True,
        arg_range=(1, 5),
        arg_default=2,
    ),
    "bend_dip": _spec(
        "bend_dip",
        "Down-up pitch dip in the middle of the note (vocal-like 哭腔).",
        ["pitch_bend"],
    ),

    # --- Vibrato variants ---
    "vibrato_light": _spec(
        "vibrato_light",
        "Gentle CC1 LFO, depth 20, ~5 Hz.",
        ["cc1_lfo"],
    ),
    "vibrato_deep": _spec(
        "vibrato_deep",
        "Deep CC1 LFO, depth 60, ~6 Hz (Erhu 揉弦, emotional).",
        ["cc1_lfo"],
    ),
    "vibrato_delayed": _spec(
        "vibrato_delayed",
        "Vibrato starts halfway through the note.",
        ["cc1_lfo"],
    ),

    # --- Articulation styling ---
    "staccato": _spec(
        "staccato",
        "Shorten the note to ~50% of written duration.",
        ["duration_adjust"],
    ),
    "tenuto": _spec(
        "tenuto",
        "Hold the note full duration with a slight velocity bump.",
        ["duration_adjust", "velocity_adjust"],
    ),
    "legato_to_next": _spec(
        "legato_to_next",
        "Eliminate gap with the next note; slight overlap for smooth phrasing.",
        ["duration_adjust"],
    ),

    # --- Strings / plucks ---
    "tremolo_rapid": _spec(
        "tremolo_rapid",
        "True note retrigger at 16th-note rate (Pipa 轮指, Yangqin).",
        ["retrigger"],
    ),
    "grace_note_above": _spec(
        "grace_note_above",
        "Insert a 1/16 grace note 1 step above before this note.",
        ["insert_note"],
    ),
    "grace_note_below": _spec(
        "grace_note_below",
        "Insert a 1/16 grace note 1 step below before this note.",
        ["insert_note"],
    ),
    "glissando_from": _spec(
        "glissando_from",
        "Arpeggiated sweep of 3-5 notes into this note (Guzheng 刮奏).",
        ["insert_note"],
    ),
    "glissando_to": _spec(
        "glissando_to",
        "Arpeggiated sweep of 3-5 notes out of this note.",
        ["insert_note"],
    ),
}


def parse_ornament(token: str) -> tuple[str, int | None]:
    """Split "slide_up_from:3" -> ("slide_up_from", 3). "vibrato_deep" -> (..., None)."""
    if ":" not in token:
        return token, None
    name, _, arg = token.partition(":")
    try:
        return name, int(arg)
    except ValueError:
        return name, None


def ornament_is_known(token: str) -> bool:
    name, _ = parse_ornament(token)
    return name in ORNAMENT_MACROS


def ornament_vocabulary_summary() -> str:
    """Compact 1-line-per-ornament listing for prompt injection."""
    lines = []
    for name, spec in ORNAMENT_MACROS.items():
        suffix = ""
        if spec.takes_arg and spec.arg_range is not None:
            lo, hi = spec.arg_range
            suffix = f" (arg={lo}-{hi})"
        lines.append(f"  - {name}{suffix}: {spec.description}")
    return "\n".join(lines)

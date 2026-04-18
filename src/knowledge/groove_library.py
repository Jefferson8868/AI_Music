"""
Groove template library — Round 2 Phase B1.

A curated set of 11 drum templates covering the section×genre matrix
that actually shows up in modern Chinese-pop / fusion arrangements.

Each template encodes:
  * The 16th-note grid pattern per drum voice (kick / snare / closed
    hat / open hat / ride / perc).
  * A swing percentage (50 = straight, >50 = shuffle feel).
  * Per-voice micro-timing offsets in milliseconds (the humanizer in
    Phase C layers additional jitter ON TOP of these).
  * Tempo / section-role fit hints so the pipeline can pick a
    sensible template automatically.

The templates are intentionally hand-written — not learned. Real
drummers carry a personal "library" of grooves they reach for; this
file is that library for our system.

Velocity convention in the 16th-grid arrays
-------------------------------------------
  0.0 = silent
  0.25-0.5 = ghost note
  0.6-0.75 = normal hit (hats, rides)
  0.85-1.0 = accent (kick on one, snare on 2/4)

The DrumAgent (Phase B2) maps these to MIDI velocity by:
  velocity = 30 + 90 * grid_value   (→ 30..120 range)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

SectionRole = Literal[
    "intro", "verse", "pre_chorus", "chorus", "bridge", "outro",
]

DrumVoice = Literal[
    "kick", "snare", "chh", "ohh", "ride", "crash", "perc",
]


@dataclass(frozen=True)
class GrooveTemplate:
    """One hand-curated groove. Immutable so multiple sections can
    safely share a reference to the same template."""

    name: str
    tempo_range: tuple[int, int]
    fits: list[SectionRole]
    swing_pct: int = 50               # 50=straight, 58-63=shuffle
    pattern: dict[DrumVoice, list[float]] = field(default_factory=dict)
    # Per-voice offsets in milliseconds applied by the humanizer
    # (snare lays back, hats push early, kick on grid, etc.).
    microtiming: dict[DrumVoice, int] = field(default_factory=dict)
    # Per-section-role "fit score" modifier. A pos value boosts the
    # template for that role; a neg value penalises it.
    role_bonus: dict[SectionRole, float] = field(default_factory=dict)
    # Free-form notes (what this groove is for / why this exists).
    notes: str = ""

    def beats(self) -> int:
        """Number of 16th cells in one loop; usually 16 (1 bar 4/4)."""
        if not self.pattern:
            return 16
        return max(len(v) for v in self.pattern.values())


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

# Shared 16th-cell patterns for reuse. A filler cell of 0.0 is silence.
_CHH_STRAIGHT_8THS = [0.7, 0.0, 0.7, 0.0, 0.7, 0.0, 0.7, 0.0,
                      0.7, 0.0, 0.7, 0.0, 0.7, 0.0, 0.7, 0.0]
_CHH_16THS = [0.7, 0.5, 0.7, 0.5, 0.7, 0.5, 0.7, 0.5,
              0.7, 0.5, 0.7, 0.5, 0.7, 0.5, 0.7, 0.5]
_KICK_BASIC_POP = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                   0.9, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
_SNARE_BACKBEAT = [0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0,
                   0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]


BALLAD_75 = GrooveTemplate(
    name="ballad_75bpm",
    tempo_range=(65, 85),
    fits=["intro", "verse", "bridge", "outro"],
    swing_pct=50,
    pattern={
        "kick": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                 0.8, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "snare": [0.0, 0.0, 0.0, 0.0, 0.8, 0.0, 0.0, 0.0,
                  0.0, 0.0, 0.0, 0.0, 0.8, 0.0, 0.0, 0.0],
        "chh": _CHH_STRAIGHT_8THS,
    },
    microtiming={"snare": +6, "chh": -2, "kick": 0},
    role_bonus={"verse": 0.3, "bridge": 0.25, "outro": 0.2},
    notes="Minimal ballad. Snare lays back 6ms for emotional weight.",
)


HALFTIME_BALLAD = GrooveTemplate(
    name="halftime_ballad",
    tempo_range=(80, 110),
    fits=["verse", "pre_chorus", "bridge"],
    swing_pct=50,
    pattern={
        "kick": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "snare": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                  1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "chh": _CHH_STRAIGHT_8THS,
    },
    microtiming={"snare": +10, "chh": -3, "kick": 0},
    role_bonus={"verse": 0.3, "bridge": 0.2},
    notes="Halftime — snare on beat 3 only. Huge lay-back. Verses.",
)


MODERN_POP_100 = GrooveTemplate(
    name="modern_pop_100",
    tempo_range=(92, 112),
    fits=["verse", "pre_chorus", "chorus"],
    swing_pct=54,
    pattern={
        "kick": _KICK_BASIC_POP,
        "snare": _SNARE_BACKBEAT,
        "chh": _CHH_16THS,
    },
    microtiming={"snare": +8, "chh": -4, "kick": 0},
    role_bonus={"verse": 0.2, "pre_chorus": 0.2, "chorus": 0.25},
    notes="Straight 16th-note hats. Backbone of modern pop.",
)


C_POP_VERSE_STANDARD = GrooveTemplate(
    name="c_pop_verse_standard",
    tempo_range=(85, 105),
    fits=["verse", "pre_chorus"],
    swing_pct=52,
    pattern={
        "kick": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5, 0.0,
                 0.9, 0.0, 0.0, 0.25, 0.0, 0.0, 0.0, 0.0],
        "snare": _SNARE_BACKBEAT,
        "chh": _CHH_16THS,
    },
    microtiming={"snare": +7, "chh": -3, "kick": 0},
    role_bonus={"verse": 0.4, "pre_chorus": 0.2},
    notes="C-pop verse w/ kick accents on syncopated 16ths.",
)


C_POP_CHORUS_STANDARD = GrooveTemplate(
    name="c_pop_chorus_standard",
    tempo_range=(88, 108),
    fits=["chorus"],
    swing_pct=58,
    pattern={
        "kick": [1.0, 0.0, 0.0, 0.0, 0.5, 0.0, 0.0, 0.0,
                 1.0, 0.0, 0.0, 0.25, 0.0, 0.0, 0.0, 0.0],
        "snare": _SNARE_BACKBEAT,
        "chh": _CHH_16THS,
        "crash": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                  0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    },
    microtiming={"snare": +8, "chh": -3, "kick": 0, "crash": 0},
    role_bonus={"chorus": 0.5},
    notes="Crash on the one. Dense hats. Canonical C-pop chorus.",
)


DEMBOW_95 = GrooveTemplate(
    name="dembow_95",
    tempo_range=(88, 102),
    fits=["verse", "chorus", "bridge"],
    swing_pct=50,
    pattern={
        "kick": [1.0, 0.0, 0.0, 0.8, 0.0, 0.0, 1.0, 0.0,
                 1.0, 0.0, 0.0, 0.8, 0.0, 0.0, 1.0, 0.0],
        "snare": [0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0,
                  0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
        "perc": [0.0, 0.5, 0.0, 0.5, 0.0, 0.5, 0.0, 0.5,
                 0.0, 0.5, 0.0, 0.5, 0.0, 0.5, 0.0, 0.5],
    },
    microtiming={"snare": +4, "kick": 0, "perc": -2},
    role_bonus={"chorus": 0.2, "bridge": 0.15},
    notes="Latin-tinged dembow for pop crossover grooves.",
)


TRAP_140 = GrooveTemplate(
    name="trap_140",
    tempo_range=(130, 150),
    fits=["verse", "pre_chorus", "chorus"],
    swing_pct=50,
    pattern={
        "kick": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.9, 0.0,
                 0.0, 0.0, 0.8, 0.0, 0.0, 0.0, 0.0, 0.0],
        "snare": [0.0, 0.0, 0.0, 0.0, 0.9, 0.0, 0.0, 0.0,
                  0.0, 0.0, 0.0, 0.0, 0.9, 0.0, 0.0, 0.0],
        # Trap hats: 16ths with periodic 32nd rolls.
        "chh": [0.7, 0.7, 0.7, 0.3, 0.7, 0.7, 0.7, 0.3,
                0.7, 0.7, 0.7, 0.7, 0.7, 0.5, 0.5, 0.5],
    },
    microtiming={"snare": +2, "chh": -1, "kick": 0},
    role_bonus={"verse": 0.2, "chorus": 0.2},
    notes="Trap flavour — 808 kick + sparse snare + hat rolls.",
)


GUZHENG_BALLAD_PERC = GrooveTemplate(
    name="guzheng_ballad_perc",
    tempo_range=(70, 92),
    fits=["intro", "verse", "outro"],
    swing_pct=50,
    pattern={
        # Traditional: frame drum + shaker replace kit, soft dynamics.
        "perc": [0.4, 0.0, 0.2, 0.0, 0.6, 0.0, 0.2, 0.0,
                 0.4, 0.0, 0.2, 0.0, 0.6, 0.0, 0.2, 0.0],
    },
    microtiming={"perc": 0},
    role_bonus={"intro": 0.3, "verse": 0.2, "outro": 0.2},
    notes="Sparse traditional-percussion feel. No drum kit.",
)


ROCK_128 = GrooveTemplate(
    name="rock_128",
    tempo_range=(118, 138),
    fits=["verse", "pre_chorus", "chorus", "bridge"],
    swing_pct=50,
    pattern={
        "kick": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5, 0.0,
                 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "snare": _SNARE_BACKBEAT,
        "chh": _CHH_16THS,
        "crash": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                  0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    },
    microtiming={"snare": +6, "chh": -3, "kick": 0, "crash": 0},
    role_bonus={"chorus": 0.3, "bridge": 0.2},
    notes="Rock 4-on-floor feel. Use for heavier choruses.",
)


INTRO_AMBIENT = GrooveTemplate(
    name="intro_ambient",
    tempo_range=(60, 120),
    fits=["intro", "outro"],
    swing_pct=50,
    pattern={
        # One soft kick per bar. Just barely there.
        "kick": [0.35, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    },
    microtiming={"kick": 0},
    role_bonus={"intro": 0.4, "outro": 0.3},
    notes="Minimal pulse — almost no drums. Intro/outro ambience.",
)


BRIDGE_HALFSTEP = GrooveTemplate(
    name="bridge_halfstep",
    tempo_range=(78, 105),
    fits=["bridge"],
    swing_pct=56,
    pattern={
        "kick": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "snare": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                  0.8, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "ride": [0.6, 0.0, 0.6, 0.0, 0.6, 0.0, 0.6, 0.0,
                 0.6, 0.0, 0.6, 0.0, 0.6, 0.0, 0.6, 0.0],
    },
    microtiming={"snare": +12, "ride": -2, "kick": 0},
    role_bonus={"bridge": 0.5},
    notes="Half-step feel on ride. Canonical 'pull back' bridge groove.",
)


ALL_TEMPLATES: list[GrooveTemplate] = [
    BALLAD_75,
    HALFTIME_BALLAD,
    MODERN_POP_100,
    C_POP_VERSE_STANDARD,
    C_POP_CHORUS_STANDARD,
    DEMBOW_95,
    TRAP_140,
    GUZHENG_BALLAD_PERC,
    ROCK_128,
    INTRO_AMBIENT,
    BRIDGE_HALFSTEP,
]


def select_template(
    section_role: SectionRole,
    tempo_bpm: float,
    genre_hint: str = "",
) -> GrooveTemplate:
    """Pick the best-fit template for (section, tempo, genre).

    Scoring is simple and deterministic:
      * +0.4 if section_role ∈ template.fits
      * +template.role_bonus.get(section_role, 0.0)
      * -0.4 if tempo is outside template.tempo_range
      * +0.2 if genre keywords match template notes (case-insensitive)

    Returns the highest-scoring template. Always returns a template —
    falls back to MODERN_POP_100 as a safe default if every candidate
    scores zero.
    """
    genre_l = (genre_hint or "").lower()
    best: GrooveTemplate | None = None
    best_score = float("-inf")
    for t in ALL_TEMPLATES:
        score = 0.0
        if section_role in t.fits:
            score += 0.4
        score += t.role_bonus.get(section_role, 0.0)
        lo, hi = t.tempo_range
        if tempo_bpm < lo or tempo_bpm > hi:
            score -= 0.4
        if genre_l and genre_l in t.notes.lower():
            score += 0.2
        if score > best_score:
            best_score = score
            best = t
    return best or MODERN_POP_100


def template_by_name(name: str) -> GrooveTemplate | None:
    """Look up a template by its name (or None if unknown)."""
    for t in ALL_TEMPLATES:
        if t.name == name:
            return t
    return None

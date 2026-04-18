"""
TransitionAgent — Round 2 Phase B4.

Scans the completed Score for section boundaries and plans one
'ear-candy' recipe per boundary. Runs ONCE between Phase 3 (score
refinement) and Phase 4 (performance render), so it sees final note
positions but emits events BEFORE humanization.

Recipe table (from the approved plan)
-------------------------------------
| boundary                 | recipe                                   |
|--------------------------|-------------------------------------------|
| intro → verse            | soft piano tail + low riser              |
| verse → pre_chorus       | snare roll accel 1 bar + short rev cym   |
| pre_chorus → chorus      | full riser + rev cym + impact + sub drop |
| chorus → bridge          | filter sweep downlifter + kick drop      |
| bridge → outro           | (vocal ad-lib tail) + soft impact        |
| * → * (generic)          | single impact on the downbeat            |

MIDI-ish events (snare_roll, kick_drop, crash) are materialized by
the MIDI writer immediately; sample-ish events (riser, reverse_cymbal,
impact, sub_drop, downlifter) are placeholders the Phase F mix bus
picks up from the assets/transitions/ stem library.
"""

from __future__ import annotations

from loguru import logger

from src.music.score import Score, TransitionEvent


# --------------------------------------------------------------------
# Recipe table (boundary key → list of event specs)
# --------------------------------------------------------------------

# Each spec: (kind, lead_beats_before_target, params_dict)
# lead_beats_before_target: how far BEFORE the boundary the event fires.
# Positive means earlier (e.g. 4 beats = 1 bar before the chorus).
_BOUNDARY_RECIPES: dict[tuple[str, str], list[tuple[str, float, dict]]] = {
    ("intro", "verse"): [
        ("riser", 2.0, {"intensity": 0.35, "shape": "low"}),
    ],
    ("verse", "pre_chorus"): [
        ("snare_roll", 4.0, {"accel": True, "bars": 1, "target_vel": 110}),
        ("reverse_cymbal", 2.0, {"variant": "short"}),
    ],
    ("pre_chorus", "chorus"): [
        ("riser", 4.0, {"intensity": 0.8, "shape": "full"}),
        ("reverse_cymbal", 2.0, {"variant": "long"}),
        ("impact", 0.0, {"depth": "crisp"}),  # ON THE ONE
        ("sub_drop", 0.0, {"depth": "deep"}),
    ],
    ("chorus", "bridge"): [
        ("downlifter", 2.0, {"variant": "filter_sweep"}),
        ("kick_drop", 0.5, {"duration_beats": 1.0}),
    ],
    ("bridge", "outro"): [
        ("impact", 0.0, {"depth": "soft"}),
    ],
    ("chorus", "outro"): [
        ("impact", 0.0, {"depth": "crisp"}),
        ("downlifter", 2.0, {"variant": "filter_sweep"}),
    ],
    # Common "continuing" boundaries (e.g. chorus → chorus repeat)
    # get only a crash accent.
    ("chorus", "chorus"): [
        ("crash", 0.0, {"voice": "crash"}),
    ],
}


# A generic fallback for any boundary not in the recipe table.
_GENERIC_BOUNDARY_RECIPE: list[tuple[str, float, dict]] = [
    ("impact", 0.0, {"depth": "crisp"}),
]


class TransitionAgent:
    """Section-boundary ear-candy planner. No LLM."""

    def __init__(self) -> None:
        self._last_boundary_count = 0

    def plan_transitions(self, score: Score) -> list[TransitionEvent]:
        """Walk `score.sections` in order and emit one event per recipe
        entry for each (section, next_section) boundary.

        Idempotent: if `score.transition_events` is already non-empty,
        returns the existing list (caller can opt to replace by
        clearing it first).
        """
        if score.transition_events:
            logger.info(
                f"[TransitionAgent] Score already has "
                f"{len(score.transition_events)} transition events; "
                "skipping (caller must clear to re-plan)."
            )
            return list(score.transition_events)

        out: list[TransitionEvent] = []
        sections = score.sections
        if len(sections) < 2:
            return out

        bpb = score.time_signature[0] if score.time_signature else 4

        for i in range(len(sections) - 1):
            cur = sections[i]
            nxt = sections[i + 1]
            # Boundary beat = end of cur = start of next.
            boundary_beat = cur.start_beat + cur.bars * bpb
            recipe = _BOUNDARY_RECIPES.get(
                (cur.name.lower(), nxt.name.lower()),
                _GENERIC_BOUNDARY_RECIPE,
            )
            for kind, lead_beats, params in recipe:
                event = TransitionEvent(
                    beat=round(max(0.0, boundary_beat - lead_beats), 4),
                    kind=kind,
                    target_section=nxt.name,
                    params={**params, "from_section": cur.name},
                )
                out.append(event)

        self._last_boundary_count = len(sections) - 1
        logger.info(
            f"[TransitionAgent] Planned {len(out)} transition events "
            f"across {self._last_boundary_count} boundaries."
        )
        return out

    def attach(self, score: Score) -> Score:
        """Mutating convenience: attach planned events to the Score."""
        score.transition_events = self.plan_transitions(score)
        return score


# --------------------------------------------------------------------
# Helpers for the MIDI writer (Phase D) to realise MIDI-ish events
# --------------------------------------------------------------------

MIDI_REALIZABLE_KINDS = {
    "snare_roll", "kick_drop", "crash",
}

SAMPLE_REALIZABLE_KINDS = {
    "riser", "reverse_cymbal", "impact", "sub_drop", "downlifter",
}


def is_midi_kind(kind: str) -> bool:
    return kind in MIDI_REALIZABLE_KINDS


def is_sample_kind(kind: str) -> bool:
    return kind in SAMPLE_REALIZABLE_KINDS

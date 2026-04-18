"""
Neighbor-section context + main-hook helpers (Bug E).

Context: the previous session's ``_previous_section_summary`` only
handed the Composer the LAST note of each track ("melody: last pitch=67,
beat=15.75"). That's enough to avoid jumping an octave, but not enough
to write a verse that sounds like it FOLLOWS the previous section
musically. Output felt stitched-together rather than composed.

This module adds two levers:

1. **Section tail** — the LAST ~8 beats of every track in the previous
   section, rendered compactly. The Composer now sees a real phrase to
   continue from instead of just the final pitch.

2. **Main hook** — a short shared motif (3-8 notes) planned in Phase 1
   and quoted (or referenced) in every verse + chorus. Gives the piece
   motivic unity across sections.

Both helpers are pure functions over dicts / pydantic objects so they
can be unit-tested without the AutoGen / LLM stack.
"""

from __future__ import annotations

from src.music.score import ScoreNote


DEFAULT_TAIL_BEATS = 8.0

# Sections where the composer should quote or reference the main hook.
# Other sections (intro, outro, bridge) can treat it as background.
HOOK_SECTIONS: frozenset[str] = frozenset({"verse", "chorus", "pre_chorus"})


# ---------------------------------------------------------------------------
# Section-tail extraction
# ---------------------------------------------------------------------------

def _pitch_name(midi: int) -> str:
    names = [
        "C", "C#", "D", "D#", "E", "F",
        "F#", "G", "G#", "A", "A#", "B",
    ]
    return f"{names[midi % 12]}{midi // 12 - 1}"


def extract_section_tail(
    all_tracks: dict[str, list[dict]],
    last_section: dict | None,
    tail_beats: float = DEFAULT_TAIL_BEATS,
) -> dict[str, list[dict]]:
    """Return the last ``tail_beats`` of notes per track for a section.

    ``all_tracks`` is the composer-notes-so-far dict keyed by track name.
    ``last_section`` is the enriched-section dict with ``start_beat`` /
    ``end_beat`` / ``name``. An empty return dict means there's no tail
    to show (first section, or no notes landed in the section yet).
    """
    if not last_section or not all_tracks:
        return {}
    end = float(last_section.get("end_beat", 0.0))
    start_of_tail = max(
        float(last_section.get("start_beat", 0.0)),
        end - float(tail_beats),
    )
    result: dict[str, list[dict]] = {}
    for trk_name, notes in all_tracks.items():
        tail_notes = [
            n for n in notes
            if start_of_tail <= n.get("start_beat", -1) < end
        ]
        if tail_notes:
            tail_notes = sorted(
                tail_notes, key=lambda n: n.get("start_beat", 0.0),
            )
            result[trk_name] = tail_notes
    return result


def format_section_tail_for_composer(
    tail: dict[str, list[dict]],
    last_section: dict | None,
    max_notes_per_track: int = 8,
) -> str:
    """Render the tail as a multi-line block for the composer prompt."""
    if not tail or not last_section:
        return ""
    sec_name = str(last_section.get("name", "section")).upper()
    sec_end = float(last_section.get("end_beat", 0.0))
    lines = [
        f"PREVIOUS-SECTION TAIL (last {DEFAULT_TAIL_BEATS:.0f} beats "
        f"of [{sec_name}], ending at beat {sec_end:.1f}):",
        "Continue smoothly from this material — do not restart cold.",
    ]
    for trk_name, notes in tail.items():
        # Cap the per-track line so very busy tracks don't blow up the
        # prompt budget.
        shown = notes[-max_notes_per_track:]
        pieces: list[str] = []
        for n in shown:
            try:
                name = _pitch_name(int(n.get("pitch", 60)))
            except (TypeError, ValueError):
                name = "?"
            pieces.append(
                f"{name}@{float(n.get('start_beat', 0.0)):.2f}"
                f"({float(n.get('duration_beats', 1.0)):.2f})"
            )
        truncated = " " if len(notes) <= max_notes_per_track else " … "
        lines.append(
            f"  {trk_name}:{truncated}" + " ".join(pieces)
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main-hook helpers
# ---------------------------------------------------------------------------

def should_quote_hook(section_name: str) -> bool:
    """Return True if the composer should quote the hook in this section."""
    if not section_name:
        return False
    return section_name.lower() in HOOK_SECTIONS


def format_main_hook_for_composer(
    hook: list[ScoreNote] | list[dict],
    section_name: str,
) -> str:
    """Format the main hook motif for a composer prompt.

    Returns "" if the hook is empty, or if the section isn't one where
    the hook should be quoted (intro/outro/bridge) — we don't want to
    force the motif into sections that exist to contrast with it.
    """
    if not hook:
        return ""
    if not should_quote_hook(section_name):
        return ""

    pieces: list[str] = []
    for item in hook:
        if isinstance(item, ScoreNote):
            pitch = item.pitch
            start = item.start_beat
            dur = item.duration_beats
        elif isinstance(item, dict):
            try:
                pitch = int(item.get("pitch", 60))
                start = float(item.get("start_beat", 0.0))
                dur = float(item.get("duration_beats", 1.0))
            except (TypeError, ValueError):
                continue
        else:
            continue
        pieces.append(
            f"{_pitch_name(pitch)}@{start:.2f}({dur:.2f})"
        )
    if not pieces:
        return ""
    return (
        "MAIN HOOK (quote or reference this motif in this section "
        "— transpose to fit the harmony, but keep the rhythmic "
        "contour recognizable):\n"
        + "  " + " ".join(pieces)
    )

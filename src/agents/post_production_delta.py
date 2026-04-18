"""
Post-production delta summary for the final Critic pass (Bug C).

Context: the Critic used to run only INSIDE the refinement loop, where it
scored a score that had no ornaments, no drum/bass groove, no transition
events, and no humanization jitter — everything in Phase 3.5 / Phase 4
runs after the loop ends. The LLM would plateau because its last feedback
was based on a MIDI that never reaches the listener's ears.

This module produces a compact delta block the pipeline appends to the
FINAL critic pass (which runs after Phase 4c). It reports what post-
production actually added on top of the composer's output so the critic
can judge ornamental / groove / humanization quality directly.

Kept dependency-free (just the Score pydantic model) so it can be
unit-tested without pulling in AutoGen or the LLM client.
"""

from __future__ import annotations

from src.music.score import Score


# ---------------------------------------------------------------------------
# Counting helpers
# ---------------------------------------------------------------------------

def _count_track_notes(score: Score, role_keywords: tuple[str, ...]) -> int:
    """Sum notes across tracks whose role/name contains any keyword."""
    total = 0
    for trk in score.tracks:
        tag = f"{trk.role} {trk.name} {trk.instrument}".lower()
        if any(k in tag for k in role_keywords):
            total += len(trk.notes)
    return total


def _count_all_pitch_bends(score: Score) -> int:
    return sum(len(t.pitch_bends) for t in score.tracks)


def _count_all_cc_events(score: Score) -> int:
    return sum(len(t.cc_events) for t in score.tracks)


def _count_humanized_tracks(score: Score) -> int:
    return sum(1 for t in score.tracks if t.humanized)


def _count_rendered_tracks(score: Score) -> int:
    return sum(1 for t in score.tracks if t.rendered)


def _count_transition_events(score: Score) -> int:
    return len(score.transition_events)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def summarize_score_production(score: Score) -> dict:
    """Return a plain dict of production-stage counters.

    Exposed for tests; the delta builder subtracts two of these dicts.
    """
    return {
        "tracks": len(score.tracks),
        "total_notes": sum(len(t.notes) for t in score.tracks),
        "drum_notes": _count_track_notes(
            score, ("drum", "percussion", "perc"),
        ),
        "bass_notes": _count_track_notes(score, ("bass",)),
        "pitch_bends": _count_all_pitch_bends(score),
        "cc_events": _count_all_cc_events(score),
        "rendered_tracks": _count_rendered_tracks(score),
        "humanized_tracks": _count_humanized_tracks(score),
        "transition_events": _count_transition_events(score),
    }


def build_post_production_delta(
    pre_score: Score | None, post_score: Score,
) -> str:
    """Render a POST-PRODUCTION DELTA block.

    Shows what Phase 3.5 (drum/bass/transitions) + Phase 4 (ornaments,
    Chinese idioms, humanizer) added on top of the composer's score.

    Returns an empty string if ``pre_score`` is missing (e.g. this is a
    fresh run with no refinement state to compare to).
    """
    if pre_score is None:
        return ""
    pre = summarize_score_production(pre_score)
    post = summarize_score_production(post_score)

    def _delta(field: str) -> int:
        return post[field] - pre[field]

    def _fmt(label: str, field: str, unit: str = "") -> str:
        d = _delta(field)
        sign = "+" if d >= 0 else ""
        u = f" {unit}" if unit else ""
        return (
            f"  {label}: {pre[field]} -> {post[field]} "
            f"({sign}{d}{u})"
        )

    lines: list[str] = [
        "POST-PRODUCTION DELTA (Phase 3.5 + Phase 4):",
        _fmt("tracks", "tracks"),
        _fmt("total_notes", "total_notes", "notes"),
        _fmt("drum_notes", "drum_notes", "notes"),
        _fmt("bass_notes", "bass_notes", "notes"),
        _fmt("pitch_bend events", "pitch_bends"),
        _fmt("CC events", "cc_events"),
        _fmt("rendered tracks", "rendered_tracks"),
        _fmt("humanized tracks", "humanized_tracks"),
        _fmt("transition events", "transition_events"),
    ]
    # Inline one-line verdict to steer the critic's attention.
    if _delta("drum_notes") == 0 and _delta("bass_notes") == 0:
        lines.append(
            "  note: neither drum nor bass augmentation ran — "
            "this is unusual for pop/fusion and worth flagging if "
            "the spotlight plan expected them."
        )
    if _delta("pitch_bends") == 0 and _delta("cc_events") == 0:
        lines.append(
            "  note: no ornament expansion events were added — "
            "erhu/dizi parts may sound like MIDI scales rather than "
            "played instruments."
        )
    if _delta("humanized_tracks") == 0:
        lines.append(
            "  note: no tracks were humanized — note timings remain "
            "perfectly gridded."
        )
    return "\n".join(lines)


def build_cumulative_score_history(
    score_history: list[float],
) -> str:
    """Render a multi-round score trajectory for the final critic.

    The in-loop ``_build_delta_block`` only compares round N to round
    N-1. The final critic benefits from seeing the full trajectory so it
    can comment on whether the whole session was converging or thrashing.
    """
    if not score_history:
        return ""
    pts = [f"{s:.2f}" for s in score_history]
    trajectory = " -> ".join(pts)
    high = max(score_history)
    low = min(score_history)
    final = score_history[-1]
    lines = [
        "CUMULATIVE SCORE HISTORY (in-loop critic rounds):",
        f"  trajectory: {trajectory}",
        f"  high={high:.2f}  low={low:.2f}  final={final:.2f}",
    ]
    if len(score_history) >= 3:
        last_three = score_history[-3:]
        spread = max(last_three) - min(last_three)
        if spread < 0.03:
            lines.append(
                f"  note: last 3 rounds plateaued within {spread:.2f} — "
                "the in-loop critic ran out of things to demand."
            )
    return "\n".join(lines)

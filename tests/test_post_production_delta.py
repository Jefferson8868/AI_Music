"""
Tests for Bug C fix — post-production delta + cumulative score history.

The final-critic pass runs AFTER Phase 4c, and these helpers build the
context it sees. Covers:
  * ``summarize_score_production`` (counters)
  * ``build_post_production_delta`` (pre/post comparison + advisory notes)
  * ``build_cumulative_score_history`` (multi-round trajectory)
"""

from __future__ import annotations

from src.agents.post_production_delta import (
    build_cumulative_score_history,
    build_post_production_delta,
    summarize_score_production,
)
from src.music.score import (
    CCEvent, PitchBendEvent, Score, ScoreNote, ScoreTrack,
    TransitionEvent,
)


# ---------------------------------------------------------------------------
# Score fixtures
# ---------------------------------------------------------------------------

def _note(pitch=60, start=0.0, dur=1.0, vel=80) -> ScoreNote:
    return ScoreNote(
        pitch=pitch, start_beat=start, duration_beats=dur, velocity=vel,
    )


def _melody_track(n_notes: int = 4) -> ScoreTrack:
    return ScoreTrack(
        name="melody", instrument="Piano", role="melody",
        notes=[_note(60 + i, start=float(i)) for i in range(n_notes)],
    )


def _drum_track(n_notes: int = 8) -> ScoreTrack:
    return ScoreTrack(
        name="drums", instrument="Cinematic Drums", role="drums",
        notes=[_note(36, start=float(i) * 0.5) for i in range(n_notes)],
    )


def _bass_track(n_notes: int = 4) -> ScoreTrack:
    return ScoreTrack(
        name="bass", instrument="Synth Bass", role="bass",
        notes=[_note(40, start=float(i)) for i in range(n_notes)],
    )


# ---------------------------------------------------------------------------
# summarize_score_production
# ---------------------------------------------------------------------------

def test_summary_counts_tracks_and_notes():
    s = Score(tracks=[_melody_track(4), _drum_track(8)])
    summary = summarize_score_production(s)
    assert summary["tracks"] == 2
    assert summary["total_notes"] == 12
    assert summary["drum_notes"] == 8
    assert summary["bass_notes"] == 0


def test_summary_counts_bass_by_role_keyword():
    s = Score(tracks=[_bass_track(4)])
    assert summarize_score_production(s)["bass_notes"] == 4


def test_summary_counts_pitch_bends_and_cc():
    trk = _melody_track(2)
    trk.pitch_bends = [
        PitchBendEvent(beat=0.0, value=1000),
        PitchBendEvent(beat=0.5, value=2000),
    ]
    trk.cc_events = [
        CCEvent(beat=0.0, controller=1, value=60),
        CCEvent(beat=0.25, controller=1, value=90),
        CCEvent(beat=0.5, controller=1, value=80),
    ]
    s = Score(tracks=[trk])
    summary = summarize_score_production(s)
    assert summary["pitch_bends"] == 2
    assert summary["cc_events"] == 3


def test_summary_counts_flags_and_transitions():
    trk = _melody_track(1)
    trk.rendered = True
    trk.humanized = True
    s = Score(
        tracks=[trk],
        transition_events=[
            TransitionEvent(
                beat=16.0, kind="riser", target_section="chorus",
            ),
            TransitionEvent(
                beat=32.0, kind="impact", target_section="bridge",
            ),
        ],
    )
    summary = summarize_score_production(s)
    assert summary["rendered_tracks"] == 1
    assert summary["humanized_tracks"] == 1
    assert summary["transition_events"] == 2


# ---------------------------------------------------------------------------
# build_post_production_delta
# ---------------------------------------------------------------------------

def test_delta_returns_empty_when_pre_score_is_none():
    s = Score(tracks=[_melody_track()])
    assert build_post_production_delta(None, s) == ""


def test_delta_shows_drum_and_bass_added():
    pre = Score(tracks=[_melody_track(4)])
    post = Score(tracks=[_melody_track(4), _drum_track(8), _bass_track(4)])
    text = build_post_production_delta(pre, post)
    assert "POST-PRODUCTION DELTA" in text
    assert "drum_notes: 0 -> 8" in text
    assert "bass_notes: 0 -> 4" in text
    assert "tracks: 1 -> 3" in text


def test_delta_shows_ornament_events_added():
    pre = Score(tracks=[_melody_track(4)])
    post_trk = _melody_track(4)
    post_trk.pitch_bends = [
        PitchBendEvent(beat=0.0, value=100) for _ in range(6)
    ]
    post_trk.cc_events = [
        CCEvent(beat=0.0, controller=1, value=60) for _ in range(12)
    ]
    post_trk.rendered = True
    post = Score(tracks=[post_trk])
    text = build_post_production_delta(pre, post)
    assert "pitch_bend events: 0 -> 6 (+6)" in text
    assert "CC events: 0 -> 12 (+12)" in text
    assert "rendered tracks: 0 -> 1" in text


def test_delta_flags_missing_drum_bass_augmentation():
    # When neither drums nor bass got added in post-production, the
    # block appends an advisory note so the critic can call it out.
    pre = Score(tracks=[_melody_track(4)])
    post = Score(tracks=[_melody_track(4)])
    text = build_post_production_delta(pre, post)
    assert "neither drum nor bass augmentation ran" in text


def test_delta_flags_missing_ornament_expansion():
    pre = Score(tracks=[_melody_track(4)])
    post = Score(tracks=[_melody_track(4), _drum_track(8)])
    text = build_post_production_delta(pre, post)
    # drums added so the drum-notes advisory is NOT present...
    assert "neither drum nor bass augmentation ran" not in text
    # ...but no pitch-bend / CC events were added → advisory fires.
    assert "no ornament expansion events were added" in text


def test_delta_flags_missing_humanizer():
    pre = Score(tracks=[_melody_track(4)])
    post_trk = _melody_track(4)
    # Ornaments were expanded but no track got humanized.
    post_trk.pitch_bends = [PitchBendEvent(beat=0.0, value=500)]
    post_trk.rendered = True
    post = Score(tracks=[post_trk, _drum_track(8)])
    text = build_post_production_delta(pre, post)
    assert "no tracks were humanized" in text


def test_delta_happy_path_no_advisories():
    # Everything got added in post-production → no advisory notes.
    pre = Score(tracks=[_melody_track(4)])
    post_melody = _melody_track(4)
    post_melody.rendered = True
    post_melody.humanized = True
    post_melody.pitch_bends = [PitchBendEvent(beat=0.0, value=500)]
    post_melody.cc_events = [CCEvent(beat=0.0, controller=1, value=60)]
    post_drums = _drum_track(8)
    post_drums.humanized = True
    post = Score(
        tracks=[post_melody, post_drums, _bass_track(4)],
    )
    text = build_post_production_delta(pre, post)
    assert "neither drum nor bass augmentation ran" not in text
    assert "no ornament expansion events were added" not in text
    assert "no tracks were humanized" not in text


# ---------------------------------------------------------------------------
# build_cumulative_score_history
# ---------------------------------------------------------------------------

def test_history_empty():
    assert build_cumulative_score_history([]) == ""


def test_history_renders_trajectory():
    text = build_cumulative_score_history([0.42, 0.55, 0.60])
    assert "CUMULATIVE SCORE HISTORY" in text
    assert "0.42 -> 0.55 -> 0.60" in text
    assert "high=0.60" in text and "low=0.42" in text
    assert "final=0.60" in text


def test_history_flags_plateau():
    text = build_cumulative_score_history([0.40, 0.60, 0.61, 0.61, 0.62])
    assert "plateaued" in text


def test_history_no_plateau_on_rising_trajectory():
    text = build_cumulative_score_history([0.40, 0.50, 0.70])
    assert "plateaued" not in text

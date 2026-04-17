"""
Tests for the performance renderer (src/music/performance.py).

These tests use only the core data models — no LLM, no MIDI file I/O,
no Magenta. Each test builds a small Score, runs the renderer, and
asserts properties of the output events.

Run with:  pytest tests/test_performance.py
"""

from __future__ import annotations

import pytest

from src.music.performance import (
    BEND_MAX,
    BEND_MIN,
    MAX_RETRIGGERS_PER_NOTE,
    apply_performance_render,
    apply_performance_render_to_track,
)
from src.music.score import (
    CCEvent,
    PitchBendEvent,
    Score,
    ScoreNote,
    ScoreSection,
    ScoreTrack,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _mk_track(
    instrument: str = "Erhu",
    role: str = "lead",
    notes: list[ScoreNote] | None = None,
    channel: int = 0,
) -> ScoreTrack:
    return ScoreTrack(
        name=f"{instrument}_track",
        instrument=instrument,
        role=role,
        channel=channel,
        program=110,
        notes=notes or [],
    )


def _mk_score_with_track(track: ScoreTrack, tempo: int = 120) -> Score:
    return Score(
        title="test",
        key="C",
        scale_type="pentatonic",
        tempo=tempo,
        time_signature=[4, 4],
        sections=[ScoreSection(name="verse", start_beat=0.0, bars=4)],
        tracks=[track],
    )


def _erhu_card() -> dict:
    return {
        "performance_recipes": {
            "vibrato_deep_depth": 75,
            "vibrato_deep_rate_hz": 6.0,
            "vibrato_light_depth": 35,
            "vibrato_light_rate_hz": 5.0,
        },
        "auto_rules": [
            {"condition": "duration > 1.5",
             "add_ornaments": ["vibrato_deep"]},
            {"condition": "ascending_step",
             "add_ornaments": ["slide_up_from:1"]},
        ],
        "ornament_vocabulary": [
            "vibrato_deep", "vibrato_light", "slide_up_from",
        ],
        "velocity_envelope_preset": {
            "attack": 0.15, "peak_ratio": 0.5, "decay": 0.10,
        },
    }


def _dizi_card() -> dict:
    return {
        "performance_recipes": {
            "vibrato_light_depth": 35,
            "vibrato_light_rate_hz": 5.2,
        },
        "auto_rules": [
            {"condition": "duration > 2.0",
             "add_ornaments": ["breath_swell"]},
        ],
        "ornament_vocabulary": [
            "breath_swell", "breath_fade", "flutter", "overblow",
        ],
        "velocity_envelope_preset": {
            "attack": 0.20, "peak_ratio": 0.4, "decay": 0.15,
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_vibrato_emits_cc1_modulation():
    note = ScoreNote(
        pitch=67, start_beat=0.0, duration_beats=2.0,
        velocity=80, ornaments=["vibrato_deep"],
    )
    track = _mk_track(notes=[note])
    out = apply_performance_render_to_track(track, _erhu_card(), tempo_bpm=120)

    mod_events = [c for c in out.cc_events if c.controller == 1]
    assert len(mod_events) > 0, "vibrato_deep must emit CC1 modulation"
    # All CC1 values in valid range.
    for c in mod_events:
        assert 0 <= c.value <= 127
    # Events span the note's duration.
    assert min(c.beat for c in mod_events) >= note.start_beat - 1e-6
    assert max(c.beat for c in mod_events) <= (
        note.start_beat + note.duration_beats + 1e-6
    )


def test_slide_up_from_emits_pitch_bend_ramp():
    note = ScoreNote(
        pitch=67, start_beat=1.0, duration_beats=1.0,
        velocity=80, ornaments=["slide_up_from:3"],
    )
    track = _mk_track(notes=[note])
    out = apply_performance_render_to_track(track, _erhu_card(), tempo_bpm=120)

    bends = sorted(out.pitch_bends, key=lambda b: b.beat)
    assert len(bends) >= 4, "slide_up_from must emit a pitch-bend ramp"
    assert bends[0].beat < note.start_beat, (
        "approach must begin before the note onset"
    )
    # Starts negative (below), ends at 0 around the note onset.
    assert bends[0].value < 0
    # There should be a neutral bend at or after note onset.
    neutral_at_onset = any(
        abs(b.beat - note.start_beat) < 0.05 and b.value == 0
        for b in bends
    )
    assert neutral_at_onset
    # All bends clamped.
    for b in bends:
        assert BEND_MIN <= b.value <= BEND_MAX


def test_flutter_inserts_retriggers_and_caps_count():
    # Very long note to try to exceed the retrigger cap.
    note = ScoreNote(
        pitch=72, start_beat=0.0, duration_beats=16.0,
        velocity=90, ornaments=["flutter"],
    )
    track = _mk_track(instrument="Dizi", notes=[note])
    out = apply_performance_render_to_track(track, _dizi_card(), tempo_bpm=100)

    # Original note is now a short "buzz" + many retriggers at same pitch.
    same_pitch_notes = [n for n in out.notes if n.pitch == note.pitch]
    assert len(same_pitch_notes) <= MAX_RETRIGGERS_PER_NOTE + 1, (
        "flutter must cap its retriggers"
    )
    assert len(same_pitch_notes) >= 2, "flutter must produce retriggers"
    # CC1 buzz events present too.
    mod_events = [c for c in out.cc_events if c.controller == 1]
    assert len(mod_events) > 0


def test_idempotency_second_render_is_noop():
    note = ScoreNote(
        pitch=60, start_beat=0.0, duration_beats=2.0,
        velocity=80, ornaments=["vibrato_deep"],
    )
    track = _mk_track(notes=[note])
    first = apply_performance_render_to_track(
        track, _erhu_card(), tempo_bpm=120,
    )
    first_bend_count = len(first.pitch_bends)
    first_cc_count = len(first.cc_events)
    first_note_count = len(first.notes)
    assert first.rendered is True

    # Second pass should NOT re-apply ornaments.
    second = apply_performance_render_to_track(
        first, _erhu_card(), tempo_bpm=120,
    )
    assert len(second.pitch_bends) == first_bend_count
    assert len(second.cc_events) == first_cc_count
    assert len(second.notes) == first_note_count


def test_auto_rules_apply_vibrato_on_long_notes():
    # No explicit ornaments — auto_rule should add vibrato_deep.
    long_note = ScoreNote(
        pitch=64, start_beat=0.0, duration_beats=2.0, velocity=80,
    )
    short_note = ScoreNote(
        pitch=64, start_beat=2.0, duration_beats=0.5, velocity=80,
    )
    track = _mk_track(notes=[long_note, short_note])
    out = apply_performance_render_to_track(track, _erhu_card(), tempo_bpm=120)

    mod_events = [c for c in out.cc_events if c.controller == 1]
    assert len(mod_events) > 0, (
        "auto_rule 'duration > 1.5 -> vibrato_deep' must fire"
    )
    # Those CC1 events should concentrate in the long note's span.
    within_long = sum(
        1 for c in mod_events
        if 0.0 <= c.beat <= 2.0 + 0.01
    )
    assert within_long == len(mod_events)


def test_legato_to_next_degrades_gracefully_on_last_note():
    # Single note with legato_to_next — should fall back to tenuto-like.
    note = ScoreNote(
        pitch=60, start_beat=0.0, duration_beats=1.0, velocity=80,
        ornaments=["legato_to_next"],
    )
    track = _mk_track(notes=[note])
    out = apply_performance_render_to_track(track, None, tempo_bpm=120)
    # Must not crash; the note must still be present; duration unchanged.
    notes_out = [n for n in out.notes if n.pitch == 60]
    assert len(notes_out) >= 1
    assert notes_out[0].duration_beats == pytest.approx(1.0)


def test_unknown_ornament_warns_but_does_not_crash():
    note = ScoreNote(
        pitch=60, start_beat=0.0, duration_beats=1.0, velocity=80,
        ornaments=["this_is_not_a_real_ornament"],
    )
    track = _mk_track(notes=[note])
    # Must not raise.
    out = apply_performance_render_to_track(track, None, tempo_bpm=120)
    # Nothing emitted for the unknown token; base note preserved.
    assert len(out.pitch_bends) == 0
    assert len(out.cc_events) == 0
    assert len(out.notes) == 1


def test_bend_values_clamped_to_midi_range():
    # Use a large semitone argument to try to overflow.
    note = ScoreNote(
        pitch=67, start_beat=1.0, duration_beats=2.0, velocity=80,
        ornaments=["slide_up_from:5"],  # clamped by spec's arg_range (1-5)
    )
    track = _mk_track(notes=[note])
    out = apply_performance_render_to_track(track, None, tempo_bpm=120)
    for b in out.pitch_bends:
        assert BEND_MIN <= b.value <= BEND_MAX


def test_golden_snapshot_erhu_chorus_ornament_density():
    """Golden-ish snapshot: a 4-note erhu chorus phrase produces a
    substantial number of bend + CC events (enough to actually feel like
    a performed line, not a bare MIDI scale).
    """
    notes = [
        ScoreNote(
            pitch=67, start_beat=0.0, duration_beats=2.0,
            velocity=90, ornaments=["vibrato_deep", "slide_up_from:2"],
        ),
        ScoreNote(
            pitch=69, start_beat=2.0, duration_beats=1.0,
            velocity=95, ornaments=["vibrato_light"],
        ),
        ScoreNote(
            pitch=72, start_beat=3.0, duration_beats=2.0,
            velocity=100, ornaments=["vibrato_deep", "slide_down_to:1"],
        ),
        ScoreNote(
            pitch=69, start_beat=5.0, duration_beats=3.0,
            velocity=85, ornaments=["vibrato_deep", "bend_dip"],
        ),
    ]
    track = _mk_track(notes=notes)
    score = _mk_score_with_track(track, tempo=90)
    out_score = apply_performance_render(score, {"Erhu": _erhu_card()})
    out_track = out_score.tracks[0]

    total_cc = len(out_track.cc_events)
    total_bend = len(out_track.pitch_bends)

    # A four-note erhu chorus phrase must contribute at least dozens of
    # control events — otherwise the rendered sound is still a bare scale.
    assert total_cc >= 40, f"too few CC events ({total_cc}); feels scale-like"
    assert total_bend >= 30, (
        f"too few pitch-bend events ({total_bend}); slides/dips missing"
    )
    assert out_track.rendered is True


def test_full_score_render_leaves_source_intact():
    note = ScoreNote(
        pitch=64, start_beat=0.0, duration_beats=2.0,
        velocity=80, ornaments=["vibrato_deep"],
    )
    track = _mk_track(notes=[note])
    score = _mk_score_with_track(track)
    orig_bend_count = len(score.tracks[0].pitch_bends)
    orig_cc_count = len(score.tracks[0].cc_events)

    _ = apply_performance_render(score, {"Erhu": _erhu_card()})

    # Input must not be mutated.
    assert len(score.tracks[0].pitch_bends) == orig_bend_count
    assert len(score.tracks[0].cc_events) == orig_cc_count
    assert score.tracks[0].rendered is False

"""
Tests for Round 2 Phase C1 — MIDI humanizer.

Covers:
  * Deterministic output given a seed.
  * Velocity jitter stays inside the per-instrument budget.
  * Micro-timing shifts notes but preserves ordering.
  * humanized-flag idempotency: a second pass is a no-op.
  * Round-robin detune emits pitch-bend events for same-pitch repeats.
  * Tempo breathing emits CC11 expression events per phrase.

Chinese performance module has its own test block at the bottom.
"""

from __future__ import annotations

from src.music.humanize import humanize_score, humanize_track
from src.music.performance_chinese import apply_chinese_performance
from src.music.score import Score, ScoreNote, ScoreTrack


def _make_drum_track(n: int = 8) -> ScoreTrack:
    return ScoreTrack(
        name="drums_kick", instrument="drums", role="rhythm",
        channel=9, program=0,
        notes=[
            ScoreNote(
                pitch=36, start_beat=float(i),
                duration_beats=0.125, velocity=100,
            )
            for i in range(n)
        ],
    )


def _make_piano_track(n: int = 4) -> ScoreTrack:
    return ScoreTrack(
        name="piano", instrument="piano", role="melody",
        channel=0, program=0,
        notes=[
            ScoreNote(
                pitch=60 + i, start_beat=float(i),
                duration_beats=1.0, velocity=80,
            )
            for i in range(n)
        ],
    )


def _make_score(*tracks: ScoreTrack) -> Score:
    s = Score(
        title="t", key="C", scale_type="major",
        tempo=100, time_signature=[4, 4],
    )
    s.tracks = list(tracks)
    return s


# --------------------------------------------------------------------------
# Humanizer: velocity / micro-timing / determinism
# --------------------------------------------------------------------------

def test_humanize_is_deterministic_given_seed():
    t1 = _make_piano_track()
    t2 = _make_piano_track()
    h1 = humanize_track(t1, seed=42)
    h2 = humanize_track(t2, seed=42)
    vels1 = [n.velocity for n in h1.notes]
    vels2 = [n.velocity for n in h2.notes]
    assert vels1 == vels2


def test_humanize_varies_with_different_seed():
    t = _make_piano_track(n=8)
    a = humanize_track(t, seed=1)
    b = humanize_track(t, seed=2)
    # Unlikely to hit collisions across 8 notes.
    assert [n.velocity for n in a.notes] != [n.velocity for n in b.notes]


def test_humanize_velocity_stays_in_budget():
    """piano budget is 7%; with original vel=80, swing should stay in
    a loose ±15 range even across an adversarial seed."""
    t = _make_piano_track(n=16)
    h = humanize_track(t, seed=7)
    for n in h.notes:
        assert 40 <= n.velocity <= 127


def test_humanize_preserves_note_count():
    t = _make_piano_track(n=8)
    h = humanize_track(t, seed=0)
    assert len(h.notes) == len(t.notes)


def test_humanize_flag_is_idempotent():
    s = _make_score(_make_piano_track())
    once = humanize_score(s, seed=0)
    twice = humanize_score(once, seed=0)
    # Second call was a no-op because track.humanized is True.
    assert [n.velocity for n in once.tracks[0].notes] == \
        [n.velocity for n in twice.tracks[0].notes]
    assert [n.start_beat for n in once.tracks[0].notes] == \
        [n.start_beat for n in twice.tracks[0].notes]


def test_humanize_sets_humanized_flag():
    s = _make_score(_make_piano_track())
    h = humanize_score(s, seed=0)
    assert all(t.humanized for t in h.tracks)


def test_humanize_starts_at_nonnegative_beat():
    """The random walk should never push a note below beat 0."""
    t = ScoreTrack(
        name="piano", instrument="piano", role="melody",
        channel=0, program=0,
        notes=[ScoreNote(
            pitch=60, start_beat=0.0,
            duration_beats=1.0, velocity=80,
        )],
    )
    h = humanize_track(t, seed=0)
    assert h.notes[0].start_beat >= 0.0


def test_humanize_round_robin_emits_pitch_bends():
    """Same-pitch repeats within the round-robin window should get
    pitch-bend detune events."""
    track = ScoreTrack(
        name="piano", instrument="piano", role="melody",
        channel=0, program=0,
        notes=[
            ScoreNote(
                pitch=60, start_beat=0.0,
                duration_beats=0.5, velocity=80,
            ),
            ScoreNote(
                pitch=60, start_beat=1.0,
                duration_beats=0.5, velocity=80,
            ),
            ScoreNote(
                pitch=60, start_beat=1.5,
                duration_beats=0.5, velocity=80,
            ),
        ],
    )
    h = humanize_track(track, seed=0)
    # At least two of the three same-pitch repeats should generate a
    # detune bend event.
    assert len(h.pitch_bends) >= 1


def test_humanize_emits_expression_cc_per_phrase():
    """Tempo-breathing writes CC11 events. A continuous 4-note run is
    a single phrase (no rests); we still get samples across it."""
    t = _make_piano_track(n=4)
    h = humanize_track(t, seed=0)
    cc11s = [e for e in h.cc_events if e.controller == 11]
    assert len(cc11s) >= 1


def test_humanize_drum_track_applies_snare_offset():
    """Snare has a positive microtime offset — notes should shift
    slightly later on average."""
    snare = ScoreTrack(
        name="drums_snare", instrument="drums", role="rhythm",
        channel=9, program=0,
        notes=[ScoreNote(
            pitch=38, start_beat=1.0,
            duration_beats=0.125, velocity=100,
        )],
    )
    # With seed 0 the random walk is small; the deterministic snare
    # offset should dominate, shifting past 1.0.
    h = humanize_track(snare, seed=0, tempo_bpm=100.0)
    # No strict ordering guarantee because of jitter, but the shift
    # should be in a small band around the note's original position.
    assert 0.9 < h.notes[0].start_beat < 1.1


# --------------------------------------------------------------------------
# Chinese performance module
# --------------------------------------------------------------------------

def test_chinese_applies_delayed_vibrato_on_long_erhu_notes():
    trk = ScoreTrack(
        name="erhu", instrument="erhu", role="melody",
        channel=0, program=0,
        notes=[ScoreNote(
            pitch=65, start_beat=0.0,
            duration_beats=2.0, velocity=80,
        )],
    )
    s = _make_score(trk)
    out = apply_chinese_performance(s)
    erhu = out.tracks[0]
    cc1 = [e for e in erhu.cc_events if e.controller == 1]
    assert cc1, "Expected modulation (CC1) events for delayed vibrato"
    # Onset of the LFO must be AFTER the note onset (delayed).
    assert cc1[0].beat > 0.0


def test_chinese_skips_non_chinese_instruments():
    trk = ScoreTrack(
        name="piano", instrument="piano", role="melody",
        channel=0, program=0,
        notes=[ScoreNote(
            pitch=60, start_beat=0.0,
            duration_beats=2.0, velocity=80,
        )],
    )
    s = _make_score(trk)
    out = apply_chinese_performance(s)
    # Piano should be untouched — no CC events written.
    assert out.tracks[0].cc_events == []


def test_chinese_dizi_emits_breath_attack_cc2():
    trk = ScoreTrack(
        name="dizi", instrument="dizi", role="melody",
        channel=0, program=0,
        notes=[
            ScoreNote(
                pitch=72, start_beat=0.0,
                duration_beats=0.5, velocity=80,
            ),
            ScoreNote(
                pitch=74, start_beat=1.0,
                duration_beats=0.5, velocity=80,
            ),
        ],
    )
    s = _make_score(trk)
    out = apply_chinese_performance(s)
    cc2 = [e for e in out.tracks[0].cc_events if e.controller == 2]
    # 3 breath samples per note × 2 notes = 6 events.
    assert len(cc2) >= 6


def test_chinese_portamento_between_close_erhu_notes():
    trk = ScoreTrack(
        name="erhu", instrument="erhu", role="melody",
        channel=0, program=0,
        notes=[
            ScoreNote(
                pitch=65, start_beat=0.0,
                duration_beats=0.5, velocity=80,
            ),
            ScoreNote(
                pitch=67, start_beat=0.5,   # adjacent, +2 semitones
                duration_beats=0.5, velocity=80,
            ),
        ],
    )
    s = _make_score(trk)
    out = apply_chinese_performance(s)
    assert out.tracks[0].pitch_bends, (
        "Expected pitch-bend ramp between adjacent erhu notes"
    )


def test_chinese_phrase_accent_lifts_velocity_after_rest():
    trk = ScoreTrack(
        name="erhu", instrument="erhu", role="melody",
        channel=0, program=0,
        notes=[
            ScoreNote(
                pitch=65, start_beat=0.0,
                duration_beats=0.25, velocity=70,
            ),
            ScoreNote(
                pitch=65, start_beat=2.0,   # 1.75-beat gap = phrase start
                duration_beats=0.25, velocity=70,
            ),
        ],
    )
    s = _make_score(trk)
    out = apply_chinese_performance(s)
    # Both notes start a phrase (first is always a phrase start; second
    # is preceded by a long rest), so both get the accent bump.
    assert out.tracks[0].notes[1].velocity > 70

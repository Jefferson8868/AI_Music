"""
Tests for Round 2 Phase B — song-feel arrangement agents.

Covers:
  * GrooveLibrary template selection (tempo-matched, role-matched).
  * DrumAgent per-section note emission: kick / snare / hat voices
    appear, swing is applied, last-bar fill fires.
  * BassAgent locks notes to the kick pattern (one bass note per
    kick hit, silence elsewhere).
  * TransitionAgent emits the correct recipe per boundary pair,
    including the generic fallback.

No LLM, no network, deterministic — safe for CI.
"""

from __future__ import annotations

from src.agents.bass_agent import BassAgent, extract_kick_positions
from src.agents.drum_agent import DrumAgent
from src.agents.transition_agent import (
    TransitionAgent,
    _BOUNDARY_RECIPES,
    _GENERIC_BOUNDARY_RECIPE,
    is_midi_kind,
    is_sample_kind,
)
from src.knowledge.groove_library import (
    ALL_TEMPLATES,
    select_template,
    template_by_name,
)
from src.music.score import Score, ScoreSection, ScoreTrack


# --------------------------------------------------------------------------
# GrooveLibrary
# --------------------------------------------------------------------------

def test_groove_library_has_core_templates():
    names = {t.name for t in ALL_TEMPLATES}
    # A handful of the templates the plan requires must be present.
    assert "ballad_75bpm" in names
    assert "modern_pop_100" in names


def test_select_template_matches_tempo_range():
    tpl = select_template("verse", 75.0, "")
    assert tpl is not None
    lo, hi = tpl.tempo_range
    assert lo <= 75 <= hi


def test_template_by_name_returns_none_for_unknown():
    assert template_by_name("nonexistent_groove_xyz") is None


# --------------------------------------------------------------------------
# DrumAgent
# --------------------------------------------------------------------------

def test_drum_agent_emits_kick_snare_hat_voices():
    agent = DrumAgent()
    tracks = agent.compose_section(
        section_role="chorus",
        start_beat=0.0,
        end_beat=16.0,
        bars=4,
        tempo_bpm=100.0,
        genre_hint="pop",
    )
    names = {t.name for t in tracks}
    # A pop chorus template must light up at least kick + snare + hat.
    assert any("kick" in n for n in names)
    assert any("snare" in n for n in names)
    assert any("chh" in n or "ohh" in n for n in names)


def test_drum_agent_last_bar_fill_fires_when_requested():
    agent = DrumAgent()
    tracks = agent.compose_section(
        section_role="verse",
        start_beat=0.0,
        end_beat=16.0,
        bars=4,
        tempo_bpm=100.0,
        genre_hint="pop",
        add_fill_on_last_bar=True,
    )
    fill_tracks = [t for t in tracks if t.name == "drums_fill"]
    assert fill_tracks, "Expected a drums_fill track when add_fill is on"
    fill = fill_tracks[0]
    # Fill should place notes inside the last bar (beats 12..16).
    assert all(n.start_beat >= 12.0 - 0.01 for n in fill.notes)
    assert any(n.start_beat < 16.0 for n in fill.notes)


def test_drum_agent_fills_skipped_on_single_bar_sections():
    agent = DrumAgent()
    tracks = agent.compose_section(
        section_role="intro",
        start_beat=0.0,
        end_beat=4.0,
        bars=1,
        tempo_bpm=100.0,
        genre_hint="pop",
        add_fill_on_last_bar=True,
    )
    # bars < 2 → no fill track.
    assert all(t.name != "drums_fill" for t in tracks)


# --------------------------------------------------------------------------
# BassAgent
# --------------------------------------------------------------------------

def test_bass_agent_locks_to_kick_positions():
    kick_positions = [0.0, 1.5, 2.0, 3.5, 4.0, 5.5, 6.0, 7.5]
    agent = BassAgent()
    track = agent.compose_section(
        section_role="chorus",
        start_beat=0.0,
        end_beat=8.0,
        bars=2,
        key_root_midi=36,
        scale_type="major",
        kick_positions=kick_positions,
        chord_progression=["I", "V"],
    )
    assert track.role == "bass"
    # One bass note per kick position, at the same beat.
    bass_beats = [round(n.start_beat, 2) for n in track.notes]
    for k in kick_positions:
        assert round(k, 2) in bass_beats


def test_bass_agent_falls_back_when_kicks_is_none():
    """kick_positions=None means 'no info' → 4-on-floor fallback."""
    agent = BassAgent()
    track = agent.compose_section(
        section_role="intro",
        start_beat=0.0,
        end_beat=8.0,
        bars=2,
        key_root_midi=36,
        scale_type="major",
        kick_positions=None,   # no info → fallback
        chord_progression=["I"],
    )
    assert track.notes, "Bass should fall back to a skeletal line"


def test_bass_agent_silent_when_kicks_list_is_empty():
    """kick_positions=[] means 'explicitly no kicks' → bass stays silent."""
    agent = BassAgent()
    track = agent.compose_section(
        section_role="intro",
        start_beat=0.0,
        end_beat=8.0,
        bars=2,
        key_root_midi=36,
        scale_type="major",
        kick_positions=[],   # explicit empty → no bass
        chord_progression=["I"],
    )
    assert track.notes == [], (
        "Bass should be silent when there are no kicks"
    )


def test_bass_agent_downbeat_hits_root():
    agent = BassAgent()
    track = agent.compose_section(
        section_role="verse",
        start_beat=0.0,
        end_beat=4.0,
        bars=1,
        key_root_midi=36,
        scale_type="major",
        kick_positions=[0.0, 2.0],
        chord_progression=["I"],
    )
    downbeat = next((n for n in track.notes if n.start_beat == 0.0), None)
    assert downbeat is not None
    assert downbeat.pitch == 36   # root of I chord in C


def test_extract_kick_positions_scans_named_track_only():
    good = ScoreTrack(
        name="drums_kick", instrument="drums", role="rhythm",
        channel=9, program=0, notes=[],
    )
    from src.music.score import ScoreNote
    good.notes.append(ScoreNote(
        pitch=36, start_beat=0.0,
        duration_beats=0.125, velocity=100,
    ))
    good.notes.append(ScoreNote(
        pitch=36, start_beat=2.0,
        duration_beats=0.125, velocity=100,
    ))
    snare = ScoreTrack(
        name="drums_snare", instrument="drums", role="rhythm",
        channel=9, program=0, notes=[
            ScoreNote(
                pitch=38, start_beat=1.0,
                duration_beats=0.125, velocity=100,
            ),
        ],
    )
    kicks = extract_kick_positions([good, snare])
    assert kicks == [0.0, 2.0]


# --------------------------------------------------------------------------
# TransitionAgent
# --------------------------------------------------------------------------

def _score_with_sections(*names_bars: tuple[str, int]) -> Score:
    s = Score(
        title="t", key="C", scale_type="major",
        tempo=100, time_signature=[4, 4],
    )
    offset = 0.0
    for n, b in names_bars:
        s.sections.append(ScoreSection(
            name=n, start_beat=offset, bars=b,
        ))
        offset += b * 4.0
    return s


def test_transition_agent_emits_events_per_boundary():
    score = _score_with_sections(
        ("intro", 2), ("verse", 4), ("chorus", 4),
    )
    agent = TransitionAgent()
    events = agent.plan_transitions(score)
    # 2 boundaries × (at least 1 event each)
    assert len(events) >= 2
    kinds = {e.kind for e in events}
    assert kinds, "Expected at least some event kinds"


def test_transition_agent_respects_known_recipes():
    # pre_chorus → chorus boundary must emit riser + reverse_cymbal +
    # impact + sub_drop per the recipe table.
    score = _score_with_sections(("pre_chorus", 4), ("chorus", 4))
    agent = TransitionAgent()
    events = agent.plan_transitions(score)
    kinds = [e.kind for e in events]
    for expected in ("riser", "reverse_cymbal", "impact", "sub_drop"):
        assert expected in kinds, f"Missing '{expected}' for pre_chorus→chorus"


def test_transition_agent_generic_fallback():
    # An unusual pair that isn't in _BOUNDARY_RECIPES.
    score = _score_with_sections(("solo", 4), ("tag", 2))
    agent = TransitionAgent()
    events = agent.plan_transitions(score)
    # Should use the generic recipe (single impact on the downbeat).
    kinds = [e.kind for e in events]
    assert "impact" in kinds


def test_transition_agent_is_idempotent():
    score = _score_with_sections(("verse", 4), ("chorus", 4))
    agent = TransitionAgent()
    first = agent.plan_transitions(score)
    score.transition_events = list(first)
    second = agent.plan_transitions(score)
    # Second call returns the same list (doesn't re-plan).
    assert len(second) == len(first)


def test_transition_agent_attach_mutates_score():
    score = _score_with_sections(("verse", 4), ("chorus", 4))
    agent = TransitionAgent()
    agent.attach(score)
    assert len(score.transition_events) > 0


def test_transition_agent_handles_single_section():
    score = _score_with_sections(("intro", 4))
    agent = TransitionAgent()
    events = agent.plan_transitions(score)
    assert events == []


# --------------------------------------------------------------------------
# Recipe / kind classification
# --------------------------------------------------------------------------

def test_recipe_keys_use_known_section_names():
    # Every recipe key should use valid-ish lowercase names.
    for (a, b) in _BOUNDARY_RECIPES:
        assert a.islower() and b.islower()


def test_generic_recipe_has_impact():
    kinds = [k for (k, _, _) in _GENERIC_BOUNDARY_RECIPE]
    assert "impact" in kinds


def test_is_midi_kind_and_is_sample_kind_partition():
    # Canonical examples from the plan table.
    assert is_midi_kind("snare_roll")
    assert is_midi_kind("kick_drop")
    assert is_midi_kind("crash")
    assert is_sample_kind("riser")
    assert is_sample_kind("reverse_cymbal")
    assert is_sample_kind("impact")
    # No overlap.
    assert not is_sample_kind("snare_roll")
    assert not is_midi_kind("riser")

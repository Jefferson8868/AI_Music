"""
Tests for Bug E — neighbor-section context + main-hook helpers.

These helpers let the pipeline inject REAL musical continuity between
sections (last 8 beats of each track) plus a shared hook motif quoted
in verse + chorus, so the output doesn't feel stitched-together.
"""

from __future__ import annotations

from src.agents.section_continuity import (
    DEFAULT_TAIL_BEATS,
    HOOK_SECTIONS,
    extract_section_tail,
    format_main_hook_for_composer,
    format_section_tail_for_composer,
    should_quote_hook,
)
from src.music.score import ScoreNote


# ---------------------------------------------------------------------------
# extract_section_tail
# ---------------------------------------------------------------------------

def _note(pitch=60, start=0.0, dur=1.0, vel=80) -> dict:
    return {
        "pitch": pitch, "start_beat": start,
        "duration_beats": dur, "velocity": vel,
    }


def test_tail_empty_when_no_section():
    out = extract_section_tail({"melody": [_note()]}, None)
    assert out == {}


def test_tail_empty_when_no_tracks():
    sec = {"name": "verse", "start_beat": 0.0, "end_beat": 16.0}
    assert extract_section_tail({}, sec) == {}


def test_tail_returns_last_8_beats():
    sec = {"name": "verse", "start_beat": 0.0, "end_beat": 16.0}
    # 16 notes across beats 0..15.
    notes = [_note(60 + i, start=float(i)) for i in range(16)]
    out = extract_section_tail({"melody": notes}, sec, tail_beats=8.0)
    assert "melody" in out
    pitches = [n["pitch"] for n in out["melody"]]
    # Should include beats 8..15 (start_beat >= 8.0).
    assert pitches == [68, 69, 70, 71, 72, 73, 74, 75]


def test_tail_clips_to_section_start_when_section_shorter_than_tail():
    sec = {"name": "intro", "start_beat": 0.0, "end_beat": 4.0}
    notes = [_note(60 + i, start=float(i)) for i in range(4)]
    out = extract_section_tail({"melody": notes}, sec, tail_beats=8.0)
    # Only 4 beats of content, returns all of it.
    assert len(out["melody"]) == 4


def test_tail_skips_tracks_with_no_notes_in_section():
    sec = {"name": "verse", "start_beat": 8.0, "end_beat": 16.0}
    # Track A only plays in the first 8 beats (before the section).
    out = extract_section_tail(
        {"A": [_note(start=0.0), _note(start=4.0)]}, sec,
    )
    assert out == {}


def test_tail_returns_notes_sorted_by_beat():
    sec = {"name": "verse", "start_beat": 0.0, "end_beat": 16.0}
    # Unsorted input.
    notes = [
        _note(72, start=15.0), _note(60, start=8.0),
        _note(65, start=10.5),
    ]
    out = extract_section_tail({"melody": notes}, sec)
    beats = [n["start_beat"] for n in out["melody"]]
    assert beats == sorted(beats)


# ---------------------------------------------------------------------------
# format_section_tail_for_composer
# ---------------------------------------------------------------------------

def test_format_tail_empty_inputs():
    assert format_section_tail_for_composer({}, None) == ""
    assert format_section_tail_for_composer(
        {}, {"name": "verse", "end_beat": 16.0},
    ) == ""


def test_format_tail_renders_header_and_tracks():
    sec = {"name": "verse", "start_beat": 0.0, "end_beat": 16.0}
    tail = {
        "melody": [_note(67, start=12.0), _note(69, start=13.0)],
        "bass":   [_note(48, start=12.0)],
    }
    text = format_section_tail_for_composer(tail, sec)
    assert "PREVIOUS-SECTION TAIL" in text
    assert "[VERSE]" in text
    assert "melody:" in text and "G4" in text and "A4" in text
    assert "bass:" in text and "C3" in text


def test_format_tail_truncates_busy_track():
    sec = {"name": "verse", "start_beat": 0.0, "end_beat": 16.0}
    # 20 notes in the last 8 beats → only last 8 are shown, prefixed " … ".
    tail = {
        "hat": [_note(42, start=8.0 + i * 0.25) for i in range(20)],
    }
    text = format_section_tail_for_composer(
        tail, sec, max_notes_per_track=8,
    )
    assert "…" in text


def test_format_tail_header_mentions_tail_beats_constant():
    # Regression guard: format should show the tail-beats value used.
    sec = {"name": "verse", "start_beat": 0.0, "end_beat": 16.0}
    tail = {"melody": [_note(67, start=12.0)]}
    text = format_section_tail_for_composer(tail, sec)
    assert f"last {DEFAULT_TAIL_BEATS:.0f} beats" in text


# ---------------------------------------------------------------------------
# should_quote_hook
# ---------------------------------------------------------------------------

def test_should_quote_hook_verse_chorus_yes():
    assert should_quote_hook("verse")
    assert should_quote_hook("chorus")
    assert should_quote_hook("pre_chorus")


def test_should_quote_hook_intro_outro_bridge_no():
    # Bridge/intro/outro exist to contrast with the hook, so the
    # composer should be free to write new material there.
    assert should_quote_hook("intro") is False
    assert should_quote_hook("outro") is False
    assert should_quote_hook("bridge") is False


def test_should_quote_hook_case_insensitive():
    assert should_quote_hook("VERSE")
    assert should_quote_hook("Chorus")


def test_should_quote_hook_empty_returns_false():
    assert should_quote_hook("") is False


def test_hook_sections_set_has_documented_members():
    # These are the sections we PROMISED the composer would see the hook
    # in — regression guard against an accidental rename.
    assert "verse" in HOOK_SECTIONS
    assert "chorus" in HOOK_SECTIONS


# ---------------------------------------------------------------------------
# format_main_hook_for_composer
# ---------------------------------------------------------------------------

def test_format_hook_empty_inputs():
    assert format_main_hook_for_composer([], "verse") == ""
    assert format_main_hook_for_composer(None, "verse") == ""  # type: ignore


def test_format_hook_skipped_for_non_hook_section():
    hook = [
        ScoreNote(pitch=67, start_beat=0.0, duration_beats=1.0),
        ScoreNote(pitch=69, start_beat=1.0, duration_beats=1.0),
    ]
    # Intro/bridge/outro should NOT get the hook forced in.
    assert format_main_hook_for_composer(hook, "intro") == ""
    assert format_main_hook_for_composer(hook, "bridge") == ""
    assert format_main_hook_for_composer(hook, "outro") == ""


def test_format_hook_renders_verse():
    hook = [
        ScoreNote(pitch=67, start_beat=0.0, duration_beats=1.0),
        ScoreNote(pitch=69, start_beat=1.0, duration_beats=0.5),
        ScoreNote(pitch=72, start_beat=1.5, duration_beats=1.5),
    ]
    text = format_main_hook_for_composer(hook, "verse")
    assert "MAIN HOOK" in text
    # Pitches rendered as note names.
    assert "G4" in text and "A4" in text and "C5" in text


def test_format_hook_accepts_dict_form():
    hook_dicts = [
        {"pitch": 60, "start_beat": 0.0, "duration_beats": 1.0},
        {"pitch": 64, "start_beat": 1.0, "duration_beats": 1.0},
    ]
    text = format_main_hook_for_composer(hook_dicts, "chorus")
    assert "C4" in text and "E4" in text


def test_format_hook_skips_malformed_dict_items():
    hook_dicts = [
        {"pitch": 60, "start_beat": 0.0, "duration_beats": 1.0},
        {"pitch": "bad", "start_beat": 1.0, "duration_beats": 1.0},
        "not a dict",
    ]
    text = format_main_hook_for_composer(hook_dicts, "chorus")  # type: ignore
    assert "C4" in text
    # Malformed ones silently dropped.
    assert text.count("@") == 1

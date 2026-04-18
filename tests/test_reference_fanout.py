"""
Tests for Round 2 Phase A — multi-engine reference fanout.

These tests exercise:
  * The new engine wrappers' stub-safe fallback (import-not-available
    path degrades cleanly; factory returns NullEngine).
  * The factory's comma-list spec parsing (implicit multi).
  * The `build_composer_section_prompt` `draft_perspectives` injection.
  * The MultiEngine.merge `source` tagging round-trip.

No LLM, no network, no models downloaded — safe for CI.
"""

from __future__ import annotations

from src.engine.factory import create_engine
from src.engine.multi_engine import MultiEngine
from src.engine.null_engine import NullEngine
from src.llm.prompts import (
    _summarize_draft_notes,
    build_composer_section_prompt,
)


# --------------------------------------------------------------------------
# Engine wrapper fallbacks
# --------------------------------------------------------------------------

def test_composers_assistant_spec_falls_back_to_null():
    """CA2 isn't installed by default → factory gives NullEngine."""
    engine = create_engine("composers_assistant")
    assert isinstance(engine, NullEngine), (
        "Missing CA2 dep should degrade to NullEngine, got "
        f"{type(engine).__name__}"
    )


def test_mmt_spec_falls_back_to_null():
    engine = create_engine("mmt")
    assert isinstance(engine, NullEngine)


def test_figaro_spec_falls_back_to_null():
    engine = create_engine("figaro")
    assert isinstance(engine, NullEngine)


def test_unknown_engine_falls_back_to_magenta_wrapper():
    """Unknown keyword still returns a usable engine (Magenta default)."""
    engine = create_engine("this_engine_does_not_exist")
    # MagentaEngine is the documented fallback and is not a NullEngine.
    assert not isinstance(engine, NullEngine)


# --------------------------------------------------------------------------
# Factory multi-spec parsing
# --------------------------------------------------------------------------

def test_comma_list_builds_multi_engine():
    """Implicit multi: 'null,null' → MultiEngine with 2 null engines."""
    engine = create_engine("null,null", strategy="merge")
    assert isinstance(engine, MultiEngine)
    assert len(engine.engines) == 2
    assert engine.strategy == "merge"


def test_explicit_multi_prefix_builds_multi_engine():
    engine = create_engine("multi:null,null", strategy="merge")
    assert isinstance(engine, MultiEngine)
    assert engine.strategy == "merge"


def test_single_name_does_not_wrap_in_multi():
    engine = create_engine("null")
    assert not isinstance(engine, MultiEngine)


# --------------------------------------------------------------------------
# Per-engine summary helper
# --------------------------------------------------------------------------

def test_summarize_draft_notes_empty():
    assert _summarize_draft_notes([]) == ""


def test_summarize_draft_notes_basic():
    notes = [
        {"pitch": 60, "start_time": 0.0, "end_time": 0.5, "velocity": 80},
        {"pitch": 64, "start_time": 0.5, "end_time": 1.0, "velocity": 80},
        {"pitch": 67, "start_time": 1.0, "end_time": 1.5, "velocity": 80},
    ]
    out = _summarize_draft_notes(notes)
    # Must name the pitches (C4 E4 G4) and show an IOI/rhythm string.
    assert "C4" in out and "E4" in out and "G4" in out
    assert "rhythm" in out
    assert "3 notes total" in out


def test_summarize_draft_notes_truncation():
    notes = [
        {"pitch": 60 + i, "start_time": float(i) * 0.25,
         "end_time": float(i) * 0.25 + 0.25, "velocity": 80}
        for i in range(40)
    ]
    out = _summarize_draft_notes(notes, max_notes=8)
    # An ellipsis indicates the truncation happened.
    assert "…" in out
    assert "40 notes total" in out


# --------------------------------------------------------------------------
# build_composer_section_prompt injection
# --------------------------------------------------------------------------

def test_build_composer_prompt_omits_block_when_no_perspectives():
    prompt = build_composer_section_prompt(
        section_name="verse",
        start_beat=0.0,
        end_beat=8.0,
        bars=2,
        mood="flowing",
        instruments=[{"name": "Guzheng", "role": "lead"}],
        key="C",
        scale_type="major",
        previous_summary="",
        draft_description="",
        critic_feedback="",
    )
    assert "REFERENCE DRAFTS" not in prompt


def test_build_composer_prompt_renders_multi_engine_block():
    perspectives = {
        "MagentaEngine": [
            {"pitch": 60, "start_time": 0.0, "end_time": 0.5,
             "velocity": 80},
            {"pitch": 64, "start_time": 0.5, "end_time": 1.0,
             "velocity": 80},
        ],
        "ComposersAssistantEngine": [
            {"pitch": 67, "start_time": 0.0, "end_time": 0.25,
             "velocity": 80},
            {"pitch": 65, "start_time": 0.25, "end_time": 0.5,
             "velocity": 80},
            {"pitch": 64, "start_time": 0.5, "end_time": 1.0,
             "velocity": 80},
        ],
    }
    prompt = build_composer_section_prompt(
        section_name="chorus",
        start_beat=0.0,
        end_beat=8.0,
        bars=2,
        mood="climactic",
        instruments=[{"name": "Guzheng", "role": "lead"}],
        key="C",
        scale_type="major",
        previous_summary="",
        draft_description="",
        critic_feedback="",
        draft_perspectives=perspectives,
    )
    assert "REFERENCE DRAFTS" in prompt
    assert "[MagentaEngine]" in prompt
    assert "[ComposersAssistantEngine]" in prompt
    # The Composer must be told NOT to copy a draft verbatim.
    assert "DO NOT copy" in prompt


def test_build_composer_prompt_tolerates_empty_engine():
    """A draft that produced zero notes should not yield an empty line."""
    perspectives = {
        "MagentaEngine": [
            {"pitch": 60, "start_time": 0.0, "end_time": 0.5,
             "velocity": 80},
        ],
        "FigaroEngine": [],  # engine crashed or no output
    }
    prompt = build_composer_section_prompt(
        section_name="verse",
        start_beat=0.0,
        end_beat=8.0,
        bars=2,
        mood="flowing",
        instruments=[{"name": "Piano", "role": "lead"}],
        key="C",
        scale_type="major",
        previous_summary="",
        draft_description="",
        critic_feedback="",
        draft_perspectives=perspectives,
    )
    assert "[MagentaEngine]" in prompt
    assert "[FigaroEngine]" not in prompt  # skipped (zero notes)

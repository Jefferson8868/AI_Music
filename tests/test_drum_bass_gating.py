"""
Tests for Bug B fix — drum/bass token detection must use substring match.

Spotlight preset tokens like ``"drums"`` are resolved against the
blueprint's actual instrument names (e.g. ``"Cinematic Drums"``,
``"Synth Bass"``) by ``_match_instrument`` in spotlight_presets.py. That
means a SpotlightEntry's ``active`` list ends up holding the canonical
blueprint name, not the short preset token. The Phase 3.5 drum/bass
gating needs to recognize those canonical names — an exact-string check
against ``_DRUM_TOKENS = {"drums", "drum", ...}`` fails on
``"cinematic drums"`` and silently skips the DrumAgent entirely.

These tests cover the extracted ``match_drum_token`` / ``match_bass_token``
helpers in ``spotlight_review.py`` (reused by pipeline.py Phase 3.5).
"""

from __future__ import annotations

from src.agents.spotlight_review import (
    DRUM_TOKENS,
    BASS_TOKENS,
    match_bass_token,
    match_drum_token,
)


# ---------------------------------------------------------------------------
# Drum detection
# ---------------------------------------------------------------------------

def test_match_drum_token_exact():
    assert match_drum_token("drums") is True
    assert match_drum_token("drum") is True
    assert match_drum_token("percussion") is True


def test_match_drum_token_case_insensitive():
    assert match_drum_token("Drums") is True
    assert match_drum_token("PERCUSSION") is True


def test_match_drum_token_substring_cinematic_drums():
    """Regression for Bug B: ``Cinematic Drums`` must register as drums."""
    assert match_drum_token("Cinematic Drums") is True
    assert match_drum_token("cinematic drums") is True


def test_match_drum_token_substring_other_variants():
    assert match_drum_token("Pop Drum Kit") is True
    assert match_drum_token("Latin Percussion") is True
    assert match_drum_token("Trap Drums") is True


def test_match_drum_token_negatives():
    assert match_drum_token("Piano") is False
    assert match_drum_token("Erhu") is False
    assert match_drum_token("Synth Bass") is False
    assert match_drum_token("") is False


# ---------------------------------------------------------------------------
# Bass detection
# ---------------------------------------------------------------------------

def test_match_bass_token_exact():
    assert match_bass_token("bass") is True
    assert match_bass_token("electric bass") is True


def test_match_bass_token_substring_variants():
    """Regression for Bug B: multi-word bass names must register."""
    assert match_bass_token("Electric Bass") is True
    assert match_bass_token("Synth Bass") is True
    assert match_bass_token("Upright Bass") is True
    assert match_bass_token("Slap Bass") is True


def test_match_bass_token_negatives():
    # Don't confuse "bassoon" (a woodwind) with bass — exclude explicitly.
    assert match_bass_token("Bassoon") is False
    assert match_bass_token("Piano") is False
    assert match_bass_token("Drums") is False


# ---------------------------------------------------------------------------
# Token sets are the documented canonical lists.
# ---------------------------------------------------------------------------

def test_drum_tokens_set_has_expected_members():
    assert "drums" in DRUM_TOKENS
    assert "drum" in DRUM_TOKENS
    assert "percussion" in DRUM_TOKENS


def test_bass_tokens_set_has_expected_members():
    assert "bass" in BASS_TOKENS
    assert "electric bass" in BASS_TOKENS

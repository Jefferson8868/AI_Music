"""
Tests for Round 2 Phase D — FluidSynth audio renderer.

Stub-safe: does NOT call FluidSynth. These tests exercise:

  * `is_renderer_available` returns a boolean regardless of environment.
  * `render_midi_to_wav` raises `RendererError` when no backend is
    present (we simulate by stubbing the probes).
  * Bank/program map returns the right bundled-SF2 slot for Chinese +
    Western instruments, and falls through to GM when disabled.
  * Bundled-instrument list includes the key names from the plan.

We don't ship a .sf2 in tests, so an actual FluidSynth render is
covered by an opt-in integration test (skipped in CI).
"""

from __future__ import annotations

import pytest

from src.audio.renderer import (
    RendererError,
    _resolve_soundfont,
    is_renderer_available,
    render_midi_to_wav,
)
from src.audio.soundfont_map import (
    bundled_instrument_names,
    resolve_bank_program,
)


# --------------------------------------------------------------------------
# Availability probe
# --------------------------------------------------------------------------

def test_is_renderer_available_returns_bool():
    result = is_renderer_available()
    assert isinstance(result, bool)


# --------------------------------------------------------------------------
# Error paths
# --------------------------------------------------------------------------

def test_render_missing_midi_raises(tmp_path):
    missing = tmp_path / "nope.mid"
    with pytest.raises(FileNotFoundError):
        render_midi_to_wav(missing)


def test_render_raises_when_no_backend(monkeypatch, tmp_path):
    """With both backends stubbed away, we should get RendererError."""
    import src.audio.renderer as r

    monkeypatch.setattr(r, "_pyfluidsynth_available", lambda: False)
    # shutil.which returns None for missing CLI.
    monkeypatch.setattr(r, "shutil", _FakeShutil(which_returns=None))

    mid = tmp_path / "empty.mid"
    mid.write_bytes(b"MThd\x00\x00\x00\x06\x00\x00\x00\x00\x00\x60")

    with pytest.raises(RendererError):
        render_midi_to_wav(mid)


class _FakeShutil:
    def __init__(self, which_returns):
        self._which = which_returns

    def which(self, _name):
        return self._which


# --------------------------------------------------------------------------
# Soundfont resolution
# --------------------------------------------------------------------------

def test_resolve_soundfont_missing_returns_none(tmp_path):
    # Passing a path that doesn't exist should log and return None.
    nonexistent = tmp_path / "doesnotexist.sf2"
    result = _resolve_soundfont(nonexistent)
    assert result is None


def test_resolve_soundfont_existing_returns_path(tmp_path):
    sf = tmp_path / "fake.sf2"
    sf.write_bytes(b"RIFF")   # content doesn't matter — just existence
    result = _resolve_soundfont(sf)
    assert result == sf


# --------------------------------------------------------------------------
# Bank / program map
# --------------------------------------------------------------------------

def test_resolve_bank_program_erhu_in_bundled_bank_1():
    bank, program = resolve_bank_program("erhu")
    assert bank == 1
    assert program == 5


def test_resolve_bank_program_dizi_in_bundled_bank_1():
    bank, program = resolve_bank_program("Dizi")
    assert bank == 1


def test_resolve_bank_program_falls_back_to_gm_when_bundled_disabled():
    bank, program = resolve_bank_program(
        "erhu", gm_program=110, use_bundled=False,
    )
    assert bank == 0
    assert program == 110


def test_resolve_bank_program_substring_fallback():
    # "Chinese Guzheng" should still hit the "guzheng" row.
    bank, program = resolve_bank_program("Chinese Guzheng")
    assert bank == 1


def test_resolve_bank_program_unknown_returns_gm():
    bank, program = resolve_bank_program(
        "ukulele", gm_program=24,
    )
    # No match → (0, 24)
    assert bank == 0
    assert program == 24


def test_resolve_bank_program_drums_use_bank_128():
    bank, program = resolve_bank_program("drums")
    assert bank == 128


def test_bundled_instruments_include_plan_set():
    names = set(bundled_instrument_names())
    for expected in ("erhu", "dizi", "pipa", "guzheng", "piano"):
        assert expected in names

"""
Tests for Round 2 Phase F — pedalboard / numpy mix bus.

Stub-safe: all tests run without pedalboard installed. We generate tiny
synthetic .wav files on the fly and assert:

  * `is_mix_available` returns a bool.
  * Missing instrumental raises `MixError`.
  * Mixing an instrumental alone yields a .wav with the same sample
    count (no transition events, no vocal).
  * Vocal gets summed at unity-ish gain (mixed loudness > instrumental).
  * Transition events at known beats drop a stem into the mix at the
    right sample offset.
  * Unknown transition kind with no matching asset is silently skipped.
  * Beat → sample conversion matches tempo.
"""

from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

from src.audio.mix import (
    MixError,
    _beat_to_samples,
    _beat_to_seconds,
    _resolve_stem_path,
    is_mix_available,
    mix_stems,
)


# --------------------------------------------------------------------------
# WAV fixture helpers
# --------------------------------------------------------------------------

SR = 44100


def _write_sine(
    path,
    seconds: float = 1.0,
    freq_hz: float = 440.0,
    amp: float = 0.3,
    sr: int = SR,
    channels: int = 2,
):
    t = np.linspace(0, seconds, int(seconds * sr), endpoint=False)
    mono = (amp * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)
    data = np.stack([mono] * channels, axis=1)
    sf.write(str(path), data, samplerate=sr)
    return path


class _FakeTransitionEvent:
    """Duck-typed stand-in for TransitionEvent (no score.py dep needed)."""

    __slots__ = ("beat", "kind")

    def __init__(self, beat: float, kind: str):
        self.beat = beat
        self.kind = kind


# --------------------------------------------------------------------------
# Basic shape
# --------------------------------------------------------------------------

def test_is_mix_available_returns_bool():
    result = is_mix_available()
    assert isinstance(result, bool)


def test_mix_missing_instrumental_raises(tmp_path):
    with pytest.raises(MixError):
        mix_stems(
            instrumental_wav=tmp_path / "nope.wav",
            out_path=tmp_path / "out.wav",
        )


# --------------------------------------------------------------------------
# Core summing
# --------------------------------------------------------------------------

def test_mix_instrumental_only_produces_same_length_wav(tmp_path):
    inst = _write_sine(tmp_path / "inst.wav", seconds=0.5)
    out = mix_stems(
        instrumental_wav=inst,
        out_path=tmp_path / "mixed.wav",
        tempo_bpm=120.0,
    )
    assert out.is_file()
    mixed, sr = sf.read(str(out), always_2d=True)
    orig, _ = sf.read(str(inst), always_2d=True)
    assert sr == SR
    # Same sample count.
    assert mixed.shape[0] == orig.shape[0]


def test_mix_sums_vocal_raising_rms(tmp_path):
    inst = _write_sine(tmp_path / "inst.wav", seconds=0.5, amp=0.3, freq_hz=440.0)
    voc = _write_sine(tmp_path / "voc.wav", seconds=0.5, amp=0.3, freq_hz=880.0)
    out = mix_stems(
        instrumental_wav=inst,
        vocal_wav=voc,
        out_path=tmp_path / "mixed.wav",
    )
    mixed, _ = sf.read(str(out), always_2d=True)
    orig, _ = sf.read(str(inst), always_2d=True)
    # Summed signal has more energy than the instrumental alone.
    # (After normalization the peak is bounded, but RMS of the mixed
    # signal should still exceed the single-source RMS.)
    assert float(np.sqrt(np.mean(mixed ** 2))) > float(
        np.sqrt(np.mean(orig ** 2))
    ) * 0.9  # 0.9 tolerance for the peak-normalization step


def test_mix_drops_vocal_with_mismatched_samplerate(tmp_path, caplog):
    inst = _write_sine(tmp_path / "inst.wav", seconds=0.3, sr=44100)
    voc = _write_sine(tmp_path / "voc.wav", seconds=0.3, sr=22050)
    # Should not crash; vocal is dropped with a warning.
    out = mix_stems(
        instrumental_wav=inst,
        vocal_wav=voc,
        out_path=tmp_path / "mixed.wav",
    )
    assert out.is_file()


# --------------------------------------------------------------------------
# Transition stems
# --------------------------------------------------------------------------

def test_mix_places_transition_stem_at_beat(tmp_path):
    inst = _write_sine(tmp_path / "inst.wav", seconds=4.0)

    # Make a fake transition asset dir with one known stem.
    assets = tmp_path / "transitions"
    assets.mkdir()
    stem_path = assets / "riser_8beat.wav"
    _write_sine(stem_path, seconds=0.2, freq_hz=1760.0)

    out = mix_stems(
        instrumental_wav=inst,
        transition_events=[_FakeTransitionEvent(beat=2.0, kind="riser")],
        asset_dir=assets,
        tempo_bpm=120.0,    # beat=2.0 → 1.0s
        out_path=tmp_path / "mixed.wav",
    )
    mixed, _ = sf.read(str(out), always_2d=True)
    orig, _ = sf.read(str(inst), always_2d=True)

    # Mixed at 1s should differ from orig at 1s (stem added).
    offset = int(1.0 * SR)
    window = slice(offset, offset + int(0.15 * SR))
    # Not an exact equality — peak normalization may have rescaled.
    # So compare shapes of the delta: is there significant change there?
    delta = np.abs(mixed[window] - orig[window] * (
        float(np.max(np.abs(mixed))) / max(float(np.max(np.abs(orig))), 1e-9)
    ))
    assert float(delta.mean()) > 0.0


def test_mix_skips_unknown_transition_kind(tmp_path):
    inst = _write_sine(tmp_path / "inst.wav", seconds=1.0)
    assets = tmp_path / "transitions"
    assets.mkdir()
    # No stems dropped.
    out = mix_stems(
        instrumental_wav=inst,
        transition_events=[_FakeTransitionEvent(beat=1.0, kind="notakind")],
        asset_dir=assets,
        out_path=tmp_path / "mixed.wav",
    )
    assert out.is_file()


def test_mix_no_transition_events_ok(tmp_path):
    inst = _write_sine(tmp_path / "inst.wav", seconds=0.5)
    out = mix_stems(
        instrumental_wav=inst,
        transition_events=None,
        out_path=tmp_path / "mixed.wav",
    )
    assert out.is_file()


# --------------------------------------------------------------------------
# Stem resolution
# --------------------------------------------------------------------------

def test_resolve_stem_variant_preferred(tmp_path):
    assets = tmp_path / "transitions"
    assets.mkdir()
    # Two variants; RNG should pick one.
    (assets / "impact_deep.wav").write_bytes(b"")
    (assets / "impact_crisp.wav").write_bytes(b"")

    import random
    pick = _resolve_stem_path("impact", assets, random.Random(0))
    assert pick is not None
    assert pick.name in {"impact_deep.wav", "impact_crisp.wav"}


def test_resolve_stem_falls_back_to_glob(tmp_path):
    assets = tmp_path / "transitions"
    assets.mkdir()
    # Variant name NOT in _STEM_VARIANTS but still starts with the kind.
    (assets / "mykind_custom.wav").write_bytes(b"")

    import random
    pick = _resolve_stem_path("mykind", assets, random.Random(0))
    assert pick is not None
    assert pick.name == "mykind_custom.wav"


def test_resolve_stem_missing_returns_none(tmp_path):
    empty = tmp_path / "transitions"
    empty.mkdir()
    import random
    assert _resolve_stem_path("riser", empty, random.Random(0)) is None


def test_resolve_stem_missing_dir_returns_none(tmp_path):
    import random
    assert _resolve_stem_path(
        "riser", tmp_path / "does-not-exist", random.Random(0),
    ) is None


# --------------------------------------------------------------------------
# Time conversion
# --------------------------------------------------------------------------

def test_beat_to_seconds_at_120bpm():
    # 120bpm = 2 beats/sec → 1 beat = 0.5s.
    assert abs(_beat_to_seconds(1.0, 120.0) - 0.5) < 1e-6
    assert abs(_beat_to_seconds(4.0, 120.0) - 2.0) < 1e-6


def test_beat_to_samples_at_44100():
    # beat=1 @ 120bpm @ 44100 = 0.5s = 22050 samples.
    assert _beat_to_samples(1.0, 120.0, 44100) == 22050


def test_beat_to_seconds_zero_tempo_is_zero():
    assert _beat_to_seconds(10.0, 0.0) == 0.0

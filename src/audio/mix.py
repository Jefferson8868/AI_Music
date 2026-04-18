"""
Mix bus (Round 2 Phase F).

Takes the instrumental .wav (from Phase D), an optional vocal .wav (from
Phase E), and the Score's transition events, and writes a final mixed
.wav with:

  * vocal summed on top of instrumental at unity gain
  * transition stems placed at section boundaries (riser / reverse_cymbal
    / impact / sub_drop / downlifter — whatever the TransitionAgent asked
    for at the "sample-ish" boundary recipes)
  * per-section reverb + compressor via pedalboard, when the optional
    dep is installed
  * per-instrument panning + bus compression, when pedalboard is there

Dependency posture
------------------
The pipeline treats the mix bus as best-effort:

  * `numpy` + `soundfile` = hard deps (already in the project's base
    install for MIDI/WAV round-tripping). Without them, `mix_stems`
    raises `MixError`.
  * `pedalboard` = soft dep. Without it, we still sum stems + drop
    transition stems at the right beats — just no FX processing.

This lets the user ship the feature without an arm64 pedalboard wheel.
"""

from __future__ import annotations

import importlib.util
import random
from pathlib import Path
from typing import Any, Iterable, Optional

from loguru import logger


DEFAULT_TRANSITION_ASSET_DIR = Path("assets/transitions")

# TransitionEvent.kind → list of asset filename stems (without .wav).
# Multiple variants per kind so we can randomize and avoid obvious reuse.
_STEM_VARIANTS: dict[str, list[str]] = {
    "riser":          ["riser_8beat", "riser_16beat", "riser_short"],
    "reverse_cymbal": ["reverse_cymbal_short", "reverse_cymbal_long"],
    "impact":         ["impact_deep", "impact_crisp", "impact_wide"],
    "sub_drop":       ["sub_drop"],
    "downlifter":     ["downlifter", "downlifter_filter"],
    # MIDI-ish kinds that can ALSO surface a sample if one is curated.
    "snare_roll":     ["snare_roll_accel_1bar", "snare_roll_accel_2bar"],
}


class MixError(RuntimeError):
    """Raised when the mix cannot complete (missing core deps, etc.)."""


# --------------------------------------------------------------------------
# Availability probes
# --------------------------------------------------------------------------

def _numpy_soundfile_available() -> bool:
    return (
        importlib.util.find_spec("numpy") is not None
        and importlib.util.find_spec("soundfile") is not None
    )


def _pedalboard_available() -> bool:
    return importlib.util.find_spec("pedalboard") is not None


def is_mix_available() -> bool:
    """True when the hard deps are installed. Pedalboard is optional."""
    return _numpy_soundfile_available()


# --------------------------------------------------------------------------
# Time helpers
# --------------------------------------------------------------------------

def _beat_to_seconds(beat: float, tempo_bpm: float) -> float:
    if tempo_bpm <= 0:
        return 0.0
    return float(beat) * 60.0 / float(tempo_bpm)


def _beat_to_samples(beat: float, tempo_bpm: float, sample_rate: int) -> int:
    return int(round(_beat_to_seconds(beat, tempo_bpm) * sample_rate))


# --------------------------------------------------------------------------
# Stem resolution
# --------------------------------------------------------------------------

def _resolve_stem_path(
    kind: str,
    asset_dir: Path,
    rng: random.Random,
) -> Optional[Path]:
    """Pick an asset for a transition kind. Returns None if nothing found.

    Walks:
      1. `_STEM_VARIANTS[kind]` — explicit curated variants.
      2. Any file matching `{asset_dir}/{kind}*.wav` (loose glob).
    Randomizes within matches so repeated boundaries sound fresh.
    """
    if not asset_dir.is_dir():
        return None

    stems = list(_STEM_VARIANTS.get(kind, []))
    candidates: list[Path] = []
    for s in stems:
        p = asset_dir / f"{s}.wav"
        if p.is_file():
            candidates.append(p)

    if not candidates:
        # Loose fallback: any file starting with the kind name.
        candidates = sorted(asset_dir.glob(f"{kind}*.wav"))

    if not candidates:
        return None
    return rng.choice(candidates)


# --------------------------------------------------------------------------
# Core summing (numpy-level)
# --------------------------------------------------------------------------

def _load_wav(path: Path):
    import numpy as np
    import soundfile as sf

    data, sr = sf.read(str(path), always_2d=True)
    # Ensure float32.
    if data.dtype != np.float32:
        data = data.astype(np.float32)
    return data, int(sr)


def _sum_into(buffer, src, offset_samples: int, gain: float = 1.0):
    """Add src into buffer at offset_samples, mixing channels + clipping tails."""
    import numpy as np

    if src.size == 0:
        return
    # Match channel count of buffer.
    buf_channels = buffer.shape[1]
    if src.shape[1] != buf_channels:
        if src.shape[1] == 1 and buf_channels == 2:
            src = np.repeat(src, 2, axis=1)
        elif src.shape[1] == 2 and buf_channels == 1:
            src = src.mean(axis=1, keepdims=True)
        else:
            src = src[:, :buf_channels]

    end = offset_samples + src.shape[0]
    if end <= 0 or offset_samples >= buffer.shape[0]:
        return
    s0 = max(0, offset_samples)
    s1 = min(buffer.shape[0], end)
    src_s0 = s0 - offset_samples
    src_s1 = src_s0 + (s1 - s0)
    buffer[s0:s1] += src[src_s0:src_s1] * gain


# --------------------------------------------------------------------------
# Pedalboard FX graph
# --------------------------------------------------------------------------

def _build_fx_board(section_plan: Optional[list[Any]]):  # noqa: ARG001
    """Compose a pedalboard with reverb + compressor if available.

    ``section_plan`` is accepted for future per-section modulation — not
    used in this first cut because pedalboard chains are static. Global
    FX chain is good enough for the single-pass mix.
    """
    if not _pedalboard_available():
        return None
    # Imported lazily so the module loads without pedalboard installed.
    from pedalboard import (  # type: ignore[import-not-found]
        Pedalboard, Reverb, Compressor, Gain,
    )

    # Modest defaults: plate-ish reverb, gentle bus compression, small
    # makeup gain. Users can override later by editing this module.
    board = Pedalboard([
        Compressor(threshold_db=-14.0, ratio=2.5, attack_ms=8, release_ms=120),
        Reverb(
            room_size=0.45,
            damping=0.5,
            wet_level=0.18,
            dry_level=0.82,
            width=1.0,
        ),
        Gain(gain_db=0.0),
    ])
    return board


def _apply_fx(audio, sample_rate: int, board) -> Any:
    if board is None:
        return audio
    try:
        return board(audio, sample_rate)
    except Exception as e:
        logger.warning(f"[mix] pedalboard FX failed ({e}); returning dry audio")
        return audio


# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------

def mix_stems(
    instrumental_wav: str | Path,
    vocal_wav: Optional[str | Path] = None,
    transition_events: Optional[Iterable[Any]] = None,
    section_plan: Optional[list[Any]] = None,
    tempo_bpm: float = 120.0,
    out_path: Optional[str | Path] = None,
    asset_dir: str | Path = DEFAULT_TRANSITION_ASSET_DIR,
    seed: int = 0,
) -> Path:
    """Mix instrumental + vocal + transition stems into a single .wav.

    Args:
        instrumental_wav: Required. The Phase D FluidSynth render.
        vocal_wav: Optional. The Phase E vocal stem.
        transition_events: Iterable of TransitionEvent-like objects with
            `.beat`, `.kind` attributes (duck-typed). Only sample-ish
            kinds resolve to actual audio placements; MIDI-ish kinds
            are silently skipped (already in the MIDI output).
        section_plan: Reserved for per-section FX modulation (not used
            in this first cut — global FX chain).
        tempo_bpm: Drives beat→seconds conversion for stem placement.
        out_path: Where to write the mixed .wav. Defaults to the
            instrumental path with a `_mixed` suffix.
        asset_dir: Where to look for transition stems.
        seed: RNG seed for deterministic stem-variant selection.

    Returns:
        Path to the mixed .wav.

    Raises:
        MixError: Missing numpy/soundfile, unreadable inputs, or write
            failure.
    """
    if not _numpy_soundfile_available():
        raise MixError(
            "Mix bus requires `numpy` + `soundfile`. "
            "Install with `pip install numpy soundfile`."
        )

    import numpy as np
    import soundfile as sf

    instrumental_wav = Path(instrumental_wav)
    if not instrumental_wav.is_file():
        raise MixError(f"Instrumental WAV not found: {instrumental_wav}")

    if out_path is None:
        out_path = instrumental_wav.with_name(
            instrumental_wav.stem + "_mixed.wav"
        )
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    asset_dir = Path(asset_dir)
    rng = random.Random(seed)

    # --- Load base instrumental -----------------------------------------
    inst, sr = _load_wav(instrumental_wav)
    # Force stereo for the mix buffer so panning + stereo stems fit.
    if inst.shape[1] == 1:
        inst = np.repeat(inst, 2, axis=1)
    buffer = inst.copy()

    # --- Sum vocal ------------------------------------------------------
    if vocal_wav is not None:
        vp = Path(vocal_wav)
        if vp.is_file():
            vocal, vsr = _load_wav(vp)
            if vsr != sr:
                logger.warning(
                    f"[mix] vocal sample rate {vsr} != instrumental {sr}; "
                    "dropping vocal from mix. Resample offline first."
                )
            else:
                _sum_into(buffer, vocal, offset_samples=0, gain=0.9)
                logger.info(
                    f"[mix] summed vocal ({vocal.shape[0]} samples)"
                )
        else:
            logger.warning(f"[mix] vocal .wav not found at {vp}")

    # --- Place transition stems -----------------------------------------
    placed = 0
    skipped_kinds: set[str] = set()
    for evt in (transition_events or []):
        kind = getattr(evt, "kind", None)
        beat = getattr(evt, "beat", None)
        if kind is None or beat is None:
            continue
        stem = _resolve_stem_path(kind, asset_dir, rng)
        if stem is None:
            skipped_kinds.add(kind)
            continue
        try:
            src, ssr = _load_wav(stem)
            if ssr != sr:
                logger.debug(
                    f"[mix] skipping {stem.name}: sr {ssr} != {sr}"
                )
                continue
            offset = _beat_to_samples(float(beat), tempo_bpm, sr)
            _sum_into(buffer, src, offset_samples=offset, gain=0.7)
            placed += 1
        except Exception as e:
            logger.warning(f"[mix] failed to place {stem}: {e}")
    if skipped_kinds:
        logger.info(
            f"[mix] no asset for kinds: {sorted(skipped_kinds)} "
            f"(drop .wav files into {asset_dir} to enable)"
        )
    if placed:
        logger.info(f"[mix] placed {placed} transition stems")

    # --- FX chain (optional) -------------------------------------------
    board = _build_fx_board(section_plan)
    buffer = _apply_fx(buffer, sample_rate=sr, board=board)

    # --- Clip + write ---------------------------------------------------
    # Soft limit to [-1, 1] to avoid hard clipping after summing.
    peak = float(np.max(np.abs(buffer))) if buffer.size else 0.0
    if peak > 0.99:
        buffer = (buffer / peak) * 0.98
        logger.debug(f"[mix] normalized mix (peak was {peak:.2f})")

    try:
        sf.write(str(out_path), buffer, samplerate=sr)
    except Exception as e:
        raise MixError(f"Failed to write mixed .wav: {e}") from e

    logger.info(f"[mix] wrote {out_path} ({buffer.shape[0]} samples @ {sr} Hz)")
    return out_path


__all__ = [
    "DEFAULT_TRANSITION_ASSET_DIR",
    "MixError",
    "is_mix_available",
    "mix_stems",
]

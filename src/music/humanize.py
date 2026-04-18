"""
MIDI humanizer — Round 2 Phase C1.

Takes a rendered Score and applies per-instrument micro-variation so
the output sounds like a real player, not a sequencer. Runs AFTER
ornament expansion (`apply_performance_render`) but BEFORE the MIDI
writer.

Four passes (all deterministic given a seed):

  1. Velocity jitter   — ±N% per note, N from performance_recipes.
  2. Micro-timing      — correlated random walk in beat offsets,
                         plus per-voice offsets (snare lays back,
                         hats push early).
  3. Tempo breathing   — phrase-level ±1-3% BPM at phrase boundaries.
                         Emitted as CC events (target = tempo meta),
                         actually applied by the MIDI writer.
  4. Fake round-robin  — consecutive same-pitch notes get ±10 cents
                         pitch bend + ±2 dB velocity variance.

Idempotency
-----------
Each ScoreTrack carries a `humanized: bool` flag (Round 2 extension).
A second call is a no-op so the pipeline can safely re-invoke this
without doubling the jitter.

Design invariants
-----------------
- Never mutates the input Score. Always returns a new one.
- A seed parameter makes runs reproducible in tests.
- All drum tracks use the `drums` recipe regardless of their
  pitch-level GM note (kick=36, snare=38, etc.).
- Notes retain their original beat order — we only shift within a
  bounded window.
"""

from __future__ import annotations

import math
import random

from loguru import logger

from src.music.score import CCEvent, Score, ScoreTrack


# --------------------------------------------------------------------------
# Per-instrument default jitter budgets (fraction of velocity / beat)
# --------------------------------------------------------------------------

# Fallbacks used when an instrument's card doesn't set a value.
_DEFAULT_VEL_JITTER_PCT = {
    "drums": 0.15,       # 15% velocity swing
    "piano": 0.07,
    "strings": 0.04,
    "bass": 0.05,
    "erhu": 0.05,
    "dizi": 0.06,
    "guzheng": 0.06,
    "pipa": 0.06,
    "pad": 0.03,
    "cello": 0.04,
    "violin": 0.04,
    "flute": 0.05,
}
_FALLBACK_VEL_JITTER = 0.05

# Micro-timing: max beats of random walk step per note (approx ±20ms at
# 100 BPM = 0.033 beat).
_DEFAULT_TIME_JITTER_BEATS = {
    "drums": 0.025,
    "piano": 0.010,
    "strings": 0.015,
    "bass": 0.015,
    "erhu": 0.020,
    "dizi": 0.020,
    "guzheng": 0.015,
    "pipa": 0.015,
    "pad": 0.005,
    "cello": 0.015,
    "violin": 0.015,
    "flute": 0.020,
}
_FALLBACK_TIME_JITTER = 0.010

# Per-voice drum offsets (milliseconds). Applied on top of the per-note
# jitter. Positive = later. Matches GrooveTemplate.microtiming defaults.
_DRUM_VOICE_OFFSETS_MS: dict[str, int] = {
    "kick": 0,
    "snare": +7,    # laid-back
    "chh": -3,      # pushed
    "ohh": -3,
    "ride": -2,
    "crash": 0,
    "perc": +2,
}

# How close in beats counts as a "phrase boundary" (gap triggers a new
# tempo-breathing segment).
_PHRASE_GAP_BEATS = 1.0

# Tempo-breathing amplitude (fraction of base BPM).
_TEMPO_BREATH_AMPLITUDE = 0.015  # ±1.5%

# Round-robin threshold: same pitch within this many beats → apply
# detune + velocity variance.
_ROUND_ROBIN_WINDOW_BEATS = 2.0
# Cents → 14-bit pitch-wheel (assuming ±200-cent bend range).
_CENTS_PER_BEND_UNIT = 200.0 / 8191.0


# --------------------------------------------------------------------------
# Public entry points
# --------------------------------------------------------------------------

def humanize_score(
    score: Score,
    *,
    seed: int | None = 0,
) -> Score:
    """Apply humanization to every un-humanized track. Returns new Score."""
    if seed is None:
        rng = random.Random()
    else:
        rng = random.Random(seed)

    new_score = score.model_copy(deep=True)
    new_tracks: list[ScoreTrack] = []
    touched = 0
    for trk in new_score.tracks:
        if trk.humanized:
            new_tracks.append(trk)
            continue
        humanized = _humanize_track(
            trk, tempo_bpm=new_score.tempo, rng=rng,
        )
        humanized.humanized = True
        new_tracks.append(humanized)
        touched += 1
    new_score.tracks = new_tracks
    logger.info(
        f"[humanize] applied to {touched}/{len(new_score.tracks)} "
        f"track(s); seed={seed}"
    )
    return new_score


def humanize_track(
    track: ScoreTrack,
    *,
    tempo_bpm: float = 120.0,
    seed: int | None = 0,
) -> ScoreTrack:
    """Single-track entry point for tests."""
    rng = random.Random(seed) if seed is not None else random.Random()
    result = _humanize_track(track, tempo_bpm=tempo_bpm, rng=rng)
    result.humanized = True
    return result


# --------------------------------------------------------------------------
# Per-track pipeline
# --------------------------------------------------------------------------

def _humanize_track(
    track: ScoreTrack,
    *,
    tempo_bpm: float,
    rng: random.Random,
) -> ScoreTrack:
    new = track.model_copy(deep=True)
    if not new.notes:
        return new

    inst_key = _instrument_key(new.instrument, new.role, new.name)

    # 1. Velocity jitter.
    _apply_velocity_jitter(new, inst_key, rng)

    # 2. Micro-timing (per-voice offsets for drums + random walk).
    _apply_micro_timing(new, inst_key, tempo_bpm, rng)

    # 3. Round-robin detune on same-pitch consecutive notes.
    _apply_round_robin(new, rng)

    # 4. Phrase-level tempo breathing (CC events; reader interprets).
    _apply_tempo_breathing(new, tempo_bpm, rng)

    # Re-sort notes; micro-timing may have re-ordered near-simultaneous.
    new.notes.sort(key=lambda n: (n.start_beat, n.pitch))
    return new


# --------------------------------------------------------------------------
# Pass 1 — Velocity jitter
# --------------------------------------------------------------------------

def _apply_velocity_jitter(
    track: ScoreTrack, inst_key: str, rng: random.Random,
) -> None:
    pct = _DEFAULT_VEL_JITTER_PCT.get(inst_key, _FALLBACK_VEL_JITTER)
    for n in track.notes:
        # Random uniform in [-pct, +pct] scaled to velocity.
        swing = rng.uniform(-pct, pct)
        new_vel = int(round(n.velocity * (1.0 + swing)))
        n.velocity = max(1, min(127, new_vel))


# --------------------------------------------------------------------------
# Pass 2 — Micro-timing
# --------------------------------------------------------------------------

def _apply_micro_timing(
    track: ScoreTrack,
    inst_key: str,
    tempo_bpm: float,
    rng: random.Random,
) -> None:
    max_step = _DEFAULT_TIME_JITTER_BEATS.get(
        inst_key, _FALLBACK_TIME_JITTER,
    )

    # Per-voice drum offset in beats (ms → beat).
    drum_offset_beats = 0.0
    if inst_key == "drums":
        voice = _classify_drum_voice(track.name)
        ms = _DRUM_VOICE_OFFSETS_MS.get(voice, 0)
        drum_offset_beats = ms * (tempo_bpm / 60_000.0)

    walk = 0.0
    for n in track.notes:
        # Gaussian-ish step so the walk wanders slowly rather than
        # snapping between extremes.
        step = rng.gauss(0.0, max_step * 0.5)
        # Clamp cumulative walk to ±max_step so we don't drift off-grid.
        walk = max(-max_step, min(max_step, walk + step))
        shift = walk + drum_offset_beats
        # Never move the downbeat below 0 — keep the piece starting on 1.
        n.start_beat = max(0.0, round(n.start_beat + shift, 4))


# --------------------------------------------------------------------------
# Pass 3 — Round-robin detune
# --------------------------------------------------------------------------

def _apply_round_robin(
    track: ScoreTrack, rng: random.Random,
) -> None:
    if len(track.notes) < 2:
        return
    sorted_notes = sorted(track.notes, key=lambda n: n.start_beat)
    last_by_pitch: dict[int, float] = {}
    for n in sorted_notes:
        prev = last_by_pitch.get(n.pitch)
        if prev is not None:
            gap = n.start_beat - prev
            if 0 < gap <= _ROUND_ROBIN_WINDOW_BEATS:
                # ±10 cents detune via pitch-bend.
                cents = rng.uniform(-10.0, 10.0)
                bend = int(round(cents / _CENTS_PER_BEND_UNIT))
                track.pitch_bends.append(__pb(
                    beat=n.start_beat,
                    value=max(-8192, min(8191, bend)),
                    channel=track.channel,
                ))
                # ±2 dB velocity variance (approx ±12 MIDI steps).
                delta = int(round(rng.uniform(-6.0, 6.0)))
                n.velocity = max(1, min(127, n.velocity + delta))
        last_by_pitch[n.pitch] = n.start_beat


def __pb(*, beat: float, value: int, channel: int):
    """Construct a PitchBendEvent lazily to avoid circular import."""
    from src.music.score import PitchBendEvent
    return PitchBendEvent(beat=beat, value=value, channel=channel)


# --------------------------------------------------------------------------
# Pass 4 — Tempo breathing
# --------------------------------------------------------------------------

def _apply_tempo_breathing(
    track: ScoreTrack,
    tempo_bpm: float,    # noqa: ARG001 — reserved for future CC→tempo-meta translation
    rng: random.Random,
) -> None:
    """Emit CC events at phrase boundaries representing tempo breath.

    The MIDI writer is free to translate these into tempo-meta
    messages (CC=0x7F reserved) or ignore them. For now we use CC11
    (expression) as an approximation for players that ignore tempo
    automation — expression scales volume, which gives a similar
    "breath" effect on MIDI sample players.
    """
    if not track.notes:
        return
    prev_end = track.notes[0].start_beat
    segments: list[tuple[float, float]] = []  # (start, end)
    seg_start = prev_end
    for n in track.notes[1:]:
        gap = n.start_beat - prev_end
        if gap >= _PHRASE_GAP_BEATS:
            # Close the previous segment.
            segments.append((seg_start, prev_end))
            seg_start = n.start_beat
        prev_end = n.start_beat + n.duration_beats
    segments.append((seg_start, prev_end))

    for start, end in segments:
        if end <= start:
            continue
        # Random ±amplitude for this phrase.
        breath = rng.uniform(
            -_TEMPO_BREATH_AMPLITUDE, _TEMPO_BREATH_AMPLITUDE,
        )
        # 5 points over the phrase so the MIDI writer can interpolate.
        steps = 5
        mid_vol = 90
        range_vol = 20
        for i in range(steps):
            t = i / max(1, steps - 1)
            # Sinusoidal curve from 0 → peak → 0 over the phrase.
            shape = math.sin(math.pi * t)
            delta = int(round(breath * range_vol * shape * 10))
            val = max(1, min(127, mid_vol + delta))
            track.cc_events.append(CCEvent(
                beat=round(start + t * (end - start), 4),
                controller=11,       # Expression
                value=val,
                channel=track.channel,
            ))


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _instrument_key(instrument: str, role: str, name: str) -> str:
    """Map a track's instrument/role/name to a jitter-budget key."""
    s = f"{instrument} {role} {name}".lower()
    # Order matters — drums / bass first, then specific instruments.
    for key in ("drums", "bass", "piano", "erhu", "dizi", "guzheng",
                "pipa", "pad", "cello", "violin", "flute", "strings"):
        if key in s:
            return key
    return "default"


def _classify_drum_voice(track_name: str) -> str:
    """'drums_kick' → 'kick', 'drums_snare' → 'snare', etc."""
    low = track_name.lower()
    for voice in ("kick", "snare", "chh", "ohh", "ride", "crash", "perc"):
        if voice in low:
            return voice
    return "perc"


# Re-exports kept tight.
__all__ = [
    "humanize_score",
    "humanize_track",
]

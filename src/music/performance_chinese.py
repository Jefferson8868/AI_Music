"""
Chinese-instrument performance realism — Round 2 Phase C2.

Specialised post-processor that runs AFTER ornament expansion but
before (or alongside) the generic humanizer, for tracks whose
instrument is in the Chinese-traditional family. These idioms are
*expected* in 国风 / fusion pop and without them traditional
instruments sound like synth pads:

- **Delayed vibrato** (erhu, dizi): on long sustained notes the
  vibrato LFO does NOT start at the note onset — real players let
  the note settle for ~400ms, then bring in vibrato.
- **Portamento between same-phrase notes** (erhu especially): pitch
  slides smoothly rather than stepping.
- **Breath-noise spikes on dizi attacks**: CC2 (breath controller)
  rises to a small peak over the first 60ms of each note and falls
  back — simulates the flutist's initial airflow.
- **Bow-articulation accent on erhu phrase starts**: +8 velocity on
  the first note after a ≥0.5-beat rest.

Design notes
------------
- Independent module; callers can selectively apply it.
- Mutates the passed Score in place (the higher-level pipeline
  calls `.model_copy(deep=True)` first).
- Skips tracks whose `humanized` OR `rendered` flags indicate they
  were already processed — but the Chinese pass is additive, so a
  track may still benefit from it after generic humanization.
- All timings are in beats, converted from ms via `tempo_bpm`.
"""

from __future__ import annotations

import math

from loguru import logger

from src.music.score import CCEvent, PitchBendEvent, Score, ScoreTrack


# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

CHINESE_INSTRUMENTS = {
    "erhu", "dizi", "guzheng", "pipa", "suona",
    "xiao", "yangqin", "ruan",
}

# Vibrato onset delay in ms (empirically ~400ms for erhu, dizi).
VIBRATO_DELAY_MS = 400

# Vibrato LFO shape.
VIBRATO_RATE_HZ = 5.5
VIBRATO_DEPTH_CC = 50   # CC1 depth in 0-127
VIBRATO_SAMPLES_PER_BEAT = 12

# Portamento threshold: consecutive notes within this semitone window
# and within this beat gap get a pitch-bend bridge.
PORTAMENTO_MAX_SEMITONES = 4
PORTAMENTO_MAX_GAP_BEATS = 0.25
# Fraction of each note's duration the portamento ramp covers at each end.
PORTAMENTO_EDGE_FRAC = 0.10

# Breath-noise attack (CC2 = breath controller).
BREATH_ATTACK_MS = 60
BREATH_PEAK = 80
BREATH_TAIL = 40

# Phrase-accent gap threshold.
PHRASE_GAP_BEATS = 0.5
PHRASE_ACCENT_VELOCITY = 8


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def apply_chinese_performance(score: Score) -> Score:
    """Apply Chinese-idiom rules to every Chinese-instrument track.

    Returns a new Score (does not mutate input).
    """
    new_score = score.model_copy(deep=True)
    touched = 0
    for trk in new_score.tracks:
        inst_l = (trk.instrument or "").lower()
        if inst_l not in CHINESE_INSTRUMENTS:
            continue
        _apply_to_track(trk, tempo_bpm=new_score.tempo)
        touched += 1

    logger.info(
        f"[performance_chinese] processed {touched} Chinese-instrument "
        f"track(s) out of {len(new_score.tracks)}"
    )
    return new_score


def _apply_to_track(track: ScoreTrack, *, tempo_bpm: int) -> None:
    inst = (track.instrument or "").lower()
    ms_to_beats = tempo_bpm / 60_000.0

    # Sort working copy for rule evaluation (neighbour lookups).
    sorted_notes = sorted(track.notes, key=lambda n: n.start_beat)
    if not sorted_notes:
        return

    # Rule: bow-articulation accent on phrase-start notes (erhu-ish,
    # applicable to any bowed / blown Chinese instrument).
    _phrase_accents(sorted_notes)

    # Rule: delayed vibrato on long notes for erhu & dizi.
    if inst in {"erhu", "dizi"}:
        _delayed_vibrato(
            track, sorted_notes, ms_to_beats=ms_to_beats,
        )

    # Rule: portamento between same-phrase notes (erhu, dizi, suona).
    if inst in {"erhu", "dizi", "suona"}:
        _portamento_between_notes(track, sorted_notes)

    # Rule: breath-noise spikes on dizi / suona attacks.
    if inst in {"dizi", "suona", "xiao"}:
        _breath_noise_attack(
            track, sorted_notes, ms_to_beats=ms_to_beats,
        )


# --------------------------------------------------------------------------
# Rule 1 — Phrase-start accent
# --------------------------------------------------------------------------

def _phrase_accents(notes: list) -> None:
    """First note after a ≥0.5-beat rest gets a velocity boost."""
    if not notes:
        return
    prev_end = -1.0  # force the very first note to count as phrase start
    for n in notes:
        gap = n.start_beat - prev_end
        if gap >= PHRASE_GAP_BEATS:
            new_vel = n.velocity + PHRASE_ACCENT_VELOCITY
            n.velocity = max(1, min(127, new_vel))
        prev_end = n.start_beat + n.duration_beats


# --------------------------------------------------------------------------
# Rule 2 — Delayed vibrato
# --------------------------------------------------------------------------

def _delayed_vibrato(
    track: ScoreTrack,
    notes: list,
    *,
    ms_to_beats: float,
) -> None:
    """For notes ≥ 0.75 beat, emit a vibrato LFO starting +delay beats
    into the note — not at onset."""
    delay_beats = VIBRATO_DELAY_MS * ms_to_beats
    for n in notes:
        if n.duration_beats < 0.75:
            continue
        lfo_start = n.start_beat + delay_beats
        lfo_end = n.start_beat + n.duration_beats
        if lfo_end <= lfo_start:
            continue
        span = lfo_end - lfo_start
        steps = max(4, int(span * VIBRATO_SAMPLES_PER_BEAT))
        for i in range(steps + 1):
            t = lfo_start + (i / max(1, steps)) * span
            phase = 2 * math.pi * VIBRATO_RATE_HZ * (t - lfo_start) / 4.0
            # t is in beats; ÷4.0 loosely approximates seconds at 4/4.
            value = int(round(
                64 + (VIBRATO_DEPTH_CC / 2) * math.sin(phase)
            ))
            track.cc_events.append(CCEvent(
                beat=round(t, 4),
                controller=1,   # Modulation / vibrato
                value=max(0, min(127, value)),
                channel=track.channel,
            ))


# --------------------------------------------------------------------------
# Rule 3 — Portamento between same-phrase notes
# --------------------------------------------------------------------------

def _portamento_between_notes(
    track: ScoreTrack, notes: list,
) -> None:
    """If two adjacent notes are close in pitch AND time, emit a pitch-
    bend ramp that slides between them over the last 10% of the prior
    note + first 10% of the next."""
    for i in range(len(notes) - 1):
        cur = notes[i]
        nxt = notes[i + 1]
        gap = nxt.start_beat - (cur.start_beat + cur.duration_beats)
        if gap < 0 or gap > PORTAMENTO_MAX_GAP_BEATS:
            continue
        semis = nxt.pitch - cur.pitch
        if abs(semis) == 0 or abs(semis) > PORTAMENTO_MAX_SEMITONES:
            continue
        # Ramp from 0 → target bend over last 10% of cur's duration.
        # target bend expresses the pitch-diff in 14-bit units, capped
        # to ±8191 at ±2 semitones (standard pitch-wheel range).
        target = int(round((semis / 2.0) * 8191))
        target = max(-8192, min(8191, target))

        edge = max(0.05, cur.duration_beats * PORTAMENTO_EDGE_FRAC)
        ramp_start = cur.start_beat + cur.duration_beats - edge
        steps = 6
        for j in range(steps + 1):
            t = ramp_start + (j / steps) * edge
            val = int(round(target * (j / steps)))
            track.pitch_bends.append(PitchBendEvent(
                beat=round(t, 4),
                value=val,
                channel=track.channel,
            ))
        # Reset bend to 0 at the next note's edge+10%, so the next
        # note plays at its natural pitch.
        edge2 = max(0.05, nxt.duration_beats * PORTAMENTO_EDGE_FRAC)
        reset_beat = nxt.start_beat + edge2
        track.pitch_bends.append(PitchBendEvent(
            beat=round(reset_beat, 4),
            value=0,
            channel=track.channel,
        ))


# --------------------------------------------------------------------------
# Rule 4 — Breath-noise attack
# --------------------------------------------------------------------------

def _breath_noise_attack(
    track: ScoreTrack,
    notes: list,
    *,
    ms_to_beats: float,
) -> None:
    """CC2 (breath) spike at 0 → peak → tail over the note's first
    BREATH_ATTACK_MS."""
    attack_beats = BREATH_ATTACK_MS * ms_to_beats
    for n in notes:
        start = n.start_beat
        # 3 points: onset (small), mid (peak), end (tail).
        track.cc_events.append(CCEvent(
            beat=round(start, 4),
            controller=2, value=0,
            channel=track.channel,
        ))
        track.cc_events.append(CCEvent(
            beat=round(start + attack_beats * 0.5, 4),
            controller=2, value=BREATH_PEAK,
            channel=track.channel,
        ))
        track.cc_events.append(CCEvent(
            beat=round(start + attack_beats, 4),
            controller=2, value=BREATH_TAIL,
            channel=track.channel,
        ))


__all__ = [
    "CHINESE_INSTRUMENTS",
    "apply_chinese_performance",
]

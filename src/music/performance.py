"""
Performance renderer — Phase 4 of the generation pipeline.

Takes a Score whose ScoreNote.ornaments lists contain high-level macro tokens
(e.g. "vibrato_deep", "slide_up_from:3") and emits concrete MIDI control
events:

- track.pitch_bends : list[PitchBendEvent]  — pitch-wheel ramps and LFOs
- track.cc_events   : list[CCEvent]        — modulation / breath / expression
- inserted notes (grace notes, retriggers, glissando sweeps)
- duration / velocity adjustments (staccato, tenuto, accent envelopes)

Design rules:
- Deterministic. Same Score in → same MIDI events out.
- Idempotent. `track.rendered = True` guard; a second render is a no-op.
- Never mutates the input Score. Returns a new one (model_copy(deep=True)).
- Unknown ornaments log a warning and are skipped, never crash.
- All bend values clamped to ±8191; retrigger counts capped at 16/note.
- Auto-rules pass runs FIRST (may add ornaments to notes); then expansion.

Entry points:
- apply_performance_render(score)                 — full pipeline
- apply_performance_render_to_track(track, card)  — single track, for tests
"""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Callable

from loguru import logger

from src.music.ornaments import ORNAMENT_MACROS, parse_ornament
from src.music.score import (
    CCEvent,
    PitchBendEvent,
    Score,
    ScoreNote,
    ScoreTrack,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BEND_MAX = 8191
BEND_MIN = -8192
CC_MAX = 127
CC_MIN = 0

# How many semitones the pitch-wheel covers at full deflection.
# Standard default; instruments/VSTs may override but 2 is safe.
PITCH_BEND_RANGE_SEMITONES = 2

# Sample rates (per beat) for continuous controllers.
VIBRATO_SAMPLES_PER_BEAT = 16   # ~96 Hz at 100 BPM
SLIDE_SAMPLES_PER_BEAT = 12
SWELL_SAMPLES_PER_BEAT = 8

# Cap on retrigger events per note (flutter / tremolo).
MAX_RETRIGGERS_PER_NOTE = 16

# Slide-approach duration (beats) for slide_up_from / slide_down_from.
APPROACH_DURATION_BEATS = 0.25

# Grace-note length (beats).
GRACE_NOTE_BEATS = 0.125


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _clamp_bend(v: float) -> int:
    return max(BEND_MIN, min(BEND_MAX, int(round(v))))


def _clamp_cc(v: float) -> int:
    return max(CC_MIN, min(CC_MAX, int(round(v))))


def _clamp_velocity(v: float) -> int:
    return max(1, min(127, int(round(v))))


def _semitones_to_bend(semitones: float) -> int:
    """Convert semitones to a pitch-wheel value. Assumes ±PITCH_BEND_RANGE."""
    frac = semitones / PITCH_BEND_RANGE_SEMITONES
    return _clamp_bend(frac * BEND_MAX)


def _fetch_recipe(card: dict | None, field: str, default):
    if not card:
        return default
    recipes = card.get("performance_recipes", {})
    return recipes.get(field, default)


def _fetch_velocity_envelope(card: dict | None) -> dict | None:
    if not card:
        return None
    return card.get("velocity_envelope_preset")


def _fetch_auto_rules(card: dict | None) -> list[dict]:
    if not card:
        return []
    return list(card.get("auto_rules", []))


# ---------------------------------------------------------------------------
# Auto-rule pass
# ---------------------------------------------------------------------------
def _note_index_relative(
    notes: list[ScoreNote], idx: int,
) -> tuple[bool, bool, ScoreNote | None, ScoreNote | None]:
    """Return (is_first, is_last, prev_note, next_note)."""
    is_first = idx == 0
    is_last = idx == len(notes) - 1
    prev_n = notes[idx - 1] if idx > 0 else None
    next_n = notes[idx + 1] if idx < len(notes) - 1 else None
    return is_first, is_last, prev_n, next_n


def _matches_condition(
    cond: str,
    note: ScoreNote,
    idx: int,
    notes: list[ScoreNote],
) -> bool:
    """Evaluate a single auto-rule condition string against a note context."""
    is_first, is_last, prev_n, next_n = _note_index_relative(notes, idx)
    c = cond.strip()

    # Prefix-based threshold conditions: "duration > 1.5"
    if c.startswith("duration >"):
        try:
            thresh = float(c.split(">", 1)[1].strip())
            return note.duration_beats > thresh
        except ValueError:
            return False
    if c.startswith("duration <"):
        try:
            thresh = float(c.split("<", 1)[1].strip())
            return note.duration_beats < thresh
        except ValueError:
            return False
    if c.startswith("velocity >"):
        try:
            thresh = float(c.split(">", 1)[1].strip())
            return note.velocity > thresh
        except ValueError:
            return False

    # Named conditions
    if c == "first_of_phrase":
        return is_first
    if c == "last_of_phrase":
        return is_last
    if c == "next_note_close":
        if not next_n:
            return False
        gap = next_n.start_beat - (note.start_beat + note.duration_beats)
        return 0 <= gap <= 0.25
    if c == "ascending_run":
        if not next_n:
            return False
        return next_n.pitch > note.pitch
    if c == "descending_run":
        if not next_n:
            return False
        return next_n.pitch < note.pitch
    if c == "ascending_step":
        if not next_n:
            return False
        return 0 < (next_n.pitch - note.pitch) <= 2
    if c == "descending_step":
        if not next_n:
            return False
        return 0 < (note.pitch - next_n.pitch) <= 2
    if c == "large_leap_up":
        if not next_n:
            return False
        return (next_n.pitch - note.pitch) >= 5
    if c == "isolated_note":
        prev_gap = (
            note.start_beat - (prev_n.start_beat + prev_n.duration_beats)
            if prev_n else float("inf")
        )
        next_gap = (
            next_n.start_beat - (note.start_beat + note.duration_beats)
            if next_n else float("inf")
        )
        return prev_gap > 1.0 and next_gap > 1.0

    logger.debug(f"[performance] unknown auto-rule condition: {cond!r}")
    return False


def _apply_auto_rules(track: ScoreTrack, card: dict | None) -> None:
    """Append ornaments to notes based on card-defined auto_rules.

    Mutates `track.notes[i].ornaments` in place. Idempotent per-note: won't
    add the same ornament twice.
    """
    rules = _fetch_auto_rules(card)
    if not rules:
        return
    notes = track.notes
    for idx, note in enumerate(notes):
        for rule in rules:
            cond = rule.get("condition", "")
            adds = rule.get("add_ornaments", [])
            if not cond or not adds:
                continue
            if not _matches_condition(cond, note, idx, notes):
                continue
            for orn in adds:
                if orn not in note.ornaments:
                    note.ornaments.append(orn)


# ---------------------------------------------------------------------------
# Per-ornament renderers
# ---------------------------------------------------------------------------
# Each renderer returns a dict with optional keys:
#   "pitch_bends":    list[PitchBendEvent]
#   "cc_events":      list[CCEvent]
#   "insert_notes":   list[ScoreNote]     (grace notes, retriggers, glissando)
#   "duration_mul":   float               (multiplicative duration adjust)
#   "duration_abs":   float               (absolute duration override)
#   "velocity_add":   int                 (additive velocity bump)
#   "consume_note":   bool                (if True, renderer will re-emit the
#                                          original note as a retrigger; caller
#                                          shortens the original)
# Missing keys = no change.

RenderResult = dict


def _render_vibrato(
    note: ScoreNote, track: ScoreTrack, card: dict | None,
    depth: int, rate_hz: float, delay_frac: float,
    tempo_bpm: int,
) -> RenderResult:
    """Emit a CC1 (modulation) LFO for the duration of the note.

    depth: peak CC1 value above baseline (0–127).
    rate_hz: vibrato frequency in Hz.
    delay_frac: 0.0 = start immediately; 0.5 = start halfway through.
    """
    ccs: list[CCEvent] = []
    beats_per_sec = tempo_bpm / 60.0
    sec_per_beat = 1.0 / beats_per_sec if beats_per_sec else 0.0
    start = note.start_beat + delay_frac * note.duration_beats
    end = note.start_beat + note.duration_beats
    span = end - start
    if span <= 0:
        return {}
    sample_count = max(2, int(span * VIBRATO_SAMPLES_PER_BEAT))
    for i in range(sample_count + 1):
        t = i / sample_count  # 0..1
        beat = start + t * span
        # Phase: oscillate sin(2π * rate_hz * (time_in_seconds))
        secs = (beat - start) * sec_per_beat
        val = depth * 0.5 * (1 + math.sin(2 * math.pi * rate_hz * secs))
        ccs.append(CCEvent(
            beat=round(beat, 4),
            controller=1,
            value=_clamp_cc(val),
            channel=track.channel,
        ))
    return {"cc_events": ccs}


def _render_slide_from(
    note: ScoreNote, track: ScoreTrack, card: dict | None,
    semitones: int, direction: int,
) -> RenderResult:
    """Portamento from (direction * semitones) below/above into the note.

    direction = +1 (slide up from below), -1 (slide down from above).
    Emits a pitch-wheel ramp over APPROACH_DURATION_BEATS before the note,
    starting at ±semitones bend and ending at 0.
    """
    bends: list[PitchBendEvent] = []
    start = max(0.0, note.start_beat - APPROACH_DURATION_BEATS)
    end = note.start_beat
    span = end - start
    if span <= 0:
        return {}
    sample_count = max(4, int(span * SLIDE_SAMPLES_PER_BEAT * 4))
    start_bend = _semitones_to_bend(-direction * semitones)
    for i in range(sample_count + 1):
        t = i / sample_count  # 0..1
        beat = start + t * span
        bend = int(round(start_bend * (1 - t)))
        bends.append(PitchBendEvent(
            beat=round(beat, 4),
            value=_clamp_bend(bend),
            channel=track.channel,
        ))
    # Neutralize at note end so subsequent notes aren't bent.
    bends.append(PitchBendEvent(
        beat=round(end, 4),
        value=0,
        channel=track.channel,
    ))
    return {"pitch_bends": bends}


def _render_slide_to(
    note: ScoreNote, track: ScoreTrack, card: dict | None,
    semitones: int, direction: int,
) -> RenderResult:
    """Bend up/down to ±semitones over the note's duration."""
    bends: list[PitchBendEvent] = []
    start = note.start_beat
    end = note.start_beat + note.duration_beats
    span = note.duration_beats
    if span <= 0:
        return {}
    sample_count = max(4, int(span * SLIDE_SAMPLES_PER_BEAT))
    target_bend = _semitones_to_bend(direction * semitones)
    for i in range(sample_count + 1):
        t = i / sample_count
        beat = start + t * span
        bend = int(round(target_bend * t))
        bends.append(PitchBendEvent(
            beat=round(beat, 4),
            value=_clamp_bend(bend),
            channel=track.channel,
        ))
    # Release bend right after the note ends.
    bends.append(PitchBendEvent(
        beat=round(end + 0.01, 4),
        value=0,
        channel=track.channel,
    ))
    return {"pitch_bends": bends}


def _render_bend_dip(
    note: ScoreNote, track: ScoreTrack, card: dict | None,
) -> RenderResult:
    """Down-up pitch dip over the middle 50% of the note (vocal-like 哭腔)."""
    bends: list[PitchBendEvent] = []
    dip_start = note.start_beat + 0.25 * note.duration_beats
    dip_end = note.start_beat + 0.75 * note.duration_beats
    span = dip_end - dip_start
    if span <= 0:
        return {}
    sample_count = max(6, int(span * SLIDE_SAMPLES_PER_BEAT))
    dip_depth = _semitones_to_bend(-1)  # about a semitone down
    for i in range(sample_count + 1):
        t = i / sample_count  # 0..1
        beat = dip_start + t * span
        # Triangle: 0 → min → 0
        val = dip_depth * (1 - abs(2 * t - 1))
        bends.append(PitchBendEvent(
            beat=round(beat, 4),
            value=_clamp_bend(val),
            channel=track.channel,
        ))
    bends.append(PitchBendEvent(
        beat=round(dip_end + 0.01, 4), value=0, channel=track.channel,
    ))
    return {"pitch_bends": bends}


def _render_flutter(
    note: ScoreNote, track: ScoreTrack, card: dict | None,
    tempo_bpm: int,
) -> RenderResult:
    """Flutter tongue: 16th-note retriggers + CC1 oscillation."""
    # Retriggers at 16th-note rate over the note's duration.
    subdiv = 0.25  # 16th at 4/4
    count = min(MAX_RETRIGGERS_PER_NOTE, int(note.duration_beats / subdiv))
    insert: list[ScoreNote] = []
    for i in range(1, count):
        insert.append(ScoreNote(
            pitch=note.pitch,
            start_beat=round(note.start_beat + i * subdiv, 4),
            duration_beats=subdiv * 0.9,
            velocity=_clamp_velocity(note.velocity * 0.85),
            articulation=note.articulation,
        ))
    # CC1 fast oscillation as tongue buzz.
    vib = _render_vibrato(
        note, track, card,
        depth=70, rate_hz=7.0, delay_frac=0.0,
        tempo_bpm=tempo_bpm,
    )
    return {
        "cc_events": vib.get("cc_events", []),
        "insert_notes": insert,
        "duration_abs": subdiv * 0.9,  # first "buzz" is just a 16th
    }


def _render_tremolo_rapid(
    note: ScoreNote, track: ScoreTrack, card: dict | None,
) -> RenderResult:
    """Pure note retrigger at 16th-note rate (Pipa 轮指, Yangqin)."""
    subdiv = 0.25
    count = min(MAX_RETRIGGERS_PER_NOTE, int(note.duration_beats / subdiv))
    insert: list[ScoreNote] = []
    for i in range(1, count):
        insert.append(ScoreNote(
            pitch=note.pitch,
            start_beat=round(note.start_beat + i * subdiv, 4),
            duration_beats=subdiv * 0.9,
            velocity=_clamp_velocity(note.velocity * 0.9),
            articulation=note.articulation,
        ))
    return {
        "insert_notes": insert,
        "duration_abs": subdiv * 0.9,
    }


def _render_grace_note(
    note: ScoreNote, track: ScoreTrack, card: dict | None,
    direction: int,
) -> RenderResult:
    """Insert a 1/16 grace note before the main note, ±1 semitone."""
    grace_start = max(0.0, note.start_beat - GRACE_NOTE_BEATS)
    insert = [ScoreNote(
        pitch=max(0, min(127, note.pitch + direction)),
        start_beat=round(grace_start, 4),
        duration_beats=GRACE_NOTE_BEATS * 0.9,
        velocity=_clamp_velocity(note.velocity * 0.7),
        articulation=note.articulation,
    )]
    return {"insert_notes": insert}


def _render_glissando(
    note: ScoreNote, track: ScoreTrack, card: dict | None,
    direction: str,
) -> RenderResult:
    """Arpeggiated sweep of 4 notes leading into or out of this note.

    direction="from": sweep precedes the note.
    direction="to":   sweep follows the note.
    """
    sweep_count = 4
    step = 2  # semitones per step (pentatonic-ish)
    subdiv = 0.08
    insert: list[ScoreNote] = []
    if direction == "from":
        base_start = note.start_beat - sweep_count * subdiv
        for i in range(sweep_count):
            insert.append(ScoreNote(
                pitch=max(0, min(127, note.pitch - (sweep_count - i) * step)),
                start_beat=round(max(0.0, base_start + i * subdiv), 4),
                duration_beats=subdiv * 0.9,
                velocity=_clamp_velocity(note.velocity * 0.65),
                articulation=note.articulation,
            ))
    else:  # "to"
        base_start = note.start_beat + note.duration_beats
        for i in range(sweep_count):
            insert.append(ScoreNote(
                pitch=max(0, min(127, note.pitch + (i + 1) * step)),
                start_beat=round(base_start + i * subdiv, 4),
                duration_beats=subdiv * 0.9,
                velocity=_clamp_velocity(note.velocity * 0.65),
                articulation=note.articulation,
            ))
    return {"insert_notes": insert}


def _render_breath_envelope(
    note: ScoreNote, track: ScoreTrack, card: dict | None,
    direction: str,
) -> RenderResult:
    """CC2 (breath) + CC11 (expression) envelope.

    direction="swell": rise over first 0.25 beats from ~40 to peak.
    direction="fade":  fall over last 0.5 beats from current to ~30.
    """
    ccs: list[CCEvent] = []
    if direction == "swell":
        span = min(0.4, max(0.1, note.duration_beats * 0.4))
        start = note.start_beat
        end = start + span
        peak_cc2 = 100
        peak_cc11 = 110
        start_cc2 = 40
        start_cc11 = 60
    else:  # fade
        span = min(0.6, max(0.2, note.duration_beats * 0.4))
        end = note.start_beat + note.duration_beats
        start = max(note.start_beat, end - span)
        peak_cc2 = 30
        peak_cc11 = 40
        start_cc2 = 90
        start_cc11 = 100
    if span <= 0:
        return {}
    sample_count = max(3, int(span * SWELL_SAMPLES_PER_BEAT))
    for i in range(sample_count + 1):
        t = i / sample_count
        beat = start + t * span
        cc2_val = start_cc2 + (peak_cc2 - start_cc2) * t
        cc11_val = start_cc11 + (peak_cc11 - start_cc11) * t
        ccs.append(CCEvent(
            beat=round(beat, 4), controller=2,
            value=_clamp_cc(cc2_val), channel=track.channel,
        ))
        ccs.append(CCEvent(
            beat=round(beat, 4), controller=11,
            value=_clamp_cc(cc11_val), channel=track.channel,
        ))
    return {"cc_events": ccs}


def _render_overblow(
    note: ScoreNote, track: ScoreTrack, card: dict | None,
) -> RenderResult:
    """Brief sharp pitch jolt + velocity bump (Dizi aggressive attack)."""
    bends: list[PitchBendEvent] = [
        PitchBendEvent(
            beat=round(note.start_beat, 4),
            value=_semitones_to_bend(0.4),
            channel=track.channel,
        ),
        PitchBendEvent(
            beat=round(note.start_beat + 0.1, 4),
            value=0,
            channel=track.channel,
        ),
    ]
    return {"pitch_bends": bends, "velocity_add": 12}


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------
def _render_one_ornament(
    token: str,
    note: ScoreNote,
    track: ScoreTrack,
    card: dict | None,
    tempo_bpm: int,
    is_last_in_track: bool,
) -> RenderResult:
    name, arg = parse_ornament(token)
    spec = ORNAMENT_MACROS.get(name)
    if spec is None:
        logger.warning(f"[performance] unknown ornament '{token}', skipping")
        return {}

    # Resolve argument with default.
    if spec.takes_arg and arg is None:
        arg = spec.arg_default if spec.arg_default is not None else 2
    if spec.takes_arg and spec.arg_range is not None:
        lo, hi = spec.arg_range
        if arg is not None:
            arg = max(lo, min(hi, arg))

    # Card-driven vibrato depth/rate.
    vib_depth_default = 40
    vib_rate_default = 5.5
    if name == "vibrato_light":
        return _render_vibrato(
            note, track, card,
            depth=_fetch_recipe(
                card, "vibrato_light_depth", vib_depth_default,
            ),
            rate_hz=_fetch_recipe(
                card, "vibrato_light_rate_hz", vib_rate_default,
            ),
            delay_frac=0.0, tempo_bpm=tempo_bpm,
        )
    if name == "vibrato_deep":
        return _render_vibrato(
            note, track, card,
            depth=_fetch_recipe(card, "vibrato_deep_depth", 75),
            rate_hz=_fetch_recipe(card, "vibrato_deep_rate_hz", 6.0),
            delay_frac=0.0, tempo_bpm=tempo_bpm,
        )
    if name == "vibrato_delayed":
        return _render_vibrato(
            note, track, card,
            depth=_fetch_recipe(card, "vibrato_deep_depth", 60),
            rate_hz=_fetch_recipe(card, "vibrato_deep_rate_hz", 5.5),
            delay_frac=0.5, tempo_bpm=tempo_bpm,
        )

    if name == "slide_up_from":
        return _render_slide_from(note, track, card, arg or 2, direction=+1)
    if name == "slide_down_from":
        return _render_slide_from(note, track, card, arg or 2, direction=-1)
    if name == "slide_up_to":
        return _render_slide_to(note, track, card, arg or 2, direction=+1)
    if name == "slide_down_to":
        return _render_slide_to(note, track, card, arg or 2, direction=-1)
    if name == "bend_dip":
        return _render_bend_dip(note, track, card)

    if name == "flutter":
        return _render_flutter(note, track, card, tempo_bpm)
    if name == "tremolo_rapid":
        return _render_tremolo_rapid(note, track, card)
    if name == "overblow":
        return _render_overblow(note, track, card)

    if name == "grace_note_above":
        return _render_grace_note(note, track, card, direction=+1)
    if name == "grace_note_below":
        return _render_grace_note(note, track, card, direction=-1)
    if name == "glissando_from":
        return _render_glissando(note, track, card, direction="from")
    if name == "glissando_to":
        return _render_glissando(note, track, card, direction="to")

    if name == "breath_swell":
        return _render_breath_envelope(note, track, card, direction="swell")
    if name == "breath_fade":
        return _render_breath_envelope(note, track, card, direction="fade")

    if name == "staccato":
        return {"duration_mul": 0.5}
    if name == "tenuto":
        return {"duration_mul": 1.0, "velocity_add": 5}
    if name == "legato_to_next":
        # Degrade to tenuto on the last note of the track.
        if is_last_in_track:
            return {"duration_mul": 1.0, "velocity_add": 3}
        # Signal to merge-pass that this note should overlap the next.
        return {"legato": True}

    logger.warning(f"[performance] renderer missing for ornament '{name}'")
    return {}


# ---------------------------------------------------------------------------
# Velocity envelope preset
# ---------------------------------------------------------------------------
def _apply_velocity_envelope(
    notes: list[ScoreNote], preset: dict | None,
) -> None:
    """Smooth velocities across the note sequence via a simple preset.

    preset = {"attack": 0..1, "peak_ratio": 0..1, "decay": 0..1}
    If omitted, notes are untouched.
    """
    if not preset or not notes:
        return
    attack = float(preset.get("attack", 0.0))
    peak_ratio = float(preset.get("peak_ratio", 0.5))
    decay = float(preset.get("decay", 0.0))
    n = len(notes)
    if n < 2:
        return
    peak_idx = max(0, min(n - 1, int(round((n - 1) * peak_ratio))))
    for i, note in enumerate(notes):
        base = note.velocity
        if i < peak_idx and attack > 0:
            # Attack ramp: boost from (1 - attack) * base at note 0 to base at peak.
            t = i / max(1, peak_idx)
            mul = (1 - attack) + attack * t
            note.velocity = _clamp_velocity(base * mul)
        elif i > peak_idx and decay > 0:
            t = (i - peak_idx) / max(1, n - 1 - peak_idx)
            mul = 1 - decay * t
            note.velocity = _clamp_velocity(base * mul)


# ---------------------------------------------------------------------------
# Per-track renderer
# ---------------------------------------------------------------------------
def apply_performance_render_to_track(
    track: ScoreTrack, card: dict | None, tempo_bpm: int = 120,
) -> ScoreTrack:
    """Render one track in place-on-a-copy. Returns the rendered copy.

    Safe to call directly from tests.
    """
    if track.rendered:
        return track

    # Deep-copy to preserve input.
    new_track = track.model_copy(deep=True)

    # 1) Auto-ornament pass.
    _apply_auto_rules(new_track, card)

    # 2) Ornament expansion pass.
    original_notes = list(new_track.notes)
    inserted_notes: list[ScoreNote] = []
    all_bends: list[PitchBendEvent] = list(new_track.pitch_bends)
    all_ccs: list[CCEvent] = list(new_track.cc_events)

    for idx, note in enumerate(original_notes):
        if not note.ornaments:
            continue
        is_last = idx == len(original_notes) - 1
        next_note = original_notes[idx + 1] if not is_last else None
        duration_mul = 1.0
        duration_abs: float | None = None
        velocity_add = 0
        legato_flag = False

        for token in note.ornaments:
            res = _render_one_ornament(
                token, note, new_track, card, tempo_bpm, is_last,
            )
            all_bends.extend(res.get("pitch_bends", []))
            all_ccs.extend(res.get("cc_events", []))
            inserted_notes.extend(res.get("insert_notes", []))
            if "duration_mul" in res:
                duration_mul *= float(res["duration_mul"])
            if "duration_abs" in res:
                duration_abs = float(res["duration_abs"])
            if "velocity_add" in res:
                velocity_add += int(res["velocity_add"])
            if res.get("legato"):
                legato_flag = True

        if duration_abs is not None:
            note.duration_beats = max(0.05, duration_abs)
        elif duration_mul != 1.0:
            note.duration_beats = max(0.05, note.duration_beats * duration_mul)

        if velocity_add:
            note.velocity = _clamp_velocity(note.velocity + velocity_add)

        if legato_flag and next_note is not None:
            # Extend this note to end right at the next note's onset.
            target_end = next_note.start_beat
            new_dur = target_end - note.start_beat
            if new_dur > 0.05:
                note.duration_beats = new_dur

    # 3) Velocity envelope.
    env = _fetch_velocity_envelope(card)
    if env:
        _apply_velocity_envelope(original_notes, env)

    # 4) Merge inserted notes; sort; dedupe exact-dup events.
    merged_notes = original_notes + inserted_notes
    merged_notes.sort(key=lambda n: (n.start_beat, n.pitch))
    new_track.notes = merged_notes

    all_bends.sort(key=lambda e: (e.beat, e.channel))
    all_ccs.sort(key=lambda e: (e.beat, e.controller, e.channel))
    new_track.pitch_bends = all_bends
    new_track.cc_events = all_ccs

    new_track.rendered = True
    return new_track


# ---------------------------------------------------------------------------
# Full-Score entry point
# ---------------------------------------------------------------------------
def _resolve_card(
    instrument_name: str, instrument_cards: dict,
) -> dict | None:
    """Case-insensitive instrument-card lookup."""
    if not instrument_name:
        return None
    if instrument_name in instrument_cards:
        return instrument_cards[instrument_name]
    lower = instrument_name.lower()
    for key, card in instrument_cards.items():
        if key.lower() == lower:
            return card
    return None


def apply_performance_render(
    score: Score,
    instrument_cards: dict | None = None,
) -> Score:
    """Render every track in the score. Returns a new Score.

    - Skips tracks where `track.rendered = True` (idempotency).
    - Never mutates `score`.
    - Instrument-cards lookup uses case-insensitive match on instrument name.
    """
    if instrument_cards is None:
        # Lazy import to avoid circular dependency at module load.
        from src.knowledge.instruments import INSTRUMENT_CARDS
        instrument_cards = INSTRUMENT_CARDS

    new_score = score.model_copy(deep=True)
    new_tracks: list[ScoreTrack] = []
    for trk in new_score.tracks:
        if trk.rendered:
            new_tracks.append(trk)
            continue
        card = _resolve_card(trk.instrument, instrument_cards)
        rendered = apply_performance_render_to_track(
            trk, card, tempo_bpm=new_score.tempo,
        )
        new_tracks.append(rendered)
    new_score.tracks = new_tracks
    return new_score

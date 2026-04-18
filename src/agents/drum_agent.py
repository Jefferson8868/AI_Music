"""
DrumAgent — Round 2 Phase B2.

Deterministic drum programmer. Given (section_role, tempo, genre), it:
  1. Picks a `GrooveTemplate` via `groove_library.select_template`.
  2. Instantiates the template's kick/snare/hat/perc positions on the
     16th-note grid, mapped to actual beats (`start_beat + cell * 0.25`).
  3. Applies swing (off-beat 16ths pushed later by `swing_pct - 50`).
  4. Applies per-voice micro-timing (ms → beat fraction) so the snare
     lays back / hats push early — before the Phase C humanizer adds
     its own jitter.
  5. On the LAST bar of the section, writes a 1-bar fill:
       * A 16th-note snare roll on the 4th beat.
       * A ghost open-hat on the last 8th.
     This is the "boundary signal" that tells the listener a section
     is about to change.

Not an LLM agent — drum programming is algorithmic. The class exposes
a plain `compose_section()` method and returns `ScoreTrack` objects
directly, so pipeline.py can merge the result into its Score without
going through the AutoGen chat protocol.
"""

from __future__ import annotations

from typing import Iterable

from loguru import logger

from src.knowledge.groove_library import (
    ALL_TEMPLATES,
    DrumVoice,
    GrooveTemplate,
    SectionRole,
    select_template,
    template_by_name,
)
from src.music.score import ScoreNote, ScoreTrack


# GM percussion-map MIDI pitches (channel 10 / program ignored).
_VOICE_TO_PITCH: dict[DrumVoice, int] = {
    "kick": 36,   # Acoustic bass drum
    "snare": 38,  # Acoustic snare
    "chh": 42,    # Closed hi-hat
    "ohh": 46,    # Open hi-hat
    "ride": 51,   # Ride cymbal 1
    "crash": 49,  # Crash cymbal 1
    "perc": 64,   # Low conga (stands in for frame drum etc.)
}

_VOICE_TO_CHANNEL = 9   # GM Channel 10 (0-indexed = 9) is the drum kit.


class DrumAgent:
    """Rule-based drum programmer. No LLM."""

    def __init__(self) -> None:
        # Cached for logging only — real selection happens per call.
        self._last_template: GrooveTemplate | None = None

    # ---------------------------------------------------------------
    # Public entry points
    # ---------------------------------------------------------------

    def compose_section(
        self,
        section_role: SectionRole,
        start_beat: float,
        end_beat: float,
        bars: int,
        tempo_bpm: float,
        genre_hint: str = "",
        template_name: str | None = None,
        add_fill_on_last_bar: bool = True,
    ) -> list[ScoreTrack]:
        """Compose the drum part for one section.

        Returns a list of ScoreTrack (one per active voice) so the
        pipeline can merge them back alongside the melodic tracks.
        """
        if template_name:
            tpl = template_by_name(template_name)
            if tpl is None:
                logger.warning(
                    f"[DrumAgent] Template '{template_name}' not found; "
                    "falling back to auto-select."
                )
                tpl = select_template(section_role, tempo_bpm, genre_hint)
        else:
            tpl = select_template(section_role, tempo_bpm, genre_hint)
        self._last_template = tpl
        logger.info(
            f"[DrumAgent] section={section_role} tempo={tempo_bpm:.0f} "
            f"→ template={tpl.name} swing={tpl.swing_pct}"
        )

        # Build one track per voice that actually has any hit.
        tracks: list[ScoreTrack] = []
        for voice_raw, grid in tpl.pattern.items():
            voice: DrumVoice = voice_raw  # type: ignore[assignment]
            if not any(v > 0 for v in grid):
                continue
            track_notes = self._realize_voice(
                voice=voice,
                grid=grid,
                start_beat=start_beat,
                end_beat=end_beat,
                bars=bars,
                tempo_bpm=tempo_bpm,
                swing_pct=tpl.swing_pct,
                microtime_ms=tpl.microtiming.get(voice, 0),
            )
            if not track_notes:
                continue
            tracks.append(ScoreTrack(
                name=f"drums_{voice}",
                instrument="drums",
                role="rhythm",
                channel=_VOICE_TO_CHANNEL,
                program=0,   # GM drum kit; actual pitches carry the voice
                notes=track_notes,
            ))

        if add_fill_on_last_bar and bars >= 2:
            fill_notes = self._last_bar_fill(
                start_beat=start_beat,
                end_beat=end_beat,
                bars=bars,
                tempo_bpm=tempo_bpm,
            )
            if fill_notes:
                tracks.append(ScoreTrack(
                    name="drums_fill",
                    instrument="drums",
                    role="rhythm",
                    channel=_VOICE_TO_CHANNEL,
                    program=0,
                    notes=fill_notes,
                ))

        return tracks

    # ---------------------------------------------------------------
    # Internals
    # ---------------------------------------------------------------

    def _realize_voice(
        self,
        voice: DrumVoice,
        grid: list[float],
        start_beat: float,
        end_beat: float,
        bars: int,
        tempo_bpm: float,
        swing_pct: int,
        microtime_ms: int,
    ) -> list[ScoreNote]:
        """Instantiate one voice's grid across every bar in the section."""
        ms_to_beats = _ms_to_beats(tempo_bpm)
        cells_per_bar = max(1, len(grid))
        # Ballad / halftime templates sometimes pack 16 cells into 1 bar
        # and sometimes into 2 bars — we treat cells_per_bar==16 as 1 bar
        # (the common case). Anything else gets passed through as-is.
        swing_offset = (swing_pct - 50) / 100.0  # 0.08 for 58%
        notes: list[ScoreNote] = []
        for bar_ix in range(bars):
            bar_start = start_beat + bar_ix * 4.0
            for cell_ix, v in enumerate(grid):
                if v <= 0:
                    continue
                beat_in_bar = (cell_ix / cells_per_bar) * 4.0
                # Swing: push every ODD 16th later by `swing_offset`
                # of a 16th note.
                if cell_ix % 2 == 1:
                    beat_in_bar += swing_offset * 0.25
                start = bar_start + beat_in_bar
                start += microtime_ms * ms_to_beats
                if start >= end_beat:
                    continue
                # Velocity: 30 + 90 * grid_value → 30..120.
                velocity = int(30 + 90 * min(1.0, max(0.0, v)))
                pitch = _VOICE_TO_PITCH[voice]
                dur = 0.125  # drums are short (32nd note felt length)
                notes.append(ScoreNote(
                    pitch=pitch,
                    start_beat=round(start, 4),
                    duration_beats=dur,
                    velocity=velocity,
                ))
        return notes

    def _last_bar_fill(
        self,
        start_beat: float,
        end_beat: float,
        bars: int,
        tempo_bpm: float,
    ) -> list[ScoreNote]:
        """Simple 1-bar fill: 16th-note snare roll on beat 4 + open hat."""
        _ = tempo_bpm  # future-use hook
        last_bar_start = start_beat + (bars - 1) * 4.0
        if last_bar_start >= end_beat:
            return []
        notes: list[ScoreNote] = []
        # Snare roll across beat 4: 4 × 16th, accelerating velocity.
        for i, vel in enumerate((55, 70, 85, 100)):
            pos = last_bar_start + 3.0 + i * 0.25
            if pos >= end_beat:
                break
            notes.append(ScoreNote(
                pitch=_VOICE_TO_PITCH["snare"],
                start_beat=round(pos, 4),
                duration_beats=0.125,
                velocity=vel,
            ))
        # Open hat on the "and" of 4.
        oh_pos = last_bar_start + 3.5
        if oh_pos < end_beat:
            notes.append(ScoreNote(
                pitch=_VOICE_TO_PITCH["ohh"],
                start_beat=round(oh_pos, 4),
                duration_beats=0.25,
                velocity=80,
            ))
        return notes


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------

def _ms_to_beats(tempo_bpm: float) -> float:
    """Convert milliseconds to beats at the given tempo.

    1 beat = 60_000 / tempo_bpm milliseconds.
    So beats = ms / (60_000 / tempo_bpm) = ms * tempo_bpm / 60_000.
    """
    if tempo_bpm <= 0:
        return 0.0
    return tempo_bpm / 60_000.0


def drum_agent_knowledge_summary() -> str:
    """Return a short human-readable inventory of available templates.

    Useful for logs / debug dumps and as a factual block in the
    Critic prompt ("these are the drum grooves in the library;
    score the rhythm spine knowing this vocabulary exists").
    """
    lines = ["DrumAgent template inventory:"]
    for t in ALL_TEMPLATES:
        fits = ", ".join(t.fits)
        lines.append(
            f"  - {t.name}: tempo {t.tempo_range[0]}-{t.tempo_range[1]}, "
            f"fits={fits}, swing={t.swing_pct}  ({t.notes})"
        )
    return "\n".join(lines)


def iter_templates() -> Iterable[GrooveTemplate]:
    """Direct iterator for tests and introspection."""
    return iter(ALL_TEMPLATES)

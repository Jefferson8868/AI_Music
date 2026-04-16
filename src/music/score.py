"""
Score — the central data structure that all Agents read and modify.
Represents a complete musical score with sections, tracks, and notes.
Designed to be compact enough for LLM context windows while retaining
note-level detail for precise editing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil

from pydantic import BaseModel, Field


class ScoreNote(BaseModel):
    pitch: int
    start_beat: float
    duration_beats: float
    velocity: int = 80
    articulation: str = "normal"
    pitch_bend: int | None = None
    expression: int | None = None


class ScoreSection(BaseModel):
    name: str
    start_beat: float
    bars: int
    chords: list[dict] = Field(default_factory=list)
    lyrics: list[dict] | None = None


class ScoreTrack(BaseModel):
    name: str
    instrument: str
    role: str
    channel: int = 0
    program: int = 0
    notes: list[ScoreNote] = Field(default_factory=list)
    vst_plugin: str | None = None
    vst_preset: str | None = None


_MIDI_NOTE_NAMES = [
    "C", "C#", "D", "D#", "E", "F",
    "F#", "G", "G#", "A", "A#", "B",
]


def _pitch_name(midi: int) -> str:
    return f"{_MIDI_NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


class Score(BaseModel):
    title: str = "Untitled"
    key: str = "C"
    scale_type: str = "major"
    tempo: int = 120
    time_signature: list[int] = Field(default_factory=lambda: [4, 4])
    sections: list[ScoreSection] = Field(default_factory=list)
    tracks: list[ScoreTrack] = Field(default_factory=list)
    version: int = 1

    def to_summary(self) -> str:
        ts = self.time_signature
        lines = [
            f"# {self.title} | {self.key} {self.scale_type}"
            f" | {self.tempo}bpm | {ts[0]}/{ts[1]}"
        ]
        for sec in self.sections:
            chords_str = ", ".join(
                f"{c.get('root', '?')}{c.get('quality', '')}"
                for c in sec.chords
            )
            lines.append(
                f"## {sec.name} ({sec.bars} bars): {chords_str}"
            )
        for trk in self.tracks:
            lines.append(
                f"Track [{trk.name}] ({trk.role}): "
                f"{len(trk.notes)} notes, ch={trk.channel}"
            )
        return "\n".join(lines)

    def to_llm_description(self) -> str:
        """Section-by-section text summary readable by LLMs."""
        bpb = self.time_signature[0] if self.time_signature else 4
        ts = self.time_signature
        total = sum(len(t.notes) for t in self.tracks)
        parts: list[str] = [
            f"SCORE: {self.title} | key={self.key} "
            f"{self.scale_type} | tempo={self.tempo} | "
            f"time={ts[0]}/{ts[1]} | "
            f"tracks={len(self.tracks)} | total_notes={total}",
        ]

        for sec in self.sections:
            sec_end = sec.start_beat + sec.bars * bpb
            bar_start = int(sec.start_beat // bpb) + 1
            bar_end = int(sec_end // bpb)
            sec_header = (
                f"\n[{sec.name.upper()}] "
                f"bars {bar_start}-{bar_end}, "
                f"beats {sec.start_beat:.0f}-{sec_end:.0f}:"
            )
            track_descs: list[str] = []
            for trk in self.tracks:
                notes_in = [
                    n for n in trk.notes
                    if sec.start_beat <= n.start_beat < sec_end
                ]
                if not notes_in:
                    track_descs.append(
                        f"  {trk.name} ({trk.instrument}): EMPTY"
                    )
                    continue
                pitches = [n.pitch for n in notes_in]
                vels = [n.velocity for n in notes_in]
                lo = _pitch_name(min(pitches))
                hi = _pitch_name(max(pitches))
                first_few = " ".join(
                    _pitch_name(n.pitch)
                    for n in notes_in[:6]
                )
                ellip = "..." if len(notes_in) > 6 else ""
                track_descs.append(
                    f"  {trk.name} ({trk.instrument}): "
                    f"{len(notes_in)} notes, "
                    f"pitch {lo}-{hi}, "
                    f"vel {min(vels)}-{max(vels)}, "
                    f"starts: {first_few}{ellip}"
                )
            parts.append(sec_header)
            parts.extend(track_descs)

        return "\n".join(parts)

    def get_section_notes(
        self, section_name: str, track_name: str,
    ) -> list[ScoreNote]:
        sec = next((s for s in self.sections if s.name == section_name), None)
        trk = next((t for t in self.tracks if t.name == track_name), None)
        if not sec or not trk:
            return []
        sec_end = sec.start_beat + sec.bars * self.time_signature[0]
        return [
            n for n in trk.notes
            if sec.start_beat <= n.start_beat < sec_end
        ]

    def replace_section_notes(
        self, section_name: str, track_name: str, new_notes: list[ScoreNote],
    ) -> None:
        sec = next((s for s in self.sections if s.name == section_name), None)
        trk = next((t for t in self.tracks if t.name == track_name), None)
        if not sec or not trk:
            return
        sec_start = sec.start_beat
        sec_end = sec_start + sec.bars * self.time_signature[0]
        trk.notes = [
            n for n in trk.notes
            if not (sec_start <= n.start_beat < sec_end)
        ]
        trk.notes.extend(new_notes)
        trk.notes.sort(key=lambda n: n.start_beat)
        self.version += 1

    def get_section(self, name: str) -> ScoreSection | None:
        return next((s for s in self.sections if s.name == name), None)

    def get_track(self, name: str) -> ScoreTrack | None:
        return next((t for t in self.tracks if t.name == name), None)

    @property
    def total_beats(self) -> float:
        if not self.sections:
            return 0.0
        last = max(self.sections, key=lambda s: s.start_beat)
        return last.start_beat + last.bars * self.time_signature[0]

    @property
    def duration_seconds(self) -> float:
        if self.tempo > 0:
            return (self.total_beats / self.tempo) * 60.0
        return 0.0


# ---------------------------------------------------------------------------
# Message payload models (used by Agents inside StructuredMessage)
# ---------------------------------------------------------------------------

class SectionPlan(BaseModel):
    name: str
    bars: int = 8
    chords_per_bar: int = 1
    mood: str = ""
    dynamics: str = "mf"


class InstrumentPlan(BaseModel):
    name: str
    role: str = "accompaniment"
    style_notes: str = ""


class LyricsPlan(BaseModel):
    include: bool = False
    language: str = "en"
    theme: str = ""
    syllable_density: str = "moderate"


class CompositionBlueprint(BaseModel):
    title: str = "Untitled"
    key: str = "C"
    scale_type: str = "major"
    tempo: int = 120
    time_signature: list[int] = Field(default_factory=lambda: [4, 4])
    sections: list[SectionPlan] = Field(default_factory=list)
    instruments: list[InstrumentPlan] = Field(default_factory=list)
    lyrics_plan: LyricsPlan = Field(default_factory=LyricsPlan)
    primer_notes: list[int] = Field(default_factory=lambda: [60, 64, 67])
    primer_temperature: float = 1.0
    global_notes: str = ""


class CriticIssue(BaseModel):
    aspect: str
    location: str
    severity: str = "moderate"
    description: str
    suggestion: str


class CriticReview(BaseModel):
    overall_score: float = 0.0
    passes: bool = False
    aspect_scores: dict[str, float] = Field(default_factory=dict)
    issues: list[CriticIssue] = Field(default_factory=list)
    request_regeneration: bool = False
    revision_instructions: str = ""


class NoteEdit(BaseModel):
    action: str
    track: str
    section: str
    target_beat: float | None = None
    pitch: int | None = None
    start_beat: float | None = None
    duration_beats: float | None = None
    velocity: int | None = None


class ScoreUpdate(BaseModel):
    edits: list[NoteEdit] = Field(default_factory=list)
    request_regeneration: bool = False
    commentary: str = ""


class SynthesisRequest(BaseModel):
    primer_notes: list[int] = Field(default_factory=lambda: [60, 64, 67])
    num_steps: int = 128
    temperature: float = 1.0
    qpm: float = 120.0
    model_type: str = "melody"
    section_name: str | None = None


# ---------------------------------------------------------------------------
# Quantitative metrics (computed by code, never by LLM)
# ---------------------------------------------------------------------------

def compute_score_metrics(
    score: Score,
    enriched_sections: list[dict],
    lyrics: list[dict] | None = None,
) -> dict:
    """Compute exact quantitative metrics for the Critic.

    Returns a dict with total_notes, track_count, per-section breakdowns,
    section_contrast info, and lyrics_alignment percentage.
    """
    metrics: dict = {
        "total_notes": 0,
        "track_count": len(score.tracks),
        "sections": {},
    }

    section_velocities: dict[str, list[int]] = {}

    for sec_info in enriched_sections:
        sec_name = sec_info["name"]
        s = float(sec_info["start_beat"])
        e = float(sec_info["end_beat"])
        bars = int(sec_info["bars"])
        sec_metrics: dict = {
            "tracks": {}, "total": 0, "bars": bars,
        }

        for trk in score.tracks:
            notes = [
                n for n in trk.notes if s <= n.start_beat < e
            ]
            count = len(notes)
            density = round(count / bars, 1) if bars > 0 else 0
            pitches = [n.pitch for n in notes]
            vels = [n.velocity for n in notes]
            sec_metrics["tracks"][trk.name] = {
                "note_count": count,
                "notes_per_bar": density,
                "pitch_range": (
                    (min(pitches), max(pitches)) if pitches else None
                ),
                "avg_velocity": (
                    round(sum(vels) / count) if count else 0
                ),
            }
            sec_metrics["total"] += count
            metrics["total_notes"] += count
            section_velocities.setdefault(sec_name, []).extend(vels)

        metrics["sections"][sec_name] = sec_metrics

    avg_vels = {
        name: round(sum(v) / len(v)) if v else 0
        for name, v in section_velocities.items()
    }
    metrics["section_avg_velocity"] = avg_vels

    if lyrics and score.tracks:
        melody_trk = next(
            (t for t in score.tracks
             if "melody" in t.name.lower() or t.role == "melody"),
            score.tracks[0],
        )
        melody_beats = {n.start_beat for n in melody_trk.notes}
        total_lyric_beats = 0
        aligned_beats = 0
        for block in lyrics:
            for line in block.get("lines", []):
                if isinstance(line, dict) and "start_beat" in line:
                    total_lyric_beats += 1
                    if float(line["start_beat"]) in melody_beats:
                        aligned_beats += 1
        metrics["lyrics_alignment_pct"] = (
            round(100 * aligned_beats / total_lyric_beats)
            if total_lyric_beats > 0 else 0
        )
    else:
        metrics["lyrics_alignment_pct"] = 0

    return metrics


def format_metrics_for_critic(metrics: dict) -> str:
    """Format pre-computed metrics into a text block for the Critic."""
    lines = [
        "QUANTITATIVE METRICS (computed by system, DO NOT recount):",
        f"- Total notes: {metrics['total_notes']} "
        f"across {metrics['track_count']} tracks",
        "- Section breakdown:",
    ]
    for sec_name, sec_data in metrics.get("sections", {}).items():
        track_parts = []
        for trk_name, trk_data in sec_data.get("tracks", {}).items():
            track_parts.append(
                f"{trk_name}: {trk_data['note_count']} notes "
                f"({trk_data['notes_per_bar']}/bar)"
            )
        lines.append(
            f"  [{sec_name.upper()}] {sec_data['total']} notes | "
            + " | ".join(track_parts)
        )

    avg_vels = metrics.get("section_avg_velocity", {})
    if avg_vels:
        contrast_parts = [
            f"{k}={v}" for k, v in avg_vels.items()
        ]
        lines.append(
            "- Section velocity contrast: " + ", ".join(contrast_parts)
        )

    alignment = metrics.get("lyrics_alignment_pct", 0)
    lines.append(
        f"- Lyrics alignment: {alignment}% of lyric beats "
        "match melody note positions"
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MainScore — the lead sheet that anchors the nested loop pipeline
# ---------------------------------------------------------------------------

@dataclass
class MainScore:
    """Lead sheet produced in Phase 2: melody + chords + rhythm guide + instrument plan."""

    melody: "list[ScoreNote]"
    chord_progression: list = field(default_factory=list)     # [{bar, root, quality}]
    rhythm_guide: dict = field(default_factory=dict)           # {section_name: "4-6 notes/bar"}
    instrument_plan: dict = field(default_factory=dict)        # {instrument_name: role description}

    def to_description(self, key: str = "C", scale_type: str = "major") -> str:
        """Text summary of the lead sheet for injection into agent prompts."""
        parts = [f"LEAD SHEET | key={key} {scale_type}"]

        parts.append(f"\nMELODY ({len(self.melody)} notes):")
        for n in self.melody[:20]:
            p = n.pitch if hasattr(n, "pitch") else n.get("pitch", 0)
            sb = n.start_beat if hasattr(n, "start_beat") else n.get("start_beat", 0)
            dur = n.duration_beats if hasattr(n, "duration_beats") else n.get("duration_beats", 0)
            parts.append(f"  {_pitch_name(p)} beat={sb} dur={dur}")
        if len(self.melody) > 20:
            parts.append(f"  ... ({len(self.melody) - 20} more)")

        if self.chord_progression:
            parts.append("\nCHORD PROGRESSION:")
            for c in self.chord_progression:
                parts.append(f"  bar {c.get('bar', '?')}: {c.get('root', '?')}{c.get('quality', '')}")

        if self.rhythm_guide:
            parts.append("\nRHYTHM GUIDE:")
            for sec, desc in self.rhythm_guide.items():
                parts.append(f"  {sec}: {desc}")

        if self.instrument_plan:
            parts.append("\nINSTRUMENT PLAN:")
            for inst, role in self.instrument_plan.items():
                parts.append(f"  {inst}: {role}")

        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Agent Inspection Tools — density, gaps, grids, register coverage
# ---------------------------------------------------------------------------

def _count_notes_in_bar(notes: list, bar_start: float, bar_end: float) -> int:
    """Count notes whose start_beat falls within [bar_start, bar_end)."""
    return sum(1 for n in notes if bar_start <= n.start_beat < bar_end)


def compute_density_heatmap(score: Score, beats_per_bar: int | None = None) -> str:
    """Bar-by-bar note density per track with ASCII bars and gap warnings."""
    if beats_per_bar is None:
        beats_per_bar = score.time_signature[0] if score.time_signature else 4
    total_bars = ceil(score.total_beats / beats_per_bar) if score.total_beats > 0 else 0
    if total_bars == 0 or not score.tracks:
        return "DENSITY HEATMAP: (empty score)"

    max_display = 8  # max blocks in ASCII bar

    lines = ["DENSITY HEATMAP (notes per bar):"]
    # header
    track_names = [t.name for t in score.tracks]
    header = f"{'Bar':>5} | " + " | ".join(f"{tn[:10]:^14}" for tn in track_names)
    lines.append(header)
    lines.append("-" * len(header))

    for bar_idx in range(total_bars):
        bar_start = bar_idx * beats_per_bar
        bar_end = bar_start + beats_per_bar
        cells = []
        bar_gap = True
        for trk in score.tracks:
            count = _count_notes_in_bar(trk.notes, bar_start, bar_end)
            blocks = min(count, max_display)
            bar_str = "\u2588" * blocks + "\u2591" * (max_display - blocks)
            cells.append(f"{bar_str} ({count})")
            if count > 0:
                bar_gap = False
        flag = "  \u26a0\ufe0f GAP" if bar_gap else ""
        lines.append(f"{bar_idx + 1:>5} | " + " | ".join(cells) + flag)

    return "\n".join(lines)


def compute_note_grid(
    score: Score,
    track_name: str,
    start_bar: int,
    end_bar: int,
    beats_per_bar: int | None = None,
) -> str:
    """Text piano-roll for a specific track within a bar range.

    Bars are 1-indexed. Shows beat positions, note names, durations, velocities.
    """
    if beats_per_bar is None:
        beats_per_bar = score.time_signature[0] if score.time_signature else 4
    trk = score.get_track(track_name)
    if not trk:
        return f"NOTE GRID: track '{track_name}' not found"

    grid_step = 0.5  # half-beat resolution
    lines = [f"NOTE GRID: {track_name} ({trk.instrument}), bars {start_bar}-{end_bar}"]

    for bar in range(start_bar, end_bar + 1):
        bar_start = (bar - 1) * beats_per_bar
        bar_end = bar_start + beats_per_bar
        notes_in_bar = [n for n in trk.notes if bar_start <= n.start_beat < bar_end]
        notes_in_bar.sort(key=lambda n: n.start_beat)

        beats = []
        beat = float(bar_start)
        while beat < bar_end:
            beats.append(beat)
            beat += grid_step

        beat_strs = [f"{b:>5.1f}" for b in beats]
        note_strs = []
        dur_strs = []
        vel_strs = []

        for b in beats:
            hit = next((n for n in notes_in_bar if abs(n.start_beat - b) < 0.01), None)
            if hit:
                note_strs.append(f"{_pitch_name(hit.pitch):>5}")
                dur_strs.append(f"{hit.duration_beats:>5.2f}")
                vel_strs.append(f"{hit.velocity:>5}")
            else:
                note_strs.append("  ---")
                dur_strs.append("     ")
                vel_strs.append("     ")

        lines.append(f"\n  Bar {bar} (beats {bar_start:.0f}-{bar_end:.0f}):")
        lines.append("  beat: " + " ".join(beat_strs))
        lines.append("  note: " + " ".join(note_strs))
        lines.append("  dur:  " + " ".join(dur_strs))
        lines.append("  vel:  " + " ".join(vel_strs))

    return "\n".join(lines)


def detect_gaps(
    score: Score,
    role_density_minimums: dict[str, int],
    beats_per_bar: int | None = None,
) -> str:
    """Detect bars below minimum density per instrument role.

    Args:
        role_density_minimums: {"lead": 4, "counter-melody": 2, ...}

    Returns text report of violations, or empty string if clean.
    """
    if beats_per_bar is None:
        beats_per_bar = score.time_signature[0] if score.time_signature else 4
    total_bars = ceil(score.total_beats / beats_per_bar) if score.total_beats > 0 else 0
    if total_bars == 0:
        return ""

    violations: list[str] = []
    total_below = 0

    for trk in score.tracks:
        role_key = trk.role.lower().replace(" ", "-").replace("_", "-")
        min_density = role_density_minimums.get(role_key, 0)
        if min_density == 0:
            for rk, rv in role_density_minimums.items():
                if rk in role_key or role_key in rk:
                    min_density = rv
                    break
        if min_density == 0:
            continue

        gap_bars = []
        for bar_idx in range(total_bars):
            bar_start = bar_idx * beats_per_bar
            bar_end = bar_start + beats_per_bar
            count = _count_notes_in_bar(trk.notes, bar_start, bar_end)
            if count < min_density:
                gap_bars.append(bar_idx + 1)

        if gap_bars:
            ranges = _compress_bar_ranges(gap_bars)
            violations.append(
                f"  {trk.name} ({trk.instrument}, {trk.role}): "
                f"bars {ranges} below min {min_density} notes/bar"
            )
            total_below += len(gap_bars)

    if not violations:
        return ""

    lines = [
        f"\u26a0\ufe0f GAPS DETECTED ({total_below} of {total_bars * len(score.tracks)} "
        f"track-bars below minimum):"
    ]
    lines.extend(violations)
    return "\n".join(lines)


def _compress_bar_ranges(bars: list[int]) -> str:
    """Compress [1,2,3,5,7,8] into '1-3, 5, 7-8'."""
    if not bars:
        return ""
    ranges = []
    start = bars[0]
    prev = bars[0]
    for b in bars[1:]:
        if b == prev + 1:
            prev = b
        else:
            ranges.append(f"{start}-{prev}" if start != prev else str(start))
            start = b
            prev = b
    ranges.append(f"{start}-{prev}" if start != prev else str(start))
    return ", ".join(ranges)


def compute_register_coverage(
    score: Score,
    instrument_ranges: dict[str, tuple[int, int]],
) -> str:
    """Show octave usage per instrument against expected sweet-spot range.

    Args:
        instrument_ranges: {"Guzheng": (55, 84), "Erhu": (55, 93), ...}
    """
    if not score.tracks:
        return "REGISTER COVERAGE: (no tracks)"

    total_display = 14  # total ASCII cells for C1(24) to C7(96)
    lo_midi = 24
    hi_midi = 96
    span = hi_midi - lo_midi

    lines = ["REGISTER COVERAGE:"]
    for trk in score.tracks:
        pitches = [n.pitch for n in trk.notes]
        if not pitches:
            lines.append(f"  {trk.name} ({trk.instrument}): (no notes)")
            continue

        actual_lo = min(pitches)
        actual_hi = max(pitches)

        cells = ["\u2591"] * total_display
        for p in range(actual_lo, actual_hi + 1):
            idx = int((p - lo_midi) / span * (total_display - 1))
            idx = max(0, min(total_display - 1, idx))
            cells[idx] = "\u2588"

        bar_str = "".join(cells)
        range_str = f"{_pitch_name(actual_lo)}-{_pitch_name(actual_hi)}"

        expected = instrument_ranges.get(trk.instrument)
        if expected:
            sweet_lo, sweet_hi = expected
            in_sweet = sweet_lo <= actual_lo and actual_hi <= sweet_hi
            check = "\u2713" if in_sweet else f"expected {_pitch_name(sweet_lo)}-{_pitch_name(sweet_hi)}"
            lines.append(f"  {trk.name} ({trk.instrument}): {bar_str} ({range_str}, {check})")
        else:
            lines.append(f"  {trk.name} ({trk.instrument}): {bar_str} ({range_str})")

    return "\n".join(lines)

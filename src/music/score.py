"""
Score — the central data structure that all Agents read and modify.
Represents a complete musical score with sections, tracks, and notes.
Designed to be compact enough for LLM context windows while retaining
note-level detail for precise editing.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ScoreNote(BaseModel):
    pitch: int
    start_beat: float
    duration_beats: float
    velocity: int = 80
    articulation: str = "normal"
    pitch_bend: int | None = None
    expression: int | None = None
    ornaments: list[str] = Field(default_factory=list)


class PitchBendEvent(BaseModel):
    beat: float
    value: int  # -8192..8191
    channel: int = 0


class CCEvent(BaseModel):
    beat: float
    controller: int  # 1=mod, 2=breath, 11=expression, 64=sustain
    value: int  # 0..127
    channel: int = 0


class TransitionEvent(BaseModel):
    """Round 2 Phase B4 — an ear-candy event at a section boundary.

    Two event families coexist:
      * MIDI-ish (snare_roll, kick_drop, crash) → realized by the MIDI
        writer now.
      * Sample-ish (riser, reverse_cymbal, impact, sub_drop,
        downlifter) → realized by the Phase F mix bus from the
        assets/transitions/ stem library.
    """
    beat: float
    kind: str                    # snare_roll | reverse_cymbal | riser | ...
    target_section: str = ""     # the section this transition leads INTO
    params: dict = Field(default_factory=dict)


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
    pitch_bends: list[PitchBendEvent] = Field(default_factory=list)
    cc_events: list[CCEvent] = Field(default_factory=list)
    rendered: bool = False


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
    # Round 2 Phase B4: ear-candy events at section boundaries.
    # Written by the TransitionAgent after Phase 3 completes.
    transition_events: list[TransitionEvent] = Field(default_factory=list)
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


class SpotlightEntry(BaseModel):
    """Per-section instrument activity: who plays, who features, who sits out."""
    section: str
    active: list[str] = Field(default_factory=list)
    featured: list[str] = Field(default_factory=list)
    silent: list[str] = Field(default_factory=list)


class SpotlightProposal(BaseModel):
    """Composer/Critic proposal to modify the spotlight plan for a section."""
    section: str
    add_instruments: list[str] = Field(default_factory=list)
    remove_instruments: list[str] = Field(default_factory=list)
    reasoning: str = ""
    confidence: float = 0.0


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
    spotlight_plan: list[SpotlightEntry] = Field(default_factory=list)


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

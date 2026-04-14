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
        lines = [
            f"# {self.title} | {self.key} {self.scale_type} | "
            f"{self.tempo}bpm | {self.time_signature[0]}/{self.time_signature[1]}"
        ]
        for sec in self.sections:
            chords_str = " → ".join(
                f"{c.get('root', '?')}{c.get('quality', '')}" for c in sec.chords
            )
            lines.append(f"## {sec.name} ({sec.bars} bars): {chords_str}")
        for trk in self.tracks:
            lines.append(
                f"Track [{trk.name}] ({trk.role}): {len(trk.notes)} notes, ch={trk.channel}"
            )
        return "\n".join(lines)

    def get_section_notes(self, section_name: str, track_name: str) -> list[ScoreNote]:
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
        return (self.total_beats / self.tempo) * 60.0 if self.tempo > 0 else 0.0


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

"""
Core music data models used across the entire system.
All musical concepts are represented as structured, serializable objects.
"""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class NoteName(str, Enum):
    C = "C"; Cs = "C#"; D = "D"; Ds = "D#"
    E = "E"; F = "F"; Fs = "F#"; G = "G"
    Gs = "G#"; A = "A"; As = "A#"; B = "B"


class ChordQuality(str, Enum):
    MAJOR = "major"
    MINOR = "minor"
    DIMINISHED = "dim"
    AUGMENTED = "aug"
    DOMINANT7 = "7"
    MAJOR7 = "maj7"
    MINOR7 = "min7"
    SUS2 = "sus2"
    SUS4 = "sus4"


class ScaleType(str, Enum):
    MAJOR = "major"
    MINOR = "minor"
    HARMONIC_MINOR = "harmonic_minor"
    MELODIC_MINOR = "melodic_minor"
    PENTATONIC_MAJOR = "pentatonic_major"
    PENTATONIC_MINOR = "pentatonic_minor"
    BLUES = "blues"
    DORIAN = "dorian"
    MIXOLYDIAN = "mixolydian"
    LYDIAN = "lydian"
    PHRYGIAN = "phrygian"
    # 东方音阶
    CHINESE_PENTATONIC = "chinese_pentatonic"
    JAPANESE_IN = "japanese_in"
    JAPANESE_YO = "japanese_yo"


class ArticulationType(str, Enum):
    NORMAL = "normal"
    LEGATO = "legato"
    STACCATO = "staccato"
    ACCENT = "accent"
    TREMOLO = "tremolo"
    GLISSANDO = "glissando"
    BEND = "bend"
    VIBRATO = "vibrato"
    TRILL = "trill"
    HARMONICS = "harmonics"
    # 东方乐器特殊技法
    GUZHENG_GLISS = "guzheng_gliss"     # 古筝刮奏
    ERHU_PORTAMENTO = "erhu_portamento" # 二胡滑音
    PIPA_TREMOLO = "pipa_tremolo"       # 琵琶轮指


# ---------------------------------------------------------------------------
# Core Music Objects
# ---------------------------------------------------------------------------

class Note(BaseModel):
    """A single MIDI note event."""
    pitch: int = Field(ge=0, le=127, description="MIDI pitch number")
    velocity: int = Field(default=80, ge=0, le=127)
    start_beat: float = Field(ge=0.0, description="Start position in beats")
    duration_beats: float = Field(gt=0.0, description="Duration in beats")
    articulation: ArticulationType = ArticulationType.NORMAL
    pitch_bend: int | None = Field(default=None, ge=-8192, le=8191)
    expression: int | None = Field(default=None, ge=0, le=127)

    @property
    def end_beat(self) -> float:
        return self.start_beat + self.duration_beats

    @property
    def note_name(self) -> str:
        names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        return f"{names[self.pitch % 12]}{self.pitch // 12 - 1}"


class Chord(BaseModel):
    """A chord symbol with timing."""
    root: NoteName
    quality: ChordQuality = ChordQuality.MAJOR
    start_beat: float = Field(ge=0.0)
    duration_beats: float = Field(gt=0.0)
    inversion: int = Field(default=0, ge=0, le=3)

    @property
    def symbol(self) -> str:
        q_map = {
            ChordQuality.MAJOR: "", ChordQuality.MINOR: "m",
            ChordQuality.DIMINISHED: "dim", ChordQuality.AUGMENTED: "aug",
            ChordQuality.DOMINANT7: "7", ChordQuality.MAJOR7: "maj7",
            ChordQuality.MINOR7: "m7", ChordQuality.SUS2: "sus2",
            ChordQuality.SUS4: "sus4",
        }
        return f"{self.root.value}{q_map[self.quality]}"


class ChordProgression(BaseModel):
    """An ordered sequence of chords."""
    chords: list[Chord]
    key: NoteName = NoteName.C
    scale_type: ScaleType = ScaleType.MAJOR

    @property
    def total_beats(self) -> float:
        if not self.chords:
            return 0.0
        last = self.chords[-1]
        return last.start_beat + last.duration_beats


class LyricSyllable(BaseModel):
    """A single syllable aligned to a musical beat."""
    text: str
    start_beat: float
    duration_beats: float


class LyricLine(BaseModel):
    """A line of lyrics with beat-aligned syllables."""
    syllables: list[LyricSyllable]
    raw_text: str = ""


class Track(BaseModel):
    """A single instrument track."""
    name: str
    instrument: str
    channel: int = Field(default=0, ge=0, le=15)
    notes: list[Note] = Field(default_factory=list)
    is_drum: bool = False
    program_number: int = Field(default=0, ge=0, le=127, description="General MIDI program")
    vst_plugin: str | None = None
    vst_preset: str | None = None

    @property
    def total_beats(self) -> float:
        if not self.notes:
            return 0.0
        return max(n.end_beat for n in self.notes)


class Section(BaseModel):
    """A musical section (intro, verse, chorus, bridge, outro)."""
    name: str
    start_beat: float
    duration_beats: float
    chord_progression: ChordProgression | None = None
    lyrics: list[LyricLine] = Field(default_factory=list)


class Arrangement(BaseModel):
    """The complete musical arrangement — the final output of the pipeline."""
    title: str = "Untitled"
    tempo: int = Field(default=120, gt=20, lt=300)
    time_signature: tuple[int, int] = (4, 4)
    key: NoteName = NoteName.C
    scale_type: ScaleType = ScaleType.MAJOR
    tracks: list[Track] = Field(default_factory=list)
    sections: list[Section] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

    @property
    def total_beats(self) -> float:
        track_max = max((t.total_beats for t in self.tracks), default=0.0)
        section_max = max(
            (s.start_beat + s.duration_beats for s in self.sections), default=0.0
        )
        return max(track_max, section_max)

    @property
    def duration_seconds(self) -> float:
        return (self.total_beats / self.tempo) * 60.0


# ---------------------------------------------------------------------------
# User Request Model
# ---------------------------------------------------------------------------

class InstrumentRequest(BaseModel):
    """User-specified instrument configuration."""
    name: str
    role: str = "accompaniment"  # "lead", "accompaniment", "bass", "drums", "pad"
    vst_plugin: str | None = None
    vst_preset: str | None = None


class MusicRequest(BaseModel):
    """The top-level user input for music generation."""
    description: str = Field(description="Natural language description of desired music")
    genre: str = "pop"
    mood: str = "neutral"
    tempo: int | None = None
    key: str | None = None
    scale_type: str | None = None
    time_signature: tuple[int, int] | None = None
    instruments: list[InstrumentRequest] = Field(default_factory=list)
    sections: list[str] = Field(
        default_factory=lambda: ["intro", "verse", "chorus", "verse", "chorus", "outro"]
    )
    bars_per_section: int = 8
    include_lyrics: bool = False
    lyric_language: str = "en"
    lyric_theme: str = ""
    reference_style: str | None = None

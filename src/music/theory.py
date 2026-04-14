"""
Music theory utilities: scales, chord voicings, interval calculations,
and cross-cultural scale support.
"""

from __future__ import annotations

from src.music.models import NoteName, ScaleType, ChordQuality

# MIDI note number for C4
_C4 = 60

NOTE_TO_SEMITONE: dict[str, int] = {
    "C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5,
    "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11,
}

SEMITONE_TO_NOTE: dict[int, str] = {v: k for k, v in NOTE_TO_SEMITONE.items()}

# ---------------------------------------------------------------------------
# Scale intervals (semitones from root)
# ---------------------------------------------------------------------------
SCALE_INTERVALS: dict[ScaleType, list[int]] = {
    ScaleType.MAJOR:            [0, 2, 4, 5, 7, 9, 11],
    ScaleType.MINOR:            [0, 2, 3, 5, 7, 8, 10],
    ScaleType.HARMONIC_MINOR:   [0, 2, 3, 5, 7, 8, 11],
    ScaleType.MELODIC_MINOR:    [0, 2, 3, 5, 7, 9, 11],
    ScaleType.PENTATONIC_MAJOR: [0, 2, 4, 7, 9],
    ScaleType.PENTATONIC_MINOR: [0, 3, 5, 7, 10],
    ScaleType.BLUES:            [0, 3, 5, 6, 7, 10],
    ScaleType.DORIAN:           [0, 2, 3, 5, 7, 9, 10],
    ScaleType.MIXOLYDIAN:       [0, 2, 4, 5, 7, 9, 10],
    ScaleType.LYDIAN:           [0, 2, 4, 6, 7, 9, 11],
    ScaleType.PHRYGIAN:         [0, 1, 3, 5, 7, 8, 10],
    # 东方音阶
    ScaleType.CHINESE_PENTATONIC: [0, 2, 4, 7, 9],       # 宫商角徵羽
    ScaleType.JAPANESE_IN:        [0, 1, 5, 7, 8],       # 都節音階
    ScaleType.JAPANESE_YO:        [0, 2, 5, 7, 9],       # 律音階
}

# Chord intervals (semitones from root)
CHORD_INTERVALS: dict[ChordQuality, list[int]] = {
    ChordQuality.MAJOR:      [0, 4, 7],
    ChordQuality.MINOR:      [0, 3, 7],
    ChordQuality.DIMINISHED: [0, 3, 6],
    ChordQuality.AUGMENTED:  [0, 4, 8],
    ChordQuality.DOMINANT7:  [0, 4, 7, 10],
    ChordQuality.MAJOR7:     [0, 4, 7, 11],
    ChordQuality.MINOR7:     [0, 3, 7, 10],
    ChordQuality.SUS2:       [0, 2, 7],
    ChordQuality.SUS4:       [0, 5, 7],
}

# Common chord progressions by Roman numeral degree (0-indexed scale degrees)
COMMON_PROGRESSIONS: dict[str, list[tuple[int, ChordQuality]]] = {
    "I-V-vi-IV": [
        (0, ChordQuality.MAJOR), (4, ChordQuality.MAJOR),
        (5, ChordQuality.MINOR), (3, ChordQuality.MAJOR),
    ],
    "I-IV-V-I": [
        (0, ChordQuality.MAJOR), (3, ChordQuality.MAJOR),
        (4, ChordQuality.MAJOR), (0, ChordQuality.MAJOR),
    ],
    "ii-V-I": [
        (1, ChordQuality.MINOR), (4, ChordQuality.MAJOR),
        (0, ChordQuality.MAJOR),
    ],
    "vi-IV-I-V": [
        (5, ChordQuality.MINOR), (3, ChordQuality.MAJOR),
        (0, ChordQuality.MAJOR), (4, ChordQuality.MAJOR),
    ],
    "I-vi-IV-V": [
        (0, ChordQuality.MAJOR), (5, ChordQuality.MINOR),
        (3, ChordQuality.MAJOR), (4, ChordQuality.MAJOR),
    ],
    "i-iv-v-i": [
        (0, ChordQuality.MINOR), (3, ChordQuality.MINOR),
        (4, ChordQuality.MINOR), (0, ChordQuality.MINOR),
    ],
    "i-VI-III-VII": [
        (0, ChordQuality.MINOR), (5, ChordQuality.MAJOR),
        (2, ChordQuality.MAJOR), (6, ChordQuality.MAJOR),
    ],
    "12-bar-blues": [
        (0, ChordQuality.DOMINANT7), (0, ChordQuality.DOMINANT7),
        (0, ChordQuality.DOMINANT7), (0, ChordQuality.DOMINANT7),
        (3, ChordQuality.DOMINANT7), (3, ChordQuality.DOMINANT7),
        (0, ChordQuality.DOMINANT7), (0, ChordQuality.DOMINANT7),
        (4, ChordQuality.DOMINANT7), (3, ChordQuality.DOMINANT7),
        (0, ChordQuality.DOMINANT7), (4, ChordQuality.DOMINANT7),
    ],
}

# General MIDI program numbers for common instruments
GM_INSTRUMENTS: dict[str, int] = {
    "piano": 0, "bright_piano": 1, "electric_piano": 4,
    "harpsichord": 6, "celesta": 8, "glockenspiel": 9,
    "vibraphone": 11, "marimba": 12, "xylophone": 13,
    "organ": 19, "accordion": 21,
    "acoustic_guitar": 25, "electric_guitar_clean": 27,
    "electric_guitar_distortion": 30, "bass": 33,
    "electric_bass": 34, "slap_bass": 36,
    "violin": 40, "viola": 41, "cello": 42, "contrabass": 43,
    "strings_ensemble": 48, "synth_strings": 50,
    "choir": 52, "voice_oohs": 53,
    "trumpet": 56, "trombone": 57, "tuba": 58,
    "french_horn": 60, "brass_section": 61,
    "soprano_sax": 64, "alto_sax": 65, "tenor_sax": 66,
    "flute": 73, "recorder": 74, "pan_flute": 75,
    "shakuhachi": 77, "whistle": 78,
    "sitar": 104, "banjo": 105, "shamisen": 106, "koto": 107,
    "kalimba": 108, "bagpipe": 109,
    "synth_lead": 80, "synth_pad": 88,
    # 东方乐器 (需通过 VST 实现，GM 仅做映射占位)
    "guzheng": 107, "erhu": 110, "pipa": 105, "dizi": 73,
    "xiao": 77, "yangqin": 15,
}


def note_name_to_midi(name: str, octave: int = 4) -> int:
    return NOTE_TO_SEMITONE[name] + (octave + 1) * 12


def midi_to_note_name(midi: int) -> tuple[str, int]:
    return SEMITONE_TO_NOTE[midi % 12], midi // 12 - 1


def get_scale_pitches(root: str | NoteName, scale_type: ScaleType, octave: int = 4) -> list[int]:
    """Return MIDI pitch numbers for one octave of the given scale."""
    root_str = root.value if isinstance(root, NoteName) else root
    base = note_name_to_midi(root_str, octave)
    return [base + i for i in SCALE_INTERVALS[scale_type]]


def get_scale_pitches_range(
    root: str | NoteName, scale_type: ScaleType,
    low: int = 48, high: int = 84,
) -> list[int]:
    """Return all scale pitches within a MIDI range."""
    root_str = root.value if isinstance(root, NoteName) else root
    root_semitone = NOTE_TO_SEMITONE[root_str]
    intervals = SCALE_INTERVALS[scale_type]
    pitches: list[int] = []
    for midi in range(low, high + 1):
        if (midi - root_semitone) % 12 in intervals:
            pitches.append(midi)
    return pitches


def get_chord_pitches(
    root: str | NoteName, quality: ChordQuality, octave: int = 4, inversion: int = 0,
) -> list[int]:
    """Return MIDI pitches for a chord voicing."""
    root_str = root.value if isinstance(root, NoteName) else root
    base = note_name_to_midi(root_str, octave)
    pitches = [base + i for i in CHORD_INTERVALS[quality]]
    for i in range(min(inversion, len(pitches))):
        pitches[i] += 12
    pitches.sort()
    return pitches


def get_diatonic_chords(root: str | NoteName, scale_type: ScaleType) -> list[tuple[str, ChordQuality]]:
    """Return the diatonic triads for a scale (7 chords for heptatonic, fewer for pentatonic)."""
    intervals = SCALE_INTERVALS[scale_type]
    root_str = root.value if isinstance(root, NoteName) else root
    root_semi = NOTE_TO_SEMITONE[root_str]
    chords: list[tuple[str, ChordQuality]] = []
    for i, semi in enumerate(intervals):
        chord_root_semi = (root_semi + semi) % 12
        chord_root_name = SEMITONE_TO_NOTE[chord_root_semi]
        if len(intervals) < 7:
            chords.append((chord_root_name, ChordQuality.MAJOR))
            continue
        third = (intervals[(i + 2) % 7] - semi) % 12
        fifth = (intervals[(i + 4) % 7] - semi) % 12
        if third == 4 and fifth == 7:
            quality = ChordQuality.MAJOR
        elif third == 3 and fifth == 7:
            quality = ChordQuality.MINOR
        elif third == 3 and fifth == 6:
            quality = ChordQuality.DIMINISHED
        else:
            quality = ChordQuality.MAJOR
        chords.append((chord_root_name, quality))
    return chords


def interval_semitones(note_a: int, note_b: int) -> int:
    return abs(note_b - note_a)


def transpose_pitch(pitch: int, semitones: int) -> int:
    return max(0, min(127, pitch + semitones))

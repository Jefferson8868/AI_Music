"""
Symbolic music generation engine.
Provides algorithmic composition tools: Markov chains, constrained random walks,
rhythm generators, and chord-aware melody construction.
"""

from __future__ import annotations

import random
from collections import defaultdict

from src.music.models import (
    Note, Chord, ChordProgression, Track, Section, Arrangement,
    NoteName, ChordQuality, ScaleType, ArticulationType,
)
from src.music.theory import (
    get_scale_pitches_range, get_chord_pitches, note_name_to_midi,
    SCALE_INTERVALS, NOTE_TO_SEMITONE, GM_INSTRUMENTS,
)


class MarkovMelodyGenerator:
    """
    First-order Markov chain over scale degrees.
    Trained on interval transitions; generates melodies that respect
    the given scale and chord context.
    """

    def __init__(self, order: int = 1):
        self.order = order
        self.transitions: dict[tuple[int, ...], list[int]] = defaultdict(list)
        self._build_default_transitions()

    def _build_default_transitions(self) -> None:
        """Pre-populate with musically sensible interval transitions."""
        common_intervals = [0, 1, 2, -1, -2, 3, -3, 4, -4, 5, -5, 7, -7]
        weights = [3, 5, 5, 5, 5, 3, 3, 2, 2, 1, 1, 1, 1]
        for prev_interval in range(-7, 8):
            for interval, weight in zip(common_intervals, weights):
                step_weight = weight
                # Prefer stepwise motion after leaps
                if abs(prev_interval) > 3 and abs(interval) <= 2:
                    step_weight += 3
                # Avoid consecutive large leaps
                if abs(prev_interval) > 4 and abs(interval) > 4:
                    step_weight = max(1, step_weight - 3)
                self.transitions[(prev_interval,)].extend([interval] * step_weight)

    def generate_intervals(self, length: int, seed_interval: int = 0) -> list[int]:
        intervals = [seed_interval]
        state = (seed_interval,)
        for _ in range(length - 1):
            candidates = self.transitions.get(state, self.transitions[(0,)])
            interval = random.choice(candidates)
            intervals.append(interval)
            state = (interval,)
        return intervals


class RhythmGenerator:
    """Generates rhythmic patterns based on time signature and style density."""

    PATTERN_PRESETS: dict[str, list[list[float]]] = {
        "quarter": [[1.0, 1.0, 1.0, 1.0]],
        "eighth": [[0.5] * 8],
        "syncopated": [[1.0, 0.5, 0.5, 0.5, 0.5, 1.0]],
        "dotted": [[1.5, 0.5, 1.5, 0.5]],
        "waltz": [[1.5, 0.75, 0.75]],
        "triplet": [[1.0/3] * 12],
        "ballad": [[2.0, 1.0, 1.0]],
        "driving": [[0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]],
    }

    @classmethod
    def generate_pattern(
        cls, beats_per_bar: int = 4, bars: int = 4,
        density: float = 0.7, style: str = "quarter",
    ) -> list[tuple[float, float]]:
        """
        Returns list of (start_beat, duration) relative to bar start.
        density in [0, 1] controls rest probability.
        """
        total_beats = beats_per_bar * bars
        presets = cls.PATTERN_PRESETS.get(style, cls.PATTERN_PRESETS["quarter"])
        base_pattern = random.choice(presets)

        events: list[tuple[float, float]] = []
        beat = 0.0
        idx = 0
        while beat < total_beats:
            dur = base_pattern[idx % len(base_pattern)]
            if beat + dur > total_beats:
                dur = total_beats - beat
            if random.random() < density:
                events.append((beat, dur))
            beat += dur
            idx += 1
        return events


class ChordProgressionGenerator:
    """Generates chord progressions using diatonic harmony rules."""

    # Transition probabilities between scale degrees (1-indexed)
    DEGREE_TRANSITIONS: dict[int, list[tuple[int, float]]] = {
        1: [(4, 0.3), (5, 0.25), (6, 0.2), (2, 0.15), (3, 0.1)],
        2: [(5, 0.5), (4, 0.2), (7, 0.15), (1, 0.15)],
        3: [(4, 0.3), (6, 0.35), (2, 0.2), (1, 0.15)],
        4: [(5, 0.35), (1, 0.25), (2, 0.2), (6, 0.2)],
        5: [(1, 0.45), (6, 0.25), (4, 0.15), (3, 0.15)],
        6: [(4, 0.3), (2, 0.25), (5, 0.25), (3, 0.2)],
        7: [(1, 0.5), (3, 0.2), (6, 0.15), (5, 0.15)],
    }

    DIATONIC_QUALITY_MAJOR = {
        1: ChordQuality.MAJOR, 2: ChordQuality.MINOR, 3: ChordQuality.MINOR,
        4: ChordQuality.MAJOR, 5: ChordQuality.MAJOR, 6: ChordQuality.MINOR,
        7: ChordQuality.DIMINISHED,
    }

    DIATONIC_QUALITY_MINOR = {
        1: ChordQuality.MINOR, 2: ChordQuality.DIMINISHED, 3: ChordQuality.MAJOR,
        4: ChordQuality.MINOR, 5: ChordQuality.MINOR, 6: ChordQuality.MAJOR,
        7: ChordQuality.MAJOR,
    }

    @classmethod
    def generate(
        cls,
        key: NoteName = NoteName.C,
        scale_type: ScaleType = ScaleType.MAJOR,
        num_chords: int = 4,
        beats_per_chord: float = 4.0,
        start_degree: int = 1,
    ) -> ChordProgression:
        intervals = SCALE_INTERVALS.get(scale_type, SCALE_INTERVALS[ScaleType.MAJOR])
        root_semi = NOTE_TO_SEMITONE[key.value]

        quality_map = (
            cls.DIATONIC_QUALITY_MAJOR
            if scale_type in (ScaleType.MAJOR, ScaleType.LYDIAN, ScaleType.MIXOLYDIAN)
            else cls.DIATONIC_QUALITY_MINOR
        )

        degrees = [start_degree]
        current = start_degree
        for _ in range(num_chords - 1):
            transitions = cls.DEGREE_TRANSITIONS.get(current, [(1, 1.0)])
            targets, weights = zip(*transitions)
            current = random.choices(targets, weights=weights, k=1)[0]
            degrees.append(current)

        chords: list[Chord] = []
        for i, deg in enumerate(degrees):
            if deg - 1 < len(intervals):
                semi_offset = intervals[deg - 1]
            else:
                semi_offset = intervals[(deg - 1) % len(intervals)]
            chord_root_semi = (root_semi + semi_offset) % 12
            from src.music.theory import SEMITONE_TO_NOTE
            chord_root_name = SEMITONE_TO_NOTE[chord_root_semi]
            quality = quality_map.get(deg, ChordQuality.MAJOR)

            chords.append(Chord(
                root=NoteName(chord_root_name),
                quality=quality,
                start_beat=i * beats_per_chord,
                duration_beats=beats_per_chord,
            ))

        return ChordProgression(chords=chords, key=key, scale_type=scale_type)


class MelodyGenerator:
    """
    High-level melody generator that combines Markov chains
    with chord-tone targeting and scale constraints.
    """

    def __init__(
        self,
        key: NoteName = NoteName.C,
        scale_type: ScaleType = ScaleType.MAJOR,
        octave_range: tuple[int, int] = (4, 5),
    ):
        self.key = key
        self.scale_type = scale_type
        self.low = octave_range[0] * 12 + NOTE_TO_SEMITONE[key.value]
        self.high = octave_range[1] * 12 + NOTE_TO_SEMITONE[key.value] + 12
        self.scale_pitches = get_scale_pitches_range(key, scale_type, self.low, self.high)
        self.markov = MarkovMelodyGenerator()

    def _snap_to_scale(self, pitch: int) -> int:
        if pitch in self.scale_pitches:
            return pitch
        closest = min(self.scale_pitches, key=lambda p: abs(p - pitch))
        return closest

    def _index_in_scale(self, pitch: int) -> int:
        snapped = self._snap_to_scale(pitch)
        if snapped in self.scale_pitches:
            return self.scale_pitches.index(snapped)
        return 0

    def generate(
        self,
        chord_progression: ChordProgression,
        rhythm_pattern: list[tuple[float, float]],
        velocity_base: int = 80,
        velocity_variation: int = 15,
    ) -> list[Note]:
        """
        Generate a melody that follows the chord progression,
        using the rhythm pattern for timing.
        """
        if not self.scale_pitches:
            return []

        notes: list[Note] = []
        start_pitch_idx = len(self.scale_pitches) // 2
        current_idx = start_pitch_idx

        for start_beat, duration in rhythm_pattern:
            current_chord = self._get_chord_at_beat(chord_progression, start_beat)
            chord_tones = self._get_chord_tones(current_chord) if current_chord else []

            # On strong beats, prefer chord tones
            is_strong_beat = (start_beat % (chord_progression.chords[0].duration_beats if chord_progression.chords else 4)) < 0.01
            if is_strong_beat and chord_tones:
                target = random.choice(chord_tones)
                target_idx = self._index_in_scale(target)
            else:
                intervals = self.markov.generate_intervals(2, seed_interval=0)
                step = intervals[-1]
                target_idx = max(0, min(len(self.scale_pitches) - 1, current_idx + step))

            current_idx = target_idx
            pitch = self.scale_pitches[current_idx]
            vel = max(1, min(127, velocity_base + random.randint(-velocity_variation, velocity_variation)))

            notes.append(Note(
                pitch=pitch,
                velocity=vel,
                start_beat=start_beat,
                duration_beats=duration * 0.9,
            ))

        return notes

    def _get_chord_at_beat(self, prog: ChordProgression, beat: float) -> Chord | None:
        for chord in prog.chords:
            if chord.start_beat <= beat < chord.start_beat + chord.duration_beats:
                return chord
        return prog.chords[-1] if prog.chords else None

    def _get_chord_tones(self, chord: Chord) -> list[int]:
        """Get chord tones within the melody's pitch range."""
        tones: list[int] = []
        for octave in range(self.low // 12, self.high // 12 + 1):
            for p in get_chord_pitches(chord.root, chord.quality, octave - 1):
                if self.low <= p <= self.high:
                    tones.append(p)
        return tones


class BasslineGenerator:
    """Generates bass lines from chord progressions."""

    @staticmethod
    def generate(
        chord_progression: ChordProgression,
        style: str = "root",
        octave: int = 2,
    ) -> list[Note]:
        notes: list[Note] = []
        for chord in chord_progression.chords:
            root_pitch = note_name_to_midi(chord.root.value, octave)

            if style == "root":
                notes.append(Note(
                    pitch=root_pitch, velocity=90,
                    start_beat=chord.start_beat,
                    duration_beats=chord.duration_beats * 0.9,
                ))
            elif style == "walking":
                chord_pitches = get_chord_pitches(chord.root, chord.quality, octave)
                beat = chord.start_beat
                step_dur = chord.duration_beats / len(chord_pitches)
                for p in chord_pitches:
                    notes.append(Note(
                        pitch=p, velocity=85,
                        start_beat=beat, duration_beats=step_dur * 0.85,
                    ))
                    beat += step_dur
            elif style == "octave":
                half = chord.duration_beats / 2
                notes.append(Note(
                    pitch=root_pitch, velocity=90,
                    start_beat=chord.start_beat, duration_beats=half * 0.9,
                ))
                notes.append(Note(
                    pitch=root_pitch + 12, velocity=80,
                    start_beat=chord.start_beat + half, duration_beats=half * 0.9,
                ))

        return notes


class DrumPatternGenerator:
    """Generates drum patterns using General MIDI drum mapping (channel 9)."""

    # GM drum map
    KICK = 36
    SNARE = 38
    CLOSED_HH = 42
    OPEN_HH = 46
    CRASH = 49
    RIDE = 51
    TOM_HIGH = 50
    TOM_MID = 47
    TOM_LOW = 45

    PRESETS: dict[str, dict[str, list[float]]] = {
        "basic_rock": {
            "kick":      [0.0, 2.0],
            "snare":     [1.0, 3.0],
            "closed_hh": [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5],
        },
        "ballad": {
            "kick":      [0.0, 2.5],
            "snare":     [1.0, 3.0],
            "closed_hh": [0.0, 1.0, 2.0, 3.0],
        },
        "dance": {
            "kick":      [0.0, 1.0, 2.0, 3.0],
            "snare":     [1.0, 3.0],
            "closed_hh": [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5],
            "open_hh":   [0.5, 2.5],
        },
        "jazz_swing": {
            "ride":      [0.0, 1.0, 1.67, 2.0, 3.0, 3.67],
            "kick":      [0.0, 2.5],
            "snare":     [1.0, 3.0],
        },
    }

    DRUM_MAP = {
        "kick": KICK, "snare": SNARE, "closed_hh": CLOSED_HH,
        "open_hh": OPEN_HH, "crash": CRASH, "ride": RIDE,
        "tom_high": TOM_HIGH, "tom_mid": TOM_MID, "tom_low": TOM_LOW,
    }

    @classmethod
    def generate(
        cls, bars: int = 4, beats_per_bar: int = 4,
        style: str = "basic_rock", humanize: float = 0.02,
    ) -> list[Note]:
        preset = cls.PRESETS.get(style, cls.PRESETS["basic_rock"])
        notes: list[Note] = []

        for bar in range(bars):
            bar_offset = bar * beats_per_bar
            for drum_name, beats in preset.items():
                pitch = cls.DRUM_MAP.get(drum_name, cls.KICK)
                vel_base = 100 if drum_name in ("kick", "snare") else 75
                for beat in beats:
                    if beat >= beats_per_bar:
                        continue
                    timing_offset = random.uniform(-humanize, humanize)
                    vel = max(1, min(127, vel_base + random.randint(-10, 10)))
                    notes.append(Note(
                        pitch=pitch,
                        velocity=vel,
                        start_beat=bar_offset + beat + timing_offset,
                        duration_beats=0.25,
                    ))

        # Add crash on beat 1 of bar 1
        if bars > 0:
            notes.append(Note(pitch=cls.CRASH, velocity=100, start_beat=0.0, duration_beats=1.0))

        return notes


def build_arrangement_from_plan(
    title: str,
    key: NoteName,
    scale_type: ScaleType,
    tempo: int,
    time_sig: tuple[int, int],
    sections_plan: list[dict],
    instruments: list[dict],
) -> Arrangement:
    """
    Construct a full Arrangement from a structured plan (typically from the Orchestrator).

    sections_plan: list of {"name": str, "bars": int, "chord_pattern": str}
    instruments: list of {"name": str, "role": str, "program": int}
    """
    beats_per_bar = time_sig[0]
    arrangement = Arrangement(
        title=title, tempo=tempo, time_signature=time_sig,
        key=key, scale_type=scale_type,
    )

    beat_cursor = 0.0
    sections: list[Section] = []

    for sp in sections_plan:
        section_bars = sp.get("bars", 8)
        section_beats = section_bars * beats_per_bar
        chords_per_bar = sp.get("chords_per_bar", 1)
        total_chords = section_bars * chords_per_bar
        beats_per_chord = section_beats / total_chords

        chord_prog = ChordProgressionGenerator.generate(
            key=key, scale_type=scale_type,
            num_chords=total_chords, beats_per_chord=beats_per_chord,
        )
        # Offset chord positions
        for c in chord_prog.chords:
            c.start_beat += beat_cursor

        sections.append(Section(
            name=sp["name"],
            start_beat=beat_cursor,
            duration_beats=section_beats,
            chord_progression=chord_prog,
        ))
        beat_cursor += section_beats

    arrangement.sections = sections

    # Generate tracks per instrument
    for inst in instruments:
        role = inst.get("role", "accompaniment")
        inst_name = inst.get("name", "piano")
        program = inst.get("program", GM_INSTRUMENTS.get(inst_name, 0))
        channel = inst.get("channel", 0)

        track = Track(
            name=inst_name, instrument=inst_name,
            channel=channel, program_number=program,
        )

        all_notes: list[Note] = []
        for section in arrangement.sections:
            cp = section.chord_progression
            if cp is None:
                continue

            if role == "lead":
                rhythm = RhythmGenerator.generate_pattern(
                    beats_per_bar=beats_per_bar,
                    bars=int(section.duration_beats / beats_per_bar),
                    density=0.8,
                )
                offset_rhythm = [(r[0] + section.start_beat, r[1]) for r in rhythm]
                melody_gen = MelodyGenerator(key=key, scale_type=scale_type)
                all_notes.extend(melody_gen.generate(cp, offset_rhythm))

            elif role == "bass":
                bass_notes = BasslineGenerator.generate(cp, style="walking", octave=2)
                all_notes.extend(bass_notes)

            elif role == "drums":
                drum_notes = DrumPatternGenerator.generate(
                    bars=int(section.duration_beats / beats_per_bar),
                    beats_per_bar=beats_per_bar,
                )
                for n in drum_notes:
                    n.start_beat += section.start_beat
                all_notes.extend(drum_notes)

            elif role == "accompaniment":
                for chord in cp.chords:
                    pitches = get_chord_pitches(chord.root, chord.quality, 4)
                    for p in pitches:
                        all_notes.append(Note(
                            pitch=p, velocity=65,
                            start_beat=chord.start_beat,
                            duration_beats=chord.duration_beats * 0.9,
                        ))

        track.notes = all_notes
        track.is_drum = (role == "drums")
        if track.is_drum:
            track.channel = 9
        arrangement.tracks.append(track)

    return arrangement

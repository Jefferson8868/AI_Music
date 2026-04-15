"""
MIDI file writer. Converts Arrangement objects into standard MIDI files
using the mido library.
"""

from __future__ import annotations

from pathlib import Path
import mido

from src.music.models import Arrangement, Track, Note, ArticulationType


def _beats_to_ticks(beats: float, ticks_per_beat: int) -> int:
    return int(beats * ticks_per_beat)


def _build_pitch_bend_events(note: Note, ticks_per_beat: int, channel: int) -> list[tuple[int, mido.Message]]:
    """Generate pitch bend messages for special articulations."""
    events: list[tuple[int, mido.Message]] = []
    start_tick = _beats_to_ticks(note.start_beat, ticks_per_beat)

    if note.articulation == ArticulationType.BEND and note.pitch_bend is not None:
        events.append((start_tick, mido.Message(
            "pitchwheel", pitch=note.pitch_bend, channel=channel,
        )))
        end_tick = _beats_to_ticks(note.end_beat, ticks_per_beat)
        events.append((end_tick, mido.Message(
            "pitchwheel", pitch=0, channel=channel,
        )))
    elif note.articulation in (
        ArticulationType.GLISSANDO,
        ArticulationType.GUZHENG_GLISS,
        ArticulationType.ERHU_PORTAMENTO,
    ):
        dur_ticks = _beats_to_ticks(note.duration_beats, ticks_per_beat)
        steps = 16
        for i in range(steps):
            t = start_tick + (dur_ticks * i // steps)
            bend = int(8191 * (i / steps)) if note.pitch_bend is None else int(note.pitch_bend * (i / steps))
            events.append((t, mido.Message("pitchwheel", pitch=bend, channel=channel)))
        events.append((start_tick + dur_ticks, mido.Message("pitchwheel", pitch=0, channel=channel)))

    if note.expression is not None:
        events.append((start_tick, mido.Message(
            "control_change", control=11, value=note.expression, channel=channel,
        )))

    return events


def arrangement_to_midi(arrangement: Arrangement, ticks_per_beat: int = 480) -> mido.MidiFile:
    """Convert an Arrangement into a mido MidiFile."""
    mid = mido.MidiFile(ticks_per_beat=ticks_per_beat)

    # Tempo track
    tempo_track = mido.MidiTrack()
    mid.tracks.append(tempo_track)
    tempo_track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(arrangement.tempo), time=0))

    numerator, denominator = arrangement.time_signature
    denom_power = {1: 0, 2: 1, 4: 2, 8: 3, 16: 4}.get(denominator, 2)
    tempo_track.append(mido.MetaMessage(
        "time_signature", numerator=numerator, denominator=denom_power,
        clocks_per_click=24, notated_32nd_notes_per_beat=8, time=0,
    ))
    tempo_track.append(mido.MetaMessage("track_name", name=arrangement.title, time=0))

    for track in arrangement.tracks:
        midi_track = _track_to_midi(track, ticks_per_beat)
        mid.tracks.append(midi_track)

    return mid


def _track_to_midi(track: Track, ticks_per_beat: int) -> mido.MidiTrack:
    midi_track = mido.MidiTrack()
    midi_track.append(mido.MetaMessage("track_name", name=track.name, time=0))

    ch = track.channel
    if not track.is_drum:
        midi_track.append(mido.Message(
            "program_change", program=track.program_number, channel=ch, time=0,
        ))

    # Collect all events with absolute tick times
    events: list[tuple[int, mido.Message]] = []

    for note in track.notes:
        start_tick = _beats_to_ticks(note.start_beat, ticks_per_beat)
        end_tick = _beats_to_ticks(note.end_beat, ticks_per_beat)
        velocity = note.velocity

        if note.articulation == ArticulationType.STACCATO:
            end_tick = start_tick + (end_tick - start_tick) // 2
        elif note.articulation == ArticulationType.ACCENT:
            velocity = min(127, velocity + 20)

        events.append((start_tick, mido.Message(
            "note_on", note=note.pitch, velocity=velocity, channel=ch,
        )))
        events.append((end_tick, mido.Message(
            "note_off", note=note.pitch, velocity=0, channel=ch,
        )))
        events.extend(_build_pitch_bend_events(note, ticks_per_beat, ch))

    events.sort(key=lambda e: e[0])

    # Convert absolute ticks to delta times
    prev_tick = 0
    for tick, msg in events:
        delta = max(0, tick - prev_tick)
        msg.time = delta
        midi_track.append(msg)
        prev_tick = tick

    midi_track.append(mido.MetaMessage("end_of_track", time=0))
    return midi_track


def save_midi(arrangement: Arrangement, path: str | Path) -> Path:
    """Save an Arrangement as a .mid file. Returns the output path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mid = arrangement_to_midi(arrangement)
    mid.save(str(path))
    return path


# ---------------------------------------------------------------------------
# Score → MIDI (bridges the new Score model to the existing MIDI writer)
# ---------------------------------------------------------------------------

_CHINESE_GM_MAP = {
    "guzheng": 107, "古筝": 107, "koto": 107,
    "erhu": 110, "二胡": 110, "fiddle": 110,
    "pipa": 106, "琵琶": 106, "shamisen": 106,
    "dizi": 77, "笛子": 77, "shakuhachi": 77,
    "xiao": 75, "箫": 75, "pan flute": 75,
    "yangqin": 15, "扬琴": 15, "dulcimer": 15,
    "cello": 42, "violin": 40, "viola": 41, "contrabass": 43,
    "flute": 73, "strings": 48, "pad": 89,
}


def _fix_program(instrument_name: str, program: int) -> int:
    """Ensure Chinese instruments get correct GM programs."""
    name = instrument_name.lower()
    for key, gm_prog in _CHINESE_GM_MAP.items():
        if key in name:
            return gm_prog
    return program


def _safe_text(text: str) -> str:
    """Transliterate or strip non-latin-1 characters so mido can encode them."""
    try:
        text.encode("latin-1")
        return text
    except UnicodeEncodeError:
        return text.encode("latin-1", errors="replace").decode("latin-1")


def score_to_midi(score, ticks_per_beat: int = 480) -> mido.MidiFile:
    """Convert a Score object to a MIDI file."""
    mid = mido.MidiFile(ticks_per_beat=ticks_per_beat)

    tempo_track = mido.MidiTrack()
    mid.tracks.append(tempo_track)
    tempo_track.append(mido.MetaMessage(
        "set_tempo", tempo=mido.bpm2tempo(score.tempo), time=0,
    ))
    ts_num = score.time_signature[0]
    ts_den = score.time_signature[1]
    denom_power = {1: 0, 2: 1, 4: 2, 8: 3, 16: 4}.get(ts_den, 2)
    tempo_track.append(mido.MetaMessage(
        "time_signature", numerator=ts_num,
        denominator=denom_power,
        clocks_per_click=24,
        notated_32nd_notes_per_beat=8, time=0,
    ))
    tempo_track.append(mido.MetaMessage(
        "track_name", name=_safe_text(score.title), time=0,
    ))

    # Add lyrics as meta events on the tempo track
    lyric_events: list[tuple[int, mido.MetaMessage]] = []
    for sec in score.sections:
        if sec.lyrics:
            for lyric in sec.lyrics:
                if isinstance(lyric, dict) and "text" in lyric:
                    beat = float(lyric.get("beat", sec.start_beat))
                    tick = _beats_to_ticks(beat, ticks_per_beat)
                    lyric_events.append((tick, mido.MetaMessage(
                        "lyrics", text=_safe_text(lyric["text"]), time=0,
                    )))
    if lyric_events:
        lyric_events.sort(key=lambda x: x[0])
        prev = 0
        for tick, meta in lyric_events:
            meta.time = max(0, tick - prev)
            tempo_track.append(meta)
            prev = tick

    tempo_track.append(mido.MetaMessage("end_of_track", time=0))

    for trk in score.tracks:
        midi_track = mido.MidiTrack()
        midi_track.append(mido.MetaMessage(
            "track_name", name=_safe_text(f"{trk.instrument} ({trk.name})"), time=0,
        ))
        ch = trk.channel
        program = _fix_program(trk.instrument, trk.program)
        midi_track.append(mido.Message(
            "program_change", program=program,
            channel=ch, time=0,
        ))

        events: list[tuple[int, mido.Message]] = []
        for n in trk.notes:
            s = _beats_to_ticks(n.start_beat, ticks_per_beat)
            e = s + _beats_to_ticks(n.duration_beats, ticks_per_beat)
            vel = min(127, max(1, n.velocity))
            events.append((s, mido.Message(
                "note_on", note=n.pitch, velocity=vel, channel=ch,
            )))
            events.append((e, mido.Message(
                "note_off", note=n.pitch, velocity=0, channel=ch,
            )))

        events.sort(key=lambda x: x[0])
        prev = 0
        for tick, msg in events:
            msg.time = max(0, tick - prev)
            midi_track.append(msg)
            prev = tick

        midi_track.append(mido.MetaMessage("end_of_track", time=0))
        mid.tracks.append(midi_track)

    return mid


def save_score_midi(score, path: str | Path) -> Path:
    """Save a Score as a .mid file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mid = score_to_midi(score)
    mid.save(str(path))
    return path

"""
Multi-Agent Pipeline -- Structured two-phase orchestration.

  Phase 1  Setup:      Orchestrator (blueprint) + Synthesizer (Magenta draft)
  Phase 2  Refinement: Per-section Composer -> Lyricist -> Instrumentalist
                       -> Critic loop for N rounds with MIDI snapshots

Key design principles (informed by CoComposer / ComposerX research):
  - Never ask the LLM to do math: beat ranges computed in Python
  - Per-section composer calls: avoids token truncation
  - Quantization enforced in post-processing (0.25 grid)
  - Pre-computed metrics injected into Critic context
  - Melody rhythm skeleton passed to Lyricist for alignment
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, Awaitable

from autogen_agentchat.messages import TextMessage
from autogen_core import CancellationToken
from loguru import logger

from src.agents.orchestrator import OrchestratorAgent
from src.agents.composer import ComposerAgent
from src.agents.lyricist import LyricistAgent
from src.agents.instrumentalist import InstrumentalistAgent
from src.agents.critic import CriticAgent
from src.agents.synthesizer import SynthesizerAgent
from src.llm.client import create_llm_client
from src.llm.prompts import (
    build_composer_section_prompt,
    build_composer_lead_sheet_prompt,
    build_inner_composer_prompt,
    build_overlap_context,
)
from src.knowledge.instruments import (
    format_for_composer,
    format_for_instrumentalist,
    format_for_critic,
    INSTRUMENT_CARDS,
)
from src.music.models import MusicRequest
from src.music.score import (
    Score, ScoreNote, ScoreSection, ScoreTrack,
    MainScore,
    compute_score_metrics, format_metrics_for_critic,
    compute_density_heatmap, compute_note_grid,
    detect_gaps, compute_register_coverage,
)
from src.music.midi_writer import save_score_midi
from config.settings import settings


ProgressCallback = Callable[[str, str, float], Awaitable[None]]


# ---------------------------------------------------------------------------
# Note / instrument parsing helpers
# ---------------------------------------------------------------------------

_NOTE_TO_MIDI = {}
for _oct in range(0, 10):
    for _name, _offset in [
        ("C", 0), ("C#", 1), ("Db", 1), ("D", 2), ("D#", 3),
        ("Eb", 3), ("E", 4), ("F", 5), ("F#", 6), ("Gb", 6),
        ("G", 7), ("G#", 8), ("Ab", 8), ("A", 9), ("A#", 10),
        ("Bb", 10), ("B", 11),
    ]:
        _NOTE_TO_MIDI[f"{_name}{_oct}"] = 12 * (_oct + 1) + _offset

_DURATION_TO_BEATS = {
    "whole": 4.0, "half": 2.0, "quarter": 1.0, "eighth": 0.5,
    "sixteenth": 0.25, "dotted half": 3.0, "dotted quarter": 1.5,
    "dotted eighth": 0.75, "triplet quarter": 2 / 3,
}

_CHINESE_INSTRUMENT_GM = {
    "guzheng": 107, "koto": 107,
    "erhu": 110, "fiddle": 110,
    "pipa": 106, "shamisen": 106,
    "dizi": 77, "shakuhachi": 77,
    "xiao": 75, "pan flute": 75,
    "yangqin": 15, "dulcimer": 15,
    "piano": 0, "grand piano": 0,
    "strings": 48, "pad": 89, "flute": 73,
    "acoustic guitar": 24, "nylon guitar": 24,
    "cello": 42, "violin": 40, "viola": 41, "contrabass": 43,
}

_GM_PITCH_RANGES = {
    "piano": (21, 108), "violin": (55, 103), "viola": (48, 91),
    "cello": (36, 76), "contrabass": (28, 67), "flute": (60, 96),
    "guzheng": (43, 96), "erhu": (55, 91), "dizi": (60, 96),
    "pipa": (45, 93), "xiao": (55, 84),
}


def _parse_pitch(val) -> int | None:
    if isinstance(val, int):
        return val if 0 <= val <= 127 else None
    if isinstance(val, float):
        return int(val) if 0 <= val <= 127 else None
    if isinstance(val, str):
        val = val.strip()
        if val.isdigit():
            return int(val) if 0 <= int(val) <= 127 else None
        return _NOTE_TO_MIDI.get(val)
    return None


def _parse_duration(val) -> float | None:
    if isinstance(val, (int, float)):
        return float(val) if val > 0 else None
    if isinstance(val, str):
        val = val.strip().lower()
        return _DURATION_TO_BEATS.get(val)
    return None


def _map_instrument_program(instrument_name: str, given: int) -> int:
    name_lower = instrument_name.lower()
    for key, prog in _CHINESE_INSTRUMENT_GM.items():
        if key in name_lower:
            return prog
    return given


def _find_json_objects(text: str) -> list[dict]:
    import re
    text = re.sub(r'```(?:json)?\s*', '', text)
    text = re.sub(r'```', '', text)
    results = []
    i = 0
    while i < len(text):
        if text[i] == '{':
            depth, start = 0, i
            for j in range(i, len(text)):
                if text[j] == '{':
                    depth += 1
                elif text[j] == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            obj = json.loads(text[start:j + 1])
                            if isinstance(obj, dict):
                                results.append(obj)
                        except json.JSONDecodeError:
                            pass
                        i = j + 1
                        break
            else:
                i += 1
        else:
            i += 1
    return results


def _extract_tracks_from_json(
    data: dict,
) -> dict[str, list[dict]] | None:
    result: dict[str, list[dict]] = {}
    if "tracks" in data and isinstance(data["tracks"], list):
        for trk in data["tracks"]:
            if not isinstance(trk, dict):
                continue
            name = trk.get("name", trk.get("instrument", "track"))
            notes_raw = trk.get("notes", [])
            if not isinstance(notes_raw, list) or not notes_raw:
                continue
            for n in notes_raw:
                if not isinstance(n, dict):
                    continue
                pitch = _parse_pitch(n.get("pitch") or n.get("note"))
                start = n.get("start_beat") or n.get("beat")
                dur = _parse_duration(
                    n.get("duration_beats") or n.get("duration")
                )
                if pitch is None or start is None:
                    continue
                if dur is None:
                    dur = 1.0
                vel = n.get("velocity", 80)
                result.setdefault(name, []).append({
                    "pitch": pitch,
                    "start_beat": float(start),
                    "duration_beats": dur,
                    "velocity": min(127, max(1, int(vel))),
                })
    if not result and "edits" in data and isinstance(data["edits"], list):
        for edit in data["edits"]:
            if not isinstance(edit, dict):
                continue
            if edit.get("action", "add") not in ("add", "modify"):
                continue
            pitch = _parse_pitch(edit.get("pitch"))
            start = edit.get("start_beat")
            dur = _parse_duration(
                edit.get("duration_beats") or edit.get("duration")
            )
            if pitch is None or start is None or dur is None:
                continue
            track_name = edit.get("track", "melody")
            vel = edit.get("velocity", 80)
            result.setdefault(track_name, []).append({
                "pitch": pitch,
                "start_beat": float(start),
                "duration_beats": dur,
                "velocity": min(127, max(1, int(vel))),
            })
    return result if result else None


def _match_instrument(
    track_name: str, inst_list: list[dict], notes: list[dict],
) -> tuple[str, dict | None]:
    tn = track_name.lower().replace("_", " ")
    for inst in inst_list:
        iname = inst["instrument"].lower()
        irole = inst["role"].lower()
        if tn in iname or iname in tn or tn in irole or irole in tn:
            return inst["instrument"], inst
    if inst_list:
        avg_pitch = (
            sum(n["pitch"] for n in notes) / len(notes) if notes else 60
        )
        if "bass" in tn or avg_pitch < 48:
            for inst in inst_list:
                if "bass" in inst["role"].lower():
                    return inst["instrument"], inst
        if "melody" in tn or "lead" in tn:
            for inst in inst_list:
                if "lead" in inst["role"].lower():
                    return inst["instrument"], inst
    return track_name, None


def _get_section_lyrics(
    section_name: str, start_beat: float, end_beat: float,
    all_lyrics: list[dict],
) -> list[dict] | None:
    result = []
    sn = section_name.lower()
    for lyric_block in all_lyrics:
        block_section = lyric_block.get("section_name", "").lower()
        lines = lyric_block.get("lines", [])
        if not isinstance(lines, list):
            continue
        if sn in block_section or block_section in sn:
            for line in lines:
                if isinstance(line, dict) and "text" in line:
                    result.append({
                        "text": line["text"],
                        "beat": float(
                            line.get("start_beat", start_beat)
                        ),
                    })
    return result if result else None


def _safe_title(title: str) -> str:
    return (
        title.encode("ascii", errors="replace")
        .decode("ascii").replace("?", "_")
    )


# ---------------------------------------------------------------------------
# Beat enrichment: compute absolute beat ranges from bar counts
# ---------------------------------------------------------------------------

def _enrich_sections(
    blueprint_sections: list[dict], bpb: int,
) -> list[dict]:
    """Add start_beat and end_beat to each section dict.

    Beats are 1-indexed (first beat of piece = 1.0).
    """
    offset = 1.0
    enriched = []
    for sec in blueprint_sections:
        bars = int(sec.get("bars", 4))
        end = offset + bars * bpb
        enriched.append({
            **sec,
            "start_beat": offset,
            "end_beat": end,
        })
        offset = end
    return enriched


# ---------------------------------------------------------------------------
# Quantization & validation (code-level, never LLM)
# ---------------------------------------------------------------------------

def _quantize_beat(val: float, grid: float) -> float:
    return round(val / grid) * grid


def _quantize_notes(
    notes: list[dict], grid: float,
) -> list[dict]:
    for n in notes:
        n["start_beat"] = _quantize_beat(n["start_beat"], grid)
        n["duration_beats"] = max(
            grid, _quantize_beat(n["duration_beats"], grid),
        )
    return notes


def _clamp_to_section(
    notes: list[dict],
    start_beat: float,
    end_beat: float,
) -> list[dict]:
    """Remove notes outside the section range."""
    return [
        n for n in notes
        if start_beat <= n["start_beat"] < end_beat
    ]


def _clamp_pitch_range(
    notes: list[dict], instrument_name: str,
) -> list[dict]:
    name_lower = instrument_name.lower()
    lo, hi = 0, 127
    for key, (rlo, rhi) in _GM_PITCH_RANGES.items():
        if key in name_lower:
            lo, hi = rlo, rhi
            break
    for n in notes:
        n["pitch"] = max(lo, min(hi, n["pitch"]))
    return notes


def _validate_channels(
    track_instruments: dict[str, dict],
) -> dict[str, dict]:
    """Ensure no two instruments share a MIDI channel."""
    used: set[int] = set()
    for iname, info in track_instruments.items():
        ch = info.get("channel", 0)
        while ch in used or ch == 9:
            ch += 1
        info["channel"] = ch
        used.add(ch)
    return track_instruments


def _filter_lyrics_to_melody(
    lyrics: list[dict],
    melody_beats: set[float],
    tolerance: float = 0.5,
) -> list[dict]:
    """Drop lyric lines whose start_beat doesn't match any melody note."""
    if not melody_beats:
        return lyrics
    filtered = []
    for block in lyrics:
        new_lines = []
        for line in block.get("lines", []):
            if not isinstance(line, dict):
                continue
            lb = float(line.get("start_beat", 0))
            if any(abs(lb - mb) < tolerance for mb in melody_beats):
                new_lines.append(line)
        if new_lines:
            filtered.append({**block, "lines": new_lines})
    return filtered


# ---------------------------------------------------------------------------
# Melody skeleton extraction (for Lyricist alignment)
# ---------------------------------------------------------------------------

def _extract_melody_skeleton(
    score: Score,
    enriched_sections: list[dict],
) -> dict[str, list[float]]:
    """Return {section_name: [sorted melody beat positions]}."""
    melody_trk = next(
        (t for t in score.tracks
         if "melody" in t.name.lower() or t.role == "melody"),
        None,
    )
    if not melody_trk:
        return {}
    skeleton: dict[str, list[float]] = {}
    for sec in enriched_sections:
        s, e = sec["start_beat"], sec["end_beat"]
        beats = sorted(
            n.start_beat for n in melody_trk.notes
            if s <= n.start_beat < e
        )
        skeleton[sec["name"]] = beats
    return skeleton


def _format_skeleton_for_lyricist(
    skeleton: dict[str, list[float]],
    enriched_sections: list[dict],
) -> str:
    """Format melody skeleton into text for the Lyricist."""
    parts = ["Melody rhythm skeleton (place lyrics ONLY on these beats):"]
    for sec in enriched_sections:
        name = sec["name"]
        if name.lower() in ("intro", "outro"):
            parts.append(
                f"  [{name.upper()}] instrumental (no lyrics)"
            )
            continue
        beats = skeleton.get(name, [])
        if not beats:
            parts.append(f"  [{name.upper()}] no melody notes")
            continue
        beat_str = ", ".join(f"{b:.1f}" for b in beats[:30])
        ellip = "..." if len(beats) > 30 else ""
        parts.append(
            f"  [{name.upper()}] beats {sec['start_beat']:.0f}"
            f"-{sec['end_beat']:.0f}: "
            f"melody at {beat_str}{ellip} ({len(beats)} notes)"
        )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Cross-section coherence summary
# ---------------------------------------------------------------------------

def _previous_section_summary(
    all_tracks: dict[str, list[dict]],
    completed_sections: list[dict],
) -> str:
    """Summarize the last completed section for coherence."""
    if not completed_sections or not all_tracks:
        return ""
    last_sec = completed_sections[-1]
    parts = [
        f"Previous: [{last_sec['name'].upper()}] "
        f"ended at beat {last_sec['end_beat']:.0f}"
    ]
    for trk_name, notes in all_tracks.items():
        sec_notes = [
            n for n in notes
            if last_sec["start_beat"] <= n["start_beat"] < last_sec["end_beat"]
        ]
        if sec_notes:
            last_n = max(sec_notes, key=lambda n: n["start_beat"])
            parts.append(
                f"  {trk_name}: last pitch={last_n['pitch']}, "
                f"beat={last_n['start_beat']:.1f}, "
                f"vel={last_n['velocity']}"
            )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Instrument knowledge helpers
# ---------------------------------------------------------------------------

def _build_composer_knowledge(
    instruments: list[dict],
) -> list[str]:
    """Look up instrument knowledge cards for all blueprint instruments."""
    knowledge: list[str] = []
    for inst in instruments:
        name = inst.get("name", "")
        role = inst.get("role", "accompaniment")
        text = format_for_composer(name, role)
        if text:
            knowledge.append(text)
    return knowledge


def _build_instrumentalist_techniques(
    instruments: list[dict],
) -> list[str]:
    """Look up technique guides for the Instrumentalist agent."""
    techniques: list[str] = []
    for inst in instruments:
        name = inst.get("name", "")
        text = format_for_instrumentalist(name)
        if text:
            techniques.append(text)
    return techniques


def _build_critic_criteria(
    instruments: list[dict],
) -> list[str]:
    """Look up evaluation criteria for the Critic agent."""
    criteria: list[str] = []
    for inst in instruments:
        name = inst.get("name", "")
        text = format_for_critic(name)
        if text:
            criteria.append(text)
    return criteria


# ---------------------------------------------------------------------------
# Score building from accumulated section tracks
# ---------------------------------------------------------------------------

def _build_score_from_sections(
    all_tracks: dict[str, list[dict]],
    title: str, key: str, scale_type: str,
    tempo: int, time_sig: list[int],
    enriched_sections: list[dict],
    track_instruments: dict[str, dict],
    lyrics: list[dict],
) -> Score | None:
    if not all_tracks:
        return None

    bpb = time_sig[0] if time_sig else 4
    sections: list[ScoreSection] = []
    for sec in enriched_sections:
        sections.append(ScoreSection(
            name=sec["name"],
            start_beat=sec["start_beat"] - 1.0,
            bars=sec["bars"],
            lyrics=_get_section_lyrics(
                sec["name"], sec["start_beat"],
                sec["end_beat"], lyrics,
            ),
        ))

    tracks: list[ScoreTrack] = []
    inst_list = list(track_instruments.values())
    used_channels: set[int] = set()

    for idx, (track_name, notes) in enumerate(all_tracks.items()):
        instrument_name, matched = _match_instrument(
            track_name, inst_list, notes,
        )
        program = _map_instrument_program(
            instrument_name,
            matched.get("program", 0) if matched else 0,
        )
        channel = matched.get("channel", idx) if matched else idx
        while channel in used_channels and channel < 15:
            channel += 1
        if channel == 9:
            channel = 10
        used_channels.add(channel)

        adjusted = []
        for n in notes:
            adjusted.append({
                **n,
                "start_beat": n["start_beat"] - 1.0,
            })

        score_notes = sorted(
            [ScoreNote(**n) for n in adjusted],
            key=lambda n: n.start_beat,
        )
        tracks.append(ScoreTrack(
            name=track_name, instrument=instrument_name,
            role=matched.get("role", "melody") if matched else "melody",
            channel=channel, program=program, notes=score_notes,
        ))

    total_notes = sum(len(t.notes) for t in tracks)
    logger.info(
        f"Score built: '{title}', {len(tracks)} tracks, "
        f"{total_notes} notes"
    )
    return Score(
        title=title, key=key, scale_type=scale_type,
        tempo=tempo, time_signature=time_sig,
        sections=sections, tracks=tracks,
    )


def _build_score_from_composer(
    text: str,
    title: str, key: str, scale_type: str,
    tempo: int, time_sig: list[int],
    blueprint_sections: list[dict],
    track_instruments: dict[str, dict],
    lyrics: list[dict],
) -> Score | None:
    """Legacy builder for Magenta draft (single-message extraction)."""
    best_tracks: dict[str, list[dict]] | None = None
    best_count = 0
    for data in _find_json_objects(text):
        candidate = _extract_tracks_from_json(data)
        if candidate:
            count = sum(len(ns) for ns in candidate.values())
            if count > best_count:
                best_tracks = candidate
                best_count = count
    if not best_tracks:
        return None

    bpb = time_sig[0] if time_sig else 4
    sections: list[ScoreSection] = []
    beat_offset = 0.0
    if blueprint_sections:
        for sd in blueprint_sections:
            bars = int(sd.get("bars", 4))
            sections.append(ScoreSection(
                name=sd["name"], start_beat=beat_offset, bars=bars,
                lyrics=_get_section_lyrics(
                    sd["name"], beat_offset,
                    beat_offset + bars * bpb, lyrics,
                ),
            ))
            beat_offset += bars * bpb
    else:
        max_beat = max(
            max(n["start_beat"] + n["duration_beats"] for n in ns)
            for ns in best_tracks.values()
        )
        sections.append(ScoreSection(
            name="main", start_beat=0.0,
            bars=int(max_beat / bpb) + 1,
        ))

    tracks: list[ScoreTrack] = []
    inst_list = list(track_instruments.values())
    used_channels: set[int] = set()

    for idx, (track_name, notes) in enumerate(best_tracks.items()):
        instrument_name, matched = _match_instrument(
            track_name, inst_list, notes,
        )
        program = _map_instrument_program(
            instrument_name,
            matched.get("program", 0) if matched else 0,
        )
        channel = matched.get("channel", idx) if matched else idx
        while channel in used_channels and channel < 15:
            channel += 1
        if channel == 9:
            channel = 10
        used_channels.add(channel)

        score_notes = sorted(
            [ScoreNote(**n) for n in notes],
            key=lambda n: n.start_beat,
        )
        tracks.append(ScoreTrack(
            name=track_name, instrument=instrument_name,
            role=matched.get("role", "melody") if matched else "melody",
            channel=channel, program=program, notes=score_notes,
        ))

    total_notes = sum(len(t.notes) for t in tracks)
    logger.info(
        f"Score built: '{title}', {len(tracks)} tracks, {total_notes} notes"
    )
    return Score(
        title=title, key=key, scale_type=scale_type,
        tempo=tempo, time_signature=time_sig,
        sections=sections, tracks=tracks,
    )


# ---------------------------------------------------------------------------
# Nested-loop helpers
# ---------------------------------------------------------------------------

_ROLE_PRIORITY = {
    "lead": 1, "melody": 1,
    "counter-melody": 2, "counter": 2,
    "accompaniment": 3, "chords": 3, "harmony": 3,
    "bass": 4,
    "pad": 5, "texture": 5,
}


def _sort_instruments_by_priority(instruments: list[dict]) -> list[dict]:
    """Order instruments by role priority: lead first, pad last."""
    def _key(inst):
        role = inst.get("role", "accompaniment").lower()
        return _ROLE_PRIORITY.get(role, 3)
    return sorted(instruments, key=_key)


def _build_role_density_minimums() -> dict[str, int]:
    """Map role names to minimum notes/bar from config."""
    return {
        "lead": settings.min_density_lead,
        "melody": settings.min_density_lead,
        "counter-melody": settings.min_density_counter,
        "counter": settings.min_density_counter,
        "accompaniment": settings.min_density_accomp,
        "chords": settings.min_density_accomp,
        "harmony": settings.min_density_accomp,
        "bass": settings.min_density_bass,
        "pad": 1,
        "texture": 1,
    }


def _build_instrument_ranges(instruments: list[dict]) -> dict[str, tuple[int, int]]:
    """Look up sweet-spot ranges from INSTRUMENT_CARDS."""
    ranges = {}
    for inst in instruments:
        name = inst.get("name", "")
        name_lower = name.lower()
        for card_key, card in INSTRUMENT_CARDS.items():
            if card_key in name_lower or name_lower in card_key:
                sweet = card.get("sweet_spot")
                if sweet:
                    ranges[name] = tuple(sweet)
                break
    return ranges


def _extract_main_score_from_response(text: str) -> MainScore | None:
    """Parse lead-sheet JSON into MainScore."""
    for data in _find_json_objects(text):
        melody_raw = data.get("melody", [])
        if not isinstance(melody_raw, list) or not melody_raw:
            continue
        melody = []
        for n in melody_raw:
            if not isinstance(n, dict):
                continue
            pitch = _parse_pitch(n.get("pitch"))
            if pitch is None:
                continue
            melody.append(ScoreNote(
                pitch=pitch,
                start_beat=float(n.get("start_beat", 0)),
                duration_beats=float(n.get("duration_beats", 1.0)),
                velocity=int(n.get("velocity", 80)),
            ))
        if not melody:
            continue
        return MainScore(
            melody=melody,
            chord_progression=data.get("chord_progression", []),
            rhythm_guide=data.get("rhythm_guide", {}),
            instrument_plan=data.get("instrument_plan", {}),
        )
    return None


def _format_arranged_instruments_context(
    score: Score,
    arranged_instruments: list[str],
    section_start: float,
    section_end: float,
) -> str:
    """Format note grids of previously arranged instruments for context.

    Uses compute_note_grid for detailed view of the section.
    """
    if not arranged_instruments:
        return ""
    bpb = score.time_signature[0] if score.time_signature else 4
    # Compute bar range for this section (0-indexed beats)
    start_bar = int(section_start / bpb) + 1
    end_bar = int(section_end / bpb)
    if end_bar < start_bar:
        end_bar = start_bar

    parts = []
    for inst_name in arranged_instruments:
        trk_name = inst_name.lower()
        trk = score.get_track(inst_name) or score.get_track(trk_name)
        if not trk:
            continue
        sec_notes = [
            n for n in trk.notes
            if section_start <= n.start_beat < section_end
        ]
        if not sec_notes:
            parts.append(f"  {inst_name}: (silent in this section)")
            continue
        # Use note grid for detailed view (limit to 4 bars to save tokens)
        grid_end = min(end_bar, start_bar + 3)
        grid_text = compute_note_grid(score, trk.name, start_bar, grid_end, bpb)
        parts.append(grid_text)
    return "\n".join(parts) if parts else ""


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class MusicGenerationPipeline:
    """
    Three-phase pipeline with nested loops:
      Phase 1: Orchestrator blueprint + Synthesizer draft
      Phase 2: Lead sheet creation (melody + chords + rhythm guide)
      Phase 3: Nested refinement
               Outer loop: per-instrument inner loops + Ensemble Critic
               Inner loop: Composer + Instrumentalist + Inner Critic
    """

    def __init__(
        self,
        backend: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        on_progress: ProgressCallback | None = None,
    ):
        self._on_progress = on_progress
        self._cancel = CancellationToken()
        self._llm_client = create_llm_client(
            backend=backend, model=model, api_key=api_key,
        )

        self.orchestrator = OrchestratorAgent(
            name="orchestrator", model_client=self._llm_client,
        )
        self.composer = ComposerAgent(
            name="composer", model_client=self._llm_client,
        )
        self.lyricist = LyricistAgent(
            name="lyricist", model_client=self._llm_client,
        )
        self.instrumentalist = InstrumentalistAgent(
            name="instrumentalist", model_client=self._llm_client,
        )
        self.critic = CriticAgent(
            name="critic", model_client=self._llm_client,
        )
        self.synthesizer = SynthesizerAgent(name="synthesizer")

    async def run(self, request: MusicRequest) -> PipelineResult:
        task_text = self._build_task(request)
        logger.info(f"Starting pipeline for: {request.description[:80]}")

        messages: list[dict] = []
        snapshots: list[str] = []
        drafts_dir = settings.output_dir / "drafts"
        drafts_dir.mkdir(parents=True, exist_ok=True)

        if self._on_progress:
            await self._on_progress("start", "Pipeline started", 0.0)

        try:
            # ---- Phase 1: Setup ----
            phase1 = await self._run_phase1_setup(
                request, task_text, messages, snapshots, drafts_dir,
            )
            title = phase1["title"]
            key = phase1["key"]
            scale_type = phase1["scale_type"]
            tempo = phase1["tempo"]
            time_sig = phase1["time_sig"]
            bpb = phase1["bpb"]
            enriched_sections = phase1["enriched_sections"]
            blueprint_instruments = phase1["blueprint_instruments"]
            draft_description = phase1["draft_description"]
            orch_resp = phase1["orch_resp"]
            safe_t = phase1["safe_t"]

            # ---- Phase 2: Lead Sheet Creation ----
            main_score, lyrics = await self._run_phase2_lead_sheet(
                enriched_sections, blueprint_instruments,
                key, scale_type, draft_description,
                orch_resp, messages, snapshots, drafts_dir, safe_t,
            )

            # ---- Phase 3: Nested Refinement ----
            final_score, articulations = await self._run_phase3_nested_refinement(
                main_score, lyrics, blueprint_instruments,
                enriched_sections, key, scale_type, tempo, time_sig,
                messages, snapshots, drafts_dir, safe_t,
                orch_resp=orch_resp, draft_description=draft_description,
            )

            if not final_score:
                logger.warning("No score produced -- returning empty result")
                return PipelineResult(
                    messages=messages,
                    total_messages=len(messages),
                    error="No score produced after refinement",
                    snapshots=snapshots,
                )

            # ---- Build final MIDI ----
            logger.info("=== Building final MIDI ===")
            ts = int(time.time())
            midi_path = str(settings.output_dir / f"{safe_t}_{ts}.mid")
            save_score_midi(final_score, midi_path, articulations=articulations)
            logger.info(f"Final MIDI exported: {midi_path}")

            if self._on_progress:
                await self._on_progress("done", "Pipeline complete", 1.0)

            return PipelineResult(
                messages=messages,
                total_messages=len(messages),
                completed=True,
                midi_path=midi_path,
                score=final_score,
                snapshots=snapshots,
            )

        except Exception as e:
            import traceback
            full_tb = traceback.format_exc()
            logger.error(f"Pipeline error: {e}\n{full_tb}")
            if self._on_progress:
                await self._on_progress("error", str(e), 0.0)
            return PipelineResult(
                messages=messages,
                total_messages=len(messages),
                error=f"{str(e)}\n\nTRACEBACK:\n{full_tb}",
                snapshots=snapshots,
            )

    # ------------------------------------------------------------------
    # Phase 1: Setup (Orchestrator + Synthesizer)
    # ------------------------------------------------------------------

    async def _run_phase1_setup(
        self, request, task_text, messages, snapshots, drafts_dir,
    ) -> dict:
        logger.info("=== Phase 1: Setup ===")

        title, key, scale_type = "Untitled", "C", "major"
        tempo = request.tempo or 120
        time_sig = list(request.time_signature) if request.time_signature else [4, 4]
        bpb = time_sig[0]
        blueprint_sections = []
        blueprint_instruments = []

        # 1a. Orchestrator
        if self._on_progress:
            await self._on_progress("orchestrator", "Creating blueprint", 0.03)

        orch_resp = await self._call_agent(self.orchestrator, messages, task_text)
        messages.append({"source": "orchestrator", "content": orch_resp})
        logger.info(f"[Phase1] Orchestrator responded ({len(orch_resp)} chars)")

        for data in _find_json_objects(orch_resp):
            title = data.get("title", title)
            key = data.get("key", key)
            scale_type = data.get("scale_type", scale_type)
            tempo = data.get("tempo", tempo)
            time_sig = data.get("time_signature", time_sig)
            bpb = time_sig[0]
            blueprint_sections = []
            for sec in data.get("sections", []):
                if isinstance(sec, dict) and "name" in sec:
                    blueprint_sections.append(sec)
            for inst in data.get("instruments", []):
                if isinstance(inst, dict) and "name" in inst:
                    blueprint_instruments.append(inst)

        enriched_sections = _enrich_sections(blueprint_sections, bpb)
        # Add bar_start/bar_end for prompt builders
        for sec in enriched_sections:
            sec["bar_start"] = int((sec["start_beat"] - 1.0) / bpb) + 1
            sec["bar_end"] = int((sec["end_beat"] - 1.0) / bpb)

        logger.info(f"[Phase1] Enriched {len(enriched_sections)} sections")
        for sec in enriched_sections:
            logger.info(f"  [{sec['name']}] bars={sec['bars']} beats={sec['start_beat']:.0f}-{sec['end_beat']:.0f}")

        safe_t = _safe_title(title)

        # 1b. Synthesizer
        if self._on_progress:
            await self._on_progress("synthesizer", "Generating Magenta draft", 0.07)

        synth_resp = await self._call_agent(self.synthesizer, messages, task_text)
        messages.append({"source": "synthesizer", "content": synth_resp})

        draft_score = _build_score_from_composer(
            synth_resp, title, key, scale_type, tempo, time_sig,
            blueprint_sections, {}, [],
        )
        draft_description = ""
        if draft_score:
            draft_path = str(drafts_dir / f"{safe_t}_round0_magenta.mid")
            save_score_midi(draft_score, draft_path)
            snapshots.append(draft_path)
            draft_description = draft_score.to_llm_description()
            logger.info(f"[Phase1] Magenta draft saved: {draft_path}")
        else:
            logger.warning("[Phase1] No usable score from Magenta")

        return {
            "title": title, "key": key, "scale_type": scale_type,
            "tempo": tempo, "time_sig": time_sig, "bpb": bpb,
            "enriched_sections": enriched_sections,
            "blueprint_instruments": blueprint_instruments,
            "draft_description": draft_description,
            "orch_resp": orch_resp, "safe_t": safe_t,
        }

    # ------------------------------------------------------------------
    # Phase 2: Lead Sheet Creation
    # ------------------------------------------------------------------

    async def _run_phase2_lead_sheet(
        self, enriched_sections, blueprint_instruments,
        key, scale_type, draft_description,
        orch_resp, messages, snapshots, drafts_dir, safe_t,
        critic_feedback="",
    ) -> tuple[MainScore, list[dict]]:
        logger.info("=== Phase 2: Lead Sheet Creation ===")
        self.composer.set_mode("lead_sheet")
        self.critic.set_mode("structural")

        max_rounds = settings.max_refinement_rounds
        main_score = None
        lyrics: list[dict] = []
        grid = settings.quantization_grid

        for rnd in range(1, max_rounds + 1):
            progress = 0.10 + (rnd - 1) / max_rounds * 0.20

            # Composer: lead sheet
            if self._on_progress:
                await self._on_progress(
                    "composer", f"Lead sheet round {rnd}/{max_rounds}", progress,
                )

            lead_prompt = build_composer_lead_sheet_prompt(
                enriched_sections=enriched_sections,
                key=key,
                scale_type=scale_type,
                instruments=blueprint_instruments,
                draft_description=draft_description if rnd == 1 else "",
                critic_feedback=critic_feedback,
            )
            comp_resp = await self._call_agent(self.composer, messages, lead_prompt)
            messages.append({"source": "composer", "content": comp_resp})

            candidate = _extract_main_score_from_response(comp_resp)
            if candidate:
                # Quantize melody
                for n in candidate.melody:
                    n.start_beat = _quantize_beat(n.start_beat, grid)
                    n.duration_beats = max(grid, _quantize_beat(n.duration_beats, grid))
                main_score = candidate
                logger.info(f"[Phase2] Lead sheet: {len(main_score.melody)} melody notes")
            else:
                logger.warning(f"[Phase2] Round {rnd}: no lead sheet extracted")
                continue

            # Build a temporary Score from melody for lyricist
            melody_track = ScoreTrack(
                name="melody", instrument="Lead", role="melody",
                notes=list(main_score.melody),
            )
            # Build 0-indexed sections for Score (Score uses 0-indexed beats)
            zero_indexed_sections = [
                ScoreSection(
                    name=sec["name"],
                    start_beat=sec["start_beat"] - 1.0,
                    bars=sec["bars"],
                )
                for sec in enriched_sections
            ]
            # Also build 0-indexed enriched dicts for functions that
            # compare against Score note beats
            enriched_0 = [
                {**sec, "start_beat": sec["start_beat"] - 1.0, "end_beat": sec["end_beat"] - 1.0}
                for sec in enriched_sections
            ]
            temp_score = Score(
                title="Lead Sheet", key=key, scale_type=scale_type,
                sections=zero_indexed_sections, tracks=[melody_track],
            )

            # Save lead sheet MIDI snapshot
            snap = str(drafts_dir / f"{safe_t}_lead_sheet_r{rnd}.mid")
            save_score_midi(temp_score, snap)
            snapshots.append(snap)

            # Lyricist
            if self._on_progress:
                await self._on_progress(
                    "lyricist", f"Lead sheet round {rnd}: lyrics", progress + 0.05,
                )

            skeleton = _extract_melody_skeleton(temp_score, enriched_0)
            skel_text = _format_skeleton_for_lyricist(skeleton, enriched_sections)

            lyricist_context = f"Blueprint:\n{orch_resp}\n\n"
            lyricist_context += "Section beat ranges:\n"
            for sec in enriched_sections:
                lyricist_context += f"  [{sec['name']}] beats {sec['start_beat']:.0f}-{sec['end_beat']:.0f}\n"
            lyricist_context += f"\n{skel_text}\n\n"
            if lyrics:
                lyricist_context += f"Previous lyrics:\n{json.dumps(lyrics, ensure_ascii=False)[:1500]}\n\n"
            if critic_feedback:
                lyricist_context += f"Critic feedback:\n{critic_feedback}\n\n"
            lyricist_context += "Write or revise lyrics. Place each lyric ONLY on melody note beats."

            lyr_resp = await self._call_agent(self.lyricist, messages, lyricist_context)
            messages.append({"source": "lyricist", "content": lyr_resp})

            lyrics = []
            for data in _find_json_objects(lyr_resp):
                if "lyrics" in data and isinstance(data["lyrics"], list):
                    lyrics.extend(data["lyrics"])
                elif "lines" in data and isinstance(data["lines"], list):
                    lyrics.append(data)

            # Structural Critic
            if self._on_progress:
                await self._on_progress(
                    "critic", f"Lead sheet round {rnd}: reviewing", progress + 0.10,
                )

            critic_ctx = f"Lead sheet summary:\n{main_score.to_description(key, scale_type)}\n\n"
            critic_ctx += f"Melody note count: {len(main_score.melody)}\n"
            critic_ctx += f"Chord entries: {len(main_score.chord_progression)}\n"
            critic_ctx += f"Sections: {len(enriched_sections)}\n\n"
            critic_ctx += "Evaluate the lead sheet. Is the melody compelling? Are chords coherent?"

            crit_resp = await self._call_agent(self.critic, messages, critic_ctx)
            messages.append({"source": "critic", "content": crit_resp})

            passes = False
            for data in _find_json_objects(crit_resp):
                passes = data.get("passes", False)
                critic_feedback = data.get("revision_instructions", "")
                score_val = data.get("overall_score", 0)
                logger.info(f"[Phase2] Structural Critic score={score_val}, passes={passes}")

            if passes:
                logger.info(f"[Phase2] Lead sheet approved at round {rnd}")
                break

        if not main_score:
            logger.warning("[Phase2] No lead sheet produced, creating fallback")
            main_score = MainScore(melody=[], chord_progression=[], rhythm_guide={}, instrument_plan={})

        return main_score, lyrics

    # ------------------------------------------------------------------
    # Phase 3: Nested Refinement
    # ------------------------------------------------------------------

    async def _run_phase3_nested_refinement(
        self, main_score, lyrics, blueprint_instruments,
        enriched_sections, key, scale_type, tempo, time_sig,
        messages, snapshots, drafts_dir, safe_t,
        orch_resp="", draft_description="",
    ) -> tuple[Score | None, dict]:
        logger.info("=== Phase 3: Nested Refinement ===")

        sorted_instruments = _sort_instruments_by_priority(blueprint_instruments)
        role_mins = _build_role_density_minimums()
        inst_ranges = _build_instrument_ranges(blueprint_instruments)
        grid = settings.quantization_grid
        bpb = time_sig[0] if time_sig else 4
        max_outer = settings.max_outer_loops
        articulations: dict[str, list[dict]] = {}
        track_instruments: dict[str, dict] = {}

        # Initialize score with sections but no tracks
        sections = [
            ScoreSection(
                name=sec["name"],
                start_beat=sec["start_beat"] - 1.0,
                bars=sec["bars"],
            )
            for sec in enriched_sections
        ]
        current_score = Score(
            title=safe_t, key=key, scale_type=scale_type,
            tempo=tempo, time_signature=time_sig,
            sections=sections, tracks=[],
        )

        frozen_instruments: set[str] = set()
        distribution_update = ""

        for outer_rnd in range(1, max_outer + 1):
            logger.info(f"=== Outer Loop {outer_rnd}/{max_outer} ===")
            outer_progress_base = 0.30 + (outer_rnd - 1) / max_outer * 0.65
            outer_step = 0.65 / max_outer

            # Clear non-frozen instrument tracks at start of each outer loop
            if outer_rnd > 1:
                current_score.tracks = [
                    t for t in current_score.tracks
                    if t.instrument in frozen_instruments
                ]

            arranged_instruments: list[str] = [
                t.instrument for t in current_score.tracks
            ]

            for inst_idx, inst_info in enumerate(sorted_instruments):
                inst_name = inst_info.get("name", "")
                inst_role = inst_info.get("role", "accompaniment")

                if inst_name in frozen_instruments:
                    logger.info(f"  [{inst_name}] frozen, skipping")
                    continue

                inst_progress = outer_progress_base + (inst_idx / len(sorted_instruments)) * outer_step * 0.8

                # Get distribution guidance from main_score or update
                dist_guidance = ""
                if distribution_update:
                    dist_guidance = distribution_update
                elif main_score.instrument_plan:
                    dist_guidance = main_score.instrument_plan.get(inst_name, "")

                # Run inner loop for this instrument
                inner_articulations = await self._run_inner_loop(
                    inst_name=inst_name,
                    inst_role=inst_role,
                    inst_info=inst_info,
                    main_score=main_score,
                    current_score=current_score,
                    enriched_sections=enriched_sections,
                    arranged_instruments=arranged_instruments,
                    key=key,
                    scale_type=scale_type,
                    role_mins=role_mins,
                    inst_ranges=inst_ranges,
                    dist_guidance=dist_guidance,
                    grid=grid,
                    messages=messages,
                    snapshots=snapshots,
                    drafts_dir=drafts_dir,
                    safe_t=safe_t,
                    outer_rnd=outer_rnd,
                    progress_base=inst_progress,
                )
                articulations.update(inner_articulations)
                arranged_instruments.append(inst_name)

                # Build track_instruments entry
                track_instruments[inst_name] = {
                    "instrument": inst_name,
                    "role": inst_role,
                    "channel": 0,
                    "program": _map_instrument_program(inst_name, 0),
                }

            # Validate channels
            track_instruments = _validate_channels(track_instruments)

            # Apply channels to score tracks
            for trk in current_score.tracks:
                ti = track_instruments.get(trk.instrument)
                if ti:
                    trk.channel = ti["channel"]
                    trk.program = ti["program"]

            # Snapshot after all instruments arranged
            snap = str(drafts_dir / f"{safe_t}_outer{outer_rnd}_ensemble.mid")
            save_score_midi(current_score, snap)
            snapshots.append(snap)

            # Ensemble Critic
            ensemble_result = await self._run_ensemble_critic(
                current_score, main_score, enriched_sections,
                blueprint_instruments, lyrics, role_mins,
                inst_ranges, messages,
                outer_progress_base + outer_step * 0.9,
            )

            if ensemble_result["passes"]:
                logger.info(f"[Outer {outer_rnd}] Ensemble Critic passed!")
                break

            # Handle selective re-runs
            main_changes = ensemble_result.get("main_score_changes")
            reruns = ensemble_result.get("instrument_reruns", [])
            keeps = ensemble_result.get("keep_instruments", [])
            distribution_update = ensemble_result.get("distribution_update", "")

            if main_changes is not None and main_changes != "":
                logger.info(f"[Outer {outer_rnd}] Main score changes requested, re-running Phase 2")
                main_score, lyrics = await self._run_phase2_lead_sheet(
                    enriched_sections, blueprint_instruments,
                    key, scale_type, draft_description,
                    orch_resp,
                    messages, snapshots, drafts_dir, safe_t,
                    critic_feedback=main_changes,
                )
                frozen_instruments.clear()
            elif reruns:
                frozen_instruments = {
                    inst.get("name", "") for inst in sorted_instruments
                    if inst.get("name", "") not in reruns
                }
                logger.info(f"[Outer {outer_rnd}] Re-running: {reruns}, frozen: {frozen_instruments}")
            else:
                # No specific guidance — re-run all
                frozen_instruments.clear()

        # Merge lyrics into final score
        if lyrics and current_score:
            for sec in current_score.sections:
                sec_lyrics = _get_section_lyrics(
                    sec.name, sec.start_beat, sec.start_beat + sec.bars * bpb, lyrics,
                )
                if sec_lyrics:
                    sec.lyrics = sec_lyrics

        return current_score, articulations

    # ------------------------------------------------------------------
    # Inner Loop: Per-instrument refinement
    # ------------------------------------------------------------------

    async def _run_inner_loop(
        self, inst_name, inst_role, inst_info,
        main_score, current_score, enriched_sections,
        arranged_instruments, key, scale_type,
        role_mins, inst_ranges, dist_guidance, grid,
        messages, snapshots, drafts_dir, safe_t,
        outer_rnd, progress_base,
    ) -> dict[str, list[dict]]:
        logger.info(f"  === Inner Loop: {inst_name} ({inst_role}) ===")
        self.composer.set_mode("instrument")
        self.critic.set_mode("inner")

        max_inner = settings.max_inner_loops
        inner_articulations: dict[str, list[dict]] = {}
        critic_feedback = ""
        bpb = current_score.time_signature[0] if current_score.time_signature else 4

        # Get instrument knowledge
        inst_knowledge_text = format_for_composer(inst_name, inst_role)
        inst_technique_text = format_for_instrumentalist(inst_name)

        for inner_rnd in range(1, max_inner + 1):
            logger.info(f"    Inner round {inner_rnd}/{max_inner} for {inst_name}")

            # Remove previous attempt for this instrument
            current_score.tracks = [
                t for t in current_score.tracks
                if t.instrument != inst_name
            ]

            all_notes: list[dict] = []

            # Compose per section
            for sec in enriched_sections:
                # Build context for this instrument + section
                main_desc = main_score.to_description(key, scale_type) if main_score.melody else ""

                arranged_ctx = _format_arranged_instruments_context(
                    current_score, arranged_instruments,
                    sec["start_beat"] - 1.0,
                    sec["end_beat"] - 1.0,
                )

                # Density and gap info (only for rounds > 1)
                density_hm = ""
                gap_rpt = ""
                if inner_rnd > 1 and current_score.tracks:
                    density_hm = compute_density_heatmap(current_score, bpb)
                    gap_rpt = detect_gaps(current_score, role_mins, bpb)

                overlap_ctx = build_overlap_context(
                    current_score, sec["name"], enriched_sections,
                    track_name=inst_name.lower(), beats_per_bar=bpb,
                )

                section_prompt = build_inner_composer_prompt(
                    instrument_name=inst_name,
                    instrument_role=inst_role,
                    section_name=sec["name"],
                    start_beat=sec["start_beat"],
                    end_beat=sec["end_beat"],
                    bars=sec["bars"],
                    mood=sec.get("mood", ""),
                    key=key,
                    scale_type=scale_type,
                    main_score_description=main_desc,
                    arranged_instruments_context=arranged_ctx,
                    density_heatmap=density_hm,
                    gap_report=gap_rpt,
                    overlap_context=overlap_ctx,
                    instrument_knowledge=inst_knowledge_text or "",
                    critic_feedback=critic_feedback if sec == enriched_sections[0] else "",
                    distribution_guidance=dist_guidance,
                )

                comp_resp = await self._call_agent(self.composer, messages, section_prompt)
                messages.append({"source": "composer", "content": comp_resp})

                for data in _find_json_objects(comp_resp):
                    candidate = _extract_tracks_from_json(data)
                    if candidate:
                        for trk_name, notes in candidate.items():
                            notes = _quantize_notes(notes, grid)
                            notes = _clamp_to_section(notes, sec["start_beat"], sec["end_beat"])
                            notes = _clamp_pitch_range(notes, inst_name)
                            all_notes.extend(notes)
                        break

            if not all_notes:
                logger.warning(f"    [{inst_name}] No notes produced in inner round {inner_rnd}")
                continue

            # Build ScoreTrack and add to score
            # Adjust beats from 1-indexed to 0-indexed
            adjusted_notes = [
                ScoreNote(
                    pitch=n["pitch"],
                    start_beat=n["start_beat"] - 1.0,
                    duration_beats=n["duration_beats"],
                    velocity=n["velocity"],
                )
                for n in all_notes
            ]
            adjusted_notes.sort(key=lambda n: n.start_beat)

            program = _map_instrument_program(inst_name, 0)
            new_track = ScoreTrack(
                name=inst_name.lower(),
                instrument=inst_name,
                role=inst_role,
                program=program,
                notes=adjusted_notes,
            )
            current_score.tracks.append(new_track)
            logger.info(f"    [{inst_name}] {len(adjusted_notes)} notes added")

            # Snapshot
            snap = str(drafts_dir / f"{safe_t}_outer{outer_rnd}_inner{inner_rnd}_{inst_name.lower()}.mid")
            save_score_midi(current_score, snap)
            snapshots.append(snap)

            # Instrumentalist: articulations for this instrument
            if self._on_progress:
                await self._on_progress(
                    "instrumentalist",
                    f"Articulations for {inst_name}",
                    progress_base + 0.02,
                )

            inst_ctx = ""
            if inst_technique_text:
                inst_ctx += f"TECHNIQUE GUIDE for {inst_name}:\n{inst_technique_text}\n\n"
            inst_ctx += f"Score summary:\n{current_score.to_llm_description()}\n\n"
            inst_ctx += f"Assign articulations for {inst_name} ONLY."

            inst_resp = await self._call_agent(self.instrumentalist, messages, inst_ctx)
            messages.append({"source": "instrumentalist", "content": inst_resp})

            for data in _find_json_objects(inst_resp):
                for trk in data.get("tracks", []):
                    if not isinstance(trk, dict):
                        continue
                    arts = trk.get("articulations", [])
                    if isinstance(arts, list) and arts:
                        inner_articulations[inst_name] = arts

            # Inner Critic
            if self._on_progress:
                await self._on_progress(
                    "critic",
                    f"Reviewing {inst_name} (inner {inner_rnd})",
                    progress_base + 0.04,
                )

            density_hm = compute_density_heatmap(current_score, bpb)
            gap_rpt = detect_gaps(current_score, role_mins, bpb)
            register_cov = compute_register_coverage(current_score, inst_ranges)

            critic_ctx = f"Evaluating {inst_name} ({inst_role}).\n\n"
            critic_ctx += f"{density_hm}\n\n"
            if gap_rpt:
                critic_ctx += f"{gap_rpt}\n\n"
            critic_ctx += f"{register_cov}\n\n"
            if main_score.melody:
                critic_ctx += f"Main score reference:\n{main_score.to_description(key, scale_type)[:800]}\n\n"
            critic_ctx += f"Score summary:\n{current_score.to_llm_description()}\n\n"
            critic_ctx += f"Evaluate {inst_name}'s part. Check density, fit, and idiom."

            crit_resp = await self._call_agent(self.critic, messages, critic_ctx)
            messages.append({"source": "critic", "content": crit_resp})

            passes = False
            for data in _find_json_objects(crit_resp):
                passes = data.get("passes", False)
                critic_feedback = data.get("revision_instructions", "")
                score_val = data.get("overall_score", 0)
                logger.info(f"    [{inst_name}] Inner Critic score={score_val}, passes={passes}")

            if passes:
                logger.info(f"    [{inst_name}] Inner Critic passed at round {inner_rnd}")
                break

        return inner_articulations

    # ------------------------------------------------------------------
    # Ensemble Critic
    # ------------------------------------------------------------------

    async def _run_ensemble_critic(
        self, current_score, main_score, enriched_sections,
        blueprint_instruments, lyrics, role_mins, inst_ranges,
        messages, progress,
    ) -> dict:
        logger.info("  === Ensemble Critic ===")
        self.critic.set_mode("ensemble")

        if self._on_progress:
            await self._on_progress("critic", "Ensemble review", progress)

        bpb = current_score.time_signature[0] if current_score.time_signature else 4

        density_hm = compute_density_heatmap(current_score, bpb)
        gap_rpt = detect_gaps(current_score, role_mins, bpb)
        register_cov = compute_register_coverage(current_score, inst_ranges)
        # Convert to 0-indexed for compute_score_metrics (score notes are 0-indexed)
        enriched_0 = [
            {**sec, "start_beat": sec["start_beat"] - 1.0, "end_beat": sec["end_beat"] - 1.0}
            for sec in enriched_sections
        ]
        metrics = compute_score_metrics(current_score, enriched_0, lyrics)
        metrics_text = format_metrics_for_critic(metrics)

        inst_criteria = _build_critic_criteria(blueprint_instruments)

        critic_ctx = "ENSEMBLE REVIEW — evaluate all instruments together.\n\n"
        critic_ctx += f"{metrics_text}\n\n"
        critic_ctx += f"{density_hm}\n\n"
        if gap_rpt:
            critic_ctx += f"{gap_rpt}\n\n"
        critic_ctx += f"{register_cov}\n\n"
        if inst_criteria:
            critic_ctx += "INSTRUMENT CRITERIA:\n" + "\n".join(inst_criteria) + "\n\n"
        critic_ctx += f"Score:\n{current_score.to_llm_description()}\n\n"
        if main_score.melody:
            critic_ctx += f"Lead sheet:\n{main_score.to_description()[:600]}\n\n"
        critic_ctx += (
            "Evaluate the ensemble. Output main_score_changes (null if melody is fine), "
            "instrument_reruns (list of instruments to re-arrange), "
            "keep_instruments (list of satisfactory instruments)."
        )

        crit_resp = await self._call_agent(self.critic, messages, critic_ctx)
        messages.append({"source": "critic", "content": crit_resp})

        result = {
            "passes": False,
            "main_score_changes": None,
            "instrument_reruns": [],
            "keep_instruments": [],
            "distribution_update": "",
        }

        for data in _find_json_objects(crit_resp):
            result["passes"] = data.get("passes", False)
            result["main_score_changes"] = data.get("main_score_changes")
            result["instrument_reruns"] = data.get("instrument_reruns", [])
            result["keep_instruments"] = data.get("keep_instruments", [])
            result["distribution_update"] = data.get("distribution_update", "")
            score_val = data.get("overall_score", 0)
            logger.info(
                f"  Ensemble Critic score={score_val}, passes={result['passes']}, "
                f"reruns={result['instrument_reruns']}"
            )

        return result

    async def _call_agent(
        self, agent, history: list[dict], user_content: str,
    ) -> str:
        history_msgs = []
        for msg in history:
            history_msgs.append(TextMessage(
                content=msg["content"], source=msg["source"],
            ))
        history_msgs.append(TextMessage(
            content=user_content, source="user",
        ))

        t0 = time.time()
        resp = await agent.on_messages(history_msgs, self._cancel)
        raw = resp.chat_message.content if resp.chat_message else ""
        logger.info(
            f"  Agent '{agent.name}' responded "
            f"in {time.time() - t0:.1f}s"
        )
        return raw

    async def run_stream(self, request: MusicRequest):
        result = await self.run(request)
        for msg in result.messages:
            yield TextMessage(
                content=msg["content"], source=msg["source"],
            )

    async def close(self) -> None:
        await self.synthesizer.close()

    def _build_task(self, request: MusicRequest) -> str:
        parts = ["Create music based on this request:"]
        parts.append(f"Description: {request.description}")
        parts.append(f"Genre: {request.genre}")
        parts.append(f"Mood: {request.mood}")
        if request.tempo:
            parts.append(f"Tempo: {request.tempo} BPM")
        if request.key:
            parts.append(f"Key: {request.key}")
        if request.scale_type:
            parts.append(f"Scale: {request.scale_type}")
        if request.time_signature:
            parts.append(
                f"Time signature: "
                f"{request.time_signature[0]}/"
                f"{request.time_signature[1]}"
            )
        if request.instruments:
            inst_str = ", ".join(
                f"{i.name} ({i.role})" for i in request.instruments
            )
            parts.append(f"Instruments: {inst_str}")
        if request.sections:
            parts.append(
                f"Sections: {', '.join(request.sections)}"
            )
        if request.include_lyrics:
            parts.append(
                f"Lyrics: yes, language={request.lyric_language}, "
                f"theme={request.lyric_theme}"
            )
        return "\n".join(parts)


class PipelineResult:
    def __init__(
        self,
        messages: list[dict],
        total_messages: int = 0,
        completed: bool = False,
        error: str | None = None,
        midi_path: str | None = None,
        score: Score | None = None,
        snapshots: list[str] | None = None,
    ):
        self.messages = messages
        self.total_messages = total_messages
        self.completed = completed
        self.error = error
        self.midi_path = midi_path
        self.score = score
        self.snapshots = snapshots or []

    def summary(self) -> dict:
        return {
            "total_messages": self.total_messages,
            "completed": self.completed,
            "error": self.error,
            "midi_path": self.midi_path,
            "snapshots": self.snapshots,
            "agents_involved": list(
                {m["source"] for m in self.messages}
            ),
        }

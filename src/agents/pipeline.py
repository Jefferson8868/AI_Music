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
from src.llm.prompts import build_composer_section_prompt
from src.music.models import MusicRequest
from src.music.score import (
    Score, ScoreNote, ScoreSection, ScoreTrack,
    compute_score_metrics, format_metrics_for_critic,
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
# Pipeline
# ---------------------------------------------------------------------------

class MusicGenerationPipeline:
    """
    Two-phase pipeline with direct agent calls:
      Phase 1: Orchestrator blueprint + Synthesizer draft
      Phase 2: Collaborative refinement loop
               Composer (per-section) -> Lyricist -> Instrumentalist -> Critic
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
        grid = settings.quantization_grid

        title, key, scale_type = "Untitled", "C", "major"
        tempo: int = request.tempo or 120
        time_sig = (
            list(request.time_signature)
            if request.time_signature else [4, 4]
        )
        bpb = time_sig[0]
        blueprint_sections: list[dict] = []
        enriched_sections: list[dict] = []
        blueprint_instruments: list[dict] = []
        track_instruments: dict[str, dict] = {}
        lyrics: list[dict] = []
        current_score: Score | None = None
        all_tracks: dict[str, list[dict]] = {}

        if self._on_progress:
            await self._on_progress("start", "Pipeline started", 0.0)

        try:
            # ---- Phase 1: Setup ----
            logger.info("=== Phase 1: Setup ===")

            # 1a. Orchestrator
            if self._on_progress:
                await self._on_progress(
                    "orchestrator", "Creating blueprint", 0.05,
                )

            orch_resp = await self._call_agent(
                self.orchestrator, messages, task_text,
            )
            messages.append({
                "source": "orchestrator", "content": orch_resp,
            })
            logger.info(
                f"[Phase1] Orchestrator responded "
                f"({len(orch_resp)} chars)"
            )

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

            enriched_sections = _enrich_sections(
                blueprint_sections, bpb,
            )
            logger.info(
                f"[Phase1] Enriched {len(enriched_sections)} sections "
                f"with absolute beat ranges"
            )
            for sec in enriched_sections:
                logger.info(
                    f"  [{sec['name']}] bars={sec['bars']} "
                    f"beats={sec['start_beat']:.0f}"
                    f"-{sec['end_beat']:.0f}"
                )

            safe_t = _safe_title(title)

            # 1b. Synthesizer (Magenta draft)
            if self._on_progress:
                await self._on_progress(
                    "synthesizer", "Generating Magenta draft", 0.1,
                )

            synth_resp = await self._call_agent(
                self.synthesizer, messages, task_text,
            )
            messages.append({
                "source": "synthesizer", "content": synth_resp,
            })
            logger.info(
                f"[Phase1] Synthesizer responded "
                f"({len(synth_resp)} chars)"
            )

            draft_score = _build_score_from_composer(
                synth_resp, title, key, scale_type, tempo, time_sig,
                blueprint_sections, {}, [],
            )
            draft_description = ""
            if draft_score:
                draft_path = str(
                    drafts_dir / f"{safe_t}_round0_magenta.mid"
                )
                save_score_midi(draft_score, draft_path)
                snapshots.append(draft_path)
                draft_description = draft_score.to_llm_description()
                logger.info(
                    f"[Phase1] Magenta draft saved: {draft_path}"
                )
            else:
                logger.warning(
                    "[Phase1] No usable score from Magenta"
                )

            # ---- Phase 2: Collaborative Refinement Loop ----
            logger.info("=== Phase 2: Collaborative Refinement ===")
            max_rounds = settings.max_refinement_rounds
            critic_feedback = ""

            for rnd in range(1, max_rounds + 1):
                base_progress = 0.15 + (
                    (rnd - 1) / max_rounds
                ) * 0.75
                step = 0.75 / max_rounds / 4

                # -- 2a. Composer (per-section) --
                if self._on_progress:
                    await self._on_progress(
                        "composer",
                        f"Round {rnd}/{max_rounds}: Composing",
                        base_progress,
                    )

                all_tracks = {}
                completed = []
                for si, sec in enumerate(enriched_sections):
                    prev_summary = _previous_section_summary(
                        all_tracks, completed,
                    )
                    section_prompt = build_composer_section_prompt(
                        section_name=sec["name"],
                        start_beat=sec["start_beat"],
                        end_beat=sec["end_beat"],
                        bars=sec["bars"],
                        mood=sec.get("mood", ""),
                        instruments=blueprint_instruments,
                        key=key,
                        scale_type=scale_type,
                        previous_summary=prev_summary,
                        draft_description=(
                            draft_description if rnd == 1 else ""
                        ),
                        critic_feedback=(
                            critic_feedback if si == 0 else ""
                        ),
                    )

                    comp_resp = await self._call_agent(
                        self.composer, messages, section_prompt,
                    )
                    messages.append({
                        "source": "composer", "content": comp_resp,
                    })

                    section_tracks = None
                    for data in _find_json_objects(comp_resp):
                        candidate = _extract_tracks_from_json(data)
                        if candidate:
                            section_tracks = candidate
                            break

                    if section_tracks:
                        for trk_name, notes in section_tracks.items():
                            notes = _quantize_notes(notes, grid)
                            notes = _clamp_to_section(
                                notes,
                                sec["start_beat"],
                                sec["end_beat"],
                            )
                            notes = _clamp_pitch_range(
                                notes, trk_name,
                            )
                            all_tracks.setdefault(
                                trk_name, [],
                            ).extend(notes)
                        logger.info(
                            f"[Round {rnd}] [{sec['name']}] "
                            f"extracted "
                            f"{sum(len(n) for n in section_tracks.values())}"
                            f" notes"
                        )
                    else:
                        logger.warning(
                            f"[Round {rnd}] [{sec['name']}] "
                            f"no notes extracted"
                        )

                    completed.append(sec)

                total_n = sum(len(n) for n in all_tracks.values())
                logger.info(
                    f"[Round {rnd}] Composer total: {total_n} notes "
                    f"across {len(all_tracks)} tracks"
                )

                current_score = _build_score_from_sections(
                    all_tracks, title, key, scale_type, tempo,
                    time_sig, enriched_sections,
                    track_instruments, lyrics,
                )
                if current_score:
                    snap = str(
                        drafts_dir / f"{safe_t}_round{rnd}.mid"
                    )
                    save_score_midi(current_score, snap)
                    snapshots.append(snap)
                    logger.info(
                        f"[Round {rnd}] Snapshot: {snap}"
                    )

                # -- 2b. Lyricist --
                if self._on_progress:
                    await self._on_progress(
                        "lyricist",
                        f"Round {rnd}/{max_rounds}: Writing lyrics",
                        base_progress + step,
                    )

                lyricist_context = f"Blueprint:\n{orch_resp}\n\n"
                lyricist_context += (
                    "Section beat ranges "
                    "(computed by system, use these exactly):\n"
                )
                for sec in enriched_sections:
                    lyricist_context += (
                        f"  [{sec['name']}] beats "
                        f"{sec['start_beat']:.0f}"
                        f"-{sec['end_beat']:.0f}\n"
                    )
                lyricist_context += "\n"

                if current_score:
                    skeleton = _extract_melody_skeleton(
                        current_score, enriched_sections,
                    )
                    skel_text = _format_skeleton_for_lyricist(
                        skeleton, enriched_sections,
                    )
                    lyricist_context += skel_text + "\n\n"

                if lyrics:
                    lyricist_context += (
                        "Previous lyrics (revise or keep):\n"
                        + json.dumps(
                            lyrics, ensure_ascii=False,
                        )[:1500]
                        + "\n\n"
                    )
                if critic_feedback:
                    lyricist_context += (
                        f"Critic feedback:\n{critic_feedback}\n\n"
                    )
                lyricist_context += (
                    "Write or revise lyrics. "
                    "Place each lyric ONLY on melody note beats."
                )

                lyr_resp = await self._call_agent(
                    self.lyricist, messages, lyricist_context,
                )
                messages.append({
                    "source": "lyricist", "content": lyr_resp,
                })
                logger.info(
                    f"[Round {rnd}] Lyricist responded "
                    f"({len(lyr_resp)} chars)"
                )

                lyrics = []
                for data in _find_json_objects(lyr_resp):
                    if (
                        "lyrics" in data
                        and isinstance(data["lyrics"], list)
                    ):
                        lyrics.extend(data["lyrics"])
                    elif (
                        "lines" in data
                        and isinstance(data["lines"], list)
                    ):
                        lyrics.append(data)

                if current_score and lyrics:
                    melody_trk = next(
                        (t for t in current_score.tracks
                         if "melody" in t.name.lower()
                         or t.role == "melody"),
                        None,
                    )
                    if melody_trk:
                        melody_beats = {
                            n.start_beat for n in melody_trk.notes
                        }
                        lyrics = _filter_lyrics_to_melody(
                            lyrics, melody_beats,
                        )

                # -- 2c. Instrumentalist --
                if self._on_progress:
                    await self._on_progress(
                        "instrumentalist",
                        f"Round {rnd}/{max_rounds}: Orchestrating",
                        base_progress + step * 2,
                    )

                inst_context = ""
                if current_score:
                    inst_context += (
                        f"Score summary:\n"
                        f"{current_score.to_llm_description()}\n\n"
                    )
                inst_context += (
                    "Section beat ranges:\n"
                )
                for sec in enriched_sections:
                    inst_context += (
                        f"  [{sec['name']}] beats "
                        f"{sec['start_beat']:.0f}"
                        f"-{sec['end_beat']:.0f}\n"
                    )
                inst_context += (
                    "\nAssign instruments, MIDI channels, "
                    "GM program numbers, and articulations."
                )

                inst_resp = await self._call_agent(
                    self.instrumentalist, messages, inst_context,
                )
                messages.append({
                    "source": "instrumentalist",
                    "content": inst_resp,
                })
                logger.info(
                    f"[Round {rnd}] Instrumentalist responded "
                    f"({len(inst_resp)} chars)"
                )

                track_instruments = {}
                articulations: dict[str, list[dict]] = {}
                for data in _find_json_objects(inst_resp):
                    for trk in data.get("tracks", []):
                        if not isinstance(trk, dict):
                            continue
                        if "instrument" not in trk:
                            continue
                        iname = trk["instrument"]
                        raw_p = int(trk.get("program_number", 0))
                        prog = _map_instrument_program(iname, raw_p)
                        track_instruments[iname] = {
                            "instrument": iname,
                            "role": trk.get(
                                "role", "accompaniment",
                            ),
                            "channel": int(
                                trk.get("midi_channel", 0),
                            ),
                            "program": prog,
                        }
                        arts = trk.get("articulations", [])
                        if isinstance(arts, list) and arts:
                            articulations[iname] = arts

                track_instruments = _validate_channels(
                    track_instruments,
                )

                # -- 2d. Critic --
                if self._on_progress:
                    await self._on_progress(
                        "critic",
                        f"Round {rnd}/{max_rounds}: Reviewing",
                        base_progress + step * 3,
                    )

                critic_context = ""
                if current_score:
                    metrics = compute_score_metrics(
                        current_score, enriched_sections, lyrics,
                    )
                    critic_context += (
                        format_metrics_for_critic(metrics) + "\n\n"
                    )
                    critic_context += (
                        "Score summary:\n"
                        + current_score.to_llm_description()
                        + "\n\n"
                    )

                if lyrics:
                    critic_context += (
                        "Lyrics:\n"
                        + json.dumps(
                            lyrics, ensure_ascii=False,
                        )[:1500]
                        + "\n\n"
                    )

                critic_context += (
                    "Evaluate the music AND lyrics together. "
                    "Use the metrics above as facts. "
                    "Focus on qualitative musical judgment."
                )

                crit_resp = await self._call_agent(
                    self.critic, messages, critic_context,
                )
                messages.append({
                    "source": "critic", "content": crit_resp,
                })
                logger.info(
                    f"[Round {rnd}] Critic responded "
                    f"({len(crit_resp)} chars)"
                )

                passes = False
                for data in _find_json_objects(crit_resp):
                    passes = data.get("passes", False)
                    critic_feedback = data.get(
                        "revision_instructions", "",
                    )
                    score_val = data.get("overall_score", 0)
                    logger.info(
                        f"[Round {rnd}] Critic "
                        f"score={score_val}, "
                        f"passes={passes}"
                    )

                if passes:
                    logger.info(
                        f"[Round {rnd}] Critic passed"
                    )
                    break

            if not current_score:
                logger.warning(
                    "No score produced -- returning empty result"
                )
                return PipelineResult(
                    messages=messages,
                    total_messages=len(messages),
                    error="No score produced after refinement",
                    snapshots=snapshots,
                )

            # ---- Build final MIDI ----
            logger.info("=== Building final MIDI ===")
            final_score = _build_score_from_sections(
                all_tracks, title, key, scale_type, tempo,
                time_sig, enriched_sections,
                track_instruments, lyrics,
            )
            if not final_score:
                final_score = current_score

            ts = int(time.time())
            midi_path = str(
                settings.output_dir / f"{safe_t}_{ts}.mid"
            )
            save_score_midi(
                final_score, midi_path,
                articulations=articulations,
            )
            logger.info(f"Final MIDI exported: {midi_path}")

            if self._on_progress:
                await self._on_progress(
                    "done", "Pipeline complete", 1.0,
                )

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

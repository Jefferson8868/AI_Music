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
from dataclasses import dataclass, field
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
# Round 2 Phase B: rule-based rhythm / bass / transition agents.
from src.agents.drum_agent import DrumAgent
from src.agents.bass_agent import BassAgent, extract_kick_positions
from src.agents.post_production_delta import (
    build_cumulative_score_history,
    build_post_production_delta,
)
from src.agents.section_continuity import (
    extract_section_tail,
    format_main_hook_for_composer,
    format_section_tail_for_composer,
)
from src.agents.transition_agent import TransitionAgent
from src.llm.client import create_llm_client
from src.llm.prompts import (
    SPOTLIGHT_REVIEW_SYSTEM,
    build_composer_section_prompt,
    build_spotlight_review_prompt,
)
from src.knowledge.instruments import (
    format_for_composer,
    format_for_instrumentalist,
    format_for_critic,
    get_continuity_profile,
    get_ornament_vocabulary,
)
from src.knowledge.query_machine import (
    get_default_machine as get_knowledge_machine,
    theory_hints_for_request,
)
from src.knowledge.spotlight_presets import (
    build_default_all_active,
    detect_preset_from_request,
    expand_preset,
)
from src.music.models import MusicRequest
from src.music.ornaments import (
    ORNAMENT_MACROS,
    ornament_is_known,
)
from src.music.performance import apply_performance_render
from src.music.performance_chinese import apply_chinese_performance
from src.music.humanize import humanize_score
from src.audio import (
    MixError,
    RendererError,
    is_mix_available,
    is_renderer_available,
    mix_stems,
    render_midi_to_wav,
)
from src.vocals import (
    VocalSynthError,
    is_vocal_synth_available,
    lyrics_to_phonemes,
    render_vocal_stem,
)
from src.music.score import (
    Score, ScoreNote, ScoreSection, ScoreTrack,
    SpotlightEntry, SpotlightProposal,
    compute_score_metrics, format_metrics_for_critic,
)
from src.music.lyrics_alignment import (
    analyze_lyrics,
    compute_section_char_targets,
    format_char_count_plan_for_lyricist,
    format_char_count_violations,
    format_density_plan_for_lyricist,
    format_lyrics_feedback_for_lyricist,
    validate_section_char_counts,
)
from src.music.midi_writer import save_score_midi
from config.settings import settings

# Confidence thresholds for spotlight proposals.
SPOTLIGHT_AUTO_ACCEPT = 0.9
SPOTLIGHT_AUTO_DROP = 0.7
LYRICS_MIN_TOTAL_LINES = 4  # verse + chorus combined


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
    "electric guitar": 27, "e-guitar": 27, "distortion guitar": 30,
    "electric bass": 34, "bass guitar": 33, "synth bass": 38,
    "drum kit": 0, "drums": 0,
    "cello": 42, "violin": 40, "viola": 41, "contrabass": 43,
}

_GM_PITCH_RANGES = {
    "piano": (21, 108), "violin": (55, 103), "viola": (48, 91),
    "cello": (36, 76), "contrabass": (28, 67), "flute": (60, 96),
    "guzheng": (43, 96), "erhu": (55, 91), "dizi": (60, 96),
    "pipa": (45, 93), "xiao": (55, 84),
    "electric guitar": (40, 88), "e-guitar": (40, 88),
    "electric bass": (28, 55), "bass guitar": (28, 55),
    "synth bass": (28, 64),
    "drums": (35, 81), "drum kit": (35, 81),
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
                ornaments = _sanitize_ornaments(n.get("ornaments"))
                result.setdefault(name, []).append({
                    "pitch": pitch,
                    "start_beat": float(start),
                    "duration_beats": dur,
                    "velocity": min(127, max(1, int(vel))),
                    "ornaments": ornaments,
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
# Spotlight plan helpers
# ---------------------------------------------------------------------------

def _parse_spotlight_from_orch(
    orch_data: dict, all_instruments: list[str],
) -> list[SpotlightEntry]:
    """Parse a spotlight_plan block from Orchestrator JSON output."""
    raw = orch_data.get("spotlight_plan", [])
    if not isinstance(raw, list) or not raw:
        return []
    all_lower = {i.lower(): i for i in all_instruments}
    entries: list[SpotlightEntry] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        sec = str(item.get("section", "")).strip()
        if not sec:
            continue
        active_spec = item.get("active", [])
        if active_spec == "ALL":
            active = list(all_instruments)
        elif isinstance(active_spec, list):
            active = []
            for token in active_spec:
                if not isinstance(token, str):
                    continue
                key = token.strip().lower()
                if key in all_lower and all_lower[key] not in active:
                    active.append(all_lower[key])
                else:
                    # substring match fallback
                    for lower, original in all_lower.items():
                        if (
                            (key in lower or lower in key)
                            and original not in active
                        ):
                            active.append(original)
                            break
        else:
            active = list(all_instruments)
        featured_raw = item.get("featured", [])
        featured: list[str] = []
        if isinstance(featured_raw, list):
            for token in featured_raw:
                if not isinstance(token, str):
                    continue
                key = token.strip().lower()
                if key in all_lower and all_lower[key] in active:
                    if all_lower[key] not in featured:
                        featured.append(all_lower[key])
        silent = [i for i in all_instruments if i not in active]
        entries.append(SpotlightEntry(
            section=sec, active=active,
            featured=featured, silent=silent,
        ))
    return entries


def _ensure_spotlight_plan(
    orch_data: dict,
    blueprint_instruments: list[dict],
    enriched_sections: list[dict],
    request_description: str,
) -> list[SpotlightEntry]:
    """Return a complete spotlight plan for every enriched section.

    Priority:
      1) Orchestrator's spotlight_plan (sections matched by name).
      2) For missing sections: preset inferred from request + instruments.
      3) Fallback: all instruments active everywhere.
    """
    all_inst_names = [i.get("name", "") for i in blueprint_instruments if i.get("name")]
    section_names = [s["name"] for s in enriched_sections]

    orch_entries = _parse_spotlight_from_orch(orch_data, all_inst_names)
    orch_map = {e.section.lower(): e for e in orch_entries}

    preset_name = detect_preset_from_request(
        request_description, all_inst_names,
    )
    preset_entries = expand_preset(
        preset_name, all_inst_names, section_names,
    )
    preset_map = {e.section.lower(): e for e in preset_entries}

    fallback_entries = build_default_all_active(
        all_inst_names, section_names,
    )
    fallback_map = {e.section.lower(): e for e in fallback_entries}

    final: list[SpotlightEntry] = []
    for name in section_names:
        key = name.lower()
        if key in orch_map:
            entry = orch_map[key]
            # normalize section name to enriched name (case may differ)
            entry.section = name
            final.append(entry)
            continue
        if key in preset_map:
            entry = preset_map[key]
            entry.section = name
            final.append(entry)
            continue
        final.append(fallback_map[key])
    logger.info(
        f"[spotlight] preset='{preset_name}', "
        f"orch_sections={len(orch_entries)}, "
        f"total_sections={len(final)}"
    )
    return final


def _get_spotlight_for_section(
    plan: list[SpotlightEntry], section_name: str,
) -> SpotlightEntry | None:
    key = section_name.lower()
    for entry in plan:
        if entry.section.lower() == key:
            return entry
    return None


def _build_section_ornament_vocab(
    featured_instruments: list[str],
) -> list[str]:
    """Build an ornament-token vocabulary tailored to a section's featured
    instruments. Lines look like:  "breath_swell (dizi): air rises into note."
    """
    universal = [
        "vibrato_light", "staccato", "tenuto", "legato_to_next",
        "grace_note_above", "grace_note_below",
    ]
    seen: list[str] = []
    lines: list[str] = []
    for inst in featured_instruments:
        for token in get_ornament_vocabulary(inst):
            if token in seen:
                continue
            seen.append(token)
            spec = ORNAMENT_MACROS.get(token)
            desc = spec.description if spec else ""
            lines.append(f"{token} ({inst}): {desc}")
    for token in universal:
        if token in seen:
            continue
        spec = ORNAMENT_MACROS.get(token)
        desc = spec.description if spec else ""
        lines.append(f"{token}: {desc}")
    return lines


def _extract_spotlight_proposals_from_json(
    data: dict,
) -> list[SpotlightProposal]:
    """Parse spotlight proposals from a Composer or Critic JSON response."""
    found: list[SpotlightProposal] = []
    candidates = []
    if isinstance(data.get("spotlight_proposal"), dict):
        candidates.append(data["spotlight_proposal"])
    raw_list = data.get("spotlight_proposals")
    if isinstance(raw_list, list):
        candidates.extend([x for x in raw_list if isinstance(x, dict)])
    for c in candidates:
        try:
            prop = SpotlightProposal(
                section=str(c.get("section", "")).strip(),
                add_instruments=[
                    str(x) for x in c.get("add_instruments", [])
                    if isinstance(x, str)
                ],
                remove_instruments=[
                    str(x) for x in c.get("remove_instruments", [])
                    if isinstance(x, str)
                ],
                reasoning=str(c.get("reasoning", "")),
                confidence=float(c.get("confidence", 0.0) or 0.0),
            )
        except (TypeError, ValueError):
            continue
        if not prop.section:
            continue
        if not prop.add_instruments and not prop.remove_instruments:
            continue
        found.append(prop)
    return found


def _apply_proposal_to_plan(
    plan: list[SpotlightEntry],
    prop: SpotlightProposal,
    all_instruments: list[str],
    source: str,
) -> bool:
    """Merge an accepted proposal into the spotlight plan.

    Returns True if the plan was modified.
    """
    entry = _get_spotlight_for_section(plan, prop.section)
    if entry is None:
        logger.warning(
            f"[spotlight] proposal references unknown "
            f"section '{prop.section}', skipped"
        )
        return False
    all_lower = {i.lower(): i for i in all_instruments}
    changed = False
    for token in prop.add_instruments:
        key = token.strip().lower()
        if key not in all_lower:
            continue
        canonical = all_lower[key]
        if canonical not in entry.active:
            entry.active.append(canonical)
            changed = True
        if canonical in entry.silent:
            entry.silent.remove(canonical)
            changed = True
    for token in prop.remove_instruments:
        key = token.strip().lower()
        if key not in all_lower:
            continue
        canonical = all_lower[key]
        if canonical in entry.active:
            entry.active.remove(canonical)
            changed = True
        if canonical in entry.featured:
            entry.featured.remove(canonical)
            changed = True
        if canonical not in entry.silent:
            entry.silent.append(canonical)
            changed = True
    if changed:
        logger.info(
            f"[spotlight] ({source}) applied proposal to "
            f"'{prop.section}' conf={prop.confidence:.2f}: "
            f"+{prop.add_instruments} -{prop.remove_instruments}"
        )
    return changed


# Re-export from the lightweight helper module so existing call sites and
# tests can import from either location.
from src.agents.spotlight_review import (
    match_bass_token as _match_bass_token,
    match_drum_token as _match_drum_token,
    parse_spotlight_review_decisions as _parse_spotlight_review_decisions,
)


# ---------------------------------------------------------------------------
# Critic feedback routing (Improvement E)
# ---------------------------------------------------------------------------

@dataclass
class CriticRound:
    """One round's parsed critic output."""

    overall_score: float = 0.0
    aspect_scores: dict[str, float] = field(default_factory=dict)
    passes: bool = False
    agent_revisions: dict[str, str] = field(default_factory=dict)
    section_revisions: dict[str, str] = field(default_factory=dict)
    issues: list[dict] = field(default_factory=list)
    raw_instructions: str = ""
    plateau_warning: bool = False


def _parse_critic_round(data: dict) -> CriticRound:
    """Parse a critic JSON blob into CriticRound (tolerant to missing keys)."""
    round_out = CriticRound()
    try:
        round_out.overall_score = float(data.get("overall_score", 0.0) or 0.0)
    except (TypeError, ValueError):
        round_out.overall_score = 0.0
    aspects = data.get("aspect_scores") or {}
    if isinstance(aspects, dict):
        for k, v in aspects.items():
            try:
                round_out.aspect_scores[str(k)] = float(v)
            except (TypeError, ValueError):
                continue
    round_out.passes = bool(data.get("passes", False))
    round_out.raw_instructions = str(data.get("revision_instructions", ""))
    round_out.plateau_warning = bool(data.get("plateau_warning", False))
    ar = data.get("agent_revisions") or {}
    if isinstance(ar, dict):
        for k, v in ar.items():
            if isinstance(v, str) and v.strip():
                round_out.agent_revisions[str(k).lower()] = v.strip()
    sr = data.get("section_revisions") or {}
    if isinstance(sr, dict):
        for k, v in sr.items():
            if isinstance(v, str) and v.strip():
                round_out.section_revisions[str(k).lower()] = v.strip()
    issues = data.get("issues") or []
    if isinstance(issues, list):
        for iss in issues:
            if isinstance(iss, dict):
                round_out.issues.append(iss)
    # Backfill section_revisions from issue.target_sections if critic
    # forgot to fill section_revisions explicitly.
    if not round_out.section_revisions and round_out.issues:
        for iss in round_out.issues:
            targets = iss.get("target_sections") or []
            desc = iss.get("description", "") or ""
            suggestion = iss.get("suggestion", "") or ""
            msg_core = " ".join(
                filter(None, [desc, suggestion])
            ).strip()
            if not msg_core:
                continue
            if isinstance(targets, list):
                for t in targets:
                    if not isinstance(t, str):
                        continue
                    key = t.lower().strip()
                    if not key:
                        continue
                    prev = round_out.section_revisions.get(key, "")
                    round_out.section_revisions[key] = (
                        (prev + " " if prev else "") + msg_core
                    )
    # Backfill agent_revisions from raw_instructions if agent_revisions
    # is empty — legacy critics dump everything into one string.
    if not round_out.agent_revisions and round_out.raw_instructions:
        round_out.agent_revisions["composer"] = round_out.raw_instructions
        round_out.agent_revisions["instrumentalist"] = (
            round_out.raw_instructions
        )
        round_out.agent_revisions["lyricist"] = round_out.raw_instructions
    return round_out


def _feedback_for_section(
    critic_round: CriticRound | None, section_name: str,
) -> str:
    """Return the per-section feedback text for the Composer.

    Falls back to the generic agent_revisions['composer'] + overall
    instructions so section 0 is NOT the only one that sees guidance
    (the old bug).
    """
    if critic_round is None:
        return ""
    section_key = (section_name or "").lower().strip()
    chunks: list[str] = []
    sec_msg = critic_round.section_revisions.get(section_key, "")
    if sec_msg:
        chunks.append(f"[{section_name}] {sec_msg}")
    composer_msg = critic_round.agent_revisions.get("composer", "")
    if composer_msg and composer_msg not in chunks:
        chunks.append(composer_msg)
    # Also surface high-severity issues matching this section.
    for iss in critic_round.issues:
        sev = str(iss.get("severity", "")).lower()
        tgts = [
            str(t).lower() for t in (iss.get("target_sections") or [])
        ]
        if sev in ("major", "critical") and section_key in tgts:
            desc = iss.get("description", "")
            sugg = iss.get("suggestion", "")
            if desc or sugg:
                chunks.append(f"! {desc} → {sugg}".strip())
    return "\n".join(chunks).strip()


def _build_delta_block(
    current: CriticRound | None, previous: CriticRound | None,
) -> str:
    """Render a DELTA block showing changes from the previous round.

    Returns an empty string if either round is missing.
    """
    if not current or not previous:
        return ""
    lines: list[str] = ["DELTA FROM PREVIOUS ROUND:"]
    d_overall = current.overall_score - previous.overall_score
    sign = "+" if d_overall >= 0 else ""
    lines.append(
        f"  overall_score: {previous.overall_score:.2f} -> "
        f"{current.overall_score:.2f} ({sign}{d_overall:.2f})"
    )
    all_aspects = set(current.aspect_scores) | set(previous.aspect_scores)
    for aspect in sorted(all_aspects):
        cur = current.aspect_scores.get(aspect, 0.0)
        pre = previous.aspect_scores.get(aspect, 0.0)
        diff = cur - pre
        sign = "+" if diff >= 0 else ""
        lines.append(
            f"  {aspect}: {pre:.2f} -> {cur:.2f} "
            f"({sign}{diff:.2f})"
        )
    if current.plateau_warning:
        lines.append(
            "  plateau_warning=true — scores stuck; push for "
            "SPECIFIC revisions this round."
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Ornament extraction
# ---------------------------------------------------------------------------

def _sanitize_ornaments(raw) -> list[str]:
    """Normalize an ornaments field on a note payload."""
    if not raw:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    cleaned: list[str] = []
    for t in raw:
        if not isinstance(t, str):
            continue
        token = t.strip()
        if not token:
            continue
        if not ornament_is_known(token):
            logger.debug(
                f"[ornament] dropped unknown token: {token!r}"
            )
            continue
        if token in cleaned:
            continue
        cleaned.append(token)
    return cleaned


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
        # Round 2 Phase B: rule-based agents (no LLM). Constructed once,
        # reused across sections.
        self.drum_agent = DrumAgent()
        self.bass_agent = BassAgent()
        self.transition_agent = TransitionAgent()

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

            orch_data_full: dict = {}
            orchestrator_main_hook: list[dict] = []
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
                if "spotlight_plan" in data:
                    orch_data_full = data
                # Bug E: main_hook motif — quoted in verse + chorus so
                # the piece has motivic unity across sections.
                hook_candidate = data.get("main_hook")
                if isinstance(hook_candidate, list) and hook_candidate:
                    orchestrator_main_hook = [
                        n for n in hook_candidate if isinstance(n, dict)
                    ]

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

            # Spotlight plan (proposed by Orchestrator or preset-derived).
            spotlight_plan: list[SpotlightEntry] = _ensure_spotlight_plan(
                orch_data_full or {},
                blueprint_instruments,
                enriched_sections,
                request.description or "",
            )
            for entry in spotlight_plan:
                logger.info(
                    f"  spotlight[{entry.section}] "
                    f"active={entry.active} "
                    f"featured={entry.featured}"
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

            # Bug E: if the Orchestrator didn't emit an explicit main_hook,
            # fall back to the first 6 notes of the Magenta melody draft so
            # verse + chorus still have a shared motif to quote.
            main_hook_notes: list[dict] = list(orchestrator_main_hook)
            if not main_hook_notes and draft_score:
                melody_trk = next(
                    (
                        t for t in draft_score.tracks
                        if (t.role or "").lower() == "melody"
                        or "melody" in (t.name or "").lower()
                    ),
                    None,
                )
                if melody_trk and melody_trk.notes:
                    main_hook_notes = [
                        {
                            "pitch": n.pitch,
                            "start_beat": n.start_beat,
                            "duration_beats": n.duration_beats,
                            "velocity": n.velocity,
                        }
                        for n in melody_trk.notes[:6]
                    ]
            if main_hook_notes:
                logger.info(
                    f"[Phase1] main_hook motif "
                    f"({len(main_hook_notes)} notes) established"
                )

            # Round 2 Phase A: multi-engine reference fanout.
            # The Synthesizer embeds a per-engine note split as a
            # `draft_perspectives` JSON block so the Composer can see
            # alternative drafts (Composer's Assistant 2 / MMT / FIGARO)
            # without having to copy any of them verbatim.
            draft_perspectives: dict[str, list[dict]] = {}
            for data in _find_json_objects(synth_resp):
                dp = data.get("draft_perspectives")
                if isinstance(dp, dict) and dp:
                    for label, notes in dp.items():
                        if isinstance(notes, list) and notes:
                            draft_perspectives[str(label)] = list(notes)
                    break
            if draft_perspectives:
                labels = ", ".join(
                    f"{k}({len(v)})" for k, v in draft_perspectives.items()
                )
                logger.info(
                    f"[Phase1] Reference-engine drafts collected: {labels}"
                )

            # ---- Phase 2: Collaborative Refinement Loop ----
            logger.info("=== Phase 2: Collaborative Refinement ===")
            max_rounds = settings.max_refinement_rounds
            # critic_feedback kept as a plain string for legacy callers;
            # the structured CriticRound carries per-section / per-agent
            # routing (Improvement E).
            critic_feedback = ""
            # Articulations survive the Phase 2 loop so that the final MIDI
            # writer below always has something well-typed to consume, even
            # if max_rounds==0 or the instrumentalist round is skipped.
            articulations: dict[str, list[dict]] = {}
            critic_round_current: CriticRound | None = None
            critic_round_previous: CriticRound | None = None
            # Plateau detection: remember overall_score history.
            score_history: list[float] = []

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
                collected_proposals: list[tuple[str, SpotlightProposal]] = []
                inst_knowledge_cache = _build_composer_knowledge(
                    blueprint_instruments,
                )
                for si, sec in enumerate(enriched_sections):
                    prev_summary = _previous_section_summary(
                        all_tracks, completed,
                    )

                    # Bug E: real neighbor-section context. Last ~8 beats
                    # of every track in the previous section + the shared
                    # main-hook motif (only injected in verse/chorus/
                    # pre_chorus — intro/outro/bridge stay free to
                    # contrast).
                    last_sec_done = completed[-1] if completed else None
                    prev_tail_text = (
                        format_section_tail_for_composer(
                            extract_section_tail(
                                all_tracks, last_sec_done,
                            ),
                            last_sec_done,
                        )
                        if last_sec_done else ""
                    )
                    hook_text = format_main_hook_for_composer(
                        main_hook_notes, sec["name"],
                    )

                    sec_spotlight = _get_spotlight_for_section(
                        spotlight_plan, sec["name"],
                    )
                    if sec_spotlight:
                        active_instruments = list(sec_spotlight.active)
                        featured_instruments = list(sec_spotlight.featured)
                    else:
                        active_instruments = [
                            i.get("name", "")
                            for i in blueprint_instruments
                        ]
                        featured_instruments = []

                    # Build section-specific inst knowledge: featured first,
                    # only cards for active instruments.
                    inst_knowledge: list[str] = []
                    active_lower = {a.lower() for a in active_instruments}
                    feat_lower = {f.lower() for f in featured_instruments}
                    for inst in blueprint_instruments:
                        iname = inst.get("name", "")
                        if iname.lower() not in active_lower:
                            continue
                        is_feat = iname.lower() in feat_lower
                        text = format_for_composer(
                            iname,
                            inst.get("role", "accompaniment"),
                            section=sec["name"],
                            is_featured=is_feat,
                        )
                        if text:
                            inst_knowledge.append(text)
                    if not inst_knowledge:
                        inst_knowledge = inst_knowledge_cache

                    ornament_vocab = _build_section_ornament_vocab(
                        featured_instruments,
                    )

                    # Build continuity_profiles map for the active
                    # instruments — this is what teaches SUPPORTING
                    # tracks (piano, strings, cello) not to drop to
                    # a single note per bar when Dizi/Erhu take the
                    # spotlight.
                    continuity_profiles: dict[str, dict] = {}
                    for inst in blueprint_instruments:
                        iname = inst.get("name", "")
                        if iname.lower() not in active_lower:
                            continue
                        prof = get_continuity_profile(iname)
                        if prof:
                            continuity_profiles[iname] = prof

                    # Pull a small set of theory hints from the
                    # knowledge machine. Cheap (local curated keyword
                    # search); cached per pipeline call via the
                    # module-level singleton.
                    req_genre = (
                        getattr(request, "genre", None) or ""
                    )
                    try:
                        sec_theory_hints = theory_hints_for_request(
                            genre=req_genre,
                            agent_name="composer",
                            extra_question=(
                                f"{sec['name']} {sec.get('mood', '')} "
                                f"{key} {scale_type}"
                            ),
                            max_results=3,
                        )
                    except Exception as exc:
                        logger.warning(
                            "Knowledge query failed: %s", exc,
                        )
                        sec_theory_hints = []

                    # Per-section critic feedback (fixes the "only
                    # section 0 sees guidance" bug). Falls back to the
                    # generic composer-wide instructions when no
                    # section-specific message exists.
                    section_feedback = _feedback_for_section(
                        critic_round_current, sec["name"],
                    ) or critic_feedback

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
                        critic_feedback=section_feedback,
                        instrument_knowledge=inst_knowledge,
                        active_instruments=active_instruments,
                        featured_instruments=featured_instruments,
                        ornament_vocabulary=ornament_vocab,
                        continuity_profiles=continuity_profiles,
                        theory_hints=sec_theory_hints,
                        # Round 2 Phase A: only inject on round 1 to keep
                        # later-round prompts compact. Multi-engine drafts
                        # are inspiration material, not course correction.
                        draft_perspectives=(
                            draft_perspectives if rnd == 1 else None
                        ),
                        previous_section_tail=prev_tail_text,
                        main_hook=hook_text,
                    )

                    comp_resp = await self._call_agent(
                        self.composer, messages, section_prompt,
                    )
                    messages.append({
                        "source": "composer", "content": comp_resp,
                    })

                    section_tracks = None
                    for data in _find_json_objects(comp_resp):
                        # Collect spotlight proposals before anything else
                        for prop in _extract_spotlight_proposals_from_json(
                            data,
                        ):
                            collected_proposals.append(
                                ("composer", prop)
                            )
                        candidate = _extract_tracks_from_json(data)
                        if candidate and section_tracks is None:
                            section_tracks = candidate

                    if section_tracks:
                        # Drop tracks for silent instruments in THIS section.
                        filtered: dict[str, list[dict]] = {}
                        for trk_name, notes in section_tracks.items():
                            if active_instruments:
                                matched = False
                                tn = trk_name.lower()
                                for ai in active_instruments:
                                    ail = ai.lower()
                                    if (
                                        ail == tn
                                        or ail in tn
                                        or tn in ail
                                    ):
                                        matched = True
                                        break
                                if not matched:
                                    logger.info(
                                        f"[spotlight] dropping silent "
                                        f"track '{trk_name}' from "
                                        f"[{sec['name']}]"
                                    )
                                    continue
                            filtered[trk_name] = notes
                        for trk_name, notes in filtered.items():
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
                            f"{sum(len(n) for n in filtered.values())}"
                            f" notes (after spotlight filter)"
                        )
                    else:
                        logger.warning(
                            f"[Round {rnd}] [{sec['name']}] "
                            f"no notes extracted"
                        )

                    completed.append(sec)

                # After composing all sections: review spotlight proposals.
                if collected_proposals:
                    await self._review_and_apply_proposals(
                        proposals=collected_proposals,
                        spotlight_plan=spotlight_plan,
                        blueprint_instruments=blueprint_instruments,
                    )

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

                # Improvement F: density plan (always) + per-round
                # feedback report (when we have previous lyrics + a
                # current score to analyze against).
                density_plan_text = format_density_plan_for_lyricist(
                    enriched_sections,
                )
                if density_plan_text:
                    lyricist_context += density_plan_text + "\n\n"

                # Bug D: absolute per-section character budget. Density
                # alone was advisory and frequently ignored; this adds a
                # HARD min/target/max character count per section so the
                # validator below can re-prompt on concrete violations.
                char_targets = compute_section_char_targets(
                    enriched_sections,
                )
                char_plan_text = format_char_count_plan_for_lyricist(
                    char_targets,
                )
                if char_plan_text:
                    lyricist_context += char_plan_text + "\n\n"

                lyrics_report = None
                if lyrics and current_score:
                    try:
                        lyrics_report = analyze_lyrics(
                            current_score, lyrics, enriched_sections,
                        )
                    except Exception as exc:
                        logger.warning(
                            "Lyrics analysis failed: %s", exc,
                        )
                        lyrics_report = None
                if lyrics_report and lyrics_report.sections:
                    feedback_text = (
                        format_lyrics_feedback_for_lyricist(
                            lyrics_report,
                        )
                    )
                    if feedback_text:
                        lyricist_context += feedback_text + "\n\n"

                lyr_feedback = ""
                if critic_round_current is not None:
                    lyr_feedback = (
                        critic_round_current.agent_revisions.get(
                            "lyricist", "",
                        )
                        or critic_feedback
                    )
                else:
                    lyr_feedback = critic_feedback
                if lyr_feedback:
                    lyricist_context += (
                        f"Critic feedback (for lyricist):\n"
                        f"{lyr_feedback}\n\n"
                    )
                lyricist_context += (
                    "Write or revise lyrics. "
                    "Place each lyric ONLY on melody note beats. "
                    "Respect the density plan above. For Chinese "
                    "lyrics, prefer characters whose tone matches the "
                    "melody contour at that beat (rising tone on "
                    "rising melody, falling tone on falling melody)."
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

                # Lyrics re-prompt loop: ensure ≥LYRICS_MIN_TOTAL_LINES
                # lines across verse+chorus when lyrics are requested.
                if (
                    request.include_lyrics
                    and current_score is not None
                ):
                    total_lines = sum(
                        len(b.get("lines", [])) for b in lyrics
                        if b.get("section_name", "").lower()
                        in ("verse", "chorus", "pre_chorus", "bridge")
                    )
                    if total_lines < LYRICS_MIN_TOTAL_LINES:
                        logger.info(
                            f"[Round {rnd}] Lyrics underfilled "
                            f"({total_lines} lines), re-prompting"
                        )
                        reprompt_ctx = (
                            lyricist_context
                            + f"\n\nHARD REQUIREMENT: emit at LEAST "
                            f"{LYRICS_MIN_TOTAL_LINES} lines total "
                            "across the verse and chorus sections. "
                            "Each line should span at least 4 melody "
                            "beats. Do not skip chorus."
                        )
                        lyr_resp2 = await self._call_agent(
                            self.lyricist, messages, reprompt_ctx,
                        )
                        messages.append({
                            "source": "lyricist", "content": lyr_resp2,
                        })
                        extra_lyrics: list[dict] = []
                        for data in _find_json_objects(lyr_resp2):
                            if (
                                "lyrics" in data
                                and isinstance(data["lyrics"], list)
                            ):
                                extra_lyrics.extend(data["lyrics"])
                            elif (
                                "lines" in data
                                and isinstance(data["lines"], list)
                            ):
                                extra_lyrics.append(data)
                        if extra_lyrics:
                            melody_trk = next(
                                (t for t in current_score.tracks
                                 if "melody" in t.name.lower()
                                 or t.role == "melody"),
                                None,
                            )
                            if melody_trk:
                                mb = {
                                    n.start_beat
                                    for n in melody_trk.notes
                                }
                                extra_lyrics = _filter_lyrics_to_melody(
                                    extra_lyrics, mb,
                                )
                            if extra_lyrics:
                                lyrics = extra_lyrics

                # Bug D: per-section character-count validation. After
                # the total-line re-prompt above we still need to verify
                # each section lands inside its min/max char budget —
                # the advisory density target used to let sections slip
                # (e.g., chorus with 3 characters or verse with 40).
                if request.include_lyrics and char_targets:
                    violations = validate_section_char_counts(
                        lyrics, char_targets,
                    )
                    if violations:
                        logger.info(
                            f"[Round {rnd}] Char-count violations in "
                            f"{len(violations)} section(s), re-prompting"
                        )
                        reprompt_ctx = (
                            lyricist_context
                            + "\n\n"
                            + format_char_count_violations(violations)
                            + "\n\nEmit the FULL lyrics JSON again "
                            "with ONLY the violations above corrected. "
                            "Keep sections that were already in range "
                            "unchanged. Respect the HARD character "
                            "budget for every section."
                        )
                        lyr_resp3 = await self._call_agent(
                            self.lyricist, messages, reprompt_ctx,
                        )
                        messages.append({
                            "source": "lyricist",
                            "content": lyr_resp3,
                        })
                        fixed_lyrics: list[dict] = []
                        for data in _find_json_objects(lyr_resp3):
                            if (
                                "lyrics" in data
                                and isinstance(data["lyrics"], list)
                            ):
                                fixed_lyrics.extend(data["lyrics"])
                            elif (
                                "lines" in data
                                and isinstance(data["lines"], list)
                            ):
                                fixed_lyrics.append(data)
                        if fixed_lyrics and current_score:
                            melody_trk = next(
                                (t for t in current_score.tracks
                                 if "melody" in t.name.lower()
                                 or t.role == "melody"),
                                None,
                            )
                            if melody_trk:
                                mb = {
                                    n.start_beat
                                    for n in melody_trk.notes
                                }
                                fixed_lyrics = _filter_lyrics_to_melody(
                                    fixed_lyrics, mb,
                                )
                            if fixed_lyrics:
                                # Only adopt the corrected version if
                                # it actually reduces violations — a
                                # regression would be worse than the
                                # original underfill.
                                new_violations = (
                                    validate_section_char_counts(
                                        fixed_lyrics, char_targets,
                                    )
                                )
                                if (
                                    len(new_violations)
                                    <= len(violations)
                                ):
                                    lyrics = fixed_lyrics

                # -- 2c. Instrumentalist --
                if self._on_progress:
                    await self._on_progress(
                        "instrumentalist",
                        f"Round {rnd}/{max_rounds}: Orchestrating",
                        base_progress + step * 2,
                    )

                inst_techniques = _build_instrumentalist_techniques(
                    blueprint_instruments,
                )
                inst_context = ""
                if inst_techniques:
                    inst_context += (
                        "INSTRUMENT TECHNIQUE REFERENCE:\n"
                    )
                    for tech in inst_techniques:
                        inst_context += f"  {tech}\n"
                    inst_context += "\n"
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
                # Per-agent critic routing (Improvement E): give the
                # Instrumentalist its dedicated revisions slice instead of
                # letting it see only the "composer" feedback by accident.
                inst_feedback = ""
                if critic_round_current is not None:
                    inst_feedback = (
                        critic_round_current.agent_revisions.get(
                            "instrumentalist", "",
                        )
                        or critic_feedback
                    )
                else:
                    inst_feedback = critic_feedback
                if inst_feedback:
                    inst_context += (
                        "\nCritic feedback (for instrumentalist):\n"
                        f"{inst_feedback}\n\n"
                    )

                inst_context += (
                    "\nAssign instruments, MIDI channels, "
                    "GM program numbers, and articulations. "
                    "Use each instrument's specific techniques "
                    "when assigning articulations."
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

                inst_criteria = _build_critic_criteria(
                    blueprint_instruments,
                )
                critic_context = ""
                if inst_criteria:
                    critic_context += (
                        "INSTRUMENT-SPECIFIC EVALUATION "
                        "CRITERIA:\n"
                    )
                    for criterion in inst_criteria:
                        critic_context += f"{criterion}\n"
                    critic_context += "\n"

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
                    # Improvement F: surface the SAME lyrics report to
                    # the critic so the lyrics_alignment + tone_conflict
                    # numbers actually drive the critique instead of
                    # being private to the Lyricist.
                    if current_score:
                        try:
                            crit_lyrics_report = analyze_lyrics(
                                current_score, lyrics,
                                enriched_sections,
                            )
                        except Exception as exc:
                            logger.warning(
                                "Lyrics analysis for critic failed: %s",
                                exc,
                            )
                            crit_lyrics_report = None
                        if (
                            crit_lyrics_report
                            and crit_lyrics_report.sections
                        ):
                            critic_context += (
                                crit_lyrics_report.to_prompt_block()
                                + "\n\n"
                            )

                critic_context += (
                    "\nCURRENT SPOTLIGHT PLAN "
                    "(evaluate ensemble_spotlight):\n"
                )
                for entry in spotlight_plan:
                    active_str = ", ".join(entry.active) or "-"
                    feat_str = ", ".join(entry.featured) or "-"
                    critic_context += (
                        f"  {entry.section}: active=[{active_str}] "
                        f"featured=[{feat_str}]\n"
                    )
                critic_context += "\n"

                # Inject theory hints for the critic role — they sharpen
                # rubric-based judgments (harmony, spotlight, continuity,
                # ornaments).
                req_genre_for_critic = (
                    getattr(request, "genre", None) or ""
                )
                try:
                    critic_hints = theory_hints_for_request(
                        genre=req_genre_for_critic,
                        agent_name="critic",
                        extra_question="evaluation rubric "
                        + req_genre_for_critic,
                        max_results=4,
                    )
                except Exception as exc:
                    logger.warning(
                        "Critic theory hint query failed: %s", exc,
                    )
                    critic_hints = []
                if critic_hints:
                    critic_context += (
                        "\nTHEORY CONTEXT (evaluate against these):\n"
                    )
                    for hint in critic_hints:
                        critic_context += f"- {hint}\n"
                    critic_context += "\n"

                # Improvement E: show the critic how scores moved vs. the
                # previous round. This gives the critic iteration memory
                # so it can reason about "what changed, what didn't" and
                # issue SPECIFIC revisions rather than restating generic
                # observations.
                delta_block = _build_delta_block(
                    critic_round_current, critic_round_previous,
                )
                if delta_block:
                    critic_context += "\n" + delta_block + "\n"

                # Plateau detection: if the last 3 overall_scores are
                # within 0.03 we're stuck — tell the critic to break the
                # loop with more concrete, per-section demands.
                plateau_hit = (
                    len(score_history) >= 3
                    and max(score_history[-3:])
                    - min(score_history[-3:]) < 0.03
                )
                if plateau_hit:
                    critic_context += (
                        "\nPLATEAU DETECTED: the last 3 rounds' "
                        "overall_scores are within 0.03 of each other. "
                        "DO NOT restate generic observations. Pick the "
                        "ONE weakest section and the ONE weakest "
                        "instrument and demand a SPECIFIC change. "
                        "Set plateau_warning=true in your JSON so "
                        "downstream agents know to prioritize.\n"
                    )

                critic_context += (
                    "Evaluate the music AND lyrics together. "
                    "Use the metrics above as facts. "
                    "Focus on qualitative musical judgment. "
                    "Check instrument_idiom using the criteria "
                    "above. Check ensemble_spotlight against the plan. "
                    "Emit spotlight_proposals if the plan should change. "
                    "Populate agent_revisions (composer / instrumentalist "
                    "/ lyricist) and section_revisions (per section) so "
                    "your feedback routes to the right collaborator."
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
                critic_proposals: list[
                    tuple[str, SpotlightProposal]
                ] = []
                # Improvement E: parse into CriticRound so the NEXT
                # composer/instrumentalist/lyricist calls can pull
                # per-agent + per-section revisions instead of all sharing
                # one string.
                new_round: CriticRound | None = None
                for data in _find_json_objects(crit_resp):
                    parsed = _parse_critic_round(data)
                    if new_round is None:
                        new_round = parsed
                    else:
                        # Later JSON blobs in the same response overwrite
                        # earlier ones for scalar fields but merge lists.
                        if parsed.overall_score:
                            new_round.overall_score = parsed.overall_score
                        if parsed.aspect_scores:
                            new_round.aspect_scores.update(
                                parsed.aspect_scores,
                            )
                        new_round.passes = new_round.passes or parsed.passes
                        new_round.plateau_warning = (
                            new_round.plateau_warning
                            or parsed.plateau_warning
                        )
                        if parsed.raw_instructions:
                            new_round.raw_instructions = (
                                parsed.raw_instructions
                            )
                        new_round.agent_revisions.update(
                            parsed.agent_revisions,
                        )
                        new_round.section_revisions.update(
                            parsed.section_revisions,
                        )
                        new_round.issues.extend(parsed.issues)
                    for prop in _extract_spotlight_proposals_from_json(
                        data,
                    ):
                        critic_proposals.append(("critic", prop))

                if new_round is not None:
                    critic_round_previous = critic_round_current
                    critic_round_current = new_round
                    passes = new_round.passes
                    critic_feedback = new_round.raw_instructions
                    score_history.append(new_round.overall_score)
                    logger.info(
                        f"[Round {rnd}] Critic "
                        f"score={new_round.overall_score:.2f}, "
                        f"passes={passes}, "
                        f"agent_targets="
                        f"{sorted(new_round.agent_revisions.keys())}, "
                        f"section_targets="
                        f"{sorted(new_round.section_revisions.keys())}"
                    )
                    if plateau_hit:
                        # If our client-side detector fired, force-mark the
                        # flag so downstream agents treat this as such.
                        critic_round_current.plateau_warning = True
                else:
                    logger.warning(
                        f"[Round {rnd}] Critic returned no parseable "
                        "JSON — keeping previous round state."
                    )

                if critic_proposals:
                    await self._review_and_apply_proposals(
                        proposals=critic_proposals,
                        spotlight_plan=spotlight_plan,
                        blueprint_instruments=blueprint_instruments,
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

            # Bug C: snapshot the composer's final score BEFORE any
            # post-production runs (Phase 3.5 / 4 / 4b / 4c). The final
            # critic pass (after Phase 4c) uses this snapshot to build a
            # POST-PRODUCTION DELTA block so it can judge what drums /
            # bass / ornaments / humanization actually added on top of
            # the LLM's composed notes.
            pre_postproduction_score = (
                final_score.model_copy(deep=True) if final_score else None
            )

            # ---- Phase 3.5: DrumAgent + BassAgent + TransitionAgent ----
            # Augment the final score with song-feel machinery:
            #   * DrumAgent writes a groove-templated drum kit per section
            #     where the spotlight plan marks drums as active.
            #   * BassAgent writes a bass line locked to the drum kicks.
            #   * TransitionAgent scans section boundaries and plans
            #     one ear-candy recipe per boundary.
            try:
                self._augment_with_drum_bass_transition(
                    final_score, spotlight_plan, enriched_sections,
                    request=request, tempo=tempo, key=key,
                    scale_type=scale_type,
                )
            except Exception as e:
                logger.warning(
                    f"[Phase3.5] Drum/Bass/Transition augmentation "
                    f"failed: {e}"
                )

            # ---- Phase 4: Performance render ----
            # Ornament macros -> pitch-bend / CC / note retrigger events.
            # Idempotent (ScoreTrack.rendered flag), so safe even if this
            # function is ever invoked a second time.
            try:
                logger.info("=== Phase 4: Performance render ===")
                final_score = apply_performance_render(final_score)
                bend_count = sum(
                    len(t.pitch_bends) for t in final_score.tracks
                )
                cc_count = sum(
                    len(t.cc_events) for t in final_score.tracks
                )
                logger.info(
                    f"[Phase4] Rendered {bend_count} pitch-bend events, "
                    f"{cc_count} CC events across "
                    f"{len(final_score.tracks)} tracks"
                )
            except Exception as e:
                logger.warning(
                    f"[Phase4] Performance render failed: {e}. "
                    "Falling back to un-rendered score."
                )

            # ---- Phase 4b: Chinese-instrument idiom pass ----
            # erhu / dizi / pipa get delayed vibrato + portamento +
            # breath spikes. Runs after generic ornament expansion so
            # its events layer on top without clobbering the ornament
            # bends.
            try:
                logger.info("=== Phase 4b: Chinese-instrument idioms ===")
                final_score = apply_chinese_performance(final_score)
            except Exception as e:
                logger.warning(
                    f"[Phase4b] Chinese-idiom pass failed: {e}"
                )

            # ---- Phase 4c: Humanizer ----
            # Velocity jitter + micro-timing + round-robin detune +
            # phrase-level tempo breathing. Idempotent via
            # ScoreTrack.humanized. Runs LAST so its jitter sits on top
            # of everything deterministic.
            try:
                logger.info("=== Phase 4c: Humanizer ===")
                if settings.humanize:
                    final_score = humanize_score(
                        final_score, seed=settings.humanize_seed,
                    )
                else:
                    logger.info(
                        "[Phase4c] Humanizer disabled via settings"
                    )
            except Exception as e:
                logger.warning(f"[Phase4c] Humanizer failed: {e}")

            # ---- Phase 4d: Final critic pass (Bug C) ----
            # The in-loop critic only ever saw the composer's raw output
            # — it never got to judge the drums, bass, ornaments, or
            # humanization that Phase 3.5 / 4 layered on top. Run the
            # critic ONCE more now with a POST-PRODUCTION DELTA block so
            # its verdict reflects what the listener actually hears.
            # Read-only: no re-runs, but the verdict is surfaced on
            # ``PipelineResult.final_critic`` for callers to inspect.
            final_critic_round: CriticRound | None = None
            try:
                final_critic_round = await self._run_final_critic_pass(
                    final_score=final_score,
                    pre_postproduction_score=pre_postproduction_score,
                    score_history=score_history,
                    enriched_sections=enriched_sections,
                    messages=messages,
                    last_round=critic_round_current,
                )
            except Exception as e:
                logger.warning(
                    f"[Phase4d] Final critic pass failed: {e}"
                )

            ts = int(time.time())
            midi_path = str(
                settings.output_dir / f"{safe_t}_{ts}.mid"
            )
            save_score_midi(
                final_score, midi_path,
                articulations=articulations,
            )
            logger.info(f"Final MIDI exported: {midi_path}")

            # ---- Phase 5: Audio render (MIDI → WAV via FluidSynth) ----
            wav_path: str | None = None
            if settings.render_audio and is_renderer_available():
                try:
                    logger.info("=== Phase 5: Audio render ===")
                    wav = render_midi_to_wav(
                        midi_path,
                        out_path=Path(midi_path).with_suffix(".wav"),
                        soundfont=settings.soundfont_path,
                        sample_rate=settings.render_sample_rate,
                    )
                    wav_path = str(wav)
                    logger.info(f"[Phase5] Rendered audio: {wav_path}")
                except (RendererError, FileNotFoundError, Exception) as e:
                    logger.warning(
                        f"[Phase5] Audio render failed: {e}. "
                        "MIDI file was still saved."
                    )
            elif settings.render_audio:
                logger.info(
                    "[Phase5] render_audio=True but no FluidSynth "
                    "backend is installed; skipping audio render. "
                    "Install `pyfluidsynth` or the fluidsynth CLI "
                    "to enable."
                )

            # ---- Phase 5b: Vocal synthesis (DiffSinger / OpenUtau) ----
            # Turn lyrics + the melody track into a sung vocal .wav stem.
            # Silently degrades when OpenUtau isn't installed.
            vocal_wav_path: str | None = None
            if (
                settings.synthesize_vocals
                and lyrics
                and is_vocal_synth_available(settings.openutau_cli)
            ):
                try:
                    logger.info("=== Phase 5b: Vocal synthesis ===")
                    melody_trk = next(
                        (t for t in final_score.tracks
                         if "melody" in (t.name or "").lower()
                         or (t.role or "").lower() == "melody"),
                        None,
                    )
                    if melody_trk is None and final_score.tracks:
                        melody_trk = final_score.tracks[0]

                    phonemes = lyrics_to_phonemes(
                        lyrics=lyrics,
                        melody_track=melody_trk,
                    )
                    if phonemes:
                        vocal_out = Path(midi_path).with_name(
                            Path(midi_path).stem + "_vocal.wav"
                        )
                        vocal_wav = render_vocal_stem(
                            phonemes,
                            voicebank=settings.vocal_voicebank,
                            out_path=vocal_out,
                            tempo_bpm=float(tempo),
                            project_name=title,
                        )
                        vocal_wav_path = str(vocal_wav)
                        logger.info(
                            f"[Phase5b] Rendered vocal stem: "
                            f"{vocal_wav_path} "
                            f"({len(phonemes)} syllables)"
                        )
                    else:
                        logger.info(
                            "[Phase5b] No phonemes produced (empty "
                            "lyrics or no melody notes). Skipping."
                        )
                except VocalSynthError as e:
                    logger.warning(
                        f"[Phase5b] Vocal synthesis failed: {e}. "
                        "Instrumental output still saved."
                    )
                except Exception as e:
                    logger.warning(
                        f"[Phase5b] Vocal synthesis errored "
                        f"unexpectedly: {e}"
                    )
            elif settings.synthesize_vocals and lyrics:
                logger.info(
                    "[Phase5b] synthesize_vocals=True but OpenUtau CLI "
                    "not on PATH; skipping vocal synthesis. Install "
                    "OpenUtau from https://www.openutau.com/ to enable."
                )
            elif settings.synthesize_vocals:
                logger.info(
                    "[Phase5b] synthesize_vocals=True but no lyrics "
                    "in this Score; skipping."
                )

            # ---- Phase 6: Mix bus (sum + transition stems + FX) ----
            # Requires a base instrumental .wav (Phase 5) to exist.
            # Pedalboard FX chain is applied if the optional dep is
            # installed; otherwise we just sum + place stems.
            mixed_wav_path: str | None = None
            if settings.apply_mix and wav_path and is_mix_available():
                try:
                    logger.info("=== Phase 6: Mix bus ===")
                    mix_out = Path(wav_path).with_name(
                        Path(wav_path).stem + "_mixed.wav"
                    )
                    mixed = mix_stems(
                        instrumental_wav=wav_path,
                        vocal_wav=vocal_wav_path,
                        transition_events=getattr(
                            final_score, "transition_events", None,
                        ),
                        section_plan=spotlight_plan,
                        tempo_bpm=float(tempo),
                        out_path=mix_out,
                        seed=settings.humanize_seed or 0,
                    )
                    mixed_wav_path = str(mixed)
                    logger.info(
                        f"[Phase6] Final mix written: {mixed_wav_path}"
                    )
                except MixError as e:
                    logger.warning(
                        f"[Phase6] Mix failed ({e}); instrumental + "
                        "optional vocal still available."
                    )
                except Exception as e:
                    logger.warning(
                        f"[Phase6] Mix errored unexpectedly: {e}"
                    )
            elif settings.apply_mix and not wav_path:
                logger.info(
                    "[Phase6] apply_mix=True but no instrumental WAV "
                    "was produced in Phase 5; skipping mix."
                )
            elif settings.apply_mix:
                logger.info(
                    "[Phase6] apply_mix=True but numpy/soundfile "
                    "missing; skipping mix. Install both to enable."
                )

            if self._on_progress:
                await self._on_progress(
                    "done", "Pipeline complete", 1.0,
                )

            return PipelineResult(
                messages=messages,
                total_messages=len(messages),
                completed=True,
                midi_path=midi_path,
                wav_path=wav_path,
                vocal_wav_path=vocal_wav_path,
                mixed_wav_path=mixed_wav_path,
                score=final_score,
                snapshots=snapshots,
                final_critic=final_critic_round,
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

    async def _review_and_apply_proposals(
        self,
        proposals: list[tuple[str, SpotlightProposal]],
        spotlight_plan: list[SpotlightEntry],
        blueprint_instruments: list[dict],
    ) -> None:
        """Arbitrate spotlight proposals.

        - confidence >= SPOTLIGHT_AUTO_ACCEPT: apply immediately.
        - confidence <  SPOTLIGHT_AUTO_DROP: drop immediately.
        - between: ask the LLM directly (one batched call, bypassing
          OrchestratorAgent so the raw ``{"decisions": [...]}`` JSON
          isn't rewritten into a blueprint).
        """
        all_inst_names = [
            i.get("name", "")
            for i in blueprint_instruments if i.get("name")
        ]
        auto_accept: list[tuple[str, SpotlightProposal]] = []
        mid_conf: list[tuple[str, SpotlightProposal]] = []
        dropped = 0
        for source, prop in proposals:
            if prop.confidence >= SPOTLIGHT_AUTO_ACCEPT:
                auto_accept.append((source, prop))
            elif prop.confidence < SPOTLIGHT_AUTO_DROP:
                dropped += 1
                logger.info(
                    f"[spotlight] dropped {source} proposal "
                    f"'{prop.section}' conf={prop.confidence:.2f} "
                    "(below threshold)"
                )
            else:
                mid_conf.append((source, prop))

        for source, prop in auto_accept:
            _apply_proposal_to_plan(
                spotlight_plan, prop, all_inst_names,
                source=f"{source}/auto",
            )

        if not mid_conf:
            return

        # Batched Orchestrator review for mid-confidence proposals.
        current_spotlight_dicts = [
            {
                "section": e.section,
                "active": list(e.active),
                "featured": list(e.featured),
            }
            for e in spotlight_plan
        ]
        proposal_dicts = [
            {
                "section": p.section,
                "add_instruments": p.add_instruments,
                "remove_instruments": p.remove_instruments,
                "reasoning": p.reasoning,
                "confidence": p.confidence,
            }
            for _src, p in mid_conf
        ]
        review_prompt = build_spotlight_review_prompt(
            proposals=proposal_dicts,
            current_spotlight=current_spotlight_dicts,
        )
        logger.info(
            f"[spotlight] reviewing "
            f"{len(mid_conf)} mid-confidence proposal(s)"
        )
        try:
            review_resp = await self._review_spotlight_via_llm(
                review_prompt,
            )
        except Exception as e:
            logger.warning(
                f"[spotlight] review call failed ({e}), "
                "mid-confidence proposals dropped"
            )
            return
        accepted_indices = _parse_spotlight_review_decisions(
            review_resp, len(mid_conf),
        )
        for idx, (source, prop) in enumerate(mid_conf):
            if idx in accepted_indices:
                _apply_proposal_to_plan(
                    spotlight_plan, prop, all_inst_names,
                    source=f"{source}/reviewed",
                )
            else:
                logger.info(
                    f"[spotlight] reviewer rejected {source} "
                    f"proposal for '{prop.section}'"
                )

    async def _review_spotlight_via_llm(self, review_prompt: str) -> str:
        """Call the LLM directly for spotlight-proposal arbitration.

        This bypasses OrchestratorAgent (which always wraps replies as
        "[Orchestrator] Blueprint created:\\n```json\\n{...}\\n```" and
        would hide the ``{"decisions": [...]}`` JSON we need). The review
        is also excluded from the shared messages history because the
        accept/reject verdict is not useful context for downstream
        composer / critic calls.
        """
        from autogen_core.models import SystemMessage, UserMessage

        llm_messages = [
            SystemMessage(content=SPOTLIGHT_REVIEW_SYSTEM),
            UserMessage(content=review_prompt, source="pipeline"),
        ]
        result = await self._llm_client.create(
            llm_messages, cancellation_token=self._cancel,
        )
        raw = result.content if isinstance(result.content, str) \
            else str(result.content)
        return raw

    async def _run_final_critic_pass(
        self,
        final_score: Score,
        pre_postproduction_score: Score | None,
        score_history: list[float],
        enriched_sections: list[dict],
        messages: list[dict],
        last_round: "CriticRound | None",
    ) -> "CriticRound | None":
        """Bug C: evaluate the fully-rendered score after Phase 4c.

        The in-loop critic only ever sees the composer's raw note grid;
        this pass hands the critic a score that already has drums, bass,
        transitions, ornaments, and humanization applied — i.e. what the
        listener actually hears. We also show the cumulative score
        trajectory + a POST-PRODUCTION DELTA block so the critic's final
        verdict is framed against the in-loop history.

        Returns the parsed ``CriticRound`` (or ``None`` if the critic
        produced no parseable JSON). This pass is read-only — the
        verdict is surfaced on ``PipelineResult.final_critic`` but never
        triggers another refinement round.
        """
        if final_score is None:
            return None

        ctx = "FINAL CRITIC PASS — after Phase 3.5 + Phase 4 a/b/c.\n\n"

        ctx += (
            "Score summary (post-production, what the listener hears):\n"
            f"{final_score.to_llm_description()}\n\n"
        )

        try:
            metrics = compute_score_metrics(
                final_score, enriched_sections,
            )
            ctx += format_metrics_for_critic(metrics) + "\n\n"
        except Exception as exc:
            logger.debug(
                "Final-critic metrics computation failed: %s", exc,
            )

        delta_block = build_post_production_delta(
            pre_postproduction_score, final_score,
        )
        if delta_block:
            ctx += delta_block + "\n\n"

        history_block = build_cumulative_score_history(score_history)
        if history_block:
            ctx += history_block + "\n\n"

        if last_round is not None:
            ctx += (
                "Last in-loop critic verdict:\n"
                f"  overall_score={last_round.overall_score:.2f}, "
                f"passes={last_round.passes}\n\n"
            )

        ctx += (
            "This is the FINAL critic pass — there are no further "
            "refinement rounds. Focus on:\n"
            "  * Did Phase 3.5 / Phase 4 add audible song-feel "
            "(groove, ornaments, humanization) or does the output "
            "still sound symphonic/MIDI-scale?\n"
            "  * Are there regressions introduced by post-production "
            "(e.g., humanizer broke a deliberate sync point, drums "
            "drown the melody)?\n"
            "Emit your standard JSON verdict."
        )

        crit_resp = await self._call_agent(self.critic, messages, ctx)
        messages.append({"source": "critic_final", "content": crit_resp})

        final_round: CriticRound | None = None
        for data in _find_json_objects(crit_resp):
            parsed = _parse_critic_round(data)
            if final_round is None:
                final_round = parsed
            else:
                if parsed.overall_score:
                    final_round.overall_score = parsed.overall_score
                if parsed.aspect_scores:
                    final_round.aspect_scores.update(parsed.aspect_scores)
                final_round.passes = (
                    final_round.passes or parsed.passes
                )
                if parsed.raw_instructions:
                    final_round.raw_instructions = parsed.raw_instructions
                final_round.issues.extend(parsed.issues)

        if final_round is not None:
            logger.info(
                f"[Phase4d] Final critic "
                f"score={final_round.overall_score:.2f}, "
                f"passes={final_round.passes}"
            )
        else:
            logger.warning(
                "[Phase4d] Final critic returned no parseable JSON"
            )
        return final_round

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

    # ------------------------------------------------------------------
    # Phase 3.5 — Rule-based drum / bass / transition augmentation
    # ------------------------------------------------------------------

    def _augment_with_drum_bass_transition(
        self,
        final_score: Score,
        spotlight_plan: list[SpotlightEntry],
        enriched_sections: list[dict],
        request: MusicRequest,
        tempo: int,
        key: str,
        scale_type: str,
    ) -> None:
        """Inject song-feel machinery into the final score.

        Rule-based agents (DrumAgent, BassAgent, TransitionAgent) run
        AFTER the LLM composition rounds converge. They:

          1. Walk each enriched section and check the spotlight plan.
          2. If 'drums' is active → call DrumAgent.compose_section and
             merge the resulting ScoreTracks (drums_kick, drums_snare,
             drums_chh, drums_ohh, drums_crash, drums_perc, drums_fill)
             by voice across sections.
          3. If 'bass' is active → call BassAgent.compose_section with
             the kick positions from step 2.
          4. Any pre-existing LLM-authored drum / bass track is
             REMOVED first — the approved plan is explicit that
             modern pop should use a deterministic groove, not a
             per-note LLM drum part.
          5. After all sections are processed, TransitionAgent scans
             section boundaries and emits one ear-candy recipe per
             boundary (riser / reverse cymbal / impact / sub-drop /
             snare roll / kick drop / crash).

        Idempotent by virtue of the TransitionAgent's own guard
        (returns the existing list if transition_events is non-empty).
        """
        import re as _re

        # -- Parse the key -> bass-register MIDI root. --
        key_token = (key or "C").strip().split()[0]
        m = _re.match(r"([A-G][b#]?)", key_token)
        base_name = m.group(1) if m else "C"
        # Root at octave 4 (middle-ish), then drop two octaves for bass.
        root_mid = _NOTE_TO_MIDI.get(f"{base_name}4", 60)
        bass_root_midi = max(24, root_mid - 24)

        # -- Index spotlight entries by lower-case section name. --
        spotlight_by_section = {
            e.section.lower(): e for e in spotlight_plan
        }

        _KNOWN_ROLES = {
            "intro", "verse", "pre_chorus",
            "chorus", "bridge", "outro",
        }

        # -- Decide up front whether we'll emit any drum / bass track. --
        #    Use whole-word substring matching so canonical instrument
        #    names like "Cinematic Drums" or "Synth Bass" count.
        any_drum = False
        any_bass = False
        for sec in enriched_sections:
            entry = spotlight_by_section.get(sec["name"].lower())
            if entry is None:
                continue
            if any(_match_drum_token(a) for a in entry.active):
                any_drum = True
            if any(_match_bass_token(a) for a in entry.active):
                any_bass = True
            if any_drum and any_bass:
                break

        # -- Strip any pre-existing LLM-authored drum / bass tracks. --
        #    The rule-based groove is the canonical one from here on.
        if any_drum or any_bass:
            kept: list[ScoreTrack] = []
            removed = 0
            for t in final_score.tracks:
                name = t.name or ""
                inst = t.instrument or ""
                role_l = (t.role or "").lower()
                is_drum_tok = (
                    _match_drum_token(name)
                    or _match_drum_token(inst)
                    or role_l == "rhythm"
                )
                is_bass_tok = (
                    _match_bass_token(name)
                    or _match_bass_token(inst)
                    or role_l == "bass"
                )
                if (any_drum and is_drum_tok) or (any_bass and is_bass_tok):
                    removed += 1
                    continue
                kept.append(t)
            if removed:
                logger.info(
                    f"[Phase3.5] Replaced {removed} LLM-authored "
                    "drum/bass track(s) with rule-based groove"
                )
            final_score.tracks = kept

        # -- Per-voice merged drum tracks + a single merged bass track. --
        merged_drum: dict[str, ScoreTrack] = {}
        merged_bass: ScoreTrack | None = None
        drum_sections = 0
        bass_sections = 0
        genre_hint = (request.genre or "").strip()

        for sec in enriched_sections:
            sec_name = sec["name"]
            bars = int(sec.get("bars", 4))
            # Score uses 0-indexed beats; enriched_sections is 1-indexed.
            start_beat_s = sec["start_beat"] - 1.0
            end_beat_s = sec["end_beat"] - 1.0
            entry = spotlight_by_section.get(sec_name.lower())
            if entry is None:
                continue
            wants_drums = any(_match_drum_token(a) for a in entry.active)
            wants_bass = any(_match_bass_token(a) for a in entry.active)
            if not (wants_drums or wants_bass):
                continue

            # Resolve section_role from the blueprint name.
            role_candidate = sec.get("role") or sec_name
            role_key = str(role_candidate).lower().replace(" ", "_")
            section_role = (
                role_key if role_key in _KNOWN_ROLES else "verse"
            )

            drum_tracks: list[ScoreTrack] = []
            if wants_drums:
                try:
                    drum_tracks = self.drum_agent.compose_section(
                        section_role=section_role,  # type: ignore[arg-type]
                        start_beat=start_beat_s,
                        end_beat=end_beat_s,
                        bars=bars,
                        tempo_bpm=float(tempo),
                        genre_hint=genre_hint,
                    )
                    for trk in drum_tracks:
                        prev = merged_drum.get(trk.name)
                        if prev is None:
                            merged_drum[trk.name] = trk
                        else:
                            prev.notes.extend(trk.notes)
                    drum_sections += 1
                except Exception as exc:
                    logger.warning(
                        f"[Phase3.5] DrumAgent failed on "
                        f"section='{sec_name}': {exc}"
                    )
                    drum_tracks = []

            if wants_bass:
                try:
                    kick_positions = extract_kick_positions(drum_tracks)
                    bass_track = self.bass_agent.compose_section(
                        section_role=section_role,
                        start_beat=start_beat_s,
                        end_beat=end_beat_s,
                        bars=bars,
                        key_root_midi=bass_root_midi,
                        scale_type=scale_type,
                        kick_positions=(
                            kick_positions if kick_positions else None
                        ),
                    )
                    if merged_bass is None:
                        merged_bass = bass_track
                    else:
                        merged_bass.notes.extend(bass_track.notes)
                    bass_sections += 1
                except Exception as exc:
                    logger.warning(
                        f"[Phase3.5] BassAgent failed on "
                        f"section='{sec_name}': {exc}"
                    )

        # -- Sort every merged track's notes and append to final_score. --
        for trk in merged_drum.values():
            trk.notes.sort(key=lambda n: n.start_beat)
            final_score.tracks.append(trk)
        if merged_bass is not None:
            merged_bass.notes.sort(key=lambda n: n.start_beat)
            final_score.tracks.append(merged_bass)

        logger.info(
            f"[Phase3.5] DrumAgent: {drum_sections} section(s), "
            f"{len(merged_drum)} voice track(s); "
            f"BassAgent: {bass_sections} section(s), "
            f"{0 if merged_bass is None else len(merged_bass.notes)} note(s)"
        )

        # -- Plan section-boundary ear-candy. --
        try:
            self.transition_agent.attach(final_score)
            logger.info(
                f"[Phase3.5] TransitionAgent attached "
                f"{len(final_score.transition_events)} event(s)"
            )
        except Exception as exc:
            logger.warning(
                f"[Phase3.5] TransitionAgent failed: {exc}"
            )

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
        wav_path: str | None = None,
        vocal_wav_path: str | None = None,
        mixed_wav_path: str | None = None,
        score: Score | None = None,
        snapshots: list[str] | None = None,
        final_critic: "CriticRound | None" = None,
    ):
        self.messages = messages
        self.total_messages = total_messages
        self.completed = completed
        self.error = error
        self.midi_path = midi_path
        # Round 2 Phase D: WAV rendered from the final MIDI (FluidSynth).
        self.wav_path = wav_path
        # Round 2 Phase E: separately-synthesized vocal stem.
        self.vocal_wav_path = vocal_wav_path
        # Round 2 Phase F: mixdown (instrumental + vocal + transitions).
        self.mixed_wav_path = mixed_wav_path
        self.score = score
        self.snapshots = snapshots or []
        # Bug C: verdict from the critic pass that ran AFTER Phase 4c
        # (ornaments + humanize + drums + transitions applied). None if
        # the final pass was skipped or failed.
        self.final_critic = final_critic

    def summary(self) -> dict:
        final_critic_summary: dict | None = None
        if self.final_critic is not None:
            final_critic_summary = {
                "overall_score": self.final_critic.overall_score,
                "passes": self.final_critic.passes,
                "aspect_scores": self.final_critic.aspect_scores,
                "plateau_warning": self.final_critic.plateau_warning,
            }
        return {
            "total_messages": self.total_messages,
            "completed": self.completed,
            "error": self.error,
            "midi_path": self.midi_path,
            "wav_path": self.wav_path,
            "vocal_wav_path": self.vocal_wav_path,
            "mixed_wav_path": self.mixed_wav_path,
            "snapshots": self.snapshots,
            "agents_involved": list(
                {m["source"] for m in self.messages}
            ),
            "final_critic": final_critic_summary,
        }

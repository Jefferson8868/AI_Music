"""
Multi-Agent Pipeline — Structured three-phase orchestration.

  Phase 1  Setup:       Orchestrator (blueprint) + Synthesizer (Magenta draft)
  Phase 2  Refinement:  Composer/Critic loop for N rounds with MIDI snapshots
  Phase 3  Finalization: Lyricist + Instrumentalist
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
from src.music.models import MusicRequest
from src.music.score import Score
from src.music.midi_writer import save_score_midi
from config.settings import settings


ProgressCallback = Callable[[str, str, float], Awaitable[None]]


# ---------------------------------------------------------------------------
# Note / instrument parsing helpers (unchanged from before)
# ---------------------------------------------------------------------------

_NOTE_TO_MIDI = {}
for _oct in range(0, 10):
    for _name, _offset in [("C", 0), ("C#", 1), ("Db", 1), ("D", 2), ("D#", 3),
                            ("Eb", 3), ("E", 4), ("F", 5), ("F#", 6), ("Gb", 6),
                            ("G", 7), ("G#", 8), ("Ab", 8), ("A", 9), ("A#", 10),
                            ("Bb", 10), ("B", 11)]:
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


def _map_instrument_program(instrument_name: str, given_program: int) -> int:
    name_lower = instrument_name.lower()
    for key, prog in _CHINESE_INSTRUMENT_GM.items():
        if key in name_lower:
            return prog
    return given_program


def _find_json_objects(text: str) -> list[dict]:
    import re
    text = re.sub(r'```(?:json)?\s*', '', text)
    text = re.sub(r'```', '', text)
    results = []
    i = 0
    while i < len(text):
        if text[i] == '{':
            depth = 0
            start = i
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


def _extract_tracks_from_json(data: dict) -> dict[str, list[dict]] | None:
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
                dur = _parse_duration(n.get("duration_beats") or n.get("duration"))
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
            dur = _parse_duration(edit.get("duration_beats") or edit.get("duration"))
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
        avg_pitch = sum(n["pitch"] for n in notes) / len(notes) if notes else 60
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
                        "beat": float(line.get("start_beat", start_beat)),
                    })
    return result if result else None


def _safe_title(title: str) -> str:
    return title.encode("ascii", errors="replace").decode("ascii").replace("?", "_")


# ---------------------------------------------------------------------------
# Score building from a single agent message
# ---------------------------------------------------------------------------

def _build_score_from_composer(
    text: str,
    title: str, key: str, scale_type: str,
    tempo: int, time_sig: list[int],
    blueprint_sections: list[dict],
    track_instruments: dict[str, dict],
    lyrics: list[dict],
) -> Score | None:
    from src.music.score import ScoreNote, ScoreSection, ScoreTrack

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

    beats_per_bar = time_sig[0] if time_sig else 4
    sections: list[ScoreSection] = []
    beat_offset = 0.0
    if blueprint_sections:
        for sd in blueprint_sections:
            bars = int(sd.get("bars", 4))
            sections.append(ScoreSection(
                name=sd["name"], start_beat=beat_offset, bars=bars,
                lyrics=_get_section_lyrics(
                    sd["name"], beat_offset,
                    beat_offset + bars * beats_per_bar, lyrics,
                ),
            ))
            beat_offset += bars * beats_per_bar
    else:
        max_beat = max(
            max(n["start_beat"] + n["duration_beats"] for n in ns)
            for ns in best_tracks.values()
        )
        sections.append(ScoreSection(
            name="main", start_beat=0.0,
            bars=int(max_beat / beats_per_bar) + 1,
        ))

    tracks: list[ScoreTrack] = []
    inst_list = list(track_instruments.values())
    used_channels: set[int] = set()

    for idx, (track_name, notes) in enumerate(best_tracks.items()):
        instrument_name, matched = _match_instrument(track_name, inst_list, notes)
        program = _map_instrument_program(
            instrument_name, matched.get("program", 0) if matched else 0,
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
    logger.info(f"Score built: '{title}', {len(tracks)} tracks, {total_notes} notes")
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
    Three-phase pipeline with direct agent calls:
      Phase 1: Orchestrator blueprint + Synthesizer draft
      Phase 2: Composer/Critic refinement loop (N rounds, MIDI snapshot each)
      Phase 3: Lyricist + Instrumentalist finalization
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

        self.orchestrator = OrchestratorAgent(name="orchestrator", model_client=self._llm_client)
        self.composer = ComposerAgent(name="composer", model_client=self._llm_client)
        self.lyricist = LyricistAgent(name="lyricist", model_client=self._llm_client)
        self.instrumentalist = InstrumentalistAgent(name="instrumentalist", model_client=self._llm_client)
        self.critic = CriticAgent(name="critic", model_client=self._llm_client)
        self.synthesizer = SynthesizerAgent(name="synthesizer")

    async def run(self, request: MusicRequest) -> PipelineResult:
        task_text = self._build_task(request)
        logger.info(f"Starting pipeline for: {request.description[:80]}")

        messages: list[dict] = []
        snapshots: list[str] = []
        drafts_dir = settings.output_dir / "drafts"
        drafts_dir.mkdir(parents=True, exist_ok=True)

        title, key, scale_type = "Untitled", "C", "major"
        tempo: int = request.tempo or 120
        time_sig = list(request.time_signature) if request.time_signature else [4, 4]
        blueprint_sections: list[dict] = []
        track_instruments: dict[str, dict] = {}
        lyrics: list[dict] = []
        current_score: Score | None = None

        if self._on_progress:
            await self._on_progress("start", "Pipeline started", 0.0)

        try:
            # ---- Phase 1: Setup ----
            logger.info("=== Phase 1: Setup ===")

            # 1a. Orchestrator
            if self._on_progress:
                await self._on_progress("orchestrator", "Creating blueprint", 0.05)

            orch_resp = await self._call_agent(
                self.orchestrator, messages, task_text,
            )
            messages.append({"source": "orchestrator", "content": orch_resp})
            logger.info(f"[Phase1] Orchestrator responded ({len(orch_resp)} chars)")

            for data in _find_json_objects(orch_resp):
                title = data.get("title", title)
                key = data.get("key", key)
                scale_type = data.get("scale_type", scale_type)
                tempo = data.get("tempo", tempo)
                time_sig = data.get("time_signature", time_sig)
                blueprint_sections = []
                for sec in data.get("sections", []):
                    if isinstance(sec, dict) and "name" in sec:
                        blueprint_sections.append(sec)

            safe_t = _safe_title(title)

            # 1b. Synthesizer (Magenta draft)
            if self._on_progress:
                await self._on_progress("synthesizer", "Generating Magenta draft", 0.1)

            synth_resp = await self._call_agent(
                self.synthesizer, messages, task_text,
            )
            messages.append({"source": "synthesizer", "content": synth_resp})
            logger.info(f"[Phase1] Synthesizer responded ({len(synth_resp)} chars)")

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
                logger.info(f"[Phase1] Magenta draft saved: {draft_path} ({sum(len(t.notes) for t in draft_score.tracks)} notes)")
            else:
                logger.warning("[Phase1] No usable score from Magenta, proceeding without draft")

            # ---- Phase 2: Refinement Loop ----
            logger.info("=== Phase 2: Refinement ===")
            max_rounds = settings.max_refinement_rounds
            critic_feedback = ""

            for rnd in range(1, max_rounds + 1):
                progress = 0.15 + (rnd / max_rounds) * 0.6
                if self._on_progress:
                    await self._on_progress("composer", f"Composing (round {rnd}/{max_rounds})", progress)

                # Build context for composer
                composer_context = f"Blueprint:\n{orch_resp}\n\n"
                if draft_description:
                    composer_context += f"Magenta draft summary:\n{draft_description}\n\n"
                if current_score:
                    composer_context += f"Current score summary:\n{current_score.to_llm_description()}\n\n"
                if critic_feedback:
                    composer_context += f"Critic feedback from previous round:\n{critic_feedback}\n\n"
                composer_context += "Write or revise the COMPLETE score as JSON."

                # Composer
                comp_resp = await self._call_agent(
                    self.composer, messages, composer_context,
                )
                messages.append({"source": "composer", "content": comp_resp})
                logger.info(f"[Round {rnd}] Composer responded ({len(comp_resp)} chars)")

                new_score = _build_score_from_composer(
                    comp_resp, title, key, scale_type, tempo, time_sig,
                    blueprint_sections, track_instruments, lyrics,
                )
                if new_score:
                    current_score = new_score
                    snap_path = str(drafts_dir / f"{safe_t}_round{rnd}.mid")
                    save_score_midi(current_score, snap_path)
                    snapshots.append(snap_path)
                    total_n = sum(len(t.notes) for t in current_score.tracks)
                    logger.info(f"[Round {rnd}] Snapshot saved: {snap_path} ({total_n} notes)")
                else:
                    logger.warning(f"[Round {rnd}] Could not extract score from composer")

                # Critic
                if self._on_progress:
                    await self._on_progress("critic", f"Reviewing (round {rnd}/{max_rounds})", progress + 0.05)

                critic_context = "Review the following score.\n\n"
                if current_score:
                    critic_context += current_score.to_llm_description()
                else:
                    critic_context += comp_resp[:3000]

                crit_resp = await self._call_agent(
                    self.critic, messages, critic_context,
                )
                messages.append({"source": "critic", "content": crit_resp})
                logger.info(f"[Round {rnd}] Critic responded ({len(crit_resp)} chars)")

                passes = False
                for data in _find_json_objects(crit_resp):
                    passes = data.get("passes", False)
                    critic_feedback = data.get("revision_instructions", "")
                    score_val = data.get("overall_score", 0)
                    logger.info(f"[Round {rnd}] Critic score={score_val}, passes={passes}")

                if passes:
                    logger.info(f"[Round {rnd}] Critic passed — exiting refinement loop")
                    break

            if not current_score:
                logger.warning("No score produced after refinement — returning empty result")
                return PipelineResult(
                    messages=messages, total_messages=len(messages),
                    error="No score produced after refinement rounds",
                    snapshots=snapshots,
                )

            # ---- Phase 3: Finalization ----
            logger.info("=== Phase 3: Finalization ===")

            # Lyricist
            if self._on_progress:
                await self._on_progress("lyricist", "Writing lyrics", 0.8)

            lyricist_context = (
                f"Blueprint:\n{orch_resp}\n\n"
                f"Score summary:\n{current_score.to_llm_description()}\n\n"
                "Write lyrics for this piece."
            )
            lyr_resp = await self._call_agent(
                self.lyricist, messages, lyricist_context,
            )
            messages.append({"source": "lyricist", "content": lyr_resp})
            logger.info(f"[Phase3] Lyricist responded ({len(lyr_resp)} chars)")

            for data in _find_json_objects(lyr_resp):
                if "lyrics" in data and isinstance(data["lyrics"], list):
                    lyrics.extend(data["lyrics"])
                elif "lines" in data and isinstance(data["lines"], list):
                    lyrics.append(data)

            # Instrumentalist
            if self._on_progress:
                await self._on_progress("instrumentalist", "Assigning instruments", 0.9)

            inst_context = (
                f"Score summary:\n{current_score.to_llm_description()}\n\n"
                "Assign instruments, MIDI channels, and GM program numbers."
            )
            inst_resp = await self._call_agent(
                self.instrumentalist, messages, inst_context,
            )
            messages.append({"source": "instrumentalist", "content": inst_resp})
            logger.info(f"[Phase3] Instrumentalist responded ({len(inst_resp)} chars)")

            for data in _find_json_objects(inst_resp):
                for trk in data.get("tracks", []):
                    if isinstance(trk, dict) and "instrument" in trk:
                        inst_name = trk.get("instrument", "Piano")
                        raw_prog = int(trk.get("program_number", 0))
                        program = _map_instrument_program(inst_name, raw_prog)
                        track_instruments[inst_name] = {
                            "instrument": inst_name,
                            "role": trk.get("role", "accompaniment"),
                            "channel": int(trk.get("midi_channel", 0)),
                            "program": program,
                        }

            # Rebuild final score with lyrics and instrument assignments
            last_composer_text = ""
            for m in reversed(messages):
                if m["source"] == "composer":
                    last_composer_text = m["content"]
                    break
            final_score = _build_score_from_composer(
                last_composer_text,
                title, key, scale_type, tempo, time_sig,
                blueprint_sections, track_instruments, lyrics,
            )
            if not final_score:
                final_score = current_score

            # Save final MIDI
            ts = int(time.time())
            midi_path = str(settings.output_dir / f"{safe_t}_{ts}.mid")
            save_score_midi(final_score, midi_path)
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
                messages=messages, total_messages=len(messages),
                error=f"{str(e)}\n\nTRACEBACK:\n{full_tb}",
                snapshots=snapshots,
            )

    async def _call_agent(
        self, agent, history: list[dict], user_content: str,
    ) -> str:
        """Call a single agent with accumulated history + new user message."""
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
        logger.info(f"  Agent '{agent.name}' responded in {time.time() - t0:.1f}s")
        return raw

    async def run_stream(self, request: MusicRequest):
        """Compatibility wrapper — runs the pipeline and yields messages."""
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
            parts.append(f"Time signature: {request.time_signature[0]}/{request.time_signature[1]}")
        if request.instruments:
            inst_str = ", ".join(f"{i.name} ({i.role})" for i in request.instruments)
            parts.append(f"Instruments: {inst_str}")
        if request.sections:
            parts.append(f"Sections: {', '.join(request.sections)}")
        if request.include_lyrics:
            parts.append(f"Lyrics: yes, language={request.lyric_language}, theme={request.lyric_theme}")
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
            "agents_involved": list({m["source"] for m in self.messages}),
        }

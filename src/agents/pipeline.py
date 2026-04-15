"""
Multi-Agent Pipeline — SelectorGroupChat orchestration.

Implements the three-phase architecture:
  Phase 1: Creative Framework (Orchestrator → Composer → Lyricist)
  Phase 2: Draft Generation (Synthesizer → Magenta)
  Phase 3: Iterative Refinement (Critic → Composer → Lyricist → Instrumentalist loop)
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Callable, Awaitable

from autogen_agentchat.teams import SelectorGroupChat
from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination
from autogen_agentchat.messages import TextMessage
from loguru import logger

from src.agents.orchestrator import OrchestratorAgent
from src.agents.composer import ComposerAgent
from src.agents.lyricist import LyricistAgent
from src.agents.instrumentalist import InstrumentalistAgent
from src.agents.critic import CriticAgent
from src.agents.synthesizer import SynthesizerAgent
from src.llm.client import create_llm_client
from src.llm.prompts import SELECTOR_PROMPT
from src.music.models import MusicRequest
from src.music.score import Score
from src.music.midi_writer import save_score_midi
from config.settings import settings


ProgressCallback = Callable[[str, str, float], Awaitable[None]]


def _find_json_objects(text: str) -> list[dict]:
    """Extract all top-level JSON objects from a text string."""
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


class MusicGenerationPipeline:
    """
    Initializes all agents and the SelectorGroupChat team,
    then runs the full generation pipeline.
    """

    def __init__(
        self,
        backend: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        on_progress: ProgressCallback | None = None,
    ):
        self._on_progress = on_progress

        self._llm_client = create_llm_client(
            backend=backend, model=model, api_key=api_key,
        )

        self.orchestrator = OrchestratorAgent(name="orchestrator", model_client=self._llm_client)
        self.composer = ComposerAgent(name="composer", model_client=self._llm_client)
        self.lyricist = LyricistAgent(name="lyricist", model_client=self._llm_client)
        self.instrumentalist = InstrumentalistAgent(name="instrumentalist", model_client=self._llm_client)
        self.critic = CriticAgent(name="critic", model_client=self._llm_client)
        self.synthesizer = SynthesizerAgent(name="synthesizer")

        termination = (
            TextMentionTermination("FINALIZED")
            | MaxMessageTermination(max_messages=settings.max_group_chat_messages)
        )

        self.team = SelectorGroupChat(
            participants=[
                self.orchestrator,
                self.composer,
                self.lyricist,
                self.instrumentalist,
                self.critic,
                self.synthesizer,
            ],
            model_client=self._llm_client,
            termination_condition=termination,
            selector_prompt=SELECTOR_PROMPT,
            allow_repeated_speaker=True,
        )

    async def run(self, request: MusicRequest) -> PipelineResult:
        """Run the full multi-agent pipeline for a music generation request."""
        task_description = self._build_task(request)
        logger.info(f"Starting pipeline for: {request.description[:80]}")

        if self._on_progress:
            await self._on_progress("start", "Pipeline started", 0.0)

        try:
            logger.info("Pipeline: using run_stream to capture live messages")
            t0 = time.time()
            messages = []
            msg_count = 0
            async for event in self.team.run_stream(task=task_description):
                if hasattr(event, "source"):
                    source = getattr(event, "source", "unknown")
                    text = event.to_text() if hasattr(event, "to_text") else str(event)
                    msg_count += 1
                    elapsed = time.time() - t0
                    preview = text[:200].replace("\n", " ")
                    logger.info(
                        f"[msg {msg_count}] [{elapsed:.1f}s] "
                        f"{source}: {preview}..."
                    )
                    messages.append({"source": source, "content": text})

                    if self._on_progress:
                        progress = min(0.9, msg_count / settings.max_group_chat_messages)
                        await self._on_progress(
                            source, f"Agent {source} responded", progress,
                        )

            result = None
            logger.info(
                f"Pipeline finished: {msg_count} messages in {time.time() - t0:.1f}s"
            )

            if self._on_progress:
                await self._on_progress("done", "Pipeline complete", 1.0)

            score = self._extract_score(messages)
            midi_path = None
            if score:
                ts = int(time.time())
                midi_path = str(
                    settings.output_dir / f"{score.title}_{ts}.mid"
                )
                save_score_midi(score, midi_path)
                logger.info(f"MIDI exported: {midi_path}")

            completed = "FINALIZED" in (
                messages[-1]["content"] if messages else ""
            )

            return PipelineResult(
                messages=messages,
                total_messages=len(messages),
                completed=completed,
                midi_path=midi_path,
                score=score,
            )

        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            if self._on_progress:
                await self._on_progress("error", str(e), 0.0)
            return PipelineResult(messages=[], total_messages=0, error=str(e))

    async def run_stream(self, request: MusicRequest):
        """Stream messages from the pipeline as they are generated."""
        task_description = self._build_task(request)
        logger.info(f"Starting streaming pipeline for: {request.description[:80]}")

        async for msg in self.team.run_stream(task=task_description):
            if hasattr(msg, "source"):
                source = getattr(msg, "source", "?")
                preview = msg.to_text()[:150] if hasattr(msg, "to_text") else str(msg)[:150]
                logger.info(f"[stream] {source}: {preview}...")
            yield msg

    async def close(self) -> None:
        await self.synthesizer.close()

    def _build_task(self, request: MusicRequest) -> str:
        parts = [f"Create music based on this request:"]
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


    @staticmethod
    def _extract_score(messages: list[dict]) -> Score | None:
        """Reconstruct a Score from agent conversation messages.

        Parses orchestrator blueprint (metadata), composer edits (notes),
        and instrumentalist assignments (tracks/instruments) to build
        a complete Score suitable for MIDI export.
        """
        from src.music.score import ScoreNote, ScoreSection, ScoreTrack

        title, key, scale_type = "Untitled", "C", "major"
        tempo, time_sig = 120, [4, 4]
        blueprint_sections: list[dict] = []
        all_notes: dict[str, list[dict]] = {}
        track_instruments: dict[str, dict] = {}

        for msg in messages:
            text = msg.get("content", "")
            source = msg.get("source", "")
            json_blocks = _find_json_objects(text)

            if source == "orchestrator":
                for data in json_blocks:
                    title = data.get("title", title)
                    key = data.get("key", key)
                    scale_type = data.get("scale_type", scale_type)
                    tempo = data.get("tempo", tempo)
                    time_sig = data.get("time_signature", time_sig)
                    for sec in data.get("sections", []):
                        if isinstance(sec, dict) and "name" in sec:
                            blueprint_sections.append(sec)

            elif source == "composer":
                for data in json_blocks:
                    edits = data.get("edits", [])
                    if not isinstance(edits, list):
                        continue
                    for edit in edits:
                        if not isinstance(edit, dict):
                            continue
                        if edit.get("action", "add") not in ("add", "modify"):
                            continue
                        pitch = edit.get("pitch")
                        start = edit.get("start_beat")
                        dur = edit.get("duration_beats")
                        if pitch is None or start is None or dur is None:
                            continue
                        track_name = edit.get("track", "melody")
                        all_notes.setdefault(track_name, []).append({
                            "pitch": int(pitch),
                            "start_beat": float(start),
                            "duration_beats": float(dur),
                            "velocity": min(127, max(1, int(edit.get("velocity", 80)))),
                        })

            elif source == "instrumentalist":
                for data in json_blocks:
                    for trk in data.get("tracks", []):
                        if isinstance(trk, dict) and "instrument" in trk:
                            track_instruments[trk["instrument"]] = {
                                "instrument": trk.get("instrument", "Piano"),
                                "role": trk.get("role", "accompaniment"),
                                "channel": int(trk.get("midi_channel", 0)),
                                "program": int(trk.get("program_number", 0)),
                            }

        if not all_notes:
            logger.warning("No note data found in any composer message")
            return None

        beats_per_bar = time_sig[0] if time_sig else 4
        sections: list[ScoreSection] = []
        beat_offset = 0.0
        if blueprint_sections:
            for sd in blueprint_sections:
                bars = int(sd.get("bars", 4))
                sections.append(ScoreSection(
                    name=sd["name"], start_beat=beat_offset, bars=bars,
                ))
                beat_offset += bars * beats_per_bar
        else:
            max_beat = max(
                max(n["start_beat"] + n["duration_beats"] for n in ns)
                for ns in all_notes.values()
            )
            sections.append(ScoreSection(
                name="main", start_beat=0.0,
                bars=int(max_beat / beats_per_bar) + 1,
            ))

        tracks: list[ScoreTrack] = []
        inst_list = list(track_instruments.values())
        for idx, (track_name, notes) in enumerate(all_notes.items()):
            matched = None
            tn_lower = track_name.lower().replace("_", " ")
            for inst in inst_list:
                if (tn_lower in inst["instrument"].lower()
                        or inst["instrument"].lower() in tn_lower
                        or inst["role"].lower() in tn_lower):
                    matched = inst
                    break
            if matched is None and idx < len(inst_list):
                matched = inst_list[idx]

            score_notes = sorted(
                [ScoreNote(**n) for n in notes],
                key=lambda n: n.start_beat,
            )
            tracks.append(ScoreTrack(
                name=track_name,
                instrument=matched["instrument"] if matched else track_name,
                role=matched["role"] if matched else "melody",
                channel=matched["channel"] if matched else idx,
                program=matched["program"] if matched else 0,
                notes=score_notes,
            ))

        total_notes = sum(len(t.notes) for t in tracks)
        logger.info(
            f"Score reconstructed: '{title}', {len(tracks)} tracks, "
            f"{total_notes} notes, {len(sections)} sections"
        )
        return Score(
            title=title, key=key, scale_type=scale_type,
            tempo=tempo, time_signature=time_sig,
            sections=sections, tracks=tracks,
        )


class PipelineResult:
    def __init__(
        self,
        messages: list[dict],
        total_messages: int = 0,
        completed: bool = False,
        error: str | None = None,
        midi_path: str | None = None,
        score: Score | None = None,
    ):
        self.messages = messages
        self.total_messages = total_messages
        self.completed = completed
        self.error = error
        self.midi_path = midi_path
        self.score = score

    def summary(self) -> dict:
        return {
            "total_messages": self.total_messages,
            "completed": self.completed,
            "error": self.error,
            "midi_path": self.midi_path,
            "agents_involved": list({m["source"] for m in self.messages}),
        }

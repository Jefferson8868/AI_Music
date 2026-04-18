"""
SynthesizerAgent — bridges the Magenta music engine.
Calls Magenta API, parses MIDI output, returns Draft Score.
This agent does NOT use an LLM — it is a pure tool-calling agent.
"""

from __future__ import annotations

import json
from typing import Sequence

from autogen_agentchat.agents import BaseChatAgent
from autogen_agentchat.base import Response
from autogen_agentchat.messages import BaseChatMessage, TextMessage
from autogen_core import CancellationToken
from loguru import logger

from config.settings import settings
from src.engine.factory import create_engine
from src.engine.interface import GenerationRequest, GenerationResult
from src.music.score import Score, ScoreNote, ScoreTrack, ScoreSection


class SynthesizerAgent(BaseChatAgent):
    def __init__(
        self,
        name: str,
        description: str = (
            "Calls music engine(s) to generate draft scores from primer "
            "notes. When settings.reference_engines lists multiple engines "
            "(e.g. 'magenta,composers_assistant,mmt'), builds a MultiEngine "
            "with strategy='merge' so the Composer sees alternative drafts."
        ),
        reference_engines: str | None = None,
    ):
        super().__init__(name=name, description=description)
        spec = reference_engines or settings.reference_engines or settings.music_engine
        # Round 2 Phase A: merge strategy tags each note with its source
        # engine label so downstream code (pipeline → Composer prompt) can
        # surface alternative drafts as reference perspectives.
        self._engine = create_engine(spec, strategy="merge")
        self._engine_spec = spec
        self._failed = False
        self._fail_count = 0

    @property
    def produced_message_types(self) -> Sequence[type[BaseChatMessage]]:
        return [TextMessage]

    async def on_messages(self, messages: Sequence[BaseChatMessage], cancellation_token: CancellationToken) -> Response:
        params = self._extract_params(messages)
        primer = params.get("primer_notes", [60, 64, 67])
        temperature = params.get("temperature", 1.0)
        qpm = params.get("qpm", 120.0)
        num_steps = params.get("num_steps", 128)
        logger.info(
            f"[Synthesizer] called — primer={primer}, temp={temperature}, "
            f"qpm={qpm}, steps={num_steps}"
        )

        if self._failed:
            self._fail_count += 1
            logger.warning(
                f"[Synthesizer] engine previously failed ({self._fail_count} calls), "
                "skipping — agents should compose via LLM"
            )
            return Response(
                chat_message=TextMessage(
                    content=(
                        "[Synthesizer] Magenta engine is unavailable (crashed previously). "
                        "Agents should compose the score directly using LLM intelligence. "
                        "Do NOT select synthesizer again."
                    ),
                    source=self.name,
                )
            )

        logger.info("[Synthesizer] checking Magenta engine health...")
        is_available = await self._engine.health_check()
        if not is_available:
            self._failed = True
            logger.warning("[Synthesizer] Magenta engine NOT available")
            return Response(
                chat_message=TextMessage(
                    content="[Synthesizer] Magenta engine is not available. Proceeding without draft score.",
                    source=self.name,
                )
            )

        try:
            import time
            t0 = time.time()
            logger.info("[Synthesizer] generating melody via Magenta...")
            melody_result = await self._engine.generate_melody(GenerationRequest(
                primer_notes=primer, num_steps=num_steps,
                temperature=temperature, qpm=qpm,
            ))
            logger.info(f"[Synthesizer] melody done in {time.time()-t0:.1f}s — {len(melody_result.notes)} notes")

            t1 = time.time()
            logger.info("[Synthesizer] generating polyphony via Magenta...")
            poly_result = await self._engine.generate_polyphony(GenerationRequest(
                primer_notes=primer, num_steps=num_steps,
                temperature=max(0.8, temperature - 0.2), qpm=qpm,
            ))
            logger.info(f"[Synthesizer] polyphony done in {time.time()-t1:.1f}s — {len(poly_result.notes)} notes")

            score = self._build_draft_score(melody_result, poly_result, params)
            score_json = score.model_dump_json(indent=2)

            # Count per-engine contributions (MultiEngine merge tags each
            # note dict with a `source` key). Useful for both operators and
            # for the Composer prompt block.
            combined_notes = melody_result.notes + poly_result.notes
            per_engine = _count_per_engine_notes(combined_notes)
            per_engine_str = ", ".join(
                f"{label}={n}" for label, n in per_engine.items()
            ) or "single engine"

            # Round 2 Phase A: embed a machine-readable per-engine split
            # so the pipeline can hand the Composer alternative drafts
            # as `draft_perspectives`. Cap at 64 notes per engine to
            # keep the agent message well under 10KB.
            perspectives = split_notes_by_engine(combined_notes)
            perspectives_payload = {
                "draft_perspectives": {
                    label: [
                        {
                            "pitch": int(n.get("pitch", 60)),
                            "start_time": float(n.get("start_time", 0.0)),
                            "end_time": float(n.get("end_time", 0.0)),
                            "velocity": int(n.get("velocity", 80)),
                            "source": str(
                                n.get("source") or label,
                            ),
                        }
                        for n in notes[:64]
                    ]
                    for label, notes in perspectives.items()
                },
                "engine_spec": self._engine_spec,
                "qpm": float(params.get("qpm", 120.0)),
            }

            output = (
                f"[Synthesizer] Draft score generated via "
                f"{self._engine_spec} (per-engine notes: "
                f"{per_engine_str}).\n"
                f"Melody: {len(melody_result.notes)} notes, "
                f"Polyphony: {len(poly_result.notes)} notes\n\n"
                f"Score summary:\n{score.to_summary()}\n\n"
                f"```json\n{score_json}\n```\n\n"
                f"Reference-draft perspectives (per engine):\n"
                f"```json\n{json.dumps(perspectives_payload, indent=2)}\n```"
            )
            return Response(chat_message=TextMessage(content=output, source=self.name))

        except Exception as e:
            self._failed = True
            logger.error(f"Synthesizer error: {e}")
            return Response(
                chat_message=TextMessage(
                    content=(
                        f"[Synthesizer] Generation failed: {e}. "
                        "Agents should compose the score directly using LLM. "
                        "Do NOT select synthesizer again."
                    ),
                    source=self.name,
                )
            )

    async def on_reset(self, cancellation_token: CancellationToken) -> None:
        pass

    async def close(self) -> None:
        await self._engine.close()

    def _extract_params(self, messages: Sequence[BaseChatMessage]) -> dict:
        """Extract generation parameters from conversation history."""
        params: dict = {}
        for msg in reversed(messages):
            text = msg.to_text()
            try:
                start = text.index("{")
                end = text.rindex("}") + 1
                data = json.loads(text[start:end])
                if "primer_notes" in data:
                    params.update(data)
                    break
                if "tempo" in data:
                    params.setdefault("qpm", data["tempo"])
                if "primer_notes" in data:
                    params["primer_notes"] = data["primer_notes"]
                if "primer_temperature" in data:
                    params["temperature"] = data["primer_temperature"]
            except (ValueError, json.JSONDecodeError):
                continue
        return params

    def _build_draft_score(
        self, melody: GenerationResult, poly: GenerationResult, params: dict,
    ) -> Score:
        melody_notes = [
            ScoreNote(
                pitch=n["pitch"],
                start_beat=n["start_time"] * params.get("qpm", 120) / 60.0,
                duration_beats=(n["end_time"] - n["start_time"]) * params.get("qpm", 120) / 60.0,
                velocity=n.get("velocity", 80),
            )
            for n in melody.notes
        ]

        poly_notes = [
            ScoreNote(
                pitch=n["pitch"],
                start_beat=n["start_time"] * params.get("qpm", 120) / 60.0,
                duration_beats=(n["end_time"] - n["start_time"]) * params.get("qpm", 120) / 60.0,
                velocity=n.get("velocity", 70),
            )
            for n in poly.notes
        ]

        total_beats = max(
            (n.start_beat + n.duration_beats for n in melody_notes),
            default=32.0,
        )
        bars = int(total_beats / 4) or 8

        return Score(
            title=params.get("title", "Draft"),
            key=params.get("key", "C"),
            scale_type=params.get("scale_type", "major"),
            tempo=int(params.get("qpm", 120)),
            sections=[ScoreSection(name="full", start_beat=0, bars=bars)],
            tracks=[
                ScoreTrack(name="melody", instrument="piano", role="lead", channel=0, program=0, notes=melody_notes),
                ScoreTrack(name="harmony", instrument="piano", role="accompaniment", channel=1, program=0, notes=poly_notes),
            ],
        )


def _count_per_engine_notes(notes: list[dict]) -> dict[str, int]:
    """Count how many notes each engine contributed (by `source` tag)."""
    counts: dict[str, int] = {}
    for n in notes:
        label = str(n.get("source") or "unknown")
        counts[label] = counts.get(label, 0) + 1
    return counts


def split_notes_by_engine(notes: list[dict]) -> dict[str, list[dict]]:
    """Split a merged note list back into per-engine draft perspectives.

    Used by pipeline.py to build the `draft_perspectives` parameter for
    `build_composer_section_prompt()` — one compact summary line per
    engine, for the Composer to compare/contrast ideas without being
    told to copy any of them.
    """
    buckets: dict[str, list[dict]] = {}
    for n in notes:
        label = str(n.get("source") or "unknown")
        buckets.setdefault(label, []).append(n)
    return buckets

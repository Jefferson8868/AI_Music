"""
OrchestratorAgent — parses user requests and produces a Composition Blueprint.
"""

from __future__ import annotations

import json
from typing import Sequence

from autogen_agentchat.agents import BaseChatAgent
from autogen_agentchat.base import Response
from autogen_agentchat.messages import BaseChatMessage, TextMessage
from autogen_core import CancellationToken
from loguru import logger

from src.llm.prompts import ORCHESTRATOR_SYSTEM
from src.music.score import CompositionBlueprint


class OrchestratorAgent(BaseChatAgent):
    def __init__(self, name: str, model_client, description: str = "Analyzes user requests and creates composition plans"):
        super().__init__(name=name, description=description)
        self._model_client = model_client
        self._blueprint: CompositionBlueprint | None = None

    @property
    def produced_message_types(self) -> Sequence[type[BaseChatMessage]]:
        return [TextMessage]

    async def on_messages(self, messages: Sequence[BaseChatMessage], cancellation_token: CancellationToken) -> Response:
        last_msg = messages[-1] if messages else None
        user_text = last_msg.to_text() if last_msg else ""
        logger.info(f"[Orchestrator] called with {len(messages)} messages, input length={len(user_text)}")

        from autogen_core.models import SystemMessage, UserMessage
        llm_messages = [
            SystemMessage(content=ORCHESTRATOR_SYSTEM),
            UserMessage(content=user_text, source=self.name),
        ]

        import time
        t0 = time.time()
        logger.info("[Orchestrator] calling LLM...")
        result = await self._model_client.create(llm_messages, cancellation_token=cancellation_token)
        raw = result.content if isinstance(result.content, str) else str(result.content)
        logger.info(f"[Orchestrator] LLM responded in {time.time()-t0:.1f}s, {len(raw)} chars")

        blueprint = self._parse_blueprint(raw)
        self._blueprint = blueprint
        logger.info(f"[Orchestrator] Blueprint: title={blueprint.title}, key={blueprint.key}, tempo={blueprint.tempo}, sections={len(blueprint.sections)}")

        output_text = f"[Orchestrator] Blueprint created:\n```json\n{blueprint.model_dump_json(indent=2)}\n```"
        return Response(chat_message=TextMessage(content=output_text, source=self.name))

    async def on_reset(self, cancellation_token: CancellationToken) -> None:
        self._blueprint = None

    def _parse_blueprint(self, raw: str) -> CompositionBlueprint:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            data = json.loads(text[start:end])
            return CompositionBlueprint(**data)
        except Exception as e:
            logger.warning(f"Failed to parse blueprint: {e}")
            return CompositionBlueprint(title="Untitled", global_notes=raw[:200])

"""
CriticAgent — reviews Score quality, produces structured feedback.
"""

from __future__ import annotations

from typing import Sequence

from autogen_agentchat.agents import BaseChatAgent
from autogen_agentchat.base import Response
from autogen_agentchat.messages import BaseChatMessage, TextMessage
from autogen_core import CancellationToken
from loguru import logger

from src.llm.prompts import CRITIC_SYSTEM
from config.settings import settings


class CriticAgent(BaseChatAgent):
    def __init__(self, name: str, model_client, description: str = "Reviews score quality and provides structured feedback"):
        super().__init__(name=name, description=description)
        self._model_client = model_client
        self._consecutive_low_scores = 0

    @property
    def produced_message_types(self) -> Sequence[type[BaseChatMessage]]:
        return [TextMessage]

    async def on_messages(self, messages: Sequence[BaseChatMessage], cancellation_token: CancellationToken) -> Response:
        context = "\n\n".join(m.to_text() for m in messages[-5:])
        logger.info(f"[Critic] called with {len(messages)} messages, context={len(context)} chars")

        from autogen_core.models import SystemMessage, UserMessage
        llm_messages = [
            SystemMessage(content=CRITIC_SYSTEM),
            UserMessage(
                content=(
                    f"Review the following musical content. "
                    f"Consecutive low-score rounds so far: {self._consecutive_low_scores}.\n\n{context}"
                ),
                source=self.name,
            ),
        ]

        import time
        t0 = time.time()
        logger.info("[Critic] calling LLM...")
        result = await self._model_client.create(llm_messages, cancellation_token=cancellation_token)
        raw = result.content if isinstance(result.content, str) else str(result.content)
        logger.info(f"[Critic] LLM responded in {time.time()-t0:.1f}s, {len(raw)} chars")

        self._track_score(raw)

        return Response(chat_message=TextMessage(content=f"[Critic] {raw}", source=self.name))

    async def on_reset(self, cancellation_token: CancellationToken) -> None:
        self._consecutive_low_scores = 0

    def _track_score(self, raw: str) -> None:
        import json
        try:
            start = raw.index("{")
            end = raw.rindex("}") + 1
            data = json.loads(raw[start:end])
            score = float(data.get("overall_score", 0.5))
            passes = data.get("passes", False)
            regen = data.get("request_regeneration", False)
            logger.info(
                f"[Critic] score={score:.2f}, passes={passes}, "
                f"regen={regen}, consecutive_low={self._consecutive_low_scores}"
            )
            if score < settings.critic_regen_threshold:
                self._consecutive_low_scores += 1
            else:
                self._consecutive_low_scores = 0
        except Exception as e:
            logger.warning(f"[Critic] could not parse score from response: {e}")

"""
InstrumentalistAgent — handles orchestration, VST assignment, and articulation.
"""

from __future__ import annotations

from typing import Sequence

from autogen_agentchat.agents import BaseChatAgent
from autogen_agentchat.base import Response
from autogen_agentchat.messages import BaseChatMessage, TextMessage
from autogen_core import CancellationToken
from loguru import logger

from src.llm.prompts import INSTRUMENTALIST_SYSTEM


class InstrumentalistAgent(BaseChatAgent):
    def __init__(self, name: str, model_client, description: str = "Assigns instruments, VST plugins, and articulations"):
        super().__init__(name=name, description=description)
        self._model_client = model_client

    @property
    def produced_message_types(self) -> Sequence[type[BaseChatMessage]]:
        return [TextMessage]

    async def on_messages(self, messages: Sequence[BaseChatMessage], cancellation_token: CancellationToken) -> Response:
        recent = messages[-6:] if len(messages) > 6 else messages
        context = "\n\n".join(m.to_text() for m in recent)
        logger.info(f"[Instrumentalist] called with {len(messages)} messages, using last {len(recent)}, context={len(context)} chars")

        from autogen_core.models import SystemMessage, UserMessage
        llm_messages = [
            SystemMessage(content=INSTRUMENTALIST_SYSTEM),
            UserMessage(
                content=f"Based on the current score and conversation, configure instruments:\n\n{context}",
                source=self.name,
            ),
        ]

        import time
        t0 = time.time()
        logger.info("[Instrumentalist] calling LLM...")
        result = await self._model_client.create(llm_messages, cancellation_token=cancellation_token)
        raw = result.content if isinstance(result.content, str) else str(result.content)
        logger.info(f"[Instrumentalist] LLM responded in {time.time()-t0:.1f}s, {len(raw)} chars")

        return Response(chat_message=TextMessage(content=f"[Instrumentalist] {raw}", source=self.name))

    async def on_reset(self, cancellation_token: CancellationToken) -> None:
        pass

"""
ComposerAgent — designs harmony, edits notes at the score level.
"""

from __future__ import annotations

import json
from typing import Sequence

from autogen_agentchat.agents import BaseChatAgent
from autogen_agentchat.base import Response
from autogen_agentchat.messages import BaseChatMessage, TextMessage
from autogen_core import CancellationToken
from loguru import logger

from src.llm.prompts import COMPOSER_SYSTEM, COMPOSER_LEAD_SHEET_SYSTEM

_COMPOSER_MODE_PROMPTS = {
    "section": COMPOSER_SYSTEM,
    "lead_sheet": COMPOSER_LEAD_SHEET_SYSTEM,
    "instrument": COMPOSER_SYSTEM,
}


class ComposerAgent(BaseChatAgent):
    def __init__(self, name: str, model_client, description: str = "Designs harmony, melody, and edits notes in the score"):
        super().__init__(name=name, description=description)
        self._model_client = model_client
        self._mode = "section"

    def set_mode(self, mode: str) -> None:
        """Set composer mode: 'section', 'lead_sheet', or 'instrument'."""
        if mode not in _COMPOSER_MODE_PROMPTS:
            raise ValueError(f"Unknown composer mode: {mode}. Valid: {list(_COMPOSER_MODE_PROMPTS)}")
        self._mode = mode
        logger.info(f"[Composer] mode set to '{mode}'")

    @property
    def produced_message_types(self) -> Sequence[type[BaseChatMessage]]:
        return [TextMessage]

    async def on_messages(self, messages: Sequence[BaseChatMessage], cancellation_token: CancellationToken) -> Response:
        recent = messages[-8:] if len(messages) > 8 else messages
        context = "\n\n".join(m.to_text() for m in recent)
        logger.info(f"[Composer] called with {len(messages)} messages, using last {len(recent)}, context={len(context)} chars")

        from autogen_core.models import SystemMessage, UserMessage
        llm_messages = [
            SystemMessage(content=_COMPOSER_MODE_PROMPTS.get(self._mode, COMPOSER_SYSTEM)),
            UserMessage(
                content=f"Here is the conversation so far. Write concrete notes as JSON edits:\n\n{context}",
                source=self.name,
            ),
        ]

        import time
        t0 = time.time()
        logger.info("[Composer] calling LLM...")
        result = await self._model_client.create(llm_messages, cancellation_token=cancellation_token)
        raw = result.content if isinstance(result.content, str) else str(result.content)
        logger.info(f"[Composer] LLM responded in {time.time()-t0:.1f}s, {len(raw)} chars")

        output = f"[Composer] {raw}"
        return Response(chat_message=TextMessage(content=output, source=self.name))

    async def on_reset(self, cancellation_token: CancellationToken) -> None:
        pass

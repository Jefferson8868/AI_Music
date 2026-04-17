"""
NullEngine — explicit no-op engine for tests, CI, and graceful
degradation when an optional engine dependency is missing.

Returns empty `GenerationResult`s and always reports healthy=True. The
Synthesizer falls back to LLM-driven composition without the Magenta
draft when the active engine is a NullEngine.
"""

from __future__ import annotations

from src.engine.interface import (
    GenerationRequest,
    GenerationResult,
    MusicEngineInterface,
)


class NullEngine(MusicEngineInterface):
    """Always-empty engine; never raises, never calls out."""

    def __init__(self, reason: str = ""):
        self.reason = reason or "NullEngine active (no external engine)"

    async def generate_melody(
        self, request: GenerationRequest,
    ) -> GenerationResult:
        return GenerationResult(
            midi_path="", notes=[], duration_seconds=0.0,
        )

    async def generate_polyphony(
        self, request: GenerationRequest,
    ) -> GenerationResult:
        return GenerationResult(
            midi_path="", notes=[], duration_seconds=0.0,
        )

    async def health_check(self) -> bool:
        # The engine is "available" in the sense that it never fails —
        # but callers should usually check `isinstance(engine, NullEngine)`
        # to decide whether to skip the draft-generation step entirely.
        return True

    async def close(self) -> None:
        return None

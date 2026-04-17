"""
MultiEngine — fanout wrapper that runs multiple engines in parallel
and returns the first healthy result (or merges all results for
diversity — see strategy).

Use cases
---------
1. Primary + fallback: use MusicLang if healthy, else Magenta.
2. Diversity: generate candidates from 2-3 engines and pass all of
   them to the Composer as reference perspectives.

Strategy
--------
`strategy="first_healthy"`  — returns the first engine whose result
                              has non-empty notes.
`strategy="merge"`         — concatenates notes from all engines
                              (each engine's notes tagged by source
                              via a key in each note dict).
`strategy="primary"`        — always uses engines[0]; others are kept
                              for health/failover only.
"""

from __future__ import annotations

import asyncio
from typing import Iterable

from loguru import logger

from src.engine.interface import (
    GenerationRequest,
    GenerationResult,
    MusicEngineInterface,
)


class MultiEngine(MusicEngineInterface):
    """Aggregate over a list of engines."""

    def __init__(
        self,
        engines: Iterable[MusicEngineInterface],
        strategy: str = "first_healthy",
    ):
        self.engines: list[MusicEngineInterface] = list(engines)
        if not self.engines:
            raise ValueError("MultiEngine requires at least one engine")
        valid = {"first_healthy", "merge", "primary"}
        if strategy not in valid:
            raise ValueError(
                f"strategy must be one of {valid}; got {strategy!r}"
            )
        self.strategy = strategy

    async def _fanout(
        self,
        fn_name: str,
        request: GenerationRequest,
    ) -> list[tuple[str, GenerationResult]]:
        """Run the named method on every engine in parallel."""

        async def _call(idx: int, eng: MusicEngineInterface):
            label = type(eng).__name__
            try:
                fn = getattr(eng, fn_name)
                res = await fn(request)
                return (label, res)
            except Exception as exc:
                logger.warning(
                    f"[MultiEngine] {label}.{fn_name} failed: {exc}"
                )
                return (label, GenerationResult())

        tasks = [
            _call(i, e) for i, e in enumerate(self.engines)
        ]
        return list(await asyncio.gather(*tasks))

    def _pick(
        self, results: list[tuple[str, GenerationResult]],
    ) -> GenerationResult:
        if not results:
            return GenerationResult()
        if self.strategy == "primary":
            return results[0][1] if results[0][1].notes else GenerationResult()
        if self.strategy == "first_healthy":
            for _, r in results:
                if r.notes:
                    return r
            return GenerationResult()
        # merge
        merged: list[dict] = []
        for label, r in results:
            for n in r.notes:
                n2 = dict(n)
                n2.setdefault("source", label)
                merged.append(n2)
        duration = max(
            (r.duration_seconds for _, r in results),
            default=0.0,
        )
        primary_path = next(
            (r.midi_path for _, r in results if r.midi_path), "",
        )
        return GenerationResult(
            midi_path=primary_path,
            notes=merged,
            duration_seconds=float(duration),
        )

    async def generate_melody(
        self, request: GenerationRequest,
    ) -> GenerationResult:
        return self._pick(await self._fanout("generate_melody", request))

    async def generate_polyphony(
        self, request: GenerationRequest,
    ) -> GenerationResult:
        return self._pick(await self._fanout("generate_polyphony", request))

    async def health_check(self) -> bool:
        """Healthy if ANY underlying engine is healthy."""
        results = await asyncio.gather(
            *(e.health_check() for e in self.engines),
            return_exceptions=True,
        )
        return any(r is True for r in results)

    async def close(self) -> None:
        await asyncio.gather(
            *(e.close() for e in self.engines),
            return_exceptions=True,
        )

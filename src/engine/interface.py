"""
Abstract interface for music generation engines.
Allows swapping Magenta for other backends (MIDI-LLM, MusicLang, etc.)
without changing any Agent code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel, Field


class GenerationRequest(BaseModel):
    primer_notes: list[int] = Field(default_factory=lambda: [60, 64, 67])
    num_steps: int = 128
    temperature: float = 1.0
    qpm: float = 120.0


class GenerationResult(BaseModel):
    midi_path: str = ""
    notes: list[dict] = Field(default_factory=list)
    duration_seconds: float = 0.0


class MusicEngineInterface(ABC):
    @abstractmethod
    async def generate_melody(self, request: GenerationRequest) -> GenerationResult:
        ...

    @abstractmethod
    async def generate_polyphony(self, request: GenerationRequest) -> GenerationResult:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...

    @abstractmethod
    async def close(self) -> None:
        ...

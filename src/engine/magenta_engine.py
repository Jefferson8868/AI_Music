"""
Magenta engine client — calls the independent Magenta microservice via HTTP.
"""

from __future__ import annotations

import httpx
from loguru import logger

from src.engine.interface import MusicEngineInterface, GenerationRequest, GenerationResult
from config.settings import settings


class MagentaEngine(MusicEngineInterface):

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.magenta_url).rstrip("/")
        self._http = httpx.AsyncClient(timeout=60.0)

    async def generate_melody(self, request: GenerationRequest) -> GenerationResult:
        resp = await self._http.post(
            f"{self.base_url}/generate_melody",
            json=request.model_dump(),
        )
        resp.raise_for_status()
        return GenerationResult(**resp.json())

    async def generate_polyphony(self, request: GenerationRequest) -> GenerationResult:
        resp = await self._http.post(
            f"{self.base_url}/generate_polyphony",
            json=request.model_dump(),
        )
        resp.raise_for_status()
        return GenerationResult(**resp.json())

    async def health_check(self) -> bool:
        try:
            resp = await self._http.get(f"{self.base_url}/health")
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        await self._http.aclose()


def create_engine() -> MusicEngineInterface:
    engine_type = settings.music_engine
    if engine_type == "magenta":
        return MagentaEngine()
    else:
        logger.warning(f"Unknown engine '{engine_type}', falling back to Magenta")
        return MagentaEngine()

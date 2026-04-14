"""
API request/response schemas.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from src.music.models import MusicRequest


class GenerateRequest(BaseModel):
    request: MusicRequest
    llm_backend: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    output_filename: str | None = None


class GenerateResponse(BaseModel):
    status: str = "ok"
    summary: dict = Field(default_factory=dict)
    messages: list[dict] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class JobStatus(BaseModel):
    job_id: str
    status: str = "pending"
    progress: float = 0.0
    stage: str = ""
    message: str = ""
    result: GenerateResponse | None = None


class HealthResponse(BaseModel):
    status: str = "ok"
    llm_backend: str = ""
    llm_model: str = ""
    music_engine: str = ""
    music_engine_available: bool = False

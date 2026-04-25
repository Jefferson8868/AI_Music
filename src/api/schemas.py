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
    # Round 2 Phase A — per-engine availability so generate scripts can
    # probe the server before submitting a long-running job and surface
    # any silently-skipped reference engines to the user.
    reference_engines: str = ""
    reference_engine_status: dict[str, dict] = Field(default_factory=dict)
    # Round 2 Phase C/D/E/F status flags.
    humanize: bool = False
    render_audio: bool = False
    synthesize_vocals: bool = False
    apply_mix: bool = False

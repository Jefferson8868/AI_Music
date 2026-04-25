"""
FastAPI route handlers.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from loguru import logger

from src.api.schemas import GenerateRequest, GenerateResponse, JobStatus, HealthResponse
from src.agents.pipeline import MusicGenerationPipeline
from src.llm.client import create_llm_client
from src.engine.factory import create_engine, engine_status_report
from config.settings import settings

router = APIRouter()

_jobs: dict[str, JobStatus] = {}


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health probe with full Round 2 status surface.

    The legacy `music_engine_available` reflects only the primary engine
    (`settings.music_engine`). The new `reference_engine_status` mirrors
    the multi-engine fanout from `settings.reference_engines` so client
    scripts (e.g. `scripts/generate_chi_ling_explicit.py`) can see at a
    glance which reference engines actually loaded vs. silently fell
    back to NullEngine.
    """
    engine = create_engine(settings.music_engine)
    try:
        engine_ok = await engine.health_check()
    except Exception:
        engine_ok = False
    finally:
        try:
            await engine.close()
        except Exception:
            pass
    spec = settings.reference_engines or settings.music_engine
    ref_report = engine_status_report(spec)
    return HealthResponse(
        status="ok",
        llm_backend=settings.llm_backend,
        llm_model=settings.llm_model,
        music_engine=settings.music_engine,
        music_engine_available=engine_ok,
        reference_engines=spec,
        reference_engine_status=ref_report,
        humanize=settings.humanize,
        render_audio=settings.render_audio,
        synthesize_vocals=settings.synthesize_vocals,
        apply_mix=settings.apply_mix,
    )


@router.post("/generate", response_model=GenerateResponse)
async def generate_sync(body: GenerateRequest):
    pipeline = MusicGenerationPipeline(
        backend=body.llm_backend,
        model=body.llm_model,
        api_key=body.llm_api_key,
    )
    try:
        result = await pipeline.run(body.request)
        return GenerateResponse(
            status="completed" if result.completed else "partial",
            summary=result.summary(),
            messages=result.messages,
            errors=[result.error] if result.error else [],
        )
    except Exception as e:
        logger.error(f"Generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await pipeline.close()


@router.post("/generate/async", response_model=JobStatus)
async def generate_async(body: GenerateRequest):
    job_id = uuid.uuid4().hex[:8]
    _jobs[job_id] = JobStatus(
        job_id=job_id, status="pending", progress=0.0,
        stage="queued", message="Job queued.",
    )
    asyncio.create_task(_run_job(job_id, body))
    return _jobs[job_id]


@router.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return _jobs[job_id]


@router.get("/jobs", response_model=list[JobStatus])
async def list_jobs():
    return list(_jobs.values())


@router.get("/midi/{filename}")
async def download_midi(filename: str):
    """Download a generated MIDI file."""
    path = settings.output_dir / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="MIDI file not found")
    return FileResponse(
        path=str(path),
        media_type="audio/midi",
        filename=filename,
    )


@router.get("/midi")
async def list_midi_files():
    """List all generated MIDI files."""
    midi_dir = settings.output_dir
    files = sorted(midi_dir.glob("*.mid"), key=lambda f: f.stat().st_mtime, reverse=True)
    return [{"name": f.name, "size": f.stat().st_size, "url": f"/api/midi/{f.name}"} for f in files]


@router.websocket("/ws/generate")
async def websocket_generate(ws: WebSocket):
    await ws.accept()
    try:
        data = await ws.receive_json()
        from src.music.models import MusicRequest
        request = MusicRequest(**data.get("request", data))

        async def progress_cb(stage: str, message: str, progress: float):
            await ws.send_json({"type": "progress", "stage": stage, "message": message, "progress": progress})

        pipeline = MusicGenerationPipeline(on_progress=progress_cb)
        try:
            async for msg in pipeline.run_stream(request):
                text = msg.to_text() if hasattr(msg, "to_text") else str(msg)
                source = getattr(msg, "source", "system")
                await ws.send_json({"type": "message", "source": source, "content": text})
            await ws.send_json({"type": "done"})
        finally:
            await pipeline.close()

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


async def _run_job(job_id: str, body: GenerateRequest) -> None:
    job = _jobs[job_id]
    job.status = "running"

    async def on_progress(stage: str, message: str, progress: float):
        job.stage = stage
        job.message = message
        job.progress = progress

    pipeline = MusicGenerationPipeline(
        backend=body.llm_backend,
        model=body.llm_model,
        api_key=body.llm_api_key,
        on_progress=on_progress,
    )
    try:
        result = await pipeline.run(body.request)
        job.status = "completed" if result.completed else "partial"
        job.progress = 1.0
        job.result = GenerateResponse(
            status=job.status,
            summary=result.summary(),
            messages=result.messages,
            errors=[result.error] if result.error else [],
        )
    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        job.status = "failed"
        job.message = str(e)
    finally:
        await pipeline.close()

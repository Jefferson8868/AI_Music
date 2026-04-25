"""
Music Generator — FastAPI Application Entry Point
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from src.api.routes import router
from config.settings import settings


def _log_round2_status() -> None:
    """Print the active Round 2 configuration + per-engine availability.

    Runs once at FastAPI startup. Reports the *real* state, not just
    `settings.music_engine`, so users can immediately tell whether the
    multi-engine fanout, audio render, vocal synth, and mix bus are
    actually online — instead of having to read individual factory
    warnings scattered through the log.
    """
    logger.info(
        f"Music Generator v0.2.0 starting on "
        f"{settings.host}:{settings.port}"
    )
    logger.info(f"LLM: {settings.llm_backend} / {settings.llm_model}")
    logger.info(f"Output: {settings.output_dir}")

    # Round 2 Phase A — multi-engine reference fanout.
    spec = settings.reference_engines or settings.music_engine
    logger.info(f"Round 2 Phase A — reference engines: {spec!r}")
    try:
        from src.engine.factory import (
            engine_status_report,
            format_engine_status,
        )
        report = engine_status_report(spec)
        logger.info("Engine availability:\n" + format_engine_status(report))
        unavailable = [
            n for n, info in report.items() if not info.get("available")
        ]
        if unavailable:
            logger.warning(
                f"  ↳ {len(unavailable)} engine(s) fell back to "
                f"NullEngine: {', '.join(unavailable)}. They will "
                f"contribute 0 reference notes to the Composer prompt."
            )
            logger.warning(
                "  ↳ To fix: install the missing pip package "
                "(`pip install musiclang_predict`, `anticipation`) or "
                "clone the repo into one of: /content/ref_engines/, "
                "./ref_engines/, ~/ref_engines/. The factory auto-adds "
                "those locations to sys.path on startup."
            )
    except Exception as exc:
        logger.warning(f"Engine status report failed: {exc}")

    # Round 2 Phase D — audio render.
    sf_path = (
        settings.soundfont_path
        if settings.soundfont_path
        else "(bundled / GM fallback)"
    )
    logger.info(
        f"Round 2 Phase D — render_audio={settings.render_audio}, "
        f"sample_rate={settings.render_sample_rate}, soundfont={sf_path}"
    )

    # Round 2 Phase C — performance realism.
    logger.info(
        f"Round 2 Phase C — humanize={settings.humanize}, "
        f"seed={settings.humanize_seed}"
    )

    # Round 2 Phase E — vocals.
    logger.info(
        f"Round 2 Phase E — synthesize_vocals="
        f"{settings.synthesize_vocals}, "
        f"voicebank={settings.vocal_voicebank!r}, "
        f"openutau_cli={settings.openutau_cli!r}"
    )

    # Round 2 Phase F — mix bus.
    logger.info(f"Round 2 Phase F — apply_mix={settings.apply_mix}")

    # Magenta microservice (legacy single-engine path; still relevant
    # when 'magenta' is in the fanout list).
    logger.info(
        f"Legacy Magenta microservice URL: {settings.magenta_url}"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    _log_round2_status()
    yield
    # Shutdown — nothing to do; pipelines manage their own resources.


app = FastAPI(
    title="Music Generator — Multi-Agent System",
    description=(
        "An interactive music co-creation system powered by AutoGen multi-agent "
        "framework and Google Magenta. Generates editable MIDI tracks with "
        "support for both Western and Eastern instruments."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


def main():
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )


if __name__ == "__main__":
    main()

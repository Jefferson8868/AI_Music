"""
Music Generator — FastAPI Application Entry Point
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from src.api.routes import router
from config.settings import settings

app = FastAPI(
    title="Music Generator — Multi-Agent System",
    description=(
        "An interactive music co-creation system powered by AutoGen multi-agent "
        "framework and Google Magenta. Generates editable MIDI tracks with "
        "support for both Western and Eastern instruments."
    ),
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.on_event("startup")
async def startup():
    logger.info(f"Music Generator v0.2.0 starting on {settings.host}:{settings.port}")
    logger.info(f"LLM: {settings.llm_backend} / {settings.llm_model}")
    logger.info(f"Music Engine: {settings.music_engine} @ {settings.magenta_url}")
    logger.info(f"Output: {settings.output_dir}")


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

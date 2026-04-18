from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    project_root: Path = Path(__file__).parent.parent
    output_dir: Path = Field(default_factory=lambda: Path(__file__).parent.parent / "output")

    # LLM
    llm_backend: str = "ollama"  # ollama | openai | claude | deepseek | gemini
    llm_model: str = "qwen2.5:14b"
    llm_api_key: str = ""
    llm_base_url: str | None = None

    # Ollama
    ollama_base_url: str = "http://localhost:11434"

    # Music Engine
    music_engine: str = "magenta"  # magenta | musiclang | midi_llm
    magenta_url: str = "http://localhost:8001"

    # Round 2 Phase A: Multi-engine reference fanout.
    # Comma-separated list (or "multi:..." prefix). When more than one
    # engine is listed, Phase 1 builds a MultiEngine(strategy="merge")
    # so the Composer sees alternative drafts as reference perspectives.
    # Unavailable engines degrade to NullEngine silently.
    reference_engines: str = "magenta"

    # Music defaults
    default_tempo: int = 120
    default_time_signature: tuple[int, int] = (4, 4)
    default_key: str = "C"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Reaper DAW
    reaper_host: str = "localhost"
    reaper_port: int = 9090

    # Agent pipeline
    max_refinement_rounds: int = 5
    max_inspiration_resets: int = 3
    max_group_chat_messages: int = 15
    critic_pass_threshold: float = 0.8
    critic_regen_threshold: float = 0.5
    agent_timeout: float = 120.0
    quantization_grid: float = 0.25

    model_config = {
        "env_prefix": "MG_",
        "env_file": Path(__file__).parent.parent / ".env",
    }


settings = Settings()
settings.output_dir.mkdir(parents=True, exist_ok=True)
(settings.output_dir / "drafts").mkdir(parents=True, exist_ok=True)

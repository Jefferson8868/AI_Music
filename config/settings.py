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

    # Round 2 Phase C: MIDI humanizer (velocity jitter, micro-timing,
    # tempo breathing, round-robin detune). Set humanize=False for
    # bit-exact reproducible output; set humanize_seed=None for a
    # different seed every run.
    humanize: bool = True
    humanize_seed: int | None = 0

    # Round 2 Phase D: FluidSynth audio render.
    # render_audio=True → pipeline emits a .wav alongside .mid.
    # Silently no-ops when FluidSynth isn't installed.
    render_audio: bool = True
    soundfont_path: Path | None = None    # None → bundled combined.sf2
    render_sample_rate: int = 44100

    # Round 2 Phase E: DiffSinger / OpenUtau vocal synthesis.
    # synthesize_vocals=True → pipeline emits a {title}_vocal.wav when
    # lyrics + a melody track are both present. Silently no-ops when the
    # OpenUtau CLI or a voicebank isn't installed.
    synthesize_vocals: bool = True
    vocal_voicebank: str = "default"  # folder name or explicit path
    # OpenUtau CLI binary name (overridable for CI / non-PATH installs).
    openutau_cli: str = "OpenUtau"

    # Round 2 Phase F: pedalboard mix bus (per-section reverb, sidechain,
    # panning, transition stem placement). When False the pipeline leaves
    # the raw FluidSynth .wav alone.
    apply_mix: bool = True

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

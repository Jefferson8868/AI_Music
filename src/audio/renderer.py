"""
FluidSynth-backed MIDI → WAV renderer (Round 2 Phase D1).

Exposes one function:

    render_midi_to_wav(midi_path, out_path=None, soundfont=None,
                       sample_rate=44100) -> Path

It tries two backends in order:

  1. pyfluidsynth (Python binding) — preferred, no subprocess.
  2. The system `fluidsynth` CLI — fallback, works if the user
     installed FluidSynth via Homebrew/apt without the Python
     binding.

If neither is available, raises `RendererError`. Callers in the
pipeline catch that and continue without audio — the MIDI file
still lands on disk.

Soundfont resolution
--------------------
`soundfont` can be:
  * None  → look for settings.soundfont_path, else
            assets/soundfonts/combined.sf2.
  * str or Path → use that path if it exists.
The bundled SF2 asset isn't shipped with the repository (too large
for git). We log a clear warning when it's missing and fall back to
whatever the OS's default SoundFont is, if FluidSynth can find one.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from loguru import logger


# The default bundled SoundFont location. Populated on first run.
DEFAULT_SOUNDFONT = Path("assets/soundfonts/combined.sf2")


class RendererError(RuntimeError):
    """FluidSynth is unavailable or the render failed."""


def is_renderer_available() -> bool:
    """True when at least one backend (pyfluidsynth or CLI) is usable."""
    if _pyfluidsynth_available():
        return True
    if shutil.which("fluidsynth"):
        return True
    return False


def render_midi_to_wav(
    midi_path: str | Path,
    out_path: Optional[str | Path] = None,
    soundfont: Optional[str | Path] = None,
    sample_rate: int = 44100,
) -> Path:
    """Render `midi_path` to a WAV file.

    Args:
        midi_path: The input .mid file.
        out_path: Where to write the .wav. Defaults to midi_path with
            `.wav` suffix.
        soundfont: SF2 path. Defaults to settings.soundfont_path or
            the bundled asset.
        sample_rate: Render sample rate.

    Returns:
        Path to the written .wav (for chaining).

    Raises:
        RendererError: if no backend is available or the render fails.
        FileNotFoundError: if the input MIDI doesn't exist.
    """
    midi_path = Path(midi_path)
    if not midi_path.is_file():
        raise FileNotFoundError(f"MIDI input not found: {midi_path}")

    if out_path is None:
        out_path = midi_path.with_suffix(".wav")
    out_path = Path(out_path)

    sf_path = _resolve_soundfont(soundfont)
    logger.info(
        f"[renderer] {midi_path.name} → {out_path.name} "
        f"(sf={sf_path.name if sf_path else 'None'}, sr={sample_rate})"
    )

    # Try pyfluidsynth first.
    if _pyfluidsynth_available():
        try:
            _render_with_pyfluidsynth(
                midi_path, out_path, sf_path, sample_rate,
            )
            return out_path
        except Exception as exc:
            logger.warning(
                f"[renderer] pyfluidsynth failed ({exc}); "
                "falling back to fluidsynth CLI"
            )

    # Fall back to the CLI.
    if shutil.which("fluidsynth"):
        _render_with_cli(midi_path, out_path, sf_path, sample_rate)
        return out_path

    raise RendererError(
        "No FluidSynth backend available. Install pyfluidsynth "
        "(`pip install pyfluidsynth`) or the fluidsynth CLI "
        "(`brew install fluidsynth`)."
    )


# --------------------------------------------------------------------------
# Backend A — pyfluidsynth
# --------------------------------------------------------------------------

def _pyfluidsynth_available() -> bool:
    try:
        import fluidsynth   # noqa: F401
        return True
    except ImportError:
        return False


def _render_with_pyfluidsynth(
    midi_path: Path,
    out_path: Path,
    sf_path: Optional[Path],
    sample_rate: int,
) -> None:
    import fluidsynth

    # Prefer the high-level midi_to_audio if the installed binding
    # exposes it (newer pyfluidsynth versions).
    syn = fluidsynth.Synth(samplerate=float(sample_rate))
    # Some builds expose midi_to_audio directly; others require a
    # manual event-pump loop. Try the easy path first.
    if hasattr(syn, "midi_to_audio"):
        if sf_path is not None:
            syn.sfload(str(sf_path))
        syn.midi_to_audio(str(midi_path), str(out_path))
        syn.delete()
        return

    # Manual fallback using a temp .wav via the CLI-compatible path.
    raise RendererError(
        "Installed pyfluidsynth lacks Synth.midi_to_audio(); "
        "use the fluidsynth CLI instead."
    )


# --------------------------------------------------------------------------
# Backend B — fluidsynth CLI
# --------------------------------------------------------------------------

def _render_with_cli(
    midi_path: Path,
    out_path: Path,
    sf_path: Optional[Path],
    sample_rate: int,
) -> None:
    cmd: list[str] = [
        "fluidsynth",
        "-ni",                       # non-interactive
        "-F", str(out_path),         # output WAV
        "-r", str(sample_rate),
    ]
    if sf_path is not None:
        cmd.append(str(sf_path))
    cmd.append(str(midi_path))

    env = os.environ.copy()
    try:
        logger.debug(f"[renderer] running: {' '.join(cmd)}")
        result = subprocess.run(
            cmd, env=env,
            capture_output=True, text=True, timeout=300,
        )
    except subprocess.TimeoutExpired as exc:
        raise RendererError("fluidsynth CLI timed out (>5 min)") from exc

    if result.returncode != 0:
        raise RendererError(
            f"fluidsynth CLI exited {result.returncode}: "
            f"{result.stderr.strip()[:400]}"
        )
    if not out_path.is_file() or out_path.stat().st_size == 0:
        raise RendererError(
            f"fluidsynth produced no output at {out_path}"
        )


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _resolve_soundfont(
    soundfont: Optional[str | Path],
) -> Optional[Path]:
    if soundfont is not None:
        p = Path(soundfont)
        if p.is_file():
            return p
        logger.warning(
            f"[renderer] soundfont '{p}' not found; "
            "continuing with fluidsynth default"
        )
        return None

    # Fall back to settings.soundfont_path if configured.
    try:
        from config.settings import settings
        p_setting = getattr(settings, "soundfont_path", None)
        if p_setting:
            p = Path(p_setting)
            if p.is_file():
                return p
    except Exception:
        pass

    if DEFAULT_SOUNDFONT.is_file():
        return DEFAULT_SOUNDFONT.resolve()

    logger.warning(
        f"[renderer] no soundfont at {DEFAULT_SOUNDFONT} or in "
        "settings; fluidsynth will use its built-in default"
    )
    return None

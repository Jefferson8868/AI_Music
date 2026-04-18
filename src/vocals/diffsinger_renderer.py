"""
DiffSinger / OpenUtau vocal renderer (Round 2 Phase E3).

Takes a list of `VocalPhoneme` and writes a rendered vocal `.wav` stem.

Two backends, tried in order (mirrors the FluidSynth renderer's design):

  1. **OpenUtau CLI** — `openutau --project X.ustx --export Y.wav` (or
     the older `OpenUtau.Cli` invocation). OpenUtau has a DiffSinger
     bridge that loads diffsinger_* phonemizers + voicebanks without
     the user having to install Python torch deps.
  2. **Nothing.** If the CLI isn't on PATH, we raise `VocalSynthError`.

We intentionally avoid hard-depending on the `diffsinger` Python package
(torch + onnxruntime + specific Python version = install pain). OpenUtau
bundles everything into one binary.

When the caller lacks OpenUtau, the pipeline catches `VocalSynthError`
and proceeds without a vocal stem. Users can install OpenUtau later and
re-run without any code change.

UST export format
-----------------
We write a UST v1.20 project — OpenUtau accepts it alongside its newer
`.ustx`. Format is simple: `[#SETTING]`, `[#0000]`, `[#0001]`, ... Each
note block carries `Length`, `Lyric`, `NoteNum`, `PreUtterance`,
`VoiceOverlap`. Lengths are in ticks at 480ppqn.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, Optional

from loguru import logger

from src.vocals.phonemizer import VocalPhoneme


TICKS_PER_BEAT = 480


class VocalSynthError(RuntimeError):
    """Raised when no vocal-synthesis backend is available."""


# --------------------------------------------------------------------------
# Availability probe
# --------------------------------------------------------------------------

def is_vocal_synth_available(cli_name: str = "OpenUtau") -> bool:
    """True when an OpenUtau-compatible CLI is on PATH."""
    if shutil.which(cli_name):
        return True
    # Common alternative binary names.
    for alt in ("openutau", "OpenUtau.Cli", "OpenUtau-cli"):
        if shutil.which(alt):
            return True
    return False


def _resolve_cli() -> Optional[str]:
    """Pick the first available OpenUtau binary on PATH."""
    try:
        from config.settings import settings
        preferred = getattr(settings, "openutau_cli", "OpenUtau")
    except Exception:
        preferred = "OpenUtau"

    candidates = [preferred, "openutau", "OpenUtau", "OpenUtau.Cli", "OpenUtau-cli"]
    seen: set[str] = set()
    for name in candidates:
        if name in seen:
            continue
        seen.add(name)
        path = shutil.which(name)
        if path:
            return path
    return None


# --------------------------------------------------------------------------
# UST writer
# --------------------------------------------------------------------------

def _beats_to_ticks(beats: float) -> int:
    # UST expects integer ticks; clamp at 30 (≈ 1/16 at 120bpm min) so
    # zero-length notes still sound.
    ticks = int(round(beats * TICKS_PER_BEAT))
    return max(ticks, 30)


def _phoneme_to_ust_lyric(ph: VocalPhoneme) -> str:
    """OpenUtau UST lyric field.

    For Mandarin we emit "<pinyin><tone>" (e.g. "zhong1") — OpenUtau's
    Chinese CVVC phonemizer maps that to the voicebank. For Latin words
    we emit the word as-is; most voicebanks won't have a match and will
    fall back to rest-padding, but the timing is still correct.
    """
    phoneme = (ph.phoneme or "").strip().lower()
    if not phoneme:
        return "R"   # rest
    if ph.tone in (1, 2, 3, 4):
        return f"{phoneme}{ph.tone}"
    return phoneme


def write_ust_file(
    phonemes: Iterable[VocalPhoneme],
    out_path: Path,
    tempo_bpm: float = 120.0,
    project_name: str = "vocal",
) -> Path:
    """Write a UST v1.20 file OpenUtau can open.

    Returns `out_path`. Always writes SOMETHING (even with 0 phonemes),
    so callers can consistently report what was produced.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    phonemes = list(phonemes)

    lines = [
        "[#SETTING]",
        f"Tempo={tempo_bpm:.2f}",
        "Tracks=1",
        f"ProjectName={project_name}",
        "Mode2=True",
    ]

    # Insert leading rest so the first lyric aligns to its own start_beat.
    cursor_beat = 0.0
    idx = 0

    def _rest_block(index: int, length_ticks: int) -> list[str]:
        return [
            f"[#{index:04d}]",
            f"Length={length_ticks}",
            "Lyric=R",
            "NoteNum=60",
            "PreUtterance=",
        ]

    def _note_block(index: int, ph: VocalPhoneme) -> list[str]:
        return [
            f"[#{index:04d}]",
            f"Length={_beats_to_ticks(ph.duration_beat)}",
            f"Lyric={_phoneme_to_ust_lyric(ph)}",
            f"NoteNum={max(0, min(127, int(ph.pitch_midi)))}",
            "PreUtterance=",
            "VoiceOverlap=",
        ]

    for ph in phonemes:
        if ph.start_beat > cursor_beat + 1e-3:
            gap_ticks = _beats_to_ticks(ph.start_beat - cursor_beat)
            lines.extend(_rest_block(idx, gap_ticks))
            idx += 1
        lines.extend(_note_block(idx, ph))
        idx += 1
        cursor_beat = ph.start_beat + ph.duration_beat

    lines.append("[#TRACKEND]")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    logger.debug(f"[vocals] wrote {idx} UST blocks → {out_path}")
    return out_path


# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------

def render_vocal_stem(
    phonemes: list[VocalPhoneme],
    voicebank: str | Path = "default",
    out_path: Optional[str | Path] = None,
    tempo_bpm: float = 120.0,
    project_name: str = "vocal",
) -> Path:
    """Render a phoneme list to a .wav via OpenUtau CLI.

    Args:
        phonemes: Output of `lyrics_to_phonemes(...)`. Empty list raises.
        voicebank: Name (looked up in `~/.openutau/singers/`) or explicit
            path to a voicebank folder. OpenUtau resolves it.
        out_path: Target .wav path. Defaults to `./vocal.wav`.
        tempo_bpm: Used in the UST header so OpenUtau renders at the
            right tempo.
        project_name: Goes into UST `ProjectName=` header.

    Returns:
        Path to the written .wav.

    Raises:
        VocalSynthError: No CLI on PATH, CLI call failed, or output empty.
    """
    if not phonemes:
        raise VocalSynthError(
            "render_vocal_stem called with empty phoneme list"
        )

    cli = _resolve_cli()
    if cli is None:
        raise VocalSynthError(
            "No OpenUtau CLI on PATH. Install from "
            "https://www.openutau.com/ and ensure `OpenUtau` (or "
            "`openutau`) is runnable."
        )

    out_path = Path(out_path) if out_path else Path("vocal.wav")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ust_path = out_path.with_suffix(".ust")
    write_ust_file(
        phonemes,
        out_path=ust_path,
        tempo_bpm=tempo_bpm,
        project_name=project_name,
    )

    # OpenUtau CLI flags vary by version; the common shape is:
    #   OpenUtau --project X.ust --singer Y --export Z.wav
    cmd = [
        cli,
        "--project", str(ust_path),
        "--singer", str(voicebank),
        "--export", str(out_path),
    ]

    logger.info(
        f"[vocals] rendering {len(phonemes)} phonemes → {out_path.name} "
        f"(singer={voicebank})"
    )
    try:
        result = subprocess.run(
            cmd,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=600,
        )
    except FileNotFoundError as exc:
        raise VocalSynthError(
            f"Failed to spawn OpenUtau CLI at '{cli}': {exc}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise VocalSynthError(
            "OpenUtau CLI timed out (>10 min)"
        ) from exc

    if result.returncode != 0:
        raise VocalSynthError(
            f"OpenUtau CLI exited {result.returncode}: "
            f"{result.stderr.strip()[:500]}"
        )
    if not out_path.is_file() or out_path.stat().st_size == 0:
        raise VocalSynthError(
            f"OpenUtau produced no output at {out_path}"
        )

    return out_path


__all__ = [
    "VocalSynthError",
    "is_vocal_synth_available",
    "render_vocal_stem",
    "write_ust_file",
]

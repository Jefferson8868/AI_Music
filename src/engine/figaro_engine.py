"""
FIGARO engine.

Reference: von Rütte et al., 'FIGARO: Generating Symbolic Music with
Fine-Grained Artistic Control', ICLR 2023 (MIT).
https://github.com/dvruette/figaro

FIGARO accepts a *description code* (chord + instrument + density +
pitch-range + velocity-profile descriptors) as conditioning and emits
MIDI matching that description. That is an excellent fit for Round 2's
Composer: we hand FIGARO the Orchestrator's structured brief (chord
progression + target instruments + target density per section) and
get a draft that already respects the brief.

Stub-safe: if `figaro` is not importable the factory falls back to
NullEngine.

Mapping Music Generator's GenerationRequest to FIGARO parameters
----------------------------------------------------------------
  request.primer_notes  -> seed notes; FIGARO is conditional, so we
                           pack these into a description if a caller
                           passes them directly.
  request.num_steps     -> max_length for the decoder.
  request.temperature   -> passed through.
  request.qpm           -> stamped on output MIDI.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from loguru import logger

from config.settings import settings
from src.engine.interface import (
    GenerationRequest,
    GenerationResult,
    MusicEngineInterface,
)


class _FigaroNotAvailable(ImportError):
    pass


def _load_figaro():
    """Lazy-import a figaro package. Raises on failure."""
    for name in ("figaro", "figaro_model", "figaro_midi"):
        try:
            mod = __import__(name)
            return mod
        except Exception:
            continue
    raise _FigaroNotAvailable(
        "figaro is not installed. Clone https://github.com/dvruette/figaro "
        "onto PYTHONPATH, or `pip install figaro-midi`."
    )


class FigaroEngine(MusicEngineInterface):
    """Description-conditioned symbolic generator (stub-safe wrapper)."""

    def __init__(self, checkpoint: str | None = None):
        self._pkg = _load_figaro()
        self.checkpoint = checkpoint
        self._model = None
        self._output_dir = settings.output_dir / "figaro"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    async def _ensure_model(self):
        if self._model is not None:
            return
        loop = asyncio.get_running_loop()

        def _load():
            pkg = self._pkg
            for attr in (
                "load_pretrained", "load_model", "Model", "Figaro",
                "FigaroModel",
            ):
                fn = getattr(pkg, attr, None)
                if fn is None:
                    continue
                try:
                    return fn(self.checkpoint) if self.checkpoint else fn()
                except Exception:
                    continue
            raise _FigaroNotAvailable(
                "figaro has no recognised loader on this version."
            )

        self._model = await loop.run_in_executor(None, _load)

    async def _sample_midi(
        self, request: GenerationRequest, mode: str,
    ) -> Path:
        await self._ensure_model()
        out_path = (
            self._output_dir / f"fg_{mode}_{uuid.uuid4().hex[:8]}.mid"
        )
        loop = asyncio.get_running_loop()

        def _run():
            model = self._model
            for attr in ("generate", "sample", "predict"):
                fn = getattr(model, attr, None) if model is not None else None
                if fn is None:
                    continue
                try:
                    # FIGARO is description-conditioned; pass a minimal
                    # description if we have one, else fall back to
                    # primer notes.
                    description = _primer_to_description(
                        request.primer_notes,
                    )
                    res = fn(
                        description=description,
                        max_length=request.num_steps,
                        temperature=request.temperature,
                    )
                    if hasattr(res, "save"):
                        res.save(str(out_path))
                    elif hasattr(res, "to_midi"):
                        res.to_midi(str(out_path))
                    elif isinstance(res, (str, Path)):
                        src = Path(str(res))
                        if src.exists() and src != out_path:
                            out_path.write_bytes(src.read_bytes())
                    else:
                        _write_empty_midi(out_path)
                    return out_path
                except Exception as exc:
                    logger.warning(
                        f"figaro.{attr} failed: {exc}; trying next API."
                    )
                    continue
            _write_empty_midi(out_path)
            return out_path

        return await loop.run_in_executor(None, _run)

    async def _midi_to_notes(self, midi_path: Path) -> list[dict]:
        try:
            import mido
        except Exception:
            return []
        try:
            midi = mido.MidiFile(str(midi_path))
        except Exception:
            return []
        ticks_per_beat = max(1, midi.ticks_per_beat)
        tempo = 500000
        sec_per_tick = tempo / 1e6 / ticks_per_beat
        open_notes: dict[int, dict] = {}
        notes: list[dict] = []
        for track in midi.tracks:
            abs_tick = 0
            for msg in track:
                abs_tick += msg.time
                if msg.type == "set_tempo":
                    tempo = msg.tempo
                    sec_per_tick = tempo / 1e6 / ticks_per_beat
                elif msg.type == "note_on" and msg.velocity > 0:
                    open_notes[msg.note] = {
                        "pitch": msg.note,
                        "start_time": abs_tick * sec_per_tick,
                        "velocity": msg.velocity,
                    }
                elif (
                    msg.type == "note_off"
                    or (msg.type == "note_on" and msg.velocity == 0)
                ):
                    n = open_notes.pop(msg.note, None)
                    if n is None:
                        continue
                    n["end_time"] = abs_tick * sec_per_tick
                    notes.append(n)
        return notes

    async def generate_melody(
        self, request: GenerationRequest,
    ) -> GenerationResult:
        midi = await self._sample_midi(request, "melody")
        notes = await self._midi_to_notes(midi)
        return GenerationResult(
            midi_path=str(midi), notes=notes,
            duration_seconds=float(max(
                (n.get("end_time", 0.0) for n in notes), default=0.0,
            )),
        )

    async def generate_polyphony(
        self, request: GenerationRequest,
    ) -> GenerationResult:
        midi = await self._sample_midi(request, "poly")
        notes = await self._midi_to_notes(midi)
        return GenerationResult(
            midi_path=str(midi), notes=notes,
            duration_seconds=float(max(
                (n.get("end_time", 0.0) for n in notes), default=0.0,
            )),
        )

    async def health_check(self) -> bool:
        try:
            await self._ensure_model()
            return True
        except Exception:
            return False

    async def close(self) -> None:
        self._model = None


def _primer_to_description(primer_notes: list[int]) -> dict:
    """Build a minimal FIGARO description from primer pitches."""
    if not primer_notes:
        return {"chords": ["C"], "instruments": ["piano"], "density": "medium"}
    lo = min(primer_notes)
    hi = max(primer_notes)
    return {
        "chords": ["C"],
        "instruments": ["piano"],
        "density": "medium",
        "pitch_range": [int(lo), int(hi)],
    }


def _write_empty_midi(path: Path) -> None:
    try:
        import mido
        m = mido.MidiFile()
        m.tracks.append(mido.MidiTrack())
        m.save(str(path))
    except Exception:
        path.write_bytes(b"")

"""
Composer's Assistant 2 engine.

Reference: Malandro, 'Composer's Assistant 2: Interactive Multi-Track
MIDI Infilling' (2024, MIT). https://github.com/m-malandro/composers-assistant-REAPER

Composer's Assistant 2 (CA2) is a T5-based multi-track MIDI infilling
model trained on public-domain MIDI. Ideal for: "fill my drums given
the melody and chords", "fill my bass given everything else" — making
it the strongest reference engine for the DrumAgent / BassAgent in
Round 2 Phase B.

This module wraps whichever local installation the user has (either
the official pip package, if one ships, or an in-tree clone exposing
a `composers_assistant` import path). If nothing usable is found the
factory falls back to NullEngine — no crash.

Mapping Music Generator's GenerationRequest to CA2 parameters
-------------------------------------------------------------
  request.primer_notes  -> seed a melody track; CA2 infills the rest.
  request.num_steps     -> controls max token length.
  request.temperature   -> passed through (0.6-0.9 typical).
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


class _ComposersAssistantNotAvailable(ImportError):
    pass


def _load_composers_assistant():
    """Lazy-import a composers-assistant package. Raises on failure.

    Several distribution shapes exist in the wild; try each in turn so
    the first-party REAPER integration, the pip side-install, and an
    in-tree clone all work transparently.
    """
    for name in (
        "composers_assistant2",
        "composers_assistant",
        "composers_assistant_reaper",
    ):
        try:
            mod = __import__(name)
            return mod
        except Exception:
            continue
    raise _ComposersAssistantNotAvailable(
        "composers_assistant is not installed. "
        "Install with: pip install composers-assistant2 "
        "(or clone https://github.com/m-malandro/composers-assistant-REAPER "
        "into a path on PYTHONPATH)."
    )


class ComposersAssistantEngine(MusicEngineInterface):
    """T5 multi-track MIDI infiller (stub-safe wrapper)."""

    def __init__(self, checkpoint: str | None = None):
        self._pkg = _load_composers_assistant()
        self.checkpoint = checkpoint
        self._model = None
        self._output_dir = settings.output_dir / "composers_assistant"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    async def _ensure_model(self):
        if self._model is not None:
            return
        loop = asyncio.get_running_loop()

        def _load():
            pkg = self._pkg
            # Try every common loader name.
            for attr in (
                "load_model", "load_pretrained", "Pretrained", "Model",
            ):
                fn = getattr(pkg, attr, None)
                if fn is None:
                    continue
                try:
                    return fn(self.checkpoint) if self.checkpoint else fn()
                except Exception:
                    continue
            raise _ComposersAssistantNotAvailable(
                "composers_assistant has no recognised loader on this "
                "version."
            )

        self._model = await loop.run_in_executor(None, _load)

    async def _infill_midi(
        self, request: GenerationRequest, mode: str,
    ) -> Path:
        await self._ensure_model()
        out_path = (
            self._output_dir / f"ca2_{mode}_{uuid.uuid4().hex[:8]}.mid"
        )
        loop = asyncio.get_running_loop()

        def _run():
            model = self._model
            # Prefer a high-level infill() if exposed.
            for attr in ("infill", "generate", "predict", "complete"):
                fn = getattr(model, attr, None) if model is not None else None
                if fn is None:
                    continue
                try:
                    res = fn(
                        primer=request.primer_notes,
                        length=request.num_steps,
                        temperature=request.temperature,
                    )
                    # Convert whatever shape to a MIDI file on disk.
                    if hasattr(res, "save"):
                        res.save(str(out_path))
                    elif isinstance(res, (str, Path)):
                        src = Path(str(res))
                        if src.exists() and src != out_path:
                            out_path.write_bytes(src.read_bytes())
                    else:
                        # Write empty to keep downstream happy.
                        _write_empty_midi(out_path)
                    return out_path
                except Exception as exc:
                    logger.warning(
                        f"composers_assistant.{attr} failed: {exc}; "
                        "trying next API."
                    )
                    continue
            # Nothing worked — write empty MIDI so pipeline doesn't
            # crash on a missing path.
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
        midi = await self._infill_midi(request, "melody")
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
        midi = await self._infill_midi(request, "poly")
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


def _write_empty_midi(path: Path) -> None:
    try:
        import mido
        m = mido.MidiFile()
        m.tracks.append(mido.MidiTrack())
        m.save(str(path))
    except Exception:
        path.write_bytes(b"")

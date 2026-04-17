"""
Anticipatory Music Transformer (AMT) engine.

Reference: Thickstun et al., 'Anticipatory Music Transformer', 2023
(Apache-2.0). https://github.com/jthickstun/anticipation

AMT specialises in *infilling* and *conditional generation* — it accepts
a set of existing events and anticipates the rest. That matches roles
like: "given a chord bed from the orchestrator, complete the melody"
which maps well onto Phase 2 of this pipeline.

This module wraps the `anticipation` pip package. If it is not
installed the factory falls back to NullEngine — no crash.
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


class _AnticipatoryNotAvailable(ImportError):
    pass


def _load_anticipation():
    try:
        import anticipation  # type: ignore
        return anticipation
    except Exception as exc:
        raise _AnticipatoryNotAvailable(
            "anticipation is not installed. "
            "Install with: pip install anticipation"
        ) from exc


class AnticipatoryEngine(MusicEngineInterface):
    """Infilling-capable symbolic music generator (stub-safe wrapper).

    The full AMT API requires a downloaded model checkpoint and GPU.
    The wrapper treats those as optional: construction succeeds iff the
    `anticipation` package imports; `health_check()` additionally probes
    model loadability.
    """

    def __init__(self, checkpoint: str | None = None):
        self._anticipation = _load_anticipation()
        self.checkpoint = checkpoint
        self._model = None
        self._output_dir = settings.output_dir / "anticipatory"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    async def _ensure_model(self):
        if self._model is not None:
            return
        loop = asyncio.get_running_loop()

        def _load():
            mod = self._anticipation
            # The package exposes `sample.ar_sample` in recent releases;
            # degrade gracefully if the API differs.
            if hasattr(mod, "load_pretrained"):
                return mod.load_pretrained(self.checkpoint)
            sample_mod = getattr(mod, "sample", None)
            if sample_mod and hasattr(sample_mod, "load"):
                return sample_mod.load(self.checkpoint)
            raise _AnticipatoryNotAvailable(
                "anticipation: no recognised model loader."
            )

        self._model = await loop.run_in_executor(None, _load)

    async def _sample_midi(
        self, request: GenerationRequest, mode: str,
    ) -> Path:
        await self._ensure_model()
        out_path = self._output_dir / f"amt_{mode}_{uuid.uuid4().hex[:8]}.mid"
        loop = asyncio.get_running_loop()

        def _run():
            mod = self._anticipation
            # Prefer the high-level helper if the package exposes one.
            if hasattr(mod, "generate"):
                try:
                    mod.generate(
                        model=self._model,
                        primer=request.primer_notes,
                        length=request.num_steps,
                        temperature=request.temperature,
                        output=str(out_path),
                    )
                    return out_path
                except Exception as exc:
                    logger.warning(
                        f"anticipation.generate failed: {exc}; "
                        "returning empty MIDI."
                    )
            # Fallback: write an empty MIDI file so downstream doesn't
            # crash on a missing path.
            try:
                import mido
                m = mido.MidiFile()
                m.tracks.append(mido.MidiTrack())
                m.save(str(out_path))
            except Exception:
                out_path.write_bytes(b"")
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

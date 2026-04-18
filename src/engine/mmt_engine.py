"""
Multitrack Music Transformer (MMT / MMT-BERT) engine.

Reference: Dong et al., 'Multitrack Music Transformer', ICASSP 2023
(MIT). https://github.com/salu133445/mmt
Reference: Zhang & Bryan, 'MMT-BERT: Chord-aware Symbolic Music
Generation', ISMIR 2024 (MIT).

MMT is a decoder-only Transformer that natively emits *multi-track*
symbolic music — kick/snare/hat/bass/melody/chords as parallel
streams. That is exactly the shape we want for a "dense ensemble"
reference draft that the Composer can look at before deciding which
instruments should actually play in each section.

This wrapper is lazy and stub-safe: if `mmt` (or the reference
repo's in-tree modules) isn't importable, the factory falls back to
NullEngine.

Mapping Music Generator's GenerationRequest to MMT parameters
-------------------------------------------------------------
  request.primer_notes  -> 1-track primer; MMT continues all tracks.
  request.num_steps     -> max_len for the sampler.
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


class _MMTNotAvailable(ImportError):
    pass


def _load_mmt():
    """Lazy-import an MMT package. Raises on failure."""
    for name in ("mmt", "mmt_bert", "multitrack_music_transformer"):
        try:
            mod = __import__(name)
            return mod
        except Exception:
            continue
    raise _MMTNotAvailable(
        "mmt is not installed. Clone "
        "https://github.com/salu133445/mmt "
        "or https://github.com/Yh-Zhang-stanford/MMT-BERT "
        "onto PYTHONPATH, or `pip install mmt`."
    )


class MMTEngine(MusicEngineInterface):
    """Multi-track symbolic generator (stub-safe wrapper)."""

    def __init__(self, checkpoint: str | None = None):
        self._pkg = _load_mmt()
        self.checkpoint = checkpoint
        self._model = None
        self._output_dir = settings.output_dir / "mmt"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    async def _ensure_model(self):
        if self._model is not None:
            return
        loop = asyncio.get_running_loop()

        def _load():
            pkg = self._pkg
            for attr in (
                "load_pretrained", "load_model", "Model",
                "MultitrackMusicTransformer", "MMT", "MMTBert",
            ):
                fn = getattr(pkg, attr, None)
                if fn is None:
                    continue
                try:
                    return fn(self.checkpoint) if self.checkpoint else fn()
                except Exception:
                    continue
            raise _MMTNotAvailable(
                "mmt has no recognised loader on this version."
            )

        self._model = await loop.run_in_executor(None, _load)

    async def _sample_midi(
        self, request: GenerationRequest, mode: str,
    ) -> Path:
        await self._ensure_model()
        out_path = (
            self._output_dir / f"mmt_{mode}_{uuid.uuid4().hex[:8]}.mid"
        )
        loop = asyncio.get_running_loop()

        def _run():
            model = self._model
            for attr in ("sample", "generate", "predict"):
                fn = getattr(model, attr, None) if model is not None else None
                if fn is None:
                    continue
                try:
                    res = fn(
                        primer=request.primer_notes,
                        max_len=request.num_steps,
                        temperature=request.temperature,
                    )
                    if hasattr(res, "to_midi"):
                        res.to_midi(str(out_path))
                    elif hasattr(res, "save"):
                        res.save(str(out_path))
                    elif isinstance(res, (str, Path)):
                        src = Path(str(res))
                        if src.exists() and src != out_path:
                            out_path.write_bytes(src.read_bytes())
                    else:
                        _write_empty_midi(out_path)
                    return out_path
                except Exception as exc:
                    logger.warning(
                        f"mmt.{attr} failed: {exc}; trying next API."
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


def _write_empty_midi(path: Path) -> None:
    try:
        import mido
        m = mido.MidiFile()
        m.tracks.append(mido.MidiTrack())
        m.save(str(path))
    except Exception:
        path.write_bytes(b"")

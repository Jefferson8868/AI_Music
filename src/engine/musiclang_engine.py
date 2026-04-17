"""
MusicLang Predict engine.

MusicLang Predict (https://github.com/musiclang/musiclang_predict, BSD-3)
is a symbolic, chord-conditioned, MIDI-generating language model that
runs locally. It is a strong fit for modern-pop harmony drafts because
it accepts a chord progression as conditioning and produces polyphonic
MIDI at the requested bar count.

This engine wraps the `musiclang_predict` Python package. If the
package is not installed, construction raises ImportError and the
factory falls back to NullEngine — no crash in normal operation.

Mapping Music Generator's GenerationRequest to MusicLang parameters
------------------------------------------------------------------
  request.primer_notes  -> used to seed a root chord sequence
  request.num_steps     -> converted to `nb_tokens` (rough ratio 1:1)
  request.temperature   -> passed through
  request.qpm           -> passed through (MusicLang respects tempo)

Returns a `GenerationResult` whose `.notes` list contains dicts with
keys compatible with the existing Synthesizer (`pitch`, `start_time`,
`end_time`, `velocity`). `midi_path` is the path to the generated MIDI
file (placed under the user's output_dir).
"""

from __future__ import annotations

import asyncio
import tempfile
import uuid
from pathlib import Path

from loguru import logger

from config.settings import settings
from src.engine.interface import (
    GenerationRequest,
    GenerationResult,
    MusicEngineInterface,
)


class _MusicLangNotAvailable(ImportError):
    pass


def _load_musiclang():
    """Lazy-import the musiclang_predict package. Raises on failure."""
    try:
        import musiclang_predict  # type: ignore
        return musiclang_predict
    except Exception as exc:
        raise _MusicLangNotAvailable(
            "musiclang_predict is not installed. "
            "Install with: pip install musiclang_predict"
        ) from exc


class MusicLangEngine(MusicEngineInterface):
    """Local symbolic MIDI generator wrapping `musiclang_predict`."""

    def __init__(self, model_name: str = "small"):
        self._musiclang = _load_musiclang()
        self.model_name = model_name
        self._model = None  # lazy — first call triggers download/load
        self._output_dir = settings.output_dir / "musiclang"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    async def _ensure_model(self):
        if self._model is not None:
            return
        loop = asyncio.get_running_loop()

        def _load():
            # musiclang_predict exposes different constructors across
            # versions. We try the common public names and degrade
            # gracefully.
            ml = self._musiclang
            for attr in ("MusicLangPredictor", "MusicLang"):
                cls = getattr(ml, attr, None)
                if cls is None:
                    continue
                try:
                    return cls(self.model_name)
                except TypeError:
                    try:
                        return cls()
                    except Exception:
                        continue
            raise _MusicLangNotAvailable(
                "musiclang_predict has no recognised predictor class "
                "on this version."
            )

        self._model = await loop.run_in_executor(None, _load)

    async def _predict_midi(
        self,
        request: GenerationRequest,
        mode: str,
    ) -> Path:
        """Run MusicLang and write a MIDI file; return its path."""
        await self._ensure_model()
        loop = asyncio.get_running_loop()
        out_path = self._output_dir / f"ml_{mode}_{uuid.uuid4().hex[:8]}.mid"

        def _run():
            # We keep the call site tolerant to API drift. The common
            # entry point is .predict() returning either a musiclang
            # Score (with .to_midi) or a path string.
            model = self._model
            nb_tokens = max(32, int(request.num_steps))
            temperature = float(request.temperature or 1.0)
            try:
                result = model.predict(
                    nb_tokens=nb_tokens,
                    temperature=temperature,
                )
            except TypeError:
                # Older API: predict(seed, ...)
                result = model.predict(request.primer_notes or [60, 64, 67])
            # Convert to MIDI.
            if hasattr(result, "to_midi"):
                result.to_midi(str(out_path), tempo=int(request.qpm or 120))
            elif isinstance(result, (str, bytes, Path)):
                # Some versions return an already-written path.
                src = Path(result if isinstance(result, (str, Path))
                           else result.decode())
                if src != out_path:
                    out_path.write_bytes(src.read_bytes())
            else:
                raise RuntimeError(
                    "MusicLang returned an unsupported result type: "
                    f"{type(result).__name__}"
                )
            return out_path

        return await loop.run_in_executor(None, _run)

    async def _midi_to_notes(self, midi_path: Path) -> list[dict]:
        """Parse a MIDI file into the Synthesizer-friendly dict shape."""
        try:
            import mido  # already a project dep
        except Exception as exc:
            logger.warning(f"mido missing, cannot parse MIDI: {exc}")
            return []
        notes: list[dict] = []
        try:
            midi = mido.MidiFile(str(midi_path))
        except Exception as exc:
            logger.warning(f"MusicLang MIDI parse failed: {exc}")
            return []
        ticks_per_beat = max(1, midi.ticks_per_beat)
        tempo = 500000  # default 120bpm
        sec_per_tick = tempo / 1e6 / ticks_per_beat
        open_notes: dict[int, dict] = {}
        abs_tick = 0
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
        midi_path = await self._predict_midi(request, "melody")
        notes = await self._midi_to_notes(midi_path)
        duration = max(
            (n.get("end_time", 0.0) for n in notes), default=0.0,
        )
        return GenerationResult(
            midi_path=str(midi_path),
            notes=notes,
            duration_seconds=float(duration),
        )

    async def generate_polyphony(
        self, request: GenerationRequest,
    ) -> GenerationResult:
        midi_path = await self._predict_midi(request, "poly")
        notes = await self._midi_to_notes(midi_path)
        duration = max(
            (n.get("end_time", 0.0) for n in notes), default=0.0,
        )
        return GenerationResult(
            midi_path=str(midi_path),
            notes=notes,
            duration_seconds=float(duration),
        )

    async def health_check(self) -> bool:
        try:
            await self._ensure_model()
            return True
        except Exception as exc:
            logger.warning(f"MusicLang health_check failed: {exc}")
            return False

    async def close(self) -> None:
        # Nothing persistent to close; free the model for GC.
        self._model = None

"""Round 2 Phase D — audio rendering utilities.

`render_midi_to_wav` exports a .mid to a .wav using FluidSynth and a
SoundFont. Degrades gracefully if pyfluidsynth and the fluidsynth CLI
are both unavailable — in that case we log a warning and skip render.
"""

from __future__ import annotations

from src.audio.renderer import (
    RendererError,
    is_renderer_available,
    render_midi_to_wav,
)
from src.audio.mix import (
    MixError,
    is_mix_available,
    mix_stems,
)

__all__ = [
    "MixError",
    "RendererError",
    "is_mix_available",
    "is_renderer_available",
    "mix_stems",
    "render_midi_to_wav",
]

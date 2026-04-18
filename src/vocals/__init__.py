"""
Vocal synthesis (Round 2 Phase E).

End-to-end: lyric text + melody notes → rendered vocal `.wav` stem.

Pipeline
--------
    lyrics_to_phonemes(lyrics, melody_track)  →  list[VocalPhoneme]
    render_vocal_stem(phonemes, voicebank, out_path, tempo_bpm)  →  Path

Public surface is kept tiny on purpose — the pipeline imports exactly
three symbols. Backend details (OpenUtau CLI invocation, .ust file
writing, DiffSinger voicebank lookup) live in the submodules.

The whole package degrades gracefully: every public entry point raises
`VocalSynthError` instead of crashing on a missing OpenUtau / voicebank.
The pipeline catches that and continues without a vocal stem.
"""

from __future__ import annotations

from src.vocals.diffsinger_renderer import (
    VocalSynthError,
    is_vocal_synth_available,
    render_vocal_stem,
)
from src.vocals.phonemizer import (
    VocalPhoneme,
    lyrics_to_phonemes,
)

__all__ = [
    "VocalPhoneme",
    "VocalSynthError",
    "is_vocal_synth_available",
    "lyrics_to_phonemes",
    "render_vocal_stem",
]

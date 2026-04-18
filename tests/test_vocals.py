"""
Tests for Round 2 Phase E — DiffSinger / OpenUtau vocal synthesis.

Stub-safe: does NOT invoke OpenUtau. We never require the real binary.
These tests cover:

  * Phonemizer: empty lyrics → [], Mandarin glyphs → pinyin + tone,
    Latin words → lowercase tokens, melisma (more notes than chars)
    extends the last syllable, too-many-chars spreads tail over the
    remaining window.
  * Renderer: `is_vocal_synth_available` returns a bool, missing CLI
    raises VocalSynthError, empty phoneme list raises early, UST writer
    produces a well-formed file.
  * Integration-surface: VocalPhoneme dataclass fields present, package
    re-exports correct symbols.
"""

from __future__ import annotations

import pytest

from src.vocals import (
    VocalPhoneme,
    VocalSynthError,
    is_vocal_synth_available,
    lyrics_to_phonemes,
    render_vocal_stem,
)
from src.vocals.diffsinger_renderer import write_ust_file


# --------------------------------------------------------------------------
# Tiny helpers: a minimal melody-track stub (no score.py dependency).
# --------------------------------------------------------------------------

class _Note:
    __slots__ = ("pitch", "start_beat", "duration_beats")

    def __init__(self, pitch: int, start_beat: float, duration_beats: float):
        self.pitch = pitch
        self.start_beat = start_beat
        self.duration_beats = duration_beats


class _Track:
    def __init__(self, notes: list[_Note]):
        self.notes = notes


def _make_melody(pitches_and_beats: list[tuple[int, float, float]]) -> _Track:
    return _Track([_Note(p, s, d) for (p, s, d) in pitches_and_beats])


# --------------------------------------------------------------------------
# Phonemizer — basic shapes
# --------------------------------------------------------------------------

def test_phonemizer_empty_lyrics_returns_empty_list():
    assert lyrics_to_phonemes(None, None) == []
    assert lyrics_to_phonemes([], None) == []


def test_phonemizer_no_lines_returns_empty_list():
    melody = _make_melody([(60, 0.0, 1.0)])
    assert lyrics_to_phonemes(
        [{"section": "verse", "lines": []}], melody,
    ) == []


def test_phonemizer_mandarin_emits_one_per_glyph():
    # 4 characters, 4 notes — one-to-one pairing, each on its note.
    melody = _make_melody([
        (60, 0.0, 1.0),
        (62, 1.0, 1.0),
        (64, 2.0, 1.0),
        (65, 3.0, 1.0),
    ])
    phs = lyrics_to_phonemes(
        [{"section": "chorus", "lines": [
            {"text": "你好世界", "start_beat": 0.0},
        ]}],
        melody_track=melody,
    )
    assert len(phs) == 4
    texts = [p.text for p in phs]
    assert texts == ["你", "好", "世", "界"]
    pitches = [p.pitch_midi for p in phs]
    assert pitches == [60, 62, 64, 65]
    # Tones from built-in dict (pypinyin may or may not be installed).
    assert phs[0].tone == 3          # 你 = tone 3
    assert phs[1].tone == 3          # 好 = tone 3


def test_phonemizer_english_words_lowercased_and_stripped():
    melody = _make_melody([
        (60, 0.0, 1.0),
        (62, 1.0, 1.0),
    ])
    phs = lyrics_to_phonemes(
        [{"section": "verse", "lines": [
            {"text": "Hello, World!", "start_beat": 0.0},
        ]}],
        melody_track=melody,
    )
    assert len(phs) == 2
    assert phs[0].text == "hello"
    assert phs[1].text == "world"
    # English tokens aren't Mandarin → tone stays 0.
    assert phs[0].tone == 0


def test_phonemizer_more_notes_than_chars_extends_last_syllable():
    # 1 char, 4 notes — the last syllable should cover the extras.
    melody = _make_melody([
        (60, 0.0, 1.0),
        (62, 1.0, 1.0),
        (64, 2.0, 1.0),
        (65, 3.0, 1.0),
    ])
    phs = lyrics_to_phonemes(
        [{"section": "chorus", "lines": [
            {"text": "啊", "start_beat": 0.0},
        ]}],
        melody_track=melody,
    )
    assert len(phs) == 1
    # Duration grows: starts as 1.0, should now >= 4.0 (all 4 notes).
    assert phs[0].duration_beat >= 4.0 - 1e-6
    # Records the melisma count in extras.
    assert phs[0].extras.get("melisma_notes") == 3


def test_phonemizer_more_chars_than_notes_spreads_extras():
    # 4 chars, 1 note — 3 extras spread over the remaining window.
    melody = _make_melody([(60, 0.0, 1.0)])
    phs = lyrics_to_phonemes(
        [{"section": "chorus", "lines": [
            {"text": "啊啊啊啊", "start_beat": 0.0},
        ]}],
        melody_track=melody,
    )
    assert len(phs) == 4
    # First sits on the melody note at pitch 60.
    assert phs[0].pitch_midi == 60
    # Extras reuse the same pitch (no new notes to borrow from).
    assert phs[1].pitch_midi == 60
    # All start_beats strictly increase.
    starts = [p.start_beat for p in phs]
    assert starts == sorted(starts)


def test_phonemizer_line_without_melody_spreads_across_window():
    # Lyric line with a start_beat that lands AFTER all melody notes.
    melody = _make_melody([(60, 0.0, 1.0)])
    phs = lyrics_to_phonemes(
        [{"section": "outro", "lines": [
            {"text": "ab cd", "start_beat": 4.0},
        ]}],
        melody_track=melody,
    )
    # 2 word-tokens, 0 notes in the window → spread at default pitch (60).
    assert len(phs) == 2
    assert all(p.pitch_midi == 60 for p in phs)
    assert phs[0].start_beat >= 4.0 - 1e-6
    assert phs[1].start_beat > phs[0].start_beat


def test_phonemizer_sorts_lines_by_start_beat():
    # Lines given out of order — phonemizer must process them in time order.
    melody = _make_melody([
        (60, 0.0, 1.0),
        (62, 1.0, 1.0),
    ])
    phs = lyrics_to_phonemes(
        [{"section": "v", "lines": [
            {"text": "b", "start_beat": 1.0},
            {"text": "a", "start_beat": 0.0},
        ]}],
        melody_track=melody,
    )
    texts_in_order = [p.text for p in phs]
    assert texts_in_order == ["a", "b"]


# --------------------------------------------------------------------------
# VocalPhoneme dataclass
# --------------------------------------------------------------------------

def test_vocal_phoneme_dataclass_fields():
    ph = VocalPhoneme(
        phoneme="ni", tone=3, pitch_midi=60,
        start_beat=0.0, duration_beat=1.0, text="你",
    )
    assert ph.phoneme == "ni"
    assert ph.tone == 3
    assert ph.extras == {}


# --------------------------------------------------------------------------
# Renderer — availability & errors
# --------------------------------------------------------------------------

def test_is_vocal_synth_available_returns_bool():
    result = is_vocal_synth_available()
    assert isinstance(result, bool)


def test_render_vocal_stem_empty_list_raises():
    with pytest.raises(VocalSynthError):
        render_vocal_stem([], voicebank="default", out_path="nope.wav")


def test_render_vocal_stem_missing_cli_raises(monkeypatch, tmp_path):
    """With the CLI stubbed away, render should raise VocalSynthError."""
    import src.vocals.diffsinger_renderer as r

    monkeypatch.setattr(r, "_resolve_cli", lambda: None)
    phs = [VocalPhoneme(
        phoneme="a", tone=0, pitch_midi=60,
        start_beat=0.0, duration_beat=1.0, text="a",
    )]
    with pytest.raises(VocalSynthError):
        render_vocal_stem(phs, out_path=tmp_path / "v.wav")


# --------------------------------------------------------------------------
# UST writer — format
# --------------------------------------------------------------------------

def test_write_ust_file_produces_expected_blocks(tmp_path):
    phs = [
        VocalPhoneme(
            phoneme="ni", tone=3, pitch_midi=60,
            start_beat=0.0, duration_beat=1.0, text="你",
        ),
        VocalPhoneme(
            phoneme="hao", tone=3, pitch_midi=62,
            start_beat=1.0, duration_beat=1.0, text="好",
        ),
    ]
    out = write_ust_file(
        phs,
        out_path=tmp_path / "vocal.ust",
        tempo_bpm=95.0,
        project_name="mytest",
    )
    assert out.is_file()
    txt = out.read_text(encoding="utf-8")
    # Header fields present.
    assert "[#SETTING]" in txt
    assert "Tempo=95.00" in txt
    assert "ProjectName=mytest" in txt
    # Note blocks.
    assert "[#0000]" in txt
    assert "[#0001]" in txt
    # Pinyin + tone fused.
    assert "Lyric=ni3" in txt
    assert "Lyric=hao3" in txt
    # Track end marker.
    assert "[#TRACKEND]" in txt


def test_write_ust_inserts_rest_for_leading_gap(tmp_path):
    # First phoneme starts at beat 2 → UST should have a leading rest.
    phs = [VocalPhoneme(
        phoneme="a", tone=1, pitch_midi=60,
        start_beat=2.0, duration_beat=1.0, text="啊",
    )]
    out = write_ust_file(phs, out_path=tmp_path / "gap.ust", tempo_bpm=120.0)
    txt = out.read_text(encoding="utf-8")
    # A rest block + the note block = 2 note blocks before trackend.
    assert "[#0000]" in txt
    assert "[#0001]" in txt
    assert "Lyric=R" in txt
    assert "Lyric=a1" in txt


def test_write_ust_handles_empty_phoneme_list(tmp_path):
    # Writer must produce a valid (if empty) file — never crash.
    out = write_ust_file([], out_path=tmp_path / "empty.ust", tempo_bpm=120.0)
    assert out.is_file()
    txt = out.read_text(encoding="utf-8")
    assert "[#SETTING]" in txt
    assert "[#TRACKEND]" in txt

"""
Lyric → phoneme conversion (Round 2 Phase E2).

Turns (lyrics, melody_track) into a sequence of `VocalPhoneme` records
that OpenUtau/DiffSinger can consume.

Design
------
* For Mandarin, each Chinese character is one syllable. We pair each
  character with the NEXT available melody note after the line's
  start_beat, in order — matching the one-note-per-syllable contract
  DiffSinger expects. When the line has more characters than notes, the
  trailing characters get a zero-duration ghost slot (DiffSinger handles
  it as a micro-glide). When there are more melody notes than characters
  in a line, we extend the LAST character's duration to cover them —
  creating a melisma, which is exactly how real singers do it.

* For non-Mandarin text (English, Latin scripts) we whitespace-split into
  word-tokens and treat each word as one syllable. The phoneme string is
  the word itself; most DiffSinger voicebanks only have Mandarin phoneme
  sets so this path produces something closer to rap/chanting, but the
  timing is still correct.

* Tone (1-4) is sourced from `src.music.lyrics_alignment._lookup_tone`
  so Round 1's built-in dictionary and the optional pypinyin fallback
  are reused — no duplication.

Pure function; no I/O. Safe on empty inputs — returns `[]`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from src.music.lyrics_alignment import _is_chinese_char, _lookup_tone


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

@dataclass
class VocalPhoneme:
    """One sung syllable / note.

    Fields mirror what OpenUtau / DiffSinger need per note event:

    * `phoneme`  — the pinyin or word token (DiffSinger looks this up in
                   the voicebank's phoneme dictionary).
    * `tone`     — Mandarin tone 1-4 (0 if not Chinese / unknown).
    * `pitch_midi` — MIDI note number the note should be sung on.
    * `start_beat` / `duration_beat` — aligned to the melody track.
    * `text`     — the original glyph/word (kept for logging + UST export).
    """
    phoneme: str
    tone: int
    pitch_midi: int
    start_beat: float
    duration_beat: float
    text: str
    extras: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Tokenization
# --------------------------------------------------------------------------

def _tokenize_line(text: str) -> list[tuple[str, bool]]:
    """Split a lyric line into (token, is_cjk) pairs.

    Chinese glyphs are one syllable each; non-CJK segments are split on
    whitespace so each word becomes one token. Punctuation drops out.
    """
    if not text:
        return []
    tokens: list[tuple[str, bool]] = []
    buf: list[str] = []

    def flush_latin() -> None:
        if not buf:
            return
        chunk = "".join(buf).strip()
        buf.clear()
        for word in chunk.split():
            # Keep letters / digits; drop stray punctuation.
            cleaned = "".join(c for c in word if c.isalnum() or c == "'")
            if cleaned:
                tokens.append((cleaned.lower(), False))

    for ch in text:
        if _is_chinese_char(ch):
            flush_latin()
            tokens.append((ch, True))
        elif ch.isspace():
            flush_latin()
        else:
            buf.append(ch)
    flush_latin()
    return tokens


# --------------------------------------------------------------------------
# Mandarin → pinyin
# --------------------------------------------------------------------------

def _char_to_pinyin(ch: str) -> str:
    """Best-effort pinyin for a single Chinese character.

    Uses pypinyin if installed; otherwise falls back to the character
    itself (OpenUtau will warn but not crash). Tone-number is dropped —
    DiffSinger voicebanks key on plain pinyin + separate tone input.
    """
    try:
        from pypinyin import pinyin, Style  # type: ignore
    except Exception:
        return ch

    try:
        py = pinyin(ch, style=Style.NORMAL, errors="ignore")
        if py and py[0]:
            return str(py[0][0]).strip().lower() or ch
    except Exception:
        pass
    return ch


# --------------------------------------------------------------------------
# Melody extraction
# --------------------------------------------------------------------------

def _melody_notes_sorted(melody_track: Any) -> list[dict]:
    """Return a sorted list of {pitch, start_beat, duration_beat} dicts."""
    if melody_track is None:
        return []
    notes = getattr(melody_track, "notes", None) or []
    out: list[dict] = []
    for n in notes:
        pitch = int(getattr(n, "pitch", 0) or 0)
        start = float(getattr(n, "start_beat", 0.0) or 0.0)
        dur = float(getattr(n, "duration_beats", 0.0) or 0.0)
        out.append({"pitch": pitch, "start_beat": start, "duration_beat": dur})
    out.sort(key=lambda d: d["start_beat"])
    return out


def _notes_in_window(
    melody_notes: list[dict],
    start_beat: float,
    end_beat: float | None,
) -> list[dict]:
    """Return melody notes whose start_beat lies in [start_beat, end_beat)."""
    if end_beat is None:
        end_beat = float("inf")
    return [
        n for n in melody_notes
        if start_beat - 1e-6 <= n["start_beat"] < end_beat - 1e-6
    ]


# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------

def lyrics_to_phonemes(
    lyrics: list[dict] | None,
    melody_track: Any,
    default_pitch_midi: int = 60,
) -> list[VocalPhoneme]:
    """Convert lyric blocks + a melody track into a phoneme stream.

    Args:
        lyrics: A list of blocks in the same shape the Lyricist emits,
            i.e. `[{"section": "...", "lines": [{"text": "...",
            "start_beat": float}, ...]}, ...]`. None / [] returns [].
        melody_track: Any object with a `.notes` iterable of items that
            expose `.pitch`, `.start_beat`, `.duration_beats`. The first
            matching track the pipeline extracts (usually the "melody"
            role or the first track).
        default_pitch_midi: Pitch to use when the line has characters but
            no melody notes land in its window. Keeps the vocal audible
            instead of silently dropping the syllable.

    Returns:
        Flat list of `VocalPhoneme` in start_beat order. Empty list when
        there's nothing to sing.
    """
    if not lyrics:
        return []

    melody_notes = _melody_notes_sorted(melody_track)

    # Gather all lyric lines as (start_beat, text) tuples.
    all_lines: list[tuple[float, str]] = []
    for block in lyrics:
        if not isinstance(block, dict):
            continue
        lines = block.get("lines") or []
        if not isinstance(lines, list):
            continue
        for line in lines:
            if not isinstance(line, dict):
                continue
            text = str(line.get("text", "")).strip()
            if not text:
                continue
            try:
                beat = float(line.get("start_beat", 0.0))
            except (TypeError, ValueError):
                continue
            all_lines.append((beat, text))

    if not all_lines:
        return []

    all_lines.sort(key=lambda x: x[0])

    phonemes: list[VocalPhoneme] = []

    for idx, (line_start, text) in enumerate(all_lines):
        # Line window = from this line's start_beat to the NEXT line's
        # start_beat (or +16 beats if it's the last line — plenty for the
        # trailing melisma).
        next_start = (
            all_lines[idx + 1][0]
            if idx + 1 < len(all_lines)
            else line_start + 16.0
        )

        tokens = _tokenize_line(text)
        if not tokens:
            continue

        window_notes = _notes_in_window(melody_notes, line_start, next_start)

        phonemes.extend(
            _pair_tokens_with_notes(
                tokens=tokens,
                notes=window_notes,
                line_start=line_start,
                line_end=next_start,
                default_pitch=default_pitch_midi,
            )
        )

    logger.debug(
        f"[phonemizer] produced {len(phonemes)} phonemes from "
        f"{len(all_lines)} lyric lines"
    )
    return phonemes


def _pair_tokens_with_notes(
    tokens: list[tuple[str, bool]],
    notes: list[dict],
    line_start: float,
    line_end: float,
    default_pitch: int,
) -> list[VocalPhoneme]:
    """Zip tokens and melody notes. Handles both uneven cases."""
    result: list[VocalPhoneme] = []

    n_tokens = len(tokens)
    n_notes = len(notes)

    if n_notes == 0:
        # Degenerate: line has lyrics but no melody notes landed in its
        # window. Spread tokens evenly across the window at the default
        # pitch so the line still gets sung.
        span = max(line_end - line_start, 1e-3)
        per_beat = span / max(n_tokens, 1)
        for i, (tok, is_cjk) in enumerate(tokens):
            phoneme = _char_to_pinyin(tok) if is_cjk else tok
            tone = _lookup_tone(tok) if is_cjk else 0
            result.append(VocalPhoneme(
                phoneme=phoneme,
                tone=tone,
                pitch_midi=default_pitch,
                start_beat=line_start + i * per_beat,
                duration_beat=per_beat,
                text=tok,
            ))
        return result

    # Pair positionally: token i → note i, up to min(n_tokens, n_notes).
    pair_count = min(n_tokens, n_notes)
    for i in range(pair_count):
        tok, is_cjk = tokens[i]
        note = notes[i]
        phoneme = _char_to_pinyin(tok) if is_cjk else tok
        tone = _lookup_tone(tok) if is_cjk else 0
        result.append(VocalPhoneme(
            phoneme=phoneme,
            tone=tone,
            pitch_midi=note["pitch"],
            start_beat=note["start_beat"],
            duration_beat=note["duration_beat"],
            text=tok,
        ))

    if n_tokens > n_notes:
        # Too many syllables for the melody — spread the extras AFTER the
        # last paired note, stealing time from the line's remaining window.
        last_note = notes[-1]
        spread_start = last_note["start_beat"] + last_note["duration_beat"]
        remaining = max(line_end - spread_start, 1e-3)
        extras = n_tokens - n_notes
        per_extra = remaining / extras
        for j in range(extras):
            tok, is_cjk = tokens[n_notes + j]
            phoneme = _char_to_pinyin(tok) if is_cjk else tok
            tone = _lookup_tone(tok) if is_cjk else 0
            result.append(VocalPhoneme(
                phoneme=phoneme,
                tone=tone,
                pitch_midi=last_note["pitch"],
                start_beat=spread_start + j * per_extra,
                duration_beat=per_extra,
                text=tok,
            ))

    elif n_notes > n_tokens and result:
        # More melody notes than syllables — melisma the last syllable
        # over all remaining notes. We do this by extending the last
        # paired phoneme's duration to cover them.
        extra_dur = sum(
            n["duration_beat"] for n in notes[pair_count:]
        )
        # Additionally bridge any gaps between the last paired note and
        # the first leftover note (so the hold reaches them).
        if notes[pair_count:]:
            first_leftover = notes[pair_count]["start_beat"]
            last_paired_end = (
                result[-1].start_beat + result[-1].duration_beat
            )
            gap = max(first_leftover - last_paired_end, 0.0)
            extra_dur += gap
        result[-1].duration_beat += extra_dur
        result[-1].extras["melisma_notes"] = n_notes - n_tokens

    return result


__all__ = [
    "VocalPhoneme",
    "lyrics_to_phonemes",
]

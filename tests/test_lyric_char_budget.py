"""
Tests for Bug D fix — per-section lyric character budget.

The Lyricist used to get only a per-beat density advisory ("target
0.55/beat") which it frequently ignored. These tests cover the pure
helpers that let the pipeline:
  * compute absolute min/target/max character counts per section,
  * format those counts as a HARD budget in the Lyricist prompt,
  * validate the Lyricist's output against the budget and return a
    per-section list of corrections ready to re-prompt with.
"""

from __future__ import annotations

from src.music.lyrics_alignment import (
    compute_section_char_targets,
    count_lyric_chars,
    format_char_count_plan_for_lyricist,
    format_char_count_violations,
    validate_section_char_counts,
)


# ---------------------------------------------------------------------------
# count_lyric_chars
# ---------------------------------------------------------------------------

def test_count_chinese_glyphs():
    assert count_lyric_chars("春花秋月") == 4


def test_count_english_words():
    assert count_lyric_chars("under neon rain tonight") == 4


def test_count_mixed_prefers_chinese():
    # Mixed CJK + Latin: the Chinese count wins because those are the
    # syllables that align with melody notes.
    assert count_lyric_chars("春 under 月 light") == 2


def test_count_ignores_punctuation_in_cjk():
    assert count_lyric_chars("春，花；秋。月") == 4


def test_count_empty():
    assert count_lyric_chars("") == 0
    assert count_lyric_chars("   ") == 0


# ---------------------------------------------------------------------------
# compute_section_char_targets
# ---------------------------------------------------------------------------

def _section(name, role, bars, beats_per_bar=4, start=1.0):
    end = start + bars * beats_per_bar
    return {
        "name": name, "role": role, "bars": bars,
        "start_beat": start, "end_beat": end,
    }


def test_targets_scale_with_span():
    # verse density target 1.00/beat * 16 beats = 16 chars.
    sec = _section("verse", "verse", bars=4)
    out = compute_section_char_targets([sec])
    assert len(out) == 1
    assert out[0]["section_name"] == "verse"
    assert out[0]["span_beats"] == 16.0
    assert out[0]["target_chars"] == 16
    # min 0.70/beat * 16 = 11.2 → round to 11.
    assert out[0]["min_chars"] == 11
    # max 1.40/beat * 16 = 22.4 → round to 22.
    assert out[0]["max_chars"] == 22


def test_targets_skip_zero_density_intro_by_default():
    # intro target density = 0.00 → char target = 0 → skipped.
    out = compute_section_char_targets([
        _section("intro", "intro", bars=2),
        _section("verse", "verse", bars=4),
    ])
    names = [t["section_name"] for t in out]
    assert "intro" not in names
    assert "verse" in names


def test_targets_allow_list_overrides_zero_density_skip():
    # Explicit allow-list forces intro to be scored anyway, even though
    # its target_chars is 0.
    out = compute_section_char_targets(
        [_section("intro", "intro", bars=2)],
        lyric_section_names=["intro"],
    )
    assert len(out) == 1
    assert out[0]["section_name"] == "intro"
    assert out[0]["target_chars"] == 0


def test_targets_use_role_for_density_lookup():
    # A section named "bridge" but with role="chorus" should use chorus
    # density (0.55/beat * 16 = 8.8 → 9).
    sec = {
        "name": "bridge", "role": "chorus", "bars": 4,
        "start_beat": 1.0, "end_beat": 17.0,
    }
    out = compute_section_char_targets([sec])
    assert out[0]["target_chars"] == 9


# ---------------------------------------------------------------------------
# format_char_count_plan_for_lyricist
# ---------------------------------------------------------------------------

def test_format_plan_mentions_each_section_with_range():
    targets = [
        {
            "section_name": "verse", "role": "verse", "span_beats": 16.0,
            "min_chars": 11, "target_chars": 16, "max_chars": 22,
        },
        {
            "section_name": "chorus", "role": "chorus", "span_beats": 16.0,
            "min_chars": 6, "target_chars": 9, "max_chars": 14,
        },
    ]
    text = format_char_count_plan_for_lyricist(targets)
    assert "HARD" in text
    assert "[verse]" in text and "11-22" in text and "target 16" in text
    assert "[chorus]" in text and "6-14" in text and "target 9" in text


def test_format_plan_empty():
    assert format_char_count_plan_for_lyricist([]) == ""


# ---------------------------------------------------------------------------
# validate_section_char_counts
# ---------------------------------------------------------------------------

def _lyric_block(section, lines):
    return {
        "section_name": section,
        "lines": [{"text": t, "start_beat": 0.0} for t in lines],
    }


def test_validate_reports_too_sparse():
    targets = [
        {
            "section_name": "verse", "role": "verse", "span_beats": 16.0,
            "min_chars": 11, "target_chars": 16, "max_chars": 22,
        },
    ]
    lyrics = [_lyric_block("verse", ["春花秋月", "风雨声"])]  # 7 chars
    violations = validate_section_char_counts(lyrics, targets)
    assert len(violations) == 1
    assert violations[0]["verdict"] == "too_sparse"
    assert violations[0]["current_chars"] == 7
    assert "ADD" in violations[0]["instruction"]


def test_validate_reports_too_dense():
    targets = [
        {
            "section_name": "chorus", "role": "chorus", "span_beats": 16.0,
            "min_chars": 6, "target_chars": 9, "max_chars": 14,
        },
    ]
    lyrics = [_lyric_block("chorus", ["春花秋月夜" * 4])]  # 20 chars
    violations = validate_section_char_counts(lyrics, targets)
    assert len(violations) == 1
    assert violations[0]["verdict"] == "too_dense"
    assert violations[0]["current_chars"] == 20
    assert "TRIM" in violations[0]["instruction"]


def test_validate_accepts_in_range():
    targets = [
        {
            "section_name": "verse", "role": "verse", "span_beats": 16.0,
            "min_chars": 11, "target_chars": 16, "max_chars": 22,
        },
    ]
    lyrics = [_lyric_block("verse", ["春花秋月夜", "风雨声声近", "远山望归人"])]
    # 5 + 5 + 5 = 15 chars — within 11-22.
    violations = validate_section_char_counts(lyrics, targets)
    assert violations == []


def test_validate_missing_section_counts_as_zero():
    # If the lyricist skips a section entirely, that's too_sparse.
    targets = [
        {
            "section_name": "chorus", "role": "chorus", "span_beats": 16.0,
            "min_chars": 6, "target_chars": 9, "max_chars": 14,
        },
    ]
    violations = validate_section_char_counts([], targets)
    assert len(violations) == 1
    assert violations[0]["verdict"] == "too_sparse"
    assert violations[0]["current_chars"] == 0


def test_validate_is_case_insensitive_on_section_name():
    targets = [
        {
            "section_name": "Verse", "role": "verse", "span_beats": 16.0,
            "min_chars": 11, "target_chars": 16, "max_chars": 22,
        },
    ]
    lyrics = [_lyric_block("verse", ["春花秋月夜风雨声声近远山望归人"])]  # 15
    violations = validate_section_char_counts(lyrics, targets)
    assert violations == []


def test_validate_counts_multiple_blocks_for_same_section():
    targets = [
        {
            "section_name": "chorus", "role": "chorus", "span_beats": 16.0,
            "min_chars": 6, "target_chars": 9, "max_chars": 14,
        },
    ]
    lyrics = [
        _lyric_block("chorus", ["春花秋月"]),   # 4
        _lyric_block("chorus", ["风雨声声"]),   # 4
    ]
    # Total 8 — in range [6, 14].
    violations = validate_section_char_counts(lyrics, targets)
    assert violations == []


def test_format_violations_renders_prompt():
    violations = [
        {
            "section_name": "verse", "current_chars": 7,
            "min_chars": 11, "max_chars": 22, "target_chars": 16,
            "verdict": "too_sparse",
            "instruction": "[verse] too sparse: have 7...",
        },
    ]
    text = format_char_count_violations(violations)
    assert "CHARACTER-COUNT VIOLATIONS" in text
    assert "[verse] too sparse" in text


def test_format_violations_empty():
    assert format_char_count_violations([]) == ""

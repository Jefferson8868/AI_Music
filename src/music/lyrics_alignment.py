"""
Lyrics alignment analysis (Improvement F).

Goal: close the loop so the Lyricist (and, by extension, the Composer when
it's lyrics-aware) actually *sees* whether the lines it produced land on
melody beats, carry a sensible syllable density, and — for Chinese lyrics —
whether character tones fight the melody contour.

Previously the pipeline only computed `lyrics_alignment_pct` for the Critic
(see `compute_score_metrics` in src/music/score.py). This module adds:

    - per-section beat alignment (not just overall percent)
    - syllable / character density vs. target density per section role
    - Chinese-tone vs. melody-contour conflict detection

All functions are pure and cheap. They never require the full Score — just
the per-section data the pipeline already has — so they can run every round.

Tone mapping for Chinese (Mandarin):
    1  阴平 (high-level)         — flat; neutral
    2  阳平 (rising)              — wants melody NOT to descend
    3  上声 (low-dipping)         — wants melody to dip or stay low
    4  去声 (falling)             — wants melody NOT to ascend
    0  neutral / unknown          — ignored

We use a tiny built-in dictionary for a handful of super-common 戏腔 / 国风
characters so the module is functional out of the box. When `pypinyin` is
installed, we fall back to it for broader coverage. Import is optional —
missing package just means we return `tone=0` for unknown characters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from loguru import logger


# --------------------------------------------------------------------------- #
# Density targets per section role                                            #
# --------------------------------------------------------------------------- #

# Empirically tuned for modern Chinese pop / fusion. The "target_per_beat"
# is lyric characters (or English syllables) per beat of the melody in that
# section. Verse is denser (story-telling), chorus thinner (melisma-friendly
# so the vocal hook can ring), bridge medium.
DENSITY_TARGETS: dict[str, dict[str, float]] = {
    "intro":      {"min": 0.00, "target": 0.00, "max": 0.20},
    "verse":      {"min": 0.70, "target": 1.00, "max": 1.40},
    "pre_chorus": {"min": 0.55, "target": 0.80, "max": 1.10},
    "chorus":     {"min": 0.40, "target": 0.55, "max": 0.90},
    "bridge":     {"min": 0.55, "target": 0.75, "max": 1.00},
    "outro":      {"min": 0.00, "target": 0.20, "max": 0.60},
    "default":    {"min": 0.50, "target": 0.80, "max": 1.20},
}


def _density_target(section_role: str) -> dict[str, float]:
    key = (section_role or "").lower().strip()
    return DENSITY_TARGETS.get(key, DENSITY_TARGETS["default"])


# --------------------------------------------------------------------------- #
# Chinese tone dictionary (minimal built-in + optional pypinyin)              #
# --------------------------------------------------------------------------- #

# Curated mini-dictionary so we're useful with zero deps. Only characters
# common in Chinese pop / 戏腔 / 国风 lyrics.
_BUILTIN_TONES: dict[str, int] = {
    # tone 1 (high-level)
    "风": 1, "秋": 1, "烟": 1, "山": 1, "天": 1, "心": 1, "星": 1, "空": 1,
    "东": 1, "西": 1, "听": 1, "说": 1, "春": 1, "花": 1, "车": 1, "思": 1,
    "江": 1, "家": 1, "书": 1, "灯": 1,
    # tone 2 (rising)
    "人": 2, "情": 2, "时": 2, "年": 2, "来": 2, "归": 2, "回": 2, "留": 2,
    "眉": 2, "头": 2, "行": 2, "长": 2, "王": 2, "名": 2, "求": 2, "何": 2,
    "如": 2, "谁": 2, "流": 2, "儿": 2,
    # tone 3 (low-dipping)
    "你": 3, "我": 3, "好": 3, "手": 3, "水": 3, "冷": 3, "海": 3, "雨": 3,
    "想": 3, "愿": 3, "老": 3, "远": 3, "晚": 3, "久": 3, "草": 3, "野": 3,
    "满": 3, "起": 3, "几": 3, "走": 3,
    # tone 4 (falling)
    "是": 4, "对": 4, "这": 4, "那": 4, "夜": 4, "月": 4, "梦": 4, "爱": 4,
    "见": 4, "念": 4, "醉": 4, "泪": 4, "怕": 4, "叹": 4, "断": 4, "恋": 4,
    "去": 4, "问": 4, "落": 4, "暮": 4,
}


def _lookup_tone(char: str) -> int:
    """Return tone number (1-4) for a Chinese character, 0 if unknown."""
    if not char:
        return 0
    t = _BUILTIN_TONES.get(char, 0)
    if t:
        return t
    # Optional pypinyin fallback.
    try:
        from pypinyin import pinyin, Style  # type: ignore
    except Exception:
        return 0
    try:
        pinyin_list = pinyin(char, style=Style.TONE3, errors="ignore")
        if not pinyin_list or not pinyin_list[0]:
            return 0
        syl = pinyin_list[0][0]
        for c in reversed(syl):
            if c.isdigit():
                d = int(c)
                return d if 1 <= d <= 4 else 0
        return 0
    except Exception:
        return 0


def _is_chinese_char(c: str) -> bool:
    # CJK Unified Ideographs.
    return bool(c) and "\u4e00" <= c <= "\u9fff"


# --------------------------------------------------------------------------- #
# Data containers                                                             #
# --------------------------------------------------------------------------- #

@dataclass
class LyricLineAnalysis:
    section_name: str
    text: str
    start_beat: float
    chars: int                 # glyph count (rough syllable proxy)
    aligned_chars: int         # chars whose beats match a melody note
    tone_conflicts: int        # rising tone on descending melody (etc.)
    notes: list[str] = field(default_factory=list)


@dataclass
class SectionLyricStats:
    section_name: str
    role: str
    bars: int
    melody_notes: int
    total_chars: int
    density_per_beat: float
    density_target: dict[str, float]
    density_verdict: str       # "too_sparse" | "too_dense" | "ok"
    aligned_chars: int
    alignment_pct: float
    tone_conflicts: int
    tone_conflict_pct: float
    notes: list[LyricLineAnalysis] = field(default_factory=list)


@dataclass
class LyricsAnalysisReport:
    sections: list[SectionLyricStats] = field(default_factory=list)
    overall_alignment_pct: float = 0.0
    overall_density_verdicts: dict[str, int] = field(default_factory=dict)
    overall_tone_conflict_pct: float = 0.0

    def to_prompt_block(self) -> str:
        """Compact, human-readable summary for a prompt."""
        if not self.sections:
            return ""
        lines = [
            "LYRICS ALIGNMENT REPORT (from current Score + lyrics):",
            f"  overall_alignment={self.overall_alignment_pct:.0f}% of "
            "lyric beats match melody beats",
            f"  overall_tone_conflicts="
            f"{self.overall_tone_conflict_pct:.0f}% of Chinese "
            "characters fight melody contour",
        ]
        if self.overall_density_verdicts:
            verdicts = ", ".join(
                f"{k}:{v}" for k, v in
                sorted(self.overall_density_verdicts.items())
            )
            lines.append(f"  density_verdicts={verdicts}")
        for sec in self.sections:
            lines.append(
                f"  [{sec.section_name}] "
                f"role={sec.role} "
                f"chars={sec.total_chars} "
                f"density={sec.density_per_beat:.2f}/beat "
                f"(target="
                f"{sec.density_target['target']:.2f}/beat, "
                f"verdict={sec.density_verdict}) "
                f"aligned={sec.alignment_pct:.0f}% "
                f"tone_conflicts={sec.tone_conflict_pct:.0f}%"
            )
            # Only surface the WORST 2 lines per section so the Lyricist
            # knows what to fix — not a 50-line wall of text.
            flagged = [
                ln for ln in sec.notes
                if (ln.chars and (
                    ln.aligned_chars < ln.chars
                    or ln.tone_conflicts
                ))
            ]
            flagged.sort(
                key=lambda l: (
                    l.tone_conflicts,
                    l.chars - l.aligned_chars,
                ),
                reverse=True,
            )
            for ln in flagged[:2]:
                lines.append(
                    f"    - {ln.text!r}@beat{ln.start_beat:.1f} "
                    f"aligned={ln.aligned_chars}/{ln.chars} "
                    f"tone_conflicts={ln.tone_conflicts}"
                )
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Core analysis                                                               #
# --------------------------------------------------------------------------- #

def _melody_contour_at(
    melody_notes: list[dict], beat: float, window: float = 0.5,
) -> int:
    """Contour sign at a beat: +1 ascending, -1 descending, 0 flat/unknown.

    `melody_notes` is a list of {"pitch", "start_beat", ...} dicts.
    """
    if not melody_notes:
        return 0
    prev_pitch = None
    next_pitch = None
    for n in melody_notes:
        b = float(n.get("start_beat", 0.0))
        if b <= beat:
            prev_pitch = n.get("pitch")
        elif next_pitch is None and b - beat <= window * 8:
            next_pitch = n.get("pitch")
            break
    if prev_pitch is None or next_pitch is None:
        return 0
    try:
        diff = int(next_pitch) - int(prev_pitch)
    except (TypeError, ValueError):
        return 0
    if diff > 1:
        return 1
    if diff < -1:
        return -1
    return 0


def _tone_vs_contour_conflict(tone: int, contour: int) -> bool:
    """Return True when the character tone fights the melody contour.

    - Tone 2 (rising) on descending melody (contour=-1) → conflict.
    - Tone 4 (falling) on ascending melody (contour=+1) → conflict.
    - Tone 3 (low-dipping) on steeply ascending melody → conflict.
    - Tone 1 (flat) on any contour → no conflict (neutral).
    """
    if tone == 2 and contour == -1:
        return True
    if tone == 4 and contour == 1:
        return True
    if tone == 3 and contour == 1:
        return True
    return False


def _section_for_beat(
    enriched_sections: list[dict], beat: float,
) -> dict | None:
    for sec in enriched_sections:
        s = float(sec.get("start_beat", 0.0))
        e = float(sec.get("end_beat", 0.0))
        if s <= beat < e:
            return sec
    return None


def _melody_notes_from_score(score) -> list[dict]:
    """Extract a list of note dicts from the melody-role track of a Score."""
    if score is None or not getattr(score, "tracks", None):
        return []
    melody_trk = None
    for t in score.tracks:
        name = (getattr(t, "name", "") or "").lower()
        role = (getattr(t, "role", "") or "").lower()
        if "melody" in name or role == "melody":
            melody_trk = t
            break
    if melody_trk is None:
        melody_trk = score.tracks[0]
    out: list[dict] = []
    for n in getattr(melody_trk, "notes", []):
        out.append(
            {
                "pitch": getattr(n, "pitch", 0),
                "start_beat": float(getattr(n, "start_beat", 0.0)),
                "duration_beats": float(
                    getattr(n, "duration_beats", 0.0),
                ),
            }
        )
    return out


def analyze_lyrics(
    score,
    lyrics: list[dict] | None,
    enriched_sections: list[dict],
) -> LyricsAnalysisReport:
    """Run the full lyrics analysis for the current round.

    Safe to call with empty inputs — returns a report with empty sections.
    """
    report = LyricsAnalysisReport()
    if not lyrics or not enriched_sections:
        return report

    melody_notes = _melody_notes_from_score(score)
    melody_beat_set = {round(n["start_beat"], 3) for n in melody_notes}

    # Group lyrics lines by the section that contains their start_beat.
    section_groups: dict[str, list[tuple[dict, dict]]] = {}
    for block in lyrics:
        if not isinstance(block, dict):
            continue
        lines = block.get("lines") or []
        if not isinstance(lines, list):
            continue
        for line in lines:
            if not isinstance(line, dict):
                continue
            if "start_beat" not in line:
                continue
            try:
                beat = float(line["start_beat"])
            except (TypeError, ValueError):
                continue
            sec = _section_for_beat(enriched_sections, beat)
            if sec is None:
                continue
            section_groups.setdefault(sec["name"], []).append(
                (sec, line),
            )

    total_aligned = 0
    total_chars = 0
    total_tone_conflicts = 0
    total_tone_opportunities = 0
    verdicts: dict[str, int] = {}

    for sec_info in enriched_sections:
        sec_name = sec_info["name"]
        role = (
            sec_info.get("role")
            or sec_info.get("mood")
            or sec_name
        )
        bars = int(sec_info.get("bars", 0) or 0)
        s_beat = float(sec_info.get("start_beat", 0.0))
        e_beat = float(sec_info.get("end_beat", 0.0))
        span_beats = max(e_beat - s_beat, 1e-6)

        melody_in_sec = [
            n for n in melody_notes
            if s_beat <= n["start_beat"] < e_beat
        ]

        line_entries = section_groups.get(sec_name, [])
        sec_chars = 0
        sec_aligned = 0
        sec_tone_conflicts = 0
        line_analyses: list[LyricLineAnalysis] = []

        for _sec, line in line_entries:
            text = str(line.get("text", "")).strip()
            try:
                start_beat = float(line["start_beat"])
            except (TypeError, ValueError):
                continue

            # Character-level iteration (Chinese glyphs) OR whitespace split
            # for Latin text.
            has_cjk = any(_is_chinese_char(c) for c in text)
            if has_cjk:
                tokens = [c for c in text if _is_chinese_char(c)]
            else:
                tokens = [t for t in text.split() if t]

            char_count = len(tokens)
            line_aligned = 0
            line_conflicts = 0

            # Alignment: does the line's start beat land on a melody note?
            # We only have per-line beats, not per-character — so approximate
            # by checking the line beat + each full-beat offset for N chars.
            for idx, tok in enumerate(tokens):
                char_beat = round(start_beat + idx * 1.0, 3)
                if char_beat in melody_beat_set:
                    line_aligned += 1
                # Tone conflict — Chinese only.
                if has_cjk:
                    tone = _lookup_tone(tok)
                    if tone in (2, 3, 4):
                        contour = _melody_contour_at(
                            melody_in_sec, char_beat,
                        )
                        if _tone_vs_contour_conflict(tone, contour):
                            line_conflicts += 1
                        total_tone_opportunities += 1

            sec_chars += char_count
            sec_aligned += line_aligned
            sec_tone_conflicts += line_conflicts

            line_analyses.append(
                LyricLineAnalysis(
                    section_name=sec_name,
                    text=text,
                    start_beat=start_beat,
                    chars=char_count,
                    aligned_chars=line_aligned,
                    tone_conflicts=line_conflicts,
                )
            )

        density_target = _density_target(role)
        density = sec_chars / span_beats if span_beats > 0 else 0.0
        if density < density_target["min"]:
            verdict = "too_sparse"
        elif density > density_target["max"]:
            verdict = "too_dense"
        else:
            verdict = "ok"
        verdicts[verdict] = verdicts.get(verdict, 0) + 1

        alignment_pct = (
            100.0 * sec_aligned / sec_chars if sec_chars else 0.0
        )
        tone_conflict_pct = (
            100.0 * sec_tone_conflicts / sec_chars
            if sec_chars else 0.0
        )

        report.sections.append(
            SectionLyricStats(
                section_name=sec_name,
                role=role,
                bars=bars,
                melody_notes=len(melody_in_sec),
                total_chars=sec_chars,
                density_per_beat=density,
                density_target=density_target,
                density_verdict=verdict,
                aligned_chars=sec_aligned,
                alignment_pct=alignment_pct,
                tone_conflicts=sec_tone_conflicts,
                tone_conflict_pct=tone_conflict_pct,
                notes=line_analyses,
            )
        )

        total_aligned += sec_aligned
        total_chars += sec_chars
        total_tone_conflicts += sec_tone_conflicts

    report.overall_alignment_pct = (
        100.0 * total_aligned / total_chars if total_chars else 0.0
    )
    report.overall_density_verdicts = verdicts
    report.overall_tone_conflict_pct = (
        100.0 * total_tone_conflicts / total_tone_opportunities
        if total_tone_opportunities else 0.0
    )
    return report


# --------------------------------------------------------------------------- #
# Lyricist-facing feedback builder                                            #
# --------------------------------------------------------------------------- #

def format_lyrics_feedback_for_lyricist(
    report: LyricsAnalysisReport,
    max_lines: int = 30,
) -> str:
    """Build an actionable feedback string for the Lyricist.

    Prioritises density failures + tone conflicts (what the Lyricist can
    fix) and per-section beat alignment (which it can fix by re-quantising).
    """
    if not report.sections:
        return ""
    out: list[str] = [
        "LYRICS FEEDBACK (from last round's analysis):",
    ]
    action_items: list[str] = []
    for sec in report.sections:
        if sec.density_verdict != "ok":
            gap = (
                sec.density_target["target"] - sec.density_per_beat
                if sec.density_verdict == "too_sparse"
                else sec.density_per_beat - sec.density_target["target"]
            )
            direction = (
                "ADD more characters"
                if sec.density_verdict == "too_sparse"
                else "TRIM characters"
            )
            action_items.append(
                f"- [{sec.section_name}] {direction}: current "
                f"{sec.density_per_beat:.2f}/beat, target "
                f"{sec.density_target['target']:.2f}/beat "
                f"(|gap|={gap:.2f})."
            )
        if sec.alignment_pct < 80 and sec.total_chars:
            action_items.append(
                f"- [{sec.section_name}] beat alignment "
                f"{sec.alignment_pct:.0f}% (<80%): snap line "
                "start_beats to actual melody note beats."
            )
        if sec.tone_conflict_pct >= 20 and sec.total_chars:
            action_items.append(
                f"- [{sec.section_name}] tone conflicts "
                f"{sec.tone_conflict_pct:.0f}%: pick characters whose "
                "tone matches the melody contour at that beat (rising "
                "tone ≈ rising melody, falling ≈ falling)."
            )
    if not action_items:
        out.append(
            "  (lyrics are on-target for density, alignment, and tones — "
            "focus on poetic quality and imagery.)"
        )
    else:
        out.extend(action_items[:max_lines])
    return "\n".join(out)


def format_density_plan_for_lyricist(
    enriched_sections: list[dict],
) -> str:
    """Build an UP-FRONT density plan the Lyricist should respect.

    Used on round 1 (no report yet) and on every round to reinforce.
    """
    if not enriched_sections:
        return ""
    out = ["LYRICS DENSITY PLAN (characters per beat, target):"]
    for sec in enriched_sections:
        role = (
            sec.get("role") or sec.get("mood") or sec.get("name", "")
        )
        tgt = _density_target(role)
        out.append(
            f"  [{sec.get('name','')}] "
            f"target {tgt['target']:.2f}/beat "
            f"(range {tgt['min']:.2f}-{tgt['max']:.2f}). "
            f"{sec.get('bars', 0)} bars."
        )
    out.append(
        "Rule of thumb: verses tell the story (denser), choruses breathe "
        "on the hook (sparser, use melisma), bridges contrast."
    )
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Per-section character budget (Bug D)                                        #
# --------------------------------------------------------------------------- #

def count_lyric_chars(text: str) -> int:
    """Count lyric units in a line.

    Chinese: number of Chinese glyphs. Latin: whitespace-split tokens.
    Mixed: Chinese count wins (CJK glyphs are the syllables that line
    up with melody notes).
    """
    if not text:
        return 0
    text = text.strip()
    has_cjk = any(_is_chinese_char(c) for c in text)
    if has_cjk:
        return sum(1 for c in text if _is_chinese_char(c))
    return len([t for t in text.split() if t])


def compute_section_char_targets(
    enriched_sections: list[dict],
    lyric_section_names: list[str] | None = None,
) -> list[dict]:
    """Convert per-beat density into absolute character budgets.

    Args:
        enriched_sections: sections with ``start_beat`` / ``end_beat`` /
            ``role`` / ``name``.
        lyric_section_names: optional allow-list of section names that
            should carry lyrics (e.g. featured sections). Sections not
            in this list are skipped entirely. ``None`` means "include
            every section with a non-zero target density".

    Returns:
        A list of dicts with ``section_name``, ``role``, ``span_beats``,
        ``min_chars``, ``target_chars``, ``max_chars``. Only sections
        that need lyrics (target_chars > 0) are included.
    """
    allow = (
        {s.lower() for s in lyric_section_names}
        if lyric_section_names is not None
        else None
    )
    targets: list[dict] = []
    for sec in enriched_sections:
        name = sec.get("name", "")
        role = (
            sec.get("role") or sec.get("mood") or name
        )
        span = max(
            float(sec.get("end_beat", 0.0))
            - float(sec.get("start_beat", 0.0)),
            0.0,
        )
        tgt = _density_target(role)
        target_chars = int(round(tgt["target"] * span))
        if allow is not None:
            if name.lower() not in allow:
                continue
        elif target_chars <= 0:
            continue
        targets.append({
            "section_name": name,
            "role": role,
            "span_beats": span,
            "min_chars": max(int(round(tgt["min"] * span)), 0),
            "target_chars": target_chars,
            "max_chars": max(int(round(tgt["max"] * span)), target_chars),
        })
    return targets


def format_char_count_plan_for_lyricist(targets: list[dict]) -> str:
    """Strict, per-section character budget for the Lyricist prompt.

    Unlike ``format_density_plan_for_lyricist`` this states ABSOLUTE
    counts (not a per-beat rate) so the Lyricist has a concrete number
    to hit rather than a rate to multiply.
    """
    if not targets:
        return ""
    out = [
        "LYRICS CHARACTER BUDGET (HARD requirement — each section "
        "must land in its range):",
    ]
    for t in targets:
        out.append(
            f"  [{t['section_name']}] "
            f"need {t['min_chars']}-{t['max_chars']} characters "
            f"(target {t['target_chars']}), "
            f"across {t['span_beats']:.0f} beats."
        )
    out.append(
        "Count Chinese glyphs one-by-one; for Latin text count "
        "whitespace-separated words. Punctuation does not count. "
        "If you cannot fill a section, use melisma (one character on "
        "multiple notes) but still hit the minimum."
    )
    return "\n".join(out)


def validate_section_char_counts(
    lyrics: list[dict],
    targets: list[dict],
) -> list[dict]:
    """Check each section's current character count against its target.

    Args:
        lyrics: list of ``{section_name, lines: [{text, ...}]}`` blocks
            (the shape emitted by Lyricist).
        targets: output of ``compute_section_char_targets``.

    Returns:
        One dict per out-of-range section, with keys ``section_name``,
        ``current_chars``, ``min_chars``, ``max_chars``, ``verdict``
        ("too_sparse" or "too_dense"), and ``instruction`` (prompt-ready
        corrective text). Empty list means the lyrics are on-target.
    """
    counts: dict[str, int] = {}
    for block in lyrics:
        if not isinstance(block, dict):
            continue
        name = str(block.get("section_name", "")).strip()
        if not name:
            continue
        total = 0
        for line in block.get("lines", []) or []:
            if isinstance(line, dict):
                total += count_lyric_chars(str(line.get("text", "")))
            elif isinstance(line, str):
                total += count_lyric_chars(line)
        counts[name.lower()] = counts.get(name.lower(), 0) + total

    violations: list[dict] = []
    for t in targets:
        name = t["section_name"]
        current = counts.get(name.lower(), 0)
        if current < t["min_chars"]:
            deficit = t["min_chars"] - current
            violations.append({
                "section_name": name,
                "current_chars": current,
                "min_chars": t["min_chars"],
                "max_chars": t["max_chars"],
                "target_chars": t["target_chars"],
                "verdict": "too_sparse",
                "instruction": (
                    f"[{name}] too sparse: have {current} chars, "
                    f"need at least {t['min_chars']} "
                    f"(target {t['target_chars']}). "
                    f"ADD {deficit}+ characters."
                ),
            })
        elif current > t["max_chars"]:
            excess = current - t["max_chars"]
            violations.append({
                "section_name": name,
                "current_chars": current,
                "min_chars": t["min_chars"],
                "max_chars": t["max_chars"],
                "target_chars": t["target_chars"],
                "verdict": "too_dense",
                "instruction": (
                    f"[{name}] too dense: have {current} chars, "
                    f"max is {t['max_chars']} "
                    f"(target {t['target_chars']}). "
                    f"TRIM {excess}+ characters."
                ),
            })
    return violations


def format_char_count_violations(violations: list[dict]) -> str:
    """Render validate_section_char_counts output as a prompt block."""
    if not violations:
        return ""
    lines = [
        "CHARACTER-COUNT VIOLATIONS (fix these specifically — the "
        "previous output was out of range):",
    ]
    for v in violations:
        lines.append(f"  - {v['instruction']}")
    return "\n".join(lines)


__all__ = [
    "DENSITY_TARGETS",
    "LyricLineAnalysis",
    "SectionLyricStats",
    "LyricsAnalysisReport",
    "analyze_lyrics",
    "count_lyric_chars",
    "compute_section_char_targets",
    "format_lyrics_feedback_for_lyricist",
    "format_density_plan_for_lyricist",
    "format_char_count_plan_for_lyricist",
    "format_char_count_violations",
    "validate_section_char_counts",
]

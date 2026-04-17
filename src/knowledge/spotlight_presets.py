"""
Spotlight presets — per-section instrument activity matrices.

A spotlight plan tells the pipeline WHICH instruments play in each section
and WHICH are featured. Presets give the Orchestrator a starting template
for common genres/styles; the Orchestrator can adjust freely.

Resolution rules:
- "active": list[str] of instrument tokens OR the literal string "ALL"
  meaning "all instruments from the blueprint".
- "featured": subset of active. Featured instruments carry melodic hooks;
  others support.
- "silent" is derived = (all_instruments - active) at expand time.

Instrument tokens are matched case-insensitively against the blueprint's
instrument names (so "dizi" matches "Dizi", "dìzi", etc.).
"""

from __future__ import annotations

from loguru import logger

from src.music.score import SpotlightEntry


# ---------------------------------------------------------------------------
# Preset: MODERN_TRADITIONAL_FUSION
# ---------------------------------------------------------------------------
# Reference songs (赤伶, 牵丝戏, 虞兮叹, 武家坡2021): modern band carries
# intro/verse; traditional instruments enter at pre-chorus and dominate the
# chorus/climax; bridge pulls back to an intimate Erhu moment; outro fades
# with a fragile Dizi phrase.
MODERN_TRADITIONAL_FUSION: dict[str, dict] = {
    "intro": {
        "active": ["piano", "pad", "strings"],
        "featured": ["piano"],
    },
    "verse": {
        "active": ["piano", "bass", "cello", "drums", "pad", "strings"],
        "featured": ["piano"],
    },
    "pre_chorus": {
        "active": [
            "piano", "bass", "cello", "drums",
            "pad", "strings", "dizi",
        ],
        "featured": ["piano", "dizi"],
    },
    "chorus": {
        "active": "ALL",
        "featured": ["dizi", "erhu"],
    },
    "bridge": {
        "active": ["piano", "erhu", "pad", "strings", "cello"],
        "featured": ["erhu"],
    },
    "outro": {
        "active": ["dizi", "pad", "strings", "piano"],
        "featured": ["dizi"],
    },
}


# ---------------------------------------------------------------------------
# Preset: MODERN_POP_DEFAULT (fallback when no traditional instruments)
# ---------------------------------------------------------------------------
MODERN_POP_DEFAULT: dict[str, dict] = {
    "intro": {
        "active": ["piano", "pad", "strings"],
        "featured": ["piano"],
    },
    "verse": {
        "active": ["piano", "bass", "drums", "pad"],
        "featured": ["piano"],
    },
    "pre_chorus": {
        "active": ["piano", "bass", "drums", "pad", "strings"],
        "featured": ["piano"],
    },
    "chorus": {
        "active": "ALL",
        "featured": ["piano", "strings"],
    },
    "bridge": {
        "active": ["piano", "pad", "strings"],
        "featured": ["piano"],
    },
    "outro": {
        "active": ["piano", "pad"],
        "featured": ["piano"],
    },
}


PRESETS: dict[str, dict[str, dict]] = {
    "modern_traditional_fusion": MODERN_TRADITIONAL_FUSION,
    "modern_pop_default": MODERN_POP_DEFAULT,
}


# ---------------------------------------------------------------------------
# Fusion keyword detection
# ---------------------------------------------------------------------------
_FUSION_KEYWORDS_EN = (
    "fusion", "chinese", "traditional chinese", "east asian",
    "guzheng", "dizi", "erhu", "pipa", "yangqin", "xiao",
    "国风", "戏腔", "古风", "中国风",
)
_FUSION_KEYWORDS_ZH = ("国风", "戏腔", "古风", "中国风", "民乐")

_TRADITIONAL_TOKENS = {
    "dizi", "erhu", "guzheng", "pipa", "yangqin", "xiao",
    "笛子", "二胡", "古筝", "琵琶", "扬琴", "箫",
}


def _normalize(s: str) -> str:
    return s.strip().lower()


def detect_preset_from_request(
    description: str,
    instrument_names: list[str],
) -> str:
    """Pick a preset name based on free-text description + instrument list.

    Heuristic:
    - If any traditional instrument name appears in instruments list AND
      the description mentions modern/fusion keywords → fusion preset.
    - If traditional instruments are present at all → fusion preset.
    - Otherwise → modern_pop_default.
    """
    text = description.lower()
    inst_tokens = {_normalize(n) for n in instrument_names}
    has_traditional = bool(inst_tokens & _TRADITIONAL_TOKENS)
    fusion_hint = any(k in text for k in _FUSION_KEYWORDS_EN) or any(
        k in description for k in _FUSION_KEYWORDS_ZH
    )
    if has_traditional or fusion_hint:
        return "modern_traditional_fusion"
    return "modern_pop_default"


# ---------------------------------------------------------------------------
# Preset expansion
# ---------------------------------------------------------------------------
def _match_instrument(token: str, all_instruments: list[str]) -> str | None:
    """Match a preset token against the blueprint's actual instrument names.

    Case-insensitive; matches by substring so "piano" matches "Piano",
    "Grand Piano", etc.
    """
    needle = _normalize(token)
    for inst in all_instruments:
        norm = _normalize(inst)
        if norm == needle or needle in norm or norm in needle:
            return inst
    return None


def _resolve_active(
    active_spec,
    all_instruments: list[str],
) -> list[str]:
    if active_spec == "ALL":
        return list(all_instruments)
    if not isinstance(active_spec, (list, tuple)):
        logger.warning(
            f"[spotlight_presets] invalid 'active' value: {active_spec!r}"
        )
        return []
    resolved: list[str] = []
    for token in active_spec:
        matched = _match_instrument(token, all_instruments)
        if matched and matched not in resolved:
            resolved.append(matched)
    return resolved


def expand_preset(
    preset_name: str,
    all_instruments: list[str],
    section_names: list[str] | None = None,
) -> list[SpotlightEntry]:
    """Expand a named preset into concrete SpotlightEntry records.

    Args:
        preset_name: key in PRESETS. Unknown names fall back to
            modern_pop_default with a warning.
        all_instruments: the blueprint's instrument names. Used to resolve
            "ALL" and to fill 'silent' lists.
        section_names: optional list of section names the Orchestrator used.
            If provided, entries are emitted only for these sections (in the
            same order). Preset sections missing from the list are dropped;
            extra sections not in the preset get an empty entry.
            If None, all preset sections are emitted in preset order.

    Returns:
        A list of SpotlightEntry, one per resolved section. 'silent' is
        computed as (all_instruments - active) for each section.
    """
    preset = PRESETS.get(preset_name)
    if preset is None:
        logger.warning(
            f"[spotlight_presets] unknown preset '{preset_name}', "
            "falling back to modern_pop_default"
        )
        preset = MODERN_POP_DEFAULT

    all_set = list(dict.fromkeys(all_instruments))  # de-dupe, preserve order

    if section_names is None:
        target_sections = list(preset.keys())
    else:
        target_sections = list(section_names)

    entries: list[SpotlightEntry] = []
    for sec_name in target_sections:
        spec = preset.get(sec_name)
        if spec is None:
            entries.append(
                SpotlightEntry(
                    section=sec_name,
                    active=list(all_set),
                    featured=[],
                    silent=[],
                )
            )
            continue
        active = _resolve_active(spec.get("active", []), all_set)
        featured = _resolve_active(spec.get("featured", []), all_set)
        # keep featured ⊆ active
        featured = [i for i in featured if i in active]
        silent = [i for i in all_set if i not in active]
        entries.append(
            SpotlightEntry(
                section=sec_name,
                active=active,
                featured=featured,
                silent=silent,
            )
        )
    return entries


def build_default_all_active(
    all_instruments: list[str],
    section_names: list[str],
) -> list[SpotlightEntry]:
    """Backward-compat fallback: every instrument active everywhere,
    no one featured. Used when the Orchestrator omits spotlight_plan and
    the piece doesn't fit any preset."""
    all_set = list(dict.fromkeys(all_instruments))
    return [
        SpotlightEntry(
            section=s, active=list(all_set), featured=[], silent=[],
        )
        for s in section_names
    ]


def preset_summary_for_prompt(preset_name: str) -> str:
    """Return a compact JSON-ish description of a preset for prompt injection."""
    preset = PRESETS.get(preset_name)
    if preset is None:
        return f"(unknown preset: {preset_name})"
    lines = [f"Preset: {preset_name}"]
    for sec_name, spec in preset.items():
        active = spec.get("active", [])
        featured = spec.get("featured", [])
        active_str = "ALL" if active == "ALL" else ", ".join(active)
        featured_str = ", ".join(featured) if featured else "-"
        lines.append(
            f"  {sec_name}: active=[{active_str}] featured=[{featured_str}]"
        )
    return "\n".join(lines)

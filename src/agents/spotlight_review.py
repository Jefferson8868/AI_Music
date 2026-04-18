"""
Spotlight-proposal review parsing.

Pure, dependency-free helper extracted from ``pipeline.py`` so it can be
unit-tested without the full agent stack.

Context — Bug A: the pipeline used to route mid-confidence spotlight
proposals through ``OrchestratorAgent``, which replaces every response
with ``"[Orchestrator] Blueprint created:\\n```json\\n{...}\\n```"``. That
wrapper hid the LLM's real ``{"decisions": [...]}`` verdict, so the
parser only ever saw blueprint JSON with no ``decisions`` key and every
mid-confidence proposal was silently rejected. The parser now lives here
and is called after a direct LLM roundtrip that doesn't rewrite content.
"""

from __future__ import annotations

import json
import re


def _find_json_objects(text: str) -> list[dict]:
    """Extract every top-level JSON object embedded in ``text``.

    Tolerates fenced ``\u0060\u0060\u0060json`` blocks and prose around the JSON.
    """
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```", "", text)
    results: list[dict] = []
    i = 0
    while i < len(text):
        if text[i] == "{":
            depth, start = 0, i
            for j in range(i, len(text)):
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            obj = json.loads(text[start:j + 1])
                            if isinstance(obj, dict):
                                results.append(obj)
                        except json.JSONDecodeError:
                            pass
                        i = j + 1
                        break
            else:
                i += 1
        else:
            i += 1
    return results


# ---------------------------------------------------------------------------
# Drum / bass instrument-name detection (Bug B)
#
# Spotlight presets use short tokens ("drums", "bass") that are resolved
# by spotlight_presets._match_instrument to the blueprint's canonical
# names ("Cinematic Drums", "Synth Bass"). Phase 3.5 gating must match
# those canonical names, not just the short tokens — otherwise DrumAgent
# and BassAgent are silently skipped.
# ---------------------------------------------------------------------------

DRUM_TOKENS: frozenset[str] = frozenset({
    "drums", "drum", "drum kit", "percussion", "perc",
})

BASS_TOKENS: frozenset[str] = frozenset({
    "bass", "electric bass", "bass guitar", "synth bass",
    "e-bass", "e bass", "upright bass", "acoustic bass",
})


def _contains_token(name: str, tokens: frozenset[str]) -> bool:
    """Return True if ``name`` contains any token as a whole word.

    Whole-word match (regex ``\\b...\\b``) is used so "Bassoon" doesn't
    accidentally register as bass, while "Electric Bass" and "E-Bass"
    still do. Multi-word tokens ("drum kit") are matched with whitespace
    collapsed and internal spaces treated as flexible whitespace.
    """
    if not name:
        return False
    haystack = name.lower().strip()
    for token in tokens:
        # Build a whole-word regex; internal spaces become \s+ so that
        # "drum kit" can match "Drum  Kit" etc.
        pattern = r"\b" + r"\s+".join(re.escape(p) for p in token.split()) \
            + r"\b"
        if re.search(pattern, haystack):
            return True
    return False


def match_drum_token(name: str) -> bool:
    """Whole-word substring check against DRUM_TOKENS."""
    return _contains_token(name, DRUM_TOKENS)


def match_bass_token(name: str) -> bool:
    """Whole-word substring check against BASS_TOKENS.

    Excludes false positives like "Bassoon" via the whole-word boundary.
    """
    return _contains_token(name, BASS_TOKENS)


def parse_spotlight_review_decisions(
    review_resp: str, n_proposals: int,
) -> set[int]:
    """Return the set of accepted proposal indices.

    Scans every JSON object in ``review_resp`` for a ``decisions`` array
    of ``{index, accept}`` entries. Returns indices whose ``accept`` is
    truthy and whose ``index`` is within ``[0, n_proposals)``. A response
    with no valid decisions (e.g. a blueprint JSON from an agent wrapper)
    yields an empty set rather than crashing.
    """
    accepted: set[int] = set()
    for data in _find_json_objects(review_resp):
        decisions = data.get("decisions", [])
        if not isinstance(decisions, list):
            continue
        for dec in decisions:
            if not isinstance(dec, dict):
                continue
            idx = dec.get("index")
            if not isinstance(idx, int):
                continue
            if 0 <= idx < n_proposals and dec.get("accept"):
                accepted.add(idx)
    return accepted

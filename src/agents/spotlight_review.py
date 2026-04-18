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

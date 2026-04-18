"""
Tests for Bug A fix — spotlight-proposal review parsing.

The pipeline's ``_review_and_apply_proposals`` used to route
mid-confidence proposals through ``OrchestratorAgent``, which always
wraps responses as ``[Orchestrator] Blueprint created:\\n```json\\n...``.
That wrapper replaces the LLM's ``{"decisions": [...]}`` verdict with a
blueprint JSON, so every mid-confidence proposal was silently rejected
and the message history got polluted with fake "Untitled" blueprints.

These tests cover the extracted ``parse_spotlight_review_decisions``
helper — the pure-function version of the parsing logic.
"""

from __future__ import annotations

from src.agents.spotlight_review import parse_spotlight_review_decisions


def test_parses_simple_accept_decisions():
    resp = """Here is my review:
    ```json
    {"decisions": [
        {"index": 0, "accept": true, "note": "ok"},
        {"index": 1, "accept": false, "note": "too busy"}
    ]}
    ```"""
    assert parse_spotlight_review_decisions(resp, 2) == {0}


def test_accepts_all_truthy_indices():
    resp = '{"decisions": [{"index": 0, "accept": true},' \
           '{"index": 1, "accept": true}]}'
    assert parse_spotlight_review_decisions(resp, 2) == {0, 1}


def test_drops_out_of_range_indices():
    resp = '{"decisions": [{"index": 0, "accept": true},' \
           '{"index": 5, "accept": true}]}'
    # Only 2 proposals, index 5 is bogus.
    assert parse_spotlight_review_decisions(resp, 2) == {0}


def test_non_integer_index_ignored():
    resp = '{"decisions": [{"index": "zero", "accept": true}]}'
    assert parse_spotlight_review_decisions(resp, 3) == set()


def test_non_dict_decisions_ignored():
    resp = '{"decisions": ["accept", "reject"]}'
    assert parse_spotlight_review_decisions(resp, 2) == set()


def test_decisions_not_a_list_ignored():
    resp = '{"decisions": "accept"}'
    assert parse_spotlight_review_decisions(resp, 1) == set()


def test_orchestrator_wrapped_blueprint_returns_empty():
    """This is the Bug A reproduction.

    If the review were routed through OrchestratorAgent, its output would
    look like this: a blueprint JSON inside the familiar marker. No
    ``decisions`` key, so the parser must return an empty set (and the
    pipeline must drop all mid-confidence proposals) — not crash.
    """
    resp = (
        "[Orchestrator] Blueprint created:\n"
        "```json\n"
        '{"title": "Untitled", "key": "C", "scale_type": "major",\n'
        ' "tempo": 120, "sections": [], "instruments": []}\n'
        "```\n"
    )
    assert parse_spotlight_review_decisions(resp, 3) == set()


def test_no_json_at_all_returns_empty():
    resp = "I think proposal 0 is fine, but proposal 1 is not."
    assert parse_spotlight_review_decisions(resp, 2) == set()


def test_accept_missing_defaults_to_reject():
    resp = '{"decisions": [{"index": 0}]}'
    # No "accept" key → treated as falsy → not accepted.
    assert parse_spotlight_review_decisions(resp, 1) == set()


def test_multiple_json_blocks_all_scanned():
    resp = (
        'noise {"other": 1} more noise\n'
        '```json\n{"decisions": [{"index": 0, "accept": true}]}\n```'
    )
    assert parse_spotlight_review_decisions(resp, 1) == {0}

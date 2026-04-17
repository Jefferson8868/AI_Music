#!/usr/bin/env python3
"""
Generate Western modern chart-style pop (Taylor Swift / Ariana Grande *inspired*
vibes: bright hooks, big chorus, contemporary harmony).

No Eastern instruments — only Western / GM-friendly orchestration.

Usage:
  python scripts/generate_western_pop.py
  MG_API_URL=http://localhost:8000 python scripts/generate_western_pop.py --timeout 1200

Requires: requests
"""

from __future__ import annotations

import argparse
import json
import os
import sys

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)


DESCRIPTION = """
Western modern radio pop: catchy verse, lift in pre-chorus, anthemic chorus with
a memorable melodic hook. Think contemporary female-led chart pop (bright, confident,
romantic or self-empowering mood) — NOT cinematic Chinese folk and NOT guzheng/erhu/dizi.

HARMONY & GROOVE
- Major or bright pop harmony; I–V–vi–IV or similar modern progressions; extensions OK.
- 4/4, danceable backbeat; tempo ~100–112 BPM feel; syncopation in verse OK.
- Pre-chorus should build energy; chorus is the peak (biggest drums energy, widest chords).

ORCHESTRATION (Western only)
- Lead melody: clear pop vocal line (represented as a bright lead instrument — use Piano
  or Violin for the main hook so it reads in MIDI).
- Chords: Piano (rhythmic comp, not sparse whole-note blocks every bar).
- Bass: walking or root–fifth pop bass on Cello or Contrabass (low register, supportive).
- Pad / lift: Strings ensemble for chorus width.
- Optional sparkle: subtle Flute or high Piano doubles on chorus hook (light, not busy).

AVOID
- Pentatonic “Chinese garden” clichés, traditional Asian scales as the default, or
  Eastern solo instruments.
- One-note-per-section accompaniment — every track should have musical motion.

SECTIONS
- intro (short, modern), verse, pre-chorus, chorus (climax), bridge (harmonic twist),
  outro (fade or tag).
""".strip()


def build_request_payload(
    *,
    include_lyrics: bool,
    lyric_language: str,
    bars_per_section: int,
) -> dict:
    return {
        "request": {
            "description": DESCRIPTION,
            "genre": "modern_western_pop",
            "mood": "bright_confident_romantic",
            "tempo": 108,
            "key": "G",
            "scale_type": "major",
            "time_signature": [4, 4],
            "sections": [
                "intro",
                "verse",
                "pre_chorus",
                "chorus",
                "bridge",
                "outro",
            ],
            "bars_per_section": bars_per_section,
            "include_lyrics": include_lyrics,
            "lyric_language": lyric_language,
            "lyric_theme": "late-night drive, finally saying what you mean, summer lights",
            "reference_style": "Contemporary Western chart pop (catchy hooks, big chorus)",
            "instruments": [
                {"name": "Piano", "role": "lead"},
                {"name": "Violin", "role": "counter-melody"},
                {"name": "Acoustic Guitar", "role": "chords"},
                {"name": "Strings", "role": "pad"},
                {"name": "Cello", "role": "bass"},
            ],
        }
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="POST a Western modern-pop generation job to the Music Generator API.",
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("MG_API_URL", "http://localhost:8000"),
        help="API base URL (default: MG_API_URL or http://localhost:8000)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=1200,
        help="HTTP timeout in seconds (default: 1200)",
    )
    parser.add_argument(
        "--bars-per-section",
        type=int,
        default=4,
        help="Bars per section hint (default: 4)",
    )
    parser.add_argument(
        "--lyrics",
        action="store_true",
        help="Request English lyrics (default: off)",
    )
    parser.add_argument(
        "--lyric-lang",
        default="en",
        help="Lyric language code (default: en)",
    )
    args = parser.parse_args()

    endpoint = args.url.rstrip("/") + "/api/generate"
    body = build_request_payload(
        include_lyrics=args.lyrics,
        lyric_language=args.lyric_lang,
        bars_per_section=args.bars_per_section,
    )

    print("Generating Western modern pop (may take several minutes)...\n")
    print(f"POST {endpoint}\n")

    response = requests.post(endpoint, json=body, timeout=args.timeout)
    response.raise_for_status()
    result = response.json()

    summary = result.get("summary", {})
    midi_path = summary.get("midi_path")
    snapshots = summary.get("snapshots", [])

    print(f"Status: {result.get('status')}")
    print(f"Final MIDI: {midi_path or 'none'}")

    if snapshots:
        print(f"\n--- Round Snapshots ({len(snapshots)}) ---")
        for i, snap in enumerate(snapshots):
            label = "Magenta draft" if "magenta" in snap.lower() else f"Round {i}"
            print(f"  [{label}] {snap}")

    slim = {k: v for k, v in summary.items() if k != "snapshots"}
    print(f"\nSummary:\n{json.dumps(slim, indent=2)}")

    messages = result.get("messages", [])
    print(f"\n--- Agent Messages ({len(messages)}) ---")
    for i, msg in enumerate(messages):
        content = msg.get("content", "")
        preview = content[:200].replace("\n", " ")
        print(f"\n[{i + 1}] {msg.get('source')}: {preview}...")


if __name__ == "__main__":
    main()

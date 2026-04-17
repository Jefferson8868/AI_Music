#!/usr/bin/env python3
"""
Generate a modern + traditional Chinese fusion song in the style of
赤伶 (Chì Líng) / 牵丝戏 (Qiān Sī Xì) / 虞兮叹 / 武家坡2021.

Core aesthetic
--------------
- Modern band (piano, cello, strings, pad) carries the intro, verse,
  and bridge.
- Traditional solo instruments (Dizi, Erhu, Guzheng) ENTER at the
  pre-chorus as a signal of the approaching climax and DOMINATE the
  chorus with ornamented, lyrical phrases.
- Bridge is an intimate Erhu moment; outro fades with a fragile Dizi.
- Pentatonic framework (Gong-Shang-Jue-Zhi-Yu) on top of Western chord
  movement (e.g. vi–IV–I–V in Am).
- Every traditional instrument plays with characteristic ornaments:
  dizi breath_swell / flutter, erhu vibrato_deep / slide_up_from,
  guzheng glissando on chorus runs.
- Featured instruments carry long, sustained, ornamented lines; they
  are NOT note-by-note.

This script hits the Music Generator API (the FastAPI server in
src/api/routes.py). Start the server first:
    python -m src.main     # or: uvicorn src.api.routes:app

Usage
-----
  python scripts/generate_modern_traditional_fusion.py
  python scripts/generate_modern_traditional_fusion.py --lyrics
  MG_API_URL=http://localhost:8000 \\
  python scripts/generate_modern_traditional_fusion.py --timeout 1800

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
Modern + traditional Chinese fusion pop ballad (国风 fusion),
reference songs: 赤伶 (Chì Líng), 牵丝戏 (Qiān Sī Xì), 虞兮叹, 武家坡2021.

OVERALL FEELING
- A modern band sets the emotional floor; traditional Chinese solo
  instruments enter late and CLIMB — they do NOT decorate every bar.
- Intimate verse, rising pre-chorus, cinematic chorus with sustained
  solo lines, reflective bridge, fragile outro.
- Tempo around 70–82 BPM; 4/4; key Am (natural minor) with pentatonic
  colouring (A-C-D-E-G as the melodic skeleton).

ORCHESTRATION & SPOTLIGHT (critical — follow exactly)
- [intro]      Piano + Pad only. Sparse.
- [verse]      Piano (lead), Cello (bass), light Pad. No Dizi/Erhu/
               Guzheng yet. Piano plays a rhythmic accompaniment
               pattern, NOT isolated quarter notes. Cello walks the
               bass line continuously.
- [pre_chorus] Add DIZI (counter-melody) as a rising signal.
               Strings enter as pad swell.
- [chorus]     ALL instruments active. DIZI + ERHU are FEATURED —
               they carry long sustained melodic lines with vibrato,
               slides, breath swells. Guzheng adds pentatonic
               sweeping glissandi. Piano and Cello move to supportive
               role.
- [bridge]     Pull back. Erhu solo over piano + pad only. Erhu is
               FEATURED — long vibrato-deep lines, vocal-like sighs.
- [outro]      Dizi + piano + pad fade. Dizi is FEATURED with
               breath_fade, continuously voiced as it exits.

CONTINUITY (non-featured instruments must NOT sound like one note
per bar)
- Piano: continuous rhythmic comp (arpeggios or 8th-note chords).
- Cello: continuous bass line with passing tones.
- Strings / Pad: sustained chord beds.
- Dizi: continuous melodic breath phrase when active (no staccato
  gaps).
- Erhu: bow each phrase across the full section; no isolated
  single-beat notes.
- Guzheng: plucked but phrases grouped (cascading runs / broken
  chords), not one note per bar.

ORNAMENTS (the performance renderer turns these into MIDI CC /
pitch-bend)
- Dizi: breath_swell on entrances, flutter on long sustains, overblow
  on chorus climaxes.
- Erhu: vibrato_deep on every held note, slide_up_from:2 on
  ascending steps, bend_dip on climax notes.
- Guzheng: tremolo_rapid on chorus pedal tones, glissando_from on
  ascending runs.
- Piano (support): legato_to_next on arpeggio runs.

AVOID
- Bare ascending/descending major or pentatonic scales.
- Every instrument playing every section with equal density (that
  makes it sound like a symphony, not a song).
- Dizi or Erhu appearing in the intro or verse — they MUST be saved
  for pre-chorus / chorus / bridge / outro.
- Traditional instruments playing note-by-note; they're voices that
  breathe and bow.

LYRICS
- Chinese (zh), one character per melody note in verse and chorus.
- Theme: quiet longing meeting fierce resolve; imagery of 月 (moon),
  烟雨 (misty rain), 戏台 (opera stage), 丝线 (silk thread).
- Verse: intimate, narrative. Chorus: large, declarative, repeats
  the hook. Bridge: a turning point.
""".strip()


def build_request_payload(
    *,
    include_lyrics: bool,
    lyric_language: str,
    bars_per_section: int,
    tempo: int,
) -> dict:
    return {
        "request": {
            "description": DESCRIPTION,
            "genre": "chinese_modern_fusion",
            "mood": "longing_climactic_bittersweet",
            "tempo": tempo,
            "key": "A",
            "scale_type": "chinese_pentatonic_minor",
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
            "lyric_theme": (
                "戏台上的一生一世 — 月下烟雨里的一念执着，"
                "丝线牵着旧故事，灯火摇曳间忽然看清了自己。"
            ),
            "reference_style": (
                "Chinese modern-traditional fusion ballad — Chi Ling, "
                "Qian Si Xi, Yu Xi Tan, Wu Jia Po 2021"
            ),
            # Five modern + three traditional = 8 instruments total.
            # The spotlight plan (Orchestrator + our preset) controls
            # who plays in which section.
            "instruments": [
                {"name": "Piano",    "role": "chords"},
                {"name": "Cello",    "role": "bass"},
                {"name": "Strings",  "role": "pad"},
                {"name": "Pad",      "role": "texture"},
                {"name": "Dizi",     "role": "lead"},
                {"name": "Erhu",     "role": "counter-melody"},
                {"name": "Guzheng",  "role": "texture"},
            ],
        }
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "POST a modern-traditional Chinese fusion generation "
            "job to the Music Generator API."
        ),
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("MG_API_URL", "http://localhost:8000"),
        help=(
            "API base URL (default: MG_API_URL or "
            "http://localhost:8000)"
        ),
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="HTTP timeout in seconds (default: 1800)",
    )
    parser.add_argument(
        "--bars-per-section",
        type=int,
        default=8,
        help=(
            "Bars per section hint (default: 8 — gives featured "
            "instruments room to breathe)"
        ),
    )
    parser.add_argument(
        "--tempo",
        type=int,
        default=76,
        help="Tempo in BPM (default: 76 — matches ballad feel)",
    )
    parser.add_argument(
        "--lyrics",
        action="store_true",
        default=True,
        help="Request Chinese lyrics (default: on)",
    )
    parser.add_argument(
        "--no-lyrics",
        dest="lyrics",
        action="store_false",
        help="Disable lyrics",
    )
    parser.add_argument(
        "--lyric-lang",
        default="zh",
        help="Lyric language code (default: zh)",
    )
    parser.add_argument(
        "--out-json",
        default=None,
        help="Optional path to save the full JSON response",
    )
    args = parser.parse_args()

    endpoint = args.url.rstrip("/") + "/api/generate"
    body = build_request_payload(
        include_lyrics=args.lyrics,
        lyric_language=args.lyric_lang,
        bars_per_section=args.bars_per_section,
        tempo=args.tempo,
    )

    print("=" * 72)
    print("Modern + Traditional Chinese Fusion Generator")
    print("=" * 72)
    print(
        f"  tempo={args.tempo} bpm    "
        f"bars/section={args.bars_per_section}    "
        f"lyrics={'zh' if args.lyrics else 'off'}"
    )
    print(f"  POST {endpoint}")
    print()
    print("This may take several minutes (LLM + performance render).")
    print()

    try:
        response = requests.post(endpoint, json=body, timeout=args.timeout)
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        response.raise_for_status()
    except requests.HTTPError as e:
        print(f"HTTP error: {e}\n{response.text[:2000]}", file=sys.stderr)
        sys.exit(2)

    result = response.json()

    if args.out_json:
        with open(args.out_json, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
        print(f"Full response saved to: {args.out_json}")

    summary = result.get("summary", {})
    midi_path = summary.get("midi_path")
    snapshots = summary.get("snapshots", [])

    print(f"Status:      {result.get('status')}")
    print(f"Final MIDI:  {midi_path or '(none)'}")
    print(f"Completed:   {summary.get('completed')}")
    if summary.get("error"):
        print(f"Error:       {summary['error']}")

    if snapshots:
        print(f"\nRound snapshots ({len(snapshots)}):")
        for i, snap in enumerate(snapshots):
            label = (
                "Magenta draft" if "magenta" in snap.lower()
                else f"Round {i}"
            )
            print(f"  [{label}] {snap}")

    agents = summary.get("agents_involved", [])
    if agents:
        print(f"\nAgents: {', '.join(agents)}")

    messages = result.get("messages", [])
    if messages:
        print(f"\nAgent messages ({len(messages)} total, first 3 previewed):")
        for i, msg in enumerate(messages[:3]):
            content = msg.get("content", "")
            preview = content[:180].replace("\n", " ")
            print(f"  [{i + 1}] {msg.get('source')}: {preview}...")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Generate a 赤伶 (Chì Líng) style Guofeng opera-pop ballad.

Why a dedicated script (vs. generate_modern_traditional_fusion.py)
-----------------------------------------------------------------
The fusion script is a general preset. This one is *hyperparameter-tuned*
to one reference song family: 赤伶 / 探窗 / 牵丝戏 / 虞兮叹 / 武家坡2021 —
the modern 戏腔 (operatic falsetto) pop-ballad wave. Differences from
the generic fusion preset:

  * Key:        E minor (赤伶 actual key) instead of A minor — sits in
                erhu's open-string register and gives the chorus a
                higher, more theatrical 戏腔 feel.
  * Tempo:      82 BPM (赤伶 ≈ 80–84) instead of 76 — enough rubato
                room for vocals, fast enough for the chorus to feel
                like a climb rather than a dirge.
  * Harmony:    explicit 赤伶-style progression hint in the description
                (i–v–VI–III–iv–V7–i) so the Composer doesn't default
                to vi-IV-I-V pop chords.
  * Spotlight:  Dizi and Erhu ALTERNATE (not harmonize) between phrases
                on the chorus — authentic 戏曲 technique.
  * Transitions: explicit riser + reverse_cymbal + impact on the
                pre_chorus → chorus boundary.  Snare roll accel over
                the final bar of the pre-chorus.  These are picked up
                by TransitionAgent and realized as MIDI + .wav stems
                (see assets/transitions/).
  * Engines:    defaults `MG_REFERENCE_ENGINES` to a multi-engine
                fanout so the Composer sees 3–4 alternative drafts
                — NOT just Magenta, which is the pipeline's weakest
                engine for this genre and is also the only one
                currently failing with 500 errors.

Prereq — start the API server first
-----------------------------------
  python -m src.main    # or: uvicorn src.api.routes:app

Usage
-----
  # Default: multi-engine reference fanout + audio render + vocals + mix
  python scripts/generate_chi_ling_style.py

  # Bypass Magenta entirely (recommended when Magenta microservice is
  # down — pipeline falls back to NullEngine for missing engines):
  MG_REFERENCE_ENGINES="musiclang,composers_assistant,mmt,figaro" \\
  python scripts/generate_chi_ling_style.py

  # Only keep engines you actually have installed:
  MG_REFERENCE_ENGINES="musiclang,null" \\
  python scripts/generate_chi_ling_style.py

  # Different API host:
  MG_API_URL=http://localhost:8000 \\
  python scripts/generate_chi_ling_style.py --timeout 2400

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


# ---------------------------------------------------------------------------
# The tuned DESCRIPTION — fed to the Orchestrator LLM as natural-language
# spec.  Every paragraph is load-bearing; do NOT shorten casually.
# ---------------------------------------------------------------------------

DESCRIPTION = """
赤伶 (Chì Líng) style Guofeng pop ballad — modern band + Chinese
traditional solo instruments + 戏腔 (operatic falsetto) vocal aesthetic.
Reference songs: 赤伶 (HITA / 李袁杰), 探窗, 牵丝戏, 虞兮叹, 武家坡2021.

EMOTIONAL ARC (non-negotiable)
- Intro: fragile, empty, dust-in-a-stage-light.  Piano + Pad only.
- Verse: intimate confessional narration.  Piano lead, cello walking.
- Pre-chorus: tension climbing, tradition enters (Dizi counter-line).
- Chorus: CLIMACTIC — 戏腔 vocal soars, erhu takes lead line, cinematic
  drums enter on the downbeat, guzheng cascades color every 2 bars.
- Bridge: collapse back to intimacy.  Erhu solo over piano + pad.  No
  drums.  This is the emotional pivot, not a second chorus.
- Outro: dizi breath_fade into silence.  Spare.

KEY, TEMPO, METER
- Key: E natural minor (the 赤伶 home key).  Melodic material uses the
  Chinese pentatonic-minor framework (E-G-A-B-D) on top of a Western
  minor-key harmony bed — i.e. the melody is pentatonic but chords
  contain the missing scale degrees (F# in ii°, D# in V7).
- Tempo: 82 BPM, 4/4.  Feel: ballad with rubato room, NOT a dirge.
- Chorus should feel a hair behind the beat on the vocal; strings and
  erhu should sit AHEAD of the beat by 3–8ms (the humanizer handles
  this).

HARMONIC PROGRESSION (explicit — don't default to vi-IV-I-V pop)
- Verse (2x 4-bar phrase):
      Em — Bm — C — G       (i – v – VI – III)
      Em — Am — B7 — Em     (i – iv – V7 – i)
- Pre-chorus (4 bars, accelerating tension):
      Am — Bm — C — D       (iv – v – VI – VII — classic Chinese opera
                              "climbing" progression used in 赤伶's
                              pre-chorus to lift into the hook)
- Chorus (2x 4-bar phrase, same as verse but thicker voicings + the
  B7 cadence resolved up an octave for lift):
      Em — Bm — C — G
      Am — B7 — Em — Em/G   (final Em/G opens the phrase back to the
                              next chorus pass or to the bridge)
- Bridge (4 bars, in the relative major for breathing room):
      G — D/F# — Em — B7    (III – VII – i – V7, then back to Em chorus)
- Outro: Em sus2 held, drifting to silence.

ORCHESTRATION & SPOTLIGHT PLAN (critical — follow EXACTLY; this is
the biggest lever for "song vs. symphony")
- [intro]       Piano (lead) + Pad (sustained drone).  8 bars.
                NO drums.  NO traditional instruments.  Negative space
                is the point.  Pad volume ~ -18 dBFS.
- [verse]       Piano (rhythmic comp: broken arpeggios in 8ths, NOT
                block chords), Cello (walking bass, one note per beat
                with passing tones), light Pad.  Still no Dizi/Erhu/
                Guzheng.  No drums yet (modern 赤伶 covers hold drums
                back to the chorus for contrast).
- [pre_chorus]  Enter DIZI with a rising counter-melody (call-and-
                response with the vocal's lyric phrase endings).
                Strings swell in as a wide sustained pad.  Add a
                snare_roll_accel on the LAST bar to telegraph the
                chorus impact.
- [chorus]      FULL ENSEMBLE.  Featured: ERHU (phrase 1) + DIZI
                (phrase 2) ALTERNATING — do NOT double them; they
                trade 2-bar phrases like operatic call-and-response.
                GUZHENG sweeps a descending pentatonic glissando
                every 2 bars as color.  Cinematic Drums enter on bar
                1 downbeat with a kick+crash impact.  Electric Bass
                locks to the kick pattern.  Piano shifts to block
                8th-note chords (supportive).  Strings carry the
                wide pad underneath.
- [bridge]     PULL BACK.  Erhu SOLO (featured) over Piano arpeggios
                + low Pad.  NO drums, NO bass, NO guzheng, NO dizi.
                This is the emotional reset.  Erhu uses vibrato_deep
                + slide_up_from:2 on every phrase start + bend_dip on
                climax notes.
- [outro]      Dizi (featured) + Piano (slow arpeggio) + Pad (fading
                drone).  Dizi uses breath_fade across the final 4
                bars.  NO drums, NO bass, NO erhu.

CONTINUITY RULES (non-featured instruments must breathe — not one
note per bar)
- Piano: continuous 8th-note comp in verse, block 8ths in chorus.
- Cello: continuous walking bass with passing tones; root on bar 1
  of each chord, approach tones on beats 3–4.
- Strings / Pad: sustained chord beds, one chord per bar minimum.
- Dizi: continuous breath phrases when active; NO isolated single-
  beat notes.
- Erhu: bow each phrase across the full section; use portamento to
  connect consecutive same-phrase notes.
- Guzheng: cascading runs + broken chords; NOT one pluck per bar.
- Electric Bass: locked to kick pattern on chorus; silent elsewhere.
- Cinematic Drums: chorus only; kick on beats 1 & 3, snare on 2 & 4
  with a ghost on the "and" of 3; hats drive 16ths.

ORNAMENTS (the performance renderer turns these into MIDI
pitch-bend / CC automation — use the names verbatim)
- Dizi: breath_swell on entrances, flutter on long sustains,
  overblow on chorus climax notes, breath_fade on the outro.
- Erhu: vibrato_deep on every held note ≥ 1 beat, slide_up_from:2
  on ascending phrase starts, bend_dip on climax notes, portamento
  between consecutive same-phrase notes.
- Guzheng: glissando_from on ascending runs, tremolo_rapid on
  pedal-tone cadences.
- Piano (support role): legato_to_next on arpeggio runs.
- Cello: vibrato_light on held root notes.

TRANSITION FX (TransitionAgent will schedule these; we're hinting
what boundary recipes to use)
- intro → verse:        soft piano tail + low riser (riser_short).
- verse → pre_chorus:   short reverse_cymbal + sparse tom fill.
- pre_chorus → chorus:  FULL cinematic entry — riser_8beat + reverse_
                        cymbal_long + impact_deep on the one + sub_drop
                        + snare_roll_accel_1bar over the final bar.
                        This is the song's biggest moment.
- chorus → bridge:      downlifter_filter + kick drop (drums cut).
- bridge → outro:       soft impact_crisp + dizi-breath fade.

LYRICS (戏腔 / operatic vernacular — theme is the mask of a stage
life concealing personal grief, the 赤伶 ("red opera performer")
archetype)
- Chinese (zh), one character per melody note in verse and most of
  chorus.  Chorus HOOK syllables may extend across 2–3 notes
  (melisma) to carry the 戏腔 lift.
- Tone-melody conflicts should be minimized on the hook — the
  lyricist should check that ascending melody lines carry 阴平 (1st
  tone) or 阳平 (2nd tone) characters, not 去声 (4th).
- Verse: intimate / narrative.  "台上台下" (on stage / off stage)
  imagery, "一曲 / 一梦" (one song / one dream).
- Chorus: the archetype declaration.  Hook should land on a single
  Chinese character held over 3–4 beats ("梦", "戏", "空", "红尘").
- Bridge: turn — the performer steps out of the role and speaks
  honestly for the first time.

AVOID (common failure modes)
- Every instrument playing every section with equal density →
  this is what makes it sound like a symphony, not a song.
- Dizi or Erhu appearing in intro or verse → they MUST be saved
  for pre-chorus / chorus / bridge / outro.
- Traditional instruments playing note-by-note → they are voices
  that breathe, bow, and glide.
- Chorus without a cinematic entry transition → the song will feel
  like it doesn't know it reached the chorus.
- Western major-key pop progressions (I-V-vi-IV) → this is not a
  Western pop song; the progression IS the 赤伶 sound.
- Drums in bridge → the bridge is the emotional reset.  No drums.
""".strip()


# ---------------------------------------------------------------------------
# Tuned hyperparameters — every value here was chosen for 赤伶 fidelity.
# ---------------------------------------------------------------------------

# Tempo: 82 BPM.  Real 赤伶 clocks at 80–84.  76 (the generic fusion
# script's default) is too slow — the pre-chorus loses its climb.
DEFAULT_TEMPO = 82

# Key: E minor.  Real 赤伶 sits in Em; it also puts the erhu's melodic
# range on its open strings (D–A), letting the open-string resonance
# carry the long sustains.
DEFAULT_KEY = "E"
DEFAULT_SCALE = "chinese_pentatonic_minor"

# Bars per section: 8 is a flat int in the API — can't vary per section.
# 8 gives chorus and verse both room to breathe; Composer can emit
# 4-bar pre_chorus + 4-bar bridge by using half the material.
DEFAULT_BARS_PER_SECTION = 8

# Sections: explicit — no "verse, chorus, verse, chorus" loop because
# 赤伶 is a through-composed arc with ONE verse-chorus pair, bridge,
# and reflective outro.  Two verse-chorus pairs double the length
# without adding emotional progression.
DEFAULT_SECTIONS = [
    "intro",
    "verse",
    "pre_chorus",
    "chorus",
    "bridge",
    "outro",
]

# Instruments: 8 total.  Ordered so that the Orchestrator's default
# "first = lead" heuristic gets the right hint (Piano leads verse,
# Erhu leads chorus, Dizi leads outro).
DEFAULT_INSTRUMENTS: list[dict[str, str]] = [
    # Modern band — the emotional floor.
    {"name": "Piano",            "role": "chords"},
    {"name": "Cello",            "role": "bass"},
    {"name": "Strings",          "role": "pad"},
    {"name": "Pad",              "role": "texture"},
    {"name": "Electric Bass",    "role": "bass"},
    {"name": "Cinematic Drums",  "role": "drums"},
    # Traditional solo instruments — featured on pre_chorus onwards.
    {"name": "Erhu",             "role": "lead"},
    {"name": "Dizi",             "role": "counter-melody"},
    {"name": "Guzheng",          "role": "texture"},
]

DEFAULT_LYRIC_THEME = (
    "台上台下两样人生 — 红妆戏裳里藏着真心，"
    "一曲梦回旧时月，灯火阑珊处方见戏外真我。"
    "主题：戏子无情而情最深，一梦红尘终成戏中人。"
)

DEFAULT_REFERENCE_STYLE = (
    "赤伶-style Chinese opera-pop ballad — HITA 赤伶, 探窗, "
    "牵丝戏, 虞兮叹, 武家坡2021.  戏腔 (opera falsetto) chorus aesthetic."
)

# When the caller hasn't overridden MG_REFERENCE_ENGINES, use a 4-way
# multi-engine fanout so the Composer sees alternative drafts from
# engines that are friendlier to this genre than Magenta.  Missing
# engines degrade to NullEngine silently (see src/engine/factory.py).
DEFAULT_REFERENCE_ENGINES = "musiclang,composers_assistant,mmt,figaro"


# ---------------------------------------------------------------------------
# Request builder + CLI driver
# ---------------------------------------------------------------------------

def build_request_payload(
    *,
    tempo: int,
    key: str,
    scale: str,
    bars_per_section: int,
    sections: list[str],
    instruments: list[dict[str, str]],
    include_lyrics: bool,
    lyric_language: str,
    lyric_theme: str,
    reference_style: str,
) -> dict:
    return {
        "request": {
            "description": DESCRIPTION,
            "genre": "chinese_modern_opera_pop",
            "mood": "longing_theatrical_bittersweet",
            "tempo": tempo,
            "key": key,
            "scale_type": scale,
            "time_signature": [4, 4],
            "sections": sections,
            "bars_per_section": bars_per_section,
            "include_lyrics": include_lyrics,
            "lyric_language": lyric_language,
            "lyric_theme": lyric_theme,
            "reference_style": reference_style,
            "instruments": instruments,
        }
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "POST a 赤伶-style Guofeng opera-pop generation job to the "
            "Music Generator API."
        ),
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("MG_API_URL", "http://localhost:8000"),
        help="API base URL (default: MG_API_URL or http://localhost:8000).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=2400,
        help="HTTP timeout in seconds (default: 2400 — this genre is slow).",
    )
    parser.add_argument(
        "--tempo",
        type=int,
        default=DEFAULT_TEMPO,
        help=f"Tempo in BPM (default: {DEFAULT_TEMPO} — matches 赤伶).",
    )
    parser.add_argument(
        "--key",
        default=DEFAULT_KEY,
        help=f"Key letter (default: {DEFAULT_KEY} — 赤伶's home key).",
    )
    parser.add_argument(
        "--scale",
        default=DEFAULT_SCALE,
        help=(
            "Scale type (default: chinese_pentatonic_minor — override "
            "with 'minor' if the Composer struggles with the pentatonic "
            "framework)."
        ),
    )
    parser.add_argument(
        "--bars-per-section",
        type=int,
        default=DEFAULT_BARS_PER_SECTION,
        help=f"Bars per section (default: {DEFAULT_BARS_PER_SECTION}).",
    )
    parser.add_argument(
        "--lyrics",
        dest="lyrics",
        action="store_true",
        default=True,
        help="Request Chinese lyrics (default: on).",
    )
    parser.add_argument(
        "--no-lyrics",
        dest="lyrics",
        action="store_false",
        help="Disable lyrics.",
    )
    parser.add_argument(
        "--lyric-lang",
        default="zh",
        help="Lyric language code (default: zh).",
    )
    parser.add_argument(
        "--reference-engines",
        default=None,
        help=(
            "Override MG_REFERENCE_ENGINES for this run only.  "
            f"Script default: '{DEFAULT_REFERENCE_ENGINES}'.  "
            "Use 'null' to skip reference drafts entirely."
        ),
    )
    parser.add_argument(
        "--out-json",
        default=None,
        help="Optional path to save the full JSON response.",
    )
    args = parser.parse_args()

    # Surface the effective reference_engines setting *in the client
    # environment* so the server (if it was started from this shell)
    # picks it up.  If the server is already running in its own shell,
    # the user must export the var before starting the server — we
    # print a reminder below.
    effective_engines = (
        args.reference_engines
        or os.environ.get("MG_REFERENCE_ENGINES")
        or DEFAULT_REFERENCE_ENGINES
    )
    os.environ["MG_REFERENCE_ENGINES"] = effective_engines

    endpoint = args.url.rstrip("/") + "/api/generate"
    body = build_request_payload(
        tempo=args.tempo,
        key=args.key,
        scale=args.scale,
        bars_per_section=args.bars_per_section,
        sections=DEFAULT_SECTIONS,
        instruments=DEFAULT_INSTRUMENTS,
        include_lyrics=args.lyrics,
        lyric_language=args.lyric_lang,
        lyric_theme=DEFAULT_LYRIC_THEME,
        reference_style=DEFAULT_REFERENCE_STYLE,
    )

    print("=" * 72)
    print("赤伶-style Guofeng Opera-Pop Generator")
    print("=" * 72)
    print(
        f"  tempo={args.tempo} bpm    key={args.key} {args.scale}    "
        f"bars/section={args.bars_per_section}    "
        f"lyrics={'zh' if args.lyrics else 'off'}"
    )
    print(f"  reference_engines = {effective_engines}")
    print(f"  POST {endpoint}")
    print()
    print("NOTE: MG_REFERENCE_ENGINES must be set in the SERVER's")
    print("      environment at startup, not just here in the client.")
    print("      If the API server was started elsewhere, kill + restart:")
    print(f"        export MG_REFERENCE_ENGINES='{effective_engines}'")
    print("        python -m src.main")
    print()
    print("This may take several minutes (LLM + render + vocals + mix).")
    print()

    try:
        response = requests.post(endpoint, json=body, timeout=args.timeout)
    except requests.exceptions.RequestException as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        print(f"HTTP error: {exc}\n{response.text[:2000]}", file=sys.stderr)
        sys.exit(2)

    result = response.json()

    if args.out_json:
        with open(args.out_json, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
        print(f"Full response saved to: {args.out_json}")

    summary = result.get("summary", {})
    midi_path = summary.get("midi_path")
    wav_path = summary.get("wav_path")
    vocal_path = summary.get("vocal_wav_path")
    mix_path = summary.get("mixed_wav_path")
    snapshots = summary.get("snapshots", [])

    print(f"Status:       {result.get('status')}")
    print(f"Final MIDI:   {midi_path or '(none)'}")
    print(f"Final WAV:    {wav_path or '(none — render skipped)'}")
    print(f"Vocal stem:   {vocal_path or '(none — vocal skipped)'}")
    print(f"Mixed WAV:    {mix_path or '(none — mix skipped)'}")
    print(f"Completed:    {summary.get('completed')}")
    if summary.get("error"):
        print(f"Error:        {summary['error']}")

    if snapshots:
        print(f"\nRound snapshots ({len(snapshots)}):")
        for i, snap in enumerate(snapshots):
            label = (
                "Reference drafts" if any(
                    key in snap.lower() for key in (
                        "magenta", "musiclang", "mmt", "figaro",
                        "composers_assistant",
                    )
                )
                else f"Round {i}"
            )
            print(f"  [{label}] {snap}")

    agents = summary.get("agents_involved", [])
    if agents:
        print(f"\nAgents: {', '.join(agents)}")


if __name__ == "__main__":
    main()

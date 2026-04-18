import os
import requests
import json

# ---------------------------------------------------------------------------
# Reference-engine selection
# ---------------------------------------------------------------------------
# 赤伶 is minor-key pop-opera fusion.  The three engines best suited:
#   * musiclang           — chord-conditioned symbolic, excels at minor-key
#                           progressions and pentatonic framing.
#   * figaro              — description-code conditioning; matches prose
#                           briefs like "dramatic theatrical climax" better
#                           than any raw sequence model.
#   * composers_assistant — multi-track MIDI infilling; fills drum + bass
#                           spine against a given melody, which is exactly
#                           what the chorus needs.
# Magenta is dropped because (a) it's failing with 500s in the current env
# and (b) it's the weakest engine for minor-key Chinese pentatonic material.
# Engines without local weights degrade to NullEngine silently.
#
# NOTE: MG_REFERENCE_ENGINES must be set in the SERVER's environment at
# startup.  Setting it here only takes effect if the server is launched
# from this same shell.  If your API server is already running, kill it
# and restart it:
#     export MG_REFERENCE_ENGINES="musiclang,figaro,composers_assistant"
#     python -m src.main
# ---------------------------------------------------------------------------
os.environ["MG_REFERENCE_ENGINES"] = "musiclang,figaro,composers_assistant"


DESCRIPTION = """
赤伶 (Chì Líng) style Guofeng opera-pop ballad — modern band + Chinese
traditional solo instruments + 戏腔 (operatic falsetto) vocal aesthetic.
Reference songs: 赤伶 (HITA / 李袁杰), 探窗, 牵丝戏, 虞兮叹, 武家坡2021.

HARMONY & GROOVE
- E natural minor.  Melody uses the Chinese pentatonic-minor skeleton
  (E-G-A-B-D, 羽调式) sitting on top of Western minor harmony.
- Explicit 赤伶-style progression — do NOT default to Western pop
  (I-V-vi-IV):
    Verse       : Em — Bm — C — G    |    Em — Am — B7 — Em
    Pre-chorus  : Am — Bm — C — D    (iv — v — VI — VII, the classic
                                      Chinese-opera "climbing" cadence
                                      that lifts into the hook)
    Chorus      : Em — Bm — C — G    |    Am — B7 — Em — Em/G
    Bridge      : G  — D/F# — Em — B7   (III — VII — i — V7, modulated
                                         to the relative major for
                                         breathing room before the final
                                         chorus)
- 4/4, tempo 82 BPM (赤伶's actual tempo range: 80-84).  Feel: ballad
  with rubato, NOT a dirge.  Chorus vocal sits a hair behind the beat;
  erhu + strings sit ~3-8 ms ahead.

ORCHESTRATION & SPOTLIGHT PLAN (critical — follow EXACTLY; this is
the biggest lever for "song vs. symphony")
- [intro]       Piano + Pad only.  8 bars sparse.  NO drums.  NO
                traditional instruments.  Negative space is the point.
- [verse]       Piano (broken 8th arpeggios, NOT block chords), Cello
                (walking bass, one note/beat with passing tones), light
                Pad.  Still NO Dizi/Erhu/Guzheng.  NO drums.
- [pre_chorus]  DIZI enters with a rising counter-melody (call-and-
                response with the vocal's line endings).  Strings swell
                as a wide sustained pad.  A snare_roll_accel fires on
                the LAST bar to telegraph the chorus impact.
- [chorus]      FULL ENSEMBLE.  Featured: ERHU (phrase 1) and DIZI
                (phrase 2) ALTERNATING — do NOT double them; they trade
                2-bar phrases like 戏曲 call-and-response.  GUZHENG
                sweeps a descending pentatonic glissando every 2 bars
                as color.  Cinematic Drums enter on bar 1 downbeat with
                a kick + crash impact; Electric Bass locks to the kick
                pattern.  Piano shifts to block 8th-note chords
                (supportive, NOT lead).  Strings carry a wide pad
                underneath.
- [bridge]     PULL BACK HARD.  Erhu SOLO (featured) over Piano
                arpeggios + low Pad.  NO drums, NO bass, NO guzheng,
                NO dizi.  This is the emotional pivot, not a second
                chorus.  Erhu uses vibrato_deep + slide_up_from:2 on
                every phrase start + bend_dip on the climax note.
- [outro]      Dizi (featured) + Piano (slow arpeggio) + Pad (fading
                drone).  Dizi uses breath_fade across the final 4 bars.
                NO drums, NO bass, NO erhu.

CONTINUITY (non-featured instruments must breathe — never one note per
bar)
- Piano: continuous 8ths (arpeggios in verse, block chords in chorus).
- Cello: walking bass with passing tones; root on bar 1 of each chord.
- Strings / Pad: sustained chord beds; minimum one chord per bar.
- Dizi: continuous breath phrases when active; NO staccato single beats.
- Erhu: bow each phrase across the full section; portamento between
  consecutive same-phrase notes.
- Guzheng: cascading runs and broken chords, NOT one pluck per bar.
- Electric Bass: locked to kick on chorus only; silent elsewhere.
- Cinematic Drums: chorus only; kick on 1 & 3, snare on 2 & 4 with a
  ghost on the "and" of 3; hats drive 16ths.

ORNAMENTS (the performance renderer turns these into MIDI pitch-bend /
CC — use the names verbatim)
- Dizi: breath_swell on entrances, flutter on long sustains, overblow
  on chorus climax notes, breath_fade on the outro.
- Erhu: vibrato_deep on every held note ≥ 1 beat, slide_up_from:2 on
  ascending phrase starts, bend_dip on climax notes, portamento
  between same-phrase notes.
- Guzheng: glissando_from on ascending runs, tremolo_rapid on pedal-
  tone cadences.
- Piano (support role): legato_to_next on arpeggio runs.
- Cello: vibrato_light on held root notes.

TRANSITION FX (TransitionAgent schedules these; names are the stem
kinds in assets/transitions/)
- intro → verse        : soft piano tail + riser_short.
- verse → pre_chorus   : short reverse_cymbal + sparse tom fill.
- pre_chorus → chorus  : FULL cinematic entry — riser_8beat +
                         reverse_cymbal_long + impact_deep on the one
                         + sub_drop + snare_roll_accel_1bar over the
                         final bar.  This is the song's biggest
                         moment.
- chorus → bridge      : downlifter_filter + kick drop (drums cut).
- bridge → outro       : soft impact_crisp + dizi-breath fade.

LYRICS (戏腔 / operatic vernacular — theme is the 赤伶 archetype: the
mask of a stage life concealing personal grief)
- Chinese (zh), one character per melody note in verse and most of
  chorus.  Chorus HOOK syllables may extend across 2–3 notes (melisma)
  to carry the 戏腔 lift.
- Minimize tone-melody conflicts on the hook: ascending melody lines
  should carry 阴平 (1st tone) or 阳平 (2nd tone) characters, not
  去声 (4th).
- Verse: intimate / narrative — imagery of 台上台下, 一曲一梦, 水袖,
  灯火阑珊.
- Chorus: archetype declaration — hook lands on a single character
  held over 3–4 beats ("梦", "戏", "空", "红尘").
- Bridge: turn — the performer steps out of role and speaks honestly.

AVOID (common failure modes)
- Every instrument playing every section with equal density → symphony,
  not song.
- Dizi or Erhu in the intro or verse → MUST be saved for pre-chorus
  onwards.
- Traditional instruments playing note-by-note → they are voices that
  breathe, bow, and glide.
- Chorus without a cinematic entry transition → song won't know it
  reached the chorus.
- Western pop progressions (I-V-vi-IV) → the progression IS the 赤伶
  sound.
- Drums in bridge → bridge is the emotional reset.
- Upbeat Western diatonic cliches, jazz / R&B syncopation, pure
  classical Chinese without modern rhythm section.
"""


print("Generating 赤伶-style Guofeng opera-pop music...")
print(f"  MG_REFERENCE_ENGINES = {os.environ['MG_REFERENCE_ENGINES']}")
print("  (reminder: set the same var in the server shell before "
      "`python -m src.main`)")
print("  Per-section composer, may take 5-10 minutes.\n")


response = requests.post(
    "http://localhost:8000/api/generate",
    json={
        "request": {
            "description": DESCRIPTION.strip(),
            "genre": "chinese_modern_opera_pop",
            "mood": "longing_theatrical_bittersweet",

            # Tempo 82 — real 赤伶 clocks 80-84.  84 is fine too but 82
            # gives the pre-chorus a hair more climb room.
            "tempo": 82,

            # E natural minor — 赤伶's actual home key.  Puts the erhu
            # on its open strings (D–A), letting the open-string
            # resonance carry the long sustains on the chorus.
            "key": "E",

            # Chinese pentatonic-minor skeleton (E-G-A-B-D = 羽调式).
            # Your DESCRIPTION says "heavily rely on the Chinese
            # pentatonic minor scale" — this is the string that makes
            # the Composer actually do it.  Fallback: change to
            # "minor" if the Composer struggles to build cadences.
            "scale_type": "chinese_pentatonic_minor",

            "time_signature": [4, 4],

            # Through-composed arc: one verse-chorus pair + bridge +
            # outro.  NOT a verse-chorus-verse-chorus loop — 赤伶 is
            # a SINGLE emotional climb, not a repeating pop form.
            "sections": [
                "intro",
                "verse",
                "pre_chorus",
                "chorus",
                "bridge",
                "outro",
            ],

            # 8 bars/section (NOT 4).  The chorus needs 8 bars to land
            # the full call-and-response between Erhu and Dizi; the
            # verse needs 8 bars to breathe into the pre-chorus lift.
            # 4 bars/section compresses the emotional arc the
            # description spells out.
            "bars_per_section": 8,

            "include_lyrics": True,
            "lyric_language": "zh",
            "lyric_theme": (
                "戏台悲欢，家国情仇，水袖与战火的交织，跨越时空的眷恋 — "
                "戏子无情而情最深，一梦红尘终成戏中人。"
                "主题：台上台下两样人生，红妆戏裳里藏着真心。"
            ),
            "reference_style": (
                "赤伶-style Chinese opera-pop ballad — HITA 赤伶, "
                "探窗, 牵丝戏, 虞兮叹, 武家坡2021. "
                "戏腔 (opera falsetto) chorus aesthetic."
            ),

            # 9 instruments total — 6 from your original + Dizi (your
            # DESCRIPTION mentions "Erhu or Dizi" but 赤伶 actually
            # uses BOTH, alternating) + Cello (walking bass in verse,
            # warmer than electric bass alone) + Pad (texture for
            # intro/outro drone).
            "instruments": [
                # Modern band — the emotional floor.
                {"name": "Piano",           "role": "chords"},
                {"name": "Cello",           "role": "bass"},
                {"name": "Strings",         "role": "pad"},
                {"name": "Pad",             "role": "texture"},
                {"name": "Electric Bass",   "role": "bass"},
                {"name": "Cinematic Drums", "role": "drums"},
                # Traditional solo instruments — pre-chorus onwards.
                {"name": "Erhu",            "role": "lead"},
                {"name": "Dizi",            "role": "counter-melody"},
                {"name": "Guzheng",         "role": "arpeggios_and_texture"},
            ],
        }
    },
    timeout=2400,  # 40 min — per-section composer + render + vocals + mix
)

result = response.json()
summary = result.get("summary", {})
midi_path = summary.get("midi_path")
wav_path = summary.get("wav_path")
vocal_path = summary.get("vocal_wav_path")
mix_path = summary.get("mixed_wav_path")
snapshots = summary.get("snapshots", [])

print(f"Status:      {result.get('status')}")
print(f"Final MIDI:  {midi_path or '(none)'}")
print(f"Final WAV:   {wav_path or '(none — render skipped)'}")
print(f"Vocal stem:  {vocal_path or '(none — vocal skipped)'}")
print(f"Mixed WAV:   {mix_path or '(none — mix skipped)'}")

if snapshots:
    print(f"\n--- Round Snapshots ({len(snapshots)}) ---")
    for i, snap in enumerate(snapshots):
        s = snap.lower()
        if any(k in s for k in (
            "magenta", "musiclang", "figaro", "composers_assistant", "mmt",
        )):
            label = "Reference drafts"
        else:
            label = f"Round {i}"
        print(f"  [{label}] {snap}")

print(
    f"\nSummary: "
    f"{json.dumps({k: v for k, v in summary.items() if k != 'snapshots'}, indent=2, ensure_ascii=False)}"
)

print(f"\n--- Agent Messages ({len(result.get('messages', []))}) ---")
for i, msg in enumerate(result.get("messages", [])):
    preview = msg["content"][:200].replace("\n", " ")
    print(f"\n[{i+1}] {msg['source']}: {preview}...")

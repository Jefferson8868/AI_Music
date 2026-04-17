"""
Curated music-theory knowledge library.

The library ships hand-written, LLM-friendly passages on:
  - Western functional harmony (progressions, cadences, voice leading).
  - Chinese traditional theory (五声 gong-shang-jue-zhi-yu, 调式 modes).
  - Genre conventions (pop, ballad, cinematic, 国风 modern-traditional
    fusion, jazz, folk, electronic).
  - Chord vocabulary (triads, 7ths, extensions, suspensions, borrowed
    chords).
  - Rhythm & feel (groove templates, syncopation, hemiola).
  - Form & section design (verse / pre_chorus / chorus, AABA, bridge).
  - Ornament / expression theory (breath phrasing, portamento, rubato).

Each entry is a plain-prose 2-6 sentence passage with a title, a list
of tags (lower-case keywords), and a free-form body. The `query_machine`
module reads THEORY_ENTRIES and performs keyword/tag matching.

This is deliberately a curated file (not a PDF-indexer) because:
  - It never hits disk at runtime beyond module import.
  - It's human-editable and reviewable.
  - Adding new entries is a one-file change with no dependencies.

For future RAG/embedding/web-search expansion, see
query_machine.MusicKnowledgeQueryMachine.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TheoryEntry:
    """One atomic knowledge passage."""

    id: str
    title: str
    tags: list[str] = field(default_factory=list)
    body: str = ""
    applies_to_genres: list[str] = field(default_factory=list)
    applies_to_agents: list[str] = field(default_factory=list)

    def match_score(self, query_terms: list[str]) -> float:
        """Return a simple match score against lowercased query terms.

        Matches on title/tags/body substrings; tags weigh 3x, title 2x,
        body 1x. Zero means no match; higher means stronger match.
        """
        score = 0.0
        qset = {t.lower().strip() for t in query_terms if t and t.strip()}
        if not qset:
            return 0.0
        title_l = self.title.lower()
        body_l = self.body.lower()
        tags_l = {t.lower() for t in self.tags}
        for term in qset:
            if term in tags_l:
                score += 3.0
            if term in title_l:
                score += 2.0
            if term in body_l:
                score += 1.0
        return score


# ---------------------------------------------------------------------------
# Library content
# ---------------------------------------------------------------------------

THEORY_ENTRIES: list[TheoryEntry] = [
    # ---- Western functional harmony --------------------------------------
    TheoryEntry(
        id="harmony.pop_progressions",
        title="Pop chord progressions (I-V-vi-IV and friends)",
        tags=[
            "harmony", "progression", "pop", "western",
            "i-v-vi-iv", "vi-iv-i-v", "cadence",
        ],
        body=(
            "Modern Western pop leans on diatonic loops. The I-V-vi-IV "
            "('Axis of Awesome' progression) is emotionally neutral and "
            "anthemic; vi-IV-I-V is melancholic-hopeful; I-vi-IV-V is the "
            "classic 50s doo-wop. Chorus hooks often sit on IV or V with a "
            "vocal peak on the vi-to-IV transition. Pre-choruses frequently "
            "move IV-V-vi or ii-V-I to prime the chorus downbeat."
        ),
        applies_to_genres=["modern_western_pop", "pop", "ballad"],
        applies_to_agents=["composer", "critic"],
    ),
    TheoryEntry(
        id="harmony.cadences",
        title="Cadence types (authentic, plagal, deceptive, half)",
        tags=["cadence", "harmony", "voice_leading", "resolution"],
        body=(
            "An authentic cadence (V-I, strongest with leading tone 7->1) "
            "is the default full stop; sections end here by default. "
            "Plagal (IV-I) sounds hymn-like and final without the leading "
            "tone. Deceptive (V-vi) subverts expectation — great end of "
            "bridge before a final chorus. Half cadence (ends on V) hangs "
            "the listener — pair with a pickup line into the next section."
        ),
        applies_to_agents=["composer", "critic"],
    ),
    TheoryEntry(
        id="harmony.voice_leading",
        title="Voice-leading basics (smooth common-tone motion)",
        tags=["voice_leading", "harmony", "counterpoint", "inversion"],
        body=(
            "Keep the top voice of chord comps within a major second of "
            "the previous chord when possible; common tones stay put. "
            "Avoid parallel fifths/octaves between the outer voices. When "
            "the bass descends by step (e.g. I - V/4-3 - vi), the "
            "top voice often moves in contrary motion."
        ),
        applies_to_agents=["composer", "instrumentalist", "critic"],
    ),
    TheoryEntry(
        id="harmony.borrowed_chords",
        title="Borrowed chords (modal mixture)",
        tags=["harmony", "modal", "borrowed", "iv_minor", "chromaticism"],
        body=(
            "Borrowing from the parallel minor (iv, bVI, bVII) darkens a "
            "major-key progression. bVI before V is a cinematic lift. "
            "iv-I (plagal with minor subdominant) is a signature of "
            "Beatles-era ballads and Taylor Swift bridges."
        ),
        applies_to_agents=["composer", "critic"],
    ),

    # ---- Chinese / Eastern theory ----------------------------------------
    TheoryEntry(
        id="theory.pentatonic_five",
        title="Chinese pentatonic — 宫商角徵羽 (gong-shang-jue-zhi-yu)",
        tags=[
            "pentatonic", "chinese", "gong", "shang", "jue", "zhi", "yu",
            "mode", "wuyin", "五声",
        ],
        body=(
            "The Chinese five-tone system names scale degrees 宫 (gong, 1), "
            "商 (shang, 2), 角 (jue, 3), 徵 (zhi, 5), 羽 (yu, 6). A "
            "pentatonic on C is C D E G A. Different modes arise from "
            "choosing different final tones: 宫调 (do-mode, bright), "
            "商调 (re-mode), 角调 (mi-mode, nostalgic), 徵调 (so-mode, "
            "stately), 羽调 (la-mode, melancholy — closest to natural "
            "minor). Modern fusion usually sits in 羽调 for its Western "
            "minor-key kinship."
        ),
        applies_to_genres=[
            "chinese_traditional", "chinese_modern_fusion",
            "chinese_pentatonic_minor",
        ],
        applies_to_agents=["composer", "critic"],
    ),
    TheoryEntry(
        id="theory.chinese_ornaments",
        title="Idiomatic ornaments in Chinese traditional music",
        tags=[
            "ornament", "chinese", "揉弦", "滑音", "花舌", "轮指",
            "portamento", "vibrato", "slide", "tremolo",
        ],
        body=(
            "Chinese solo lines breathe through ornaments. Erhu uses deep "
            "揉弦 (vibrato, often wider and slower than Western violin) and "
            "frequent 滑音 (portamento, a defining sound). Dizi uses "
            "花舌 (flutter-tongue) on climaxes and breathy 气震音 on "
            "sustained notes. Pipa's signature is 轮指 (rapid finger "
            "tremolo) producing a sustained shimmer. Guzheng pours "
            "pentatonic 刮奏 (glissando) between phrases. A 'clean' "
            "un-ornamented line sounds wrong — it reads as sheet music, "
            "not music."
        ),
        applies_to_genres=[
            "chinese_traditional", "chinese_modern_fusion",
        ],
        applies_to_agents=["composer", "instrumentalist", "critic"],
    ),
    TheoryEntry(
        id="theory.fusion_arrangement",
        title="Modern-traditional Chinese fusion arrangement (国风 pop)",
        tags=[
            "fusion", "国风", "chinese_modern_fusion", "arrangement",
            "spotlight", "赤伶", "牵丝戏", "虞兮叹",
        ],
        body=(
            "The modern-traditional fusion ballad (reference: 赤伶, 牵丝戏, "
            "虞兮叹, 武家坡2021) reserves traditional solo instruments for "
            "climactic moments. The modern band (piano, cello, pad, "
            "strings) carries the intro and verse; Dizi enters at the "
            "pre-chorus as a signal; Dizi + Erhu OWN the chorus with "
            "ornamented, sustained lines; the bridge pulls back to an "
            "intimate Erhu over piano; a fragile Dizi fades the outro. "
            "The emotional arc comes from this spotlight contrast, not "
            "from every instrument playing everywhere."
        ),
        applies_to_genres=["chinese_modern_fusion"],
        applies_to_agents=["orchestrator", "composer", "critic"],
    ),
    TheoryEntry(
        id="theory.chinese_tonal_lyric",
        title="Chinese lyric tones vs. melody contour (字正腔圆)",
        tags=[
            "lyrics", "chinese", "tones", "字正腔圆", "阴平", "阳平",
            "上声", "去声",
        ],
        body=(
            "Chinese character tones interact with melody. A 去声 "
            "(falling, 4th tone) word wants a descending or stable "
            "melodic step; setting it to a rising melody (e.g. an octave "
            "leap UP on '去') distorts meaning and sounds unnatural. "
            "Songwriters aim for '字正腔圆' — every character is "
            "intelligible. Rule of thumb: falling tones on flat/descending "
            "notes; rising (阳平, 2nd) tones on ascending or held notes; "
            "1st tone (阴平) anywhere."
        ),
        applies_to_agents=["lyricist", "composer", "critic"],
    ),

    # ---- Rhythm & feel ---------------------------------------------------
    TheoryEntry(
        id="rhythm.pop_ballad_groove",
        title="Pop ballad groove (70-88 BPM)",
        tags=["rhythm", "groove", "ballad", "tempo", "70-88"],
        body=(
            "Ballads sit in the 70-88 BPM range. Piano comp is usually "
            "continuous 8th-note chord cells or flowing 1-5-10 arpeggios. "
            "Cello/bass walks root-fifth on downbeats with a passing tone "
            "on beat 4. Pad strings hold whole-note chord beds under the "
            "melody. Drums, when present, enter at the pre-chorus with a "
            "soft kick-snare backbeat."
        ),
        applies_to_genres=["ballad", "chinese_modern_fusion"],
        applies_to_agents=["composer", "instrumentalist"],
    ),
    TheoryEntry(
        id="rhythm.modern_pop_groove",
        title="Modern radio pop groove (100-118 BPM)",
        tags=["rhythm", "groove", "pop", "100-118", "backbeat"],
        body=(
            "Contemporary chart pop sits 100-118 BPM with a danceable "
            "backbeat. Syncopated verse melody, straight chorus downbeats. "
            "Pre-chorus often drops the drums or shifts to half-time to "
            "let the chorus hit harder. The hook is usually 2 or 4 bars "
            "repeated; ear expects to hear it again."
        ),
        applies_to_genres=["modern_western_pop", "pop"],
        applies_to_agents=["composer", "instrumentalist"],
    ),

    # ---- Form & section design -------------------------------------------
    TheoryEntry(
        id="form.verse_chorus",
        title="Verse-chorus form with pre-chorus lift",
        tags=["form", "verse", "chorus", "pre_chorus", "bridge", "structure"],
        body=(
            "The standard modern pop form is intro - verse - pre_chorus - "
            "chorus - verse - pre_chorus - chorus - bridge - chorus - outro. "
            "Verse narrates; pre-chorus tightens harmonic rhythm and "
            "raises register to set up the chorus; chorus states the hook "
            "and sits at emotional peak; bridge introduces contrast "
            "(new key, new rhythm, sparser texture) before the final "
            "chorus."
        ),
        applies_to_agents=["orchestrator", "composer", "critic"],
    ),
    TheoryEntry(
        id="form.bridge_design",
        title="Bridge design — contrast and release",
        tags=["form", "bridge", "contrast", "modulation"],
        body=(
            "A strong bridge does ONE of: (a) modulates to a related key, "
            "(b) drops to half-time, (c) strips to one or two instruments "
            "for intimacy. The bridge's last bar must return energy to "
            "set up the final chorus — either via a dominant pedal (V), "
            "a drum fill, or a rising melodic line."
        ),
        applies_to_agents=["composer", "critic"],
    ),

    # ---- Orchestration & range ------------------------------------------
    TheoryEntry(
        id="orch.range_awareness",
        title="Keep instruments in their sweet spot, not their extreme",
        tags=["orchestration", "range", "sweet_spot", "register"],
        body=(
            "Each instrument has a sweet spot where it blooms. Erhu "
            "shines D4-A5; pushed above C6 it shrieks. Dizi is bright "
            "and penetrating D5-D6; below G4 it loses projection. "
            "Cello sings C3-G4; above G4 it enters the alto range and "
            "starts competing with violin/viola. Extreme registers are "
            "for climaxes, not sustained comping."
        ),
        applies_to_agents=["composer", "instrumentalist", "critic"],
    ),
    TheoryEntry(
        id="orch.density_contrast",
        title="Section density as contrast device",
        tags=[
            "orchestration", "density", "dynamics", "contrast", "spotlight",
        ],
        body=(
            "Don't use volume as your only dynamic lever — vary "
            "orchestral density instead. Intro: 1-2 tracks. Verse: 3-4. "
            "Pre-chorus: add ONE new track (not all of them) — that new "
            "entrance IS the lift. Chorus: full ensemble but still with "
            "a featured soloist. Bridge: pull back to 2-3 tracks. Outro: "
            "fade to one. Equal density everywhere = symphonic mush."
        ),
        applies_to_agents=["orchestrator", "composer", "critic"],
    ),
    TheoryEntry(
        id="orch.continuity_vs_sparsity",
        title="Continuity — active instruments must play continuously",
        tags=[
            "continuity", "phrasing", "density",
            "breath", "bowing", "comping",
        ],
        body=(
            "An instrument active in a section must SOUND active. "
            "Continuous-breath (dizi, xiao, flute) and continuous-bowed "
            "(erhu, violin, cello) instruments must phrase across 2-4 "
            "bars with legato and vibrato, not drop isolated single "
            "notes. Rhythmic-comp instruments (piano, guitar) must "
            "maintain their repeating cell, not comp one bar and rest "
            "three. Plucked-discrete instruments (guzheng, pipa) must "
            "group phrases as runs or tremolo, not stab single plucks. "
            "A silence between notes from the same active instrument "
            "that exceeds max_gap_beats reads as a mistake."
        ),
        applies_to_agents=["composer", "instrumentalist", "critic"],
    ),

    # ---- Expression / performance ----------------------------------------
    TheoryEntry(
        id="expr.velocity_envelopes",
        title="Velocity envelopes per instrument family",
        tags=["velocity", "envelope", "attack", "decay", "expression"],
        body=(
            "Piano and plucked strings (guzheng, pipa, harp) have sharp "
            "attack + exponential decay — high velocity on attack, then "
            "you can't add energy mid-note. Bowed strings and winds can "
            "SWELL mid-note — start soft, grow, fade. That's why vibrato "
            "and CC11 (expression) shape sustained bowed/wind notes, "
            "while piano relies on velocity alone."
        ),
        applies_to_agents=["instrumentalist", "composer"],
    ),
    TheoryEntry(
        id="expr.rubato_ballads",
        title="Rubato — expressive tempo in ballads",
        tags=["rubato", "tempo", "expression", "ballad"],
        body=(
            "Ballads breathe — slight tempo stretches across phrase ends "
            "make them feel alive. Stretching the last two beats of a "
            "bridge before the final chorus is a classic move. In MIDI "
            "this is an explicit tempo change or slight note-onset shift; "
            "avoid rubato on groove-driven sections where listeners want "
            "a steady backbeat."
        ),
        applies_to_agents=["composer", "instrumentalist", "critic"],
    ),

    # ---- Critic evaluation criteria --------------------------------------
    TheoryEntry(
        id="critic.evaluation_axes",
        title="Critic evaluation axes (what good music generation looks for)",
        tags=["critic", "evaluation", "rubric", "score"],
        body=(
            "Evaluate across these axes: (1) harmonic coherence — chords "
            "actually function; (2) melodic shape — clear arc, not "
            "random walk; (3) instrument idiom — each part sounds like "
            "its instrument, not like 'generic MIDI'; (4) spotlight "
            "contrast — sections feel different; (5) continuity — active "
            "parts don't drop to single notes; (6) ornament density — "
            "featured tracks have 30-60% ornament coverage; (7) "
            "rhythmic groove coherence; (8) lyric-melody fit. Each axis "
            "0.0-1.0; aggregate weighted average."
        ),
        applies_to_agents=["critic"],
    ),
]


def all_entry_ids() -> list[str]:
    """Return the list of all entry IDs (useful for debugging)."""
    return [e.id for e in THEORY_ENTRIES]


def get_entry(entry_id: str) -> TheoryEntry | None:
    """Return the entry with the given id, or None."""
    for e in THEORY_ENTRIES:
        if e.id == entry_id:
            return e
    return None

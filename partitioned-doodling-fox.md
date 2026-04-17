# Spotlight Arrangement + Instrument Realism — Implementation Plan

## Context

The nested-loop pipeline (previous spec, version 3, committed) solved structural density but produced two musical problems the user called out after listening to a Neon Rain / 雨夜霓虹 test generation:

1. **"Symphonic, not a song"** — every instrument plays in every section. Critic scores plateaued at 0.55–0.65. Reference Chinese-modern-fusion songs (赤伶, 牵丝戏, 虞兮叹, 武家坡2021) reserve traditional instruments for climactic peaks; current output has Dizi/Erhu droning through intro/verse/chorus equally. Root cause: `src/llm/prompts.py:123` — *"Include ALL tracks from the blueprint"*.

2. **"Sounds like a MIDI scale"** — instruments lack resonance. Dizi is missing breath/flutter-tongue/slide; Erhu is missing vocal-like vibrato and portamento. Root causes: (a) `src/knowledge/instruments.py` truncates rich technique text to 200 chars before the Composer sees it; (b) `src/music/midi_writer.py:243–303` renders articulations as coarse on/off envelopes at track level with no per-note depth variation; (c) the Instrumentalist writes MIDI-level data the LLM is bad at producing.

This spec addresses both together because they are tightly coupled: spotlight decides *when* an instrument plays, ornaments decide *how* it sounds. Fixing either alone leaves the other failure visible.

**Sub-projects C/D/E/F deferred** (see Future Work appendix): knowledge RAG/web-search, Magenta abstraction + alternate engines (MusicLang Predict, Anticipatory Transformer), critic feedback loop overhaul, full lyrics alignment, statistical MIDI-corpus mining.

---

## Dependency Chain

```
Step 1: src/music/score.py            (data model: SpotlightEntry, SpotlightProposal,
                                        PitchBendEvent, CCEvent, ScoreTrack extensions,
                                        ScoreNote.ornaments)
Step 2: src/music/ornaments.py        (NEW — ornament macro vocabulary registry)
Step 3: src/knowledge/instruments.py  (add performance_recipes, auto_rules,
                                        ornament_vocabulary, spotlight_profile,
                                        idiomatic_motifs, velocity_envelope_preset
                                        to all 18 cards; remove 200-char truncation)
Step 4: src/knowledge/spotlight_presets.py (NEW — MODERN_TRADITIONAL_FUSION preset)
Step 5: src/music/performance.py      (NEW — Phase 4 render stage)
Step 6: src/music/midi_writer.py      (consume track.pitch_bends + track.cc_events)
Step 7: src/llm/prompts.py            (Orchestrator spotlight_plan output; inner Composer
                                        featured/supporting block; ornament vocabulary
                                        injection; lyricist non-empty guarantee;
                                        critic spotlight evaluation)
Step 8: src/agents/pipeline.py        (spotlight enforcement in Phase 3; proposal
                                        collection + review; Phase 4 invocation)
Step 9: tests/test_performance.py     (NEW — renderer unit + golden snapshot tests)
```

Steps 1–2 independent. Step 3 depends on Step 2 (ornament names). Steps 4–6 depend on Steps 1–3. Step 7 depends on Step 3. Step 8 depends on all prior. Step 9 depends on Step 5.

---

## Step 1: Score Data Model Extensions

**File:** `src/music/score.py`

Add new models (after existing `ScoreUpdate`):

```python
class SpotlightEntry(BaseModel):
    section: str
    active: list[str] = Field(default_factory=list)
    featured: list[str] = Field(default_factory=list)
    silent: list[str] = Field(default_factory=list)

class SpotlightProposal(BaseModel):
    section: str
    add_instruments: list[str] = Field(default_factory=list)
    remove_instruments: list[str] = Field(default_factory=list)
    reasoning: str = ""
    confidence: float = 0.0

class PitchBendEvent(BaseModel):
    beat: float
    value: int       # -8192..8191
    channel: int = 0

class CCEvent(BaseModel):
    beat: float
    controller: int  # 1=mod, 2=breath, 11=expression, 64=sustain
    value: int       # 0..127
    channel: int = 0
```

Extend existing models:

- `ScoreNote`: add `ornaments: list[str] = Field(default_factory=list)`.
- `ScoreTrack`: add `pitch_bends: list[PitchBendEvent]`, `cc_events: list[CCEvent]`, `rendered: bool = False`.
- `CompositionBlueprint`: add `spotlight_plan: list[SpotlightEntry] = Field(default_factory=list)`.

**Backward compat:** Empty `spotlight_plan` means "all instruments active in all sections" — pipeline emits this default when the Orchestrator produced no plan. `ornaments=[]` renders as plain note (current behavior).

**Verify:** Load an existing saved blueprint JSON (if any exist); ensure it still parses without the new fields.

---

## Step 2: Ornament Macro Registry

**File:** `src/music/ornaments.py` (NEW)

Single module exporting:

```python
ORNAMENT_MACROS: dict[str, OrnamentSpec]
# Keys: breath_swell, breath_fade, flutter, overblow,
#       slide_up_from, slide_down_from, slide_up_to, slide_down_to, bend_dip,
#       vibrato_light, vibrato_deep, vibrato_delayed,
#       staccato, tenuto, legato_to_next,
#       tremolo_rapid, grace_note_above, grace_note_below,
#       glissando_from, glissando_to

class OrnamentSpec(BaseModel):
    name: str
    description: str           # 1-line, shown to LLM
    takes_arg: bool = False    # e.g. slide_up_from:2
    arg_range: tuple[int, int] | None = None
    arg_default: int | None = None
    # Renderer-side parameters:
    renders_to: list[str]      # e.g. ["pitch_bend"], ["cc1_lfo"], ["retrigger"]
```

Plus helper `parse_ornament(token: str) -> tuple[str, int | None]` that splits `"slide_up_from:3"` → `("slide_up_from", 3)`.

**No MIDI logic here** — just vocabulary metadata. Rendering lives in Step 5.

**Verify:** Import the module, call `parse_ornament("vibrato_deep")` and `parse_ornament("slide_up_from:3")`; assert results.

---

## Step 3: INSTRUMENT_CARDS Expansion + Truncation Fix

**File:** `src/knowledge/instruments.py`

### 3a. Remove truncation

Find `[:200]` and `[:150]` caps in `format_for_composer()`, `format_for_instrumentalist()`, `format_for_critic()`. Delete them.

### 3b. Add new fields to all 18 cards

Schema per card (add — don't replace existing fields):

```python
"performance_recipes": {
    "default_vibrato": {"type": "vibrato_light" | "vibrato_deep" | None,
                        "depth": 0..127, "rate_hz": float},
    "long_note_threshold_beats": float,
    "long_note_ornaments": list[str],
    "consecutive_step_threshold_beats": float,
    "consecutive_step_ornaments": list[str],
    "phrase_end_ornaments": list[str],
    "velocity_curve": "swell" | "decay" | "flat" | "accent",
},

"auto_rules": [
    {"condition": "duration > X" | "next_note_close" | "first_of_phrase" | "last_of_phrase" | "ascending_run",
     "add_ornaments": list[str]},
],

"ornament_vocabulary": list[str],  # subset of ORNAMENT_MACROS keys

"spotlight_profile": {
    "typical_role": str,
    "good_at": list[str],       # section names
    "avoid": list[str],
    "pairs_with": list[str],
    "competes_with": list[str],
},

"idiomatic_motifs": [
    {"name": str, "description": str, "notes": list[ScoreNote-shape dict]},
],

"velocity_envelope_preset": {"attack": 0.0..1.0, "peak_ratio": float, "decay": 0.0..1.0},
```

**Priority:** Write rich content for Erhu, Dizi, Guzheng, Piano, Cello, Strings/Pad first (the user's current test piece). Remaining 12 instruments get minimum-viable defaults.

### 3c. Scoped formatter signatures

```python
def format_for_composer(name: str, role: str, section: str | None = None,
                        is_featured: bool = False) -> str: ...
def format_for_instrumentalist(name: str, section: str | None = None) -> str: ...
def format_for_critic(name: str) -> str: ...
```

- `format_for_composer`: returns FULL `techniques` + `style_notes` + `role_guidance[role]` + `ornament_vocabulary` + up to 2 motifs from `idiomatic_motifs`. If `is_featured=False`, returns a shorter summary (sweet_spot + 3-line technique excerpt + ornament_vocabulary).
- `format_for_instrumentalist`: returns `ornament_vocabulary` + `performance_recipes` + techniques (full).
- `format_for_critic`: returns `critic_criteria` + `spotlight_profile`.

### 3d. Validation

Add `_validate_card(name, card) -> None` called at module import for every entry. Asserts new fields exist with correct types. Raises with helpful message if malformed.

### 3e. Accessor

```python
def get_performance_recipe(instrument_name: str, field_name: str, default=None): ...
def get_auto_rules(instrument_name: str) -> list[dict]: ...
def get_spotlight_profile(instrument_name: str) -> dict: ...
```

Used by the performance renderer (Step 5) and pipeline (Step 8).

**Verify:** Import module — validation should pass for all 18 cards. Call `format_for_composer("Erhu", "lead", "chorus", is_featured=True)` and assert output is > 400 chars and contains "Portamento".

---

## Step 4: Spotlight Preset

**File:** `src/knowledge/spotlight_presets.py` (NEW)

```python
MODERN_TRADITIONAL_FUSION = {
    "intro":      {"active": ["piano", "pad"], "featured": ["piano"]},
    "verse":      {"active": ["piano", "bass", "drums", "pad"],
                   "featured": ["piano"]},
    "pre_chorus": {"active": ["piano", "bass", "drums", "pad", "dizi"],
                   "featured": ["piano", "dizi"]},
    "chorus":     {"active": "ALL", "featured": ["dizi", "erhu"]},
    "bridge":     {"active": ["piano", "erhu", "pad"], "featured": ["erhu"]},
    "outro":      {"active": ["dizi", "pad"], "featured": ["dizi"]},
}

PRESETS: dict[str, dict] = {
    "modern_traditional_fusion": MODERN_TRADITIONAL_FUSION,
    # extend later
}

def expand_preset(preset_name: str,
                  all_instruments: list[str]) -> list[SpotlightEntry]:
    """Expand a preset + resolve 'ALL' to the actual instrument list."""
```

Helper is used by the Orchestrator prompt example and by a fallback path in `pipeline._ensure_spotlight_plan()`.

**Verify:** `expand_preset("modern_traditional_fusion", ["dizi","erhu","piano","pad","bass"])` returns a list of 6 `SpotlightEntry` with `"ALL"` expanded to the full list.

---

## Step 5: Performance Renderer

**File:** `src/music/performance.py` (NEW)

Single entry point:

```python
def apply_performance_render(score: Score,
                             instrument_cards: dict = INSTRUMENT_CARDS) -> Score:
    """Expand ornaments into PitchBendEvents, CCEvents, note retriggers, and
    velocity/duration adjustments. Idempotent (skipped if track.rendered=True).
    Returns a new Score — never mutates input."""
```

### 5a. Pipeline inside the function

For each track:

1. **Skip if `track.rendered`** — idempotency guard.
2. **Auto-ornament pass:** call `get_auto_rules(track.instrument)`. For each rule, find notes matching the condition and append the rule's ornaments to `note.ornaments` (if not already present).
3. **Ornament expansion pass:** walk `track.notes`; for each note, dispatch each ornament through `_render_<ornament_name>(note, track, cards)` which returns `(pitch_bends, cc_events, extra_notes, duration_adjust, velocity_adjust)` and applies them.
4. **Velocity envelope pass:** apply `velocity_envelope_preset` per-note via `velocity_adjust` multiplier.
5. **Sort track.pitch_bends and track.cc_events by beat.** Mark `track.rendered = True`.

### 5b. Per-ornament renderers

Individual functions, each 10–40 lines, deterministic. Key ones:

- `_render_vibrato_light/deep/delayed`: emits CC1 samples on a sine LFO at configured depth+rate, spanning `note.start_beat → note.start_beat + note.duration_beats` (minus attack delay for `_delayed`).
- `_render_slide_up/down_from`: emits a PitchBendEvent ramp starting 0.25 beats before the note, ending at `note.start_beat` with value=0 (neutral), source pitch determined by arg.
- `_render_slide_up/down_to`: mirror — ramp over the note's duration from 0 to target bend.
- `_render_bend_dip`: down-up triangle over middle 50% of note.
- `_render_flutter`: inserts retriggered notes at 16th-note rate for the note's duration; original note shortened to first 16th.
- `_render_tremolo_rapid`: same as flutter but without CC1 modulation (pure note retrigger — Pipa 轮指).
- `_render_grace_note_above/below`: inserts a ScoreNote 0.125 beats before the main note, pitch ±1 step, velocity = 0.7 × main note.
- `_render_glissando_from/to`: inserts 3–5 arpeggiated notes into the preceding/following interval.
- `_render_breath_swell/fade`: CC2 (breath) + CC11 (expression) envelope rising to target over 0.25 beats.
- `_render_staccato`: `duration_adjust = 0.5`.
- `_render_tenuto`: `duration_adjust = 1.0`, `velocity_adjust = +5`.
- `_render_legato_to_next`: extends duration to eliminate gap with next note.

### 5c. Edge cases

- Ornament on last note + `legato_to_next` → degrade to `tenuto`.
- Unknown ornament name → log warning, skip. Don't crash.
- Ornament with missing arg (e.g. `slide_up_from` without `:N`) → use `arg_default` from `OrnamentSpec`.
- Bend value clamped to ±8191.
- Retrigger count capped at 16 per note (safety).

### 5d. `_render_track_only` helper

Public function `apply_performance_render_to_track(track, instrument_card) -> ScoreTrack` so tests can verify single-track behavior.

**Verify:** Construct a `Score` with one Erhu track with two notes, one marked `["slide_up_from:3", "vibrato_deep"]`. Call renderer; assert `track.pitch_bends` has ≥8 entries (the slide ramp) and `track.cc_events` has ≥20 entries (the vibrato LFO). Call again; assert no new events added (idempotent).

---

## Step 6: MIDI Writer Upgrade

**File:** `src/music/midi_writer.py`

In `score_to_midi()`:

1. After writing each track's notes, iterate `track.pitch_bends`: emit `mido.Message('pitchwheel', channel=..., pitch=event.value, time=delta_ticks)`.
2. Iterate `track.cc_events`: emit `mido.Message('control_change', channel=..., control=event.controller, value=event.value, time=delta_ticks)`.
3. Delta-time calculation shares the existing beat→ticks converter.
4. Keep existing `trk_arts` path alive (legacy): if a track has `pitch_bends`/`cc_events` populated, use them; otherwise fall back to the old articulation code.

**Verify:** Round-trip a rendered Score to MIDI and back via `mido`. Assert the pitchwheel/CC messages are present at expected ticks.

---

## Step 7: Prompt Updates

**File:** `src/llm/prompts.py`

### 7a. `ORCHESTRATOR_SYSTEM`

Add `spotlight_plan` to the required output JSON with the example shape matching `SpotlightEntry`. Add guidance:
*"If the user request mentions modern+traditional fusion (e.g. 戏腔, 国风, fusion, cinematic pop with Chinese instruments), start from the MODERN_TRADITIONAL_FUSION preset (shown below) and adjust as needed. Otherwise, design the spotlight_plan freshly — traditional instruments should generally be reserved for featured entrances, not play constantly."*

Include the `MODERN_TRADITIONAL_FUSION` preset JSON inline in the prompt as a reference example.

### 7b. `build_composer_section_prompt()` (inner loop)

Add new parameters `is_featured: bool` and `section_active_instruments: list[str]`. Inject a new block near the top:

```
You are {FEATURED | SUPPORTING} in this section.
Other active instruments here: {...}.
Instruments silent in this section: {...}.

If you are SUPPORTING: leave register and rhythmic space for the featured instruments.
If you are FEATURED: carry the melodic hook.
```

Also inject the ornament vocabulary list (from `ornament_vocabulary` of that instrument's card): *"You may use these ornaments on notes: breath_swell, flutter, slide_up_from:N, vibrato_deep, ... Most notes should have 0–1 ornaments. Only climactic notes get 2+."*

### 7c. Spotlight proposal schema in Composer + Inner Critic outputs

Append to both Composer and Inner Critic JSON schemas an optional top-level `spotlight_proposal` field matching `SpotlightProposal`. Document in the prompt:
*"If you strongly believe an instrument should be added/removed from a section that differs from the current spotlight_plan, include a spotlight_proposal with reasoning and confidence (0.0–1.0). Proposals with confidence ≥ 0.9 auto-apply; 0.7–0.9 get reviewed; < 0.7 are ignored."*

### 7d. `STRUCTURAL_CRITIC_SYSTEM`

Add an evaluation criterion: *"Does spotlight_plan create contrast between sections? Are traditional instruments reserved for climactic moments when the piece calls for fusion style?"*

### 7e. `ENSEMBLE_CRITIC_SYSTEM`

Add a block: spotlight_plan is shown to the critic; it must flag any instrument that generated notes while being marked silent in a section.

### 7f. `LYRICIST_SYSTEM`

Add: *"For every section where the spotlight_plan lists a melody-role instrument as featured, you MUST produce at least 4 lyric lines aligned to melody note beats. Returning an empty lines array for a featured section causes re-prompt."*

### 7g. New builder: `build_spotlight_review_prompt(proposals, current_plan) -> str`

Used by `_review_spotlight_proposals()` to ask the Ensemble Critic (in a new `spotlight_review` submode) whether to accept each proposal. Returns JSON `{accepted: [...], rejected: [...], reasoning: str}`.

**Verify:** Import each new/updated builder, call with dummy args, assert output length and key substrings.

---

## Step 8: Pipeline Integration

**File:** `src/agents/pipeline.py`

### 8a. Phase 1 setup — spotlight defaulting

After Orchestrator returns a blueprint, call `_ensure_spotlight_plan(blueprint)`:
- If `blueprint.spotlight_plan` is empty, emit warning, call `expand_preset("modern_traditional_fusion", instrument_names)` if user description contains fusion keywords, else build a flat "all active" plan.
- Validate: every section in `enriched_sections` has a corresponding `SpotlightEntry`; every listed instrument is in the blueprint.

### 8b. Phase 3 outer loop — spotlight enforcement

At the top of `_run_phase3_nested_refinement()`:

```python
current_spotlight = {e.section: e for e in blueprint.spotlight_plan}
```

Inside the outer loop, `_sort_instruments_by_priority()` stays. But `_run_inner_loop()` signature grows:

```python
def _run_inner_loop(self, inst_info, main_score, current_score,
                    enriched_sections, arranged_instruments,
                    current_spotlight, ...):
    active_sections = [sec for sec in enriched_sections
                       if inst_info["name"] in current_spotlight[sec["name"]].active]
    if not active_sections:
        logger.info(f"[InnerLoop] {inst_info['name']} has no active sections — skipped")
        return current_score
    # ... existing loop iterates `active_sections` not all sections
```

For each section in `active_sections`, the Composer prompt is built with `is_featured = inst_info["name"] in current_spotlight[section].featured`.

### 8c. Spotlight proposal collection

After each Composer call and after each Inner Critic call, run:
```python
proposals.extend(_collect_spotlight_proposals(agent_response_json))
```

At the end of the outer iteration (before Ensemble Critic runs), call:
```python
accepted, rejected = _review_spotlight_proposals(proposals, current_spotlight, ensemble_critic)
affected = _apply_accepted_proposals(accepted, current_spotlight)
# Affected instruments added to instrument_reruns for next outer iteration
```

### 8d. Phase 4 — performance render

Between Phase 3 completion and `_build_final_output()`:

```python
from src.music.performance import apply_performance_render
score = apply_performance_render(score)  # idempotent
```

Save a render snapshot MIDI: `{title}_outer{K}_render.mid`.

### 8e. Lyrics non-empty guarantee

In the existing lyricist call inside Phase 2 / Phase 3, inspect returned lyrics. For each featured section with zero lyric lines, re-prompt up to 2 times with an explicit error: *"Your previous output had empty lyrics for section X, which is featured. Provide ≥4 lines."*

### 8f. New helpers

- `_ensure_spotlight_plan(blueprint, task_text) -> None`
- `_collect_spotlight_proposals(agent_response: str) -> list[SpotlightProposal]`
- `_review_spotlight_proposals(proposals, current_spotlight, ensemble_critic) -> tuple[list, list]`
- `_apply_accepted_proposals(accepted, current_spotlight) -> set[str]`

### 8g. Progress reallocation

Phase 1: 0.00 – 0.08, Phase 2: 0.08 – 0.25, Phase 3: 0.25 – 0.88, Phase 4 render: 0.88 – 0.95, Finalize: 0.95 – 1.00.

**Verify:** Full pipeline run with a fusion-genre test request. Assert:
- Blueprint contains `spotlight_plan`.
- Final Score has at least one section where Dizi track has zero notes (intro or verse).
- Final Score has at least one featured section where Dizi has dense notes.
- At least one track has non-empty `pitch_bends` and `cc_events`.

---

## Step 9: Performance Renderer Tests

**File:** `tests/test_performance.py` (NEW)

Tests:

1. **test_vibrato_emits_cc1**: 2-beat note with `["vibrato_deep"]`; assert ≥20 CC1 events with expected oscillation shape.
2. **test_slide_up_from_emits_pitchbend_ramp**: note with `["slide_up_from:3"]`; assert pitch_bend ramp spans 0.25 beats before note, 8 intermediate values.
3. **test_flutter_inserts_retriggers**: 1-beat note with `["flutter"]`; assert 4 additional notes inserted at 16th-note intervals.
4. **test_idempotency**: render twice; assert second render is a no-op (equal events).
5. **test_auto_rules_apply**: Erhu track with two consecutive notes gap=0.25 beats; assert `legato_to_next` appears automatically.
6. **test_legato_to_next_on_last_note_degrades**: last note of track has `legato_to_next`; assert no crash, degraded to `tenuto`.
7. **test_unknown_ornament_warns_not_crashes**: note with `["gibberish"]`; assert no exception.
8. **test_bend_clamped_to_range**: ornament that would produce bend > 8191 → clamped.
9. **test_golden_snapshot_erhu_chorus**: fixture Score with 8-note Erhu chorus → compare emitted events to checked-in expected JSON.

---

## Key Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Token budget overflow from untruncated instrument knowledge | `format_for_composer` is scoped: featured instrument gets full text, supporting gets summary, silent omitted. Budget guard trims least-relevant first. |
| Composer ignores ornament vocabulary and keeps writing bare notes | Prompt explicitly lists available ornaments per instrument + examples in `idiomatic_motifs`. Inner Critic scores `instrument_idiom` low if note list has 0 ornaments in featured sections. |
| Auto-rules over-add ornaments (every note gets vibrato) | Auto-rules only fire when conditions match AND the ornament isn't already present. Velocity/duration limits in rule conditions prevent spam. |
| Performance render inflates metrics mid-pipeline | Render runs in Phase 4 *after* all critics. Metrics computed on pre-render Score. |
| Spotlight proposal flood (every composer call submits one) | Confidence threshold gating (< 0.7 dropped silently). Proposals batched per outer iteration, not per composer call. |
| Orchestrator produces invalid spotlight_plan (unknown instruments, malformed sections) | `_ensure_spotlight_plan()` validates against blueprint instruments + enriched_sections; falls back to safe default on mismatch. |
| Lyricist re-prompt loop infinite | Capped at 2 re-prompts; after that, accept empty lyrics with warning. |
| Large renderer diff hard to review | Split `performance.py` into `performance.py` (dispatcher) + `performance_ornaments/*.py` (one file per ornament family: bends, vibratos, articulations, retriggers). |
| Existing MIDI output changes silently for old scores | `track.rendered=False` by default; `apply_performance_render` is explicit opt-in. Old scores without ornaments render identically. |

---

## Verification Plan

1. **Unit tests per step** (see Verify sections).
2. **Golden renderer snapshot**: checked-in fixture Score + expected MIDI events.
3. **Full-pipeline integration run** with the user's Neon Rain 雨夜霓虹 request:
   - Inspect final Score: Dizi/Erhu should have ZERO notes in intro, DENSE notes in chorus.
   - Inspect final MIDI: pitchwheel and CC1 messages present on Erhu/Dizi tracks during featured sections.
   - Listen to output: chorus entry of traditional instruments should be audibly contrasted.
4. **Token budget measurement**: log prompt sizes for Composer per-section, assert < 4000 tokens even with full instrument knowledge.
5. **Score plateau test**: run 3 outer iterations, log `overall_score` trajectory. Expect at least one score rise > 0.1 when spotlight proposal is accepted.

---

## Future Work Appendix (captured, not implemented in this spec)

### C. Knowledge Query Machine

User expressed interest in a retrieval system. We decided to start with curated JSON (implemented in Step 3 above). Future layers:

- **C1. Local RAG over music-theory texts**: chunk Adler's *Study of Orchestration*, 斯波索宾《和声学》, and user-supplied PDFs using bge-m3 embeddings into a local Chroma/LanceDB index. Expose as a `music_theory_query(question: str) -> list[str]` tool callable from Composer/Critic agents.
- **C2. Web search fallback**: Tavily or Serper API as an agent-callable tool for long-tail/current questions. Gated behind a "knowledge confidence low" signal. Legal note: 知乎 direct scraping violates their ToS and content is copyrighted; must use official search APIs or user-bookmarked passages only.

### D. Magenta Abstraction + Alternate Model Engines

Current `src/engine/magenta_engine.py:47–53` hard-codes Magenta regardless of `settings.music_engine`. Also Magenta service returns 500 errors in the user's logs. Future work:

- **D1. Fix `engine/interface.py` abstraction**: real factory that respects `settings.music_engine`.
- **D2. Add MusicLang Predict engine** (github.com/musiclang/musiclang_predict, BSD-3, chord-conditioned symbolic). Runs locally. Strong fit for modern pop harmony.
- **D3. Add Anticipatory Music Transformer** (Thickstun et al., Apache-2.0, infilling + conditional generation). Better for "complete this melody given these constraints" agent roles.
- **D4. Multi-model fanout**: run 2–3 engines in parallel for Phase 1 draft, give Composer agent all drafts as reference perspectives. Increases compute but provides diversity.
- **D5. Consider MMT (Multitrack Music Transformer)** for native ensemble output if single-track generation proves limiting.

Skipped: MusicGen/AudioCraft (audio, not MIDI), YuE/Suno (audio, not integrable with symbolic pipeline).

### E. Critic Feedback Loop Overhaul

Scores plateau at 0.55–0.65. Root causes identified in exploration:

- `pipeline.py:858–860` — critic feedback reaches only the FIRST section of each round. Other sections get empty feedback.
- Critic has no iteration-delta visibility — judges each round in isolation.
- Instrumentalist/Lyricist never see `revision_instructions`.
- Aspect scores naively averaged — LLM settles at 0.6 per aspect.

Future fixes:

- **E1. Every-section feedback**: pass `critic_feedback` to Composer on all sections, not just first.
- **E2. Iteration delta prompts**: critic receives `previous_score_summary` + `current_score_summary` + metric deltas and must explain what changed and why.
- **E3. Structured revision routing**: parse `revision_instructions` into per-agent substrings; inject the Composer part into the next Composer call, Instrumentalist part into Instrumentalist, etc.
- **E4. Weighted aspect scoring**: `overall_score = sum(aspect * weight)` with explicit per-aspect weights in settings. Prevents "safe 0.6 average".
- **E5. Plateau detection**: if score unchanged > N rounds, force hard reset or switch prompt style.

### F. Full Lyrics Alignment (beyond minimum guarantee)

This spec adds only "≥4 lines on featured sections" re-prompt guard (Step 8e). Larger future work:

- **F1. Lyrics-driven melody rhythm**: generate lyrics FIRST in featured sections; Composer generates melody to fit lyric rhythm. Reverses current order.
- **F2. Tonal alignment for Chinese lyrics**: check character tone (阴平/阳平/上声/去声) against melody contour; warn when falling tone on ascending pitch.
- **F3. `lyrics_alignment_pct` feedback loop**: currently computed, shown to Critic, but never returned to Lyricist/Composer. Fix the loop.
- **F4. Syllable density planner**: per-section target density (e.g., verse = 1 syllable/beat, chorus = 0.5 syllable/beat for sustained melismas).

### G. Statistical MIDI Corpus Mining

User flagged this as "future potential" when answering questions. Future work:

- **G1. Build local extractor**: analyze POP909, MAESTRO, any Chinese-instrument performance MIDI you can license/download. Compute per-instrument velocity histograms, IOI distributions, pitch-bend usage patterns.
- **G2. Surface as agent tool**: `query_performance_stats(instrument, section_role) -> dict` — returns expected velocity range, typical ornament frequency, typical IOI patterns.
- **G3. Use stats to refine `auto_rules`**: replace hand-tuned thresholds with data-driven ones.
- Public Chinese-instrument performance MIDI is scarce (CBFdataset is audio+annotations; Jingju datasets are score/audio) — may require transcription or user-supplied corpus.

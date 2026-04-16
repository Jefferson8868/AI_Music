# Nested Loop Pipeline Redesign

## Problem

The current single-loop pipeline produces sparse, disconnected music because:

1. **No anchor melody.** The Composer writes ALL instrument tracks simultaneously in one pass. No instrument gets enough creative focus to form a compelling melodic line.
2. **No ensemble logic.** Instruments are generated as parallel equals without sequential layering (lead first, then accompaniment against lead, etc.).
3. **No density awareness.** Agents have no tools to see gaps (e.g., "bar 7 has zero notes"). No post-processing catches sparsity.
4. **No continuity enforcement.** Sections end abruptly. No overlap context or transition requirements.

Evidence: comparing the reference piano score (122 BPM, dense melody + accompaniment) against generated output (80 BPM, 5 sparse instruments with frequent gaps).

## Solution: 3-Phase Nested Loop Architecture

### Phase 1: Initialization (unchanged)

```
User Request → Orchestrator → Blueprint (title, key, tempo, sections, instruments, roles)
                                  ↓
                           Synthesizer → Magenta draft MIDI
```

### Phase 2: Main Score Creation (NEW)

Produces a **lead sheet** — the song's identity, independent of any specific instrument:

| Component | Description | Format |
|-----------|-------------|--------|
| **Melody** | Single-voice melody line with specific notes | `list[ScoreNote]` |
| **Chord progression** | Root + quality per bar | `[{bar, root, quality}]` |
| **Rhythm density guide** | Per-section note density targets | `{section_name: "4-6 notes/bar"}` |
| **Instrument distribution plan** | Which instrument does what where | `{instrument: "lead in verse, rest in chorus"}` |

**Agents involved:**
- Composer: writes the lead sheet (melody + chords)
- Lyricist: aligns lyrics to the melody
- Structural Critic: reviews the lead sheet for melodic quality, harmonic coherence, and section contrast

**Data model addition:**
```python
class MainScore:
    melody: list[ScoreNote]
    chord_progression: list[dict]     # [{bar, root, quality}]
    rhythm_guide: dict[str, str]      # {section_name: density description}
    instrument_plan: dict[str, str]   # {instrument_name: role description}
```

### Phase 3: Nested Refinement (REDESIGNED)

```
Outer Loop (max K=3 iterations):
│
├── For each instrument in priority order:
│   │
│   └── Inner Loop (max M=2 iterations):
│       ├── Composer: writes/refines notes for THIS instrument only
│       │   Context: main score + previously arranged instruments + tools
│       ├── Instrumentalist: articulations + technique mapping
│       └── Instrument Critic: evaluates this instrument's part
│           ├── PASS → exit inner loop early
│           └── FAIL → feedback → next inner iteration
│
├── Ensemble Critic: reviews full orchestration
│   ├── PASS → final output
│   └── FAIL → revision_instructions
│       ├── main_score_changes → Phase 2 re-runs, then all inner loops re-run
│       ├── instrument_reruns: [list] → only these instruments re-run inner loops
│       └── keep_instruments: [list] → frozen, carried forward
│
└── Next outer iteration
```

**Instrument priority order** (derived from blueprint roles):
1. Lead (e.g., guzheng, piano melody)
2. Counter-melody (e.g., erhu, dizi)
3. Accompaniment (e.g., pipa, yangqin)
4. Bass (e.g., cello, contrabass)
5. Pad (e.g., sustained strings, xiao)

Each instrument's inner loop sees all previously arranged instruments' parts, so the erhu knows what the guzheng wrote.

## Agent Inspection Tools

### Tool 1: Density Heatmap (`compute_density_heatmap`)

Bar-by-bar note count per track with visual indicators and gap flags:

```
Bar  1: Guzheng ████░░░░ (4)  Erhu ░░░░░░░░ (0)  Cello ██░░░░░░ (2)
Bar  2: Guzheng ██████░░ (6)  Erhu ██░░░░░░ (2)  Cello ██░░░░░░ (2)
Bar  3: Guzheng ░░░░░░░░ (0)  Erhu ░░░░░░░░ (0)  Cello █░░░░░░░ (1)  ⚠️ GAP
```

Injected into Composer and Critic prompts.

### Tool 2: Bar-by-Bar Note Grid (`compute_note_grid`)

Text piano-roll showing exact note positions within a bar:

```
Bar 5 (beats 17.0-20.0), Guzheng:
  beat: 17.0  17.5  18.0  18.5  19.0  19.5
  note:  G4   ---   A4    B4   ---   D5
  dur:  0.5         0.5   0.5        1.0
  vel:   75          80    80         85
```

Used when inner-loop Composer needs to see exactly what exists.

### Tool 3: Gap Detector (`detect_gaps`)

Identifies density violations against role-based minimums:

```
⚠️ GAPS DETECTED:
  Guzheng: bars 3, 7-8 (0 notes) — min 4 notes/bar for lead
  Erhu: bars 1-4 (0 notes) — expected entry at verse
  Overall: 12/32 bars below minimum density
```

Injected into Critic prompts. Blocks PASS if critical gaps remain.

### Tool 4: Register & Range Coverage (`compute_register_coverage`)

Shows octave usage per instrument against sweet spot:

```
Guzheng: ░░░████████░░░ (G3-D5, sweet spot: G3-C5 ✓)
Erhu:    ░░░░░██░░░░░░ (A4-D5 — too narrow, expected G3-D6)
```

## Continuity Strategy

Three layers working together:

### Layer 1: Minimum Density Floors (Hard — blocks Critic PASS)

| Role | Min notes/bar | Enforcement |
|------|--------------|-------------|
| Lead | 4 | Gap Detector flags, Critic blocks pass |
| Counter-melody | 2 | Gap Detector flags, Critic blocks pass |
| Accompaniment | 2 | Gap Detector flags |
| Bass | 1 | Gap Detector flags |
| Pad | 1 per 2 bars | Gap Detector flags |

These are NOT auto-filled. The Critic sees the violation and instructs the Composer to fix it.

### Layer 2: Overlap Context (Soft — prompt engineering)

When composing section N for any instrument, the Composer prompt includes:
- Last 4 beats of section N-1 (actual notes)
- First 4 beats of section N+1 (if written; otherwise main score melody)
- Explicit instruction: "The last note of section N-1 is [X]. Create a smooth voice-leading connection."

### Layer 3: Transition Requirements (Checked by Critic)

- Last 2 beats of each section must not be empty for lead/counter-melody
- First beat of a section should be within a 3rd interval of the previous section's last note
- No sudden velocity jumps > 30 across section boundaries

## Information Flow Per Inner Loop

```
Inner Loop for instrument X (iteration i):

  Composer receives:
    ├── Main score (melody + chords + rhythm guide)
    ├── Instrument distribution plan ("you are lead in verse, counter in chorus")
    ├── Previously arranged instruments' note grids (read-only)
    ├── Density heatmap for instrument X (if i > 1)
    ├── Gap detector output for instrument X
    ├── Overlap context (adjacent sections' boundary notes)
    ├── Instrument X's knowledge card (range, techniques, intervals)
    └── Inner Critic feedback from iteration i-1 (if any)

  Instrumentalist receives:
    ├── Instrument X's notes (just written by Composer)
    ├── Instrument X's technique guide
    └── Main score chord progression (for harmonic-aware articulation)

  Inner Critic receives:
    ├── Instrument X's notes + articulations
    ├── Density heatmap + gap detector
    ├── Register coverage
    ├── Main score (alignment check)
    └── Previously arranged instruments (ensemble fit check)
```

## Cross-Loop Propagation

When the Ensemble Critic requests changes:

```json
{
  "main_score_changes": "Chorus melody needs stronger climax",
  "instrument_reruns": ["guzheng", "erhu"],
  "keep_instruments": ["cello", "pipa"],
  "distribution_update": "Erhu doubles guzheng in chorus"
}
```

1. If `main_score_changes` is non-null → Phase 2 re-runs (Composer updates lead sheet, Lyricist realigns lyrics to updated melody)
2. Only instruments in `instrument_reruns` get their inner loops re-run (all other instruments are implicitly in `keep_instruments`)
3. Instruments in `keep_instruments` are frozen — their notes carry forward
4. Updated `distribution_update` is injected into inner loop prompts

## Configuration Additions

New settings in `config/settings.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `max_outer_loops` | 3 | Max outer loop iterations |
| `max_inner_loops` | 2 | Max inner loop iterations per instrument |
| `min_density_lead` | 4 | Min notes/bar for lead role |
| `min_density_counter` | 2 | Min notes/bar for counter-melody |
| `min_density_accomp` | 2 | Min notes/bar for accompaniment |
| `min_density_bass` | 1 | Min notes/bar for bass |
| `inner_critic_threshold` | 0.75 | Inner Critic pass score |
| `ensemble_critic_threshold` | 0.80 | Ensemble Critic pass score |

## Files to Modify

| File | Changes |
|------|---------|
| `src/agents/pipeline.py` | Rewrite Phase 2 & 3 with nested loop logic |
| `src/music/score.py` | Add `MainScore` class, density heatmap, note grid, gap detector, register coverage tools |
| `src/llm/prompts.py` | New prompts for Phase 2 Composer (lead sheet), inner-loop Composer (per-instrument), inner Critic, Ensemble Critic |
| `config/settings.py` | Add nested loop configuration parameters |
| `src/agents/critic.py` | Support 3 modes: Structural Critic (Phase 2, lead sheet), Inner Critic (per-instrument), Ensemble Critic (full orchestration) |
| `src/agents/composer.py` | Support lead-sheet mode vs instrument-arrangement mode |

## Verification

1. Run the full pipeline with a test request (e.g., Chinese folk song with guzheng, erhu, dizi, cello)
2. Compare output MIDI density: each instrument should have >= minimum notes/bar for its role
3. Check round snapshots: `output/drafts/` should show progressive improvement
4. Listen to transitions: section boundaries should connect smoothly
5. Compare total note count against the sparse reference — should be significantly higher
6. Verify inner loop early exit: if instrument passes on iteration 1, iteration 2 is skipped

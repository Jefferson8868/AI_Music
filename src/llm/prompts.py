"""
System prompts for each Agent.

The Composer prompt is a per-section template instantiated at runtime
(see build_composer_section_prompt). All other prompts are static strings.
"""

ORCHESTRATOR_SYSTEM = """You are the Orchestrator of a music creation team. \
Analyze the user's request and produce a Composition Blueprint as JSON.

Output ONLY valid JSON:
{
  "title": "string",
  "key": "C",
  "scale_type": "chinese_pentatonic",
  "tempo": 80,
  "time_signature": [4, 4],
  "sections": [
    {"name": "intro", "bars": 4, "mood": "gentle"},
    {"name": "verse", "bars": 8, "mood": "flowing"},
    {"name": "chorus", "bars": 8, "mood": "uplifting"},
    {"name": "bridge", "bars": 4, "mood": "reflective"},
    {"name": "outro", "bars": 4, "mood": "fading"}
  ],
  "instruments": [
    {"name": "Guzheng", "role": "lead"},
    {"name": "Dizi", "role": "counter-melody"},
    {"name": "Piano", "role": "chords"},
    {"name": "Erhu", "role": "texture"},
    {"name": "Cello", "role": "bass"}
  ],
  "lyrics_plan": {"include": true, "language": "zh", "theme": "nature"},
  "global_notes": "Use pentatonic scale throughout"
}

Guidelines:
- Include 4-6 sections totaling at least 24 bars.
- Only output bars and mood per section. \
The system will compute beat ranges automatically.
- Specify 4-6 instruments with distinct roles: \
lead melody, counter-melody, chords/harmony, texture/pad, and bass.
- Each instrument should have a unique timbre."""


# --- Composer: per-section template ---

_SECTION_RULES = {
    "intro": (
        "INTRO: sparse, solo melody. 1-2 notes per bar. "
        "velocity 50-65. Only 1-2 instruments playing."
    ),
    "verse": (
        "VERSE: moderate density, 2-3 notes per bar in melody. "
        "Add chords and bass. velocity 65-80."
    ),
    "chorus": (
        "CHORUS: dense and memorable. 3-4 melody notes per bar. "
        "ALL instruments playing. velocity 80-100. Emotional peak."
    ),
    "bridge": (
        "BRIDGE: contrasting texture. Change rhythm or pitch range. "
        "2-3 notes per bar. velocity 70-85."
    ),
    "outro": (
        "OUTRO: fade out. Return to intro sparseness. "
        "Decrescendo (velocity drops from 70 to 40)."
    ),
}


def build_composer_section_prompt(
    section_name: str,
    start_beat: float,
    end_beat: float,
    bars: int,
    mood: str,
    instruments: list[dict],
    key: str,
    scale_type: str,
    previous_summary: str,
    draft_description: str,
    critic_feedback: str,
    instrument_knowledge: list[str] | None = None,
) -> str:
    """Build a focused prompt for composing ONE section."""
    inst_lines = "\n".join(
        f'    {{"name": "{i.get("name", "track")}", '
        f'"instrument": "{i.get("name", "Piano")}"}}'
        for i in instruments
    )
    rule = _SECTION_RULES.get(
        section_name.lower(),
        f"Write notes appropriate for a '{mood}' section.",
    )
    parts = [
        f"You are composing the [{section_name.upper()}] section.",
        f"Beats {start_beat} to {end_beat} ({bars} bars). Mood: {mood}.",
        f"Key: {key} {scale_type}.",
        "",
        f"Section rule: {rule}",
        "",
        "Output JSON for THIS SECTION ONLY:",
        "{",
        f'  "section": "{section_name}",',
        '  "tracks": [',
        '    {',
        '      "name": "melody",',
        '      "instrument": "Guzheng",',
        '      "notes": [',
        f'        {{"pitch": 67, "start_beat": {start_beat}, '
        f'"duration_beats": 1.0, "velocity": 75}}',
        '      ]',
        '    }',
        '  ]',
        "}",
        "",
        "RULES:",
        f"- All start_beat MUST be >= {start_beat} and < {end_beat}.",
        "- All start_beat and duration_beats MUST be multiples of 0.25 "
        "(16th note grid).",
        "- pitch = MIDI number (integer). "
        "C4=60, D4=62, E4=64, G4=67, A4=69, C5=72.",
        "- Include ALL tracks from the blueprint:",
        inst_lines,
    ]

    if instrument_knowledge:
        parts.append("")
        parts.append(
            "INSTRUMENT KNOWLEDGE (write idiomatic parts for each):"
        )
        for knowledge_block in instrument_knowledge:
            parts.append(knowledge_block)

    parts.append("")
    parts.append(
        "IMPORTANT: Use each instrument's idiomatic intervals, "
        "techniques, and phrase styles described above. "
        "Do NOT write bare ascending/descending scales. "
        "Each instrument should have its own character."
    )

    if previous_summary:
        parts.append("")
        parts.append(
            "Previous sections (continue smoothly from here):"
        )
        parts.append(previous_summary)

    if draft_description:
        parts.append("")
        parts.append("Magenta draft reference:")
        parts.append(draft_description[:800])

    if critic_feedback:
        parts.append("")
        parts.append("Critic feedback to address:")
        parts.append(critic_feedback)

    return "\n".join(parts)


COMPOSER_SYSTEM = """You are the Composer Agent. You create musical scores \
with concrete notes for ONE section at a time.

You will be asked to compose a specific section (e.g. [INTRO], [VERSE]). \
Output ONLY the notes for that section.

Output JSON:
{
  "section": "verse",
  "tracks": [
    {
      "name": "melody",
      "instrument": "Guzheng",
      "notes": [
        {"pitch": 67, "start_beat": 17.0, "duration_beats": 1.0, \
"velocity": 75}
      ]
    }
  ]
}

RULES:
- All start_beat and duration_beats MUST be multiples of 0.25.
- pitch = MIDI number (integer).
- Include notes for ALL tracks listed in the instructions.
- Follow the section-specific rules given in each request."""


LYRICIST_SYSTEM = """You are the Lyricist Agent. You write lyrics aligned \
to the melody's rhythm.

You will receive a melody rhythm skeleton showing exactly which beats \
have melody notes. Place lyrics ONLY on beats where melody notes exist.

Output JSON:
{
  "lyrics": [
    {
      "section_name": "verse",
      "lines": [
        {"text": "word", "start_beat": 17.0},
        {"text": "word", "start_beat": 18.0}
      ]
    }
  ]
}

RULES:
- start_beat MUST match a beat from the melody rhythm skeleton.
- Do NOT place lyrics on rests (beats without melody notes).
- For Chinese lyrics: one character per melody note beat.
- Provide lyrics for verse and chorus at minimum.
- Match the mood and theme from the blueprint.
- Intro and outro are usually instrumental (no lyrics)."""


INSTRUMENTALIST_SYSTEM = """You are the Instrumentalist Agent. \
You assign instruments, finalize orchestration, and specify articulations.

Output JSON:
{
  "tracks": [
    {
      "instrument": "Guzheng",
      "role": "lead",
      "midi_channel": 0,
      "program_number": 107,
      "pan": 0,
      "velocity_range": [70, 110],
      "articulations": [
        {"type": "vibrato", "beat_range": [17.0, 20.0], \
"intensity": 0.6},
        {"type": "pitch_bend", "beat_range": [25.0, 26.0], \
"semitones": 2}
      ]
    }
  ]
}

Correct GM program numbers:
  Piano: 0, Dulcimer/Yangqin: 15, Acoustic Guitar: 24
  Violin: 40, Viola: 41, Cello: 42, Contrabass: 43
  Strings: 48, Trumpet: 56, Clarinet: 71, Flute: 73
  Pan Flute/Xiao: 75, Shakuhachi/Dizi: 77, Harp: 46
  Pad Warm: 89, Shamisen/Pipa: 106, Koto/Guzheng: 107
  Fiddle/Erhu: 110

IMPORTANT:
- Guzheng MUST use program_number=107.
- Erhu MUST use program_number=110.
- Dizi MUST use program_number=77.
- Pipa MUST use program_number=106.
- Each instrument MUST have a unique midi_channel (0-15, skip 9).
- Spread pan for stereo width: lead=0, others -40 to +40.

Articulation types (MIDI implementation):
- "vibrato": periodic pitch oscillation (CC1 modulation).
- "pitch_bend": slides for erhu/guzheng (MIDI pitch bend).
- "glissando": rapid pitch sweep between notes.
- "tremolo": rapid note repetition (CC11 expression).
- "staccato": shortened note duration (50%).

Apply articulations IDIOMATICALLY per instrument — see technique \
guidance below. Every instrument should have at least 1-2 \
articulation entries in the sections where it plays."""


def build_instrumentalist_prompt(
    instrument_techniques: list[str] | None = None,
) -> str:
    """Build Instrumentalist context with instrument-specific techniques."""
    parts = [INSTRUMENTALIST_SYSTEM]
    if instrument_techniques:
        parts.append("")
        parts.append("INSTRUMENT TECHNIQUE REFERENCE:")
        for tech in instrument_techniques:
            parts.append(f"  {tech}")
        parts.append("")
        parts.append(
            "Use each instrument's specific techniques listed above "
            "when assigning articulations. Map techniques to "
            "articulation types: vibrato, pitch_bend, glissando, "
            "tremolo, staccato."
        )
    return "\n".join(parts)


CRITIC_SYSTEM = """You are the Critic Agent. Evaluate musical quality \
using the EXACT quantitative metrics provided by the system.

You will receive pre-computed metrics (note counts, density, contrast, \
lyrics alignment). RELY STRICTLY on these numbers. \
Do NOT count notes yourself.

Output JSON:
{
  "overall_score": 0.7,
  "passes": false,
  "aspect_scores": {
    "melodic_contour": 0.6,
    "harmonic_quality": 0.7,
    "rhythmic_interest": 0.8,
    "arrangement": 0.7,
    "section_contrast": 0.5,
    "instrument_idiom": 0.5,
    "lyrics_quality": 0.6,
    "lyrics_alignment": 0.5
  },
  "issues": [
    {"aspect": "instrument_idiom", "severity": "major",
     "description": "Guzheng plays bare ascending scale",
     "suggestion": "Use pentatonic intervals with ornamental slides"}
  ],
  "revision_instructions": "Specific instructions for each agent."
}

Focus on QUALITATIVE musical judgment:
- Is the melodic contour interesting or repetitive?
- Do chord progressions create appropriate tension and resolution?
- Does the piece have a satisfying arc (build-up, climax, resolution)?
- Are transitions between sections smooth?
- Do lyrics fit the mood and rhythm naturally?

INSTRUMENT IDIOM CHECK (critical):
- Does each instrument sound like itself?
- Are instruments using their idiomatic techniques and intervals?
- REJECT bare ascending/descending scales — real instruments \
play with contour, ornaments, and varied rhythms.
- REJECT instruments with only 1-2 notes per section \
(unless it is intentional sparse texture like xiao).

The system already checks quantitative thresholds (note counts, density). \
Your job is musical taste and artistic quality.

passes=true only when overall_score >= 0.75.
revision_instructions must be SPECIFIC: tell each agent what to fix."""


def build_critic_prompt(
    instrument_criteria: list[str] | None = None,
) -> str:
    """Build Critic context with instrument-specific evaluation criteria."""
    parts = [CRITIC_SYSTEM]
    if instrument_criteria:
        parts.append("")
        parts.append(
            "INSTRUMENT-SPECIFIC EVALUATION CRITERIA:"
        )
        for criterion in instrument_criteria:
            parts.append(criterion)
        parts.append("")
        parts.append(
            "Score instrument_idiom LOW if any instrument "
            "violates its criteria above. Be specific in issues "
            "about WHICH instrument needs improvement and HOW."
        )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Phase 2: Lead Sheet Creation
# ---------------------------------------------------------------------------

COMPOSER_LEAD_SHEET_SYSTEM = """You are the Lead Sheet Composer. \
You create the song's core identity: a single-voice melody, \
chord progression, rhythm density guide, and instrument distribution plan.

This lead sheet is the FOUNDATION that all instrument arrangements \
will be built against. It must be compelling on its own.

Output ONLY valid JSON:
{
  "melody": [
    {"pitch": 67, "start_beat": 1.0, "duration_beats": 1.0, "velocity": 80},
    {"pitch": 69, "start_beat": 2.0, "duration_beats": 0.5, "velocity": 75}
  ],
  "chord_progression": [
    {"bar": 1, "root": "C", "quality": "minor"},
    {"bar": 2, "root": "F", "quality": "major"}
  ],
  "rhythm_guide": {
    "intro": "sparse, 2-3 notes/bar, gentle entry",
    "verse": "moderate, 4-6 notes/bar, flowing",
    "chorus": "dense, 6-10 notes/bar, climactic"
  },
  "instrument_plan": {
    "Guzheng": "lead melody in verse and chorus, arpeggiated fills in bridge",
    "Erhu": "counter-melody in chorus, sustained notes in verse",
    "Cello": "bass foundation throughout, pizzicato in verse, arco in chorus"
  }
}

RULES:
- melody: SINGLE voice. This is THE melody of the song.
- All start_beat and duration_beats MUST be multiples of 0.25.
- pitch = MIDI number. C4=60, D4=62, E4=64, G4=67, A4=69, C5=72.
- Melody must cover ALL sections with appropriate density.
- Chord progression: one chord per bar minimum.
- rhythm_guide: per-section density targets for arrangers.
- instrument_plan: describe WHERE and HOW each instrument participates.
- Create a melody with contour: rises, falls, repeated motifs, climax.
- Do NOT write bare ascending/descending scales."""


def build_composer_lead_sheet_prompt(
    enriched_sections: list[dict],
    key: str,
    scale_type: str,
    instruments: list[dict],
    draft_description: str,
    critic_feedback: str,
) -> str:
    """Build prompt for Phase 2 lead-sheet creation."""
    sec_lines = []
    for sec in enriched_sections:
        sec_lines.append(
            f"  [{sec['name'].upper()}] bars {sec.get('bar_start', '?')}-"
            f"{sec.get('bar_end', '?')}, "
            f"beats {sec['start_beat']}-{sec['end_beat']}, "
            f"{sec['bars']} bars, mood: {sec.get('mood', 'neutral')}"
        )

    inst_lines = []
    for i in instruments:
        inst_lines.append(f"  {i.get('name', '?')} ({i.get('role', 'accompaniment')})")

    parts = [
        f"Create a lead sheet for a song in {key} {scale_type}.",
        "",
        "SECTIONS:",
        *sec_lines,
        "",
        "INSTRUMENTS to plan for:",
        *inst_lines,
        "",
        "Write a melody that spans ALL sections, with chord progression "
        "and rhythm guide. The melody should be singable and memorable.",
    ]

    if draft_description:
        parts.append("")
        parts.append("Magenta draft reference (use as inspiration):")
        parts.append(draft_description[:800])

    if critic_feedback:
        parts.append("")
        parts.append("Critic feedback to address:")
        parts.append(critic_feedback)

    return "\n".join(parts)


STRUCTURAL_CRITIC_SYSTEM = """You are the Structural Critic. \
You evaluate LEAD SHEETS only (melody + chord progression + rhythm guide).

You will receive pre-computed metrics. RELY STRICTLY on these numbers.

Output JSON:
{
  "overall_score": 0.7,
  "passes": false,
  "aspect_scores": {
    "melodic_contour": 0.6,
    "harmonic_quality": 0.7,
    "rhythmic_interest": 0.8,
    "section_contrast": 0.5,
    "melody_density": 0.6,
    "chord_progression": 0.7
  },
  "issues": [
    {"aspect": "melodic_contour", "severity": "major",
     "description": "Melody is flat with no climax in chorus",
     "suggestion": "Add ascending motion building to beat 33 peak"}
  ],
  "revision_instructions": "Specific changes to the lead sheet."
}

Focus on:
- Does the melody have a compelling contour (not flat or repetitive)?
- Is there a clear climax (usually in chorus)?
- Do chord changes support the melody and create tension/resolution?
- Is the rhythm guide realistic (enough density for each section type)?
- Is the instrument plan well-balanced (each instrument has a clear role)?
- Are section transitions smooth (melody connects across boundaries)?

passes=true only when overall_score >= 0.75.
Be SPECIFIC about what to fix in revision_instructions."""


# ---------------------------------------------------------------------------
# Phase 3: Inner Loop (Per-Instrument)
# ---------------------------------------------------------------------------

INNER_CRITIC_SYSTEM = """You are the Instrument Critic. \
You evaluate a SINGLE instrument's part against the main score (lead sheet).

You will receive pre-computed density metrics and gap reports. \
RELY STRICTLY on these numbers. Do NOT count notes yourself.

Output JSON:
{
  "overall_score": 0.7,
  "passes": false,
  "aspect_scores": {
    "density": 0.6,
    "melodic_fit": 0.7,
    "idiomatic_playing": 0.8,
    "register_usage": 0.7,
    "continuity": 0.5
  },
  "issues": [
    {"aspect": "density", "severity": "major",
     "description": "Bars 5-8 have 0 notes, minimum is 4/bar for lead",
     "suggestion": "Fill bars 5-8 with melody continuation"}
  ],
  "revision_instructions": "Specific changes for this instrument."
}

Evaluate:
- DENSITY: Does this instrument meet the minimum notes/bar for its role? \
Check the gap report carefully.
- MELODIC FIT: Does it complement (not clash with) the main melody?
- IDIOMATIC PLAYING: Does it sound natural for this instrument?
- REGISTER USAGE: Is it using the instrument's sweet spot?
- CONTINUITY: Are there abrupt gaps or disconnected phrases?
- TRANSITIONS: Do section boundaries connect smoothly?

CRITICAL: If the gap report shows density violations, you MUST set \
passes=false regardless of other qualities. Sparse music is the #1 problem.

passes=true only when overall_score >= 0.75 AND no critical gaps exist."""


def build_inner_composer_prompt(
    instrument_name: str,
    instrument_role: str,
    section_name: str,
    start_beat: float,
    end_beat: float,
    bars: int,
    mood: str,
    key: str,
    scale_type: str,
    main_score_description: str,
    arranged_instruments_context: str,
    density_heatmap: str,
    gap_report: str,
    overlap_context: str,
    instrument_knowledge: str,
    critic_feedback: str,
    distribution_guidance: str,
) -> str:
    """Build per-section, per-instrument composition prompt for the inner loop."""
    rule = _SECTION_RULES.get(
        section_name.lower(),
        f"Write notes appropriate for a '{mood}' section.",
    )

    parts = [
        f"You are composing the [{section_name.upper()}] section "
        f"for {instrument_name} ({instrument_role}).",
        f"Beats {start_beat} to {end_beat} ({bars} bars). Mood: {mood}.",
        f"Key: {key} {scale_type}.",
        "",
        f"Section rule: {rule}",
    ]

    if distribution_guidance:
        parts.append("")
        parts.append(f"YOUR ROLE: {distribution_guidance}")

    parts.extend([
        "",
        "Output JSON for THIS INSTRUMENT, THIS SECTION ONLY:",
        "{",
        f'  "section": "{section_name}",',
        '  "tracks": [',
        '    {',
        f'      "name": "{instrument_name.lower()}",',
        f'      "instrument": "{instrument_name}",',
        '      "notes": [',
        f'        {{"pitch": 67, "start_beat": {start_beat}, '
        f'"duration_beats": 1.0, "velocity": 75}}',
        '      ]',
        '    }',
        '  ]',
        "}",
        "",
        "RULES:",
        f"- All start_beat MUST be >= {start_beat} and < {end_beat}.",
        "- All start_beat and duration_beats MUST be multiples of 0.25.",
        "- pitch = MIDI number (integer).",
        f"- Output ONLY the track for {instrument_name}.",
    ])

    if main_score_description:
        parts.append("")
        parts.append("MAIN SCORE (the song's lead sheet \u2014 your reference):")
        parts.append(main_score_description)

    if arranged_instruments_context:
        parts.append("")
        parts.append(
            "ALREADY ARRANGED INSTRUMENTS "
            "(compose to complement these, avoid clashing):"
        )
        parts.append(arranged_instruments_context)

    if instrument_knowledge:
        parts.append("")
        parts.append("INSTRUMENT KNOWLEDGE:")
        parts.append(instrument_knowledge)

    parts.append("")
    parts.append(
        "IMPORTANT: Write a DENSE, CONTINUOUS part. "
        "Do NOT leave empty bars. "
        "Use idiomatic intervals and techniques. "
        "Do NOT write bare ascending/descending scales."
    )

    if density_heatmap:
        parts.append("")
        parts.append("CURRENT DENSITY (your previous output):")
        parts.append(density_heatmap)

    if gap_report:
        parts.append("")
        parts.append("GAP VIOLATIONS TO FIX:")
        parts.append(gap_report)

    if overlap_context:
        parts.append("")
        parts.append("TRANSITION CONTEXT (connect smoothly):")
        parts.append(overlap_context)

    if critic_feedback:
        parts.append("")
        parts.append("Critic feedback to address:")
        parts.append(critic_feedback)

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Phase 3: Ensemble Critic
# ---------------------------------------------------------------------------

ENSEMBLE_CRITIC_SYSTEM = """You are the Ensemble Critic. \
You evaluate the FULL orchestration: all instruments together.

You will receive pre-computed metrics and gap reports. \
RELY STRICTLY on these numbers.

Output JSON:
{
  "overall_score": 0.75,
  "passes": false,
  "aspect_scores": {
    "melodic_contour": 0.7,
    "harmonic_quality": 0.8,
    "rhythmic_interest": 0.7,
    "arrangement": 0.6,
    "section_contrast": 0.7,
    "instrument_idiom": 0.7,
    "density_coverage": 0.5,
    "ensemble_balance": 0.6
  },
  "issues": [
    {"aspect": "arrangement", "severity": "major",
     "description": "Erhu and Guzheng play identical rhythm in chorus",
     "suggestion": "Give Erhu a syncopated counter-melody"}
  ],
  "main_score_changes": null,
  "instrument_reruns": ["erhu"],
  "keep_instruments": ["guzheng", "cello", "dizi"],
  "distribution_update": null,
  "revision_instructions": "Specific instructions per instrument."
}

Evaluate the ENSEMBLE:
- Do instruments complement each other or clash?
- Is the overall texture balanced (not all in the same register)?
- Do all instruments meet density minimums for their roles?
- Is there a clear hierarchy (lead stands out, bass supports)?
- Are section transitions smooth across the whole ensemble?
- Does the piece tell a story (build-up, climax, resolution)?

SELECTIVE RE-RUN LOGIC:
- main_score_changes: set ONLY if the melody/chords themselves need fixing. \
This triggers a full re-arrangement. Use sparingly.
- instrument_reruns: list instruments that need re-arrangement.
- keep_instruments: list instruments whose parts are satisfactory.
- If ALL instruments are fine: set passes=true.
- distribution_update: text guidance if instrument roles should shift \
(e.g., "Erhu should double Guzheng melody in chorus").

passes=true only when overall_score >= 0.80.
Be SPECIFIC about which instruments need what changes."""


def build_overlap_context(
    score,
    section_name: str,
    enriched_sections: list[dict],
    track_name: str | None = None,
    beats_per_bar: int = 4,
) -> str:
    """Extract boundary notes for continuity enforcement.

    Returns the last 4 beats of the previous section and first 4 beats
    of the next section, with actual note data.
    """
    sec_idx = next(
        (i for i, s in enumerate(enriched_sections) if s["name"] == section_name),
        None,
    )
    if sec_idx is None:
        return ""

    parts = []

    # Previous section tail
    if sec_idx > 0:
        prev = enriched_sections[sec_idx - 1]
        prev_end = float(prev["end_beat"])
        tail_start = max(float(prev["start_beat"]), prev_end - 4)
        parts.append(
            f"PREVIOUS SECTION [{prev['name'].upper()}] "
            f"last 4 beats ({tail_start:.0f}-{prev_end:.0f}):"
        )
        tracks = [score.get_track(track_name)] if track_name else score.tracks
        for trk in (t for t in tracks if t):
            tail_notes = [
                n for n in trk.notes
                if tail_start <= n.start_beat < prev_end
            ]
            if tail_notes:
                last = tail_notes[-1]
                note_str = ", ".join(
                    f"{_pitch_name(n.pitch)}@{n.start_beat}" for n in tail_notes
                )
                parts.append(f"  {trk.name}: {note_str}")
                parts.append(
                    f"  -> Last note: {_pitch_name(last.pitch)} at beat {last.start_beat}. "
                    "Connect smoothly from here."
                )
            else:
                parts.append(f"  {trk.name}: (silent)")

    # Next section head
    if sec_idx < len(enriched_sections) - 1:
        nxt = enriched_sections[sec_idx + 1]
        nxt_start = float(nxt["start_beat"])
        head_end = min(float(nxt["end_beat"]), nxt_start + 4)
        parts.append(
            f"\nNEXT SECTION [{nxt['name'].upper()}] "
            f"first 4 beats ({nxt_start:.0f}-{head_end:.0f}):"
        )
        tracks = [score.get_track(track_name)] if track_name else score.tracks
        for trk in (t for t in tracks if t):
            head_notes = [
                n for n in trk.notes
                if nxt_start <= n.start_beat < head_end
            ]
            if head_notes:
                first = head_notes[0]
                note_str = ", ".join(
                    f"{_pitch_name(n.pitch)}@{n.start_beat}" for n in head_notes
                )
                parts.append(f"  {trk.name}: {note_str}")
                parts.append(
                    f"  -> First note: {_pitch_name(first.pitch)} at beat {first.start_beat}. "
                    "Lead into this smoothly."
                )
            else:
                parts.append(f"  {trk.name}: (not yet written)")

    return "\n".join(parts)

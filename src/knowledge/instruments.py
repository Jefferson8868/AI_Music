"""
Instrument Knowledge Cards for idiomatic music generation.

Each card describes what makes an instrument sound authentic:
range, sweet spot, idiomatic intervals, techniques, role guidance,
and short example phrases for few-shot inspiration.

Example phrases use our ScoreNote format:
  {"pitch": MIDI, "start_beat": float, "duration_beats": float,
   "velocity": int}

Phrases are relative (start_beat begins at 0) so the pipeline can
offset them to any section.
"""

from __future__ import annotations

INSTRUMENT_CARDS: dict[str, dict] = {

    # =================================================================
    # EASTERN INSTRUMENTS
    # =================================================================

    "guzheng": {
        "name": "Guzheng (古筝)",
        "gm_program": 107,
        "range": (43, 96),
        "sweet_spot": (55, 84),
        "idiomatic_intervals": [2, 3, 5, 7, 12],
        "avoid_intervals": [1, 6, 11],
        "techniques": (
            "Glissando (刮奏): rapid sweeps across strings, often "
            "ascending or descending over 1-2 octaves. "
            "Tremolo (摇指): rapid repeated plucking on a single note "
            "for sustained singing tone. "
            "Arpeggio (琶音): broken chords across 4-5 strings. "
            "Slides (滑音): pitch bends up/down 1-2 semitones for "
            "expressive ornamentation. "
            "Harmonics (泛音): light touch producing bell-like tones."
        ),
        "role_guidance": {
            "lead": (
                "Play flowing pentatonic melodies with ornamental "
                "slides and occasional glissando sweeps. Use tremolo "
                "on long sustained notes. Vary dynamics between "
                "phrases — soft contemplative passages contrasting "
                "with bright energetic runs."
            ),
            "accompaniment": (
                "Use arpeggiated chord patterns (broken chords "
                "across 4-5 notes). Alternate between low-register "
                "bass notes and mid-register arpeggios. Add "
                "glissando sweeps at section transitions."
            ),
        },
        "example_phrases": [
            {
                "description": (
                    "Flowing pentatonic melody with ornamental slide"
                ),
                "notes": [
                    {"pitch": 67, "start_beat": 0.0,
                     "duration_beats": 0.75, "velocity": 80},
                    {"pitch": 69, "start_beat": 0.75,
                     "duration_beats": 0.5, "velocity": 75},
                    {"pitch": 72, "start_beat": 1.5,
                     "duration_beats": 1.0, "velocity": 85},
                    {"pitch": 74, "start_beat": 2.5,
                     "duration_beats": 0.5, "velocity": 70},
                    {"pitch": 72, "start_beat": 3.0,
                     "duration_beats": 0.5, "velocity": 75},
                    {"pitch": 69, "start_beat": 3.5,
                     "duration_beats": 1.0, "velocity": 80},
                    {"pitch": 67, "start_beat": 4.5,
                     "duration_beats": 0.75, "velocity": 70},
                    {"pitch": 64, "start_beat": 5.25,
                     "duration_beats": 0.75, "velocity": 65},
                ],
            },
            {
                "description": "Arpeggio pattern for accompaniment",
                "notes": [
                    {"pitch": 55, "start_beat": 0.0,
                     "duration_beats": 0.5, "velocity": 60},
                    {"pitch": 60, "start_beat": 0.25,
                     "duration_beats": 0.5, "velocity": 55},
                    {"pitch": 64, "start_beat": 0.5,
                     "duration_beats": 0.5, "velocity": 55},
                    {"pitch": 67, "start_beat": 0.75,
                     "duration_beats": 0.5, "velocity": 60},
                    {"pitch": 72, "start_beat": 1.0,
                     "duration_beats": 0.75, "velocity": 65},
                    {"pitch": 67, "start_beat": 1.75,
                     "duration_beats": 0.25, "velocity": 55},
                    {"pitch": 64, "start_beat": 2.0,
                     "duration_beats": 0.5, "velocity": 55},
                    {"pitch": 60, "start_beat": 2.5,
                     "duration_beats": 0.5, "velocity": 60},
                ],
            },
        ],
        "style_notes": (
            "Guzheng is tuned to pentatonic scales. Avoid chromatic "
            "movement (semitone steps). Use groups of 3-5 quick notes "
            "for ornamental runs between longer melodic tones. "
            "Dynamics should breathe — crescendo into phrase peaks, "
            "diminuendo at phrase endings. Silence between phrases "
            "is part of the expression."
        ),
        "critic_criteria": (
            "Guzheng part should use pentatonic intervals (2, 3, 5, "
            "7 semitones). Check for ornamental variety (slides, "
            "arpeggios, tremolo). Reject bare ascending/descending "
            "scales — real guzheng playing has contour, dynamics "
            "variation, and mixed note durations."
        ),
    },

    "erhu": {
        "name": "Erhu (二胡)",
        "gm_program": 110,
        "range": (55, 91),
        "sweet_spot": (60, 81),
        "idiomatic_intervals": [1, 2, 3, 5, 7],
        "avoid_intervals": [6, 11],
        "techniques": (
            "Portamento (滑音): continuous pitch slides between "
            "notes — the defining erhu characteristic. Use between "
            "most melodic intervals. "
            "Vibrato (揉弦): wide, expressive vibrato on sustained "
            "notes, deeper and slower than Western vibrato. "
            "Trills (颤音): rapid alternation with adjacent note. "
            "Bow pressure variation: light for ethereal, heavy for "
            "passionate."
        ),
        "role_guidance": {
            "lead": (
                "Play singing, vocal-like melodies. The erhu should "
                "sound like a human voice — use portamento slides "
                "between most intervals larger than a whole step. "
                "Sustain long notes with vibrato. Use varied "
                "rhythms: mix long sustained notes with quick "
                "ornamental groups of 2-3 short notes."
            ),
            "texture": (
                "Provide a sustained, singing countermelody above "
                "or below the lead. Use long notes with vibrato "
                "and occasional melodic response phrases. "
                "Avoid single held notes per section — erhu "
                "should always have melodic motion."
            ),
        },
        "example_phrases": [
            {
                "description": (
                    "Singing melody with portamento and vibrato"
                ),
                "notes": [
                    {"pitch": 67, "start_beat": 0.0,
                     "duration_beats": 1.5, "velocity": 75},
                    {"pitch": 69, "start_beat": 1.5,
                     "duration_beats": 0.5, "velocity": 70},
                    {"pitch": 72, "start_beat": 2.0,
                     "duration_beats": 2.0, "velocity": 85},
                    {"pitch": 71, "start_beat": 4.0,
                     "duration_beats": 0.25, "velocity": 65},
                    {"pitch": 69, "start_beat": 4.25,
                     "duration_beats": 0.75, "velocity": 70},
                    {"pitch": 67, "start_beat": 5.0,
                     "duration_beats": 1.5, "velocity": 80},
                    {"pitch": 64, "start_beat": 6.5,
                     "duration_beats": 1.5, "velocity": 75},
                ],
            },
        ],
        "style_notes": (
            "Erhu is a bowed string instrument that imitates the "
            "human voice. NEVER write isolated single notes — erhu "
            "phrases should flow continuously. Use slides (pitch "
            "bend) on most intervals of 3+ semitones. Long notes "
            "need vibrato. Mix sustained notes (1-2 beats) with "
            "quick grace notes (0.25 beats) for vocal-like phrasing."
        ),
        "critic_criteria": (
            "Erhu should have flowing, connected phrases — not "
            "isolated single notes. Check for varied note durations "
            "(mix of long and short). Reject if erhu plays fewer "
            "than 3 notes per section or uses only uniform "
            "note lengths."
        ),
    },

    "dizi": {
        "name": "Dizi (笛子)",
        "gm_program": 77,
        "range": (60, 96),
        "sweet_spot": (65, 88),
        "idiomatic_intervals": [2, 3, 5, 7, 12],
        "avoid_intervals": [1, 6, 11],
        "techniques": (
            "Flutter tongue (花舌): rapid articulation producing "
            "a buzzing, energetic sound. "
            "Circular breathing: enables long unbroken phrases. "
            "Grace notes (装饰音): quick ornamental notes before "
            "main melody tones. "
            "Overtone jumps: leaping to harmonics for bright accents."
        ),
        "role_guidance": {
            "lead": (
                "Play bright, lively pentatonic melodies with "
                "quick ornamental grace notes. Dizi excels at "
                "rapid passages — use 16th-note runs of 3-4 notes "
                "leading into main melody tones. Alternate between "
                "high-register bright passages and mid-register "
                "lyrical phrases."
            ),
            "counter-melody": (
                "Provide playful responses to the main melody, "
                "often an octave higher. Use short, bright phrases "
                "in gaps between main melody phrases. Add quick "
                "ornamental runs as fills."
            ),
        },
        "example_phrases": [
            {
                "description": (
                    "Bright melody with grace note ornaments"
                ),
                "notes": [
                    {"pitch": 79, "start_beat": 0.0,
                     "duration_beats": 0.25, "velocity": 65},
                    {"pitch": 81, "start_beat": 0.25,
                     "duration_beats": 0.75, "velocity": 80},
                    {"pitch": 84, "start_beat": 1.0,
                     "duration_beats": 0.5, "velocity": 85},
                    {"pitch": 81, "start_beat": 1.5,
                     "duration_beats": 0.5, "velocity": 75},
                    {"pitch": 79, "start_beat": 2.0,
                     "duration_beats": 1.0, "velocity": 80},
                    {"pitch": 76, "start_beat": 3.0,
                     "duration_beats": 0.25, "velocity": 65},
                    {"pitch": 74, "start_beat": 3.25,
                     "duration_beats": 0.75, "velocity": 75},
                    {"pitch": 72, "start_beat": 4.0,
                     "duration_beats": 1.0, "velocity": 80},
                ],
            },
        ],
        "style_notes": (
            "Dizi is a bright, piercing bamboo flute. It excels at "
            "quick ornamental passages and lively melodies. Use "
            "grace notes (0.25 beat) before main notes. Avoid long "
            "static passages — dizi should be energetic and "
            "rhythmically active. Pentatonic scale is standard."
        ),
        "critic_criteria": (
            "Dizi should be rhythmically active with ornamental "
            "grace notes. Check for pentatonic intervals. Reject "
            "if dizi plays only long sustained notes — it should "
            "have at least some quick passages."
        ),
    },

    "pipa": {
        "name": "Pipa (琵琶)",
        "gm_program": 106,
        "range": (45, 93),
        "sweet_spot": (52, 84),
        "idiomatic_intervals": [1, 2, 3, 5, 7, 12],
        "avoid_intervals": [6, 11],
        "techniques": (
            "Tremolo (轮指): rapid finger rolls on a single note — "
            "the signature pipa technique, producing a sustained "
            "shimmering sound. "
            "Strumming (扫弦): aggressive full-string sweeps for "
            "dramatic accents. "
            "Bending (推拉): pushing strings sideways for pitch "
            "bends up to 2 semitones. "
            "Harmonics: bell-like tones at specific positions."
        ),
        "role_guidance": {
            "lead": (
                "Play virtuosic melodies mixing rapid tremolo "
                "passages with dramatic strummed chords. Pipa can "
                "be both delicate and explosive. Use tremolo (rapid "
                "repeated notes at same pitch) for sustained melody "
                "tones. Quick scalar runs of 4-6 notes between "
                "longer tones. Occasional dramatic low-string "
                "strums for emphasis."
            ),
            "accompaniment": (
                "Provide rhythmic drive with plucked patterns. "
                "Alternate between bass notes and higher arpeggios. "
                "Use tremolo on chord tones for sustained harmony. "
                "Add percussive strums at phrase boundaries."
            ),
        },
        "example_phrases": [
            {
                "description": (
                    "Virtuosic passage with tremolo and runs"
                ),
                "notes": [
                    {"pitch": 72, "start_beat": 0.0,
                     "duration_beats": 0.25, "velocity": 85},
                    {"pitch": 72, "start_beat": 0.25,
                     "duration_beats": 0.25, "velocity": 80},
                    {"pitch": 72, "start_beat": 0.5,
                     "duration_beats": 0.25, "velocity": 85},
                    {"pitch": 72, "start_beat": 0.75,
                     "duration_beats": 0.25, "velocity": 80},
                    {"pitch": 74, "start_beat": 1.0,
                     "duration_beats": 0.25, "velocity": 75},
                    {"pitch": 76, "start_beat": 1.25,
                     "duration_beats": 0.25, "velocity": 78},
                    {"pitch": 79, "start_beat": 1.5,
                     "duration_beats": 0.5, "velocity": 85},
                    {"pitch": 76, "start_beat": 2.0,
                     "duration_beats": 0.5, "velocity": 75},
                    {"pitch": 72, "start_beat": 2.5,
                     "duration_beats": 1.0, "velocity": 80},
                ],
            },
        ],
        "style_notes": (
            "Pipa is a plucked lute capable of both delicate "
            "melodies and fierce, percussive attacks. The tremolo "
            "technique (4 rapid notes on same pitch) is essential "
            "for sustaining melody notes. Unlike guzheng, pipa can "
            "use chromatic intervals. Mix tremolo passages, scalar "
            "runs, and dramatic pauses."
        ),
        "critic_criteria": (
            "Pipa should show dynamic range — both quiet melodic "
            "passages and louder dramatic moments. Check for "
            "varied articulation (tremolo, single plucks, runs). "
            "Reject if pipa plays only simple stepwise lines."
        ),
    },

    "xiao": {
        "name": "Xiao (箫)",
        "gm_program": 75,
        "range": (55, 84),
        "sweet_spot": (60, 79),
        "idiomatic_intervals": [2, 3, 5, 7],
        "avoid_intervals": [1, 6, 11],
        "techniques": (
            "Breathy tone: intentional air noise mixed with pitch "
            "for ethereal quality. "
            "Subtle vibrato: gentle, slow pitch wavering. "
            "Microtonal bends: slight pitch inflections at phrase "
            "endings. "
            "Silence: rests between phrases are integral to the "
            "aesthetic."
        ),
        "role_guidance": {
            "lead": (
                "Play slow, meditative melodies with space between "
                "phrases. Xiao is contemplative — use longer note "
                "durations (1-2 beats) with gentle dynamic curves. "
                "End phrases with gradual diminuendo. Leave rests "
                "of 1-2 beats between melodic phrases."
            ),
            "texture": (
                "Provide a quiet, ethereal background layer with "
                "very long sustained notes (2-4 beats) and gentle "
                "melodic fragments. Stay in the mid-low register "
                "for warmth."
            ),
        },
        "example_phrases": [
            {
                "description": "Meditative melody with breathing space",
                "notes": [
                    {"pitch": 67, "start_beat": 0.0,
                     "duration_beats": 2.0, "velocity": 60},
                    {"pitch": 69, "start_beat": 2.5,
                     "duration_beats": 1.5, "velocity": 55},
                    {"pitch": 72, "start_beat": 4.5,
                     "duration_beats": 2.0, "velocity": 65},
                    {"pitch": 69, "start_beat": 7.0,
                     "duration_beats": 1.0, "velocity": 55},
                    {"pitch": 67, "start_beat": 8.5,
                     "duration_beats": 2.5, "velocity": 50},
                ],
            },
        ],
        "style_notes": (
            "Xiao is a vertical bamboo flute with a breathy, "
            "haunting tone. It is the opposite of dizi — slow, "
            "contemplative, and sparse. Use fewer notes with "
            "longer durations. Rests between phrases are essential. "
            "Dynamics should be soft (velocity 45-70)."
        ),
        "critic_criteria": (
            "Xiao should be sparse and meditative. Check that note "
            "count is moderate (not too dense). Reject if xiao "
            "plays rapid, busy passages — it should have rests "
            "and long tones."
        ),
    },

    "yangqin": {
        "name": "Yangqin (扬琴)",
        "gm_program": 15,
        "range": (48, 96),
        "sweet_spot": (55, 84),
        "idiomatic_intervals": [2, 3, 5, 7, 12],
        "avoid_intervals": [6, 11],
        "techniques": (
            "Rapid alternating strikes: hammered dulcimer technique "
            "with left-right hand alternation for tremolo effect. "
            "Rolled chords: rapid arpeggiation of 3-4 note chords. "
            "Octave doubling: playing same melody in two octaves. "
            "Damped strikes: muted notes for rhythmic punctuation."
        ),
        "role_guidance": {
            "lead": (
                "Play bright, sparkling melodies using the hammered "
                "technique. Yangqin excels at rapid passages — use "
                "16th-note patterns. Alternate between melody in "
                "the high register and accompaniment patterns in "
                "the mid register."
            ),
            "chords": (
                "Provide rhythmic harmonic support with rolled "
                "chords on beats 1 and 3. Fill between chord strikes "
                "with quick arpeggiated patterns. Add octave "
                "doublings for richness."
            ),
        },
        "example_phrases": [
            {
                "description": "Sparkling hammered pattern",
                "notes": [
                    {"pitch": 72, "start_beat": 0.0,
                     "duration_beats": 0.25, "velocity": 75},
                    {"pitch": 79, "start_beat": 0.25,
                     "duration_beats": 0.25, "velocity": 70},
                    {"pitch": 72, "start_beat": 0.5,
                     "duration_beats": 0.25, "velocity": 75},
                    {"pitch": 76, "start_beat": 0.75,
                     "duration_beats": 0.25, "velocity": 70},
                    {"pitch": 74, "start_beat": 1.0,
                     "duration_beats": 0.5, "velocity": 80},
                    {"pitch": 72, "start_beat": 1.5,
                     "duration_beats": 0.25, "velocity": 70},
                    {"pitch": 67, "start_beat": 1.75,
                     "duration_beats": 0.25, "velocity": 65},
                    {"pitch": 72, "start_beat": 2.0,
                     "duration_beats": 1.0, "velocity": 80},
                ],
            },
        ],
        "style_notes": (
            "Yangqin is a hammered dulcimer with a bright, "
            "bell-like resonance. It can sustain through rapid "
            "re-striking (tremolo). Use alternating-hand patterns "
            "for rhythmic drive. Pentatonic scale is typical. "
            "Effective for both melody and rhythmic accompaniment."
        ),
        "critic_criteria": (
            "Yangqin should be rhythmically active with varied "
            "note patterns. Check for mix of melodic lines and "
            "rhythmic figures. Reject if playing only simple "
            "long notes — yangqin is a hammered instrument."
        ),
    },

    # =================================================================
    # WESTERN INSTRUMENTS
    # =================================================================

    "piano": {
        "name": "Piano",
        "gm_program": 0,
        "range": (21, 108),
        "sweet_spot": (48, 84),
        "idiomatic_intervals": [1, 2, 3, 4, 5, 7, 12],
        "avoid_intervals": [],
        "techniques": (
            "Block chords: simultaneous 3-4 note voicings. "
            "Arpeggiated chords: broken chord patterns. "
            "Alberti bass: alternating bass-chord-middle-chord "
            "pattern in the left hand. "
            "Octave runs: parallel octaves for power. "
            "Sustain pedal: blending notes across beats."
        ),
        "role_guidance": {
            "lead": (
                "Play expressive melodies in the upper register "
                "(C4-C6) with dynamic shaping. Use octave doubling "
                "for emphasis. Mix stepwise motion with expressive "
                "leaps of 4ths, 5ths, and octaves."
            ),
            "chords": (
                "Provide harmonic foundation with varied voicings. "
                "Use Alberti bass or arpeggiated patterns rather "
                "than block chords on every beat. Spread voicings "
                "across left and right hand registers. Root in bass "
                "(C2-C4), chord tones in mid range (C4-C5)."
            ),
            "accompaniment": (
                "Use broken chord patterns or gentle arpeggios. "
                "Vary the pattern every 2-4 bars to maintain "
                "interest. Provide rhythmic and harmonic support "
                "without overwhelming the lead instrument."
            ),
        },
        "example_phrases": [
            {
                "description": (
                    "Arpeggiated accompaniment pattern"
                ),
                "notes": [
                    {"pitch": 48, "start_beat": 0.0,
                     "duration_beats": 0.5, "velocity": 65},
                    {"pitch": 55, "start_beat": 0.5,
                     "duration_beats": 0.5, "velocity": 55},
                    {"pitch": 60, "start_beat": 1.0,
                     "duration_beats": 0.5, "velocity": 55},
                    {"pitch": 64, "start_beat": 1.5,
                     "duration_beats": 0.5, "velocity": 60},
                    {"pitch": 60, "start_beat": 2.0,
                     "duration_beats": 0.5, "velocity": 55},
                    {"pitch": 55, "start_beat": 2.5,
                     "duration_beats": 0.5, "velocity": 55},
                    {"pitch": 48, "start_beat": 3.0,
                     "duration_beats": 1.0, "velocity": 65},
                ],
            },
        ],
        "style_notes": (
            "Piano is the most versatile instrument. When used for "
            "chords, avoid monotonous block chords on every beat — "
            "use broken patterns, arpeggios, or rhythmic variations. "
            "Register separation is key: bass notes in the low "
            "register, chord tones in the middle, melody on top."
        ),
        "critic_criteria": (
            "Piano should show register variety and rhythmic "
            "interest. Reject monotonous repeated block chords. "
            "Check for dynamic variation and pattern changes "
            "across sections."
        ),
    },

    "violin": {
        "name": "Violin",
        "gm_program": 40,
        "range": (55, 103),
        "sweet_spot": (60, 93),
        "idiomatic_intervals": [1, 2, 3, 4, 5, 7, 12],
        "avoid_intervals": [],
        "techniques": (
            "Legato: smooth connected bowing for singing melodies. "
            "Pizzicato: plucked notes for rhythmic accents. "
            "Double stops: two notes played simultaneously. "
            "Spiccato: bouncing bow for light, articulate passages. "
            "Vibrato: natural on sustained notes."
        ),
        "role_guidance": {
            "lead": (
                "Play lyrical, singing melodies using legato "
                "bowing. Violin excels at long, connected phrases "
                "with expressive vibrato. Use dynamic swells on "
                "long notes. Mix smooth legato passages with "
                "faster, more articulate sections."
            ),
            "counter-melody": (
                "Provide a melodic response to the main voice, "
                "often harmonizing a 3rd or 6th above/below. "
                "Use call-and-response patterns. Keep the "
                "counter-melody rhythmically complementary — "
                "active when the lead rests, sustained when "
                "the lead moves."
            ),
        },
        "example_phrases": [
            {
                "description": "Lyrical legato melody",
                "notes": [
                    {"pitch": 67, "start_beat": 0.0,
                     "duration_beats": 1.0, "velocity": 75},
                    {"pitch": 69, "start_beat": 1.0,
                     "duration_beats": 0.5, "velocity": 78},
                    {"pitch": 72, "start_beat": 1.5,
                     "duration_beats": 1.5, "velocity": 85},
                    {"pitch": 74, "start_beat": 3.0,
                     "duration_beats": 0.5, "velocity": 80},
                    {"pitch": 72, "start_beat": 3.5,
                     "duration_beats": 0.5, "velocity": 75},
                    {"pitch": 69, "start_beat": 4.0,
                     "duration_beats": 1.0, "velocity": 80},
                    {"pitch": 67, "start_beat": 5.0,
                     "duration_beats": 2.0, "velocity": 70},
                ],
            },
        ],
        "style_notes": (
            "Violin is a lyrical instrument that sings. Use "
            "connected phrasing — notes should flow into each "
            "other. Avoid choppy isolated notes unless "
            "specifically using spiccato or pizzicato style. "
            "Dynamic shaping within phrases is essential."
        ),
        "critic_criteria": (
            "Violin should have legato phrasing with dynamic "
            "variation. Check for connected note durations "
            "(notes should overlap or be adjacent, not sparse). "
            "Reject if violin plays only detached single notes."
        ),
    },

    "cello": {
        "name": "Cello",
        "gm_program": 42,
        "range": (36, 76),
        "sweet_spot": (40, 69),
        "idiomatic_intervals": [1, 2, 3, 5, 7, 12],
        "avoid_intervals": [],
        "techniques": (
            "Rich legato: warm, sustained bowing in lower register. "
            "Pizzicato bass: plucked notes for walking bass lines. "
            "Vibrato: wide, expressive on sustained notes. "
            "Harmonic overtones: high register bell-like tones."
        ),
        "role_guidance": {
            "lead": (
                "Play warm, rich melodies in the mid-upper register "
                "(C3-C5). Cello melodies should be broad and "
                "sustained with wide vibrato. Use dynamics to "
                "shape long phrases."
            ),
            "bass": (
                "Provide harmonic foundation with root notes on "
                "strong beats. Use walking bass lines with stepwise "
                "motion and occasional leaps to the 5th. Mix long "
                "sustained root notes with shorter passing tones. "
                "Pizzicato for lighter sections."
            ),
        },
        "example_phrases": [
            {
                "description": "Walking bass line",
                "notes": [
                    {"pitch": 48, "start_beat": 0.0,
                     "duration_beats": 1.0, "velocity": 70},
                    {"pitch": 50, "start_beat": 1.0,
                     "duration_beats": 0.5, "velocity": 60},
                    {"pitch": 52, "start_beat": 1.5,
                     "duration_beats": 0.5, "velocity": 60},
                    {"pitch": 53, "start_beat": 2.0,
                     "duration_beats": 1.0, "velocity": 70},
                    {"pitch": 55, "start_beat": 3.0,
                     "duration_beats": 0.5, "velocity": 65},
                    {"pitch": 53, "start_beat": 3.5,
                     "duration_beats": 0.5, "velocity": 60},
                    {"pitch": 48, "start_beat": 4.0,
                     "duration_beats": 2.0, "velocity": 70},
                ],
            },
        ],
        "style_notes": (
            "Cello provides warmth and depth. As bass, avoid "
            "single repeated root notes on every downbeat — use "
            "walking lines, passing tones, and occasional melodic "
            "bass movement. As lead, exploit the rich singing "
            "quality of the A and D strings (C3-G4)."
        ),
        "critic_criteria": (
            "Cello bass lines should have melodic interest — not "
            "just root notes on beat 1. Check for walking bass "
            "movement or varied rhythmic patterns. Reject "
            "single-note-per-bar bass lines."
        ),
    },

    "acoustic guitar": {
        "name": "Acoustic Guitar",
        "gm_program": 24,
        "range": (40, 88),
        "sweet_spot": (48, 79),
        "idiomatic_intervals": [1, 2, 3, 4, 5, 7, 12],
        "avoid_intervals": [],
        "techniques": (
            "Fingerpicking: independent patterns across 4-6 "
            "strings producing melody and harmony simultaneously. "
            "Strumming: rhythmic chord strokes on all strings. "
            "Hammer-ons/pull-offs: legato ornaments between fretted "
            "notes. "
            "Harmonics: bell-like tones at fret 5, 7, or 12."
        ),
        "role_guidance": {
            "chords": (
                "Use fingerpicking or arpeggiated patterns rather "
                "than simple block strums. Alternate bass notes "
                "with higher chord tones (Travis picking style). "
                "Vary the pattern every 2-4 bars."
            ),
            "accompaniment": (
                "Provide gentle fingerpicked patterns with a steady "
                "bass note on beats 1 and 3, and upper chord tones "
                "filling the offbeats. Mix open-string and fretted "
                "notes for variety."
            ),
        },
        "example_phrases": [
            {
                "description": "Travis-style fingerpicking pattern",
                "notes": [
                    {"pitch": 48, "start_beat": 0.0,
                     "duration_beats": 0.5, "velocity": 65},
                    {"pitch": 64, "start_beat": 0.25,
                     "duration_beats": 0.5, "velocity": 50},
                    {"pitch": 55, "start_beat": 0.5,
                     "duration_beats": 0.5, "velocity": 55},
                    {"pitch": 60, "start_beat": 0.75,
                     "duration_beats": 0.5, "velocity": 50},
                    {"pitch": 48, "start_beat": 1.0,
                     "duration_beats": 0.5, "velocity": 65},
                    {"pitch": 67, "start_beat": 1.25,
                     "duration_beats": 0.5, "velocity": 50},
                    {"pitch": 55, "start_beat": 1.5,
                     "duration_beats": 0.5, "velocity": 55},
                    {"pitch": 64, "start_beat": 1.75,
                     "duration_beats": 0.5, "velocity": 50},
                ],
            },
        ],
        "style_notes": (
            "Guitar is inherently polyphonic — it sounds best "
            "with multi-voice patterns (bass + treble). Avoid "
            "single-note lines unless doing a solo. Use varied "
            "strumming/picking patterns. Consider the physical "
            "layout: bass strings (E2-A2), mid (D3-G3), "
            "treble (B3-E4)."
        ),
        "critic_criteria": (
            "Guitar should show multi-voice patterns (bass + "
            "treble) rather than single-note lines. Check for "
            "rhythmic variety in strumming/picking patterns. "
            "Reject flat single-note passages."
        ),
    },

    "flute": {
        "name": "Flute",
        "gm_program": 73,
        "range": (60, 96),
        "sweet_spot": (67, 91),
        "idiomatic_intervals": [1, 2, 3, 4, 5, 7, 12],
        "avoid_intervals": [],
        "techniques": (
            "Flutter tongue: rapid articulation for texture. "
            "Legato: smooth connected phrases. "
            "Staccato: short, detached notes for lightness. "
            "Trills: rapid alternation between adjacent notes. "
            "Dynamic swells: crescendo/diminuendo on long notes."
        ),
        "role_guidance": {
            "lead": (
                "Play bright, lyrical melodies. Flute excels in "
                "the upper register for clear, singing lines. "
                "Mix legato phrases with staccato passages for "
                "contrast. Use trills as ornaments on long notes."
            ),
            "counter-melody": (
                "Provide a bright, high-register commentary on the "
                "main melody. Use short phrases in the gaps of the "
                "lead melody. Occasionally double the melody an "
                "octave higher for emphasis."
            ),
        },
        "example_phrases": [
            {
                "description": "Lyrical flute melody",
                "notes": [
                    {"pitch": 79, "start_beat": 0.0,
                     "duration_beats": 1.0, "velocity": 70},
                    {"pitch": 81, "start_beat": 1.0,
                     "duration_beats": 0.5, "velocity": 75},
                    {"pitch": 84, "start_beat": 1.5,
                     "duration_beats": 1.0, "velocity": 80},
                    {"pitch": 81, "start_beat": 2.5,
                     "duration_beats": 0.5, "velocity": 70},
                    {"pitch": 79, "start_beat": 3.0,
                     "duration_beats": 0.5, "velocity": 75},
                    {"pitch": 76, "start_beat": 3.5,
                     "duration_beats": 1.0, "velocity": 70},
                    {"pitch": 74, "start_beat": 4.5,
                     "duration_beats": 1.5, "velocity": 65},
                ],
            },
        ],
        "style_notes": (
            "Western flute has a pure, clear tone. It projects "
            "well in the upper register. Use breath-like phrasing "
            "with natural phrase lengths (2-4 bars). Avoid "
            "sustained notes longer than 3 beats without melodic "
            "movement."
        ),
        "critic_criteria": (
            "Flute should have clear melodic phrasing with "
            "natural breath points. Check for dynamic variation. "
            "Reject if flute plays monotonous repeated patterns."
        ),
    },

    "trumpet": {
        "name": "Trumpet",
        "gm_program": 56,
        "range": (54, 89),
        "sweet_spot": (58, 82),
        "idiomatic_intervals": [1, 2, 3, 4, 5, 7, 12],
        "avoid_intervals": [],
        "techniques": (
            "Fanfare: bright, bold melodic statements. "
            "Muted playing: softer, more intimate timbre. "
            "Shake/lip trill: rapid pitch oscillation. "
            "Fall-offs: pitch slides downward at phrase endings. "
            "Double/triple tonguing: rapid articulation."
        ),
        "role_guidance": {
            "lead": (
                "Play bold, heroic melodies with strong attacks. "
                "Trumpet cuts through — use for main thematic "
                "statements. Fanfare-like phrases with dotted "
                "rhythms and wide intervals (4ths, 5ths). "
                "Save high register (above G5) for climactic "
                "moments."
            ),
            "counter-melody": (
                "Provide punctuating responses between main melody "
                "phrases. Use short, bright motifs. Muted trumpet "
                "for softer, more intimate passages."
            ),
        },
        "example_phrases": [
            {
                "description": "Bold fanfare statement",
                "notes": [
                    {"pitch": 72, "start_beat": 0.0,
                     "duration_beats": 1.5, "velocity": 90},
                    {"pitch": 67, "start_beat": 1.5,
                     "duration_beats": 0.5, "velocity": 80},
                    {"pitch": 72, "start_beat": 2.0,
                     "duration_beats": 0.75, "velocity": 85},
                    {"pitch": 74, "start_beat": 2.75,
                     "duration_beats": 0.25, "velocity": 80},
                    {"pitch": 76, "start_beat": 3.0,
                     "duration_beats": 2.0, "velocity": 95},
                    {"pitch": 74, "start_beat": 5.0,
                     "duration_beats": 0.5, "velocity": 75},
                    {"pitch": 72, "start_beat": 5.5,
                     "duration_beats": 1.5, "velocity": 80},
                ],
            },
        ],
        "style_notes": (
            "Trumpet is a powerful, projecting instrument. It "
            "needs rest between phrases (breathing). Avoid "
            "continuous playing for more than 4-8 bars. Use "
            "dynamic contrast — forte for heroic statements, "
            "piano with mute for intimate passages."
        ),
        "critic_criteria": (
            "Trumpet should have bold phrasing with natural rests. "
            "Check for dynamic variety (not all fortissimo). "
            "Reject if trumpet plays continuous wall-of-sound."
        ),
    },

    "clarinet": {
        "name": "Clarinet",
        "gm_program": 71,
        "range": (50, 91),
        "sweet_spot": (55, 84),
        "idiomatic_intervals": [1, 2, 3, 4, 5, 7, 12],
        "avoid_intervals": [],
        "techniques": (
            "Legato: exceptionally smooth connected playing. "
            "Chalumeau register: warm, dark low tones. "
            "Clarion register: bright, clear mid-high tones. "
            "Wide leaps: clarinet handles large interval jumps "
            "smoothly (12ths are characteristic). "
            "Rapid passages: excellent agility for scalar runs."
        ),
        "role_guidance": {
            "lead": (
                "Play warm, expressive melodies exploiting the "
                "full range. Use the chalumeau (low) register for "
                "dark, mysterious passages and the clarion (high) "
                "for bright, soaring lines. Wide interval leaps "
                "(especially 12ths) are characteristic."
            ),
            "counter-melody": (
                "Provide a warm melodic commentary, often weaving "
                "around the main melody. Use the mid register for "
                "blending. Quick scalar fills between main melody "
                "phrases."
            ),
        },
        "example_phrases": [
            {
                "description": (
                    "Expressive melody using register contrast"
                ),
                "notes": [
                    {"pitch": 55, "start_beat": 0.0,
                     "duration_beats": 1.0, "velocity": 65},
                    {"pitch": 57, "start_beat": 1.0,
                     "duration_beats": 0.5, "velocity": 70},
                    {"pitch": 60, "start_beat": 1.5,
                     "duration_beats": 0.5, "velocity": 75},
                    {"pitch": 72, "start_beat": 2.0,
                     "duration_beats": 1.5, "velocity": 80},
                    {"pitch": 74, "start_beat": 3.5,
                     "duration_beats": 0.5, "velocity": 75},
                    {"pitch": 72, "start_beat": 4.0,
                     "duration_beats": 1.0, "velocity": 70},
                    {"pitch": 67, "start_beat": 5.0,
                     "duration_beats": 2.0, "velocity": 65},
                ],
            },
        ],
        "style_notes": (
            "Clarinet has the widest dynamic and pitch range of "
            "all woodwinds. Exploit register contrast — the low "
            "register sounds dark and warm, the high register "
            "sounds bright and clear. The break between registers "
            "around Bb4 is a feature, not a problem."
        ),
        "critic_criteria": (
            "Clarinet should use its full range with register "
            "contrast. Check for legato phrasing and dynamic "
            "variation. Reject monotonous mid-range playing."
        ),
    },

    "harp": {
        "name": "Harp",
        "gm_program": 46,
        "range": (24, 103),
        "sweet_spot": (40, 91),
        "idiomatic_intervals": [2, 3, 4, 5, 7, 12],
        "avoid_intervals": [1],
        "techniques": (
            "Glissando: sweeping across strings — the signature "
            "harp technique. "
            "Arpeggiated chords: broken chords across the strings. "
            "Bisbigliando: rapid alternation between two pitches "
            "creating a shimmering effect. "
            "Harmonics: bell-like tones an octave above."
        ),
        "role_guidance": {
            "chords": (
                "Play arpeggiated chords with the bass note first, "
                "rolling upward through chord tones. Vary the "
                "speed of arpeggiation. Use glissando sweeps at "
                "section transitions."
            ),
            "accompaniment": (
                "Provide gentle, flowing arpeggiated patterns. "
                "Alternate between bass register and treble "
                "register arpeggios. Use bisbigliando for "
                "sustained texture on held chords."
            ),
        },
        "example_phrases": [
            {
                "description": "Arpeggiated chord pattern",
                "notes": [
                    {"pitch": 48, "start_beat": 0.0,
                     "duration_beats": 1.0, "velocity": 60},
                    {"pitch": 55, "start_beat": 0.25,
                     "duration_beats": 1.0, "velocity": 55},
                    {"pitch": 60, "start_beat": 0.5,
                     "duration_beats": 1.0, "velocity": 55},
                    {"pitch": 64, "start_beat": 0.75,
                     "duration_beats": 1.0, "velocity": 60},
                    {"pitch": 67, "start_beat": 1.0,
                     "duration_beats": 1.0, "velocity": 65},
                    {"pitch": 72, "start_beat": 1.25,
                     "duration_beats": 1.0, "velocity": 60},
                    {"pitch": 48, "start_beat": 2.0,
                     "duration_beats": 1.0, "velocity": 60},
                    {"pitch": 52, "start_beat": 2.25,
                     "duration_beats": 1.0, "velocity": 55},
                ],
            },
        ],
        "style_notes": (
            "Harp sounds best with flowing, arpeggiated textures "
            "rather than single-note melodies. Notes ring and "
            "overlap naturally. Use wide spacing between chord "
            "tones. Glissandos are the harp's signature — use "
            "them for transitions. Avoid chromatic semitone steps."
        ),
        "critic_criteria": (
            "Harp should have arpeggiated textures rather than "
            "single-note lines. Check for overlapping note "
            "durations (notes should ring together). Reject "
            "simple single-note passages."
        ),
    },

    # =================================================================
    # ENSEMBLE / PAD entries
    # =================================================================

    "strings": {
        "name": "Strings Ensemble",
        "gm_program": 48,
        "range": (36, 96),
        "sweet_spot": (48, 84),
        "idiomatic_intervals": [1, 2, 3, 5, 7, 12],
        "avoid_intervals": [],
        "techniques": (
            "Sustained pads: long held chords for harmonic support. "
            "Tremolo: rapid bow oscillation for tension. "
            "Legato melody: unison melodic lines. "
            "Pizzicato: plucked ensemble for rhythmic lightness."
        ),
        "role_guidance": {
            "texture": (
                "Provide warm sustained chords that evolve with "
                "voice leading — move each chord tone by the "
                "smallest interval to the next chord. Use 3-4 "
                "note voicings with smooth transitions."
            ),
            "chords": (
                "Hold harmonic pads changing every 2-4 beats. "
                "Use dynamic swells for emotional emphasis. "
                "Add tremolo for tension in dramatic sections."
            ),
        },
        "example_phrases": [
            {
                "description": "Sustained pad with voice leading",
                "notes": [
                    {"pitch": 60, "start_beat": 0.0,
                     "duration_beats": 4.0, "velocity": 55},
                    {"pitch": 64, "start_beat": 0.0,
                     "duration_beats": 4.0, "velocity": 50},
                    {"pitch": 67, "start_beat": 0.0,
                     "duration_beats": 4.0, "velocity": 50},
                    {"pitch": 60, "start_beat": 4.0,
                     "duration_beats": 4.0, "velocity": 60},
                    {"pitch": 65, "start_beat": 4.0,
                     "duration_beats": 4.0, "velocity": 55},
                    {"pitch": 69, "start_beat": 4.0,
                     "duration_beats": 4.0, "velocity": 55},
                ],
            },
        ],
        "style_notes": (
            "String ensembles provide warmth and depth. Use smooth "
            "voice leading between chords — each voice moves by "
            "the smallest possible interval. Dynamic swells "
            "(crescendo/diminuendo) are essential for expression."
        ),
        "critic_criteria": (
            "Strings ensemble should provide sustained harmonic "
            "support with voice leading. Reject single-note pads "
            "without chord structure."
        ),
    },

    "contrabass": {
        "name": "Contrabass",
        "gm_program": 43,
        "range": (28, 67),
        "sweet_spot": (28, 55),
        "idiomatic_intervals": [2, 3, 5, 7, 12],
        "avoid_intervals": [1],
        "techniques": (
            "Arco: bowed sustained bass for warmth. "
            "Pizzicato: plucked bass for rhythmic drive — "
            "the most common jazz/folk technique. "
            "Walking bass: stepwise melodic bass lines."
        ),
        "role_guidance": {
            "bass": (
                "Provide the harmonic and rhythmic foundation. "
                "Use root on beat 1, fifth on beat 3 as a "
                "starting point, then add passing tones between. "
                "Walking bass lines with stepwise and leap motion "
                "keep the bass part musical."
            ),
        },
        "example_phrases": [
            {
                "description": "Pizzicato walking bass",
                "notes": [
                    {"pitch": 36, "start_beat": 0.0,
                     "duration_beats": 1.0, "velocity": 70},
                    {"pitch": 38, "start_beat": 1.0,
                     "duration_beats": 1.0, "velocity": 65},
                    {"pitch": 40, "start_beat": 2.0,
                     "duration_beats": 1.0, "velocity": 70},
                    {"pitch": 43, "start_beat": 3.0,
                     "duration_beats": 0.5, "velocity": 65},
                    {"pitch": 40, "start_beat": 3.5,
                     "duration_beats": 0.5, "velocity": 60},
                    {"pitch": 36, "start_beat": 4.0,
                     "duration_beats": 2.0, "velocity": 70},
                ],
            },
        ],
        "style_notes": (
            "Contrabass anchors the ensemble. Avoid static single "
            "notes held for entire sections. Even simple bass "
            "patterns should have melodic interest — root-5th "
            "movement, passing tones, approach notes."
        ),
        "critic_criteria": (
            "Bass should have melodic movement, not just held "
            "root notes. Check for at least 2-3 different pitches "
            "per section."
        ),
    },

    "viola": {
        "name": "Viola",
        "gm_program": 41,
        "range": (48, 91),
        "sweet_spot": (55, 79),
        "idiomatic_intervals": [1, 2, 3, 5, 7, 12],
        "avoid_intervals": [],
        "techniques": (
            "Rich legato in the C-string register (warm, dark). "
            "Inner voice leading: filling harmonic space between "
            "melody and bass. "
            "Double stops: two-note chords. "
            "Vibrato: warm and wide."
        ),
        "role_guidance": {
            "texture": (
                "Fill the harmonic space between melody and bass. "
                "Play inner voice lines with smooth legato. "
                "Provide sustained harmonic tones that complement "
                "rather than compete with the lead melody."
            ),
            "counter-melody": (
                "Provide warm, mid-register melodic responses. "
                "Use the rich C-string tone for dark, emotional "
                "passages."
            ),
        },
        "example_phrases": [
            {
                "description": "Inner voice harmonic line",
                "notes": [
                    {"pitch": 60, "start_beat": 0.0,
                     "duration_beats": 2.0, "velocity": 55},
                    {"pitch": 62, "start_beat": 2.0,
                     "duration_beats": 1.0, "velocity": 58},
                    {"pitch": 64, "start_beat": 3.0,
                     "duration_beats": 2.0, "velocity": 55},
                    {"pitch": 62, "start_beat": 5.0,
                     "duration_beats": 1.0, "velocity": 50},
                    {"pitch": 60, "start_beat": 6.0,
                     "duration_beats": 2.0, "velocity": 55},
                ],
            },
        ],
        "style_notes": (
            "Viola fills the mid-range harmonic space. It should "
            "NOT try to compete with the melody. Use smooth voice "
            "leading with stepwise motion. Velocity should be "
            "softer than the lead instrument."
        ),
        "critic_criteria": (
            "Viola should provide harmonic support without "
            "dominating. Check that velocity is moderate and "
            "that the part has smooth voice leading."
        ),
    },
}


def lookup_instrument(name: str) -> dict | None:
    """Find an instrument card by name (case-insensitive, fuzzy)."""
    key = name.lower().strip()
    if key in INSTRUMENT_CARDS:
        return INSTRUMENT_CARDS[key]
    for card_key, card in INSTRUMENT_CARDS.items():
        if card_key in key or key in card_key:
            return card
    for card_key, card in INSTRUMENT_CARDS.items():
        aliases = card_key.split("/")
        for alias in aliases:
            if alias in key or key in alias:
                return card
    return None


def format_for_composer(
    instrument_name: str, role: str,
) -> str | None:
    """Format a knowledge card as Composer prompt text."""
    card = lookup_instrument(instrument_name)
    if not card:
        return None

    role_key = role.lower().replace("-", "").replace("_", "")
    role_text = card["role_guidance"].get(role_key)
    if not role_text:
        role_text = next(iter(card["role_guidance"].values()), "")

    example = card["example_phrases"][0]
    notes_str = ", ".join(
        f'{{"pitch": {n["pitch"]}, '
        f'"start_beat": {n["start_beat"]}, '
        f'"duration_beats": {n["duration_beats"]}, '
        f'"velocity": {n["velocity"]}}}'
        for n in example["notes"][:6]
    )

    intervals_str = ", ".join(str(i) for i in card["idiomatic_intervals"])
    avoid_str = (
        ", ".join(str(i) for i in card["avoid_intervals"])
        if card["avoid_intervals"]
        else "none"
    )

    lines = [
        f"--- {card['name']} ({role}) ---",
        f"Sweet spot: MIDI {card['sweet_spot'][0]}-{card['sweet_spot'][1]}",
        f"Idiomatic intervals (semitones): {intervals_str}",
        f"Intervals to avoid: {avoid_str}",
        f"Techniques: {card['techniques'][:200]}",
        f"Playing guide: {role_text}",
        f"Style: {card['style_notes'][:200]}",
        "",
        f"Example ({example['description']}) — "
        "use as INSPIRATION, create your own phrases:",
        f"  [{notes_str}]",
    ]
    return "\n".join(lines)


def format_for_instrumentalist(
    instrument_name: str,
) -> str | None:
    """Format technique guidance for the Instrumentalist agent."""
    card = lookup_instrument(instrument_name)
    if not card:
        return None

    return (
        f"{card['name']}: {card['techniques']}"
    )


def format_for_critic(
    instrument_name: str,
) -> str | None:
    """Format evaluation criteria for the Critic agent."""
    card = lookup_instrument(instrument_name)
    if not card:
        return None

    return f"- {card['name']}: {card['critic_criteria']}"

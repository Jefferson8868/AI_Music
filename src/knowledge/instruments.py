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
    instrument_name: str,
    role: str,
    section: str | None = None,
    is_featured: bool = False,
) -> str | None:
    """Format a knowledge card as Composer prompt text.

    If is_featured, returns full techniques/style/role_guidance plus the
    ornament vocabulary and up to 2 idiomatic motifs.
    If not featured, returns a compact summary to save tokens for supporting
    instruments.
    """
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

    vocab = card.get("ornament_vocabulary") or []
    motifs = card.get("idiomatic_motifs") or []
    spot_role = "FEATURED" if is_featured else "SUPPORTING"
    section_tag = f" in [{section.upper()}]" if section else ""

    lines = [
        f"--- {card['name']} ({role}) [{spot_role}]{section_tag} ---",
        f"Sweet spot: MIDI {card['sweet_spot'][0]}-{card['sweet_spot'][1]}",
        f"Idiomatic intervals (semitones): {intervals_str}",
        f"Intervals to avoid: {avoid_str}",
    ]

    # Continuity rules are shown to BOTH featured and supporting
    # instruments — in fact they matter MORE for supporting tracks,
    # because that's where the "note-by-note" failure shows up.
    continuity = card.get("continuity_profile") or {}
    if continuity:
        style = continuity.get("style", "rhythmic_comp")
        cov = continuity.get("min_section_coverage_pct", 60)
        max_gap = continuity.get("max_gap_beats", 2.0)
        hint = continuity.get("phrase_grouping_hint", "")
        lines.append(
            f"Continuity: style={style}, "
            f"cover >= {cov}% of the section in playing beats, "
            f"no gap longer than {max_gap} beats between your notes."
        )
        if hint:
            lines.append(f"Continuity hint: {hint}")

    if is_featured:
        lines.append(f"Techniques: {card['techniques']}")
        lines.append(f"Playing guide: {role_text}")
        lines.append(f"Style: {card['style_notes']}")
        if vocab:
            lines.append(
                "Available ornaments: " + ", ".join(vocab)
            )
        for motif in motifs[:2]:
            motif_notes = ", ".join(
                f'{{"pitch": {n["pitch"]}, '
                f'"start_beat": {n["start_beat"]}, '
                f'"duration_beats": {n["duration_beats"]}, '
                f'"velocity": {n["velocity"]}, '
                f'"ornaments": {n.get("ornaments", [])}}}'
                for n in motif["notes"][:8]
            )
            lines.append(
                f"Motif '{motif['name']}' ({motif['description']}): "
                f"[{motif_notes}]"
            )
    else:
        # Compact summary for supporting instruments
        tech_summary = card["techniques"].split(".")[0][:160]
        lines.append(f"Techniques (summary): {tech_summary}.")
        lines.append(f"Playing guide: {role_text[:200]}")
        if vocab:
            lines.append(
                "Available ornaments: " + ", ".join(vocab)
            )

    lines.append("")
    lines.append(
        f"Example ({example['description']}) — "
        "use as INSPIRATION, create your own phrases:"
    )
    lines.append(f"  [{notes_str}]")
    return "\n".join(lines)


def format_for_instrumentalist(
    instrument_name: str,
    section: str | None = None,
) -> str | None:
    """Format technique guidance + ornament vocabulary for the Instrumentalist."""
    card = lookup_instrument(instrument_name)
    if not card:
        return None

    vocab = card.get("ornament_vocabulary") or []
    recipes = card.get("performance_recipes") or {}
    lines = [f"{card['name']}:"]
    lines.append(f"  Techniques: {card['techniques']}")
    if vocab:
        lines.append("  Ornament vocabulary: " + ", ".join(vocab))
    if recipes:
        default_vib = recipes.get("default_vibrato")
        if default_vib:
            lines.append(
                f"  Default vibrato: {default_vib.get('type')} "
                f"(depth={default_vib.get('depth')}, "
                f"rate={default_vib.get('rate_hz')}Hz)"
            )
        vc = recipes.get("velocity_curve")
        if vc:
            lines.append(f"  Velocity curve: {vc}")
    return "\n".join(lines)


def format_for_critic(
    instrument_name: str,
) -> str | None:
    """Format evaluation criteria + spotlight profile for the Critic agent."""
    card = lookup_instrument(instrument_name)
    if not card:
        return None

    lines = [f"- {card['name']}: {card['critic_criteria']}"]
    profile = card.get("spotlight_profile")
    if profile:
        lines.append(
            f"  Spotlight profile: typical_role={profile.get('typical_role')}, "
            f"good_at={profile.get('good_at', [])}, "
            f"avoid={profile.get('avoid', [])}, "
            f"pairs_with={profile.get('pairs_with', [])}, "
            f"competes_with={profile.get('competes_with', [])}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Accessors for the performance renderer
# ---------------------------------------------------------------------------

def get_performance_recipe(
    instrument_name: str, field_name: str, default=None,
):
    """Return a specific field from the card's performance_recipes, or default."""
    card = lookup_instrument(instrument_name)
    if not card:
        return default
    recipes = card.get("performance_recipes") or {}
    return recipes.get(field_name, default)


def get_auto_rules(instrument_name: str) -> list[dict]:
    """Return the list of auto-ornament rules for an instrument."""
    card = lookup_instrument(instrument_name)
    if not card:
        return []
    return list(card.get("auto_rules") or [])


def get_spotlight_profile(instrument_name: str) -> dict:
    """Return the spotlight profile dict for an instrument, or {}."""
    card = lookup_instrument(instrument_name)
    if not card:
        return {}
    return dict(card.get("spotlight_profile") or {})


def get_ornament_vocabulary(instrument_name: str) -> list[str]:
    """Return the list of ornament names this instrument supports."""
    card = lookup_instrument(instrument_name)
    if not card:
        return []
    return list(card.get("ornament_vocabulary") or [])


def get_continuity_profile(instrument_name: str) -> dict:
    """Return the continuity_profile dict for an instrument, or {}.

    The profile carries the keys:
        style: one of continuous_breath / continuous_bowed /
               sustained_pad / rhythmic_comp / plucked_discrete /
               percussive.
        min_section_coverage_pct: 0-100, minimum % of beats active.
        max_gap_beats: float, longest tolerated silence.
        phrase_grouping_hint: natural-language hint for the Composer.
    """
    card = lookup_instrument(instrument_name)
    if not card:
        return {}
    return dict(card.get("continuity_profile") or {})


# ---------------------------------------------------------------------------
# Validation & extension merge
# ---------------------------------------------------------------------------

_REQUIRED_EXT_FIELDS = (
    "performance_recipes",
    "auto_rules",
    "ornament_vocabulary",
    "spotlight_profile",
    "idiomatic_motifs",
    "velocity_envelope_preset",
    "continuity_profile",
)

# continuity_profile semantics
# ---------------------------------------------------------------------------
# "style": one of
#     "continuous_breath"  — wind instruments that must breathe through a
#                             line. Dizi, Xiao, Flute, Clarinet, Trumpet.
#                             Leaving single-beat notes with long gaps
#                             sounds mechanical.
#     "continuous_bowed"   — bowed strings. Erhu, Violin, Viola, Cello,
#                             Contrabass. Same rule as breath — lines
#                             should span phrases.
#     "sustained_pad"      — evolving pad/texture. Strings (section), Pad.
#                             Must hold chords across many beats.
#     "rhythmic_comp"      — chord comping instruments that repeat a
#                             rhythmic cell. Piano, Acoustic Guitar.
#                             "Continuous" means the pattern repeats
#                             through the section — not that every beat
#                             has a note, but there must be no silent bar.
#     "plucked_discrete"   — plucked strings that naturally produce
#                             discrete attacks. Guzheng, Pipa, Yangqin,
#                             Harp. Fine to have rests, but phrases must
#                             be GROUPED (runs / arpeggios) not single
#                             beats.
#     "percussive"         — drums / percussion (not currently used).
#
# "min_section_coverage_pct": when active in a section, the ACTUAL playing
#     beats (note durations summed) should cover at least this percent of
#     the section's beats. 0-100.
#
# "max_gap_beats": the longest allowed silence between consecutive notes
#     from this instrument when it is active. Violations mean the part
#     sounds note-by-note.
#
# "phrase_grouping_hint": natural language guidance the Composer reads.
# ---------------------------------------------------------------------------
_DEFAULT_EXTENSIONS: dict = {
    "performance_recipes": {
        "default_vibrato": None,
        "long_note_threshold_beats": 2.0,
        "long_note_ornaments": [],
        "consecutive_step_threshold_beats": 0.5,
        "consecutive_step_ornaments": [],
        "phrase_end_ornaments": [],
        "velocity_curve": "flat",
    },
    "auto_rules": [],
    "ornament_vocabulary": ["staccato", "tenuto", "legato_to_next"],
    "spotlight_profile": {
        "typical_role": "accompaniment",
        "good_at": [],
        "avoid": [],
        "pairs_with": [],
        "competes_with": [],
    },
    "idiomatic_motifs": [],
    "velocity_envelope_preset": {
        "attack": 0.1, "peak_ratio": 1.0, "decay": 0.2,
    },
    "continuity_profile": {
        "style": "rhythmic_comp",
        "min_section_coverage_pct": 60,
        "max_gap_beats": 2.0,
        "phrase_grouping_hint": (
            "Group notes into phrases of 2-4 bars rather than "
            "emitting single beats."
        ),
    },
}


def _validate_card(name: str, card: dict) -> None:
    """Assert card has all new extension fields (after merge). Fail fast."""
    for field in _REQUIRED_EXT_FIELDS:
        if field not in card:
            raise ValueError(
                f"INSTRUMENT_CARDS['{name}'] missing required field '{field}' "
                f"after extension merge. Check INSTRUMENT_EXTENSIONS."
            )
    vocab = card.get("ornament_vocabulary") or []
    if not isinstance(vocab, list):
        raise ValueError(
            f"INSTRUMENT_CARDS['{name}'].ornament_vocabulary must be a list"
        )


def _merge_extensions() -> None:
    """Inject INSTRUMENT_EXTENSIONS into INSTRUMENT_CARDS + fill defaults."""
    ext_table = globals().get("INSTRUMENT_EXTENSIONS", {})
    for inst_name, card in INSTRUMENT_CARDS.items():
        ext = ext_table.get(inst_name, {})
        for field, default in _DEFAULT_EXTENSIONS.items():
            if field in ext:
                card[field] = ext[field]
            elif field not in card:
                # Deep-copy defaults to avoid shared mutable state
                if isinstance(default, dict):
                    card[field] = dict(default)
                elif isinstance(default, list):
                    card[field] = list(default)
                else:
                    card[field] = default
        _validate_card(inst_name, card)


# ---------------------------------------------------------------------------
# Extension data for each instrument. Rich entries for Erhu / Dizi / Guzheng /
# Piano / Cello / Strings (the user's fusion test piece). Remaining
# instruments fall back to _DEFAULT_EXTENSIONS unless overridden here.
# ---------------------------------------------------------------------------

INSTRUMENT_EXTENSIONS: dict[str, dict] = {
    "erhu": {
        "performance_recipes": {
            "default_vibrato": {
                "type": "vibrato_deep", "depth": 60, "rate_hz": 6.0,
            },
            "long_note_threshold_beats": 1.5,
            "long_note_ornaments": ["vibrato_deep"],
            "consecutive_step_threshold_beats": 0.5,
            "consecutive_step_ornaments": [
                "legato_to_next", "slide_up_from:1",
            ],
            "phrase_end_ornaments": ["vibrato_deep"],
            "velocity_curve": "swell",
        },
        "auto_rules": [
            {"condition": "duration > 1.5",
             "add_ornaments": ["vibrato_deep"]},
            {"condition": "next_note_close",
             "add_ornaments": ["legato_to_next"]},
            {"condition": "ascending_step",
             "add_ornaments": ["slide_up_from:1"]},
            {"condition": "descending_step",
             "add_ornaments": ["slide_down_from:1"]},
        ],
        "ornament_vocabulary": [
            "vibrato_light", "vibrato_deep", "vibrato_delayed",
            "slide_up_from", "slide_down_from",
            "slide_up_to", "slide_down_to",
            "bend_dip", "legato_to_next", "tenuto",
        ],
        "spotlight_profile": {
            "typical_role": "lead",
            "good_at": ["chorus", "bridge", "pre_chorus"],
            "avoid": ["intro"],
            "pairs_with": ["dizi", "pipa"],
            "competes_with": ["violin", "viola"],
        },
        "idiomatic_motifs": [
            {
                "name": "erhu_lyrical_ascent",
                "description": "Rising emotional phrase with portamento",
                "notes": [
                    {"pitch": 62, "start_beat": 0.0,
                     "duration_beats": 1.0, "velocity": 70,
                     "ornaments": ["slide_up_from:2"]},
                    {"pitch": 64, "start_beat": 1.0,
                     "duration_beats": 0.5, "velocity": 75,
                     "ornaments": ["legato_to_next"]},
                    {"pitch": 67, "start_beat": 1.5,
                     "duration_beats": 2.0, "velocity": 85,
                     "ornaments": ["vibrato_deep"]},
                ],
            },
            {
                "name": "erhu_vocal_sigh",
                "description": "Vocal-like sigh with dip",
                "notes": [
                    {"pitch": 69, "start_beat": 0.0,
                     "duration_beats": 2.0, "velocity": 80,
                     "ornaments": ["vibrato_delayed", "bend_dip"]},
                    {"pitch": 67, "start_beat": 2.0,
                     "duration_beats": 1.5, "velocity": 70,
                     "ornaments": ["slide_down_from:2"]},
                ],
            },
        ],
        "velocity_envelope_preset": {
            "attack": 0.15, "peak_ratio": 1.05, "decay": 0.25,
        },
        "continuity_profile": {
            "style": "continuous_bowed",
            "min_section_coverage_pct": 75,
            "max_gap_beats": 1.0,
            "phrase_grouping_hint": (
                "Erhu bows a phrase as one breath. When active in a "
                "section, shape ONE continuous melodic line per 2-4 "
                "bars with legato/slides between notes — no gaps "
                "longer than a quarter note unless it's the phrase "
                "breath."
            ),
        },
    },

    "dizi": {
        "performance_recipes": {
            "default_vibrato": {
                "type": "vibrato_light", "depth": 30, "rate_hz": 5.5,
            },
            "long_note_threshold_beats": 1.5,
            "long_note_ornaments": ["breath_swell", "vibrato_light"],
            "consecutive_step_threshold_beats": 0.5,
            "consecutive_step_ornaments": ["legato_to_next"],
            "phrase_end_ornaments": ["breath_fade"],
            "velocity_curve": "swell",
        },
        "auto_rules": [
            {"condition": "duration > 1.5",
             "add_ornaments": ["breath_swell", "vibrato_light"]},
            {"condition": "first_of_phrase",
             "add_ornaments": ["breath_swell"]},
            {"condition": "last_of_phrase",
             "add_ornaments": ["breath_fade"]},
            {"condition": "short_high_note",
             "add_ornaments": ["grace_note_above"]},
        ],
        "ornament_vocabulary": [
            "breath_swell", "breath_fade", "flutter", "overblow",
            "vibrato_light", "vibrato_deep", "vibrato_delayed",
            "slide_up_to", "slide_down_to",
            "grace_note_above", "grace_note_below",
            "staccato", "tenuto", "legato_to_next",
        ],
        "spotlight_profile": {
            "typical_role": "lead",
            "good_at": ["chorus", "pre_chorus", "outro"],
            "avoid": ["intro", "verse"],
            "pairs_with": ["erhu", "pipa", "guzheng"],
            "competes_with": ["flute", "xiao"],
        },
        "idiomatic_motifs": [
            {
                "name": "dizi_bright_hook",
                "description": "Bright climactic hook with flutter",
                "notes": [
                    {"pitch": 79, "start_beat": 0.0,
                     "duration_beats": 0.5, "velocity": 90,
                     "ornaments": ["grace_note_above"]},
                    {"pitch": 81, "start_beat": 0.5,
                     "duration_beats": 0.5, "velocity": 92,
                     "ornaments": []},
                    {"pitch": 84, "start_beat": 1.0,
                     "duration_beats": 2.0, "velocity": 100,
                     "ornaments": ["breath_swell", "flutter"]},
                ],
            },
            {
                "name": "dizi_breath_entrance",
                "description": "Slow breath-swell entry typical of 国风",
                "notes": [
                    {"pitch": 74, "start_beat": 0.0,
                     "duration_beats": 3.0, "velocity": 65,
                     "ornaments": ["breath_swell", "vibrato_light"]},
                    {"pitch": 76, "start_beat": 3.0,
                     "duration_beats": 1.0, "velocity": 70,
                     "ornaments": ["breath_fade"]},
                ],
            },
        ],
        "velocity_envelope_preset": {
            "attack": 0.2, "peak_ratio": 1.1, "decay": 0.3,
        },
        "continuity_profile": {
            "style": "continuous_breath",
            "min_section_coverage_pct": 75,
            "max_gap_beats": 1.0,
            "phrase_grouping_hint": (
                "Dizi is a breath instrument. When active in a section, "
                "shape ONE continuous breath line that connects through "
                "legato / slides / breath_swell — no isolated single-beat "
                "notes with bar-long gaps. A rest must feel like a "
                "deliberate breath, not a silence."
            ),
        },
    },

    "guzheng": {
        "performance_recipes": {
            "default_vibrato": None,
            "long_note_threshold_beats": 2.0,
            "long_note_ornaments": ["tremolo_rapid"],
            "consecutive_step_threshold_beats": 0.5,
            "consecutive_step_ornaments": [],
            "phrase_end_ornaments": [],
            "velocity_curve": "decay",
        },
        "auto_rules": [
            {"condition": "duration > 2.0",
             "add_ornaments": ["tremolo_rapid"]},
            {"condition": "ascending_run",
             "add_ornaments": ["glissando_from"]},
            {"condition": "first_of_phrase",
             "add_ornaments": ["glissando_from"]},
        ],
        "ornament_vocabulary": [
            "tremolo_rapid", "glissando_from", "glissando_to",
            "slide_up_from", "slide_down_from",
            "grace_note_above", "grace_note_below",
            "staccato", "tenuto",
        ],
        "spotlight_profile": {
            "typical_role": "lead",
            "good_at": ["verse", "chorus", "bridge"],
            "avoid": [],
            "pairs_with": ["dizi", "erhu"],
            "competes_with": ["pipa", "harp", "yangqin"],
        },
        "idiomatic_motifs": [
            {
                "name": "guzheng_pentatonic_sweep",
                "description": "Ascending pentatonic sweep with gliss",
                "notes": [
                    {"pitch": 67, "start_beat": 0.0,
                     "duration_beats": 0.5, "velocity": 80,
                     "ornaments": ["glissando_from"]},
                    {"pitch": 69, "start_beat": 0.5,
                     "duration_beats": 0.5, "velocity": 78,
                     "ornaments": []},
                    {"pitch": 72, "start_beat": 1.0,
                     "duration_beats": 2.0, "velocity": 85,
                     "ornaments": ["tremolo_rapid"]},
                ],
            },
        ],
        "velocity_envelope_preset": {
            "attack": 0.02, "peak_ratio": 1.0, "decay": 0.5,
        },
        "continuity_profile": {
            "style": "plucked_discrete",
            "min_section_coverage_pct": 55,
            "max_gap_beats": 2.0,
            "phrase_grouping_hint": (
                "Guzheng is plucked — rests are natural. BUT phrases "
                "must be GROUPED as sweeping runs, broken chords, or "
                "tremolo, not one pluck per bar. A featured chorus "
                "guzheng should pour a cascading pentatonic run, not "
                "punctuate single notes."
            ),
        },
    },

    "piano": {
        "performance_recipes": {
            "default_vibrato": None,
            "long_note_threshold_beats": 3.0,
            "long_note_ornaments": [],
            "consecutive_step_threshold_beats": 0.25,
            "consecutive_step_ornaments": ["legato_to_next"],
            "phrase_end_ornaments": [],
            "velocity_curve": "decay",
        },
        "auto_rules": [
            {"condition": "next_note_close",
             "add_ornaments": ["legato_to_next"]},
        ],
        "ornament_vocabulary": [
            "staccato", "tenuto", "legato_to_next",
            "grace_note_above", "grace_note_below",
        ],
        "spotlight_profile": {
            "typical_role": "chords",
            "good_at": ["intro", "verse", "chorus", "bridge", "outro"],
            "avoid": [],
            "pairs_with": ["bass", "drums", "pad"],
            "competes_with": ["yangqin", "harp"],
        },
        "idiomatic_motifs": [
            {
                "name": "piano_pop_comp",
                "description": "Modern pop chord comping with voice leading",
                "notes": [
                    {"pitch": 60, "start_beat": 0.0,
                     "duration_beats": 0.5, "velocity": 70,
                     "ornaments": ["legato_to_next"]},
                    {"pitch": 64, "start_beat": 0.0,
                     "duration_beats": 0.5, "velocity": 65,
                     "ornaments": []},
                    {"pitch": 67, "start_beat": 0.0,
                     "duration_beats": 0.5, "velocity": 60,
                     "ornaments": []},
                ],
            },
        ],
        "velocity_envelope_preset": {
            "attack": 0.01, "peak_ratio": 1.0, "decay": 0.4,
        },
        "continuity_profile": {
            "style": "rhythmic_comp",
            "min_section_coverage_pct": 85,
            "max_gap_beats": 0.75,
            "phrase_grouping_hint": (
                "Piano keeps a rhythmic comping pattern (arpeggios or "
                "8th-note chord voicings) going CONTINUOUSLY through "
                "the section. Even during a featured solo on another "
                "instrument, piano maintains its comp. No bar of total "
                "silence unless the section explicitly calls for it."
            ),
        },
    },

    "cello": {
        "performance_recipes": {
            "default_vibrato": {
                "type": "vibrato_light", "depth": 25, "rate_hz": 4.5,
            },
            "long_note_threshold_beats": 2.0,
            "long_note_ornaments": ["vibrato_light"],
            "consecutive_step_threshold_beats": 0.5,
            "consecutive_step_ornaments": ["legato_to_next"],
            "phrase_end_ornaments": ["vibrato_light"],
            "velocity_curve": "swell",
        },
        "auto_rules": [
            {"condition": "duration > 2.0",
             "add_ornaments": ["vibrato_light"]},
            {"condition": "next_note_close",
             "add_ornaments": ["legato_to_next"]},
        ],
        "ornament_vocabulary": [
            "vibrato_light", "vibrato_deep", "vibrato_delayed",
            "slide_up_from", "slide_down_from",
            "legato_to_next", "staccato", "tenuto",
        ],
        "spotlight_profile": {
            "typical_role": "bass",
            "good_at": ["verse", "chorus", "bridge", "outro"],
            "avoid": [],
            "pairs_with": ["piano", "pad", "strings"],
            "competes_with": ["contrabass"],
        },
        "idiomatic_motifs": [
            {
                "name": "cello_bass_walk",
                "description": "Walking bass line with smooth voice leading",
                "notes": [
                    {"pitch": 43, "start_beat": 0.0,
                     "duration_beats": 1.0, "velocity": 75,
                     "ornaments": ["legato_to_next"]},
                    {"pitch": 45, "start_beat": 1.0,
                     "duration_beats": 1.0, "velocity": 72,
                     "ornaments": ["legato_to_next"]},
                    {"pitch": 47, "start_beat": 2.0,
                     "duration_beats": 2.0, "velocity": 78,
                     "ornaments": ["vibrato_light"]},
                ],
            },
        ],
        "velocity_envelope_preset": {
            "attack": 0.12, "peak_ratio": 1.0, "decay": 0.25,
        },
        "continuity_profile": {
            "style": "continuous_bowed",
            "min_section_coverage_pct": 80,
            "max_gap_beats": 1.0,
            "phrase_grouping_hint": (
                "Cello bass line is continuous — walk the roots with "
                "passing tones and legato transitions. When supporting, "
                "sustain long tones with vibrato; when grooving, keep a "
                "steady root-fifth pulse. Avoid quarter-note-and-silence "
                "patterns."
            ),
        },
    },

    "strings": {
        "performance_recipes": {
            "default_vibrato": {
                "type": "vibrato_light", "depth": 20, "rate_hz": 5.0,
            },
            "long_note_threshold_beats": 2.0,
            "long_note_ornaments": ["vibrato_light"],
            "consecutive_step_threshold_beats": 1.0,
            "consecutive_step_ornaments": ["legato_to_next"],
            "phrase_end_ornaments": [],
            "velocity_curve": "swell",
        },
        "auto_rules": [
            {"condition": "duration > 2.0",
             "add_ornaments": ["vibrato_light"]},
        ],
        "ornament_vocabulary": [
            "vibrato_light", "vibrato_deep",
            "legato_to_next", "tenuto",
        ],
        "spotlight_profile": {
            "typical_role": "pad",
            "good_at": ["chorus", "bridge", "outro"],
            "avoid": [],
            "pairs_with": ["piano", "pad", "cello"],
            "competes_with": ["viola"],
        },
        "idiomatic_motifs": [
            {
                "name": "strings_pad_swell",
                "description": "Sustained pad chord with swell",
                "notes": [
                    {"pitch": 60, "start_beat": 0.0,
                     "duration_beats": 4.0, "velocity": 55,
                     "ornaments": ["vibrato_light"]},
                    {"pitch": 64, "start_beat": 0.0,
                     "duration_beats": 4.0, "velocity": 52,
                     "ornaments": []},
                    {"pitch": 67, "start_beat": 0.0,
                     "duration_beats": 4.0, "velocity": 50,
                     "ornaments": []},
                ],
            },
        ],
        "velocity_envelope_preset": {
            "attack": 0.3, "peak_ratio": 1.0, "decay": 0.35,
        },
        "continuity_profile": {
            "style": "sustained_pad",
            "min_section_coverage_pct": 95,
            "max_gap_beats": 0.5,
            "phrase_grouping_hint": (
                "Strings pad HOLDS chord beds across the full section. "
                "Voice the chord as long whole-notes / double-whole-notes "
                "with light swells at section boundaries. Never emit "
                "staccato pulses; never leave the harmony unsupported."
            ),
        },
    },

    # --- Remaining instruments: minimum-viable extensions ---

    "pipa": {
        "performance_recipes": {
            "default_vibrato": None,
            "long_note_threshold_beats": 1.5,
            "long_note_ornaments": ["tremolo_rapid"],
            "consecutive_step_threshold_beats": 0.25,
            "consecutive_step_ornaments": [],
            "phrase_end_ornaments": [],
            "velocity_curve": "decay",
        },
        "auto_rules": [
            {"condition": "duration > 1.5",
             "add_ornaments": ["tremolo_rapid"]},
        ],
        "ornament_vocabulary": [
            "tremolo_rapid", "glissando_from",
            "grace_note_above", "grace_note_below",
            "staccato", "tenuto",
        ],
        "spotlight_profile": {
            "typical_role": "lead",
            "good_at": ["chorus", "bridge"],
            "avoid": [],
            "pairs_with": ["erhu", "dizi"],
            "competes_with": ["guzheng", "yangqin"],
        },
        "velocity_envelope_preset": {
            "attack": 0.02, "peak_ratio": 1.0, "decay": 0.45,
        },
        "continuity_profile": {
            "style": "plucked_discrete",
            "min_section_coverage_pct": 55,
            "max_gap_beats": 2.0,
            "phrase_grouping_hint": (
                "Pipa is plucked. Group phrases as 轮指 tremolo sustains "
                "or rapid melodic runs, not single-beat punctuations."
            ),
        },
    },

    "xiao": {
        "performance_recipes": {
            "default_vibrato": {
                "type": "vibrato_light", "depth": 15, "rate_hz": 4.5,
            },
            "long_note_threshold_beats": 1.5,
            "long_note_ornaments": ["breath_swell", "vibrato_light"],
            "consecutive_step_threshold_beats": 0.5,
            "consecutive_step_ornaments": ["legato_to_next"],
            "phrase_end_ornaments": ["breath_fade"],
            "velocity_curve": "swell",
        },
        "auto_rules": [
            {"condition": "first_of_phrase",
             "add_ornaments": ["breath_swell"]},
            {"condition": "last_of_phrase",
             "add_ornaments": ["breath_fade"]},
        ],
        "ornament_vocabulary": [
            "breath_swell", "breath_fade",
            "vibrato_light", "vibrato_delayed",
            "legato_to_next", "tenuto",
        ],
        "spotlight_profile": {
            "typical_role": "texture",
            "good_at": ["intro", "outro", "bridge"],
            "avoid": ["chorus"],
            "pairs_with": ["erhu", "guzheng"],
            "competes_with": ["dizi", "flute"],
        },
        "velocity_envelope_preset": {
            "attack": 0.3, "peak_ratio": 0.95, "decay": 0.4,
        },
        "continuity_profile": {
            "style": "continuous_breath",
            "min_section_coverage_pct": 70,
            "max_gap_beats": 1.5,
            "phrase_grouping_hint": (
                "Xiao is a breath instrument — softer than dizi, "
                "breathier, more plaintive. Shape long breath-lines; "
                "use breath_swell into, breath_fade out of each phrase."
            ),
        },
    },

    "yangqin": {
        "ornament_vocabulary": [
            "tremolo_rapid", "grace_note_above",
            "staccato", "tenuto",
        ],
        "spotlight_profile": {
            "typical_role": "accompaniment",
            "good_at": ["verse", "chorus"],
            "avoid": [],
            "pairs_with": ["erhu", "dizi"],
            "competes_with": ["guzheng", "piano", "harp"],
        },
        "continuity_profile": {
            "style": "plucked_discrete",
            "min_section_coverage_pct": 70,
            "max_gap_beats": 1.5,
            "phrase_grouping_hint": (
                "Yangqin (dulcimer) produces crisp plucks but is a "
                "comping instrument — keep a continuous 8th / 16th "
                "filigree pattern, not single hits per bar."
            ),
        },
    },

    "violin": {
        "performance_recipes": {
            "default_vibrato": {
                "type": "vibrato_light", "depth": 30, "rate_hz": 5.5,
            },
            "long_note_threshold_beats": 2.0,
            "long_note_ornaments": ["vibrato_light"],
            "consecutive_step_threshold_beats": 0.5,
            "consecutive_step_ornaments": ["legato_to_next"],
            "phrase_end_ornaments": [],
            "velocity_curve": "swell",
        },
        "auto_rules": [
            {"condition": "duration > 2.0",
             "add_ornaments": ["vibrato_light"]},
        ],
        "ornament_vocabulary": [
            "vibrato_light", "vibrato_deep",
            "slide_up_from", "slide_down_from",
            "legato_to_next", "staccato", "tenuto",
        ],
        "spotlight_profile": {
            "typical_role": "lead",
            "good_at": ["chorus", "bridge"],
            "avoid": [],
            "pairs_with": ["cello", "piano"],
            "competes_with": ["erhu", "viola"],
        },
        "continuity_profile": {
            "style": "continuous_bowed",
            "min_section_coverage_pct": 75,
            "max_gap_beats": 1.0,
            "phrase_grouping_hint": (
                "Violin bows long lyrical lines with vibrato and legato; "
                "when supporting, sustain counter-melodies; never leave "
                "isolated quarter-notes with bar-long gaps."
            ),
        },
    },

    "flute": {
        "performance_recipes": {
            "default_vibrato": {
                "type": "vibrato_light", "depth": 25, "rate_hz": 5.0,
            },
            "long_note_threshold_beats": 2.0,
            "long_note_ornaments": ["breath_swell", "vibrato_light"],
            "consecutive_step_threshold_beats": 0.5,
            "consecutive_step_ornaments": ["legato_to_next"],
            "phrase_end_ornaments": ["breath_fade"],
            "velocity_curve": "swell",
        },
        "auto_rules": [
            {"condition": "first_of_phrase",
             "add_ornaments": ["breath_swell"]},
        ],
        "ornament_vocabulary": [
            "breath_swell", "breath_fade", "flutter",
            "vibrato_light", "grace_note_above",
            "legato_to_next", "staccato", "tenuto",
        ],
        "spotlight_profile": {
            "typical_role": "lead",
            "good_at": ["chorus", "bridge"],
            "avoid": [],
            "pairs_with": ["strings", "piano"],
            "competes_with": ["dizi", "xiao"],
        },
        "continuity_profile": {
            "style": "continuous_breath",
            "min_section_coverage_pct": 75,
            "max_gap_beats": 1.0,
            "phrase_grouping_hint": (
                "Flute is a breath instrument — phrase it in long "
                "legato arcs with breath_swell on entrances. Avoid "
                "choppy staccato quarter-notes when the role is lyrical."
            ),
        },
    },

    "trumpet": {
        "ornament_vocabulary": [
            "staccato", "tenuto", "legato_to_next",
            "slide_up_to", "overblow",
        ],
        "spotlight_profile": {
            "typical_role": "lead",
            "good_at": ["chorus"],
            "avoid": ["intro"],
            "pairs_with": ["piano", "drums"],
            "competes_with": [],
        },
        "continuity_profile": {
            "style": "continuous_breath",
            "min_section_coverage_pct": 65,
            "max_gap_beats": 1.5,
            "phrase_grouping_hint": (
                "Trumpet phrases are brassy and declarative but still "
                "breath-driven. Group notes into punchy but connected "
                "phrases — no single-note-per-bar riffs unless "
                "intentional rhythmic stabs."
            ),
        },
    },

    "clarinet": {
        "performance_recipes": {
            "default_vibrato": {
                "type": "vibrato_light", "depth": 20, "rate_hz": 4.5,
            },
            "long_note_threshold_beats": 2.0,
            "long_note_ornaments": ["vibrato_light"],
            "consecutive_step_threshold_beats": 0.5,
            "consecutive_step_ornaments": ["legato_to_next"],
            "phrase_end_ornaments": [],
            "velocity_curve": "swell",
        },
        "auto_rules": [],
        "ornament_vocabulary": [
            "vibrato_light", "breath_swell", "breath_fade",
            "legato_to_next", "staccato", "tenuto",
        ],
        "spotlight_profile": {
            "typical_role": "counter-melody",
            "good_at": ["verse", "bridge"],
            "avoid": [],
            "pairs_with": ["piano", "strings"],
            "competes_with": ["flute"],
        },
        "continuity_profile": {
            "style": "continuous_breath",
            "min_section_coverage_pct": 70,
            "max_gap_beats": 1.5,
            "phrase_grouping_hint": (
                "Clarinet speaks in long flowing counter-melodies; "
                "breathe between 2-4 bar phrases. No fragmented stabs."
            ),
        },
    },

    "harp": {
        "ornament_vocabulary": [
            "glissando_from", "glissando_to",
            "tremolo_rapid", "tenuto",
        ],
        "spotlight_profile": {
            "typical_role": "texture",
            "good_at": ["intro", "bridge", "outro"],
            "avoid": [],
            "pairs_with": ["strings", "pad"],
            "competes_with": ["guzheng", "yangqin"],
        },
        "continuity_profile": {
            "style": "plucked_discrete",
            "min_section_coverage_pct": 55,
            "max_gap_beats": 2.0,
            "phrase_grouping_hint": (
                "Harp phrases are sweeping arpeggios or rolled chords, "
                "not isolated plucks. Group into cascading figures."
            ),
        },
    },

    "contrabass": {
        "ornament_vocabulary": [
            "staccato", "tenuto", "legato_to_next",
        ],
        "spotlight_profile": {
            "typical_role": "bass",
            "good_at": ["verse", "chorus"],
            "avoid": [],
            "pairs_with": ["piano", "drums"],
            "competes_with": ["cello"],
        },
        "continuity_profile": {
            "style": "continuous_bowed",
            "min_section_coverage_pct": 80,
            "max_gap_beats": 1.0,
            "phrase_grouping_hint": (
                "Contrabass anchors the harmony with sustained roots "
                "or walking lines. Keep the bottom of the mix present "
                "— avoid whole-bar gaps."
            ),
        },
    },

    "viola": {
        "performance_recipes": {
            "default_vibrato": {
                "type": "vibrato_light", "depth": 25, "rate_hz": 5.0,
            },
            "long_note_threshold_beats": 2.0,
            "long_note_ornaments": ["vibrato_light"],
            "consecutive_step_threshold_beats": 0.5,
            "consecutive_step_ornaments": ["legato_to_next"],
            "phrase_end_ornaments": [],
            "velocity_curve": "swell",
        },
        "auto_rules": [
            {"condition": "duration > 2.0",
             "add_ornaments": ["vibrato_light"]},
        ],
        "ornament_vocabulary": [
            "vibrato_light", "legato_to_next",
            "staccato", "tenuto",
        ],
        "spotlight_profile": {
            "typical_role": "texture",
            "good_at": ["bridge"],
            "avoid": [],
            "pairs_with": ["cello", "violin"],
            "competes_with": ["strings"],
        },
        "continuity_profile": {
            "style": "continuous_bowed",
            "min_section_coverage_pct": 75,
            "max_gap_beats": 1.0,
            "phrase_grouping_hint": (
                "Viola bows inner voice counter-melodies or sustained "
                "pads — keep the inner texture continuous, no gaps."
            ),
        },
    },
}


# Run the merge + validation at import time so failures are immediate.
_merge_extensions()

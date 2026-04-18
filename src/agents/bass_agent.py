"""
BassAgent — Round 2 Phase B3.

Deterministic bass line programmer that LOCKS TO THE KICK.

Rules
-----
1. Root note on beat 1 of each chord change (chord progression comes
   from the Orchestrator blueprint, or a simple I-V-vi-IV default if
   none was provided).
2. Bass hit on EVERY kick position in the drum track (passed in from
   the DrumAgent). Pitch = chord root if the kick hits on beat 1-3 of
   a chord; pitch = nearest passing tone (scale degree 2 / 5 / 7) on
   syncopated kick positions.
3. Silence wherever the kick is silent. No root-on-every-beat.

This intentionally rejects "note-per-bar" bass lines — the whole
point of bass in modern pop is the rhythmic interplay with the kick.

Uses `continuity_profile` from the bass card in
`src/knowledge/instruments.py` (rhythmic_comp,
min_section_coverage_pct=70). We don't hard-enforce coverage here;
the CONTINUITY RULES block in the Composer prompt still applies to
LLM-generated bass parts, and this algorithmic bass line is a
drop-in replacement that is always in sync.
"""

from __future__ import annotations

from loguru import logger

from src.music.score import ScoreNote, ScoreTrack


# Scale-degree chromatic offsets (major scale). Used for passing tones.
_MAJOR_SCALE_DEGREES = [0, 2, 4, 5, 7, 9, 11]
# Chinese pentatonic: gong 宫 / shang 商 / jue 角 / zhi 徵 / yu 羽.
_CHINESE_PENTATONIC = [0, 2, 4, 7, 9]


class BassAgent:
    """Algorithmic bass programmer. No LLM."""

    def __init__(self) -> None:
        self._last_kick_positions: list[float] = []

    # ---------------------------------------------------------------
    # Public entry
    # ---------------------------------------------------------------

    def compose_section(
        self,
        section_role: str,
        start_beat: float,
        end_beat: float,
        bars: int,
        key_root_midi: int,
        scale_type: str = "major",
        kick_positions: list[float] | None = None,
        chord_progression: list[str] | None = None,
    ) -> ScoreTrack:
        """Compose the bass track for one section, locked to the kick.

        Args:
            key_root_midi: MIDI pitch of the key root (e.g. 48 for C2).
                The bass lives an octave below the key root usually, so
                callers should pass a bass-range value already.
            kick_positions: list of beat positions where the kick hits
                in this section (from DrumAgent). If None, falls back
                to a 4-on-the-floor beat-1/beat-3 pattern so the bass
                still has something to sit on.
            chord_progression: e.g. ["I", "V", "vi", "IV"] — one entry
                per BAR. If shorter than `bars`, repeated.
        """
        if kick_positions is None:
            kick_positions = [
                start_beat + b * 4.0 + k
                for b in range(bars)
                for k in (0.0, 2.0)
            ]
        self._last_kick_positions = list(kick_positions)

        if not chord_progression:
            chord_progression = ["I", "V", "vi", "IV"]

        scale = (
            _CHINESE_PENTATONIC
            if "pent" in scale_type.lower()
            or "chinese" in scale_type.lower()
            else _MAJOR_SCALE_DEGREES
        )

        # Map chord roman numerals → scale-degree index (0 = root).
        chord_to_degree = {
            "I": 0, "II": 1, "III": 2, "IV": 3, "V": 4, "VI": 5, "VII": 6,
            "i": 0, "ii": 1, "iii": 2, "iv": 3, "v": 4, "vi": 5, "vii": 6,
        }

        notes: list[ScoreNote] = []
        for bar_ix in range(bars):
            chord_name = chord_progression[bar_ix % len(chord_progression)]
            degree = chord_to_degree.get(chord_name, 0)
            root_semitone = scale[degree % len(scale)]
            root_pitch = key_root_midi + root_semitone

            bar_start = start_beat + bar_ix * 4.0
            bar_end = min(bar_start + 4.0, end_beat)
            bar_kicks = [k for k in kick_positions if bar_start <= k < bar_end]
            if not bar_kicks:
                continue

            # Root on bar downbeat (always), then follow kicks thereafter.
            downbeat_done = False
            for i, k in enumerate(bar_kicks):
                # On the downbeat: always the root.
                is_downbeat = abs(k - bar_start) < 0.01
                if is_downbeat and not downbeat_done:
                    pitch = root_pitch
                    velocity = 95
                    downbeat_done = True
                else:
                    # Passing tones on syncopated kick beats.
                    # Choose scale degree 4 (fifth) on the "and of 2"
                    # or beat 3.5, degree 2 (third) on beat 4, and
                    # otherwise the root again.
                    offset_in_bar = k - bar_start
                    if 1.5 <= offset_in_bar < 2.5:
                        pitch = root_pitch + scale[4 % len(scale)]
                    elif 3.0 <= offset_in_bar < 3.75:
                        pitch = root_pitch + scale[2 % len(scale)]
                    elif 3.75 <= offset_in_bar < 4.0:
                        # Leading tone: degree 6 of the NEXT chord root.
                        next_chord = chord_progression[
                            (bar_ix + 1) % len(chord_progression)
                        ]
                        next_deg = chord_to_degree.get(next_chord, 0)
                        next_root = scale[next_deg % len(scale)]
                        pitch = key_root_midi + next_root - 1
                    else:
                        pitch = root_pitch
                    velocity = 80
                # Duration: extend until next kick or bar end (gives
                # the bass a "sustained" feel rather than clicks).
                if i + 1 < len(bar_kicks):
                    dur = bar_kicks[i + 1] - k
                else:
                    dur = bar_end - k
                dur = max(0.125, min(dur, 1.0))
                notes.append(ScoreNote(
                    pitch=int(pitch),
                    start_beat=round(k, 4),
                    duration_beats=round(dur, 4),
                    velocity=velocity,
                ))

        logger.info(
            f"[BassAgent] section={section_role} → {len(notes)} bass "
            f"notes locked to {len(kick_positions)} kick positions"
        )
        return ScoreTrack(
            name="bass",
            instrument="Bass",
            role="bass",
            channel=1,
            program=33,  # GM Electric Bass (finger)
            notes=notes,
        )


def extract_kick_positions(drum_tracks: list[ScoreTrack]) -> list[float]:
    """Extract kick-drum hit positions from a list of DrumAgent tracks.

    Looks for tracks named 'drums_kick' (the DrumAgent convention) and
    returns the sorted unique start_beat values. Returns an empty list
    if no kick track is present (e.g. guzheng_ballad_perc which has
    only shaker/frame-drum).
    """
    kicks: set[float] = set()
    for trk in drum_tracks:
        if trk.name != "drums_kick":
            continue
        for n in trk.notes:
            kicks.add(float(n.start_beat))
    return sorted(kicks)

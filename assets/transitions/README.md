# Transition stems (Round 2 Phase F)

Drop curated `.wav` files in this folder to give the mix bus real ear-candy
at section boundaries. The pipeline's `TransitionAgent` emits events with
these `kind` values; `src/audio/mix.py` looks for the first matching asset
when it places the stem.

## Recognized filenames

The mix bus prefers an exact variant match (one of the names below), and
falls back to any file starting with the `kind` if no exact match exists.
Sample rate **must match** the instrumental render (`settings.render_sample_rate`,
default 44100 Hz) or the stem is silently skipped — resample offline first.

| Kind              | Preferred variants                                   |
|-------------------|------------------------------------------------------|
| `riser`           | `riser_8beat.wav`, `riser_16beat.wav`, `riser_short.wav` |
| `reverse_cymbal`  | `reverse_cymbal_short.wav`, `reverse_cymbal_long.wav` |
| `impact`          | `impact_deep.wav`, `impact_crisp.wav`, `impact_wide.wav` |
| `sub_drop`        | `sub_drop.wav`                                       |
| `downlifter`      | `downlifter.wav`, `downlifter_filter.wav`            |
| `snare_roll`      | `snare_roll_accel_1bar.wav`, `snare_roll_accel_2bar.wav` |

## Where to find free, legally-clean stems

- **freesound.org** — CC-0 / CC-BY sound library. Search "riser", "impact", etc.
- **cymatics free packs** — most are sample-pack terms that permit use.
- **Splice free samples** — free tier has a lot of trailer-style FX.
- Roll your own in a DAW — a 2-bar pink-noise high-pass sweep is a fine riser.

The mix bus is entirely optional. With an empty folder the pipeline still
writes the final mix — it just has no sample-based transition ear-candy.

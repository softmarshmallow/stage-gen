# Authored game sound effects

> **Contract maturity: exact-current prepared-package contract.**

A genre's audio contract binds its semantic events to named effects, says
how each effect is realized, and says what the soundtrack does at the run's
edges. Today the runner member owns one, `runner/audio.toml`
with the exact identity `runner-audio-v4`. An effect is realized as a
provider-free `oscillator_sweep_v1` the consumer synthesizes, as a
`generated_clip_v1` the execution graph buys once from a text-to-sound-effect
route and the consumer plays back, or as a `spoken_line_v1` - a bark - the
graph buys once from a text-to-speech route on a voice the game's catalog
casts; that third kind has its own page, [game-voice.md](game-voice.md). The
event bindings are the same in every case, so a cue can change realization
without remapping gameplay. Eight events are consequences of player verbs and
every package binds all eight; the ninth, `stage_start`, is an announcement
and may be left silent.

This page is the authoring and execution contract for the generated kind. The
measured behaviour of the route it is bought from - what it can and cannot be
asked for - is the model boundary in
[spec/model-eleven-text-to-sound-v2.md](spec/model-eleven-text-to-sound-v2.md).
**Read that first.** The pipeline does not compensate for the model: the prompt
you write is the prompt it hears.

## Ownership

| Owner | Owns |
| --- | --- |
| `runner/audio.toml` | Event-to-effect bindings, each effect's realization, for a generated clip the prompt, exact duration, prompt influence, and playback mix, and the music transitions on death, restart, and hurt |
| `game.toml` | Exact audio source path |
| Runtime (web consumer) | When events fire, Web Audio lifecycle, decoding, applying the authored gain and rate lift, and performing the music transitions on the soundtrack element |
| Recipe | Provider/model selection, one generate node and one admission node per clip, provenance, and cache identity |
| Model doc | Which cues the route serves, how to word them, and why some are out of reach |

## Current source

```toml
schema_version = 4
kind = "runner-audio-v4"
game_id = "example-game"
revision = 1

[music.death]
action = "stop"
fade_seconds = 1.2
curve = "exponential"

[music.restart]
action = "play"
fade_seconds = 0.5
curve = "linear"

[music.hurt]
duck_gain = 0.4
fade_seconds = 0.05
hold_seconds = 0.2
recovery_seconds = 0.8
curve = "linear"

[bindings]
takeoff = "takeoff_whistle"
air_jump = "air_jump_whistle"
land = "soft_landing"
slide = "leaf_slide"
hazard_cleared = "clear_sparkle"
collect = "token_chime"
hurt = "hull_clank"
death = "hatch_release"

[[effects]]
effect_id = "takeoff_whistle"
display_name = "Takeoff Whistle"

[effects.realization]
kind = "oscillator_sweep_v1"
waveform = "triangle"
start_frequency_hz = 330
end_frequency_hz = 660
duration_milliseconds = 120
gain = 0.16
strength_pitch_multiplier = 0.0

[[effects]]
effect_id = "hull_clank"
display_name = "Hull Clank"

[effects.realization]
kind = "generated_clip_v1"
prompt = "metal clank impact"
duration_seconds = 0.5
gain = 0.5
strength_pitch_multiplier = 0.0

[[effects]]
effect_id = "hatch_release"
display_name = "Hatch Release"

[effects.realization]
kind = "generated_clip_v1"
prompt = "metal hatch latch release"
duration_seconds = 0.6
prompt_influence = 0.3
gain = 0.5
strength_pitch_multiplier = 0.0
```

The eight events are takeoff, air jump, land, slide, hazard cleared, collect,
hurt (the frame a survivable vitals drain connects; silent in a one-hit-kill
package), and death. Every event binds to a declared effect and every declared
effect is bound; the loader refuses anything else before any spend. A generated clip's fields:

| Field | Range | Meaning |
| --- | --- | --- |
| `prompt` | 1–450 characters, already trimmed | Sent to the provider verbatim. No direction, medium line, or originality clause is added. |
| `duration_seconds` | 0.5–30, required | The window the model fills. It is the repetition control: half a second is one event, two seconds is a cycle. Letting the model choose is refused because it overshoots. |
| `prompt_influence` | 0–1, optional | Omitted means the provider default. Unmeasured in this repository; do not assume a direction. |
| `gain` | (0, 1] | Playback gain in the consumer. |
| `strength_pitch_multiplier` | 0–2 | Playback rate becomes `1 + strength × value`, so a chained collect can rise the way the oscillator's does. |

`gain` and `strength_pitch_multiplier` are mixing, not generation. They travel
in the manifest and are **not** part of the clip's cache identity, so rebalancing
a set after listening is a free re-plan, never a redraw. Anything under half a
second stays an oscillator: the route cannot go shorter and trimming is
post-processing.

## Music transitions

What the soundtrack does when the run ends is authored, not assumed, and it is
authored in the vocabulary interactive-music middleware (Wwise, FMOD) already
uses. Three things fire on one game event and are independent of each other:

| Term | Meaning | In this contract |
| --- | --- | --- |
| Action | What the playing music does: stop, pause, resume, play, or nothing. Each carries a fade time and a fade curve; a zero fade is the arcade hard cut. | `[music.death]`, `[music.restart]` |
| Stinger | A short one-shot layered *over* the music at the event, the game-over jingle. Posted beside the action, never instead of it. | The effect bound to `death` (and `hurt`) |
| Ducking | The music dips under a sound effect, holds, and recovers. | `[music.hurt]`, optional |

So a runner's game over is both at once: the death stinger plays immediately
and the music fades out underneath it. The fields:

| Table | Field | Range | Meaning |
| --- | --- | --- | --- |
| `music.death` | `action` | `stop`, `pause`, `continue` | `stop` ends the track; `pause` holds its position; `continue` leaves the music alone |
| | `fade_seconds` | 0–10 | Time to reach silence. Zero applies at once. |
| | `curve` | `linear`, `exponential` | As Web Audio defines them: `exponential` interpolates gain geometrically to a near-zero floor, the equal-loudness feel of a middleware exp/log curve |
| `music.restart` | `action` | `play`, `resume`, `continue` | Must pair with death: `stop → play` (the next shuffled track from the top), `pause → resume`, `continue → continue`. Any other pair is refused at load. |
| | `fade_seconds`, `curve` | as above | The fade-in |
| `music.hurt` (optional) | `duck_gain` | (0, 1) | The music's gain factor while ducked |
| | `fade_seconds`, `hold_seconds`, `recovery_seconds` | 0–10 each | Dip, hold, recover |
| | `curve` | as above | Applied to the dip and the recovery |

Every value here is consumer mixing, like `gain` on a clip: no cache identity
includes it, so tuning after listening is a re-plan and never a redraw. The
table is required and inert in a package with no soundtrack member. A
transition arriving during another cancels it, so a restart pressed mid-fade
starts the next track cleanly. Beat-synced transitions and transition segments
are excluded: the runner's seam rule forbids beat sync. A tape-stop is not
middleware vocabulary and the media element cannot ramp its rate to zero, so
it is not offered either.

## What is checked, and what is not

The only automated verdicts are the ones a decoder can state about the bytes.
Each refuses rather than repairs; a refused draw is redrawn inside the provider
component's single retry owner, at most six attempts.

| Gate | Where | Verdict |
| --- | --- | --- |
| Byte floor | retry owner | Under 2 KiB is a truncated container |
| Dead level | retry owner | Peak below −40 dBFS was heard as silence |
| Clipping | retry owner | Peak at or above −0.1 dBFS was clipped by the model |
| Exact duration | local admission node | More than 0.15 s from the authored duration |

Level is measured, recorded as `peak_dbfs` in the artifact's provenance and its
validation record, and never changed. **No normalization, no trimming, no
concatenation.** That is a repository rule and the spike that produced the model
doc showed why: normalizing to a fixed peak caused the harshness it was meant to
prevent.

Whether the clip *sounds like* its cue is a listening verdict. The validation
record carries `listening_verdict: "not_performed"` until a person makes it.

## Execution

For each generated effect the runner graph contains:

```text
audio/<effect_id>:generate   (sound_effect_generation, elevenlabs route)
  -> audio/<effect_id>:validate   (local: ffprobe duration, ffmpeg level)
  -> manifest-assemble
```

The generate node's card shows the authored prompt exactly. Its cache identity
is the prompt, duration, prompt influence, and output format; the package is a
barrier, not lineage, so an unrelated authored edit does not re-bill a clip.
Oscillator effects add no nodes. The route is declared in the runner's binding
table as `sound_effect_generation` against `elevenlabs`, and execution refuses
before any spend when a clip is declared and `ELEVENLABS_API_KEY` is absent.

The manifest publishes what the consumer plays - `clip`, `duration_seconds`,
`gain`, `strength_pitch_multiplier` - and not what bought it. The prompt lives
in `audio/<effect_id>.mp3.meta.json`.

## Auditioning a prompt

A clip costs a few credits; a package run costs the whole graph. Try the wording
first:

```sh
uv run stage-gen generate-sound-effect --output out/hatch.mp3 --duration 0.6 "metal hatch latch release"
```

Optional `--prompt-influence 0.3` and `--loop`. The same admission applies and
the output is untouched provider bytes with a provenance sidecar. Listen, then
commit the wording to `audio.toml`.

## Validation

```sh
uv run stage-gen package validate --input library/games/iron-petal-unit
uv run stage-gen package plan --input library/games/iron-petal-unit
```

Contract validity proves the closure and the plan, not the sound. Generated
audio needs a separate listening review before any quality or publication claim.

See [Authored game soundtracks](game-soundtrack.md) for the music path this one
mirrors, and [the runner genre](spec/game/runner.md) for the member that owns
the contract.

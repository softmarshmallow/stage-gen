# Authored game sound effects

> **Contract maturity: exact-current prepared-package contract.**

A genre's audio contract binds its semantic events to named effects and says
how each effect is realized. Today the runner member owns one, `runner/audio.toml`
with the exact identity `runner-audio-v2`. An effect is realized either as a
provider-free `oscillator_sweep_v1` the consumer synthesizes, or as a
`generated_clip_v1` the execution graph buys once from a text-to-sound-effect
route and the consumer plays back. The event bindings are the same either way,
so a cue can change realization without remapping gameplay.

This page is the authoring and execution contract for the generated kind. The
measured behaviour of the route it is bought from - what it can and cannot be
asked for - is the model boundary in
[spec/model-eleven-text-to-sound-v2.md](spec/model-eleven-text-to-sound-v2.md).
**Read that first.** The pipeline does not compensate for the model: the prompt
you write is the prompt it hears.

## Ownership

| Owner | Owns |
| --- | --- |
| `runner/audio.toml` | Event-to-effect bindings, each effect's realization, and for a generated clip the prompt, exact duration, prompt influence, and playback mix |
| `game.toml` | Exact audio source path |
| Runtime (web consumer) | When events fire, Web Audio lifecycle, decoding, and applying the authored gain and rate lift |
| Recipe | Provider/model selection, one generate node and one admission node per clip, provenance, and cache identity |
| Model doc | Which cues the route serves, how to word them, and why some are out of reach |

## Current source

```toml
schema_version = 2
kind = "runner-audio-v2"
game_id = "example-game"
revision = 1

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

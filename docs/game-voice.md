# Authored game voice

> **Contract maturity: exact-current prepared-package contract.**

A game's *voice* is two things: a **cast** - the voices the game may speak in,
each an externally-held identity with a rights statement, catalogued in the
root sibling `voices.toml` with the exact identity `game-voices-v1` - and the
**lines** those voices read. Today the only lines are barks: a genre audio
contract realizes an effect as a `spoken_line_v1`, the execution graph buys
the read once from a text-to-speech route on the voice the catalog casts, and
the consumer plays it exactly as it plays any clip. The runner is the first
host, announcing its stage start in `runner/audio.toml`.

The measured behaviour of the route - what it can and cannot be asked for - is
the model boundary in [spec/model-eleven-v3.md](spec/model-eleven-v3.md).
**Read that first.** The pipeline does not compensate for the model: the text
you write, annotations included, is the text it reads.

## Vocabulary

The industry's word for a short, event-triggered spoken one-liner is a
**bark** - "Let's go!", "Reloading!", the line a character throws at a moment.
Its non-verbal sibling - the jump grunt, the hit gasp, the death cry - is an
**effort**. Both are voice used as a sound effect, which is exactly why they
live in the audio contract beside the oscillator sweeps and generated clips
rather than in a script: they answer an event, not a line of dialogue.

A **voiced script** - a character's dialogue read line by line in a visual
novel or cutscene - is the other use of the same cast, and is not built yet.
The seam it will use is at the end of this page.

## Ownership

| Owner | Owns |
| --- | --- |
| `voices.toml` | Each `voice_id`, its display name, language, casting note for a person, rights status and basis, and the provider voice it resolves to with the date that was last checked |
| Genre audio contract (`runner/audio.toml`) | Which event a line answers, the verbatim text with its delivery annotations, the `voice_id` that reads it, stability, the length ceiling, and the playback mix |
| `game.toml` | Exact `voices.toml` source path, bound per genre member the way `fx.toml` is |
| Recipe | Provider/model selection, one speak node and one admission node per line, the cache identity, provenance, and publishing the measured length |
| Runtime (web consumer) | When the event fires, Web Audio lifecycle, decoding, applying the authored gain and rate lift, and holding the one announcement that fires before audio can start |
| Model doc | What the route serves, how annotations behave, and what is out of reach |

Provider and model identifiers never appear in an authored contract. The line
names a voice; the catalog names a provider reference; the binding table names
the route. A recast is a catalog edit.

## Current source

The cast:

```toml
schema_version = 1
kind = "game-voices-v1"
game_id = "iron-petal-unit"
revision = 1

[[voices]]
voice_id = "mira"
display_name = "Mira"
language_code = "ja"
casting = "Eleven-year-old rescue pilot: bright, quick, never breathy."
rights_status = "unreviewed"           # "restricted" | "redistribution-approved" need a basis
rights_basis = []

[voices.provider]
name = "elevenlabs"
voice = "6awt6FKyZGV0HyQEwisX"         # the provider's own reference, opaque here
verified_on = "2026-09-03"
```

`voice_id` values are unique and canonically ordered. A status other than
`unreviewed` requires at least one basis line. `verified_on` is when the
reference was last seen on the provider; hosted voices come and go, and an old
date is a prompt to re-check, not a gate.

The line, in the runner's audio contract (`runner-audio-v4`):

```toml
[bindings]
stage_start = "mira_go"                 # the one binding that may be absent
takeoff = "servo_takeoff"
# ... the other seven verb events, all required

[[effects]]
effect_id = "mira_go"
display_name = "Mira: Here We Go"

[effects.realization]
kind = "spoken_line_v1"
text = "[excited][shouting] よーし、いくよーっ！"
voice_id = "mira"
stability = 0.5
max_seconds = 3.0
gain = 0.7
strength_pitch_multiplier = 0.0
```

`text` is sent verbatim, brackets included, up to 1000 characters - a bark is a
line, not a paragraph. `stability` is optional and passes through; `max_seconds`
is required, because the route has no duration control and a bark has a frame
budget. `gain` and `strength_pitch_multiplier` are consumer mixing.

### Writing the text

Annotations steer the words after them: `[excited]`, `[cheerful]`,
`[shouting]`, `[determined]`, `[giggles]`, `[whispers]`. CAPS carry emphasis,
`…` buys a beat, and a doubled vowel or a small っ (`いくよーっ`) stretches and
snaps a delivery in a way no tag does. Short lines are the model's weak spot;
the fix is direction and voice, never a run-up, because a run-up is only
usable by trimming and trimming is forbidden.

## Events

The runner posts nine. Eight are consequences of player verbs and every
package binds all eight. The ninth, `stage_start`, is an announcement: the
first frame of a boot - with a stage-start cut-in that is the intro's first
frame, so the line and the rip are one beat; without one, the first running
frame - and never on a restart. It is the one binding a package may leave
silent, because silence is a legitimate announcement where a verb's
consequence is not.

Any event may bind a spoken line. Iron Petal binds one; an effort on `hurt`
or `death` is the same mechanism and a different authoring choice.

## Identity

A line's cache identity is the text, the resolved provider and voice
reference, the stability, the language, and the output format, under the
`runner-speech-line-v1` contract. It deliberately excludes:

- **gain, pitch response, and `max_seconds`** - they change how a line is
  played or judged, not which line was read, so a rebalance after listening is
  a re-plan and never a redraw;
- **the seed** - measured, it pins the length of a read and not its waveform,
  so it cannot make a draw repeatable and is never sent.

The same `voice_id` recast to another provider voice is a different asset.

## What is checked, and what is not

| Gate | Where | Verdict |
| --- | --- | --- |
| Byte floor | retry owner | Under 2 KiB is a truncated container |
| Dead level | retry owner | Peak below −40 dBFS was heard as silence |
| Clipping | retry owner | Peak at or above −0.1 dBFS was clipped by the model |
| Length ceiling | retry owner | Longer than `max_seconds` (+50 ms of frame quantization) is refused and redrawn |
| Cast | package resolver, offline | A `voice_id` the catalog lacks, or a line with no catalog bound, is refused before any plan |
| Route | graph builder, offline | A voice cast on a provider the binding table does not route is refused before any spend |

Level and length are measured from one decode pass over the bytes and
recorded; nothing is changed. **No normalization, no trimming, no
concatenation.** Whether the line *sounds like the character* is a listening
verdict, recorded as `listening_verdict: "not_performed"` until a person makes
it.

## Execution

For each spoken line the runner graph contains:

```text
speech-<effect_id>-generate   (speech_generation, elevenlabs route, the cast voice)
  -> speech-<effect_id>-validate   (local: ffprobe, level and length facts)
  -> manifest-assemble
```

The generate node's card shows the authored text exactly. Execution refuses
before any spend when a line is declared and `ELEVENLABS_API_KEY` is absent.

The manifest publishes what the consumer plays - `clip`, `duration_seconds`,
`gain`, `strength_pitch_multiplier` - under the same shape as a generated
clip, so the runtime treats the two identically. `duration_seconds` is the
**measured** read, taken off the admission record, since the route never took
one. The text and the provider voice live only in
`audio/<effect_id>.mp3.meta.json`.

## Auditioning a line

```sh
uv run stage-gen generate-speech --output out/go.mp3 --voice 6awt6FKyZGV0HyQEwisX --stability 0.5 --language ja "[excited][shouting] よーし、いくよーっ！"
```

The command takes the provider's voice reference directly, as the sound-effect
audition takes a raw prompt: it is a tool for choosing, not a package. The same
level gates apply; the output is untouched provider bytes with a provenance
sidecar. Listen, then commit the text to the audio contract and the voice to
the catalog.

## Validation

```sh
uv run stage-gen package validate --input library/games/iron-petal-unit
uv run stage-gen package plan --input library/games/iron-petal-unit
```

Contract validity proves the cast resolves and the plan is sound, not the
performance. Generated speech needs a separate listening review before any
quality or publication claim, and a voice's rights statement is the author's,
never inferred from a provider's terms.

## The seam for a voiced script

The sequence contract already says what a voiced utterance must carry before
`after_voice` can be used: its digest, language, speaker identity, duration,
rights, and utterance binding
([spec/game/dialogue-and-cutscene-sequences.md](spec/game/dialogue-and-cutscene-sequences.md)).
Every one of those exists here: the artifact digest and duration in the
admission record, the language and rights on the catalog voice, the speaker
as `voice_id`. What a script adds is the binding of a line of dialogue to a
read - a per-utterance realization owned by the scenario or sequence rather
than by an event - and a character profile naming its `voice_id`. Neither is
written; both consume the modality, the route, the catalog, and the gates on
this page unchanged.

See [Authored game sound effects](game-sound-effects.md) for the contract this
kind sits inside, and [the runner genre](spec/game/runner.md) for the member
that hosts it.

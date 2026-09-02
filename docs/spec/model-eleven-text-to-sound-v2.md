# Sound-effect model adapter contract

Request surface verified against ElevenLabs' published API reference on
2026-09-02. Behavioural findings below were measured in this repository over
roughly 370 generations, and every accepted or rejected verdict came from a
listening review by the task owner; nothing here was judged by an agent. Sample
sizes are given because most of them are small.

This page records the model-specific boundary. General provider procedure lives
in [../providers.md](../providers.md); the component contract lives in
[../component-contract.md](../component-contract.md); the authored contract that
consumes this route, and the gates it applies, is
[../game-sound-effects.md](../game-sound-effects.md).

## Route

- Model: `eleven_text_to_sound_v2` (the only value the endpoint accepts).
- Endpoint: `POST https://api.elevenlabs.io/v1/sound-generation`.
- Credential: header `xi-api-key`, from `ELEVENLABS_API_KEY`.
- Input: text only. There is no reference-audio input and no seed.
- Output: audio bytes in the requested container.

### Request surface

| field | range | note |
|---|---|---|
| `text` | up to 450 characters | the whole prompt |
| `duration_seconds` | 0.5 to 30, or null | null lets the model choose |
| `prompt_influence` | 0 to 1, default 0.3 | |
| `loop` | boolean, default false | v2 only |
| `output_format` | query parameter | mp3, pcm, ulaw, alaw and opus variants |

`duration_seconds` is honoured exactly: 58 of 58 clips landed within 60 ms of
the request, the residual being mp3 frame quantization. There is no seed, so
two identical requests are independent draws.

## What this model is

**It is a foley engine, not a synthesizer.** It reproduces sounds that exist in
the physical world and were plausibly recorded. It does not produce the
synthesized, non-diegetic cues that a large part of game audio consists of.

A door, a footstep, an axe swing, an arrow in flight, a blade on armour: the
game plays approximately what a microphone would have captured, and the model
serves these well. A coin pickup, a jump, a power-up, a spell: the game plays a
sound that was *synthesized*, that resembles nothing real, and that a listener
recognises by convention rather than by resemblance. The model has no referent
for these and fails on them.

Across 141 scored draws, classified by cue and by how the prompt was written:

| | accepted | |
|---|---|---|
| foley cue, prompt names the event and its material | 25/37 | **68%** |
| foley cue, prompt names the object or is abstract | 0/16 | 0% |
| foley cue named well, duration too long | 0/6 | 0% |
| stylized cue, plain conventional name | 6/25 | 24% |
| stylized cue, prompt names the medium or idiom | 4/24 | 17% |
| stylized cue, prompt describes it physically | 0/33 | 0% |
| **all diegetic foley cues** | **25/59** | **42%** |
| **all stylized cues** | **10/82** | **12%** |

The class matters, and within the foley class the *naming* matters just as much:
a diegetic cue named badly scores zero, the same as a stylized cue described
physically. Both halves of the table have to be right at once.

Rewriting a stylized cue as a concrete physical event makes it strictly worse -
zero of thirty-three - because the model then correctly delivers reality instead
of the convention:

| authored cue | physical rewrite | outcome |
|---|---|---|
| `character jump` | `boots pushing off gravel` | a footstep, which is what jumping actually sounds like and not what a jump cue sounds like |
| `coin pickup` | `small metal coin ringing on stone` | coins spilling, not a coin being collected |
| `ui button click` | `plastic switch clicking` | worse than the plain conventional name |

## Prompting

### The subject noun is the entire prompt

Decoration is a measured null. Across 36 blinded clips, twelve cues, three arms
holding duration and `prompt_influence` fixed:

| arm | mean score | yes | ok | no |
|---|---|---|---|---|
| bare subject | 1.00 | 4 | 4 | 4 |
| plus a `single one-shot` prefix | 1.00 | 4 | 4 | 4 |
| plus `, sound effects foley, high-quality, professionally recorded` | 1.00 | 4 | 4 | 4 |

Identical, to the clip; and each arm won four of the twelve cues. The
production-tag suffix that vendor and third-party guides recommend — the
supposed analogue of writing `35mm, f/1.4` on an image prompt — bought nothing
here. Do not spend prompt budget on it.

### Name the event, not the object

The clearest single result in the evidence. Same cue, three wordings:

| prompt | outcome |
|---|---|
| `bowstring release` | fails — returns the wood |
| `wooden bow creak and arrow whoosh` | fails — returns the wood |
| `arrow flying past` | **3/3** |

Naming the object gives the object's material. Naming the event in the air gives
the event. `footsteps on stone`, `wooden door opens` and `heavy axe swing` are
all of the winning shape: an action, with the surface or material it acts on.

### Naming the medium reaches stylized cues, at a price

For a stylized cue there is one wording that gets anywhere: name the *convention*
rather than the physics or the game event. `retro video game coin collect sound`,
`retro 2D platformer jump blip`, `arcade game power up jingle`,
`video game magic spell sound effect`.

It does not raise the hit rate. Medium-named stylized cues scored 4/24 against
6/25 for the plain conventional name - indistinguishable at these sample sizes.
What it changes is *reachability*: `magic` had failed 14 consecutive draws across
four wordings and produced its first usable clip here. A cue that was impossible
became merely unreliable.

The price is that the asset is bound to the idiom named. Two of the four
successes were qualified as working "under certain conditions, not universally" -
a `retro 2D platformer jump blip` belongs to a retro 2D platformer and to nothing
else. So this wording is only available where the game's declared `[style]`
already matches the idiom, and it cannot be applied generically.

### Avoid words that name a human act of speech

`magic spell cast` returned a human voice speaking an incantation on five draws
out of five. "Spell" and "cast" are words about utterance. Three further
wordings that dropped them still failed, on loudness and piercing brightness
rather than on voice, so the cue is out of reach for a second reason; but the
first failure was purely lexical and is worth avoiding generally.

## Parameters

### `duration_seconds` is the repetition control

The model fills whatever window it is given. Ask for two seconds of
`footsteps on stone` and it delivers a walk cycle; ask for half a second and it
delivers one step. Same bare prompts, twelve cues, counting clips containing
more than one discrete event:

| `duration_seconds` | clips with more than one event |
|---|---|
| 0.5 | **0/12** |
| 1.0 | 1/12 |
| 2.0 | 4/12 |
| null | 5/12 |

There is no repetition parameter. `loop` was false throughout, and prompt words
intended to suppress repetition changed nothing. Auto duration also overshoots
badly — a `ui button click` came back at 16.0 seconds.

**Set `duration_seconds` explicitly, per cue, and keep it short.** Duration is
authored cue data, not a global default: an explosion needs more than a second,
a UI tick needs half of one.

### Output level is uncontrolled

Two draws of one identical prompt at identical parameters came back **43 dB
apart** — one at -1.4 dBFS, its twin at -44.2 dBFS, which a listener described
as "no sound at all". Across sixty raw clips levels ran -41.8 to 0.0 dBFS, and
within a single cue's five draws the spread reached 40.9 dB. Clips that peak at
exactly 0.0 dBFS have been clipped by the model and were heard as too loud.

There is no level parameter. This is a **selection and rejection** problem, not
a repair problem; see below.

### `prompt_influence`

Left at the 0.3 default throughout. A probe at 1.0 exists in the spike record
but was never scored, so this repository has no evidence about it. Do not assume
a direction.

## Selection

Given no seed and uncontrolled level, quality per draw is a lottery and the only
mechanism that moves the outcome is drawing more than once. Measured
single-draw acceptance was 24 of 60 raw clips, and best-of-five yielded at least
one shippable asset for nine of twelve cues.

Draw N, validate each, and let a reviewer select. Treat every draw as
independent.

## Post-processing is forbidden

**The asset is whatever the provider returns.** No normalization, no equalization,
no trimming, no concatenation. This is a repository rule, and the evidence
supports it: an earlier round of this work peak-normalized every clip to
-1 dBFS and drew nine complaints of harshness across 36 clips; the same
vocabulary reviewed raw drew **zero**, and its per-draw acceptance rate was
*higher*. The normalization caused the defect it was meant to prevent.

Two consequences follow, and neither has a workaround.

**Level screening is a rejection rule.** Measure a draw, refuse it, draw again.
Measuring and refusing leaves the bytes untouched and is validation, not
post-processing. Repairing a bad draw is forbidden even though the fix is trivial.

**The 0.5 second floor is a hard wall.** Cues shorter than half a second cannot
be served, because reaching them would require trimming.
`library/games/iron-petal-unit/runner/audio.toml` declares 90–170 ms envelopes
for its short cues, all under the floor. Those cues stay synthesized. This is
not a temporary gap — a synthesized 90 ms servo sweep is both cheaper and more
precise than anything this route could return, and it is a stylized cue besides,
so the taxonomy above rejects it independently.

## Scope

Suitable: doors, footsteps, drawers and other object handling, weapon swings and
impacts, arrows and projectiles in flight, body impacts, mechanical and
environmental texture, ambience beds.

Reachable but unreliable, and only when the game's declared style matches the
idiom named: stylized cues written as a medium — coin collects, jump blips,
power-up jingles, spell effects. Budget many draws and expect most to be
rejected.

Not suitable: any cue under 0.5 seconds; stylized cues in a game whose style does
not match one of the idioms the model knows; anything requiring a consistent
output level within a set, since level cannot be controlled or repaired.

Marginal: explosions — acceptable in isolation at one second, but reported as not
aligning with the visuals at every duration tried.

## Open questions

- Which idioms the model actually knows. `retro`, `arcade`, `2D platformer` and
  `8-bit` were tried once each; the vocabulary of recognised conventions is
  otherwise unmapped, and it bounds what stylized cues are reachable.
- Whether a set of cues generated for one game can be made to sit together, given
  that level varies by up to 40 dB across draws and cannot be corrected.
- `prompt_influence`, entirely unmeasured here.
- Whether `loop` produces a genuinely seamless ambience bed. Four clips were
  generated in the first round and never reviewed.
- Lossless output. Everything measured used `mp3_44100_192` so that review
  clips would play anywhere; a pipeline would want PCM.

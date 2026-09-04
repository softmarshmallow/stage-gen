# Speech model adapter contract

> **Checked by:** `tests/contract/test_current_game_docs.py`.

Request surface verified against the account's live model listing on
2026-09-03. Behavioural findings below were measured in this repository over
35 generations (`spikes/tts-elevenlabs/`, rounds 1 and 1b); every listening
verdict is the task owner's, and the sample sizes are small enough that each
finding says so.

This page records the model-specific boundary. General provider procedure lives
in [../providers.md](../providers.md); the sibling sound-effect boundary, whose
findings do **not** transfer, is
[model-eleven-text-to-sound-v2.md](model-eleven-text-to-sound-v2.md); the
authored contract that consumes this route is
[../game-voice.md](../game-voice.md).

## Route

- Model: `eleven_v3`. Reachable on this key with `requires_alpha_access` false.
  `eleven_v3_conversational` exists at half the character cost and is
  unexplored.
- Endpoint: `POST https://api.elevenlabs.io/v1/text-to-speech/{voice}`.
- Credential: header `xi-api-key`, from `ELEVENLABS_API_KEY`.
- Input: text and a voice reference. No reference audio.
- Output: audio bytes in the requested container.

### Request surface

| field | range | note |
|---|---|---|
| `text` | up to 5000 characters | verbatim, bracketed delivery tags included |
| `voice` | path segment | the provider's own voice reference |
| `voice_settings.stability` | 0 to 1 | documented as three modes: 0.0 creative, 0.5 natural, 1.0 robust |
| `language_code` | ISO code | optional; the model infers otherwise |
| `output_format` | query parameter | mp3 variants; this adapter requests `mp3_44100_192` |

The model reports `can_use_style = false` and `can_use_speaker_boost = false`,
so nothing but `stability` is sent. There is no duration parameter. A `seed`
is accepted and deliberately never sent - see below.

## What this model is

A speech model that takes direction. Where the sound-effect route is a foley
engine with no notion of a performer, this route has one: the voice is half
the result, and the bracketed annotations (`[excited]`, `[shouting]`,
`[giggles]`, `[whispers]`) steer the read of the words that follow them.

The three findings that shape every request:

### Level is controlled

Every one of the 35 clips landed between −0.2 and −2.1 dBFS: no silent draws,
nothing pinned at the 0.0 dBFS ceiling. The sound-effect route's spec records
two draws of one prompt arriving 43 dB apart and, on a Japanese shout, ten of
twenty-four clips clipped at exactly 0.0 dBFS. That route's level problem is
unfixable by rule (repair is post-processing; refusal is the only remedy). This
route does not appear to have it. The level gates are kept anyway, as cheap
insurance, and they have never fired.

### The seed pins duration and nothing else

| group | seed | durations |
|---|---|---|
| A | 111111 | 2.160 s, 2.160 s, 2.160 s |
| B | 222222 | 2.000 s, 2.000 s, 2.000 s |
| none | — | 2.160 s, 2.160 s, 2.320 s, 2.160 s |

Exact within a seed, different between seeds, spread without one. But the
waveforms inside a seed group are **uncorrelated** - r between −0.10 and +0.24
across nine pairs, the difference signal measuring 2.1 to 2.8 dB *louder* than
the audio itself. Three seeded draws in round 1 shared a byte count to the byte
and decoded to three unrelated takes.

So the seed is a length control, not a reproducibility handle. A cache cannot
be keyed on `(text, voice, settings, seed)` and expect the clip back; the
adapter never sends one, and the identity records none. Selection stays a
human choice over N draws, with the chosen bytes as the only durable artifact -
the same conclusion the sound route reaches, by a different mechanism.

Caveat: n = 3 per seed group, and mp3 duration is frame-quantized, so an exact
match is cheaper than it looks. Two independent groups matching internally
while the unseeded group spread is the load-bearing part.

### Tags cost time, and less time than speaking them would

| text | mean length |
|---|---|
| `いくよっ！` | 1.00 s |
| `[excited] いくよっ！` | 1.28 s |
| `よーし、いくよーっ！` | 1.84 s |
| `[excited][shouting] よーし、いくよーっ！` | 2.20 s |

The tags change the read by 20 to 28%, which rules out their being dropped.
Speaking "excited" or "excited shouting" aloud would cost far more than the
0.28 s and 0.36 s observed, which argues for steering over recitation; the task
owner's listen confirmed it ("the annotations work from v3"). On the v2 model
family a bracketed tag is ignored or read out loud as words - this route
requires `eleven_v3`.

## Parameters

### There is no duration control

The model decides how long a line takes. Bare lines came back at 0.88 to
2.48 s; the same text is read at different lengths on different draws (spread
160 to 240 ms unseeded). A cue with a frame budget therefore states the longest
read it tolerates, and a longer draw is **refused and redrawn** inside the
retry owner. It is never trimmed: post-processing is forbidden repository-wide,
and the sound spike measured why.

Corollary: the run-up trick - giving the voice a sentence or two to accelerate
through before the line - is out. Two run-up clips came back at 7.68 s and
8.56 s against 2.24–2.48 s for the same line cold, and are usable only by
trimming to the last beat.

### `stability`

Three documented modes. Measured, 0.0 against 1.0 barely moved duration
(2.16 s against 2.24–2.40 s), so if the modes differ it is in expressiveness,
which only a listen sees. Unscored in this repository; the shipped line uses
0.5.

### Language

Suzu (`6awt6FKyZGV0HyQEwisX`, ja-JP) read Japanese text correctly with and
without `language_code`. The parameter is passed through when the catalog
voice declares one; whether it changes anything is unmeasured.

## Selection

Quality per draw is still a lottery, for a different reason than the sound
route: not level, but delivery. Draw N, admit each on length and level, and let
a reviewer select. Every draw is independent; the seed does not change that.

## Post-processing is forbidden

The asset is whatever the provider returns. No normalization, no trimming, no
concatenation. Level screening and the length ceiling are rejection rules:
measure, refuse, draw again.

## Scope

Suitable: barks - short, event-triggered one-liners - on a voice the game's
catalog casts, in any of the 74 languages the model lists, Japanese among
them. The stock roster includes a young ja-JP character voice; a game whose
cast needs a voice the roster lacks needs voice design, which is out of scope.

Reachable but unmeasured: efforts (non-verbal exertions - a jump grunt, a hit
gasp); longer scripted lines for a visual novel, where the 5000-character
ceiling and no duration budget make a different admission story.

Not suitable: anything whose length must be exact; anything needing a
reproducible draw; the v2 model family when tags are relied on.

## Open questions

- `stability` modes by ear, at matched text.
- Whether `language_code` changes a read on a voice already cast in that language.
- `eleven_v3_conversational`, at half the cost.
- Efforts: whether a purely non-verbal tag (`[laughs]`, `[gasps]`) with no
  words reads as one.
- Whether one voice holds its delivery across a whole game's set of lines.
- PCM output for a pipeline, once a consumer wants it.

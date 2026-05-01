# BGM pack library

Background music for the side-scroll runtime. **Curated**, not generated:
the world prompt picks one pack at runtime; the audio file itself is a
hand-authored / licensed track that lives in this folder.

This pack library lives under `fixtures/` (alongside `prompts.txt` and
`styles.txt`) because it is **input data to the pipeline**, not a
generated artifact. The web runtime serves these files through a thin
mapped route — no duplication into `web/public/` required.

## Folder layout

```
fixtures/bgm/
├── index.json           # manifest — every pack registered here
├── README.md            # this file
├── forest_calm.mp3
├── snowy_majestic.mp3
└── …
```

Flat layout: one audio file per pack, sitting next to the manifest. Move
to per-pack subdirs only if a pack needs multiple stems / intros / alts.

## Manifest schema (`index.json`)

```json
{
  "version": 1,
  "packs": [
    {
      "id": "forest_calm",
      "file": "forest_calm.mp3",
      "title": "Forest Calm",
      "description": "Soft acoustic guitar over gentle wind and bird ambience. Slow tempo, daytime mood, unhurried exploration. Pairs with lush green outdoor worlds and contemplative pacing.",
      "tags": ["forest", "outdoor", "calm", "peaceful", "daytime", "exploration"],
      "mood": ["peaceful", "warm"],
      "biomes": ["forest", "jungle", "garden", "meadow"],
      "tempo": "slow",
      "loop": true,
      "loopStartSec": 0,
      "credits": "Composer Name — License (e.g. CC-BY 4.0, royalty-free, original)"
    }
  ]
}
```

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Stable slug. Persisted in stage metadata; never rename in place. `lowercase_snake_case`. |
| `file` | yes | Filename relative to this folder. Prefer `.mp3` (universal browser support) or `.ogg`. |
| `title` | yes | Human-readable name shown in HUD / debug. |
| `description` | yes | Natural-language pitch — **the picker's primary matching signal**. One or two sentences covering instrumentation, tempo, mood, time of day, and what kind of world / pacing this fits. Write it like you're describing it to a music supervisor. |
| `tags` | yes | Discrete keywords for cheap overlap matching against the user's world prompt. Mix biome / mood / instrumentation / tempo terms. ~5–12 entries. |
| `mood` | yes | 1–3 mood adjectives (peaceful, uneasy, heroic, playful, oppressive, tense, dreamy, …). |
| `biomes` | yes | Biome words this pack pairs well with (forest, desert, snow, swamp, candy, urban, ruins, …). Open-ended. |
| `tempo` | yes | One of `slow` / `mid` / `fast`. |
| `loop` | no | Defaults to `true`. Set to `false` for one-shot stingers. |
| `loopStartSec` | no | Seek-back point in seconds for loops with a non-zero start (e.g. after an intro stinger embedded in the same file). Defaults to `0`. |
| `credits` | yes | Attribution. Required for any non-original track — name + license. |

## How the picker uses this

(Wiring still to come — this section describes intent.)

1. The world prompt (`"snowy mountain platformer with…"`) is normalised
   into a token bag.
2. Each pack's `tags + mood + biomes + tempo + description` is scored
   against the prompt. A simple weighted overlap is enough as a baseline;
   embedding-based scoring is a drop-in upgrade later.
3. The highest-scoring pack wins; ties break on `id` for determinism.
4. The chosen `id` is persisted alongside the world's other generated
   assets so the runtime always plays the same track for the same world.

## Adding a pack

1. Drop the audio file in this folder (e.g. `volcano_tense.mp3`).
2. Append a new entry to `index.json` with all required fields.
3. The picker reads `index.json` at startup — no rebuild step.

## Audio format guidance

- **Format**: `.mp3` (most compatible) or `.ogg`. Avoid `.wav` — too heavy.
- **Bitrate**: 128–192 kbps stereo is plenty for a game BGM.
- **Length**: 1–3 minutes per loop. Shorter loops sound repetitive; longer
  ones inflate download.
- **Loop seam**: trim so the end-of-file flows into the start without a
  click. Crossfade ~50 ms in your DAW if needed.
- **Loudness**: peak-normalise around –1 dBFS, target loudness around
  –16 LUFS so packs sit at similar volume without per-pack gain.

## Licensing

Every pack must have a credit string. Use original work, CC-BY,
CC0/public-domain, or a clearly-licensed royalty-free track. Track
licenses live in `credits`; longer licence text (CC-BY etc.) goes
alongside the audio file as `<id>.LICENSE.txt` if needed.

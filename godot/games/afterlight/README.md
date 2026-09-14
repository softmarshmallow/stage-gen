# Afterlight

An original visual novel about a courier, an impossible address and the people
who help him return. The game invokes the Godot-owned
[Scenario framework](../../packages/scenario_runtime/README.md) for its complete
episode. It owns its art, English/Korean text, voice policy, application UI,
resource bindings, camera geometry and scene navigation.

From the repository root, with its prepared local media installed:

```sh
godot --path godot/games/afterlight -- --language en
```

Click/tap, Space or Enter reveals or continues; the player chooses replies and
must confirm the authored fingertip contact. Pause, language selection and Lab
navigation remain game controls. Playback and voice inspection never generate or
refresh media. A source-only checkout needs the local files named by the art and
voice catalogs; missing content is reported by the owning loader.

## Narrative and bindings

| Owner | Responsibility |
| --- | --- |
| `narrative/episode.scenario` | Sole authored episode: stable IDs, dialogue, choice branches, gates, cues, effects and timing |
| `narrative/catalog.json` | Versioned named configurations of installed presentation capabilities |
| `narrative/program.json` | Compiled execution document |
| `authoring/program.map.json` | Compiler source locations for authoring and verification |
| `tools/compile_narrative.py` | Deterministic compilation and `--check` freshness |
| `story_beats.gd` | Read-only review/voice inventory projection of compiled content; no progression |
| `story.gd` | Game UI/input/audio and invocation of the shared Session/presentation APIs |
| `narrative_binding.gd` | Game geometry, root settings and resource/capability bindings |
| `cast_stage.gd`, `transmission_display.gd` | Thin game bindings/decorations over package cast and portrait-feed presenters |
| `root.gd`, `main.tscn`, `roots.gd` | Application composition, routes, installed art and language defaults |
| `text/`, `voice/`, `assets/` | Game-owned words, review, voice policy and art catalogs |

The package's `presentation/front_types.json` is the installed capability schema;
`front_stage.gd`, `front_cast.gd`, `portrait_feed.gd` and reading transport supply
reusable presentation behavior. The episode configures them through typed data.
There is no per-beat GDScript callback or alternate episode director.

With the optional game environment installed:

```sh
uv run --group games python godot/games/afterlight/tools/compile_narrative.py --check
uv run --group games python godot/games/afterlight/tools/compile_narrative.py
```

The episode retains 57 review beat identities. The compiled graph includes both
reply paths and an explicit end; review inventory is not an execution index.
Localized strings remain keyed independently of presentation and choice identity.

## Presentation and lifecycle

The episode includes intertitles, walking/establishing shots, waking-eye openings,
actor focus and handoffs, camera drift/pan, background blackout, raster Manpu,
contact feedback, portrait transmission, voice treatment, ambient particles,
refraction, corruption, halo and finite impact. These are authored choices over
installed mechanisms. The game binds actual resources and owns its fixed logical
canvas and native window layout; Scenario does not infer anatomy or create a world.

Contact geometry is game-owned. Text reveal, required contact completion and
feedback duration are declared sequence gates/cues. Audio reports its actual
completion; reading/autoplay cannot bypass mandatory input. Language changes
preserve sequence identity and use the selected text/voice policy. The
[voice guide](voice/README.md) and [manual preparation guide](tools/AFTERLIGHT_VOICE_PREPARATION.md)
define recording availability and explicit refresh; listening acceptance is separate.

Version-5 in-session checkpoints store the fingerprinted Session snapshot,
presentation command journal bound to operation identities/parameters/clocks,
audio and transport state. Restore reconstructs presentation silently before
resuming current playback. Old version-4 shell checkpoints are refused and
preserved with a visible Restart option; there is no silent migration or fallback.
These bounded checkpoints do not constitute a general durable save system.

The private [scene-navigation helper](../_shared/runtime/addons/scene_navigation/README.md)
owns replacement/input-detachment lifecycle. Afterlight owns route meanings,
checkpoint admission and restart. The independent
[Presentation Lab](../command_link/lab/README.md) keeps study sliders and galleries
outside the episode. Entering the Lab does not turn its study callbacks into
Scenario instructions.

## Art and checks

The local [Yuzu/Riko Movie Sprite Actor diagnostic](docs/movie-sprite-diagnostic.md)
in Afterlight Lab plays prepared transparent body loops with independently
controlled eyes and speaking mouth states through the independent
[Movie Sprite Actor package](../../packages/movie_sprite_actor/README.md).
Afterlight owns the diagnostic composition and preparation. It reuses existing art, subtitles and
recordings without changing the episode or promoting the generation pipeline:

```sh
godot --path godot/games/afterlight -- --game lab --route movie_sprite_study --language en
```

The [presentation history](docs/presentation-history.md) preserves detailed
artistic decisions and their scoped evidence. The
[paired story review](text/STORY_REVIEW.md), [asset catalog](assets/catalog.json)
and local art reviews retain their rights and review status. This refactor changes
execution ownership without requesting new artwork or recordings.

```sh
uv run --group games python godot/tools/check.py --owner afterlight
uv run --group games python godot/tools/check.py --owner afterlight --include-media
```

Media checks require existing art/recordings; external-content and native-rendered
suites have additional declared prerequisites. Read
[Godot verification](../../docs/verification.md) for complete commands and scope.
Source freshness, native behavior, rendered composition and listening are separate
verdicts; historical art approval is not a new visual verdict for changed code.

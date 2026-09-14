# Movie Sprite Actor diagnostic: Yuzu and Riko

The [canonical name and runtime boundary](../../../docs/movie-sprite-actor.md)
are **Movie Sprite Actor**. Existing `movie_sprite` paths and launch routes stay
stable for source/provenance continuity. The independent
[runtime package](../../../packages/movie_sprite_actor/README.md) owns playback
and compositing; this diagnostic does not import rig or deformation data.

Local integration introduced on 2026-09-14. This is a diagnostic of existing
prepared artwork, not a new episode, generation capability promotion, or public
media release. No AI calls are required or made by playback.

## Current ownership and decision

Afterlight is now a standalone game at `godot/games/afterlight`.
[Scenario](../../../packages/scenario_runtime/README.md) owns its authored episode
progression and front-stage presenters; [game_presentation](../../../packages/game_presentation/README.md)
is a lower mechanism dependency, and [content_io](../../../packages/content_io/README.md)
owns local file admission and decoding. The old presentation-playground paths and
historical optional-Scenario recommendations do not describe this checkout.

| Responsibility | Owner for this integration |
| --- | --- |
| Source motion, stabilized/keyed body and repaint patch generation | Existing local asset work; unchanged |
| FFV1 conversion, native patch registration, portable hashes and source evidence | Afterlight's offline [preparation tool](../tools/prepare_movie_sprite.py) and [prepared-content contract](movie-sprite-content.md) |
| Atlas paging, explicit body clock, eye/mouth RGB replacement, resource lifecycle | Independent [Movie Sprite Actor](../../../packages/movie_sprite_actor/addons/movie_sprite_actor/movie_sprite_actor.gd) |
| Blink/wink timing, speaking mouth cycle, positions, background, UI and existing line selection | [Lab composition](../lab/movie_sprite_study.gd) |
| Existing text, recording availability and playback | Afterlight text/voice policy and existing Text Reveal Audio component |
| Main episode and installed Scenario capability types | Unchanged by this diagnostic |

The package's version-1 contract admits a bounded sequence of full-canvas body frames
and independently selected eye/mouth replacements. This boundary is sufficient
for these two supplied assets. It is not a canonical anatomy, viseme, skeleton,
tracking or generation schema. A future shared actor-surface contract should be
reviewed against actual consumers before changing Scenario's texture-only cast
binding. There is no mutation of the shared cast presenter's private sprite nodes.

The **body loop**, **facial state selection**, and **facial direction** are separate
responsibilities. A face-state change does not restart the body. The host supplies
one transform for the entire source canvas, so patches cannot drift independently
when the actor is positioned or scaled. Source padding and actual face placement
are taken from these movie-derived canvases, not the old standing-PNG geometry.

## Run

From the repository root after preparing local content:

```sh
Godot --path godot/games/afterlight -- --game lab --route movie_sprite_study --language en
```

The same study appears as **Movie Sprite Actors · Yuzu / Riko** in Afterlight Lab's
effects menu. **Back to Lab** uses the existing navigation lifecycle. Entering
from the story preserves the story checkpoint; the diagnostic itself restarts
when entered again. `--language ko` selects existing Korean subtitle/audio data.
Diagnostic controls remain authored in English.

Use the independent eye and mouth selectors while the bodies continue looping.
**Pause** freezes body and facial clocks and current audio, with no elapsed-time
catch-up on resume. **Restart loops** stops the line and returns the body clocks
to zero. **Alpha check** replaces the existing reading-room background with a
checkerboard for edge inspection. Manually selected face states persist until
the corresponding selector is returned to automatic control.

**Yuzu · speak** and **Riko · speak** replay two existing approved story lines;
they neither advance the episode nor generate recordings. The existing voice
policy binds only usable recordings. Available voices show the complete subtitle
and drive a simple rest/A/O speaking cycle until playback finishes. Missing or
stale voices use the existing typewriter/typing fallback, with mouth cycling only
while text reveals. Stop, language switch, route exit and a replacement line stop
the old audio. Language switching leaves the body loops running.

This is a host-directed speaking animation, not forced alignment: it has no
phoneme timing, silence detection or complete viseme inventory. No new listening
acceptance is implied by reusing a recording.

## Source limits preserved

Both bodies are 720 × 1280, 192 frames at 16 FPS: a 12-second loop. Transparent
FFV1 caches are preparation inputs; Godot plays the resulting textures. Keying,
stabilization, slowdown and loop closure are already baked and are not repeated.
Yuzu uses the repaired final body and its video-derived canonical. Riko uses the
specific previously validated canonical/patch compatibility described in the
source handoff; that does not license arbitrary atlas reuse.

Yuzu has bilateral half/closed blinking. Riko has only a **canvas-left wink**;
that label is image-space, not an anatomical left-eye claim. `rest` uses the
current body's untouched RGB. Both have A/O mouth alternatives. Masks select
replacement RGB, preserving the current body's alpha; they are not translucent
stickers or another feathering pass. Native edge softness remains in the source.

The two actors use bounded atlas paging rather than retaining all 384 RGBA
frames. A page unavailable in time pauses its body clock visibly as buffering;
there is no skipped-frame catch-up. Playback failures are explicit and stop
speech. Route exit joins in-flight decoding and releases retained textures.

Media and source evidence stay local and ignored. Hashes, source files and their
existing provenance are preserved across the real game-content boundary.
See [CONTENT.md](../CONTENT.md) for the selected external-root convention.

## Verification record

The complete offline product gate passed all 14 steps (1,879 Python tests).
The game-owned preparation/export checks passed 25 tests; its unchanged episode
still matches the compiled Scenario program. Default and copied-content
headless game integration each passed 105 checks. Documentation and changed Python
format/lint checks passed. The copied-content run reads 240 inventory-verified
files from a separate local directory, including the movie provenance closure.
Four subsequent UI-signal assertions also passed (109 headless integration
checks), verifying that each eye/mouth selector controls the intended actor.
The wider Afterlight media run passed 23 outcomes and initially rejected one
synthetic player's successful output because its message lacked the coordinator's
required `PASS` marker. That marker was corrected and the focused coordinator
rerun passed. This was a check-reporting correction, not a gameplay failure.

The [native review record](../tests/movie-sprite/REVIEW.md) owns the final rendered
verdict and 42 captures from 259 native checks, including both window sizes, changing facial states while
the body moves, transparent edges, repeated live loops, bilingual speaking and
scene cleanup. Both actors completed two loops in 24.003 seconds with zero new
buffering holds during that interval. Offline checks alone are not a visual or
listening verdict.

Future promotion should review a drawable actor surface/lifecycle boundary for
Scenario's existing texture-only cast presenter, instead of reaching into its
private nodes. This local adapter does not establish that public API. Further
questions are platform-specific texture budgets, moving-head registration, and
whether a host wants timed mouth cycling, audio-energy response or phoneme
alignment. None requires modifying the existing repaint contract in this pass.

## Runtime extraction follow-up

The authorized extraction moved the player, shader and original UID sidecars to
`godot/packages/movie_sprite_actor`; Afterlight imports the installed addon.
The package owns the generic descriptor/API and synthetic checks. Afterlight
retains source preparation, content/provenance, UI, face direction and actual-game
integration checks. Existing prepared files remain valid and unchanged.

The final package suite passed 247 assertions. Afterlight passed 109 headless
checks against normal and copied external content, and 263 final native checks.
Seven actor/background capture regions are pixel-identical to the earlier
Compatibility render, with no new buffering during two measured live loops.
The [extraction review](../tests/movie-sprite/REVIEW.md#package-extraction-verification-2026-09-14)
records the sampled visual observations and their limits. A separate synthetic
consumer verifies that package use requires neither Afterlight nor Scenario.

## Request record

The user asked to first inspect the changed game/shared topology, then integrate
existing Yuzu/Riko bodies as indefinitely looping sprites with independent
game-controlled eyes and speaking mouth movement. Their supplied brief was:

> Bring the existing Yuzu and Riko movie_sprite assets into Afterlight as a local diagnostic game demo.
>
> Read: spikes/movie_sprite/GAME_ASSET_HANDOFF.md
>
> Use the final transparent body sources: 720×1280, 192 frames, 16 FPS, 12-second loops. Prepare game-owned runtime textures and metadata, preserving provenance. Display them over an existing game background.
>
> Keep facial controls independent of body playback: Yuzu supports bilateral blinking; Riko supports a canvas-left wink; both support rest/A/O mouth states. Use their video-derived canonicals and recorded patch placement.
>
> Verify looping, face registration, transparency, framing and scene lifecycle in Godot. Keep the existing repaint pipeline unchanged. This is diagnostic asset integration only; generation-module promotion remains deferred. No new AI generation is needed.

The follow-up framing requires reviewing and ratifying suitable contracts rather
than blindly copying the brief. This pass adopts the local version-1 prepared
content boundary and tests its consumer. A shared generation/runtime contract,
main-story replacement and new anatomy annotation remain separate future work.

The later **GO** authorizes the runtime extraction described above. Generation
work, main-story replacement and a Scenario actor-surface adapter remain outside
that extraction.

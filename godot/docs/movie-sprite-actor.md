# Movie Sprite Actor

**Canonical project term:** Movie Sprite Actor.
**Description:** Pre-rendered body motion with independently controlled facial states.
**Runtime package identifier:** `movie_sprite_actor`.

The shared prefix is deliberate: `movie_sprite` names the asset family and its
generation pipeline; **Movie Sprite Actor** names the runtime consumer of those
assets. “Layered raster actor” describes its implementation rather than naming
a competing system. A pipeline implementation and an engine runtime can share
this vocabulary while retaining separate ownership and dependencies.

Status, 2026-09-14: the representation and its bounded registered-face atlas
profile are implemented by an independent [Godot runtime package](../packages/movie_sprite_actor/README.md).
Afterlight consumes it, and a separate synthetic consumer exercises copied source
without Afterlight. This is a local canary SDK; no release or generation-module
promotion is implied.
This is our project vocabulary, not a claim of an industry standard.

## Purpose

Video models supply an already rendered body performance, and image models supply
compatible facial states. The game assembles these raster inputs into an actor
whose body can move continuously while the game independently directs blinking,
winking and speaking. This achieves the intended animated-character presentation
without manually authoring a deformable character rig.

The runtime consumes pixels, registration and timing metadata. It imports no
skeletal animation, deformation parameters, mesh rig or authored motion curves.
The frames are themselves animation content; “no animation-data import” here
means there is no separate rig/motion format driving their shape. In particular,
frame count, frame rate and loop policy are still necessary data.

“Faux Live2D” explains the original motivation informally. It is not the API name,
a compatibility claim or a required file format. The runtime contract also does
not require a particular AI model: supplied raster assets can implement the same
representation, regardless of how their producer made them.

## Representation and responsibilities

| Part | Meaning | Current Afterlight profile |
| --- | --- | --- |
| Body performance | A sequence of pre-rendered transparent frames with a declared canvas and timebase | An indefinitely looping 192-frame performance at 16 FPS |
| Facial baseline | The neutral face on which independent changes are applied | Baked into each body frame; the matching canonical image is retained for preparation and registration |
| Eye states | Independently selectable eye appearance | Yuzu has open/half/closed bilateral eyes; Riko has open/canvas-left wink |
| Mouth states | Independently selectable mouth appearance | Rest/A/O for each actor |
| Registration and compositing | Where each state belongs and how it modifies the base raster | One source canvas, fixed registered support, selected RGB replacement preserving body alpha |
| Runtime control | Body clock, facial selection, pause, seek, loading and cleanup | Explicit methods on a single drawable actor |
| Performance direction | When to blink, who speaks, which mouth state to choose | The game host; separate from frame playback and asset preparation |

A layer is a logical compositing responsibility. It need not be a separate node
or a separate draw call. The current profile has **no separately rendered
neutral face sprite**: `rest` reveals the neutral face already present in the
current body frame. The independent eye and mouth textures replace selected RGB
there. Calling the preparation canonical a live face layer would be inaccurate.

An explicitly replaceable whole-face base would be another representation
profile. It is not implemented today and is not necessary to use the current
body-plus-eyes-plus-mouth mechanism. The common contract must distinguish these
encodings rather than requiring an invisible or redundant face sprite.

## Core invariants

1. Body playback and facial selection are independent. Changing an eye or mouth
   state does not restart the body; a body-loop wrap does not reset the face.
2. The declared canvas, registration and actor transform apply to the complete
   composition. Moving/scaling the actor does not separately move a patch.
3. The prepared asset declares its actual states and compositing convention.
   `eyes_closed` does not by itself mean bilateral blinking; Riko's meaning is
   explicitly a canvas-left wink. Canvas-side labels are not anatomical sides.
4. `rest` means no replacement within that feature's channel. It does not seek
   the body or substitute an entire still portrait.
5. In the current profile, binary patch alpha selects prepared RGB; the current
   body alpha remains authoritative. Feathering is already baked into those RGB
   values. Adding another alpha blend or feather changes the representation.
6. A fixed facial patch requires valid registration throughout the body motion.
   Current preparation proves canonical equality on every selected pixel in all
   body frames and refuses overlapping eye/mouth support. A moving head requires
   another supported registration strategy; arbitrary motion is not silently
   admitted by this profile.
7. Playback reads prepared content. Replay, facial state changes and scene entry
   never invoke a video model, image model or regeneration tool.
8. The host owns advancement and pause policy. Decode buffering is explicit;
   the player holds rather than accumulating catch-up time. Removal releases
   decoding work and retained textures. Body completion does not advance a story.

A video and its decoded frame sequence can carry the same body performance.
Storage is an encoding choice, with decoder/alpha/timebase support defined by a
specific runtime profile. **The current Godot implementation plays PNG atlas
pages only.** Transparent FFV1 video is an offline preparation source, not a
second implemented runtime decoder. Existing endpoint, pixel and registration
checks establish this conversion for the supplied Yuzu/Riko sources.

The Afterlight assets use a 720×1280 canvas, 192 frames, 16 FPS and 4×2 atlas
packing. The package reads these values from the descriptor and supports other
validated dimensions, timing and packing, including partial final pages.
The same applies to the particular blink intervals and A/O cycle used by the Lab.

## Current implementation and names

The independent package owns the
[player and lifecycle](../packages/movie_sprite_actor/addons/movie_sprite_actor/movie_sprite_actor.gd),
[compositor](../packages/movie_sprite_actor/addons/movie_sprite_actor/compositor.gdshader),
and [public API and representation admission](../packages/movie_sprite_actor/addons/movie_sprite_actor/API.md).
Its only runtime dependency is `content_io`. Neither Scenario nor a named game is
imported. The payload retains the moved script/shader UIDs, license and declared
dependency; development links and copied installations use the same source.

The [Afterlight diagnostic](../games/afterlight/docs/movie-sprite-diagnostic.md)
keeps [host direction](../games/afterlight/lab/movie_sprite_study.gd) and its
[preparation profile](../games/afterlight/docs/movie-sprite-content.md) local.
Its prepared manifests and pixel/provenance files remain unchanged.

Existing `movie_sprite` paths, source manifests, launch routes and provenance
identities remain stable. `movie_sprite` continues to name the source-generation
work and existing diagnostic storage. **Movie Sprite Actor** names the resulting
actor representation and runtime responsibility. No historical asset is renamed
or has its provenance rewritten to adopt this term.

The public API comprises `configure`, `advance`, `seek`, `set_paused`,
`set_eye_state`, `set_mouth_state`, `snapshot`/`get_state`, and `shutdown`, plus
ready/failure signals. The host supplies the clock and decides blink/mouth timing.
Registration and mask semantics remain preparation preconditions; runtime checks
structure, resource bounds, exact decoded dimensions and bound source digests.
It does not claim semantic quality by accepting structurally valid content.

## Ownership and verification

| Owner | Boundary |
| --- | --- |
| `movie_sprite_actor` under Godot packages | Descriptor admission, body paging/clock, face-state compositing, drawable transform and resource lifecycle; declares only `content_io` |
| Generation and repaint capabilities | Produce compatible motion and facial raster inputs; retain their own contracts, provenance and review |
| Game preparation adapter | Convert accepted sources into a declared runtime encoding, validate registration and preserve lineage |
| Game host | Cast, art choices, blink cadence, speaking activity/mouth cycles, audio, UI, placement and story |
| Optional future Scenario binding | Invoke installed actor controls through declared capabilities; keep Scenario out of the actor package |

[Package checks](../packages/movie_sprite_actor/tests/run_checks.gd) exercise
synthetic dimensions/timebases, partial and single pages, declared face states,
content refusal, buffering and cleanup. The
[standalone assembler](../packages/movie_sprite_actor/tools/assemble_standalone.py)
copies the payload and declared dependency into an independent procedural example,
with UIDs, licenses and a hashed file inventory. It requires no Afterlight media
or generation environment at runtime. Its source copy is inspected by
[assembly tests](../packages/movie_sprite_actor/tests/python/test_standalone_assembly.py).
Afterlight retains its own native integration and visual review evidence.

The initial encoding intentionally supports fixed registered patches and PNG
atlases. A moving-head registration strategy, separately replaceable whole-face
base, runtime video decoder, phoneme alignment, anatomical annotation and Scenario
actor-surface integration require their own explicit decisions. None is implied
by packaging this player, and none requires a generation-format rewrite now.

## Request record

The user's clarification on 2026-09-14 defines the intent: a body supplied as
video or raster frames, with independently controlled facial sprites, generated
through video/image models instead of manual rig authoring. They requested an
explicit name and consideration of a dedicated SDK/package when the contract is
sufficiently complete. This note names that representation, distinguishes its
implemented profile from additional face-base/runtime-video encodings, and
records the bounded package extraction criteria. It does not promote generation.
The subsequent naming instruction asks to extend `movie_sprite` so the pipeline
and runtime visibly belong together. `movie_sprite_actor` adopts that prefix;
the earlier “Layered Raster Actor” suggestion is retained only as a description.

After reviewing why runtime code remained game-local, the user authorized
extraction with **GO**. The implementation moved into `movie_sprite_actor` with
its original UIDs; descriptor-driven bounds replaced Afterlight-specific canvas,
frame count, FPS, page packing and state-name assumptions. Afterlight now imports
the addon. Pure player checks moved with it, a separate synthetic consumer and
source-copy checks were added, and the Godot coordinator owns the new package's
checks. Art, preparation, UI, speaking direction and story remain game-owned.
This supersedes the earlier extraction proposal without promoting generation.

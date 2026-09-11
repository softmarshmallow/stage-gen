# Game roots and shared presentation

P107 implements the [successor design](../../../docs/research/game-presentation-sdk-design.md)
as one [installable addon](addons/game_presentation/README.md). This page describes
the current source tree; [packaging](PACKAGING.md) covers installation and external
content. [CURRENT_STATUS.md](CURRENT_STATUS.md) and [TERMINOLOGY.md](TERMINOLOGY.md)
track demonstrated behavior. Upstream generation contracts remain separate.

SDK behavior has no dependency on a whole game. The concrete stage, opening,
UI theme and graph widget remain example code under `presentation/`; game roots
own story, content adapters and all interface choices. A new host starts from
`starter_source/` or preloads only the addon components it needs. No mandatory
facade, common UI hierarchy or universal effect superclass is introduced.

## Composition in Godot

`main_games.gd` explicitly names three small Godot roots. Command Link remains
the default. There is no game DSL, universal schema, or dependency container.

```text
main.gd + main_games.gd
    games/command_link/root.gd       -> tactical story/menu/profile
    games/bishoujo_afterlight/root.gd -> ensemble episode/cast/art/text/UI
    games/presentation_lab/root.gd   -> two prepared study collections
                    |
      addons/game_presentation/
                    |
             Godot primitives

Each root -> its own UI/stage + explicit local content loader
Starter   -> its own main.gd + the same addon (no example assets)
```

P67 replaces Afterlight's selected-guest scene with a linear ensemble adventure;
P68 clarifies bishōjo rather than dating simulation. Its root binds prepared
content and `story_beats.gd`; the independent `story.gd` Control owns the episode
and complete interface. Its concrete `cast_stage.gd` composes existing actor
controllers. It does not inherit either a study host or Command Link's mission.
P71 adds one reconverging choice and game-owned gradient chrome/advance cues.
Choice IDs and delayed manpu timings are episode checkpoint data; the shared
presentation controllers keep their existing contracts.
`dating_sim` remains a launch compatibility alias only.

P90 adds a bounded placement API to Afterlight's concrete cast adapter. Actor
Blocking is the direction umbrella; Quick Approach resolves a destination from
a visible actor pair and stopping distance, then reuses Motion Curve. It needs
no separate shared controller or Lab route. The root owns default duration/gap/
curve settings, the story owns identities and timing, and the existing Actor
Motion study owns tuning controls. Positions hold after completion; the host
explicitly restages before an incompatible fixed-slot handoff. See
[the local contract](games/bishoujo_afterlight/ACTOR_BLOCKING.md).

P91 separates layer framing from local blocking and world-camera framing. The
small Layer Pan sampler consumes an offset and existing Motion Curve settings;
it knows no cast, background or viewport. Afterlight's `_cast_transform()`
composes its offset with the world camera for actors, attached manpu and
cast-associated effects. Scenery and environmental fields keep their world
transform. Target resolution, held framing and composition-reset policy belong
to the host. [Cast Pan cues](games/bishoujo_afterlight/CAST_PAN.md) are ordinary
dictionary data, without a new game DSL or layer registry.

Presentation Lab owns all focused routes. The earlier Afterlight host and study
implementations moved under `games/presentation_lab/afterlight/`; tactical
workbenches remain under `demos/`, selected solely by the lab root. The lab
uses separate prepared fixture instances. Shared mechanisms import no game.
A demo composition may import a game's prepared content without reading or
changing its live state. The old study launch routes redirect into the lab.

Each root chooses its routes and prepares nodes before they enter the tree.
The shell supports explicit `game:<id>` or `game:<id>/<route>` navigation and
retains separate root instances and in-session story checkpoints per game.
Afterlight replays elapsed authored cues to resume controllers, with separate
text reveal progress so skipping text never advances world time. It rejects
incompatible episode checkpoints. This is not a durable cross-version save
contract. Command Link keeps its existing save format.

Afterlight's English/Korean Text Set remains instance-local. Language changes
preserve the beat, actor identities, effect clocks, and normalized reveal
progress. The lab fixture owns a separate language selection; Command Link
retains its current English text. Each host owns fonts and language UI.

## Directory responsibilities

| Location | Responsibility |
| --- | --- |
| `main.gd`, `main_games.gd` | Application routing and explicit game selection. |
| `games/command_link/` | Command Link composition, story, menu, and prepared content bindings. |
| `games/bishoujo_afterlight/` | Master composition, episode and reconverging choice cues, optional autoplay policy/time, concrete cast adapter, complete host UI, paired text, and independently replaceable assets. |
| `games/bishoujo_afterlight/voice/` | Afterlight speaker/line policy, optional speech scripts, selected provider casting, prepared-recording manifest, source revisions, runtime lookup and provider-free export/status. |
| `games/presentation_lab/` | Dedicated lab root/menu and moved Afterlight study interfaces. No live game state. |
| `presentation/stage.gd`, `stage_profile.gd` | Concrete integrated presenter and its supplied cast/art/landmarks; includes current tactical UI and workbench policy. |
| `presentation/animation/` | Existing track and motion-curve sampling, plus explicit-time Layer Pan offsets. |
| `presentation/focus/`, `manpu/`, `transitions/` | Actor focus, attached reactions, exits, cast handoffs, and first-person eye transitions. |
| `presentation/camera/` | Dialogue Camera, Establishing Shot, Walking Approach, Camera Drift, and Impact Shake controllers. |
| `presentation/narrative/` | Independent Intertitle reveal/continue state and optional Text Reveal Audio playback; neither owns text meaning, layout, or game flow. |
| `presentation/interaction/` | Point Contact's circular hit test and acknowledged state; hosts own input routing, presented geometry, readiness and feedback. |
| `presentation/text/` | Instance-local Text Set lookup, fallback, and validation. No shared language UI or global locale. |
| `presentation/effects/` | Actor Halo, Refraction Field, Ominous Corruption, and Radial Sprite Burst presenters over supplied textures, geometry, or screen content. |
| `presentation/shaders/` | Concrete actor and screen-effect shader implementations. |
| `presentation/ui/` | Existing tactical styling utility; no shared game-UI contract. |
| `presentation/opening.gd` | Current concrete title route combining video playback and tactical continuation UI; the root supplies its video and label. |
| `demos/` | Workbenches using an explicit Command Link fixture; never a second story runtime. |
| `qa/` | Regression scripts and the extracted legacy presentation checks/capture scenarios. |
| `assets/` | Current prepared asset bindings and locally retained media. |
| `tools/prepare_afterlight_voice.py` | Explicitly invoked local preparation only; uses the existing speech service with pass accounting, never a runtime dependency. |

These are source components in one Godot project. A folder does not declare a
separately packaged module. Shared presentation imports no game root or story.
Game roots and demos may depend on presentation. QA may inspect either.

P88's [Radial Sprite Burst](presentation/effects/SPRITE_BURST.md) owns small,
finite sprite batches with explicit emission origins, seeded motion and a host
clock. Each emission captures its texture pool and settings. The host places
the layer behind or above actors and supplies the final world-to-parent camera.
Afterlight emits at a fixed authored time during Sena's repair line and clears
on the next beat; checkpoint replay reconstructs that event from elapsed time.
No actor or story name enters the shared effect. The Lab uses independent rear
and front instances to compare texture pools, layering, overlap and camera motion.
This finite burst remains separate from P99's sustained Sprite Particle Emitter;
neither introduces a universal emitter graph.

### Ambient and transmission ownership (P99)

`presentation/effects/ambient_particles.gd` is the reusable Sprite Particle
Emitter: supplied rectangle/textures/settings, an explicit deterministic clock,
world transform, stop/drain/clear, and seek/checkpoint reconstruction. It has no
scene/cast dependencies. Its optional raster fallbacks are replaceable inputs.
`games/bishoujo_afterlight/atmosphere_profile.gd` owns quiet/relay/infernal presets;
`root.gd` maps backgrounds to them. The story keeps continuous atmosphere across
ordinary lines, resets at environment changes, pauses it during monologues,
and reconstructs its time from existing history. Particles draw after background
fields but before scenery blackout and actors; their transform is the world
camera with shake/zoom, without Cast Pan. [Contract](presentation/effects/SPRITE_PARTICLE_EMITTER.md).

`presentation/audio/voice_effects.gd` owns an isolated playback bus and its DSP.
Text Reveal Audio accepts an optional `voice_bus` separate from its existing
`bus`, keeping typing dry. Afterlight's root selects Transmission Voice and
strength, and marks the projected cast profile. The story resolves the actual
voiced speaker and projection state, stops old speech, resets filter history,
and chooses processing or bypass. Audio has no dependency on hologram shaders,
TTS, voice policy or story; the host coordinates these. [Contract](presentation/audio/VOICE_PROCESSING.md).

Two new independent Lab studies consume these mechanisms and prepared fixtures.
Only the real Afterlight story receives its game-owned voice-policy object;
Lab fixtures receive localized content and existing stream bindings. Their UI,
state and audio buses belong to the Lab instance, never the running story.

### Localized voice ownership (P95/P96)

Afterlight's `voice/voices.json` owns speaker defaults, per-line overrides and
sparse speech scripts. `voice/cast.json` selects existing provider voices by
speaker and language. `voice/voice_policy.gd` resolves actual speaker and stable
text ID against a prepared `manifest.json`, validates current source revision,
and binds only ready streams. A portrait's actor does not necessarily identify
the speaking voice: `a_hand_to_hold` is courier narration; `nami_beyond_the_wall`
is Nami speaking while no actor is visible. Alternative replies have their own
stable IDs. These are concrete Afterlight content decisions.

The story chooses complete subtitles for ready voiced lines, preserves the
typewriter for `none` or unavailable recordings, and decides when a cinematic
caption becomes audible. Text Reveal Audio receives an `AudioStream` and keeps
its existing playback contract; it knows no provider, cast, source file, or
voice-policy schema. Pause, language switching, continuation and checkpoint
decisions remain with the host. No shared component performs generation or
promotes Afterlight's policy into a universal voice catalog.

Preparation reads an explicitly exported inventory outside Godot gameplay. The
small [manual command](tools/AFTERLIGHT_VOICE_PREPARATION.md) reuses the existing
speech service, original MP3/provenance, and durable per-pass accounting.
`none` skips provider work; stale/missing/failed recordings await a later
requested refresh. There are no file watchers, automatic synchronization,
provider calls on replay, or game-framework changes. See the
[host voice contract](games/bishoujo_afterlight/voice/README.md).

### Autoplay ownership (P97)

Afterlight's root supplies `CONTENT.autoplay` timing and initial state; its beat
data supplies `autoplay.default_choice` and `autoplay.require_input`. The story
owns the top toggle, delay clock, default-choice countdown, progression and
checkpoint state. It observes the existing reveal, cinematic and voice
completion states before counting. Intertitle and Text Reveal Audio retain
their independent contracts and never choose options or advance the game.

The delay uses unpaused host time, including monologues whose world clock is
held. It cannot synthesize a contact hit or cross a mandatory-input gate.
Manual advance resets it, pause freezes it, a changed language restarts it,
and eligible Lab checkpoint restoration retains it. The ending disables
autoplay without restarting the episode. This is a local gameplay policy;
Command Link and Presentation Lab retain their own controls. See the
[autoplay contract](games/bishoujo_afterlight/AUTOPLAY.md).


## Component contracts

Independence is scoped to these Godot scene-presentation behaviors. A component
can depend on another named component; it must not depend on a game's story or
cast. The current project-relative script paths are local dependencies, not
separately installable packages. The stage is one consumer and integrator of
these components, not their mandatory base class.

| Component | Inputs and outputs | Declared dependencies and limits |
| --- | --- | --- |
| [Presentation Animation](presentation/animation/README.md) | Validated tracks and explicit time produce scalar channel samples. | Godot values; no target state, nodes, or clock ownership. Motion Curve similarly samples translation progress. |
| [Layer Pan](presentation/animation/LAYER_PAN.md) | Offset, curve settings and explicit elapsed time produce a held translation transform. | Motion Curve and Godot vectors/matrices; no layer registry, actor identity, viewport or asset assumptions. Host selects membership, focus anchor and composition. |
| [Actor Focus](presentation/focus/README.md) | Actor IDs, catalog, and focus cues produce per-actor motion/color samples. | Presentation Animation and a supplied local catalog; owns focus state, not speaker selection or rendering. |
| [Manpu animation](presentation/manpu/README.md) | Persistent actor/mark cues produce introduction or loop samples with frame IDs; explicit one-shot instances expire. A host may substitute a pure animation sampler. | Presentation Animation and a supplied catalog; the host owns textures, attachment coordinates, render nodes, and time. |
| [Character Exit](presentation/transitions/README.md) | Actor IDs, catalog, and exit/show calls produce local X/Y offsets, brightness, opacity, and visibility. | Presentation Animation and a supplied local catalog; the presenter applies values to the source silhouette. |
| [Cast Transition](presentation/transitions/CAST_TRANSITIONS.md) | Ordered actor IDs and a specification produce occupancy, position, and departure/arrival samples. | Character Exit, Presentation Animation, and Motion Curve; exactly three actors, two positions, explicit sequence patterns. |
| [Dialogue Camera](presentation/camera/DIALOGUE_CAMERA.md) | Background bounds and directed focus/wide calls produce zoom and offset. | Godot geometry; bounded coverage and maximum zoom. The stage resolves actor landmarks and decides when this camera is permitted. |
| [Walking Approach](presentation/camera/WALKING_APPROACH.md) | Background bounds and shot settings produce a push-in with vertical bob, settling to a held pose. | Godot geometry; explicit clock, constrained coverage, replay/skip/reset and validated in-memory restore. No asset, actor, route, or UI dependency. |
| [Camera Drift](presentation/camera/CAMERA_DRIFT.md) | Amplitudes, periods, phase, and explicit elapsed time produce a bounded 2D offset. | Godot values; independent state and restore. Geometry helpers constrain a supplied covered background. The host binds the same final offset to its world elements. |
| [Impact Shake](presentation/camera/IMPACT_SHAKE.md) | Finite X/Y displacement with attack/decay and a supplied base transform produces a covered final world transform. | Godot geometry; explicit host clock, finite replayable state, positive axis-aligned base framing, no camera node or story dependency. |
| [Intertitle](presentation/narrative/INTERTITLE.md) | Text, reveal rate, elapsed time, and advance input produce visible-character count and reveal/hold/completion state. | Godot string/value types; no Label, black panel, narrative role, audio, or next-scene dependency. First advance reveals; the next completes once. |
| [Sprite Particle Emitter](presentation/effects/SPRITE_PARTICLE_EMITTER.md) | Host advances seeded sustained emission or restores explicit time; stop drains, clear interrupts. | Godot Control and supplied raster textures; host owns world transform, depth and semantic profiles. |
| [Voice Processing](presentation/audio/VOICE_PROCESSING.md) | Runtime filter strength/bypass, history reset and private bus cleanup. | Godot audio bus/effects; host routes selected voices and coordinates visual state. No generation, story or character dependencies. |
| [Text Reveal Audio](presentation/narrative/TEXT_REVEAL_AUDIO.md) | Visible codepoint count and host time pace typing sounds; supplied voice, pause, interruption, and silent synchronization have explicit calls. | Godot Node/AudioStreamPlayer; no cast, game, UI, or text-clock ownership. Host selects policy, streams, language, and checkpoint position. |
| [Text Set](presentation/text/TEXT_SET.md) | Supplied language dictionaries and stable keys produce translated strings with named values and fallback. | Godot values; no loader, font, UI, story, or global locale. Host chooses language and refresh policy. |
| [Actor Halo](presentation/effects/ACTOR_HALO.md) | Texture, original displayed rectangle, color, radius, intensity, and strength produce an outer glow behind the sprite. | Godot TextureRect and canvas shader; own material, full-source alpha, padded bounds, no clock. The host owns layering, clipping, and lifetime. |
| [Radial Sprite Burst](presentation/effects/SPRITE_BURST.md) | Origin, texture pool and seeded options produce finite outward-moving, rotating and fading sprite groups. | Godot Control; explicit host clock and world camera, independent overlapping events, no actor or asset identity. Host owns placement and cancellation across scenes. |
| [Background Blackout](presentation/transitions/BACKGROUND_BLACKOUT.md) | Target opacity, fade duration and explicit time produce a held black scenery cover, with continuous reversal. | Godot ColorRect and Presentation Animation opacity sampling. Host places it above scenery and below actors/UI; it changes no actor or camera state. |
| [Screen fields](presentation/effects/SCREEN_FIELDS.md) | Refraction Field supplies barrier/heat modes; Ominous Corruption uses source alpha, an area, or the screen. Both consume geometry, strength, explicit time, and optional reusable textures. | Godot Control, canvas shader, and an explicit BackBufferCopy per pass; source colors remain unchanged. Host owns draw order and target projection. No effect graph or general particle emitter. |
| [Eye Transition](presentation/transitions/EYE_TRANSITIONS.md) | Opening, closing, blink, or waking-opening cues produce eyelid openness and closure history; an independent shader draws rounded black coverage. | Explicit host clock and screen-space layer; validated timing/peek settings and in-memory restore. Host decides when to change the revealed scene and which UI remains visible. |
| [Establishing Shot](presentation/camera/README.md) | Location ID and shot settings produce timed pan, zoom, and flare values. | Godot values; the presenter owns image binding, final coverage, UI visibility, and light projection. |
| [Character effects](CHARACTER_EFFECTS.md) and lens flare | Texture/material parameters produce actor-local treatment or a projected screen overlay. | Godot canvas shaders; placement, parameter updates, and lifetime belong to the presenter. No arbitrary shader stack exists. |
| [Tactical styling utility](presentation/ui/README.md) | Style helpers and drawing values for controls and panels. | Concrete Godot styling used by the current routes. It owns no screen composition or story; it is not an agnostic skin contract. |

The controller APIs above define their own validation and lifecycle semantics;
there is no invented common interface over unlike behaviors. Controllers are
advanced explicitly by their owner. Sampling does not advance their clocks.
The stage owns its controller instances; Command Link separately owns its cast
handoff. A caller must not advance the same controller twice.

Interruption also remains explicit: focus retargets or clears, manpu cues sync
or clear, exits can show an actor again, cast handoffs reset, and shots can be
replaced, skipped, or cleared through their documented APIs. State snapshots
are not all restorable: camera, eye-transition, and intertitle controllers expose restore;
Command Link reconstructs its particular cast handoff from elapsed time. A new
consumer must choose its own pause/resume policy rather than assume a universal
save protocol.

## Root and presenter integration contracts

These are local GDScript conventions exercised by
[composition checks](qa/composition_checks.gd), not a persisted game schema.

| Boundary | Current obligation |
| --- | --- |
| Root registration | `main_games.gd` maps a game ID to a fresh root object. Shared components never look up a root. |
| Root methods | `id()`, `title()`, `entry_route()`, `scene_path(route_id)`, `validate_options(options)`, and `prepare_scene(scene, route_id, options, saved_state)`. Unsupported routes return an empty path; option validation returns error strings. |
| Route scene | A `Control` with `navigate(route_id: String)`. The `game` route also provides `save_game() -> Dictionary`; the shell stores that game's in-memory state when leaving it. |
| Preparation | The shell instantiates the scene, calls the root's `prepare_scene`, connects navigation, then adds it to the tree. A stage must receive a fresh valid `stage_profile` before `_ready`. |
| Stage profile | [The profile type](presentation/stage_profile.gd) supplies actor IDs, asset bindings, landmarks, optional pose roles, catalogs, and sample dialogue. It does not select story progression or infer content from a game name. |
| Concrete stage | Loads prepared media, creates per-instance controllers/materials, applies coordinate transforms, and provides the current workbench. Game and demo adapters choose their interface and scene policy through overrides and existing APIs. |
| Game direction | Chooses scenes, speakers, choices, timing, input gates, effect cues, and resume policy. It may coordinate several components; that coordination is legitimate game code. |

`root.gd` is the discoverable master composition for each game. It may contain
direction directly or delegate to supporting scripts and assets. There is no
size limit or requirement to hide useful wiring behind a framework. A game can
reuse the concrete stage where its behavior fits, or compose the smaller
controllers with its own UI. Reuse optional utilities or independently useful
mechanisms when they fit; the host retains ownership of the complete interface.

## Point Contact and host interaction (P94)

[Point Contact](presentation/interaction/README.md) extracts the existing
circle hit test and acknowledged state from the tactical presenter. It accepts
the current point, target center and radius in one coordinate space, emits a
confirmation signal on the first hit, and supports silent acknowledgement
reset for host checkpoints. It keeps no image, geometry cache, clock or UI.

Command Link's `_connected` property delegates to that state while preserving
its existing input/entry gates, reaction rings and mission progression.
Afterlight's P94 integration supplies its own Nami pose, normalized fingertip
binding and a dedicated `a_touch_that_stays` beat after `a_hand_to_hold`, before
`only_a_second`. Its story owns readiness, acknowledgement feedback and the
next-line gate. The new pose is bound to a reviewed source; the hosts retain
independent confirmation, pause and checkpoint state.
No shared dialogue view, target registry or new Lab route is introduced.

## UI ownership, P45

The host/route owns controls, hierarchy, layout, styling/assets, and action
wiring. Each game configures those manually in its own Godot script or scene.
It need not implement a common dialogue view, shared game-UI schema, or skin
slot. A master composition may delegate to host-owned UI files for readability.

Shared utilities can help construct styles or draw geometry; a reusable control
or behavior needs its own independent purpose and contract. Repeated layout or
similar-looking dialogue panels alone do not require a shared component.
Asset-backed UI follows the same ownership rule: the host chooses its artwork
and layout and binds the interaction.

Currently `stage.gd` still installs tactical styling and creates header/panel
decoration and workbench controls. The [opening route](assets/opening/README.md)
combines video fitting/loop fades with a tactical continuation button and route
navigation. Those are remaining implementation constraints for that presenter.
Command Link's game and menu own their controls and layout. P47's Afterlight
host owns its complete UI and never loads that stage or tactical styling. Its
working scene demonstrates the P45 ownership decision without introducing a
shared whole-UI abstraction or rewriting the existing tactical interface.

## Camera and screen ownership

| Element | Coordinate and effect ownership |
| --- | --- |
| Background | World framing; camera motion must preserve background coverage. |
| Character | Authored placement, then actor-local focus/transition, then optional cast-layer framing and world camera. |
| Manpu | Actor-relative anchor and its own animation, then the same cast-layer framing and world camera. |
| Actor material shader | Hologram shades that actor's own texture; it does not filter scenery or dialogue. |
| Actor Halo | Behind the unchanged character; same full source rectangle and final camera offset, with extra glow padding. |
| Refraction and corruption | Screen-reading passes affect already-drawn content within supplied coverage. Actor masks follow projected geometry; full-screen fields stay in screen space. The host puts UI after these passes. |
| Impact Shake | Composes once with the unshaken world transform and adds temporary overscan; screen-space UI stays fixed. |
| Lens flare | Screen-space effect whose light anchor is projected from the background. |
| Eye transition mask | Screen-space world coverage, unaffected by world-camera movement. Afterlight places it above scenery/actors and below navigation; story dialogue hides during the eye opening. |
| Dialogue, controls, location title | Fixed logical screen space; window scaling still applies. |
| Intertitle text and black backing | Screen space, with layer, input, and world-pause policy owned by the host. Afterlight hides all other UI during its monologues. |

The renderers currently compose transforms through rectangles rather than a
single Camera2D node. The tactical stage also draws some screen chrome alongside scenery and
combines dialogue backing with manpu in a foreground canvas. Those draw items
have different coordinate ownership: putting their whole parent under a future
camera would move the interface twice or transform elements that should stay
fixed.

For future camera motion, start each sample from its authored/base shot,
compose local offsets, and constrain the final framing to available background
coverage. Do not accumulate the previous frame's transform. The existing
Dialogue Camera policy applies to dialogue. Walking Approach has its own
explicit cue and lifecycle, rendered by Afterlight. No general camera-effect
stack or automatic speaker-follow policy is introduced.

## Status of the original five requests

| Hint | Working term and owner | Status |
| --- | --- | --- |
| TTS voiceover | Dialogue voice playback; the game supplies line/voice choices, with synthesis outside the renderer. | P73 implements supplied-voice playback and fallback. P95/P96 add Afterlight's English/Korean recording policy and manual preparation, with intentionally unvoiced protagonist lines and source freshness tracking. |
| Approach with vertical motion and zoom | Walking Approach: camera bob with a push-in over a background-only shot. | Implemented in P47 with four settings, coverage constraints, final hold, skip/replay/reset, and paused scene resume. Afterlight owns the route and UI. |
| Gentle motion around an obscured close-up | Camera Drift; P63 chooses a chin-to-chest Portrait Detail Shot with the face outside the frame. | Implemented in the story and separate study. Actor Halo is separately composed with the story shot. P66 binds Nami's approved dedicated art; other guests retain portrait crops. |
| Floating dust, glare, or sparkles | Ambient particles in a scene or foreground layer, distinct from lens flare. | P99 implements sustained Sprite Particle Emitter with host-owned textures, atmosphere profiles and world-space layer choice; quiet interiors and the infernal hall demonstrate it. |
| Centered typewritten text on black | Intertitle, authored as a scene beat in screen space. | Implemented with five player monologues, explicit reveal/continue input, paused world state, resume, and a separate study. |

A mechanism can be shared while the timing, composition, dialogue, characters,
and emotional direction remain game-specific. Text Reveal Audio has a concrete
Afterlight consumer; P95 adds localized character recordings to that integration.
P99 completes general Ambient Particles with a separate sustained emitter.
The motes inside Ominous Corruption remain local to that shader treatment.

Afterlight's root binds the original ensemble episode and prepared art. The
story gives each presentation cue a narrative reason: a warning seal flashes,
a letter is held into window light, Nami leaves to operate a bypass, Sena
arrives with tools, and Eira appears in a dedicated relay transmission while
Riko remains physical. Continuation follows the host's manual/autoplay policy;
mandatory contact still requires player input. No affection system,
character-selection route, or branching romance belongs to this episode.
The lab keeps independent controls for alternatives and experimentation.

## Present limits

The stage still uses the tactical skin and existing fixed 1280 by 900 layout.
Cast centering follows the supplied actor count, but spacing and sprite height
remain authored values; this is not an arbitrary-count responsive layout.
The existing handoff demo still illustrates three actors and two positions.
Sample dialogue still accepts display-name speakers; direct actor operations
use stable actor IDs. The supported controller lifecycles remain their current
explicit APIs rather than a newly unified scheduler.

The tactical stage still provides a basic inspection interface and small QA input
helpers. Fixture validation and capture routines
live separately in `qa/legacy_presentation.gd`. Further extraction should
follow actual new requirements, not be a prerequisite for extending either game.

Git continues to track source/configuration/docs while generated media and
working output stay local. This organization is entirely inside the experiment;
upstream production review and promotion remain separate work.

## Run and check

From the repository root:

```sh
Godot --path godot/games/playground -- --game command_link
Godot --path godot/games/playground -- --game bishoujo_afterlight
Godot --path godot/games/playground -- --game presentation_lab --route approach_study
Godot --path godot/games/playground -- --game presentation_lab --route eye_study
Godot --path godot/games/playground -- --game presentation_lab --route effects_menu
Godot --path godot/games/playground -- --route demos/dialogue_camera
Godot --path godot/games/playground --script res://qa/composition_checks.gd
```

Presentation Lab owns both study collections. Existing `demos/*` launch links
redirect to that root and use its explicit Command Link fixture.

## Walk-Away and Restless Bounce (P69)

These are new presets over the existing sampler and target controllers. The
sampler adds neutral-default `offset_x_ratio`; both X and Y ratios use original
target height. Character Exit now accepts movement tracks alongside color and
opacity, while Actor Focus supplies the Y-only expressive cue. Cast Transition
selects an exit preset and avoids adding its own departure X travel when the
selected preset already owns that motion. The concrete renderers compose
local offsets once before camera projection, with proportional manpu.

Afterlight owns which lines use these choices; the lab owns replay/selection
controls. A walking sprite does not infer a path or automatically track the
screen edge. Current authored distances are verified for the wide examples.
Restless Bounce is finite and does not exit or infer an emotion from text.

## One-shot manpu (P70)

The existing manpu controller now owns two distinct lifecycles: reconciled
persistent `(actor, id)` cues and explicitly emitted transient instances.
An event snapshots its preset, owns an independent clock/handle, and expires
without relying on dialogue advancement. Persistent sync/configure/replay does
not recreate or retune events. The controller knows no texture, character class,
position, camera, or rendering node; hosts resolve target/art identifiers.

Afterlight's cast adapter composes local scalar samples with its mouth anchor
and camera, and removes expired TextureRects. The tactical presenter draws
the same samples through its existing immediate overlay. The lab additionally
adapts one shared controller instance to Sprite3D billboards; switching its 2D
and 3D preview does not restart clocks. Billboard units, depth/orientation,
attachment policy, and node ownership remain concrete host concerns. This
proves a bounded 3D consumer, without introducing a generic particle system,
3D gameplay root, or permanent-save contract.


P93's Sweat Drop Fall is another preset in this same one-shot lifecycle.
The preset contains only scalar tracks; the host binds `sweat_drop` artwork
at the existing brow anchor. It emits downward motion/fade through the same
controller and renderers as Sigh Puff. Story timing and the Lab's one-shot
variant selector remain host decisions.

## Looping Manpu and sampler boundary (P92)

Persistent cues can pin a preset and supply ordered frame IDs. Manpu owns their
clocks and repetition; Presentation Animation samples smooth or held scalar
tracks. Rotation is applied around the attached mark center. Textures, actor
anchors, draw nodes and final camera/group transforms remain in each renderer.
The tactical canvas, Afterlight TextureRects, and Lab Sprite3D preview resolve
the same sampled sprite ID. Supplying frame art never changes the controller.

The optional `sample_with(actor, id, sampler)` callback receives a copied
sampling context and returns bounded channel/frame overrides. The host chooses
whether to call it; Manpu stores no callback, graph, game node, or UI dependency.
It preserves one clock/lifecycle owner and allows a different animation method
without embedding it in Manpu. This is a local code interface, not a serialized
animation-graph contract.

Afterlight authors `mark_preset` alongside its existing `mark`. Its story owns
which reactions loop and reconstructs their clocks through the existing episode
checkpoint replay. Presentation Lab expands its existing Manpu study rather
than adding another route. Two/three-frame examples deliberately use existing
different marks; no dedicated frame artwork has been generated.

## P74: bounded screen fields and camera impact

Afterlight's 56-beat *The Address Beyond* introduces all four heroines and
completes the ward repair before the otherworld excursion. P75 places
`the_seal_answers` after `the_reroute`, followed by the twelve excursion/return
beats. The Keeper has a dedicated `keeper` actor identity and a new independently
reviewed sprite, added under P75 without replacing heroine art. P76's pretty
face and evil-smile direction are reflected in that image. Story text, cast
bindings, speaker/place labels,
strength cues, and the temporary realm remain owned by this game.

Two independent screen-reading presenters live in `presentation/effects/`:
[Refraction Field](presentation/effects/SCREEN_FIELDS.md) with barrier/heat modes,
and Ominous Corruption with alpha, area, and screen coverage. A shared shader
include supplies procedural noise. Each presenter copies the content below it
before sampling; the host places the passes among its world nodes and before
its UI. Screen fields consume time and displayed rectangles, not actor names
or story states. The alpha adapter reads `get_presented_actor_rect()` to follow
focus and camera geometry. These are 2D canvas integrations, not a renderer-
independent material or universal effect graph.

[Impact Shake](presentation/camera/IMPACT_SHAKE.md) is a separate camera modifier.
It composes from the unshaken camera and adds bounded overscan to preserve final
background coverage. Afterlight advances it and the shader clock with world
time, freezes them during monologues/menu pause, and reconstructs them from
checkpoint history. Entering the normal-house return clears all field strengths.
Presentation Lab owns the independent tuning fixture and optional shared-noise
comparison; ordinary play retains only the story.

P85 strengthens the Keeper encounter through this game's profiles and authored
beat strengths. P86 adds an optional pattern transform to Ominous Corruption:
Afterlight supplies its final world camera, including shake and zoom, so the
procedural mist and ember flecks move with the scene. Source masks and aura
coverage still follow their displayed rectangles; the vignette stays in
screen space. Other consumers retain source-local patterns by default. This
bounded shader extension does not introduce a general particle emitter.

P87 authors Waking Eye-Opening at both realm changes. The story's
`eye_portrait: false` cue reveals the empty hall through the existing eye mask;
the return cue reveals Nami's prepared close portrait. The shared transition
controller owns timing and openness without knowing which scene is revealed.


## P77: story-led environments

Story and scene intent determine the setting; existing background art does not
constrain the narrative. Assets may be prepared later, and an ordinary story
edit does not require generation. The Hall of Unclaimed Names is a third indoor
background dedicated to the Keeper encounter. P78 sets a darker infernal mood
with obsidian, black iron, and furnace light. The independently reviewed image
is appended as background index 2, preserving both original locations. The host reveals it after `between_addresses`, then restores the
reading room for the return. Location bindings remain game-owned; no shared
effect assumes a particular background. This new asset binding changes neither
the shared controllers nor the generation pipeline.

## P81/P82: dedicated transmission scene

Afterlight adds Eira under its supporting cast and binds a fourth background,
a scientific Relay Laboratory. Six authored turns form a private conversation
with the courier. Her portrait sits inside a floating framed display rather
than using the standing-cast layer. Existing monologues cover entry and return
background changes; projection state clears at the end. Riko remains physical.

`games/bishoujo_afterlight/transmission_display.gd` is this game's presentation
adapter: frame design, clipped portrait feed, restrained TV treatment, floating
motion and framed-camera composition. It uses the existing hologram shader.
The host supplies texture, settings and effect time; the display does not own
dialogue progression or its own autonomous clock. This game-owned scene does
not require a new public controller, universal screen UI, or dedicated route.

## Proposed anatomy/geometry boundary (P100)

[Actor anatomy and visual geometry](../../../docs/research/actor-anatomy-visual-geometry.md)
is the canonical **unratified proposal**, shared with the repository research
index. Per-view asset evidence would own anatomy, regions and source coordinates;
a separate VLM annotation process would own estimation/provenance; hosts would
own attachment rules, offsets, transforms and overrides. Scale calibration is
explicit and separate. The document audits these hosts alongside upstream face
localization, sprite packing and calibration. No source migration, asset
annotation, runtime consumer or generation stage is added by this review.

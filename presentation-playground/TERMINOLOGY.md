# Presentation terminology dictionary

P107 maps reusable mechanisms to the [Game Presentation SDK](addons/game_presentation/README.md).
Presets, host choreography and UI keep their existing ownership; terminology is
not a list of mandatory modules. [Topology](TOPOLOGY.md) is the implemented tree.

This is our working vocabulary for requesting, demonstrating, and discussing
presentation features. Names describe the experience and its scope; they do
not decide which code becomes a module. This document records project usage,
not a claim that every studio uses the same taxonomy.

**Implemented** means a playable demonstration exists here. **Deferred** means
the idea is recorded but its mechanism is not implemented. Example use cases
describe where a feature could be directed; they are not additional promises
of assets or story content. The host/route owns its UI and authored direction.
For the consolidated inventory and remaining work, read
[CURRENT_STATUS.md](CURRENT_STATUS.md). This vocabulary mixes mechanisms,
presets, shot direction, and supporting utilities; its term count is not a
module count.

The [P106 SDK design](../docs/research/game-presentation-sdk-design.md#2-taxonomy-what-kind-of-thing-is-this)
classifies these terms as umbrellas, mechanisms, presets, bounded patterns,
authored compositions, assets and host/tooling policy. Its
[feature census](../docs/research/game-presentation-sdk-design.md#3-feature-census-and-proposed-ownership)
is the proposed SDK ownership map; this dictionary remains the experience
vocabulary. No term is promoted into a package solely by appearing here.

## Screen and point-of-view transitions

These change what the player can see through a screen-space mask. They do not
move the camera or change a character's actual eye sprite.

| Term | Meaning here | Example use case | Current proof |
| --- | --- | --- | --- |
| **Eye-Opening Transition** | A black eyelid mask slowly opens into a rounded horizontal aperture, ending with the complete scene visible. Code mode: `eye_opening`. | The player opens their eyes and discovers a character leaning close, looking directly at them. | Available in Presentation Lab's **Eye transitions** study; the authored story now selects the waking variant. Nami uses a dedicated close portrait; the lab's other guests use standing crops. |
| **Waking Eye-Opening Transition** | A brief partial opening closes again, holds shut, then opens fully. Code mode: `waking_opening`; peek duration/depth and close/hold/open timing are configurable. | The player recovers from a flash or unconsciousness, glimpses someone close or an unfamiliar place, reflexively blinks, then takes in the scene. | P84 adds the first Nami recovery and eye study. P87 also uses it for the empty infernal hall and return to Nami. This is a variant within the Eye Transition family, not another module. |
| **Eye-Closing Transition** | The rounded opening contracts until the world is completely covered in black. Code mode: `eye_closing`. | The player closes their eyes before sleep, loses consciousness, or pauses before a scene change. | Implemented: the study closes and holds black until another explicit command. |
| **Blink Transition** | Eye-closing, an optional fully closed hold, then eye-opening. The two durations are independent. Code mode: `blink`. | A brief first-person blink, or a longer reveal: close on the current view, change what is behind the mask while fully closed, then reopen on someone nearby. | Implemented in Presentation Lab. Afterlight authors opening/waking variants; Blink remains an independently replayable alternative. |
| **Edge Feathering** | A gradual alpha falloff at a mask boundary. It softens the cutout edge while retaining fully covered and fully revealed endpoints. | Make an eyelid opening feel softer and less graphic. | Implemented with a live **Edge softness** control in the eye study. This does not blur the scene image. |

The [Eye Transition contract](presentation/transitions/EYE_TRANSITIONS.md)
owns timing, endpoints, interruption, and state. A black-mask shader supplies
the rounded coverage. Afterlight places it above scenery/actors and below its
navigation controls; its story hides dialogue while the transition runs.
That layering is host direction, not a universal UI policy of the effect.

**Character blink** is a separate term: changing a character's open-eye and
closed-eye images or facial animation. Mira's existing sprite blink in Command
Link is not an Eye-Opening, Eye-Closing, or Blink Transition.

If an organic, irregular edge later warrants image-model artwork, the relevant
asset is a grayscale coverage mask or edge profile with a documented opacity
convention. Animation and endpoint handling would remain in code. The current
rounded aperture and feathering need no generated image. Blurring the underlying
scene for a waking/focusing sensation is a separate, currently unimplemented
effect.

## Background transitions

**Background Blackout** is a selective background transition: scenery fades to
complete black while the actor retains position, scale and appearance. Hold
black until a restore cue, then fade the scenery back in. A solo character's
stunned realization is the demonstrated use; the behavior does not infer an
emotion or require one actor. It differs from a whole-scene Fade to Black, an
Eye Transition, and a character Silhouette Fade by which layer changes.
P89 demonstrates Yuzu's warning in the story and a dedicated Lab study.
[Contract](presentation/transitions/BACKGROUND_BLACKOUT.md).

## Camera movement and shot direction

| Term | Meaning here | Example use case | Current proof |
| --- | --- | --- | --- |
| **Push-In** | Gradually move the framing closer. The current 2D implementation increases scene scale while retaining background coverage. | Approach a place or give a moment more emphasis. | Implemented as part of Walking Approach; not a separate generic camera component. |
| **Camera Bob** | Repeated, controlled vertical movement suggesting footsteps. | A first-person walk toward a meeting place, with scenery only. | Implemented within Walking Approach, with adjustable height and cadence. |
| **Walking Approach** | A push-in combined with camera bob that settles into a held view. | Walk into the café before meeting a character. | Implemented in Afterlight's story and Presentation Lab's **Camera study**. [Contract](presentation/camera/WALKING_APPROACH.md). |
| **Camera Shake** | Brief oscillation or disturbance of framing; its direction, duration, and cause are authored. | An impact or sudden interruption. | Implemented through finite Impact Shake in Afterlight's realm crossings and the Ominous Effects study. Camera Bob remains a separate walking cue. [Contract](presentation/camera/IMPACT_SHAKE.md). |
| **Camera Drift** | Gentle ongoing movement around an authored framing, with bounded independent horizontal and vertical motion. | Linger on someone nearby during a quiet, uncertain pause. | Implemented in Afterlight's detail beat and **Camera Drift** study. Explicit clock; the host applies one coverage-constrained offset to background and portrait. [Contract](presentation/camera/CAMERA_DRIFT.md). |
| **Portrait Detail Shot** | An authored close framing of part of a character. P63 frames the chin, collar, and upper torso with the face outside the view. | Convey proximity and mystery without showing the character's expression. | Implemented in Afterlight. P66 installs Nami's approved dedicated portrait; other guests use approved-art crops. This is shot direction, not a silhouette shader or separate generic module. |
| **Close-Up / Dialogue Camera** | An explicitly directed closer shot of an actor, held across dialogue beats until another camera cue. | Hold on someone during several consecutive lines, then return wide for a choice. | Implemented in Command Link and `demos/dialogue_camera`. [Contract](presentation/camera/DIALOGUE_CAMERA.md). Afterlight also authors close and detail framing, with Camera Drift during its detail beat. |
| **Establishing Shot** | A view that introduces a place before the main interaction. It can include background pan/zoom and a location announcement. | Enter a bright exterior, show its surroundings, then bring in the cast. | Implemented in Command Link and `demos/establishing_shot`. [Contract](presentation/camera/README.md). |

A shot describes composition and direction. A camera effect describes how that
framing changes. They can be combined deliberately without becoming one universal
camera graph. Background, actor, and attached-manpu geometry must agree on the
world transform; final framing must preserve background coverage.

## Character and attached presentation

| Term | Meaning here | Example use case | Current proof |
| --- | --- | --- | --- |
| **Actor Focus** | Speaker emphasis using a configured preset: bounce, slight enlargement, listener dimming/fading, or none. | A new speaker receives a small vertical pulse. | Implemented in Command Link and its focus demo. [Contract](presentation/focus/README.md). |
| **Manpu / Emanata** | Expressive marks associated with a character. **Manpu Introduction** animates each mark independently when cued. | A surprised mark appears with a small shake above the actor. | Implemented with raster marks, independent introduction clocks, looping steps/frames, and explicit one-shot events. [Contract](presentation/manpu/README.md). |
| **Opacity Fade** | Change an actor's opacity directly. | A simple departure where translucency is acceptable. | Implemented as a Character Exit preset. [Contract](presentation/transitions/README.md). |
| **Silhouette Fade** | Fade the colored actor to an alpha-shaped black silhouette while retaining coverage, then fade the silhouette away. | Let a character leave without first showing scenery through their colored body. | Implemented in the exit demo and Command Link's handoff. [Contract](presentation/transitions/README.md). This is actor-shaped coverage, unlike the screen-wide eyelid mask. |
| **Cast Transition** | A coordinated departure, optional repositioning, and arrival, with explicit sequencing and translation curves. | One actor leaves, the remaining actor changes position, then a third arrives. | Implemented for three actors/two positions. [Contract](presentation/transitions/CAST_TRANSITIONS.md). |
| **Hologram / Holographic Projection** | An actor-local projected-display treatment with tint, scanlines, flicker, and distortion. | A remote character joins the conversation through a projection. | Visual effect implemented; P99 adds host-coordinated Transmission Voice processing. [Vocabulary and scope](CHARACTER_EFFECTS.md). |
| **Actor Halo / Outer Glow** | A soft, colored glow outside the sprite's alpha silhouette, drawn behind the unchanged character. | Give a nearby heroine a gentle luminous outline during an intimate or mysterious moment. | Implemented in Afterlight's detail beat and **Actor Halo** study. Radius, color, intensity, and strength are runtime parameters. [Contract](presentation/effects/ACTOR_HALO.md). No glow is baked into the artwork. |

## Contact interaction

| Term | Meaning here | Example use case | Current proof |
| --- | --- | --- | --- |
| **Point Contact** | Circular hit testing and one acknowledged contact, independent of art, input device, timing and feedback. | Accept a pointer/touch hit on a target presented by the host. | P94 extracts the shared behavior from the tactical stage. [Contract](presentation/interaction/README.md). |
| **Fingertip Contact** | An authored interaction in which the player touches the offered fingertip in a character image. | Confirm that the courier has returned by touching Nami's offered finger. | Command Link's Mira scene and existing contact study remain playable; P94 adds Nami's dedicated pose and Afterlight story use, with native target/input checks at both window resolutions. This is a use of Point Contact, not an additional interaction framework. |

The host measures the target in the image, maps it through the presented
geometry, gates input and supplies the response. A moving camera or resized
window must update the target consistently with the image. The shared behavior
does not choose a character, draw a ring, play a sound or advance the story.

## Atmosphere and narrative presentation

| Term | Meaning here | Example use case | Current proof |
| --- | --- | --- | --- |
| **Lens Flare** | An optical-style overlay anchored to a light source projected from the scenery. | Arrive at a bright coastal location with brief sun glare. | Implemented in establishing shots. [Details](presentation/camera/README.md#camera-and-lens-flare). |
| **Ambient Particles** | Dust, floating glints, or sparkles in a chosen scene/foreground layer. | Small motes drift through a quiet close-up. | Implemented in P99 with sustained Sprite Particle Emitters: quiet dust and infernal smoke/embers/sparks. World-bound scene elements, not dirt stuck to a lens. [Contract](presentation/effects/SPRITE_PARTICLE_EMITTER.md). |
| **Radial Sprite Burst** | A finite group of sprites pops into view, disperses outward from an emission origin, and fades. The name describes motion and lifetime; sprite textures are interchangeable inputs. | Sparkles burst around Sena after a successful repair; another host can use petals, stars or confetti with the same timing. | P88 implements seeded one-shot emissions, overlap, outward easing, scale pop, rotation and fade in world space. The story and independent Lab use existing raster inputs. [Contract](presentation/effects/SPRITE_BURST.md). |
| **Intertitle** | A text-only beat interrupting the scene, here centered on black with progressive text reveal. | Introduce a memory, a passage of time, or a private thought between scenes. | Implemented in Afterlight and Presentation Lab's **Intertitle** study. The reusable controller owns reveal/continue state; the host owns text, black backing, layout, and continuation. [Contract](presentation/narrative/INTERTITLE.md). |
| **Monologue / Internal Monologue** | A character's private thoughts. Afterlight uses the player's first-person thoughts between spoken exchanges. | The courier weighs the letter's danger or registers an impossible step between realms, then returns to the scene. | Five authored intertitles in Afterlight. Monologue describes the narrative use; it is not a separate rendering module or a voiceover requirement. |
| **Typewriter Reveal** | Progressively reveal the characters in a text string. | Let a short thought appear at a measured pace before the player continues. | Implemented within Intertitle. First advance reveals the remainder; the next completes the beat. Optional Typewriter Audio is separately composed by the host; no automatic continuation is implied. |
| **Autoplay** | Optional host-controlled continuation after a ready beat's reading delay, with explicit defaults for timed choices and stops for mandatory input. | Let Afterlight run through dialogue, thoughts and cinematics until Nami requires a fingertip gesture. | P97 adds a top on/off control, off by default; ordinary ready beats wait 3 seconds and the authored courier-choice default waits 5 seconds with a countdown. Pause, language and Lab continuity are game-owned. [Contract](games/bishoujo_afterlight/AUTOPLAY.md). |
| **Opening Title Sequence** | The game's initial video-backed presentation. | A short montage before the player explicitly enters the game. | Implemented for Command Link, looping with fade-through-black. [Behavior](assets/opening/README.md). Separate from an intertitle. |
| **Typewriter Audio / Text Blips** | Short non-positional sounds paced by newly visible text, with whitespace suppression and a maximum cadence. | Audible feedback for a dialogue line or internal monologue without voiceover. | Implemented as optional Text Reveal Audio, with a built-in procedural sound and replaceable stream. Manual reveal stays silent. [Contract](presentation/narrative/TEXT_REVEAL_AUDIO.md). |
| **Dialogue Voiceover** | Playback of a supplied spoken line. | Use the character's localized voice instead of typing sounds. | Text Reveal Audio owns playback, pause and interruption. P95 adds Afterlight's localized recording bindings and complete subtitles for ready voiced lines. The audio component never advances the story; P97's optional host autoplay waits for its completion before starting the reading delay. |
| **Text-to-Speech / TTS** | Generation of spoken assets from authored text and voice choices. | Prepare an English and Korean character line before play. | P95 uses the existing ElevenLabs v3 route in a manually invoked local pass. Generation is separate from runtime; P96 forbids automatic refresh during development or gameplay. |
| **Voice Policy** | An authored decision that a speaker or line is voiced or intentionally unvoiced. | The courier's monologue uses `none`; Nami's dialogue uses a prepared recording. | Afterlight owns speaker defaults and per-line overrides. Intentional `none` is distinct from a recording problem and always wins over existing files. [Contract](games/bishoujo_afterlight/voice/README.md). |
| **Speech Script** | Optional spoken-text direction separate from displayed subtitles. | Add a sigh or short pause to a stable line without showing its tags on screen. | Fourteen sparse English/Korean overrides; absent overrides use display text. This is content for generation, not a new text renderer. |
| **Recording Freshness** | Whether a prepared recording matches its current source revision and is usable. | A wording or casting edit marks a clip `stale` for the next requested refresh. | Host status reports `none`, `pending`, `missing`, `failed`, `stale`, or `ready`. Inspection never generates or replaces audio. |

## Maintaining this dictionary

**Text Set** is a supporting utility, not a visual effect: stable text keys
resolve through a selected language with a fallback. **Language Selection** is
host policy/UI. Afterlight demonstrates English/Korean story and controls, with
in-place switching that preserves monologue progress and effect state. Text
meaning, fonts, and translated wording remain host content; the shared lookup
has no global locale or game dependency. [Contract](presentation/text/TEXT_SET.md).

For a new term, record its category, visible behavior, example use case, and
current proof/status. Link the component contract where one exists. Keep
authored choreography, asset needs, and host UI separate from the reusable
mechanism. Preserve the distinction between a proposed use case and a scene
actually demonstrated. Exact requests remain in [USER_PROMPTS.md](USER_PROMPTS.md)
and concise outcomes in [REQUESTS.md](REQUESTS.md).

**Radial Sprite Burst** belongs to emission/motion behavior. **Sparkles**, **hearts**,
**petals**, and **confetti** describe sprite content; **celebration** or **impact**
describe authored uses. A burst can serve a Manpu reaction, but it needs no
emotion, actor identity, or dialogue contract. Its finite outward release is
separate from the sustained emission and drift of Ambient Particles (P99).
Behind/in-front placement is the host's draw order; a 2D burst does not infer
3D depth or collision from the source artwork.

## Ensemble episode composition (P67–P68)

**Bishōjo** identifies the cast/presentation direction; **ensemble adventure
with a reconverging choice** identifies this episode's structure. It is not a dating-simulation
system. **Episode** and **beat** are authoring terms, not additional modules.

Afterlight's 57-beat *The Address Beyond* combines Walking Approach,
Eye-Opening, Intertitle, Portrait Detail Shot, Camera Drift, Actor Halo,
Speaker Bounce, animated Manpu, Dialogue Camera, Silhouette Fade, Cast
Transition with spring motion, Hologram, Establishing Shot, location labels,
Lens Flare, Text Reveal Audio, Refraction Field, Heat Haze, Ominous Corruption,
Impact Shake, and Fingertip Contact in one original story. Four heroines precede the distinct
Keeper villain; four indoor backgrounds follow the episode's setting. The
[paired episode review](games/bishoujo_afterlight/text/STORY_REVIEW.md) maps
precise beat IDs to their uses. Eira's dedicated transmission and its cleanup
are explicit authored cues; Riko stays physical throughout.

**Presentation Lab** is a separate demonstration host for both games' focused
studies. Its sliders, galleries, and sample conversations do not belong to the
main stories or define reusable component contracts. Existing story effects
retain their names and contracts. Opening-video examples remain in Command Link;
P94 extends fingertip contact to Afterlight while keeping its existing Lab route.
P95/P96 add localized character speech with explicit unvoiced narration and
manual preparation. P99 adds sustained Ambient Particles and applies
Transmission Voice processing to Eira's existing recordings while projected.
P97 adds optional host autoplay to this composition, including authored choice
defaults and mandatory-input gates; it creates no shared narrative module.

## Actor motion presets (P69)

| Term | Category and behavior | Example and status |
| --- | --- | --- |
| **Walk-Away** | Character Exit preset: horizontal travel with a repeated vertical step bounce; the actor leaves the visible scene. Left/right direction variants. | Implemented for Nami leaving to operate the bypass, and Presentation Lab's Actor motion/Character Exit studies. Full color is retained during visible travel. |
| **Restless Bounce** | Actor Focus / expressive motion preset: repeated Y-only bounce, unchanged X, settles at rest and stays visible. | Implemented for Riko's impatient ward-monitor report and the lab. Anger or anxiety is an authored interpretation, not an automatic emotion detector. |

Both reuse Presentation Animation scalar tracks. Offsets are proportional to
the original target height and compose before the world camera; attached manpu
follow. Walk-Away owns departure visibility through Character Exit. Restless
Bounce is a finite replayable focus cue, not a sustained emotion state. These
are our working preset names, not separate promoted modules or industry claims.
[Exit contract](presentation/transitions/README.md) ·
[Focus contract](presentation/focus/README.md).

### Actor Blocking and Quick Approach (P90)

**Actor Blocking** describes authored placement and movement of actors within
a scene. It is a direction category, not a new effect module. Entry/exit,
repositioning and a coordinated Cast Transition can participate in that direction.

**Quick Approach** is a blocking preset: one already-visible actor rapidly closes
the distance to another, stops nearby, and holds that position. Yuzu approaches
Sena while answering her toolbox remark. The recipient stays still; neither
actor fades or leaves. Walking Approach remains the separate first-person
camera movement. Speaker Bounce remains an emphasis cue rather than a change
in standing position.

The existing [Motion Curve](addons/game_presentation/motion/motion_curve.gd) supplies
linear, eased or spring interpolation. Afterlight's
[cast adapter](games/bishoujo_afterlight/cast_stage.gd) resolves the actor/target
pair and a one-time destination. Its root supplies duration and stopping
distance; the story supplies who, whom and when. Distance is between sprite
centers in logical world units, not a collision or silhouette-edge gap.
Attached manpu follows the actor before the world camera is applied.

The existing Actor Motion Lab demonstrates either direction, duration, gap and
curve selection. These are parameters over existing movement math; they do not
imply pathfinding, contact detection, a tracking target or a new promoted module.
See the [host contract](games/bishoujo_afterlight/ACTOR_BLOCKING.md).

### Layer Transforms and Cast Pan (P91)

**Layer Transform** is presentation applied to a chosen group of renderables.
**Layer Pan** is its translation-only behavior, sampled with the existing Motion
Curve. **Cast Pan** is the authored use: shift all characters and their attached
manpu together to bring one into focus while scenery remains fixed. It preserves
local actor spacing; Quick Approach changes that spacing. World-camera movement
reframes both scenery and cast.

Afterlight demonstrates Riko → Yuzu → Riko during the relay conversation, with a
dedicated Lab study for targets, retargeting, duration, anchor and curve. The
target is captured once; another speaker does not implicitly trigger a pan.
This is useful when a background fills the screen and provides no additional
pan coverage. Characters can scroll beyond the viewport without exposing a
background edge.

Ren'Py's named-layer `camera`/`show layer` facilities provide the relevant
engine precedent; Cast Pan is our descriptive name for this use.
[Ren'Py layer documentation](https://www.renpy.org/doc/html/displaying_images.html#camera-and-show-layer-statements).
[Sampler contract](presentation/animation/LAYER_PAN.md) ·
[Afterlight cues and composition](games/bishoujo_afterlight/CAST_PAN.md).

## One-shot manpu (P70, P93)

| Term | Category and behavior | Example and status |
| --- | --- | --- |
| **One-Shot Manpu** | Manpu lifecycle: an explicit event emits an independently timed instance, then removes it on completion. Repeated triggers may overlap. | Implemented in the existing manpu controller, with 2D cast and 3D billboard demonstrations. A sigh, brief surprise burst, or impact punctuation can use this lifecycle. |
| **Sigh Puff** | Manpu artwork and motion preset: a short exhaled puff grows, travels outward/upward, and fades over 0.65 seconds. | Four after-reveal cues in Afterlight cover Nami's resignation, her choice reply, relief after the return, and Riko's all-clear. The lab compares one-shot, static, and shaking uses of the same raster image. |
| **Sweat Drop Fall** | Manpu artwork and motion preset: the existing sweat raster appears near the temple, drifts downward and fades over 0.75 seconds. | Implemented through the same One-Shot Manpu emission and Presentation Animation tracks as Sigh Puff. Sena's modest-name joke and Riko's proper introduction emit it after text reveal; the Lab compares both presets in 2D/3D. |

Artwork, motion, and lifetime are separate decisions. A static puff is a
persistent cue; the same image can use a shaking introduction or be emitted as
a one-shot. Only an explicit emission starts a transient event. Dialogue
refreshes, camera changes, and rendering cannot replay it. The shared controller
owns identifiers, scalar samples, and expiration; a host owns actor anchors,
units, billboard orientation, depth, and node cleanup. This is a reusable manpu
behavior, not an ambient particle emitter or a new genre-specific module.
See the [lifecycle and composition contract](presentation/manpu/README.md).

## Looping Manpu animation (P92)

| Term | Category and behavior | Example and status |
| --- | --- | --- |
| **Stepped Transform Loop** | Presentation Animation: hold each authored transform, jump to the next, and repeat. No interpolation between the held steps. | One Manpu image alternates 0°/30° rotation and full/smaller scale. Implemented in Nami's early reaction, Riko's impatient arrival, and the reunion. |
| **Sprite-Frame Loop** | Presentation Animation: cycle supplied raster frame IDs on the same clock, with two, three, or more frames. Frame content is host-owned. | Lab uses existing different marks as explicit timing fixtures; future matching animation frames can replace those inputs. Implemented in 2D and the 3D preview. |
| **Looping Manpu** | A persistent Manpu cue with repeating motion and/or frames. This describes playback, not a new particle lifecycle. | Continues until the cue is removed; pause holds phase, replay returns to the first sample. |

Use *animation* or *frame animation* for these marks. *Locomotion* describes
movement through the scene and would be misleading for a mark turning in place.
The same scalar sampler provides the smooth introduction and held transform
steps. A host can instead supply a pure custom sampler through `sample_with`;
its returned channels and frame choice obey the same rendering contract.

Frame selection, transform motion, and lifetime are independent. Multiple
frames can also carry stepped motion; a single raster needs no generation to
loop expressively. Sigh Puff remains an explicitly emitted finite event.
[Manpu contract](presentation/manpu/README.md) ·
[Animation channels](presentation/animation/README.md).

## Afterlight narrative presentation (P71–P72)

| Term | Scope and use |
| --- | --- |
| **Advance Indicator** | A small pulsing dot indicates that the current text or cinematic has settled and can be continued. Hidden during an unresolved choice. Owned by Afterlight's UI. |
| **Edge Gradient** | A full-width background fade behind the top information and bottom dialogue, preserving text contrast without inset panel borders. Owned by the game. |
| **Reconverging Choice** | Two authored replies produce distinct short responses, then resume the same episode. The choice has a stable ID for language changes and in-session checkpoints. Implemented as Afterlight story direction, not a shared branching framework. |
| **After-Reveal Manpu Cue** | Story timing for a one-shot event: a puff begins when its line finishes revealing, so it remains visible while the player reads. The shared One-Shot Manpu lifecycle is unchanged. |


## Ominous scene presentation (P74)

| Term | Scope and use |
| --- | --- |
| **Refraction Field** | A foreground screen-reading region bends content drawn behind it. The barrier preset uses a small inward lens displacement and faint red tint; it does not rotate the image into a vortex. Host owns placement and draw order. |
| **Heat Haze / Heat Distortion** | Rising irregular refractive columns with no required color tint. A mode of Refraction Field, demonstrated during the realm excursion and separately in the lab. |
| **Ominous Corruption** | Our working name for a composable red-black treatment: darkening, procedural mist/aura, sparse drifting motes, subtle refraction, edge glow and screen vignette. An existing sprite's alpha, any reusable alpha mask, a soft area, or the full screen defines coverage. No new character artwork is required. |
| **Impact Shake** | A finite camera modifier with stronger irregular X/Y displacement, smooth attack/decay, and bounded overscan. World geometry moves together; dialogue UI stays fixed. Used for crossing the boundary and the Keeper's response. |
| **Realm Shift** | Authored story direction: the courier crosses into the Keeper's infernal Hall of Unclaimed Names, resists her demand, then returns. P77/P78 give this setting its own background; the location follows the story. This composes effects and the Eye-Opening Transition; it is not a new generic module. |

[Screen-field contracts and art tradeoffs](presentation/effects/SCREEN_FIELDS.md)
· [Impact Shake](presentation/camera/IMPACT_SHAKE.md). The corruption shader's
analytic motes belong to that visual treatment; they do not implement the still
separate sustained Ambient Particles mechanism, implemented in P99.

P85 retunes these existing effects as an **authored scene preset** for the Keeper
encounter. Broader red aura/mist, stronger background heat and brief impact
shakes target the user's requested increase from roughly 3/10 to 7/10. That
scale describes perceived intensity, not a shared numeric API or another effect
family. Close dialogue uses less foreground refraction than the rupture beats;
the return fades the effects away. Shared shader defaults and lab presets retain
their own values. No general particle emitter is introduced by this tuning.

P86 gives the existing corruption's **procedural pattern** an optional transform
from world coordinates to its parent canvas. Afterlight supplies the final camera
transform so its noise and ember flecks follow camera translation, zoom and
Impact Shake. Alpha coverage still follows the target; a screen vignette remains
screen-relative. The embers use varied elongated glowing cores rather than
uniform points. These remain analytic shader elements, not a general particle
emitter or sprite-based particle system. Optional future particle artwork does
not define the coordinate-space or lifetime contract.

## Particle Effects (P80 proposal, implemented in P99)

**Particle Effects** is the mechanism family. **Sprite Particle Emitter** is the
sustained emission component. **Ambient Particles** describes an atmospheric use;
**dust**, **smoke**, **rising embers**, and **sparks** are appearance/motion presets.
**Radial Sprite Burst** keeps its distinct finite outward-release lifecycle.
These local terms do not ratify package boundaries.

| Level | Responsibility and current proof |
| --- | --- |
| Sprite Particle Emitter | Continuous seeded births, bounded lifetimes, velocity/drift/spin/fade, interchangeable textures, explicit time and world transform; stop/drain, seek and reset. [Contract](presentation/effects/SPRITE_PARTICLE_EMITTER.md). |
| Game-owned atmosphere presets | Sparse warm lounge dust, cool relay dust, dark expanding smoke, rising elongated embers and faster sparks. Code-authored raster fallbacks can be replaced with prepared images without changing motion. |
| Host composition | Afterlight chooses scene profiles, depth, camera and intensity. Particles persist between dialogue lines, freeze during black monologues, and reconstruct across Lab detours. Camera shake and zoom affect them; Cast Pan does not. |

Current corruption motes remain analytic shader output. Screen-field mist and
particle smoke coexist; neither must be rewritten into the other. One-Shot
Manpu retains its expressive cue contract. Similar lifetimes do not require
merging it into an emitter. No new general simulation framework is introduced.
Two-dimensional particle sprites do not infer 3D depth or collisions. A later
3D consumer must supply its own rendering adapter; only the current 2D host is
proven here. The existing One-Shot Manpu 3D example is a separate proof.

## Audio Effects and Voice Processing (P99)

| Term | Meaning and example | Current proof |
| --- | --- | --- |
| **Audio Effects** | Umbrella for signal treatments applied during playback. | Working taxonomy, separate from speech generation and narrative timing. |
| **Voice Processing** | A reusable processor on a selected voice route; the host decides who and when. | Private Godot bus, explicit destination, strength, bypass, reset and cleanup. Typing has a separate dry route. [Contract](presentation/audio/VOICE_PROCESSING.md). |
| **Transmission Voice** | Band-limited, gently distorted radio/display speech. | Eira's framed call uses strength 0.65; dry/wet and intensity can be compared in the Lab using existing EN/KO clips. No modulation, static layer or voice regeneration is required. |
| **Audio/Visual Effect Coordination** | Host direction connecting independent visual and audio treatments to the same authored state. | Eira's actual voiced lines are processed while projected; protagonist replies, physical speakers and call cleanup bypass the effect. |

## Dedicated Transmission Scene (P81/P82)

A game-authored conversation conducted through a remote character's
transmission. Afterlight uses researcher Eira and a Relay Laboratory for four
operator lines and two player replies. Monologues hide the location changes.
Riko is physically present in her own ensemble scenes.

**Framed Transmission Display** is the working name for P82's floating screen:
a clean portrait feed is clipped inside a code-drawn frame, with the existing
TV/Holographic Projection shader applied inside the display. The face remains
readable, the frame gently floats, and a restrained close framing stays clear
of dialogue. This is game-owned visual composition, not another universal
module. Eira's technical clothing and laboratory are generated art; the frame,
motion, scanlines and timing are runtime presentation. P99 adds independently reusable Transmission Voice
processing, coordinated with the display by Afterlight.

P83 strengthens the existing **Holographic Projection** preset rather than
introducing a new effect name: more visible scanlines, rolling band and signal
fluctuation, with 90% actor and 70% framed-feed defaults. Blue source art still
reads as a transmission; its material strength remains configurable.

## Actor anatomy and visual geometry (P100 — proposal only)

The [canonical proposal](../docs/research/actor-anatomy-visual-geometry.md)
separates **Anatomical Landmarks**, **Anatomical Regions**, **Image Geometry**,
**Scale Calibration**, and **Consumer Attachment Rules**. It recommends COCO's
17 human-keypoint names as an available sparse vocabulary, with explicit local
point definitions and optional `mouth_center` / `face_region` additions.
Anatomical sides differ from canvas sides; a head pivot is not a face center,
and alpha bounds are not anatomical size. Existing host coordinates remain
unchanged. The proposed VLM-only evaluation has not run; runtime, annotation,
generation integration and standing framing remain deferred.

# Bishōjo: Afterlight

**The Address Beyond** is an ensemble fantasy adventure through a male
courier's viewpoint. An undeliverable letter brings him into Afterlight House,
where he meets all four heroines, consults remote operator Eira alone in the
Relay Laboratory, and helps repair the station wards. Only after
that repair does the seal pull him into the Hall of Unclaimed Names, a dedicated
infernal otherworld interior.
The Keeper, a dedicated villain, demands his name as the price of returning;
Nami reaches him through the seal and offers her fingertip to confirm he is
back. Tomorrow's unnamed visitor leaves room for
a later episode.

The game is bishōjo, with character chemistry and an attractive ensemble. It
has no dating routes, guest selection, affection score, or romance choice.
The old `dating_sim` launch selector survives only as a compatibility alias.
Brown Dust 2's central-story presentation was the requested reference, not its
plot or characters ([official Story Pack description](https://browndust2.gitbook.io/guide_en/game-guideline/pack/story-pack)).
This original episode primarily demonstrates presentation mechanisms naturally.
The project-wide [current status](../../CURRENT_STATUS.md) separates implemented
mechanisms from open work and provisional module terminology.

## Play

```sh
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/godot/games/playground -- --game bishoujo_afterlight --language ko
```

Click/tap the scene, or use Space/Enter. Ready voiced character lines display
their full subtitle immediately and play the recording; an advance continues
and stops the previous recording. Unvoiced lines first reveal their text, then
continue on the next advance. With autoplay off, voice completion alone leaves
the current beat in place.
A small dot appears when the scene is ready; no Next/Skip buttons or on-screen
input instructions interrupt the view. Top information and bottom dialogue
use gradients flush with the screen edges. During a cinematic, an advance
action finishes its motion before the next action continues. In the dedicated
fingertip-contact beat, touch Nami's offered finger after the line is revealed;
a general advance does not bypass that contact. The gesture confirms the moment,
then its brief feedback completes and the story continues.

The top **Autoplay** on/off button remains available during monologues and
close-ups. It starts off. Turn it on to continue automatically 3 seconds after
text, finite cinematic motion and voice playback finish. Manual advance still
works and restarts the delay. Autoplay waits for mandatory interaction and
turns off at the ending. The [autoplay contract](AUTOPLAY.md) covers timing,
authored gates and in-session continuity.

The 57 beats introduce the whole cast. An early two-option exchange lets the
courier offer help or negotiate tea, earns a different reply from Nami, and
rejoins the same episode. Choices appear near the lower center, above the
dialogue sheet. With autoplay on, the authored offer-help default shows a
5-second countdown before selection; either option can be selected immediately.
Without autoplay, choices wait for the player. Escape opens the pause menu.
From there, resume,
restart the episode, visit Presentation Lab, or switch to Command Link.
Language can be changed with the header button or F6, including during a
monologue. Use `--language en` for English; the default is English.

The [paired English/Korean story review](text/STORY_REVIEW.md) lists every beat
and its effect cues for wording feedback. These stable beat IDs are useful
references when requesting changes.

P99 binds scene-specific [atmosphere profiles](atmosphere_profile.gd) to the
shared Sprite Particle Emitter, with quiet warm/cool dust and infernal smoke,
embers and sparks. Particles follow the world camera, freeze during pause and
monologues, and restore across replay/Lab detours. They draw behind actors and
dialogue. Eira's existing voice recordings use [Transmission Voice processing](../../presentation/audio/VOICE_PROCESSING.md)
while she is projected; other voices and typing are dry. Both effects have
independent Lab studies. Standing framing remains explicitly deferred.

## Direction and ownership

[root.gd](root.gd) is the discoverable composition root: routes, installed art,
effect settings, text sets, and [story_beats.gd](story_beats.gd). The latter is
ordinary authored Godot content, not a portable scenario schema or a universal
game language. [story.gd](story.gd) owns the episode, input, clocks, camera
composition, and the complete game UI. [cast_stage.gd](cast_stage.gd) is its
concrete standing-cast adapter, composing the existing independent controllers.
It contains no dialogue or story branching and is not imposed on other games.

| Story situation | Existing presentation mechanisms |
| --- | --- |
| Courier's thoughts between scenes | Intertitle on black; progressive text reveal; suspended world clock |
| Crossing the conservatory | Character-free Walking Approach with push-in and vertical bob; sustained world-space dust |
| Recovering from the seal's flash | Feathered Waking Eye-Opening: brief partial peek, blink shut, then fully open onto Nami's close portrait |
| Reading the warning together | Multi-actor dialogue, Speaker Bounce, animated raster manpu, directed camera close-ups |
| Yuzu recognizes the sender | Solo held close-up with Background Blackout: only scenery fades to black; the next line restores it |
| Offering help or negotiating tea | Two centered response options, a distinct Nami reply, then the shared story continues |
| Holding the seal toward the window | Nami's approved chin-to-chest Portrait Detail Shot, Camera Drift, Actor Halo |
| Nami leaves; Sena brings her tools | Walk-Away with X travel and Y step bounce, then survivor reposition and new arrival with spring translation |
| Yuzu answers Sena's toolbox remark | Quick Approach: one visible actor closes the gap to the other, then holds the closer position; attached manpu follows |
| Sena completes the ward repair | A Radial Sprite Burst releases sparkles from behind her shoulders, disperses outward, then fades |
| Entering the reading room; returning home | Background-only Establishing Shots, location label, pan/zoom, modest lens flare |
| Riko brings the station monitor and checks the relay | Physical actor with an impatient Restless Bounce, then a Silhouette Fade departure |
| Riko and Yuzu exchange relay instructions | Cast Pan slides the three-character group toward each speaker over a fixed background, preserving local spacing and attached reactions |
| Private memory-glass call with Eira | Dedicated operator and indoor setting; six turns with only her framed portrait transmission visible, held close-up, black intertitles covering entry/return, and matching Transmission Voice processing with explicit projection/audio cleanup |
| The repaired seal pulls the courier into another house | Barrier refraction, Heat Haze, scene/area corruption, finite Impact Shake |
| The Keeper demands a name as payment | Dedicated villain identity, alpha-masked corruption, directed close-up, layered smoke/rising embers/sparks |
| Nami pulls the courier back | Effect fade-out, Waking Eye-Opening Transition, relief Sigh Puff |
| Nami makes sure he has returned | Dedicated reach portrait and Fingertip Contact: the host maps the image landmark to a circular hit target and owns the acknowledgement feedback |
| The group regathers | Four-character composition; Riko's physical arrival clears the projection treatment |

The main story contains no study sliders, guest picker, backdrop picker, or
per-effect routes. Those implementations moved to the independent
[Presentation Lab](../presentation_lab/README.md), whose prepared fixtures have
their own state and language. Both games remain accessible from its menu.

The fixed logical canvas is 1280×900; Godot renders at the native window
resolution with proportional actor/manpu transforms. Dialogue remains in screen
space. Camera endpoints and drift are constrained to background coverage.
Pause and lab visits freeze the story. In-session checkpoints record stable beat
ID, elapsed cue history, chosen response IDs, event timing, and separate reveal progress; replay restores effects
without advancing wall time or forcing a common controller save interface.
These are bounded episode checkpoints, not durable cross-version save files.

## Art and remaining scope

P94 adds a dedicated Nami reach portrait, bringing the active catalog to thirteen
images. It is an unchanged copy of the independently reviewed 2048×1536 source;
[the review](../../art/rounds/afterlight-contact-v1/REVIEW.md) records preserved
identity/style, the manually selected fingertip and the limited hood headroom
and baked glow. One Sunburst max request cost $0.2822 from a fresh $5 budget;
the remaining $4.7178 is recorded in that round's budget file. Native target,
input and story-continuity checks pass at 1280×900 and 2560×1800. This is an authorized new addition, not a
replacement of the earlier Nami images or a new user quality verdict.

`a_touch_that_stays` follows `a_hand_to_hold` and precedes `only_a_second`.
The preceding narration leaves contact to the player instead of claiming it
already happened. The game root owns the image binding, rectangle and normalized
fingertip `(0.462890625, 0.57421875)` with radius `0.03515625` of image height.
The story owns reveal readiness, pointer/touch routing, acknowledgement feedback,
continuation and checkpoint state. The shared
[Point Contact](../../presentation/interaction/README.md) behavior only tests
the supplied circular target and latches confirmation; it has no art or UI.
The episode now has 57 beats, 312 matching English/Korean keys and 60 paired
review rows. The existing tactical contact study keeps its route.

All existing approved PNGs remain unchanged: four standing heroines, Nami's
close and dedicated detail portraits, and two indoor backgrounds. Nami/Yuzu
retain the flat proportion direction; Sena/Riko retain exaggerated feminine
proportions. A dedicated `keeper_standing.png` was added separately under P75
following independent visual and alpha review. Its pretty face and controlled
evil smile follow P76. This addition leaves all four heroine images unchanged;
user quality feedback remains distinct from the integration record.
P77 adds a third indoor setting, the Hall of Unclaimed Names, for the Keeper
encounter. P78 gives it a darker infernal direction: obsidian and black iron,
crimson furnace light, and molten glow under side grates. The final image was
added unchanged after independent review; the calmer draft remains unused.
Its actual source is 1496×1051 RGB, so a 2560×1800 window enlarges that image
rather than revealing additional native detail. The reveal
follows the black `between_addresses` intertitle; the return restores the
reading room. The conservatory and reading lounge remain available unchanged.
Story intent determines the setting; prepared backgrounds can follow later,
without requiring new generation for every wording change.

P81/P82 add Eira's clean portrait feed and a scientific Relay Laboratory. The
floating frame and its motion are drawn by the game; the existing hologram
shader treats only the clipped feed. The initial full-body/alcove additions
remain inactive drafts. No previously approved heroine image changed.

Media remains local and ignored by Git; source-only checkouts need the prepared
files listed in [the asset catalog](assets/catalog.json).

P95/P96 add localized character speech through P73's existing voice playback
and built-in typing fallback. The protagonist stays explicitly unvoiced;
recording preparation and later refreshes happen only on a manual request.
P99 adds sustained Ambient Particles and matching Transmission Voice processing. The tactical
opening video remains in Command Link. Afterlight reuses Point Contact with its
own dedicated Nami pose and story beat; Mira's image stays with the tactical
game and its existing contact study. Eye-Closing/Blink alternatives,
focus/exit presets, and tunable curves remain individually explorable in the lab.

The initial `eyes_on_nami` beat selects `waking_opening`: a 0.22-second partial
peek to 42% aperture, 0.14-second closure, 0.08-second closed hold, then a
2.2-second full opening. Root settings define these timings; an eye beat can
select `eye_mode` and supply `eye_settings` overrides. P87 uses the same waking
variant for the infernal hall and later recovery. The hall sets `eye_portrait`
to false and stages no actors, letting the player blink into the new setting
before the Keeper appears. The [Eye Transition contract](../../presentation/transitions/EYE_TRANSITIONS.md)
owns the behavior; the game owns the chosen scene and preset.

The Keeper's infernal scene uses stronger P85 direction over existing effects:
18-pixel heat/barrier amplitude, a 140-pixel red aura with denser black mist,
and larger finite impacts. Her arrival has a short impact; resistance peaks at
72×54 logical pixels. Foreground barrier strength remains 0.28 during the close
dialogue, with higher strengths reserved for rupture/resistance. World darkening
is balanced against the brighter glow to keep the hall legible. The return
fades all fields out over 1.8 seconds before the recovery shot. These settings
live in the root and story cues; the shader contracts and art are reused.
P86 binds both corruption patterns to the final world transform, including
camera shake and zoom. Its brighter ember flecks have varied elongated shapes
and soft glow. Mask coverage and screen vignette retain their own placement;
general Ambient Particles and optional sprite inputs remain separate work.

## Checks

```sh
/Users/universe/.local/bin/Godot --headless --path /Users/universe/Documents/shared/stage-gen/godot/games/playground --script res://qa/afterlight_ensemble_checks.gd -- --game bishoujo_afterlight
/Users/universe/.local/bin/Godot --headless --path /Users/universe/Documents/shared/stage-gen/godot/games/playground --script res://qa/presentation_lab_checks.gd
```

The old selected-guest story QA entry points delegate to the ensemble suite.
Controller and laboratory checks retain independent effect coverage.

P69 adds selectable motion presets without new assets. `exit_preset` on the
handoff/exit beat chooses the departure; `focus` chooses the speaking cue.
Nami's `sena_takes_over` departure uses `walk_away`, while Riko's first
transmission uses `restless_bounce`. The latter stays in place and settles,
without an exit. Both variants can be replayed in Presentation Lab → Afterlight
studies → Actor motion.

P70 adds `manpu_events`; P72 schedules them after text reveal. The current
episode has four Sigh Puff cues: Nami's `no_forwarding_address`, her
`courier_reply`, her relief in `only_a_second`, and Riko's `all_clear`.
Each event names an actor, prepared raster mark, and motion preset. The story
emits once when the line finishes revealing, including an explicit reveal
action. Sigh Puff travels and fades in 0.65 seconds. Scene
cuts cancel attached events, and checkpoint replay restores a mid-puff moment
from authored history/time. Persistent `mark` cues retain their behavior.

P92 allows a persistent mark to choose its animation with `mark_preset`.
`no_ordinary_post`, `riko_on_the_glass`, and `everyone_accounted_for` select
`step_loop`: the same raster alternates held 0°/30° poses and full/smaller scale.
The loop lasts until the next beat removes it. Actor motion, Cast Pan and world
camera still carry the mark together. Language changes and Lab detours restore
its sampled phase through the existing story history.

The shared [Manpu contract](../../presentation/manpu/README.md) also accepts
ordered frame IDs and a host-supplied animation sampler. Dedicated matching
frame art is not required for the single-sprite story proof; the Lab demonstrates
two/three-frame playback with existing marked fixture inputs.


P93 adds two Sweat Drop Fall events alongside the four Sigh Puff cues.
Sena's `a_modest_name` joke and Riko's `a_proper_hello` introduction emit the
prepared `sweat_drop` raster with preset `sweat_drop_fall` after text reveal.
The drop slides down from the temple and fades in 0.75 seconds. These are
new authored uses of the existing one-shot mechanism, with unchanged dialogue.

## Text reveal audio (P73)

Dialogue, monologues, and the choice prompt use the optional
[Text Reveal Audio presenter](../../presentation/narrative/TEXT_REVEAL_AUDIO.md).
The built-in procedural tap follows new non-whitespace characters with a cadence
cap. Clicking to reveal the full line produces no sound burst. Menu pause stops
both clocks and playback; entering another beat or game stops the old cue.
Cinematic captions are silent because their text reveals while hidden.

The host's `CONTENT.text_audio` sets the default policy (`auto` at -18 dB typing
gain). Each beat can override it with `text_audio`. `auto` uses a supplied voice
for the whole line, otherwise typing; `typing` forces the fallback, and `silent`
disables both. `typing_stream` can replace the built-in tap with an AudioStream.
No audio generation or paid call is required for the default.

`CONTENT.voiceovers` maps language to resolved text ID to AudioStream, including
choice-specific replies. P95's game-owned voice resolver binds only ready,
current recordings. In `auto`, a ready voice reveals the complete subtitle and
suppresses typing for that cue. Cinematic speech waits until its caption is
visible; manual advance can still finish the motion. A missing, stale or
failed recording uses the host's fallback instead of playing outdated speech.

Checkpoints save voice position (or completion) and source revision; historical
cue replay stays silent. The same-language, same-revision current line resumes
from that position. A language change starts the other language's recording
from its beginning, retaining the current beat and scene state. There is no
word-level timing. The audio component never advances the game; optional host
autoplay waits for voice completion before starting its continuation delay.

### Afterlight voice policy and manual refresh (P95/P96)

The unchanged 57 beats contain 58 unique story text IDs per language, including
alternate replies. Each language has 40 voiced character lines and 18 deliberate
protagonist `none` lines. Four localized choice-button labels are excluded, as
are menus and technical demos. Six character identities use consistent existing
voices; casting is recorded separately for English and Korean. Fourteen sparse
speech-script overrides add delivery tags without changing approved display
text. Other lines use that display text directly.

The [voice contract](voice/README.md) describes speaker defaults, line overrides,
source revisions and `none`/`pending`/`missing`/`failed`/`stale`/`ready` states.
These states are inspectable without refreshing anything:

```sh
/Users/universe/.local/bin/Godot --headless --path godot/games/playground --script res://games/bishoujo_afterlight/voice/export_inventory.gd -- --status
```

Run that command from the repository root. Playback, replay, edits and status
inspection never generate audio. A later refresh happens only when requested;
the [manual preparation command](../../tools/AFTERLIGHT_VOICE_PREPARATION.md)
preserves valid recordings and their provenance. Objective decoding is separate
from a listening verdict, which has not been performed for this pass.


## The Address Beyond (P74)

The twelve excursion/return beats run from `scarlet_pressure` through
`only_a_second`. P75 places them after the ward repair at `the_reroute`, with
`the_seal_answers` introducing the renewed threat. All four heroines have
already entered the story. Warm teamwork becomes an ominous encounter, then
returns to the same cast. The villain uses a dedicated `keeper` identity;
its new character artwork was independently reviewed and added under P75.
Existing heroine art and the two original backgrounds remain unchanged. P77
adds the dedicated Hall of Unclaimed Names environment for this excursion.

`heat`, `barrier`, `scene_corruption`, `corruption`, and `shake` are this host's
ordinary authored cue fields. Their shared implementations remain independent.
`root.gd` holds the host's effect settings. Screen refraction is intentionally mild;
stronger mood comes from selective darkening and aura. `rift` is a held cinematic
cue: the first advance finishes it, then another continues. The return lets the
fields fade away before Nami's Waking Eye-Opening Transition. Autoplay waits for
the cinematic to complete naturally before beginning its reading delay.

Draw order is background → heat → background corruption → cast/portrait → local
corruption → foreground barrier → other overlays → UI. Speaker text and controls
stay crisp. The local alpha treatment uses the actor's displayed texture rect,
including focus and camera motion. Shader time and Impact Shake follow the world
clock, preserving pause and in-session restore. Local passes intentionally affect
whatever is rendered behind their mask, so arbitrary overlapping characters may
need a different host layer arrangement; isolated material ownership is not implied.

Presentation Lab → Afterlight effects → Ominous effects compares barrier, heat,
corruption targets and combined treatment, procedural/default noise and a reusable
noise texture, and stronger camera shake. General ambient particles remain
deferred; P95/P96's localized voice pass is separate from these visual effects.

# Game Presentation Kit

For agent continuity, start with the [current handoff](HANDOFF.md).

The [Game Presentation SDK](../addons/game_presentation/README.md) is the code-first
successor of this implementation, packaged at `addons/game_presentation/`.
Afterlight, Command Link and Presentation Lab use that same maintained source.
The development folder remains `godot/games/playground/` so existing launch
commands and local asset locations stay valid. Asset-generation recipes and
upstream engine-free gameplay families remain independent.

Start a new game with the [standalone starter](../../../templates/vn/README.md), whose
single `main.gd` owns its story, composition and complete UI. The addon needs no
example media. Prepared example art/recordings can be loaded from a separate
local content root; see [packaging and external content](../docs/PACKAGING.md).
Normal Godot source UID sidecars travel with source; imported caches do not.

P106 records the [SDK design](../../../../docs/research/game-presentation-sdk-design.md)
and [complete historical request triage](../../../../docs/research/game-presentation-sdk-triage.md).
P107 implements the package boundary and starter. Scenario remains an optional,
experimental secondary authoring surface. Anatomy annotation and standing framing
remain deferred. This pass is local source packaging, not a public release.

Three explicit roots share presentation mechanisms. **Command Link** remains
playable by default. **Bishōjo: Afterlight** is an original 57-beat
ensemble adventure with one brief reconverging choice, English/Korean text,
and a male courier viewpoint. All four heroines enter and complete the ward
repair before a brief otherworld encounter with the dedicated Keeper villain.
A dedicated, independently reviewed Keeper sprite has been added; the four
heroine images remain unchanged. P77 gives the encounter its own third indoor
setting, the infernal Hall of Unclaimed Names, added after independent review.
P81/P82 add Eira, a remote relay researcher, with a six-turn solo call through
a floating framed portrait display in a fourth interior, the Relay Laboratory.
Riko remains physically in the ensemble.
P94 adds Nami's offered-fingertip moment after the return from the otherworld.
The shared [Point Contact](../../../games/command_link/presentation/interaction/README.md) behavior serves
both games with independent story gates and feedback. Nami's new pose passed
independent art review, and native input/continuity checks pass at both window
resolutions.
P95/P96 add English/Korean character voiceovers with explicit unvoiced
protagonist lines, separate speech direction, and source revisions. Ready voiced
lines show their complete subtitle immediately; unvoiced lines retain typing.
Recordings are prepared only on an explicit manual request. The
[Afterlight voice contract](../../../games/afterlight/voice/README.md) owns policy,
freshness states, and the provider-free status command.
P97 adds a persistent top **Autoplay** on/off control to Afterlight, off by
default. It waits for text, cinematics and voice playback, then continues after
a reading delay; the courier choice has a timed default. Mandatory interaction
still waits for the player, and the ending turns autoplay off. See the
[autoplay contract](../../../games/afterlight/AUTOPLAY.md).
Environment assets follow the story's needs; the original locations remain available.
**Presentation Lab** owns both collections of technical demonstrations; the
actual games contain their stories and small navigation menus.

- [Current inventory and open items](CURRENT_STATUS.md)
- [Afterlight play, story, and effects](../../../games/afterlight/README.md)
- [Paired English/Korean story review](../../../games/afterlight/text/STORY_REVIEW.md)
- [Presentation Lab](../../../games/command_link/lab/README.md)
- [Topology and responsibilities](TOPOLOGY.md)
- [Presentation terminology dictionary](../docs/TERMINOLOGY.md)

The old `--game dating_sim` selector is a compatibility alias for Afterlight,
not a genre description. UI is wholly owned and manually configured by its
host/route. Shared code offers utilities and independent behaviors; it does
not prescribe a common game UI or universal story language.

```sh
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/godot/games/playground -- --game bishoujo_afterlight --language ko
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/godot/games/playground -- --game presentation_lab
```

The existing media moved here intact and remains local. The project's
`.gitignore` excludes generated PNG/OGV assets, art working files, captures,
QA output, and the Godot import cache. A fresh Git checkout needs the prepared
PNG and OGV files copied into their matching `assets/` paths from this local
project before it can play the same game; launching never generates assets.
Historical art and QA links refer to local evidence and may be absent in a
source-only checkout.

For the short request-to-outcome history and exact user wording, see
[the request ledger](REQUESTS.md) and [prompt archive](USER_PROMPTS.md).
These records leave module boundaries and final terminology for later review.
The [promotion review](PROMOTION_REVIEW.md) proposes boundaries and integration
gates; it does not approve or perform promotion.
The hologram experiment's working vocabulary and matching voice processing
are in [Character visual effects](../docs/CHARACTER_EFFECTS.md).

## Scope

- Bishōjo: Afterlight: an ensemble investigation introducing all four heroines
  through one episode with a playful two-option exchange. Walking Approach, Eye-Opening and Waking Eye-Opening Transitions, black
  monologues, portrait detail/drift/halo, focus, manpu, cast handoff, hologram,
  Background Blackout, fingertip contact, and establishing shots support the plot. A brief otherworld encounter adds
  Refraction Field, Heat Haze, Ominous Corruption, and Impact Shake. Text Reveal Audio supplies a built-in
  typing sound or plays the selected localized character recording. Sustained
  Ambient Particles add quiet dust and infernal smoke/embers/sparks; Transmission
  Voice processes Eira's existing recordings while her projection is active.
- Presentation Lab: both games' independent study collections. Eye-Closing,
  Blink, alternate exit/focus presets, and adjustable curves remain here. Its
  twenty-four studies comprise eleven Command Link and thirteen Afterlight workbenches.
  The eye study adds adjustable peek duration/depth for the waking variant,
  alongside opening, closing, closed hold, and live edge softness.
- Command Link has two 1080p anime opening edits, 22.5 and 22 seconds, with one Begin Briefing
  control and a fade through black between loops. [Opening behavior](../../../games/command_link/assets/opening/README.md).
- Command Link's three original adult women use a polished painted tactical-anime style: Mira,
  25, Lena, 21, and Sera, 23. These are temporary names for the prototype's dialogue.
- Mira's full-body open-eye sprite and registered closed-eye blink variant,
  plus Lena's and Sera's single full-body standing sprites.
- A closer pose that faces the player and offers one index fingertip toward the
  camera, so clicking or touching the drawn fingertip can feel like contact.
  P94 brings that gesture into Afterlight through a dedicated Nami pose and
  the same small interaction behavior; each game owns its story and feedback.
- **Command Link**, a playable tactical briefing with the player as commander,
  two decisions, a later order callback, required fingertip pairing, and an ending.
- Small game menus preserve story state when visiting the independent lab.
- Nine image-model-painted manpu, with persistent introductions and independently
  emitted one-shot instances. Sigh Puff moves, fades, and expires automatically.
- Three painted tactical locations, a choice of approach, and character-free
  establishing shots with pan, zoom, location titles, and an optional lens flare.
- An explicitly authored Dialogue Camera close-up held over several briefing
  lines, with a separate demo for all three actors and an adjustable scene zoom.
- A dedicated hologram demonstration with actor selection, an on/off toggle,
  and adjustable strength.
- A dedicated Character Exit demonstration comparing Silhouette Fade,
  Opacity Fade, and left/right Walk-Away on independently selected actors.
- A bilingual Actor motion study compares horizontal walking departures with
  the Y-only Restless Bounce used for an impatient or anxious speaker, plus a
  two-actor Quick Approach with adjustable distance, duration and curve.
- Cast Pan frames a character by translating the cast together over a fixed
  background, with target and timing controls in its dedicated study.
- A Cast Transition demonstration with sequential departures, position changes,
  and arrivals, plus an adjustable motion curve and its live graph.
- Command Link's code-authored tactical interface has dark clipped-corner panels, condensed
  headings, amber primary actions, and numbered demonstration cards.

Command Link's current art follows the user's supplied visual references: dimensional
painted shading, layered tactical fashion, and distinct leather, fabric, metal,
and hosiery materials. Mira retains short auburn hair and teal accents; Lena
retains long blonde hair and burgundy accents. Sera adds a dark ink-blue ponytail,
amber eyes, and ivory/cobalt clothing.

Command Link's art was prepared through individually authorized FAL API requests.
Afterlight uses FAL-generated assets and later built-in image-model additions;
its catalog records each active source and review.
There is no Stage Gen generation graph, prepared game package, or new public
schema in this experiment. Character, manpu, and background artwork are PNGs
from image-model requests. Godot draws the interface and interaction feedback.
Afterlight combines a built-in typing fallback with explicitly prepared localized
speech. Its voice policy and original MP3 provenance remain separate from the
display text and runtime playback. Preparation is manual; the game never calls
a provider.

Command Link's interface uses native Godot drawing and controls, with tactical style helpers in
[the tactical UI notes](../../../games/command_link/presentation/ui/README.md). Body text uses Godot's bundled font;
headings use installed system-font fallbacks. This pass adds no generated UI
images, SVG, or downloaded fonts. Future image-model UI automation remains a
later possibility recorded in P27.

## Open

From the repository root:

```sh
Godot --editor --path godot/games/playground
```

To play directly:

```sh
Godot --path godot/games/playground
```

The opening video loops until an explicit click or tap. Click **Begin Briefing**
or click/tap the video to enter the story; keyboard input does not continue the
opening. Use **Menu** or **Esc** during the story to pause it and visit
Presentation Lab. A study route can also be opened directly:

```sh
Godot --path godot/games/playground -- --route demos/contact
```

Use `--route menu` for the menu, `--route game` to bypass the opening, or
`--route opening` to replay the title sequence. The eleven demo
route IDs and their controls are listed below. Legacy `--mode full_body`,
`reach_out`, `dialogue`, and `manpu_gallery` map to `demos/characters`,
`demos/contact`, `demos/dialogue`, and `demos/manpu`, respectively. In particular,
`--mode dialogue` opens the focused dialogue demo, not the main story.

The project is self-contained and uses the installed Godot 4.7. Its generated
import cache can be rebuilt by opening the project. Keep this entire experiment
in this standalone project until the user requests a later extraction or disposal.

## Fixed presentation size

This POC uses one **1280 x 900** design canvas. Resizing the window scales the
entire composition together: characters, manpu, background, text, controls,
and shader output. There is no responsive reflow or small-window font variant.
Different aspect ratios add bars instead of stretching or rearranging the
scene. Small windows make everything proportionally smaller.

Command Link's dialogue cast uses standing canvases 716 pixels high with their
top at 146. Afterlight uses standing canvases 960 pixels high with their top at
140. Both deliberately place the dialogue over the lower body. Their separate
dialogue backings draw above the characters; manpu follow actor size.
These are authored spike values; making framing configurable is deferred in
[P19](USER_PROMPTS.md#p19), which notes the user's existing-product precedent.

The design size is independent of rendering resolution. Godot's **Canvas Items**
stretch mode with **Keep** aspect renders assets, text, and effects directly at
the window's content resolution. It avoids enlarging a previously rendered
1280×900 frame. The layout stays fixed, including proportional manpu. See
[Multiple resolutions](https://docs.godotengine.org/en/stable/tutorials/rendering/multiple_resolutions.html).

## Art record

`assets/` holds only the images and placement data the game reads. `art/` holds
the prompts, original provider images, fetched API schemas, sanitized request
records, and local preparation notes. `art/` is excluded from Godot import.

The chosen route is `openai/gpt-image-2.5/sunburst` through FAL, using PNG and
maximum quality, with transparent sprites and opaque backgrounds. The generation/edit schemas were
fetched from FAL's public OpenAPI endpoint before the first request. The edit
requests for Mira use the new standing image as the identity reference. The
current standing designs use three user-provided game illustrations as visual
style references, documented in `art/rounds/tactical-v2/REFERENCES.md`. Those
inputs remain outside runtime assets. Their characters, logos, and page layouts
are not reproduced in the new sprites.

The manual helper `art/request_image.py` submits one named request at a time,
keeps its queue ID before polling, has no automatic generation retries, and
refuses an already-recorded name. It requires both `--live` and
`STAGE_GEN_RUN_LIVE=1`. Credentials come from the repository's allowlisted
provider-key loader or the process environment and are never saved in this
project. A six-submission limit bounds each explicitly authorized preparation
round. The initial set used four submissions. The user's request to regenerate
all assets starts the separate `tactical-v2` round, with its own documented
opt-in. This helper is an experiment record, not a proposed generation service.

The superseded initial three images passed independent review for this local prototype in
`art/REVIEW.md`. The closed-eye image is a manual composite of the generated
eye regions onto the original image: every pixel outside the eye mask is
unchanged, so blinking does not move the body or redraw the clothing. Exact
preparation details and hashes are in `art/preparation.json`.

Lena's initial additional standing image used Mira's original image only as a style
and framing reference. She is a distinct character with long blonde hair and
a burgundy outfit, authored as age 21. Her prompt is
`art/prompts/second-standing.txt`; the original output and sanitized provider
record are retained beside the initial requests. Her independent review is
`art/REVIEW-second-actor.md`. She has no pointing or additional motion frames.

The current complete replacement set is recorded under `art/rounds/tactical-v2/`:
`prompts/` contains all four final generation instructions, `records/` contains
sanitized FAL request records, and `REVIEW.md` records independent visual
acceptance. The new blink registration and fingertip measurement are specific
to this set; the initial preparation script's coordinates are historical.
`art/ACTIVE.json` maps the four installed sprites to that review. Four requests
completed for this revision. Runtime texture filtering uses mipmaps to keep
the detailed hair and costume highlights smooth when the sprites are scaled down.

Sera's additional standing sprite is recorded in `art/rounds/third-actor-v1/`.
One FAL request reused all three preserved user references plus the current
Mira and Lena standing images for style and framing consistency. Its prompt,
reference basis, sanitized provider record, and independent exact-hash review
remain in that round. `art/THIRD_ACTOR_ACTIVE.json` binds the fifth character
PNG, `assets/character_third_standing.png`, to that review. The installed image
is a byte-identical copy of the generated transparent PNG.

Sera was added for a three-character presentation demonstration. The later
hologram experiment adds an actor shader effect. The dedicated Character Exit
demo compares a color-to-silhouette departure with an ordinary opacity fade;
the main briefing now uses Silhouette Fade within its authored cast handoff.

## Playing Command Link

The window title is **Command Link**. You command Mira, Lena, and Sera in a
near-future coastal defense squad preparing an evacuation escort. The briefing
begins at Forward Command with Lena left and Mira right; Sera is initially
offstage. Choose whether the reserve team protects the convoy
or helps restore its dark relay beacon; a later line remembers that order.
Your second decision visits Perimeter Overlook first or goes directly to
Coastal Staging. Both approaches reach the deployment apron and an ending.

Lena's three-line briefing receives an authored close-up: the whole scene moves
closer on her first line and holds through the next two. Mira's order prompt
returns wide, and choices become available when that move finishes. Camera cues
are deliberate story direction; speaking turns do not automatically move the
camera.

After your first order, Lena says she will scout ahead. Advance her departure
line to let the handoff play: Lena fades through a black silhouette and leaves,
Mira moves into the left position, then Sera fades and moves into the right.
Dialogue waits until all three phases finish, then Sera continues the briefing.
The first outdoor establishing shot restores the full squad while characters
are hidden, so subsequent scenes reveal the ordinary three-person framing.

Use **Next**, **Space**, or **Enter** to advance, then choose a displayed order.
Mira's close reach pose is part of the mission: touch or click her fingertip to
pair your command link with the squad channel. The story waits for that contact,
then acknowledges the link and restores **Next**. A miss does nothing. The ending
offers **Begin again**, which resets the briefing, orders, and connection.

Entering a new place first shows its background without characters or dialogue.
The view gently pans and zooms to the ordinary framing; Coastal Staging also
adds a temporary lens flare from its painted sun. **Skip view**, **Space**, or
**Enter** completes this introduction and reveals the held dialogue beat.
The active speaker receives a small vertical bounce; listeners stay bright.
Normal character rendering, Mira's automatic standing blink, and shaking manpu
remain part of the story. Technical tuning controls live in the demos.

**Menu** or **Esc** pauses the mission. **Continue briefing** restores the beat,
orders, connection, location, and any partial camera move, establishing shot, or
cast handoff after visiting demos. **Start a new briefing** resets the story.
Continuation is held only in memory for the current process; there is no disk
save. **Esc** from the menu also returns to the story.

## Feature demonstrations

Presentation Lab owns these routes. Its Command Link collection opens a
separate scene for each feature. **Demos** or **Esc** returns to that collection;
**Play** returns to the paused Command Link story, or
starts it if none has been played. **Reset** or **R** resets the current demo
without changing its route. Demo settings do not alter the saved story or carry
into a different demo.

| Route | Demonstration and controls |
| --- | --- |
| `demos/characters` | Mira's standing and matched eye states. **Close/Open eyes** or **B**; **Auto blink** or **N**. |
| `demos/contact` | Click or touch Mira's offered fingertip for a ripple and acknowledgment. **Show/Hide target** or **H** displays the hit area. A miss does nothing. |
| `demos/dialogue` | An eleven-line tactical exchange with all three actors and speaker emphasis. **Next**, **Space**, or **Enter** advances; **Read again** returns to its start. |
| `demos/actor_focus` | Compare Actor Focus presets with **P**, replay the cue with **F**, or advance the speaker with **Next**. **Reset** restores Bounce. |
| `demos/character_exit` | **T** selects an actor, **P** selects the next exit preset, **E** exits, and **S** shows the actor again. **Reset / R** restores the demo. Sera is selected initially. |
| `demos/cast_transition` | **P** selects the handoff pattern, **C** selects the motion curve, and **Run / E** starts it. Sliders tune the curve, duration, and travel. **Reset / R** restores the original cast and default settings. |
| `demos/manpu` | Per-line reactions with independent introductions. **P** cycles the animation preset, **T** selects a replay target, and **F** replays it. **Next / Space / Enter** advances; **G** switches to the nine-mark gallery. **Reset** restores Shake. |
| `demos/locations` | Background and location-title behavior on an empty stage. **Change scene** or **L** switches places; **Replay title** or **P** repeats the current announcement. |
| `demos/establishing_shot` | **L** changes location, **E** replays, **Space** skips the view, and **F** toggles flare for the next replay. Sliders tune duration, pan, opening zoom, and flare strength while settled. **Reset / R** returns to Coastal Staging's profile. |
| `demos/dialogue_camera` | **Frame speaker / C** moves toward the current speaker; **Wide / W** returns wide. **T** changes speaker and **Next line / Space / Enter** advances without changing the held shot. Sliders set the next zoom and duration; **L** changes location and **Reset / R** restores the opening wide view. |
| `demos/hologram` | Actor selection with **T**, **Normal / Hologram** with **E**, a strength slider, and dialogue advancement. Sera starts at 90% hologram; Mira and Lena start normal. |

All other demos start with normal actor materials. The dialogue demo isolates
speaker behavior; contextual reaction marks are demonstrated in the manpu route
and used naturally in the main story.

The fingertip is measured in original image coordinates and transformed with
the displayed sprite. The close pose is currently one open-eye image; it has
no alternate expression or blinking frame. The full-body pair demonstrates
the two eye states requested for this initial setup.
The shared circular hit test and acknowledged state live in
[Point Contact](../../../games/command_link/presentation/interaction/README.md). That behavior contains no
art, input routing or visual feedback, so Afterlight can reuse it independently
of the tactical stage. The existing contact study keeps its current route.

## Ambient particles and transmission voice

P99 adds [Sprite Particle Emitter](../../../games/command_link/presentation/effects/SPRITE_PARTICLE_EMITTER.md)
under Particle Effects and [Transmission Voice](../../../games/command_link/presentation/audio/VOICE_PROCESSING.md)
under Audio Effects → Voice Processing. Afterlight demonstrates both naturally:
quiet interior dust, layered infernal smoke/embers/sparks, and filtered Eira
speech while her floating display is active. The unchanged recordings remain
revision-tracked. Dedicated Lab routes are `ambient_particles_study` and
`transmission_voice_study`, launched with `--game presentation_lab --route <id>`.
The Lab owns density, texture/preset, camera, dry/wet, strength and language
controls. Standing-cast framing parameters remain explicitly deferred.

## Radial Sprite Burst

A finite group of supplied sprites pops outward and fades. The reusable
[Radial Sprite Burst](../../../games/command_link/presentation/effects/SPRITE_BURST.md) keeps motion and
timing independent of the texture pool; the host owns placement and camera.
Afterlight uses it behind Sena during the ward repair. Presentation Lab adds
`--route sprite_burst_study` with sparkle, heart and mixed inputs, rear/front
placement, timing, overlap and world-camera controls. This pass reuses prepared
raster art. P99 separately implements sustained Ambient Particles.

## Manpu

P93 adds Sweat Drop Fall beside Sigh Puff in the same One-Shot Manpu family,
using the prepared sweat raster and downward motion/fade. Two Afterlight
story cues and the existing Lab demonstrate it.

P92 adds [Stepped Transform Loops and Sprite-Frame Loops](../../../games/command_link/presentation/manpu/README.md).
A cue can choose its own preset and ordered raster frames. Three Afterlight
story reactions loop using one existing image; Presentation Lab's Manpu study
also compares two/three supplied fixture frames in 2D and 3D. A host can supply
a custom sampling function while reusing the same channels and lifecycle.

`assets/manpu/` contains nine transparent PNGs and `catalog.json`. The original
art is a single FAL image-model generation in `art/rounds/manpu-v1/`; its eight
cells were extracted and padded as individual square PNGs without repainting
or resampling their pixels. The original atlas, prompt, provider record, and
preparation details remain in that directory.
Independent acceptance is recorded in that round's `REVIEW.md`, and
`art/MANPU_ACTIVE.json` maps the installed files to the reviewed hashes.
P70 adds a separately generated original `sigh_puff.png` from
`art/rounds/manpu-sigh-puff-v1/`. Its text-only Sunburst/max prompt, provider
receipt, raw 1024×1024 RGBA image, and independent review stay in that ignored
round. The original eight files are unchanged.

| Manpu ID | Dialogue use |
| --- | --- |
| `surprise` | Unexpected arrival or sudden realization |
| `confusion` | Puzzlement or uncertainty |
| `sweat_drop` | An awkward or nervous admission |
| `anger_vein` | Comic irritation |
| `sparkle` | Delight or admiration |
| `heart` | Affection or appreciation |
| `gloom_lines` | Dismay or dejection |
| `sigh` | Relief or resignation |
| `sigh_puff` | A brief exhalation, demonstrated as static, shaking, or one-shot |

Story beats in `games/command_link/game.gd` and the demo exchange in
`presentation/stage.gd` use explicit `manpu` arrays. A cue names its actor,
allowing a listener to react while someone else speaks. In the tactical demo
exchange, Lena's map report gives her an `anger_vein` and Mira a `sweat_drop`
simultaneously. The story authors reactions for its mission beats. Empty cue
arrays clear marks on neutral lines, and the manpu gallery shows the complete set.

The PNG artwork stays unchanged. Each newly visible `(actor, id)` pair plays
its own **Manpu Introduction** animation. The main story and manpu demo select
Shake; the available presets are Shake, Scale pulse, Fade in, and None. A pair
that remains across lines keeps its own clock even if the speaker changes.
Removing it discards its state, so a later reappearance starts afresh. Empty
cue arrays, the gallery, and restart clear active introductions. Continuing the
paused story restores its marks at their settled endings.

In the manpu demo, **P** cycles the preset for all active marks. **T** selects
**All marks** or a currently cued actor; **F** replays all marks or that exact
actor/mark pair. Choosing a preset retargets continuously from the current
appearance, so changing a visible mark to Fade in can look unchanged. Replay
starts at the authored beginning, including opacity zero for Fade in.

Manpu are in-game character elements. Their size is proportional to the actor's
drawn height (10%), with no minimum or maximum screen-pixel clamp. Their source-image
anchors keep the sigh near the mouth and gloom beside the brow. Window scaling
scales the marks and their actors together; it does not enlarge the marks
independently to preserve UI readability.
Actor Focus moves and scales the owner first; the mark then applies its own
center-pivot scale and vertical offset measured in attached-mark height. Local
mark brightness and opacity remain separate from the owner's focus color or
hologram material. The Actor Focus demo selects None for local mark animation,
so it can show the owner attachment behavior by itself.

The [Manpu Introduction contract](../../../games/command_link/presentation/manpu/README.md) and
[shared Presentation Animation contract](../../../games/command_link/presentation/animation/README.md) describe the
API, lifecycle, and data-defined tracks. This is authored scene behavior inside
the spike, with no text inference or asset-generation step during play.

**One-Shot Manpu** is an explicit event rather than a persistent dialogue cue.
Each emission snapshots its motion preset, advances on the host's clock, and
expires independently. Repeated puffs can overlap; redraw, language changes,
and persistent cue synchronization never retrigger them. Afterlight uses Sigh
Puff on Nami's resigned reply and Riko's all-clear. A scene cut cancels attached
events; an in-session story checkpoint reconstructs them from authored cue time.

Presentation Lab's `sigh_puff_study` compares static, shaking, and one-shot
uses of the same artwork. It includes pause, repeat emission, and a switch
between the 2D presenter and a real Sprite3D billboard preview consuming the
same controller samples. The billboard host owns camera-facing placement,
world units, depth, and node cleanup. This is a bounded 3D rendering example;
the shared lifecycle does not depend on a visual novel, speaker, or 2D canvas.

## Locations

The three static backgrounds are **Forward Command**, a coastal briefing bunker;
**Perimeter Overlook**, a wet fortified walkway above the convoy road; and
**Coastal Staging**, a sunny palm-fringed deployment apron. All are opaque
2048 x 1152 PNGs. Godot scales each to cover the fixed design canvas
without stretching. Window resizing preserves that same crop and scales the
whole composition. Soft scrims keep characters, manpu, and controls readable
over the painted scenery.

The story begins at Forward Command, then follows the commander's approach
choice through Perimeter Overlook or directly to Coastal Staging. Both paths
finish at Coastal Staging. **Begin again** or **Start a new briefing** returns
to Forward Command. Pausing and continuing preserves the place and shot timing.

The general feature demos select a background randomly on entry or reset.
Locations exposes **Change scene / L** and **Replay title / P**. Establishing Shot
starts at Coastal Staging and provides its own location, camera, and flare
controls. Neither route changes the paused story's location.

The **location title** briefly announces the place name and district on entry
or a scene change. After it fades, a smaller location label remains in the
header. Its timer is held during an establishing shot, then resumes as characters
enter. The Locations demo can also demonstrate the title without a camera view.

**Establishing Shot** names the scene-opening camera view; **Scene Presentation**
is the working local umbrella. The new demo and main story use the same
[Establishing Shot contract](../../../games/command_link/presentation/camera/README.md). Coastal Staging's flare follows
the painted sun through the pan and zoom, then disappears before ordinary play.
It is a procedural shader overlay; it adds no image asset or baked filtering.

**Dialogue Camera** is another Scene Presentation example. Explicit cues can
push in on an actor, hold across multiple lines, and return wide. The same 2D
pan/zoom transforms the background, cast, and attached manpu; dialogue and
controls stay fixed. Camera offsets preserve background coverage, with requested
zoom bounded to 1–4×. This uses the existing images. The
[Dialogue Camera contract](../../../games/command_link/presentation/camera/DIALOGUE_CAMERA.md) records cue ownership,
framing limits, and continuation state; the dedicated demo compares all three
actors without following speakers automatically.

`assets/locations/catalog.json` holds the spike's location IDs, display names,
details, image paths, and establishing-shot profiles. The current three prompts,
original images, sanitized FAL records, preparation, and independent exact-hash
review are in `art/rounds/tactical-locations-v1/`. Perimeter Overlook used the
existing original Mira illustration as a style reference; Forward Command and
Coastal Staging used text-only requests. The images contain no people or legible
interface text. `art/LOCATIONS_ACTIVE.json` binds the installed, byte-identical
PNGs to their local acceptance. The superseded cafe and terrace records remain
historical evidence in `art/rounds/locations-v1/`. No public gameplay contract
or production module has been introduced.

## Character visual effects

**Actor Focus** is the working umbrella for speaker emphasis. It groups a
vertical bounce, a small scale pulse, listener dimming, listener fading, and
no emphasis. The main game and dialogue demo select Bounce; the Actor Focus
demo compares all six presets, including the repeated Restless Bounce. Consecutive lines by the same actor do not
retrigger the cue. A narrator clears focus, and returning from the menu resumes
the speaker at rest.

The spike-local [Actor Focus contract](../../../games/command_link/presentation/focus/README.md) separates the
`set_focus(actor_id)` cue from the selected animation. Presets in
`presentation/focus/presets.json` supply normalized keyframe tracks for vertical offset,
scale, opacity, and brightness to the shared
[Presentation Animation sampler](../../../games/command_link/presentation/animation/README.md). Adding a preset using
those channels changes data rather than dialogue code. Manpu follow the actor's
animated position and size, then apply their independent introduction tracks;
their painted colors stay independent. Entry fades
and hologram materials continue to compose with the focus result. This is a
local interface for the POC; module boundaries and promotion remain deferred.

**Character Exit** is the working umbrella for departures in
`demos/character_exit`. Its default **Silhouette Fade** first turns the colored
sprite into a black silhouette without adding exit transparency, then fades that
black silhouette. The 0.9-second preset spends 55% on color and 45% on opacity.
**Opacity Fade** provides a comparison. Each actor keeps its own running exit;
changing the selected preset affects subsequent exits. **Show** immediately
restores the selected actor. The main story reuses Silhouette Fade for Lena's
departure within its sequential cast handoff.

The [Character Exit contract](../../../games/command_link/presentation/transitions/README.md) uses the existing texture
once, through brightness and opacity tracks from the shared sampler. Normal,
settled actors keep their original PNG alpha coverage during the color phase.
Existing entry, focus, and hologram treatments retain their separate composition
roles. This adds no artwork or shader and stays inside the spike.

**Cast Transition**, in `demos/cast_transition`, starts with Mira left, Lena
right, and Sera waiting offstage. Its default handoff makes Mira leave, then
moves Lena left, then introduces Sera on the right. Replace in place keeps Lena
right and brings Sera into the vacated left position. Every phase finishes
before the next; another Run uses the current cast.

The motion controls offer Linear, Ease in / out, and Spring, with adjustable
frequency, damping, move/entry duration, and travel distance. The live graph
samples the same translation curve as the actors. Opacity stays on separate
bounded tracks. Settings are fixed during a handoff, and Reset cancels it.
The [Cast Transition contract](../../../games/command_link/presentation/transitions/CAST_TRANSITIONS.md) records the
limits and lifecycle. Its tuning stays separate from the main story, which
uses the same controller for Lena's departure, Mira's shift, and Sera's arrival.
Both reuse existing art.

Open **Character visual effects** in Presentation Lab or route `demos/hologram` to see
Sera as a hologram beside the normally rendered Mira and Lena. This demo's
controls choose an actor (**T**), toggle **Normal / Hologram** (**E**), and adjust
strength. Each actor keeps independent settings, so more than one can be
holographic. Selecting an actor changes the control target; it does not move an
existing effect to that actor.

Hologram combines cyan tonal shading, partial transparency, fine horizontal
scanlines, a moving scan band, gentle signal fluctuation, and sparse horizontal
displacement. It uses the existing PNGs. No new artwork or audio was generated.
P83 increases line contrast and signal motion so the treatment reads on blue-toned
art. Shared actor defaults use 90% strength; Eira's framed portrait uses 70% for
readable facial detail. Both use the same shader.

Actor effect settings survive dialogue advancement within this demo. **Reset**
restores Sera's 90% hologram and normal Mira/Lena. Leaving and reopening the route
creates a fresh demo; effects do not transfer to the story or other demos. The
manpu, contact feedback, background, location label, and other controls are drawn
separately from actor materials.

The implementation uses individual actor `TextureRect` nodes and separate
`ShaderMaterial` instances sharing `presentation/shaders/character_hologram.gdshader`.
An explicit effect clock makes captures deterministic. This is a direct
character material effect; it does not read or filter the whole screen.
Zero strength uses the original sampled image with its ordinary entry and
speaker modulation. [CHARACTER_EFFECTS.md](../docs/CHARACTER_EFFECTS.md) explains
the working terms, later composition questions, and matching voice processing
requirement. It is not a module or public contract proposal.

## Local code layout

`main_games.gd` names three explicit roots: `command_link` (default),
`bishoujo_afterlight`, and `presentation_lab`. `main.gd` routes scenes and keeps
separate in-session story states. Command Link retains its own story/menu and
prepared stage profile. Afterlight's root binds assets, text, and authored
`story_beats.gd`; `story.gd` owns its episode, choices, clocks, and interface, while
`cast_stage.gd` composes the existing actor controllers with this game's geometry.

Presentation Lab binds two independent fixture collections. The Command Link
workbenches remain under `demos/`; the former Afterlight host and study scenes
now live under `games/presentation_lab/afterlight/`. Real games own no study
routes. Legacy links redirect into the lab for compatibility.

`presentation/stage.gd` is the concrete tactical presenter used by Command Link
and its workbenches. It
requires an explicit `presentation/stage_profile.gd` object before entering the
scene tree, and has no game-specific asset/cast defaults. The historical
fixture validation and capture harness now lives in `qa/legacy_presentation.gd`.
`presentation/ui/tactical_theme.gd` provides shared native control styles and typography;
the stage, story, and menu adapters compose their own panels and hierarchy.
`presentation/animation/presentation_animation.gd` supplies common track validation and
sampling; `presentation/focus/actor_focus.gd` owns speaker/listener transitions, and
`presentation/manpu/manpu_animation.gd` owns persistent actor/mark introduction
clocks and independently expiring one-shot instances.
`presentation/transitions/character_exit.gd` owns per-actor visible/exiting/hidden state and
the selected color/coverage exit preset.
`presentation/transitions/cast_transition.gd` coordinates sequential cast handoffs;
`presentation/animation/motion_curve.gd` supplies translation samples shared with its graph.
`presentation/camera/establishing_shot.gd` owns location-view timing and settings; the shared
stage frames the background and maps its source light to
`presentation/shaders/location_lens_flare.gdshader`.
`presentation/camera/dialogue_camera.gd` owns held scene framing and camera interpolation;
the stage resolves actor anchors and applies the shared world transform.
This split stays inside the disposable spike. It is not module extraction or a
proposed public contract.

See [TOPOLOGY.md](TOPOLOGY.md) for game/content ownership, camera versus screen
coordinates, current limits, and the status of the five requested feature ideas.

## Verification

Check explicit camera cues, held framing, covered world transforms, retargeting,
and save/restore with `-- --validate-dialogue-camera`. A windowed
`-- --capture-dialogue-camera` run records all three actors against all three
locations at maximum zoom, plus wide and intermediate samples.

Check camera settings, phase timing, save/restore, image coverage, and cast
isolation with `-- --validate-establishing-shot`. Use
`-- --capture-establishing-shot` in a windowed run for its fixed-time renders.
The route suite below also checks all four mission branches, mandatory fingertip
contact, the authored cast handoff, and resuming each handoff phase. Current
results and independent visual review are in [QA.md](QA.md).

Check the Actor Focus data contract, interruption behavior, and rendering
integration with `-- --validate-focus`. Use `-- --capture-focus` in a windowed
run to record fixed-time samples of its animations. `--capture-dir` selects
the output folder for either focus or route captures.

Check the new router, story, and dedicated demo routes with:

```sh
Godot --headless --path godot/games/playground -- --validate-routes
```

Capture the new playable and demo routes in a windowed run with:

```sh
Godot --path godot/games/playground -- --capture-routes
```

Run results and visual acceptance are recorded in `QA.md`. These commands are
separate from the older private presentation-stage checks below.

The legacy `--validate`, `--capture-state`, and `--capture-all` options dispatch
directly to that private harness, rather than the story or demo routes:

```sh
Godot --headless --path godot/games/playground -- --validate
```

This includes viewport-routed mouse and touch events under window scaling and
letterboxing, misses outside the fingertip, rejection while the character is still
invisible, blink switching, and restart. Dialogue checks cover all three actors'
framing, control placement, speaker changes, button and keyboard progression,
and isolation from the fingertip interaction.
Manpu checks cover the PNG catalog, actor and mark references, speaker/listener
and simultaneous cues, clearing, placement, and gallery layout.
Location checks cover the catalog and opaque images, cover scaling, random
selection, input routing, title timing and repeated changes, text fit, and
preserving dialogue and manpu across a location change.
Hologram checks cover actor/material isolation, target and toggle controls,
strength, state persistence and reset, layering, and deterministic timing.
Actual windowed captures are needed to verify shader output.
Scaling checks distinguish physical window dimensions from the fixed logical
canvas, verify the output transform, and keep manpu proportional to characters.

Legacy windowed captures can be reproduced with:

```sh
Godot --path godot/games/playground -- --capture-all
```

The images go to `captures/`; use `--capture-dir <absolute directory>` to
choose another directory. These PNGs now record the rendered content resolution;
the layout remains a logical 1280×900 canvas. Adjacent JSON records state both
sizes, output scale, and letterbox offset. Bars outside the content are excluded
from the render capture. Older fixed-resolution captures remain historical evidence.
Single states use `--capture-state full_body`,
`blink`, `reach_out`, `connection`, `debug`, `dialogue_mira`, or `dialogue_lena`.
`dialogue_sera` shows the third actor's speaker turn with all three visible.
The manpu examples include `manpu_gallery`, `manpu_surprise`, `manpu_listener`,
`manpu_both`, `manpu_clear`, `manpu_gloom`, `manpu_sigh`, `manpu_heart`, and
`manpu_confusion`.
Historical capture aliases `cafe_title`, `cafe_settled`, and `cafe_midfade` now
use Forward Command; `terrace_title` and `terrace_settled` use Perimeter Overlook.
The midfade state records the announcement halfway through its entrance.
For other capture states, add `--location forward_command`,
`--location perimeter_overlook`, or `--location coastal_staging` to choose the
current background deterministically.
Effect states include `effect_normal`, `effect_zero`, `hologram_sera`,
`hologram_sera_later`, `hologram_mira`, `hologram_lena`, `hologram_blink`,
and `hologram_contact`.
The capture run validates input
before recording and exits on completion. Headless rendering cannot produce
these pictures.

Independent visual review and runtime checks are recorded in `QA.md`.
Local use in this prototype does not authorize media publication or promotion.

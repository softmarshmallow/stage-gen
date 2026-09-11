# Current implementation and open items

Updated 2026-09-11 through [P116](USER_PROMPTS.md#p116), against the local source,
prepared-asset catalog, prompt archive, and recorded verification. P79 performed
the full archive audit; subsequent passes keep this inventory current. [REQUESTS.md](REQUESTS.md) records outcomes at each historical
pass; an old “deferred” entry may have been completed by a later request.

P108 adds the [agent handoff](HANDOFF.md); P107 implementation is complete and
there is no newly authorized feature pending. Runtime behavior is unchanged.
P109–P114 propose the [post-promotion topology](../../../docs/research/game-presentation-sdk-topology.md):
one `godot/` monorepo of `packages/`, `templates/` and `games/`. Unratified; nothing has moved.

P101–P106 establish the code-first direct-successor direction and the
[SDK design](../../../docs/research/game-presentation-sdk-design.md), with
[complete historical request triage](../../../docs/research/game-presentation-sdk-triage.md).
P107 implements a self-contained [Godot addon](addons/game_presentation/README.md),
a standalone source-only starter, and explicit resource/raw-file content loading
for both examples and Lab fixtures. Runtime controllers are moved directly,
with one maintained implementation; stories, UI and prepared recordings stay
host-owned. The current package is canary, not a published stable release.
Scenario remains experimental; legacy standalone point-and-click compatibility
is excluded. No anatomy annotation, standing framing calibration, legacy-game
deletion or generation-pipeline migration is included. See [packaging](PACKAGING.md)
and [verification](QA.md#sdk-package-and-content-boundary-p107).

[P80](USER_PROMPTS.md#p80) adds a particle taxonomy proposal; implementation
status is unchanged by P80. P81/P82 add Eira's dedicated framed transmission scene.
P83 strengthens the shared hologram treatment, with 90% actor and 70% framed-feed defaults.
P84 adds a configurable Waking Eye-Opening variant: quick peek and blink before
the full opening, demonstrated in the initial Nami recovery shot and eye study.
P85 strengthens the Keeper encounter through Afterlight's existing effect
profiles and cue intensities, with stronger heat, red aura/mist and finite impacts.
P86 anchors corruption patterns/ember flecks to the final world camera; P87
uses the waking blink for the character-free hall reveal and Nami's return shot.
P88 adds Radial Sprite Burst with interchangeable texture inputs, a story cue,
and a dedicated Lab study.
P89 adds Background Blackout: a selective scenery fade beneath a fixed actor,
held until restored, with a solo warning shot and dedicated Lab controls.
P90 adds Quick Approach as an Actor Blocking preset: Yuzu moves toward Sena
during a reply. The existing Actor Motion study exposes direction, stopping
distance, duration and curve; there is no additional route or shared module.
P91 adds Cast Pan: a group translation that frames the selected character over
fixed scenery while preserving local blocking. Three relay turns and a dedicated
Lab study use the target-neutral Layer Pan sampler with explicit cue settings.

P92 adds per-cue Manpu loops with held transforms, supplied sprite frames,
and optional custom sampling. Three story reactions reuse existing art; the
expanded Manpu Lab retains its route and demonstrates both 2D and 3D playback.

P93 adds Sweat Drop Fall as another data preset in One-Shot Manpu. Two late
story reactions emit the existing sweat raster downward after text reveal;
the same Lab selects sigh or sweat. No controller API changes are needed.

P94 adds Nami's dedicated reach pose and a fingertip-contact beat after the
waking return. Point Contact shares the circular hit test and acknowledgement
state already used by Command Link; [its contract](presentation/interaction/README.md)
keeps readiness, feedback, image coordinates and story progression with each
host. The new local asset passed independent review; the single request cost
$0.2822 under this pass's fresh $5 budget. Native input and continuity checks
pass at both window resolutions; no user quality approval is inferred from
implementation.

P95/P96 add English/Korean character voice policy and prepared-recording
bindings through the existing Text Reveal Audio presenter. The episode remains
57 beats: 58 unique story text IDs per language resolve to 40 voiced character
lines and 18 intentionally unvoiced protagonist lines. Four localized choice
labels, menus, and technical demos are excluded. Fourteen sparse speech scripts
add delivery tags without changing approved display text. Generation is a
separate one-time manual pass; later changes report stale recordings and wait
for an explicit refresh request. The batch prepared 80 recordings in 81 returned
attempts, with one technical retry and zero final generation failures. Its
7,174 submitted text characters correspond to $0.7174 at the verified published
API rate; receipts report 3,946 subscription credits separately. All 80 clips
pass decoding and binding checks; native playback, pause/resume, language,
Lab continuity and both-size full-story checks pass. Removed-line annotations
remain inactive and appear in the offline status report. No listening verdict
has been performed. See the [pass report](games/bishoujo_afterlight/voice/GENERATION_REPORT.md)
and [playback evidence](qa/voiceovers/REVIEW.md).

P97 adds optional Afterlight autoplay through a persistent top on/off button.
It starts off, waits until text, finite cinematic motion and voice playback
finish, then holds for 3 seconds before continuing. The courier's choice has
an authored `help_first` default and a visible 5-second countdown. Choices
without a default, explicit `require_input` gates and fingertip contact
wait for real input; the ending turns autoplay off. Pause freezes the delay,
manual actions and language changes reset it, and Lab checkpoints preserve
eligible elapsed time. Three paired UI labels bring the text sets to 288 keys;
the story and its 80 current recordings are unchanged. See the
[host autoplay contract](games/bishoujo_afterlight/AUTOPLAY.md).

P99 completes **Ambient Particles** under **Particle Effects → Sprite Particle
Emitter**, and **Transmission Voice** under **Audio Effects → Voice Processing**.
Afterlight binds quiet dust in both lounges, cool dust in the relay, and layered
smoke, embers and sparks in the Keeper hall. These sprites use the world camera,
including shake/zoom, and sit below actors, blackout and UI. Their explicit clock
reconstructs across pause/replay/Lab visits. Eira's existing recordings receive
host-selected transmission filtering while projected; protagonist typing and
physical voices stay dry. Twenty-four new paired Lab labels bring the text sets to 312 keys, preserving
all 288 prior values. Two independent Lab studies expose atmosphere presets,
density, camera, dry/wet, strength and language. Texture replacement is part
of the emitter contract and its focused checks. No source audio,
spoken text, art, generation or provider spend changes. Only standing-cast
framing remains on the concrete unimplemented-request list.

P100 adds a [canonical anatomy/visual-geometry proposal](../../../docs/research/actor-anatomy-visual-geometry.md)
with incumbent audit, foundation comparison, illustrative missing-data contract,
and a proposed VLM-only accuracy evaluation. It is unratified and changes no
runtime, asset metadata or generation path. Standing framing remains deferred.

## Current playable project

| Host | What is present |
| --- | --- |
| **Command Link** | Tactical commander-led story, three actors, player choices, required fingertip contact, and a looping video opening with explicit click/tap entry. Two generated opening edits exist; the selected `command-link-a` is wired. |
| **Bishōjo: Afterlight** | *The Address Beyond*: 57 authored beats, four heroine introductions, ward repair, the later Keeper encounter, and return. A six-turn solo call introduces researcher Eira inside a floating framed transmission display. One two-option choice reconverges. Five black intertitles carry the courier's thoughts. Nami offers a fingertip after the waking return. Optional autoplay has an authored choice default and mandatory-input gates. English/Korean have 312 matching text keys and 60 paired review rows; voice policy covers 40 character lines and 18 intentional protagonist skips per language. |
| **Presentation Lab** | Independent host with 24 focused studies (11 tactical, thirteen Afterlight), plus three navigation menus. These include alternate eye transitions, actor motion, looping/one-shot manpu with a 3D billboard example, ominous fields, Radial Sprite Burst, Background Blackout, Cast Pan, Ambient Particles, and Transmission Voice. Study UI stays out of the actual stories. |

[main_games.gd](main_games.gd) registers three roots. `dating_sim` is a legacy
alias for Afterlight, not a fourth game or a dating-system implementation.
Each game has a discoverable root and supporting direction/presentation files;
UI belongs to its host. This remains a standalone experiment inside Git.

Afterlight binds thirteen active prepared images: four heroine standing sprites,
Nami's close/detail/contact portraits, the Keeper, Eira's portrait feed, and four interiors. The Keeper's
**Hall of Unclaimed Names** is the dedicated infernal setting. Its background
switch occurs behind the `between_addresses` intertitle; the return restores
the reading room. P94's new contact image is an unchanged copy of its reviewed
source; the [review](art/rounds/afterlight-contact-v1/REVIEW.md) records the
fingertip landmark, cropped hood headroom and baked glow limitations.
The hall source is 1496×1051; larger windows enlarge that image. Native window
rendering does not create additional source detail.

## Implemented presentation inventory

These are capabilities, presets, and authored uses, not a list of ratified
modules. [TERMINOLOGY.md](TERMINOLOGY.md) defines their meanings and examples;
[TOPOLOGY.md](TOPOLOGY.md) identifies their owners and contracts.

| Area | Implemented scope and evidence |
| --- | --- |
| Dialogue and narrative | Explicit reveal/advance, Intertitle, monologues, reconverging choice, ready dot, host-owned edge-gradient UI. [Narrative controller](presentation/narrative/INTERTITLE.md), [Afterlight story](games/bishoujo_afterlight/story.gd). |
| Autoplay | Optional top toggle, completion-aware reading delay, authored default-choice countdown, mandatory-input stops and end shutdown. Afterlight owns timing, controls and checkpoint state. [Host contract](games/bishoujo_afterlight/AUTOPLAY.md). |
| Text and language | Stable Text Set keys, fallback lookup, in-place English/Korean switching, language-specific voice binding hooks. [Text Set](presentation/text/TEXT_SET.md), [paired story](games/bishoujo_afterlight/text/STORY_REVIEW.md). |
| Text audio and localized voice | Built-in typing sound, supplied recording playback, `auto`/`typing`/`silent` policy, pause/interruption and revision-aware voice resume. Afterlight's ready voiced lines show full subtitles; explicit `none` retains the typewriter and fallback. The host distinguishes `none`, `pending`, `missing`, `failed`, `stale`, and `ready`. [Playback](presentation/narrative/TEXT_REVEAL_AUDIO.md), [host policy](games/bishoujo_afterlight/voice/README.md). |
| Actor focus and animation | Shared scalar tracks, Speaker Bounce, scale pulse, listener dim/fade, none, and Restless Bounce. [Animation](presentation/animation/README.md), [Actor Focus](presentation/focus/README.md). |
| Character exits and handoffs | Opacity Fade, Silhouette Fade, left/right Walk-Away, sequential exit/reposition/entry, configurable translation curves including spring. [Character Exit](presentation/transitions/README.md), [Cast Transition](presentation/transitions/CAST_TRANSITIONS.md). |
| Actor blocking | Quick Approach moves a visible actor toward another and holds the closer position. The concrete cast adapter reuses Motion Curve with host-owned target resolution, world distance and time. [Host contract](games/bishoujo_afterlight/ACTOR_BLOCKING.md). |
| Layer framing | Cast Pan shifts the cast and attached presentation together while background/UI stay fixed; local actor spacing is preserved. Targets, anchor, duration, curve and held/reset behavior are authored. [Layer Pan](presentation/animation/LAYER_PAN.md), [host composition](games/bishoujo_afterlight/CAST_PAN.md). |
| Manpu / emanata | Nine raster marks, static/introduction presets, stepped transform and supplied-frame loops, an optional external sampler, independent one-shot instances, Sigh Puff and Sweat Drop Fall motion/expiry with after-reveal story timing. A separate 3D billboard host proves the transient lifecycle outside VN staging. [Manpu](presentation/manpu/README.md). |
| Actor art and contact | Mira's registered open/closed sprite blink and camera-facing fingertip target with pointer/touch interaction. Shared Point Contact handles hit testing and acknowledgement. Nami's dedicated reach pose supplies Afterlight's post-return contact moment alongside her existing close/detail portraits. Native target alignment and input gates pass at both window resolutions. [Contact contract](presentation/interaction/README.md), [Afterlight bindings](games/bishoujo_afterlight/root.gd). |
| Camera direction | Dialogue Camera close-ups, background-only Establishing Shot, Walking Approach push-in/bob, Camera Drift, coverage-preserving Impact Shake. [Camera contracts](presentation/camera/README.md), [drift](presentation/camera/CAMERA_DRIFT.md), [shake](presentation/camera/IMPACT_SHAKE.md). |
| Background transitions | Background Blackout fades scenery to complete black, holds, and restores it while the actor stays unchanged. Solo Yuzu story direction and a dedicated Lab example. [Contract](presentation/transitions/BACKGROUND_BLACKOUT.md). |
| Eye transitions | Eye-Opening, Eye-Closing, Blink, Waking Eye-Opening with adjustable peek duration/depth, independent timing, and Edge Feathering. This mask is separate from a character blinking. [Eye Transitions](presentation/transitions/EYE_TRANSITIONS.md). |
| Character visual effects | Holographic Projection, Eira's game-owned Framed Transmission Display, and alpha-based Actor Halo. Portrait Detail Shot is authored composition; the requested black silhouette was revised to a cropped chin/upper-torso shot. [Character effects](CHARACTER_EFFECTS.md), [Halo](presentation/effects/ACTOR_HALO.md). |
| Ambient particles | Sustained seeded sprites with explicit rate/lifetime, drift, spin, fade, supplied texture pools, warmup and stop/drain. Quiet interior dust and layered infernal smoke/embers/sparks demonstrate world-space camera attachment. [Emitter contract](presentation/effects/SPRITE_PARTICLE_EMITTER.md). |
| Voice processing | Private runtime bus with band filtering and gentle distortion, tunable strength and exact bypass. Eira’s projection state selects processing; typing and other voices remain dry. [Contract](presentation/audio/VOICE_PROCESSING.md). |
| Sprite emission | Radial Sprite Burst: finite seeded sprite groups, configurable outward dispersion/pop/fade, interchangeable textures and explicit world camera. Story repair cue and independent Lab layering/texture examples. [Contract](presentation/effects/SPRITE_BURST.md). |
| Scene and screen effects | Location announcement, Lens Flare, Refraction Field, Heat Haze, Ominous Corruption for sprite alpha, area or screen, procedural noise and optional reusable noise/mask input. [Screen fields](presentation/effects/SCREEN_FIELDS.md). |
| Opening video | Replaceable OGV playback, looping fade-through-black, missing-video fallback, and click/tap-only entry in Command Link. [Opening](assets/opening/README.md). |
| Composition and continuity | Fixed 1280×900 logical canvas with native-resolution rendering, proportional actors/manpu, screen-space UI, coverage bounds, pause and per-game in-session checkpoints across lab visits. [Topology](TOPOLOGY.md), [verification record](QA.md). |

## Requested work still unimplemented

| Item | Request | What is already done; what remains |
| --- | --- | --- |
| **Standing-cast framing parameters** | [P19](USER_PROMPTS.md#p19), explicitly later | The requested larger/lower staging is implemented. Tactical placement and Afterlight standing height/top remain authored constants. A reusable configurable standing-framing profile is explicitly deferred again by P99; camera and dedicated portrait parameters already exist. |

All original five requests now have implementations. **#4 Ambient Particles**
was completed in P99. Original items **#2 Walking Approach**, **#3 Camera Drift with Portrait Detail
Shot**, and **#5 Intertitle/monologue** are complete. P63 revised #3 away from
a literal black silhouette; that discarded direction is not an unfinished effect.
P95/P96 take original **#1 TTS voiceover** out of deferral with scoped character
recordings and host-owned policy. Its current generation/verification pass is
tracked above; automatic future synchronization is deliberately not requested.

## Recorded possibilities and separate future work

| Item | Status |
| --- | --- |
| Actor anatomy and visual geometry | [P100 canonical proposal](../../../docs/research/actor-anatomy-visual-geometry.md) delivered. Vocabulary ratification and a separately authorized VLM-only evaluation remain open; runtime, annotation and generation integration are explicitly deferred. |
| Scene defocus during waking; generated organic eyelid edge mask | Optional directions discussed around [P50](USER_PROMPTS.md#p50). Neither exists. The requested edge-softening work was delivered as feathering; these are not pending requirements from that pass. |
| Image-model/asset-based UI automation | Future possibility in [P27](USER_PROMPTS.md#p27). Current code-authored, host-owned UI fulfills the requested prototype work. No shared skin framework is required. |
| SDK package, starter and direct-successor implementation | P106 delivers the [SDK design and taxonomy](../../../docs/research/game-presentation-sdk-design.md). Design acceptance, portable packaging, external content adapters and fresh-project/export proof remain future implementation work; no public package or runtime migration has occurred. |
| Historical promotion proofs | P102–P106 supersede the old mandatory room/prop, second-genre and incumbent-Scenario comparison gates. Independent SDK installation and preservation of Afterlight's behavior are the proposed practical checks; no new room engine or Scenario parity is required. |
| More techniques/effects mentioned but not supplied | P02 mentioned roughly twenty; P38 mentioned five to ten further ideas. Only concrete later requests are tracked as implementable work. No unseen list can be reconstructed. |

## Scope limits, not missing requests

- Fingertip contact is the point-and-click proof here. A general room exploration,
  inventory or puzzle engine was not delivered or promised as part of this spike.
- The opening request was fulfilled in Command Link. Afterlight has no separate
  video opening configured; that is not an unfulfilled Afterlight request.
- Game checkpoints are in-session, not durable cross-version save files.
- Prepared media remains ignored and local. Git contains source and records;
  a fresh checkout requires the local assets. Publication is not authorized.
- Desktop checks do not constitute mobile/export performance or production
  contract validation. Art-review and media-budget details remain in the catalog
  and local provenance; this audit does not invent new user quality approvals.

## Audit and maintenance

P01–P106 have one-to-one prompt/ledger/SDK-triage coverage, with no duplicated IDs or missing
actionable request found in the visible conversation. P106 reviewed every record
and the implemented mechanism boundaries without rerunning gameplay. Formatting and attached
reference filenames are described in the archive. Stale current claims about
missing Impact Shake/audio playback, two monologues, the old episode title,
two roots and tactical-only global UI/art have been corrected. Historical
promotion/readiness and QA documents retain their original evidence and dates.

P79 checked documentation links, language-key and paired-story consistency,
active artifact digests and source bindings without rerunning gameplay. P81/P82
add the dedicated Eira scene and its framed portrait display. The final 56-beat
episode passes headless and native checks at 1280×900 and 2560×1800, with 40
captures, six call-turn language/Lab round trips, contained portrait framing,
and display cleanup. See [QA.md](QA.md) for evidence and practical limits.
The two earlier P81 images are inactive drafts; the 12 active Afterlight images
and prior approved art retain their catalog digests. There are 284 matching
English/Korean keys and 59 paired episode text rows.
P83's focused native checks verify stronger TV defaults on both tactical actors
and Eira's framed portrait at both resolutions, with exact strength-zero bypass,
alpha-outline confinement, independent controls, and no changes outside the
intended treatment. The shared shader uses the existing source images.
P84's controller and focused native story/lab checks cover the waking sequence,
pause/language/menu restoration at each active phase, all four modes, and
independent tuning/reset at both resolutions. Sixteen captures document the
peek, closure, reopening and open frames; the existing mask shader is unchanged.
P85–P87 add stronger encounter direction, world-bound procedural ember flecks,
and waking reveals for both realm transitions. Thirty final native encounter
captures and a separate six-capture pattern fixture pass at both resolutions.
The fixture proves translation/zoom attachment with exact sampled RGB alignment;
host checks cover active shake, pause/language/Lab restoration and clean return.
The recovered ensemble remains pixel-identical to the earlier clean scene.
An independent visual review accepts the stronger atmosphere and clear held
facial features. General Ambient Particles was still unimplemented at P85–P87; P99 completes it.
P88 adds five passing Sprite Burst controller groups and 36 native captures
covering the authored event, world translation/zoom, opacity fade and Lab controls
at both scales. Active pause/language/Lab restoration and early cancellation pass;
the full 56-beat headless episode still passes. Sprite artwork changes preserve
the same sampled motion and lifetime. The 19 new Lab labels have paired English
and Korean values; episode wording is unchanged.

P89 adds Background Blackout with a solo Yuzu story cue and a dedicated Lab
study. Controller and native checks verify exact black scenery, continuous
fade/restore, unchanged actor geometry/material and explicit timing at both
scales. Pause, language switching, Lab detours and interruption preserve the
intended state. The full 56-beat headless episode passes. Seven new Lab labels
have paired English/Korean values; episode wording remains unchanged. See
[QA.md](QA.md) for the source-alpha compositing limits and rendered evidence.

P90 adds Quick Approach within Actor Blocking using the existing Motion Curve.
Focused cast checks and 12 native story/Lab captures verify held positioning,
stationary recipients, manpu/camera attachment, pause/language/Lab continuity,
early cancellation and both approach directions. The full 56-beat episode and
earlier motion modes pass. Ten paired Lab labels expose tuning without changing
episode wording or the 21-study route count. [QA.md](QA.md) records the evidence.

P91 adds Layer Pan sampling and the Cast Pan host composition, demonstrated in
three relay turns and a new Lab study. Fourteen native captures at both scales
verify fixed background pixels, preserved local blocking, group framing and
manpu attachment, active pause/language/Lab continuity, retargeting, cleanup and
composition with Quick Approach. The full 56-beat episode passes. Eight paired
Lab labels bring the text sets to 274 keys; episode wording is unchanged. The
Lab at P91 has 22 studies; P99 adds two more. [QA.md](QA.md) records the evidence and limits.

P92 adds looping Manpu with held transform steps, supplied raster-frame sequences,
and an optional external sampler. Three story reactions reuse existing sprites.
Controller, legacy focus/exit, and one-shot checks pass. Fourteen native captures
at both scales verify raster selection, centered rotation, world attachment,
loop/event independence, pause/language/Lab restoration and a camera-facing 3D
preview. The full 56-beat headless episode passes. Seven new paired labels bring
the current text sets to 281 keys, with no episode wording or route-count change.
[QA.md](QA.md) records the checks and remaining evidence limits.

P93 adds Sweat Drop Fall as a data-only One-Shot Manpu preset, with Sena/Riko
story emissions and a selector in the existing Lab. Six native captures at both
scales verify downward movement, raster binding, expiry, concurrent sigh/loop
behavior, pause/language continuity and the angled 3D view. Controller and legacy
Manpu checks pass, as does the full 56-beat headless episode. Three paired labels
bring the text sets to 284 keys; all 59 review rows and episode wording remain.
[QA.md](QA.md) records the scoped evidence.


P94 extends the episode to 57 beats with 285 matching English/Korean keys and
60 paired text-review rows. The thirteenth active image is Nami's independently
reviewed reach pose. Point Contact, existing tactical composition and all four
Command Link route branches pass their focused regression checks. The full
57-beat Afterlight episode passes headless at both scales; six native captures
at 1280×900 and 2560×1800 verify target alignment, mouse/touch, misses and Space
gating, one confirmation, the 0.45-second feedback, pause/language/Lab continuity
and cleanup. Root visual review accepts the ready and feedback compositions.
See [QA.md](QA.md) for the recorded evidence and headless environment warnings.
The P94 request cost $0.2822, leaving $4.7178 of its separate $5 budget.

After each feature pass, keep this inventory and the open-item status aligned
with the source, add the exact request and outcome to the historical ledger,
and update the terminology/contract and paired story only where affected.

```sh
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/godot/games/playground -- --game bishoujo_afterlight --language ko
```

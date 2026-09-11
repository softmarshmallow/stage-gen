# Game Presentation Kit verification

Updated: 2026-09-11. Earlier sections retain evidence from their own revisions.

## SDK package and content boundary (P107)

The direct successor is now one canary addon, with a source-only starter and
unchanged example stories. This pass makes no provider calls and regenerates no
art or speech. It does not supply a new listening verdict or publish a release.

- Package closure: 37 source/resource files, 13 literal dependencies entirely
  inside the addon, complete unique source UID sidecars. A fresh editor import
  completed with no script errors. Local editor-settings/log-write warnings are
  environment output, not gameplay or import assertions.
- Existing behavior: 21 focused headless/controller and Command Link route suites
  pass. One Walk-Away check still expected five channels after P92 added rotation;
  it now verifies the actual six-channel contract and preserved source sample.
  Runtime animation was unchanged by this correction.
- Native VFX: Actor Halo, corruption world coordinates, hologram defaults and
  Ominous VFX suites pass, including 1x/2x framing, bypass/instance isolation,
  source-alpha behavior, distortion ordering and background coverage.
- External content: Command Link tests use independent synthetic actors, WebP
  scenery/Manpu, contact JSON and raw OGV. Looping and explicit-click entry,
  missing-video fallback and path rejection pass. Afterlight tests compare exact
  default/external pixels and mipmaps, all 80 MP3 bytes/revisions and 36 deliberate
  no-voice entries; invalid roots, missing text and escaping catalog paths refuse.
- Full host: external-content Afterlight completes all 57 beats at both logical
  scales; ambient/transmission integration, localized voice policy/playback,
  autoplay and required-contact gates pass. Existing composition and independent
  Lab round-trip checks pass. EN/KO display text and prepared recordings are unchanged.
- Native voice playback: external EN/KO recording output produces measured mixer
  frames (77,312 EN; 122,368 KO), with full-subtitle and paused captures at both
  sizes. The final native run reports no script errors or leaks. No listening
  approval is inferred from decoding, mixer measurements or screenshots.
- Content copying: eight provider-free tests cover exact bytes/provenance,
  exclusion of scripts/imports, refusal of overwrites, escaping/symlink bindings,
  and missing recordings without a partial output directory. The prepared local
  example-content copy contains 215 files; no generation working tree is copied.

Native required contact also passes with real mouse/touch events at 1280x900
and 2560x1800, including language/pause/Lab continuity before and after a single
confirmation and explicit replay/restart. Root independently inspected the new
Korean contact-ready capture and the starter choice capture: text and interaction
targets remain readable; no fresh art review is claimed.

The credential-free repository gate executed all 30 steps. Its initial run passed
27 steps: two formatting/lint findings in the new package checker were corrected,
and the Python source-archive text ceiling was updated after inspecting the added
anatomy/SDK research documents. The 2,829 passing tests and one initial archive
failure were followed by nine passing focused package/starter tests; all formatting
and lint checks then passed. The archive check now explicitly excludes this Godot
workspace from both Python distributions. Mypy, web checks, generated-run Godot
suite, build, documentation, package validation and dry-run CLI steps passed.
A further 108 focused documentation/rights/packaging checks passed, plus eight
example-content copier checks. SDK-owned Python checks stay under `qa/python/`,
because their implementation is deliberately absent from the Python sdist.

The final standalone assembly contains 73 byte-identical SDK files and nine
starter files. It imports and completes both story branches, mandatory contact,
pause, camera/Manpu composition, audio precedence and burst checks at native 1x/2x.
Its 177,468-byte exported PCK also completes the flow in both headless and native
Godot outside the checkout. This proves pack export with the installed engine,
not a standalone native executable. The six starter-assembly tests pass at their
final scoped path, `qa/python/test_starter_assembly.py`.

The starter's final assembly/export report lives in `qa/sdk-package/` when these
local checks are run; content and voice regressions live under `qa/sdk/content/`.
Those outputs are ignored QA artifacts. Reproduction commands are in
[packaging](../docs/PACKAGING.md), the [starter](../../../templates/vn/README.md), and
[SDK content checks](../tests/SDK_CONTENT_CHECKS.md). Code/API and source UIDs are tracked
source; no export product, cache or generated example media is part of the addon.

The package remains bounded to the documented desktop Compatibility baseline,
2D transform contract and existing cast-transition slots. P100 anatomy/VLM
annotation, standing framing and Scenario integration remain deferred. Complete
native executable/export-template coverage and a stable/public release are not
claimed by a PCK check.

## Opening video

P30/P31 add a default opening route with a replaceable Ogg Theora clip, code
title, and one Begin Briefing control. The local placeholder derives from the
existing coastal background. There were no provider calls or production edits.

Native OpenGL smoke checks passed: decoded 1280×720 frames and advancing video
clock, aspect preservation on the 1280×900 canvas, natural completion,
button/background/keyboard/touch skip, ignored key repeats, no skip input
advancing the first story beat, menu resumption, and missing-video fallback.
Evidence: [smoke result](../../../games/command_link/tests/opening/smoke.json) and
[native title capture](../../../games/command_link/tests/opening/title.png). This pass did not verify export
packaging or audio, and did not exercise the stalled-decoder timeout.

The existing native route suite also passes all four mission branches,
required fingertip contact, handoff/resume, scene and choice gates, replay,
menu/demo links, and scaled input: [route log](../../../games/command_link/tests/opening/routes.log).
The runs contain existing direct-image-loading/export warnings from the
prototype stage, with no script errors in the final successful runs.

Independent visual verdict: **accepted for the placeholder opening**. The
non-producer reviewer inspected the native capture and confirmed readable
title/control placement, aspect-preserving letterboxing, and tactical context.
This is local prototype review, not final cinematic or publication approval.

## Code-authored tactical UI

P27 replaces the interface styling with native Godot panels and controls:
angular dialogue backing, actor-accented speaker tabs, condensed headings,
amber primary actions, teal interaction cues, and eleven numbered menu cards.
The shared helpers and host-font fallback are documented in
[the tactical UI notes](../../../games/command_link/presentation/ui/README.md). Existing artwork, fixed 1280×900 canvas,
route behavior, and input contracts remain intact. No UI image generation,
SVG, font download, or production promotion is part of this pass.

`qa/tactical-ui-stage-validation.log` passes the existing stage, scaled-input,
asset, and text-fit checks. Native OpenGL runs pass the route and camera checks
and record **49 PNG/JSON pairs** under `qa/tactical-ui/`: 31 in `routes/`, 12 in
`camera/`, and six actual interaction states in `controls/`. The latter assert
focus, hover, press, and disabled states before capture. Route and control logs
have no warnings or errors; the camera log retains the known repeated Viewport
mouse-leave warnings without script errors. The repository documentation
checker also passes.

`qa/tactical-ui/final-verification.json` binds all 49 capture pairs and ten
runtime/helper source files by hash; all captures are nonblank 1280×900 images.

**Independent visual verdict: accepted for local prototype.** The non-producer
reviewer inspected ten route frames, three maximum close-ups spanning all
actors and locations, a mid-push frame, and all six control-state captures.
All eleven menu titles and descriptions fit. Longer story lines wrap above the
actions, and angular panels leave faces and the contact fingertip clear. Dense
demo sliders and the motion graph remain readable; the fixed UI stays aligned
at maximum zoom. Primary and choice focus, card hover/press, slider emphasis,
and disabled choices are visibly distinct. Existing natural edge cropping of
close-up manpu remains acceptable. This is visual acceptance of the recorded
local renders, not a cross-platform font or performance certification.

## Dialogue Camera and held close-ups

P26 adds explicit scene framing through `scene/dialogue_camera.gd` and the
eleventh demonstration, `demos/dialogue_camera`. The camera transforms scenery,
all actors, and attached manpu together while dialogue, controls, and scrims
remain fixed. Valid finite zoom requests clamp to 1–4×; covered endpoint poses
and their shared interpolation keep the background on the full design canvas.
The controller holds its pose until a later cue and retargets from the current
sample. It does not follow speakers or count dialogue lines automatically.

The main story authors a 3.5×, 0.9-second close-up on Lena's first briefing line,
holds it over her next two lines, and explicitly returns wide for Mira's order
prompt. Choices wait for the wide move. Menu continuation restores the camera
timeline without replaying the cue; the cast handoff, contact pose, and location
introductions retain their own framing. No artwork was regenerated.

### Verification and evidence

`qa/dialogue-camera-validation.log` records PASS for explicit held cues, bounded
zoom and background coverage, interrupted continuity, atomic errors, fixed UI,
actor/manpu composition, frozen clocks, exact restore, and wide non-dialogue
boundaries. `qa/dialogue-camera-routes-validation.log` passes all eleven routes,
the four mission branches, contact, camera and choice gating, handoff/resume,
and scaled input. The companion focus and manpu validation logs also pass.
The existing stage, Character Exit, Cast Transition, and Establishing Shot
regressions pass in `qa/dialogue-camera-validate*.log`.

Real OpenGL runs produced **43 PNG/JSON pairs**: 12 camera states in
`qa/dialogue-camera/captures/` and 31 updated story/menu/demo states in
`qa/dialogue-camera/routes/`. Their logs finish PASS with those counts. The
route capture has no warnings or errors. The camera capture retains repeated
Viewport mouse-leave notifications, with no script errors. Some earlier
headless logs include nonfatal image-as-resource warnings from an editor parse
scan; its generated PNG import sidecars were removed, leaving the source art
unchanged and preserving the spike's raw-image workflow.

`qa/dialogue-camera/final-verification.json` binds all 43 captures and eight
runtime/check source files by hash. The parent verified nonblank 1280×900 images
and background coverage wherever capture metadata declares its rectangle.
The repository documentation checker also passed. No production code, media
publication, or module promotion is part of this change.

### Independent visual verdict

**Accepted for local prototype.** The non-producer reviewer inspected all
12 camera states: all three actors at 4× against each of the three locations,
the wide control, a mid-push sample, and an interrupted retarget. Faces, eyes,
upper hair, and shoulder context remain readable. Backgrounds fill the frame,
and title, dialogue, status, buttons, and sliders retain their fixed layout.
Surprise and sparkle side details crop at maximum zoom, but their main symbols
remain recognizable and correctly attached; the crop does not pin a mark to
the screen or move it away from its owner.

Six refreshed story/menu frames additionally show Lena's 3.5× close-up and held
next line, the restored wide order choice, the matte departure, fingertip
contact, and the eleven-card menu. Lena's complete sweat-drop mark is visible
in the story view, and the longer held line wraps cleanly. The camera treatment
does not obstruct the later handoff or contact interaction. This verdict is
based on selected deterministic renders, complemented by runtime checks; it is
not a measurement of continuous playback smoothness or frame rate.

## Command Link, Establishing Shot, and the story handoff

P24 replaces the cafe story with a commander-led tactical briefing and adds
`demos/establishing_shot`, the tenth focused demonstration. Forward Command,
Perimeter Overlook, and Coastal Staging have character-free opening views with
pan, zoom, and location announcements. Coastal Staging adds an optional lens
flare anchored to the painted sun. The main mission requires Mira's fingertip
contact to pair the command link, includes two decisions with four combinations,
and remembers the commander's reserve-team order.

P25 brings the existing transition contracts into that mission. Lena starts
left and Mira right. After Lena's departure line, she leaves with Silhouette
Fade over 0.9 seconds, Mira moves left over 0.8 seconds, and Sera enters right
over 0.8 seconds. Dialogue resumes only after the handoff. Menu continuation
reconstructs each phase from its saved elapsed time. The first outdoor opening
restores all three actors while they are hidden; later dialogue uses the ordinary
full-squad framing. These story choices add no public module or new character art.

### Artwork and runtime checks

All three opaque 2048×1152 backgrounds passed independent non-producer review
at full size and the fixed 1280×900 cover crop. The exact SHA256 verdicts are in
[the tactical location review](../../../games/command_link/art/rounds/tactical-locations-v1/REVIEW.md).
`art/LOCATIONS_ACTIVE.json` binds the byte-identical installed PNGs to that
local-only acceptance. The locations provide distinct operational contexts and
open staging space without people or legible interface text. Their realistic
matte-painting finish is compatible with the dimensional tactical cast.

The following recorded checks pass:

- `qa/mission-stage-validation.log`: existing fixed-canvas scaling, mouse/touch,
  fingertip mapping, art, three locations, dialogue/manpu, and hologram checks.
- `qa/mission-handoff-routes-validation.log`: all four mission branches,
  required contact, authored handoff and per-phase resume, shot/choice gating,
  replay, all ten menu routes, isolated controls, and scaled physical input.
- `qa/mission-handoff-{focus,manpu,exit,cast}-validation.log`: existing focus,
  manpu, exit, and cast-transition contracts and their story integration.
- `qa/establishing-shot/capture.log`: bounded camera settings, frame partitions,
  active snapshots, atomic restore, skip and exact completion, cover geometry,
  actor/manpu isolation, frozen redraw, and saved timeline restoration.

Headless runs retain the existing macOS certificate diagnostic and finish PASS.
The focused repository documentation/media-rights tests report 89 passed;
`scripts/check_docs.py` also passed. No production Python changed in this pass,
and the broad Python gate was not repeated.

### Rendered evidence and independent visual review

Godot's real OpenGL backend produced **39 PNG/JSON pairs** under
`qa/establishing-shot/`: 11 camera/flare states in `captures/` and 28 story/menu/
demo states in `routes/`. Both `capture.log` and `routes.log` finish PASS with
their complete counts. The route run has no warnings or errors. The camera run
contains repeated Viewport mouse-leave notifications, with no script errors;
these do not prevent capture completion.

The parent's `qa/establishing-shot/final-verification.json` records PASS for all
39 nonblank 1280×900 PNG/JSON pairs, binds their exact capture hashes, and verifies
all three installed background hashes against art acceptance. Its enabled versus
disabled extreme-flare comparison changes 66,483 pixels within scene region
`(0, 105, 1280, 650)`, excluding the title and controls. This supplements the
separate semantic review rather than replacing it.

Independent visual review accepted the new two-person briefing, five sampled
handoff/analysis frames, refreshed main establishing views, menu layout,
fingertip instructions and acknowledgment, and tactical cast/background
composition. The handoff shows Lena's retained alpha-shaped coverage darken to
black, then her absence before Mira's move and Sera's arrival. The final
Mira-left/Sera-right dialogue is unobstructed. The menu fits all ten entries.
No technical tuning controls appear in the story.

The refreshed opening captures show the correct held location titles. Coastal
flare samples follow the visible light source; extreme enabled/disabled frames
separate the effect from the unchanged painted background and show the actual
tuning values. The camera's exact completion frame precedes the ordinary actor
entry fade, so actors can still have zero entry opacity in that sample.
These are deterministic logical-viewport renders and sampled visual judgments,
not measurements of live frame rate or animation smoothness. Earlier captures
and QA sections remain evidence for their respective revisions.

## Sequential Cast Transition and tunable motion curves

P23 adds `demos/cast_transition`, the ninth demonstration, with an initial pair
of Mira and Lena and a hidden Sera. The default handoff runs Exit → Reposition
→ Enter: Mira leaves with the existing Silhouette Fade and outward translation,
Lena moves to the vacated left position, then Sera fades and moves into the right
position. Replace in place omits repositioning. Further runs rotate the current
cast. The main story has no newly authored handoff cues.

The route exposes Linear, Ease in/out, and Spring motion, frequency, damping,
move/entrance duration, and exit/entrance travel distance. The graph draws the
same sampler that positions actors. Busy controls preserve the active snapshot;
Reset cancels and restores the original cast and defaults. Translation may
overshoot, while opacity stays bounded through the separate presentation sampler.
The authored slots are 410/890 on the existing 1280 x 900 canvas. The left slot
provides room for the strongest allowed spring without clamping its curve.

`qa/cast-transition/validation.log` records independent sequence, curve, and
runtime checks: both patterns, phase ordering, initial visibility, two-actor
limit, role rotation, coarse/fine frame partitions, exact rest, finite settings,
atomic rejection, unchanged frozen clocks, graph/runtime agreement, slider and
keyboard controls, reset, and route isolation. Existing Actor Focus, Manpu
Introduction, Character Exit, and asset/input/scaling suites also pass; their
logs are in the same directory. Headless logs retain the existing macOS
certificate diagnostic and finish PASS.

Real OpenGL captures completed without errors or warnings: `capture.log` records
15 PNG/JSON pairs under `captures/`, including the exit/move/enter boundaries,
both completed patterns, a repeated handoff, three curve comparisons, tuned
graph, and extreme spring peak. `routes-capture.log` records 18 route captures
and passing nine-demo navigation/story/input checks. The fixed menu uses a
three-column, three-row layout with wrapped descriptions. These are sampled
logical-viewport renders, not live frame-rate or smoothness measurements.

The parent's eight independent checks in `pixel-checks.json` verify phase
visibility and bounded appearance; graph points against an independent curve
calculation (maximum error about 1.1e-7); actual sprite centers against the
translation formula (rounding below 0.00004 pixels); exact final 410/890 slots;
and pixel-identical survivor artwork before movement. Changing idle tuning
changes the graph while keeping the cast region pixel-identical. At the
strongest spring peak, the faint rendered alpha fringe stays inside the left
edge; the opaque silhouette has additional margin. Source hashes bind this
evidence to the implementation and capture harness.

Independent visual review accepted the staged handoff, newcomer visibility,
completed composition, extreme spring margin, graph and controls, and all nine
menu cards. Exact P23 wording and its short outcome remain in the request
documents. All code and evidence remain inside the disposable spike.
Documentation checks, relative links in the seven changed spike documents, and
89 focused documentation/media-rights tests passed.

## Character Exit and Silhouette Fade

P22 adds `demos/character_exit`, the eighth focused demo, with independent actor
selection, Silhouette Fade and Opacity Fade presets, Exit, Show, and Reset.
The existing sprite supplies its alpha shape once. Silhouette Fade reduces
brightness to black while holding exit opacity at one for the first 55% of
0.9 seconds, then reduces the black silhouette's opacity to zero. This adds no
artwork, material, or shader. Main-story departure cues remain unauthored.

`qa/character-exit/validation.log` records the independent suite for phase
ordering, full exit coverage during color change, black matte transparency,
persistent hidden states, independent actor clocks, repeated-exit idempotence,
Show cancellation, preset snapshots, frozen redraw, source-color composition,
attached-manpu removal, contact hit/feedback ownership, and reset/route isolation.
Unsupported spatial tracks and invalid operations are rejected atomically.
The existing Actor Focus, Manpu Introduction, asset/input/scaling, and updated
eight-demo route checks also pass; their logs are in the same directory.
Headless logs retain the existing macOS certificate diagnostic and finish PASS.

Real OpenGL runs completed without errors or warnings: `capture.log` records
11 exit PNG/JSON pairs under `captures/`; `routes-capture.log` records 17 route
pairs under `routes/`. Exit frames include the color midpoint, opaque black
matte, matte-fade midpoint, complete disappearance, ordinary opacity comparison,
staggered independent exits, interrupted restoration, and a direct-hide control.
Metadata records clocks, preset snapshots, channels, node visibility, geometry,
modulation, and output transform. These are sampled logical 1280 x 900 renders,
not live frame-rate measurements.

The parent's ten independent RGB checks in `pixel-checks.json` verify:

- The color midpoint equals the average of the original and opaque-matte
  renders, demonstrating unchanged source coverage while color fades.
- The matte-fade midpoint equals the average of the matte and direct-hide
  control; the opacity midpoint instead averages the colored actor and control.
- All three midpoint identities differ by at most 0.5 on a 0–255 RGB scale,
  including source-alpha edges. Comparisons exclude changing demo text and the
  foreground dialogue scrim.
- Both hidden endings exactly match the direct-hide control in the cast region;
  Show restores the original full render. Other actors remain pixel-identical.

Independent visual review accepted matching silhouette geometry, phase order,
actor isolation, absence of rectangular backing or doubled outlines, readable
controls, and the eight-card menu. Source hashes bind the pixel evidence to the
controller, presets, stage, demo, and capture harness. Exact request P22 and the
short outcome are retained; all implementation remains in the disposable spike.
Documentation checks, relative links in all seven changed spike documents, and
89 focused documentation/media-rights tests passed.

## Shared presentation animation and individual manpu

P21 reuses `animation/presentation_animation.gd` for Actor Focus and Manpu
Introduction. The stage composes each mark's local animation after its owner's
position and scale. The main story and Manpu demo use Shake; the demo adds
preset selection, individual replay targeting, and explicit replay. Artwork is
unchanged. Exact request P21 and its outcome remain in the prompt archive and
request ledger; production module boundaries remain deferred.

`qa/manpu-animation/validation.log` records the independent manpu suite:
different clocks for simultaneous pairs, unchanged persistent cues, removal and
fresh reintroduction, targeted replay, atomic validation failures, preset-change
continuity, authored fade-in starting at zero, composed geometry and color,
frozen redraw, gallery/reset, and settled story resume. Existing Actor Focus,
route/story/input, and historical asset/scaling checks also pass; their logs
are `focus-validation.log`, `routes-validation.log`, and `legacy-validation.log`
in the same directory. Headless runs retain the existing macOS certificate
diagnostic and complete with PASS.

Real OpenGL runs completed without errors or warnings. `capture.log` records
27 PNG/JSON pairs under `captures/`: Shake, Scale Pulse, Fade In, combined
actor bounce and mark shake, targeted replay with two marks, and None.
`routes-capture.log` records 16 route captures under `routes/`, including the
updated Manpu controls and disabled gallery controls. Captures record the
1280 x 900 logical viewport, sampled time, individual clocks and channels,
owner-attached and final mark rectangles, final draw colors, and actor
rectangles. These are fixed-time render samples, not a frame-rate benchmark.

The parent's seven independent RGB checks in `pixel-checks.json` verify that
individual shake, scale, and fade change only the mark region; replaying Lena's
mark leaves Mira's mark and the surrounding scene unchanged; and mark-only
or combined actor/mark pulses return to pixel-identical resting renders.
The record binds the relevant implementation and QA source hashes.

Documentation checks, all eight changed spike documents' local links, and 89
focused documentation/media-rights tests passed. The parent inspected the
updated Manpu conversation and gallery controls in the native renderer captures.
Independent visual review accepted the sampled shake, scale, fade, combined
actor/mark motion, and named replay. Marks remain clear of faces, their attachment
is readable, and all six demo controls and keyboard hints fit without clipping.

## Actor Focus and interchangeable presets

P20 introduces the local contract in `focus/README.md`, its sampler in
`focus/actor_focus.gd`, and five data presets in `focus/presets.json`. The story
and dialogue demo use Bounce. A seventh route, `demos/actor_focus`, compares
Bounce, Scale Pulse, Listener Dim, Listener Fade, and None through the same cue
and channel sampler. The menu keeps the fixed canvas with four rows of cards.

`qa/actor-focus/validation.log` records the independent focus suite. It covers
atomic rejection of malformed catalogs and invalid cues; finite ordered
keyframes; held dim/fade versus temporary pulses; unchanged time on repeated
speaker cues; continuity through rapid handoffs, preset changes, and replay;
neutral narration; and no position or scale drift at rest. Runtime checks cover
the actual actor rectangle, bottom-center scale pivot, attached manpu movement
and size, entry/focus opacity multiplication, independent hologram materials,
frozen clocks, consecutive Mira lines, and settled menu resume. The custom-track
probe `focus/check_sample_bounds.gd` also passed residual overshoot bounds.

`qa/actor-focus/routes-validation.log` records all story branches and seven
demo routes, including preset cycling, explicit replay, speaker advance, reset,
menu navigation, and native scaled-window input. The historical asset/input
suite passed in `legacy-validation.log`. Headless logs retain the existing
macOS certificate diagnostic; the checks complete with PASS.

Two real OpenGL runs completed without errors or warnings:
`qa/actor-focus/capture.log` records 30 focus PNG/JSON pairs under `captures/`,
and `routes-capture.log` records 16 route pairs under `routes/`. Focus evidence
includes opening, middle, and settled states for all five presets, plus sampled
bounce, scale, and interrupted-handoff sequences at 0, 0.1, 0.2, 0.3, and 0.42
seconds. These are logical-viewport renders with authored-time metadata, not
native window screenshots or a frame-rate benchmark.

The parent's independent RGB checks in `qa/actor-focus/pixel-checks.json` show
that bounce and scale change only the affected actor/manpu region and return
to pixel-identical opening images. Listener dim/fade change only the listener
regions. The record includes sampler, preset, and stage source hashes.
Independent visual review found no issue with the restrained motion, face and
text readability, manpu attachment, listener transparency, or speaker handoff.
The parent also inspected the updated menu and preset screens.

Documentation checks and 89 focused documentation/media-rights tests passed.
P20 is recorded verbatim in `USER_PROMPTS.md` with a short outcome in
`REQUESTS.md`. The contract remains inside the disposable spike; framing
parameterization from P19, module promotion, and audio remain deferred.

## Larger, lower dialogue cast

P19 enlarges each standing dialogue canvas from 551 to 716 pixels high (about
30%) and moves its top from 112 to 146 on the fixed 1280 x 900 canvas. The story
and dialogue-based demos share this framing. Legs now extend behind the dialogue
and controls. The existing dialogue scrim draws once above the actors and below
text, keeping bright clothing from competing with the words. Manpu remain 10%
of actor height and follow the same head anchors.

`qa/cast-framing/validation.log` records passing asset, geometry, manpu, input,
and viewport-scaling checks. The old non-overlapping source-canvas assertion
now permits transparent margins to overlap while checking viewport containment
and distinct face regions. No configurable framing contract was introduced;
that later work is recorded in P19 of the prompt archive and request ledger.

The real OpenGL run in `qa/cast-framing/capture.log` passed all four story paths,
route navigation, demo controls, and physical input at scaled window sizes.
It completed 15 logical-viewport captures with state sidecars in
`qa/cast-framing/captures/`, without runtime errors or warnings. The parent
inspected the opening and choice screens: actors are visibly larger and lower,
legs are visible through the dialogue backing, and both text and choices remain
clear. Earlier `qa/routes/` captures retain the previous framing for comparison.
Independent review of both locations, choices, manpu, and hologram captures found
no issue with face separation, text readability, or drawing the backing twice.

## Playable story and separate demo routes

P18 changes the default launch to the story in `scenes/game.tscn`. The main
script only selects routes and retains in-memory story progress. Six individual
demo scenes under `scenes/demos/` have focused controls and shortcuts; the menu
links to each one. The existing drawing and asset loading remain spike-local
in `presentation_stage.gd`. No production module was extracted.

`qa/routes/validation.log` records the independent `--validate-routes` suite.
All four combinations of greeting and place choices reach their matching
responses and the ending. Routed mouse and focused keyboard choices select
once; unfocused Space/Enter cannot skip a choice. Replay and New game clear the
branch state. Menu, every demo, and Continue/Play preserve the paused story's
beat, remembered reply, and location. Demo shortcuts do not affect the story
or unrelated demos, and Reset restores the current demo instead of navigating
elsewhere. Fingertip contact and actor effect controls remain functional.

Physical input checks also pass at 640 x 450 and 1280 x 580, using the native
viewport transform with its letterbox offsets and one-pixel output rounding
tolerance. The design canvas remains 1280 x 900. The historical renderer/asset
regression suite also passes through the opt-in `--validate` entry point; it is
separate from ordinary routes. Headless macOS logs retain the known system
certificate diagnostic; the checks complete with PASS.

All 15 real OpenGL route captures and state sidecars are in `qa/routes/captures/`;
`qa/routes/capture.log` records the successful bounded renderer run, with no
runtime errors or warnings. These PNGs show the
logical viewport, not OS window pixels. Sidecars identify the route, story or
demo state, physical window size, and output transform. Independent code review
found no actionable issue in route lifecycle, story preservation, keyboard
choice gating, or fixed-canvas layout. The parent inspected the story opening,
both choice screens, branch responses, ending, menu, all six demo layouts, and
the manpu gallery. Text and controls fit the fixed canvas; the story has only
its play controls, and each demo exposes its own feature. The hologram remains
confined to Sera at that route's opening. The character capture freezes auto
blink off for reproducibility and labels that state; ordinary entry enables it.

The repository documentation check and 89 focused documentation/media-rights
tests passed. Local spike documentation links and all six scene paths were
also checked directly, since the spike is ignored by Git.

The exact request and short outcome are P18 in `USER_PROMPTS.md` and
`REQUESTS.md`. Existing artwork is reused; no audio or new transition effect
was introduced. Earlier combined-control screenshots below are historical.

## Fixed canvas and proportional manpu

P17 replaces responsive layout with a single 1280 x 900 logical canvas.
Godot's native Viewport stretch with Keep aspect scales the complete rendered
scene: UI, actors, backgrounds, manpu, and shader output. Physical window
resizing does not change the composition, font sizes, or background crop.
Responsive font branches are removed. Manpu width is exactly 10% of its
actor's drawn height, without the previous 36–54 screen-pixel clamp.

Focused validation passes in `qa/fixed-canvas/validation.log`. The window
matrix is 1280 x 900, 640 x 450, 720 x 900, and 1440 x 900. Each retains the
1280 x 900 logical viewport. Output is respectively 1280 x 900, 640 x 450,
720 x 506 centered vertically, and 1280 x 900 centered horizontally. Integer
output dimensions permit one pixel of rounding at fractional scales.

Mouse and touch input tests enter physical window coordinates through Godot's
native inverse stretch transform, including letterbox offsets. Fingertip hits
and misses, dialogue controls, actor/effect state, location controls, and
restarts pass. The manpu-to-character ratio is checked after output scaling.
Logical render PNGs remain 1280 x 900; their adjacent JSON explicitly labels
the capture space and records physical window/output geometry.

All four bounded real-renderer runs exited successfully. The fixed
`hologram_sera` state is RGB pixel-identical across
`qa/fixed-canvas/{base,half,tall,wide}/`; the parent independently repeated the
comparison. `qa/fixed-canvas/comparison.json` records logical-image equality
and the native output rectangles. A synthetic GUI hover left by validation
was cleared for frozen captures before the final comparison.

Separate native-window evidence is `qa/fixed-canvas/native-half-window.png`,
with source/size/hash notes in `native-window-evidence.json`. The parent
inspected the actual 640 x 450 client window: the whole scene, UI, and manpu
scale down together. Native window chrome is outside the game canvas. This
used existing screen-capture access after a read-only permission check; no
macOS permission was requested or changed. Logical render buffers are not
presented as physical-window screenshots.

The earlier small-window captures below show the preceding responsive layout;
they do not describe the current fixed composition. No artwork was regenerated.

## Hologram character visual effect

Working terminology and the deferred matching-voice requirement are recorded
in `CHARACTER_EFFECTS.md`; the exact request is P16 in `USER_PROMPTS.md`.
The effect uses `shaders/character_hologram.gdshader` on independent per-actor
materials. It shades existing character textures; all fifteen reviewed PNGs
remain byte-identical. No audio implementation or new entrance/exit sequence
was added.

Sera begins at 80% hologram strength. Dialogue controls select the actor (T),
toggle Normal/Hologram (E), and adjust strength. Each actor's effect state is
independent and survives ordinary dialogue, location, and mode changes;
restart restores the demonstration defaults. The shader preserves the original
alpha silhouette and entry/speaker modulation. Manpu, contact feedback, and
interface draw in separate layers above the actor materials.

Focused checks passed at 1280 x 900, 720 x 900, 960 x 580, and 640 x 560.
`qa/hologram/validation.log` covers material identity, controls and strength,
state ownership/reset, deterministic shader time, layer/input behavior, and
the existing character, manpu, location, blink, and fingertip checks. An
independent code review found no unresolved actionable issue; a contact
capture's target metadata was corrected during review.
The headless log also contains macOS sandbox log-file/certificate warnings;
the focused checks completed with PASS. The windowed renderer logs below
contain no shader or runtime errors.

Both real OpenGL capture runs completed all 30 states and exited successfully,
with no shader compile/runtime errors in their logs. PNGs and matching JSON
state/rectangle records are in `qa/hologram/normal/` and `smallest/`; see
`qa/hologram/RUNTIME_REVIEW.md`. The normal set refreshes `captures/`.
The parent inspected normal Sera and Mira effects, minimum Sera and Lena,
and the holographic contact pose. The independent code reviewer also inspected
minimum effects and contact layering. The projected appearance is recognizable,
with visible scanlines, readable faces, separated actors, and clear controls.
Fine facial detail is naturally smaller in the minimum window.

Independent exact-RGBA comparisons are recorded in
`qa/hologram/pixel-comparison.json`, bound to the shader and capture hashes:

- Zero strength equals the normal render pixel-for-pixel at both tested sizes,
  excluding only the changed effect-control labels/slider.
- Applying the effect separately to Mira, Lena, or Sera changes no pixels
  outside that actor's rectangle and the expected effect controls. The actor
  rectangle allows a one-pixel rasterization margin.
- Two frozen animation times differ within Sera's image while every pixel
  outside her rectangle stays identical. This verifies animated output without
  attributing unrelated scene changes to the shader.

These ten comparisons cover 1280 x 900 and 640 x 560. They establish effect
scope and reversibility; the user's final aesthetic preference remains open.
The sixteen prompt/outcome pairs and local links passed verification; the
repository documentation checker and 89 focused documentation/media-rights
tests also passed.

## Third actor preparation

Sera, authored as an adult woman age 23, adds one transparent 1024 x 1536
standing sprite. One manual FAL image request reused the three preserved
user reference PNGs plus the current original Mira/Lena standing images for
style and framing. The saved user references were verified against their
original hashes. Her name, age, dark ponytail, amber eyes, and ivory/cobalt
outfit are demonstration choices.

Independent non-producer art review: `art/rounds/third-actor-v1/REVIEW.md`.
The reviewer accepted the exact PNG for local use after checking rendering,
distinct adult design, hands, full-body framing, and dark/light alpha
composites. The source has tight but complete head/boot margins; the scene
preserves the full canvas and display padding. Runtime installation is a
byte-identical copy, bound by `art/THIRD_ACTOR_ACTIVE.json`. No regeneration
was needed. The fourteen previous character/manpu/background PNGs retain
their existing hashes.

Dialogue now displays Mira, Lena, and Sera in three standing positions with
the same active-speaker emphasis. The original ten lines and cue indices
remain intact. An eleventh line gives Sera a speaking turn and her own
sparkle. Her line was shortened after the smallest-window text-fit check
found wrapping. Lena and Sera each retain one standing frame; Mira's blink
pair and contact pose are unchanged.

Focused Godot validation passed in `qa/third-actor/validation.log`, covering
all three actors' full-canvas framing, speaker and manpu ownership, neighboring
face clearance, progression through Sera's turn and Read again, and text fit
at 1280 x 900, 720 x 900, 960 x 580, and 640 x 560. Existing fingertip mouse/touch,
blink, gallery, location selection/title, and restart checks also pass.

The real OpenGL renderer completed all 22 states at 1280 x 900 and 640 x 560;
both capture processes exited successfully. Evidence is in
`qa/third-actor/normal/`, `qa/third-actor/smallest/`, and their adjacent
capture logs and `RUNTIME_REVIEW.md`. The normal set also refreshes `captures/`.
The runtime author inspected Sera's turn, simultaneous manpu, Mira, gloom,
sigh, and the terrace title. The parent independently inspected normal Sera
and simultaneous-manpu frames plus minimum-size Sera and terrace-title frames.
All three complete silhouettes, faces, manpu, dialogue, and controls remain
separate and visible. Fine character detail is naturally smaller at the minimum
window size.

Documentation checks passed, including all fifteen prompt/outcome links and
the new asset/review/prompt bindings. The repository documentation checker and
89 focused documentation/media-rights tests also passed. No Python provider
helper or production runtime was changed for this addition.

This is preparation for the user's next experiment. Character exits, matte
effects, post-processing, and new shader behavior are not implemented; their
details remain with the user. No module extraction or promotion occurred.

## Location backgrounds and title

Two image-model requests produced opaque 2048 x 1152 PNG backgrounds:
**Glasshouse Cafe** (Old Harbor, evening) and **Lantern Terrace** (Canal District,
dusk). Both use the existing original Mira illustration as a rendering-style
reference. No actors or location-label text are baked into the images.

Independent non-producer review: `art/rounds/locations-v1/REVIEW.md`. Both
originals and their centered minimum-window crops were accepted for local
prototype use. The backgrounds remain distinct as a warm glasshouse interior
and a cool outdoor canal terrace. Their installed bytes match the reviewed
originals exactly; `art/LOCATIONS_ACTIVE.json` records the hashes and bindings.
There were two FAL submissions and no regeneration. The four character and
eight manpu PNG hashes remain unchanged.

The game selects a background randomly on entry or restart. Change scene and
L select the other place without resetting dialogue, manpu, blink, or actor
entry. Dialogue advance and mode changes preserve the current location. The
location title fades in for 0.35 seconds, holds for 2.4 seconds, and fades out
for 0.7 seconds. The ordinary header and smaller persistent location name
then return over 0.25 seconds.

Focused Godot validation passed in `qa/locations/validation.log`. Checks cover
both opaque PNGs, centered cover scaling without uncovered edges or aspect
distortion, seeded random selection exercising both places, change and restart
semantics, unchanged location selection, title timing and rapid
retriggering, state ownership, scene-button and L input, and header font metrics
at 1280 x 900, 720 x 900, 960 x 580, and 640 x 560. Existing dialogue, manpu,
gallery, blink, fingertip mouse/touch, and restart checks also pass.

The first midpoint capture exposed overlapping announcement and header text.
Their fades now run in sequence, and lifecycle checks assert that the two sets
of strings never appear simultaneously. The earlier image remains under
`qa/locations/before-title-fix/` as diagnostic evidence.

All 21 windowed capture states completed at 1280 x 900 in `captures/` and
at 640 x 560 in `qa/locations/smallest/`; both capture processes exited
successfully. Logs: `qa/locations/capture.log` and
`qa/locations/smallest-capture.log`. The runtime author inspected both places,
announcement/settled/mid-fade headers, the longest dialogue line, gallery,
and preserved full-body, blink, and contact states. The parent independently
inspected both normal location announcements, the corrected midpoint fade,
the minimum-size cafe announcement and settled terrace, contact, and gallery.
Both places remain recognizable, with readable character/manpu contrast and
no overlapping title strings, clipped controls, or obscured fingertip in
these views. Fine actor detail is naturally reduced in the minimum window.

The manual FAL helper's opaque-background option passed Ruff lint, format
verification, and Python compilation. All fourteen active image hashes were
verified against their review bindings. This work remains entirely inside
the ignored standalone spike; no production pipeline or adapter was changed.

## Manpu extension

The static manpu set contains eight model-generated transparent PNGs: surprise,
confusion, sweat drop, anger vein, sparkle, heart, gloom lines, and sigh. The
user requested image-model artwork. One FAL request produced the painted atlas;
fixed cell extraction and transparent square padding preserved the original
symbol pixels without repainting or resampling.

Independent review: `art/rounds/manpu-v1/REVIEW.md`. All eight exact PNG hashes
are accepted for local prototype use, with clean alpha, no adjacent-cell
contamination, distinct meanings, and readable 36/56-pixel previews. Runtime
bindings are recorded in `art/MANPU_ACTIVE.json`. Review sheets are
`qa/manpu/static-set.png` and `qa/manpu/scale-check.png`.

The dialogue uses explicit `manpu` cues naming an actor and mark. Its authored
ten-line demonstration includes speaker and listener cues, two actors marked
simultaneously, and neutral lines that clear preceding marks. The gallery
shows the complete set. Terminology in the code and catalog uses `manpu`.

The manpu preparation script passed Ruff lint, format verification, and Python
compilation. Character PNGs were not regenerated for this extension.

Focused Godot validation passed; log: `qa/manpu/validation.log`. Checks cover
all eight PNGs, invalid actor/mark rejection, every authored cue, replacement
on advance, listener and simultaneous actor reactions, clearing on neutral
lines/mode changes/restart, gallery controls, and existing blink/contact/input
behavior. Placement and text fit pass at 1280 x 900, 720 x 900, 960 x 580,
and 640 x 560. Marks use a 36-pixel minimum display size and stay clear of
the measured face regions.

Windowed evidence: all 16 capture states completed at 1280 x 900 in `captures/`
and at 640 x 560 in `qa/manpu/smallest/`, with both runs exiting successfully.
Logs: `qa/manpu/capture.log` and `qa/manpu/smallest-capture.log`. The runtime
author inspected the new cue states, gallery, longest line, and preserved
character/contact modes. The parent independently inspected simultaneous cues,
listener sparkle, neutral clearing, gloom, sigh, gallery, and the smallest
simultaneous-cue frame. No obscured face, clipped mark, or clipped control was
observed in those views. A bounded forced draw keeps capture independent of
macOS window focus.

## Result

Current art revision: `tactical-v2`. Exact active hashes and review bindings are
in `art/ACTIVE.json`; the initial runtime assets and captures were preserved
under `art/rounds/tactical-v2/superseded-initial/` before replacement.

The standalone Godot prototype runs with all four prepared character assets.
The focused checks passed and the seven windowed captures were inspected.
The second actor is Lena, authored as a 21-year-old adult woman with one
standing pose. She appears alongside Mira in the dialogue view.

## Runtime

Engine: Godot 4.7.2, OpenGL compatibility renderer on the local Apple M4 Pro.

Command: `Godot --headless --path spikes/presentation-playground -- --validate`

Result: pass. Checks cover matching full-body canvases, alpha at the measured
fingertip, image-to-viewport coordinate mapping, eye toggles, contact only in
the reach-out view, restart, and rejection during the initially invisible
entrance. Additional input checks route real Godot `InputEventMouseButton` and
`InputEventScreenTouch` events through the viewport at 1280 x 900, 720 x 900,
and 960 x 580: mode-button input works, off-target presses are ignored, and
fingertip presses trigger the acknowledgment through both input paths.

The second-actor extension also passes at all three viewport sizes: both
standing sprites fit without overlapping, controls remain inside the viewport,
and Next, Space, and Enter each advance exactly one line with the expected
speaker. Background clicks and touches in dialogue do not advance it or trigger
contact. The result is saved in `qa/second-actor-validation.log`.

The same focused checks passed with all four tactical sprites and the new
fingertip location, recorded in `qa/tactical-v2-validation.log`. The detailed
new artwork showed jagged highlights when reduced to dialogue scale, so runtime
textures now generate mipmaps and use linear filtering with mipmaps. Before
and after comparisons are saved under `qa/tactical-v2-before-filter/` and
`qa/tactical-v2-after-filter/`. The change smooths hair, straps, and hosiery
without changing the source PNGs, scene layout, or input behavior.

This proves Godot input routing with constructed events. It does not claim a
test on physical touchscreen hardware or a subjective verdict from the user.

## Windowed pictures

Command: `Godot --path spikes/presentation-playground -- --capture-all`

Result: pass. The capture harness runs input checks before taking pictures.
The captures use the actual windowed renderer; a dummy headless renderer is
not used for picture evidence.

- `captures/full_body.png`: complete head-to-shoe framing, readable controls.
- `captures/blink.png`: eyes closed, face and body registered with open state.
- `captures/reach_out.png`: face and foreshortened fingertip visible together.
- `captures/connection.png`: contact ripple and acknowledgment visible.
- `captures/debug.png`: measured hit circle sits over the fingertip pad.
- `captures/dialogue_mira.png`: both actors visible with Mira speaking.
- `captures/dialogue_lena.png`: same framing with Lena speaking.

All seven were inspected by the runtime author. The parent independently
inspected the initial full-body and reach-out frames, and the current tactical
blink, connection, and both dialogue frames. The final tactical capture run
completed all seven states with exit 0 after the filtering change.
No clipped interface
or obstructed face/fingertip was observed in the 1280 x 900 captures.

The runtime author also captured and inspected the smallest allowed window,
640 x 560, in `qa/tactical-v2-smallest/dialogue_lena.png`. Both complete actors,
the dialogue, and controls fit; fine facial detail is naturally smaller there.

## Art

Current independent non-producer review: `art/rounds/tactical-v2/REVIEW.md`.
All four regenerated PNGs are accepted for local prototype use, bound to their
exact SHA256 hashes. Four FAL submissions completed without regeneration.
The set follows the user's three visual references with dimensional painted
anime rendering, layered tactical fashion, and differentiated material shading.
Both characters remain original designs with their established identities.

The new Mira blink differs from the open sprite in 3,347 pixels, all within
the newly measured eye mask; there are zero changes outside it. The fingertip
center is now (1095, 530) in the 1536 x 1024 contact canvas, with a 43-pixel
radius. The three other final PNGs are byte-identical copies of their new
provider outputs. Preparation is recorded in
`art/rounds/tactical-v2/preparation.json` and its adjacent `prepare.py`.

The new set passed checks for reference-specific rendering, adult presentation,
distinct identities, complete bodies, plausible hands, transparent silhouettes,
Mira's identity across poses, and an unobstructed bare index fingertip. Exact
ages 25 and 21 remain authored character attributes. Lena still has one standing
frame only. No audio was introduced.

### Historical initial artwork

Initial independent non-producer review: `art/REVIEW.md`. All three initial PNGs were
accepted for local prototype use, bound to their exact SHA256 hashes. The
three single-image FAL requests completed without regeneration. The open and
closed full-body images differ in 5,051 pixels, all inside the manually
measured eye mask. Preparation used no additional provider calls.

The initial close pose retained the character identity and offered a single index
finger toward the camera. Its superseded contact center was (1052, 542) in its
1536 x 1024 canvas, with a 42-pixel radius. The original raw art and prompts remain under `art/`.
There is no audio in this first setup.

Lena's fourth FAL request completed without regeneration. Her independent
non-producer review is `art/REVIEW-second-actor.md`, accepting the exact final
PNG hash for local prototype use. Her distinct blonde hair and burgundy outfit,
matching illustration style, complete standing framing, relaxed hands, and
alpha composite passed review. Age 21 is authored metadata. No pointing or
additional expression frame was generated for her.

## Scope

This is a disposable experiment under `spikes/`. Nothing was staged, committed,
published, or extracted into the production Godot or generation code. The
production files modified by another task were left untouched.

## Supplemental repository gate

During the initial setup, the repository Python gate was also attempted.
`uv run --offline
python scripts/check.py` encountered a macOS system-configuration panic before
the checks began; the same script was then run using the existing virtualenv
with credentials stripped by the gate. Logs are retained under `qa/`.

Final result: **26 of 28 steps passed in 411 seconds**, exit 1. Python tests
reported **2,164 passed, 1 failed, 7 deselected**. The two failing steps were:

- Strict mypy: `src/stage_gen/components/sideview_terrain/atlas.py:596`, a
  tuple-to-integer comparison type error in the terrain work outside this spike.
- Pytest: `test_planning_bellweather_reproduces_its_cache_key_golden` in
  `tests/unit/recipes/sideview_platformer/test_execution_graph_identity.py`.

Neither failure is in the prototype's files. The terrain file was already
being modified by another task during this gate; this session did not change
it or the platformer golden. No unrelated repair was attempted.

The spike's two manual art helper scripts separately passed Ruff formatting,
Ruff lint, and Python compilation. The broad gate does not discover this
ignored standalone Godot project; its focused runtime and art checks above
are the evidence for this prototype.

The earlier second-actor extension changed only this spike's art, Godot source,
and records and did not repeat the broad repository gate.

The tactical revision is confined to this spike. Its manual FAL helper now
accepts multiple reference images and a separate explicitly authorized revision
directory with a six-submission limit. The new preparation script records the
measured blink and fingertip data. Both touched Python helpers passed Ruff lint,
format checks, and compilation; the broad repository gate was not repeated for
this manual artwork revision.

## P32-P35: generated opening videos and selected default

2026-09-10. The user selected `command-link-a.mp4` after previewing it. Its
matching Ogg Theora encode is the default `assets/opening/title.ogv`.

- Two 1080p/24 fps visual edits: A is exactly 540 frames / 22.5 seconds;
  B is exactly 528 frames / 22 seconds. All MP4 and OGV files fully decode
  without errors and contain no audio track. [Media checks](../../../games/command_link/art/opening-v1/review/media-checks.json).
- Independent visual review accepts the final edits for local spike binding,
  including the corrected group finale and cropped Sera face insert. Rejected
  source ranges remain excluded. [Review](../../../games/command_link/art/opening-v1/review/FINAL_REVIEW.md).
- Native macOS Godot checks decode 1920×1080 frames, preserve the 1280×720 image
  at y=90 on the fixed 1280×900 canvas, keep one unobtrusive control in the lower
  letterbox, and observe real natural completion into the first story beat.
  Pointer/button, touch, Enter, Space and Escape skip; key repeats are ignored.
  [Selected opening A evidence](../../../games/command_link/tests/opening-v1/a.json),
  [alternate B](../../../games/command_link/tests/opening-v1/b.json), and
  [direct game bypass](../../../games/command_link/tests/opening-v1/direct-game.json).
- The existing full headless route suite passed after the bounded opening-route
  update. No production runtime or generation-pipeline boundary changed.
  The repository-wide Python gate was not repeated for this ignored spike.
- All ten provider attempts are reconciled at $10.0886 against the authorized
  $20 cap, including the rejected group video and one image keyframe. No more
  generation is scheduled. [Budget](../../../games/command_link/art/opening-v1/budget.json).

The final edit is silent; no soundtrack or voice processing was implemented or
listening-reviewed. Existing direct-PNG loading warnings remain in native logs;
there are no script or playback errors in the successful checks. This is native
local play evidence, not an export/publication claim. The original placeholder
is retained, and no art or runtime module was promoted.

The alternate smoke runner initially waited for a background-window draw event
after playback completed. The test capture now forces a synchronous evidence
frame and checks player validity; the repeated B check passed. This was a
test-runner correction, with no additional game runtime change.

## P36: looping opening and explicit continuation

Both A and B pass the native [loop smoke runner](../../../games/command_link/tests/opening-loop/native_smoke.gd).
Playback fades to black near its end, wraps into a second cycle, recovers to
full opacity, and remains on the opening route. Minimum sampled end opacity
is 0.0 for A and 0.00147 for B. Fades run over the final 0.8 seconds and first
0.35 seconds; the Begin Briefing control stays visible throughout.

Enter, keypad Enter, Space, Escape, and right-click do not continue. Left-click
on the control or scene and touch each enter the original first story beat.
Missing media stays on the opening with the control available and only emits
navigation after an explicit click. [A evidence](../../../games/command_link/tests/opening-loop/a.json) and
[B evidence](../../../games/command_link/tests/opening-loop/b.json) include frames, source hashes, opacity
samples, and no errors. [Independent review](../../../games/command_link/tests/opening-loop/REVIEW.md) accepts
the fade and restored-loop captures. The former P32-P35 checks are historical.

The source MP4/OGV files and reviewed hashes are unchanged; fade and loop are
Godot playback behavior. No provider calls, new art, or module promotion.

## P37: native resolution with fixed logical layout

The prior Viewport stretch mode rendered the entire scene into 1280×900 and
then enlarged that buffer. Canvas Items with Keep aspect now renders directly
at the content's output resolution while preserving the 1280×900 design space.
No image assets were regenerated or resized.

The native [probe](../../../games/command_link/tests/native-resolution/probe.json) compares the former mode
with the new setting. At a 2560×1800 window, the captured render changes from
1280×900 to 2560×1800. It also verifies 1920×1350 output and 1536×1080 content
inside a 1920×1080 letterboxed window, with unchanged logical Control geometry.
The large opening retains its 1920×1080 decoded source and a physical-window
click enters the first story beat. The enlarged cast/text capture was inspected.

The [native route suite](../../../games/command_link/tests/native-resolution/routes.log) passes, including
physical input at the new 1920×1350 test size. Existing scale QA now distinguishes
logical geometry from native image dimensions and records both in captures.
Native image readback is used for render dimensions; Godot's ViewportTexture
size getter reports a misleading additional scale under Canvas Items.

Earlier fixed-size captures and their QA entries are historical. The user-facing
layout, proportional manpu, letterboxing, and opening-loop contract are preserved.

The [native presentation suite](../../../games/command_link/tests/native-resolution/presentation.log) also
passes at all five window shapes, including 1.5×. It confirms mouse/touch hit
mapping, letterbox exclusion, unchanged layout, and the 0.10 manpu/actor height
ratio alongside actual native render dimensions.

## P40 — Git-visible standalone project

Moved the complete local directory from `spikes/presentation-playground/` to
repository-root `godot/games/playground/`. Runtime code and all 19 prepared
PNG/OGV media files retain their behavior and exact media SHA-256 digests.
Removed one trailing blank line in `main.tscn` for Git whitespace validation.
Current launch commands, repository-relative documentation links, and the two
ignored art helpers' repository-root calculations follow the new location.

Source, scene files, settings, documentation, and QA scripts are staged in Git.
Prepared binary assets, generation history, captures, QA output, and import
caches remain present locally and ignored. This is still an experimental
standalone Godot project; a fresh source checkout requires the local assets.

Independent native checks from the new location passed:

- `Godot --path godot/games/playground -- --validate-routes`: exit 0.
- `Godot --path godot/games/playground -- --validate`: exit 0, including
  native-resolution output, fixed layout, scaled input, and manpu proportions.
- `Godot --path godot/games/playground --quit-after 120`: exit 0 for the
  default opening, with no warnings or errors.
- The two optional local art helpers' `--help` commands: exit 0, no provider calls.

Route and presentation checks retain the existing raw-PNG export warnings;
export portability was not changed or newly validated. Native logs are local
under `/tmp/godot/games/playground-relocation-{routes,presentation,opening}.log`.

The repository documentation checker passed. The media size/location check,
media-rights unit tests, and documentation contract tests passed: 90 tests.
No generated binary was added to the Git index.

## P41 — Shared presentation and explicit game roots

The current layout is documented in [TOPOLOGY.md](TOPOLOGY.md). Command Link's
story/menu/profile moved to its game folder; `main_games.gd` selects the two
explicit roots. The dating root has only a pending setup screen. Shared
presentation requires a supplied profile and imports no game. Legacy fixture
validation/captures moved to `qa/legacy_presentation.gd`.

Independent `qa/composition_checks.gd` passed headless and native, exit 0:

- Distinct roots and fresh nested profiles; Command Link still enters its
  original arrival, and the dating root loads no tactical cast or video.
- Four renamed actor IDs and texture aliases, different roster centering,
  camera/manpu targeting, optional contact, and isolated controllers/materials.
- Separate portrait and contact actors, independent texture selection, and
  correct fingertip ownership and exit gating.
- Explicit actor-free scenes; missing profiles and five invalid landmark cases
  stop cleanly before loading assets or creating actor nodes.

All eight existing native suites passed from the reorganized project:
`--validate`, `--validate-routes`, `--validate-focus`,
`--validate-manpu-animation`, `--validate-character-exit`,
`--validate-cast-transition`, `--validate-establishing-shot`, and
`--validate-dialogue-camera`. These cover story branches/resume/input, original
three-actor framing, native resolution scaling, and the existing effects.
The opening-loop native smoke also passed, including a full video loop,
fade/restart, ignored keyboard input, explicit click/touch entry, and missing
media behavior. The separate dating root launches with exit 0; unknown/missing
game selection and an unsupported dating opening option reject with exit 2.

The 19 prepared runtime PNG/OGV SHA-256 digests are unchanged. No new assets or
audio were generated. The five future features remain documentation only.
Native runtime logs are local under `/tmp/presentation-composition-*.log`.
Existing direct-PNG export warnings remain; this pass does not prove exported
asset loading. Historical capture links elsewhere in this file retain their
original paths and observed behavior.

Repository checks also pass: documentation checker, media size/location,
media-rights unit tests, and documentation contracts (90 tests). Active resource
and documentation links resolve. Shared presentation imports no game root.

## P43 — Practical extensibility review

This pass changes documentation and local development guidance only. A second
source reviewer checked both the existing component boundaries and the updated
contract descriptions. No preparatory runtime fix was found necessary for the
next requested feature. The current conclusion and its limits are in
[EXTENSIBILITY_REVIEW.md](EXTENSIBILITY_REVIEW.md).

The existing `qa/composition_checks.gd` passed headless again, exit 0, covering
the five groups listed under P41: root/profile isolation, alternate cast,
separate portrait/contact bindings, empty/missing profiles, and bad landmarks.
The local log is `/tmp/presentation-p43-composition.log`. The sandbox cannot
write Godot's usual user log and reports the existing macOS certificate-store
error; redirected output records all five passing groups with no script error.
Existing direct-PNG export warnings remain; this check provides no new visual
or export evidence.

The repository documentation checker and links in this pass's seven changed
documents pass. A source scan confirms that shared presentation still imports
no game or demo. Native story/effect suites were not rerun for documentation
changes; P41's native results remain the preceding runtime evidence.

## P47 — Afterlight and Walking Approach

[Afterlight](../../../games/afterlight/README.md) replaces the reserved dating
root with a short playable scene and its own camera study. It owns its UI and
uses the [Walking Approach controller](../../../games/command_link/presentation/camera/WALKING_APPROACH.md)
without inheriting the tactical stage. The controller and its independent QA
were authored separately; a further source review caught and resolved host-side
resume-geometry checks and study defaults that needed to follow the game root.

Focused checks passed:

- `qa/walking_approach_checks.gd`, headless: visible vertical bob, monotonic
  zoom, settled final hold, deterministic split timing, replay/skip/reset,
  snapshot restore, per-instance state, and atomic invalid-input rejection.
  Coverage checks sample 48,080 frames across five geometries and setting limits.
- `qa/afterlight_checks.gd`, headless and native: approach/guest sequencing,
  choice/replay, fixed UI, study tuning isolation, route pause/resume, invalid
  geometry/no-shot restore rejection, root-authored defaults, and missing-media
  controls. Physical clicks work at 1280×900 and 2560×1800; native image readback
  confirms matching raster dimensions rather than a scaled low-resolution frame.
- `qa/composition_checks.gd`, headless: both active roots and the old dating
  alias, isolated content, plus the existing alternate-cast/profile checks.
- Command Link's native `--validate-routes` regression: all four mission
  branches, contact, cast handoff/resume, camera/choice gates, menus/demos,
  keyboard actions, and scaled input.

Native log: `/tmp/afterlight-native-checks.log`. Command Link regression log:
`/tmp/afterlight-command-link-routes.log`. Local captures in `qa/afterlight/`:
`walking-base.png`, `greeting-base.png`, `study-held.png`, `ending-base.png`, and
`greeting-double.png`. Root and independent reviewer inspected the rendered
UI and actor visibility. These stills do not by themselves establish the feel
of continuous motion; deterministic checks cover its sampled behavior.

Three independently copied placeholder PNGs match their originals by SHA-256;
[placeholders.json](../../../games/afterlight/assets/placeholders.json) retains
source and existing review references. No artwork was generated or republished.
Existing direct-PNG export warnings and sandbox log/certificate messages remain
outside these behavior assertions; no exported-package claim is made.

Run the focused checks from the repository root:

```sh
Godot --headless --path godot/games/playground --script res://qa/walking_approach_checks.gd
Godot --path godot/games/playground --script res://qa/afterlight_checks.gd -- --game bishoujo_afterlight --capture-afterlight
Godot --headless --path godot/games/playground --script res://qa/composition_checks.gd
```

## P49–P50 — Eye Transitions and edge softness

Afterlight now demonstrates Eye-Opening, Eye-Closing, and Blink Transitions in
its own study route. The main scene introduces the guest while the blink is
fully closed, then opens onto her. The reusable controller owns timing and
snapshot state; the host owns the screen-space mask, layering, and controls.
The [terminology dictionary](../docs/TERMINOLOGY.md) records these names, example uses,
and the distinction between edge feathering and future scene defocus.

Focused checks passed:

- `qa/eye_transition_checks.gd`, headless: exact endpoints, easing, closed hold,
  closure history across large frames, replay/skip/clear, isolated settings,
  JSON snapshot resume, and atomic invalid-input rejection.
- `qa/eye_transition_integration_checks.gd`, headless and native: guest reveal
  under full closure, leftover frame time, route pause/resume through each
  blink phase, inconsistent-state rejection, and physical study controls at
  1280×900 and 2560×1800. Native pixel checks prove rounded coverage, fully
  black/clear endpoints, and unaffected UI above the mask.
- A second native integration pass verifies the softer default edge: a broad,
  gradual alpha falloff compared with zero softness, preserved endpoints at
  maximum softness, live adjustment without retiming, and Reset restoring the
  game root's default. This feathers mask coverage; it does not blur the scene.
- Updated `qa/afterlight_checks.gd`, headless and native: the new approach/blink/
  greeting sequence and separate skip actions retain choices, replay, route
  state, missing-media behavior, and input at both window sizes.
- Existing `qa/composition_checks.gd`, headless: both roots, alternate cast,
  component isolation, and invalid-profile handling remain valid.

Native softness log: `/tmp/eye-transition-softness-native.log`. Afterlight
regression log: `/tmp/afterlight-eye-regression-native.log`. Local captures in
`qa/eye-transitions/` include closed, hard-edge, rounded-opening, and open study
frames at both sizes. Root and independent QA reviewer inspected the captures;
stills demonstrate coverage and appearance, while sampled checks cover timing.
No assets were generated. Existing direct-PNG export and sandbox log/certificate
warnings remain outside these assertions; this is not export-package evidence.

Run the focused checks from the repository root:

```sh
Godot --headless --path godot/games/playground --script res://qa/eye_transition_checks.gd
Godot --path godot/games/playground --script res://qa/eye_transition_integration_checks.gd -- --game bishoujo_afterlight --capture-eye-transitions
```

## P51–P52 — Original Afterlight cast and indoor locations

The existing manual FAL CLI produced four standing sprites, Nami's close
portrait, two indoor backgrounds, and one superseded outdoor candidate. Eight
submissions cost $1.5804 in provider-reported receipts, within the $5 budget; no
request was retried. An independent reviewer inspected every full source image,
alpha coverage, identity, clothing, cast contrast, and usable background space.
The cast forms two restrained/flat silhouettes and two fuller silhouettes; no
numeric ages are assigned.

[The asset catalog](../../../games/afterlight/assets/catalog.json) binds active
and inactive images to exact source hashes, prompt hashes, receipts, and
independent review-report hashes. Runtime installation copies accepted PNGs
unchanged. Raw RGB previews can show colored pixels outside the figures, but
those pixels are transparent; the alpha-applied cast sheet and native captures
show clean compositing. Standing-image margins are tight but complete. Nami's
close portrait intentionally crops her lower torso and uses its own eye anchor.

The expanded `qa/afterlight_checks.gd` passed headless and natively: four
physical guest selections, the 50/50 root configuration, matching sprite and
speaker identity, restored guest/choice state after study detours, both
backgrounds, close-art selection, eye landmarks, and input at 1280×900 and
2560×1800. Existing walking/choice/replay/missing-media checks remain in that
suite. The existing eye integration passed headless and natively, including
mask pixels, timing, closure reveal, route state, and softness at both sizes.
The composition suite also passed headless; shared controllers and Command
Link's code are unchanged.

Logs: `/tmp/afterlight-new-cast-native.log`,
`/tmp/afterlight-new-cast-eye-native.log`, and
`/tmp/afterlight-p51-composition.log`. Captures in `qa/afterlight/` include
`cast-{guest}-{width}.png`, `eye-cast-{guest}-{width}.png`, and
`conservatory-greeting.png`. These initial captures retain the first background
bindings and picker position; the final indoor capture below supersedes their
location and UI-placement evidence. Native review prompted moving the host's
guest selector to the upper right so it no longer overlaps standing faces.

This pass changes local art and Afterlight's own cast selection/bindings. It
does not introduce a shared UI framework or generation contract. Generated
media and reference inputs remain ignored; no publication was performed.
Existing direct-PNG export warnings remain outside the local-runtime evidence.

The final targeted native check passed after correcting a stale outdoor binding:
Conservatory is the default, Reading lounge is the alternate, all four relocated
guest buttons and Change backdrop accept physical clicks at both sizes, and
standing/close portraits render at native raster dimensions. Final log:
`/tmp/afterlight-final-indoor-native.log`. Reviewed captures in
`qa/afterlight/indoor-final/` include `conservatory-nami-1280.png`,
`reading-lounge-riko-1280.png`, and `conservatory-nami-close-2560.png`.
Their 2× counterparts and Yuzu close captures are retained alongside them.
The final asset/digest/receipt/link checks and repository documentation check
also pass. All seven active PNGs remain excluded from Git.

## P53–P56 — Rejected redesign and canonical-style preview

P53 produced four text-only standing redesigns and a matching close portrait
for $0.9896. P54 rejected their attractiveness and paused that direction before
any runtime activation. Earlier independent technical findings did not predict
the user's aesthetic judgment; they are retained only as historical evidence
under `art/rounds/afterlight-cast-v2/`. The in-flight close request completed
after the pause and is included in that rejected-round cost.

P55 uses the user-selected approach: one supplied image (#3) as canonical
rendering-style input, with an independently described lavender-haired heroine.
One proof PNG cost $0.1752. Total spend through this preview, including all
rejected candidates, is $2.7452 of $5. Exact prompt, receipt, source image and
alpha-applied preview are in `art/rounds/afterlight-style-proof-v1/`. Advisory
inspection finds stronger expressive-eye/blush continuity and distinct character
features; full-body framing remains tight. P56 reserves quality and replacement
approval for the user. No candidate is accepted into runtime by this note.

All seven active PNG hashes still match the existing catalog and the root still
uses the original selected cast. No runtime code or image binding changed; no
new runtime test was needed. Documentation checks pass.

## P61 — Approved high-resolution cast installed

Installed the five final user-approved P59–P60 PNGs unchanged: four 2048×3072
standing sprites and the corrected 2048×2048 Nami close portrait. The corrected
Yuzu standing asset keeps the requested 50/50 proportion split. Root eye
landmarks were remeasured from the exact source pixels; the existing close
height and story framing remain suitable. Backgrounds and shared presentation
code are unchanged.

The native `qa/afterlight_checks.gd` suite passed: all four physical guest
selections, dialogue and both choices, replay, route/state restoration, both
indoor backgrounds, dedicated close-art binding, eye-anchor alignment, and
native raster/input at 1280×900 and 2560×1800. The native
`qa/eye_transition_integration_checks.gd` suite also passed, including all
blink-phase resumes, feathering/closure/opening pixels, fixed UI layering and
study inputs at both sizes. Neither native run reported errors or warnings.

Current captures in `qa/afterlight/` and `qa/eye-transitions/` supersede the
P51–P52 cast views. Logs: `/tmp/afterlight-p61-native.log` and
`/tmp/afterlight-p61-eye-native.log`. The bound capture/source receipt is
`qa/afterlight/approved-cast-v3-verification.json`. All active asset, source,
prompt and independent review hashes match the catalog. User approval and
installation are recorded in `art/rounds/afterlight-cast-v3/activation-p61.json`.

No new generation, source-art transformation, or media publication occurred.
PNG assets and run output remain ignored by Git. This evidence covers local
native gameplay, with $5.9598 spent of the expanded $10 image budget.

Independent native visual review found no blocking issue across all four story
and eye-study views at base size, plus Yuzu story and Nami/Yuzu close views at
2×. Faces and chin remain clear of controls, eye landmarks center correctly,
and alpha edges and fine artwork detail remain clean. The existing header can
cover some hood/ear tips; it does not cover faces. This still review complements
the integration suite's dynamic mask assertions.

## P63 — Monologue, portrait detail, Camera Drift, and Actor Halo

The three new component checks pass: `qa/intertitle_checks.gd`,
`qa/camera_drift_checks.gd`, and `qa/actor_halo_checks.gd`. They cover explicit
time/reveal/continue behavior, interruption and atomic restore/refusal, isolated
instances, finite bounded camera samples and coverage, and alpha-derived halo
geometry. The native halo check additionally proves glow beyond the source quad,
invisible opaque interiors, RGB-edge independence, zero strength, and clipping.
Log: `/tmp/afterlight-actor-halo-native.log`.

Native `qa/afterlight_narrative_checks.gd -- --game bishoujo_afterlight
--capture-narrative` passes at 1280×900 and 2560×1800. It checks two player
monologues, separate reveal/continue pointer and keyboard actions, black/text
pixels, paused world clocks, exact monologue/detail route restoration, camera
coverage, actor/halo registration, choices, ending, and replay. The detail hides
top navigation and restores it for conversation; Escape still leaves and resumes
the paused beat. Captures in `qa/afterlight-narrative/` show monologue reveal/hold
and the combined detail/drift/halo beat. Log: `/tmp/afterlight-narrative-native.log`.

Native `qa/afterlight_effect_study_checks.gd` passes at both sizes, including
physical scaled input, all four guests, optional dedicated-detail bindings,
editable intertitle duration, drift pause/clear/coverage, and halo tuning/toggle.
Captures in `qa/afterlight-effects/` cover the menu and three separate routes.
Visual review confirms readable controls, sharp native raster, and clipped
portrait framing without a glowing rectangular boundary.

Visual inspection prompted moving the fallback crop so the mouth is fully
outside the shot and increasing its overscan so the source's lower cut edge
also remains outside the window. The narrative check now asserts full viewport
overscan including halo margin. Full texture alpha is preserved. The generated
detail candidate is not used in these runtime captures. The current approved
portrait crop remains active in both story and studies.

Existing Afterlight and Eye Integration checks also pass. Composition checks
pass after replacing an obsolete no-script-inheritance assertion with the actual
boundary: Afterlight must not inherit the tactical stage or Command Link.
Its new `story.gd` inherits only its own host. Command Link's entry and prepared
cast checks remain intact. Headless runs retain existing direct-PNG export
warnings; native evidence covers local play, not packaged export.

The dedicated Nami image is retained under `art/rounds/afterlight-detail-v1/`
with prompt, provider receipt, budget, and independent advisory visual review.
It cost $0.4432; cumulative spend is $6.4030 of $10. User quality selection remains
pending under P56, so no new asset activation is claimed. TTS and Ambient
Particles remain deferred. Source/contracts/docs are tracked locally; generated
art, captures, and provider output remain ignored and unpublished.

## P64 — English/Korean text sets and live language selection

`qa/afterlight_language_checks.gd` passes headless and with native rendering at
1280×900 and 2560×1800. The data checks cover isolated dictionary copies, named
values, English fallback, visible unknown keys, missing translations, and atomic
refusal of malformed sets, mismatched placeholders, or unknown language choices.
The two authored catalogs contain 124 matching keys with matching placeholders.

Native integration checks exercise the physical language button and F6 during
walking, dialogue, monologue reveal/hold, detail, and choices. Camera/eye/drift
clocks, stable actor/choice IDs, and story continuation remain intact. Changing
language in a study and returning also preserves a partly revealed monologue.
The five study/menu routes retain their controls, effect settings, paused state,
and custom text. Default Intertitle study text follows language selection.

All 299 unique Hangul syllables in the Korean set are available through the
host's actual SystemFont. Native text-bound checks and visual inspection found
readable dialogue, centered monologues, choices, and study controls at both sizes.
Twenty captures are retained in `qa/afterlight-language/`. Final passing log:
`/tmp/afterlight-language-native-diagnostic.log`. One earlier native input run
unexpectedly reached a held monologue before its partial-reveal assertion and
cascaded; the traced rerun passed without host changes. That intermittent input
observation is retained separately from the final passing evidence.

The existing Afterlight, Eye Integration, effect-study, and composition suites
also pass headless. Their logs use `/tmp/afterlight-p64-<check_name>.log`.
The effect-study fixture now resolves the root's text IDs through the same
preparation boundary as normal play. Existing raw-PNG export warnings remain;
this evidence covers local runtime rendering. Repository documentation checks
and scoped whitespace checks pass. No provider call or active-art replacement
occurred in this pass.

## P66 — Approved dedicated Nami detail portrait installed

Installed the user-selected P63 portrait as `characters/nami_detail.png`, a
2048×2048 RGBA PNG copied byte-for-byte from the reviewed source. Nami's root
profile binds it to the main detail beat and Camera Drift/Actor Halo studies
at 1600 logical pixels high with a vertical offset of -200. Standing and eye
portraits, the other guests, and text sets remain unchanged.

Native narrative checks pass in Korean at 1280×900 and 2560×1800; the effect
study suite passes at both sizes in English. The added assertion verifies
actual dedicated-texture binding and full viewport overscan including halo
padding throughout drift. Fourteen captures in `qa/afterlight-narrative/` and
`qa/afterlight-effects/` supersede the earlier fallback-detail views.
Independent visual review confirms visible chin/neck/collar/upper torso,
mouth and eyes outside the shot, crisp text, and no straight source boundary
or rectangular halo. The halo remains subtle in this tightly framed shot.

Logs: `/private/tmp/afterlight-p66-narrative-native.log` and
`/private/tmp/afterlight-p66-effects-native.log`. No runtime/script errors;
existing raw-PNG export warnings remain outside this local runtime proof.
Asset, prompt, and review digests validate across the catalog. Approval and
bound runtime evidence are recorded in
`art/rounds/afterlight-detail-v1/activation-p66.json`. No new provider operation
or spend; cumulative image cost remains $6.4030 of $10. Documentation and scoped
whitespace checks pass. Generated PNGs and captures remain ignored by Git.

## P67–P68: linear ensemble episode and dedicated Presentation Lab

Afterlight now plays the original 34-beat *The Letter Without a Sender* with
all four cast introduced by the plot. It is a bishōjo ensemble adventure, not
a guest selector or dating-route simulation. The shared effects are composed
by its independent game-owned story and cast renderer. Existing approved art
is unchanged and no provider operation was performed.

The new primary `qa/afterlight_ensemble_checks.gd` passes headless and native at
1280×900 and 2560×1800. It exercises the full linear story, explicit cinematic
finish/reveal/continue gates, all four introductions, physical return after
projection, background coverage, world suspension during monologues/pause,
English/Korean reveal continuity, and actual shell trips through the lab at
walking, eye, handoff, detail, projection, intertitle, exit, and establishing
checkpoints. Native evidence: `qa/afterlight-ensemble/` contains 22 PNG captures
and matching beat/geometry metadata. Log: `/tmp/afterlight-ensemble-native.log`.
Independent rendered review confirms readable Korean, unclipped dialogue,
proportional manpu, the approved face-excluding detail shot, and distinct
four-character staging. A small game-owned header backing improves contrast
against the bright indoor art.

`qa/afterlight_cast_stage_checks.gd` independently checks actor-local hologram,
matte color-before-opacity departure, ordered handoff and large-delta
completion, scene cancellation, camera/manpu attachment, and frozen render
sampling. It passes headless.

Presentation Lab's suite loads all 17 routed workbenches/menus, redirects legacy
launch routes to the actual lab root, preserves separate game checkpoints, and
checks independent lab/story language and restart isolation. Moved Afterlight
effect studies, the complete Command Link story route suite, composition suite,
and all six prior focus/manpu/exit/cast/establishing/dialogue-camera suites pass
headless after the extraction. Logs: `/tmp/p67-presentation-lab-console.log`,
`/tmp/p67-lab-effects-console.log`, `/tmp/p67-command-routes-console.log`,
`/tmp/p67-composition-console.log`, and `/tmp/p67-*-routing-console.log`.

The old `afterlight_checks`, `afterlight_narrative_checks`,
`afterlight_language_checks`, and `eye_transition_integration_checks` entry
points now delegate to the new ensemble suite. Earlier selected-guest story
captures/results above are historical; independent controller/study tests
continue to cover isolated mechanisms. This change does not claim export
readiness, permanent saves, TTS playback, or an Ambient Particles system.

```sh
/Users/universe/.local/bin/Godot --headless --path /Users/universe/Documents/shared/stage-gen/godot/games/playground --script res://qa/afterlight_ensemble_checks.gd -- --game bishoujo_afterlight
/Users/universe/.local/bin/Godot --headless --path /Users/universe/Documents/shared/stage-gen/godot/games/playground --script res://qa/presentation_lab_checks.gd
```

Final P67/P68 native input checks also pass at 1×/2×. The dedicated
`qa/afterlight_input_checks.gd` sends viewport mouse/keyboard events for black
monologue clicks, Next, Space/Enter, Escape pause/resume, and F6 language changes.
Its final header and ensemble captures verify the contrast adjustment against
current source: `qa/afterlight-ensemble/final-header-{1280,2560}.png` and
`final-ensemble-{1280,2560}.png`. Log: `/tmp/afterlight-input-native.log`.
Presentation Lab also passes natively; four reviewed menu captures live in
`qa/presentation-lab/captures/`. Log:
`/tmp/p67-presentation-lab-native-console.log`. Repository documentation check,
current local documentation links, and whitespace checks pass.

## P69 — Walk-Away and Restless Bounce

`qa/walk_away_controller_checks.gd` passes the shared sampler, both directional
exit presets, finite Y-only focus cue, legacy four-channel retarget input,
reset/cancel, and atomic Cast Transition preset selection. A walking departure
owns its horizontal travel once; survivor/entrance phases retain the existing
motion curve. Existing focus, manpu, exit, and cast controller checks also pass.

`qa/walk_away_integration_checks.gd` passes six groups across Afterlight's cast
adapter, the integrated tactical presenter, the actual story/Lab checkpoint
round trip, and all 12 cast/motion combinations in the new study. Checks cover
monotonic X, repeated Y steps, original-height scaling, attached manpu, frozen
sampling, cancellation, terminal visibility, and pause/language/replay/reset.
Prepared wide framing clears the complete sprite rectangle before the final
opacity tail in both walking directions. This does not assert that these fixed
travel presets clear every future camera crop; a host must choose sufficient
travel for its own framing.

Logs: `/tmp/afterlight-walk-away-core.log` and
`/tmp/walk-away-integration-headless.log`. Existing Actor Focus and Character
Exit runtime suites pass, as does Presentation Lab's expanded 18-route ownership
and isolation suite. The source text sets retain matching English/Korean keys.
No assets were generated or replaced for this change.

The final native run passes eight groups, including Riko's authored hologram
plus Y-only motion without disturbing Yuzu or the shader. Twenty reviewed
captures with geometry metadata at 1280×900 and 2560×1800 live under
`qa/walk-away/`; `motion-paths.json` records 14 sampled exit trajectories.
Visible travel stays fully colored, the offscreen frame is clean, and Restless
Bounce returns to center. Korean controls and the four-card effect menu fit at
both sizes. Log: `/tmp/walk-away-integration-native.log`. No script or rendering
errors remain; the existing raw-image export warnings are outside this local
prototype change.

```sh
/Users/universe/.local/bin/Godot --headless --path /Users/universe/Documents/shared/stage-gen/godot/games/playground --script res://qa/walk_away_controller_checks.gd
/Users/universe/.local/bin/Godot --headless --path /Users/universe/Documents/shared/stage-gen/godot/games/playground --script res://qa/walk_away_integration_checks.gd
```

## P70 — One-Shot Manpu and Sigh Puff

`qa/one_shot_manpu_checks.gd` passes event identity, overlapping same-target
emissions, independent expiry, frame partitions/large deltas, frozen sampling,
immutable preset snapshots, atomic invalid input, targeted cancellation, and
persistent-cue compatibility. The existing controller regression set also
passes. Logs: `/tmp/one-shot-manpu-controller.log` and
`/tmp/one-shot-manpu-existing-controller-regression.log`.

The existing Manpu runtime suite passes after the event renderer integration.
Afterlight's complete 34-beat ensemble suite passes, including language/pause
and actual laboratory checkpoint detours. Presentation Lab loads all 19 routed
studies/menus and retains game ownership/isolation. Logs:
`/tmp/p70-manpu-runtime-output.log`, `/tmp/p70-ensemble-output.log`, and
`/tmp/p70-lab-routes-output.log`.

The lab's focused projection check also passes: 2D TextureRect and Sprite3D
projected centers/sizes agree within 0.02 logical pixels at 1×/2× and camera
angles of 0°/25°. Both renderers consume the same event samples; changing the
preview or output resolution preserves clocks, and expired instances remove
their corresponding nodes. Log: `/tmp/p70-lab-projection-console.log`.

The new original 1024×1024 RGBA puff was independently reviewed on light and
dark backgrounds before installation. Its PNG bytes are unchanged; the other
eight manpu are unchanged. Source, exact prompt, sanitized receipt, alpha
diagnostics, and review remain in ignored `art/rounds/manpu-sigh-puff-v1/`.
This is local prototype acceptance, not a generated-media publication decision.

`qa/one_shot_manpu_integration_checks.gd` passes headless and natively. It covers
both 2D hosts, expiration/hidden-owner node cleanup, camera composition, the two
authored story emissions, a real lab detour during a live puff, and mouse/F6
interaction with static/shake/event, pause/reset, and 2D/3D preview controls.
Ten reviewed native PNGs in `qa/one-shot-manpu/` show the story, tactical host,
lab menu, and 2D/3D puff views at 1×/2×. The puff retains a clean transparent
contour, the Korean controls fit, and the 3D camera-facing presentation remains
coherent at 25°. Logs: `/tmp/p70-manpu-integration-headless.log` and
`/tmp/p70-manpu-integration-native.log`. No script/rendering errors remain.
This proves a bounded Sprite3D consumer; general 3D scene authoring and ambient
particle emission remain separate work.

```sh
/Users/universe/.local/bin/Godot --headless --path /Users/universe/Documents/shared/stage-gen/godot/games/playground --script res://qa/one_shot_manpu_checks.gd
/Users/universe/.local/bin/Godot --headless --path /Users/universe/Documents/shared/stage-gen/godot/games/playground --script res://qa/one_shot_manpu_integration_checks.gd
```


## P71–P72 — Afterlight gradients, reconverging choice, and visible Sigh Puff cues

Afterlight now has 36 beats, including one explicit two-option exchange and
its selected reply. The existing input suite passes background mouse/touch,
Space/Enter reveal/advance, menu blocking, readiness-dot visibility, absence of
Next/Skip/instruction controls, and choice placement above the dialogue sheet.
It exercises both replies and their shared continuation, including keyboard
selection and pending/resolved checkpoints through actual Presentation Lab
navigation. English/Korean changes preserve the chosen reply, reveal fraction,
and effect timing.

The ensemble suite passes all 36 beats at 1280×900 and 2560×1800, including
camera coverage, pause, language, and laboratory detours. The One-Shot Manpu
integration suite verifies natural and manual after-reveal emissions on all
three story cues, once-only triggering, expiry, and live-puff checkpoint replay.
Walk-Away integration also passes. These checks use the existing prepared
assets and make no provider calls.

Headless logs: `/tmp/p71-afterlight_input_checks-console.log`,
`/tmp/p71-afterlight_ensemble_checks-console.log`,
`/tmp/p71-one_shot_manpu_integration_checks-console.log`, and
`/tmp/p71-walk_away_integration_checks-console.log`.

```sh
/Users/universe/.local/bin/Godot --headless --path /Users/universe/Documents/shared/stage-gen/godot/games/playground --script res://qa/afterlight_input_checks.gd -- --game bishoujo_afterlight
```

The same input suite passes with the native renderer. Seven PNGs in
`qa/afterlight-ensemble/input-*.png` show dialogue, monologue, and the choice at
both native sizes, plus Nami's live reply puff. Visual review confirms readable
Korean text, full-width edge gradients, centered separated answers above the
sheet, and a clearly visible puff beside Nami's face. Capture uses an explicit
`RenderingServer.force_draw()` to avoid waiting indefinitely for an idle
renderer signal. Native log: `/tmp/p71-afterlight-input-native-console.log`.
No script errors remain. Documentation checks and `git diff --check` pass.


## P73 — Text Reveal Audio and voice-first fallback

`qa/text_reveal_audio_checks.gd` passes headlessly. It checks paced natural
Unicode reveal, whitespace suppression, bounded long-frame behavior, silent
manual reveal, pause, custom streams, explicit `auto`/`typing`/`silent` modes,
voice precedence, actual clip completion, and completed-voice resume. The real
Afterlight host is exercised for monologue/dialogue and choice response audio,
Sigh Puff compatibility, language changes, silent checkpoint reconstruction,
route cleanup, localized resolved-key voice binding, saved playback position,
and per-beat silence even when a voice exists.

An AudioEffectCapture on Godot's mixer captures the actual built-in output
while the component follows paced reveal. The local ignored audition file is
`qa/text-audio/default-typing.wav`; measured peak amplitude is about 0.02244,
with nonzero samples and no clipping. This validates audio output and timing,
not a listening verdict or final production mix. No provider calls or paid
asset generation were involved.

The existing Afterlight input regression also passes. Logs:
`/tmp/p73-text-audio-qa-console.log` and `/tmp/p73-input-qa-console.log`.
No script errors or playback leaks remain; the existing macOS certificate and
raw-image export warnings are unrelated to this change. Documentation checks
and scoped Git whitespace checks pass.

```sh
/Users/universe/.local/bin/Godot --headless --path /Users/universe/Documents/shared/stage-gen/godot/games/playground --script res://qa/text_reveal_audio_checks.gd -- --game bishoujo_afterlight --language ko
```

## P74–P76 — ominous fields, later encounter, dedicated Keeper

The final 49-beat ensemble passes headlessly and with the native renderer at
1280×900 and 2560×1800. The sequence checks require every heroine introduction
and the ward repair before the excursion. Keeper uses a separate supporting
cast profile and PNG; the four approved heroine files retain their digests.
The suite exercises active shake/corruption during language changes and lab
detours, explicit continuation, monologue and pause clocks, world coverage,
the clean return, and Nami's once-only after-reveal Sigh Puff. All four heroines
return, with Riko's projection preserved until her later physical arrival.

Logs: `/tmp/afterlight-keeper-ensemble-checks.log` and
`/tmp/afterlight-keeper-ensemble-native.log`, both exit 0. Thirty native captures
are in `qa/afterlight-ensemble/`. The Keeper introduction, close-up, impact, and
return puff were visually reviewed: the malicious smile remains readable,
alpha composites cleanly, and no field seams or camera-exposed edges appear.
Host-local corruption darkness is 0.45 to preserve her face while keeping
the surrounding mist and background treatment active.

```sh
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/godot/games/playground --script res://qa/afterlight_ensemble_checks.gd -- --game bishoujo_afterlight --language ko --capture-ensemble
```

The independent field suite passes headlessly and natively, with 14 captures
under `qa/ominous-vfx/`: two existing actor sprites, an environmental area,
the screen, barrier/heat modes, procedural and optional texture noise, zero
strength pixel equivalence, UI isolation, pause/reset, and 1×/2× framing.
Logs: `/tmp/ominous-qa-headless-final.log` and `/tmp/ominous-qa-native.log`.
Impact Shake checks also pass deterministic timing, finite motion, exact
settlement, coverage, snapshots, and atomic validation in
`/tmp/impact-shake-checks.log`. Static independent integration review found no
blocking lifecycle or host-boundary defect. These prove this desktop prototype;
mobile/export performance has not been profiled.

Keeper generation used two built-in image attempts (both returned RGB with a
painted transparency grid), then one existing FAL Sunburst `max` CLI edit.
The final 2048×3072 RGBA image passed an independent, digest-bound semantic
review in local `art/rounds/afterlight-keeper-v1/REVIEW.md` and was copied
unchanged as the new character requested in P75/P76. Existing heroine art was
not replaced. This records independent review, not a new user quality verdict.
The FAL receipt is $0.3954; built-in per-image cost is unavailable. Media and
private generation records remain ignored, with no publication authorization.
Documentation and scoped whitespace checks pass.

## P77/P78 — dedicated infernal background

The 49-beat episode passes headless and native checks at 1280×900 and
2560×1800 with `keeper_hall` as the third background. Assertions cover binding
the new setting behind the black `between_addresses` intertitle, its first
character-free reveal and retention throughout the encounter, background
identity after lab checkpoint replay, and the reading-room return. The new
image aspect ratio also passes camera, impact-shake and viewport coverage.
Logs: `/tmp/afterlight-keeper-hall-ensemble-checks.log` and
`/tmp/afterlight-keeper-hall-ensemble-native.log`, both exit 0 without script or
shader errors. The native run produced 32 captures.

Local snapshots in `qa/keeper-hall-v1/` preserve the hall reveal, Keeper close-up,
and warm-room return. Visual review confirms the chained doors and furnace
floor remain readable under the existing effects, with a clear face and smile.
No shared controller or shader tuning was needed. English/Korean narration and
the location label describe the infernal hall; the paired review matches them.

The built-in image tool produced a calmer original and the P78 infernal edit.
The accepted source is 1496×1051 RGB, despite the larger requested dimensions;
doubled-window rendering enlarges that source and does not add native detail.
An independent `pass` bound to the image digest is recorded in local
`art/rounds/afterlight-keeper-hall-v1/REVIEW.md`. The new PNG was copied unchanged;
the two original location files and all cast art retain their existing digests.
The image tool exposes no per-image cost; no FAL CLI call was made this pass.
Media remains ignored. Documentation and scoped whitespace checks pass.

## P79 — documentation and remaining-work audit

This pass changes documentation only. [CURRENT_STATUS.md](CURRENT_STATUS.md)
separates implemented capabilities, deferred requests, optional directions,
and historical promotion proposals. Current-facing docs now reflect the three
roots, the 49-beat episode, four monologues, Impact Shake, and supplied-voice
playback. Older review and verification records retain their historical scope.

Focused audit checks pass:

- P01–P79 have 79 ordered, unique prompt IDs and 79 matching ledger rows.
  All 214 existing quoted lines are preserved; P51's five reference filenames
  and the exact P79 request are recorded.
- Local file links in the maintained documentation resolve, including
  prompt anchors. Private art, runtime capture, and import-cache directories
  are outside this documentation-link scan.
- English/Korean have 216 matching keys. All 52 paired episode text rows match
  their runtime values, covering the 49 beats and both choice/reply variants.
- All 27 active prepared runtime PNGs decode. Afterlight's ten active images
  match catalog digests, and their source, prompt, and review records exist.
  The unused outdoor candidate remains inactive. The selected opening's MP4,
  source OGV, and runtime OGV match the selection record; the alternate edit
  also remains available locally.
- Repository documentation checks and scoped Git whitespace checks pass.
  No runtime source, asset, or localization values changed in this pass.

The latest gameplay/visual evidence remains the P77/P78 run above. No gameplay
suite, provider generation, publication, or new user art approval occurred in
this documentation audit.

## P81/P82 — solo framed transmission in the relay laboratory

Afterlight's final 56-beat episode passes headless and native checks at
1280×900 and 2560×1800. Eira has six private conversation turns: four operator
lines and two courier replies. Each call turn checks exclusive Eira identity,
hidden standing-cast layer, the portrait feed clipped inside its frame, face
and eye containment, UI clearance, shared host time, English/Korean continuity,
pause, and a complete Presentation Lab round trip. Returning through the black
monologue clears the display identity, geometry, texture, shader clock/strength,
and projection state. Riko remains physical and retains Restless Bounce.

The display is authored by Afterlight, with a code-drawn frame and an existing
hologram shader over the feed. A 1.06x camera move keeps the framed call above
the dialogue; the frame floats from the host's effect clock. No shared shader
or controller API changed. Both location changes are covered by existing black
monologues. The five monologues, four Sigh Puffs, ward repair, later Keeper
encounter, and clean return remain in the main episode.

The native suite produced 40 captures. Five exact captures and an independent
visual review are retained in [transmission-v2/REVIEW.md](../../../games/afterlight/tests/transmission-v2/REVIEW.md).
They confirm readable face and Korean text, a distinct display above the lab
emitter, scanlines confined to the feed, and no display remaining in the returned
group scene. Still images do not by themselves prove motion or pause behavior;
the runtime state checks cover those clocks and restore semantics.

Logs: `/tmp/afterlight-framed-transmission-headless-final-console.log` and
`/tmp/afterlight-framed-transmission-native-console.log`. The updated Walk-Away
integration also passes in `/tmp/afterlight-framed-walkaway-console.log`.
The standard raw-image export warnings remain a local-prototype limitation;
there are no script or shader errors in the completed native run.
The final headless run also exits without ObjectDB leaks after the QA runner
frees the host and allows the audio server three frames to release playback.
This is orderly test teardown; runtime behavior is unchanged.

P81 prepared a full-body Eira and fantasy relay alcove. The user's P82 steering
superseded those drafts with a clean 2048×1536 opaque portrait feed and a
2048×1440 scientific laboratory. Both final images passed independent,
digest-bound review in `art/rounds/afterlight-transmission-v2/REVIEW.md` and were
copied unchanged. The portrait's tiny upper hair tuft reaches its source edge;
the face and main hairstyle remain intact. All pre-existing approved cast and
location files retain their digests. The two P81 drafts remain inactive.

Four FAL submissions at Sunburst `max` cost $1.1677 across P81/P82, with no
provider retries. Known cumulative image spend is $7.9661 of $10; $2.0339 remains.
Earlier built-in image costs are unavailable and excluded from that accounting.
No publication or new user quality approval is inferred. The catalog retains
source, prompt, receipt and independent-review lineage. Media stays ignored.

The archive and ledger have 82 matching IDs. All 225 English/Korean keys match;
the 59 paired story rows agree with runtime values. Active-image/review digests,
local documentation links, repository docs checks, and scoped whitespace checks
pass. No production promotion or ambient-particle implementation occurred.

## P83 — stronger shared TV defaults

Raised default actor strength from 80% to 90%, and the framed Eira feed from
38% to 70%. The shared shader increases scanline contrast, signal fluctuation,
rolling-band brightness, and sparse displacement. Material parameters, explicit
host clocks, source alpha confinement, and the strength-zero bypass retain
their existing contract. This pass generates no art and incurs no spend.

The focused native `qa/hologram_defaults_checks.gd` run passes at 1280×900 and
2560×1800, producing 18 images in `qa/hologram-defaults/`. Pixel comparisons
confirm exact zero-strength rendering, changes confined to the target actor
or portrait feed, and visible variation between frozen clock samples. Tactical
zero comparisons allow the explicitly changed toggle/strength controls; all
other pixels match. A transparent GPU fixture separately proves exact RGBA
zero bypass and no paint outside the original alpha outline at both scales.
Actor material/control independence and default reset checks also pass.

Eira's wide/close compositions retain face containment and dialogue clearance.
The full 56-beat suite remains the P81/P82 integration evidence above; P83
changes only shared shader appearance and default parameters. Pixel evidence
is bound to the shader digest in `qa/hologram-defaults/pixel-checks.json`.
Native log: `/tmp/hologram-defaults-native-console.log`. Existing raw-image
export warnings remain; no script/shader errors or ObjectDB leaks were reported.

Independent [visual review](../../../games/command_link/tests/hologram-defaults/REVIEW.md) passes for eight
shader/capture-digest-bound views. The stronger treatment is clear on blue
source art, with readable faces and no visible spill. It reduces original
skin/eye warmth; still captures do not certify continuous flicker comfort.

The existing routed-input helper passes at five window sizes, including mouse
strength adjustment and keyboard target/toggle/reset. Log:
`/tmp/hologram-defaults-routed-native-console.log`. The full legacy `--validate`
entry was attempted but stops at an unrelated static-dialogue coverage assertion,
“The authored demonstration never uses sigh_puff.” That older fixture expects
every newly available manpu mark; P83 leaves it unchanged. The dedicated shader
and directly exercised input checks pass.

The archive/ledger now have 83 matching IDs. All 225 EN/KO keys and 12 active
image digests remain valid; documentation/link and scoped whitespace checks pass.

```sh
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/godot/games/playground --script res://qa/hologram_defaults_checks.gd
```

## P84 — Waking Eye-Opening variant

The Eye Transition controller adds `waking_opening`: closed, partial peek,
reclosure, closed hold, and full opening. Afterlight authors a 0.22-second peek
to 42% aperture, 0.14-second closure, 0.08-second hold, then a 2.2-second final
opening. The first Nami recovery beat selects it; later ordinary opening cues
retain their mode. The shader and prepared artwork are unchanged.

All seven groups in `qa/eye_transition_checks.gd` pass, including the original
modes, partial-opening bounds, exact endpoints, frame partitioning/large deltas,
independent final-opening duration, configuration isolation, skip/replay,
phase-by-phase JSON continuation, and atomic input rejection. Version 2 stores
the added peek settings; strict import of original version 1 snapshots preserves
their old mode and timing. Log: `/tmp/p84-eye-controller.log`.

The focused `qa/waking_eye_integration_checks.gd` native run passes at 1280×900
and 2560×1800. It reaches the first recovery through normal story inputs,
tests pause, language/menu actions and checkpoint restoration during all four
active phases, and checks skip without skipping the following beat. The lab
exposes four mode buttons, five timing/depth sliders and live edge softness;
initial values and Reset agree with root configuration, tuning applies on
Replay, and the suspended story remains unchanged. Physical mode/replay/skip
buttons work at both sizes. Log: `/tmp/p84-waking-native.log`.
The final focused headless run also passes in `/tmp/p84-waking-headless.log`.
An initial fixture boundary assertion used literal `0.6` instead of the slider's
exact configured duration; reading that duration corrected the test. No runtime
change was required. Headless startup retains the known macOS certificate
diagnostic; all controller/host assertions pass.

Sixteen still captures in `qa/waking-eye/` cover peek, full closure, reopening
and open endpoints for the story and lab at both sizes. Inspected
[lab controls](../../../games/afterlight/tests/waking-eye/lab-peek-1280.png),
[story peek](../../../games/afterlight/tests/waking-eye/story-peek-1280.png),
[reopening](../../../games/afterlight/tests/waking-eye/story-reopening-1280.png), and
[full reveal](../../../games/afterlight/tests/waking-eye/story-open-2560.png) retain the softened edge and
readable portrait/UI. The native check also samples the black center at closure.
Still images show framing; timing and continuation are covered by the running
controller/host checks, not inferred from the images. Native logs report no
script/shader errors or ObjectDB leaks; existing raw-image export warnings remain.

The full 56-beat episode suite was not repeated for this bounded cue variant.
The archive/ledger now have 84 matching IDs, with 230 matched EN/KO keys and
placeholders. Dictionary, story direction and contract documentation reflect
the new variant. No generation, spend, shader rewrite, or module promotion.

```sh
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/godot/games/playground --script res://qa/waking_eye_integration_checks.gd -- --game bishoujo_afterlight --capture-waking
```

## P85–P87 — stronger encounter, world embers, realm waking

Afterlight increases heat, red aura, corruption and finite impact shakes through
game-owned profiles and cues. The strongest resistance shake is 72×54 logical
pixels. Held dialogue uses lower foreground refraction after review identified
duplicate facial contours in the initial candidate. The final independent
[visual review](../../../games/afterlight/tests/keeper-intensity/REVIEW.md) accepts the stronger surroundings,
clear eyes/lips, warm ember flecks and clean return. The requested 7/10 remains
an artistic target, not a calibrated shared-controller parameter.

Ominous Corruption now accepts an optional positive axis-aligned pattern
transform. The story binds its final world camera to both fields, including
shake and zoom. Procedural flecks have varied length, taper, angle, warm cores
and soft glow. Source masks, aura coverage and viewport vignette keep their
existing coordinate ownership; unbound consumers retain local patterns.
No generated particle sprite or general Ambient Particles system is added.

The focused native `qa/keeper_intensity_checks.gd` run passes at 1280×900 and
2560×1800. Thirty final captures in `qa/keeper-intensity/after/` cover seven
encounter samples and both realm waking sequences. The hall starts with no
character or portrait; Nami's return uses her close portrait. Both sequences
prove partial peek, fully black closure, reopening and full reveal. Coverage
during active shakes, final-camera pattern bindings, fixed UI geometry/materials,
pause, English/Korean switching, Lab checkpoint restoration and return cleanup
pass. The initial direct-seek fixture asserted visibility before its first
render; rendering the entered beat fixed those assertions without a runtime
change.

Fourteen original captures remain in `qa/keeper-intensity/before/`. The final
`comparison.json` compares twelve eligible samples at matching clocks and
excludes the hall's changed eye direction from direct intensity comparison.
The clean `only_a_second` frame remains exactly RGB-identical at both sizes.
The first stronger candidate is preserved separately under `p85-initial-tuning`;
the final manifest pins the loaded root, story, beat and shader digests.

The native `qa/corruption_pattern_checks.gd` fixture passes at both resolutions,
with six captures and shader-bound metrics in `qa/corruption-pattern/checks.json`.
At a frozen host clock, translation and 2× zoom preserve exact RGB correspondence
at 24,000 sampled points at 1× and 96,000 at 2×. Comparing the same screen
positions produces a nonzero difference, proving that the visible pattern
moves. Later-drawn UI pixels stay identical. Invalid transform rejection is
atomic; clock/source geometry invariance, reset and clear also pass.
Native logs: `/tmp/keeper-world-waking-verified-native-console.log` and
`/tmp/corruption-pattern-native-console.log`.

The existing Ominous VFX lifecycle fixture passes headless for arbitrary
sprite/area/screen targets, procedural/texture inputs, zero strength, clocks,
pause/reset/cleanup, copy order and coverage. Log:
`/tmp/p85-87-ominous-headless.log`. Native checks report no script/shader errors
or ObjectDB leaks. Existing raw-image export warnings and the headless macOS
certificate diagnostic remain. This is desktop correctness/visual evidence,
not an export or frame-rate benchmark. The full episode input matrix was not
repeated for this scoped encounter pass.

The archive and ledger contain 87 matching requests. Runtime English/Korean
text remains unchanged with 230 matching keys and 59 paired episode rows.
Documentation, terminology and story direction reflect the new cues. No art
generation, spend, production promotion or publication occurred.
Repository documentation checks and all 89 documentation/media-rights tests
pass, along with edited-document links, paired-text and capture/source digest
audits, and scoped whitespace checks. The existing virtual environment runs
these offline checks directly because the default uv cache is sandbox-blocked.

```sh
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/godot/games/playground --script res://qa/keeper_intensity_checks.gd -- --game bishoujo_afterlight
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/godot/games/playground --script res://qa/corruption_pattern_checks.gd
```

## P88 — Radial Sprite Burst

The new shared `presentation/effects/sprite_burst.gd` accepts supplied texture
pools and an emission origin. Seeded directions, outward easing, a short scale
pop, varied rotation and tail opacity define the effect. The host supplies time,
world camera, draw order and interruption policy. The controller has no actor,
dialogue, asset-path or automatic respawn dependency.

Five groups in `qa/sprite_burst_checks.gd` pass headless: deterministic frame
partitioning and texture replacement, aspect/pop/fade/expiry, independent overlap
and cancellation, atomic invalid input rejection, and bounded capacity. Changing
texture-pool size preserves the motion random sequence. Log:
`/tmp/p88-burst-core.log`; final source rerun: `/tmp/p88-burst-core-final.log`.

The focused native `qa/sprite_burst_integration_checks.gd` run passes at 1280×900
and 2560×1800 with 36 captures in `qa/sprite-burst/`. Sena's repair emits exactly
one burst after its authored 0.85-second delay, clears on early advance, and
expires naturally without respawning. Captures sample early emergence, outward
travel, fading and expiry. English/Korean switching, pause, and a Lab detour
preserve the active burst. Its origin is captured in world space; the final
camera affects all emitted sprites while UI stays fixed.

The independent native coordinate fixture checks rendered translation, doubled
size/area under zoom, frozen state across presentation calls, and unchanged UI
pixels. It also compares different texture palettes with equal sampled motion,
checks visible fading, and verifies atomic camera rejection. The Lab's actual
buttons exercise sprite/placement selection, overlapping emission, pause,
zoom, impact shake, clear and return at both resolutions. Its camera moves the
background, actor and both burst layers together. The source/capture manifest
and [visual review](../../../games/afterlight/tests/sprite-burst/REVIEW.md) record the inspected evidence.
Native log: `/tmp/p88-burst-native-final.log`.

The existing full 56-beat episode regression passes headless at both scales in
`/tmp/p88-ensemble-headless.log`. That first run reported two shutdown ObjectDB
instances; a diagnostic verbose rerun also passes and reports no leaks in
`/tmp/p88-ensemble-verbose-console.log`. No burst/controller error was reported.
Native verification reports no script errors or leaks. Existing raw-image
export warnings and the sandbox's headless macOS certificate notice remain.
These checks do not claim exported-game or mobile performance validation.

The request archive and ledger contain 88 matching IDs. All 249 English/Korean
keys and placeholders match; the 59 paired episode rows still match runtime
wording. Documentation checks and all 89 documentation/media-rights tests pass.
No new artwork, paid generation, production promotion or publication occurs.
General Ambient Particles remains separate from this finite radial emission.

```sh
/Users/universe/.local/bin/Godot --headless --path /Users/universe/Documents/shared/stage-gen/godot/games/playground --script res://qa/sprite_burst_checks.gd
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/godot/games/playground --script res://qa/sprite_burst_integration_checks.gd -- --game bishoujo_afterlight
```

## P89 — Background Blackout

The shared `presentation/transitions/background_blackout.gd` fades an independent
black layer between scenery and actors. It supports a held target, continuous
reversal, instant changes, reset and an explicit host clock. The focused
controller checks pass, including exact endpoints and atomic invalid-input
rejection. Log: `/tmp/p89-background-blackout-checks.log`.

Yuzu's solo `the_warning` beat lets the camera settle before starting a
0.45-second fade at 1.0 seconds. Black holds until advancing; the following beat
restores scenery over 0.4 seconds. Native story and Lab checks pass at 1280×900
and 2560×1800, covering midpoint blending, exact black scenery, fixed actor
geometry/material, reversal, early advance, restart, pause, language switching,
Lab detours and actual Lab controls. Captures and the independent
[visual review](../../../games/afterlight/tests/background-blackout/REVIEW.md) record the evidence. Log:
`/tmp/p89-blackout-native.log`.

The prepared actor images have nearly opaque cores rather than alpha 255.
Their rendered colors therefore change slightly with the background as expected
from alpha compositing; the fixture checks that source-derived tolerance without
editing the art. A separate fully opaque sprite fixture verifies exact actor/UI
pixel invariance. Restoring the isolated Lab world reproduces its initial pixels.

The existing full 56-beat episode regression passes headless with no script errors
or ObjectDB leaks in `/tmp/p89-ensemble-headless-console.log`. Documentation checks
and all 89 documentation/media-rights tests pass. There are 89 matching prompt and
ledger IDs, 256 paired English/Korean keys and 59 unchanged paired episode rows.
These are desktop correctness checks, not export or mobile performance evidence.

```sh
/Users/universe/.local/bin/Godot --headless --path /Users/universe/Documents/shared/stage-gen/godot/games/playground --script res://qa/background_blackout_checks.gd
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/godot/games/playground --script res://qa/background_blackout_integration_checks.gd -- --game bishoujo_afterlight
```

## P90 — Quick Approach under Actor Blocking

Afterlight's concrete cast adapter resolves a visible actor's destination and
reuses the existing Motion Curve. `qa/actor_blocking_checks.gd` passes for both
approach directions, stationary recipients, exact held spacing, equivalent
elapsed-time partitions, continuous retargeting, reset/dismissal, atomic invalid
requests, and actor/manpu camera composition. The existing cast-stage integration
checks also pass, preserving fixed-slot handoffs and exit behavior. Logs:
`/tmp/p90-actor-blocking-checks.log` and `/tmp/p90-existing-cast-checks.log`.

The existing full 56-beat episode regression passes headless at both scales in
`/tmp/p90-ensemble-headless-console.log`, with no script errors or ObjectDB leaks.
Quick Approach uses `the_useful_kind`; dialogue wording and the number of beats
are unchanged. The following establishing shot cancels and clears the pair.

The focused native integration passes at 1280×900 and 2560×1800, with 12 captures
in `qa/quick-approach/`. It checks the delayed story move, stationary recipient,
unchanged vertical pose/size/alpha, attached manpu and camera projection, held
endpoint, active pause/language/Lab continuity and early cancellation. Actual
Lab controls exercise either direction and tuning; the three earlier motion
modes still play and reset. The independent [visual review](../../../games/afterlight/tests/quick-approach/REVIEW.md)
records the resulting grouping and readable English/Korean controls. Log:
`/tmp/p90-quick-approach-native.log`. No script errors or ObjectDB leaks were
reported; existing raw-image loading warnings remain. This verifies the desktop
compositions, not general collision handling or exported-build performance.

Documentation checks and all 89 documentation/media-rights tests pass. The prompt
archive and ledger contain 90 matching IDs, the text sets have 266 matching keys
and placeholders, and all 59 paired episode rows match runtime wording. No new
art, provider spend, route, shared module or production promotion is introduced.

```sh
/Users/universe/.local/bin/Godot --headless --path /Users/universe/Documents/shared/stage-gen/godot/games/playground --script res://qa/actor_blocking_checks.gd
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/godot/games/playground --script res://qa/quick_approach_integration_checks.gd -- --game bishoujo_afterlight
```

## P91 — Cast Pan and Layer Pan

The target-neutral Layer Pan sampler reuses Motion Curve and returns one
translation transform. Focused checks pass for interpolation, exact endpoints,
hold, explicit clock, continuous retargeting, independent instances, reset and
atomic invalid requests. Log: `/tmp/p91-layer-pan-checks.log`.

Afterlight applies that transform only to its cast presentation. The existing
56-beat episode regression passes headless at both scales, with no script errors
or ObjectDB leaks in `/tmp/p91-ensemble-headless-console.log`. Riko, Yuzu and Riko
are framed in succession during three existing relay turns; local speaker
animations remain active and the following monologue clears layer framing.

The focused native run passes at 1280×900 and 2560×1800 with 14 captures and six
runtime source hashes in `qa/cast-pan/manifest.json`. Isolated background pixels
remain identical while the cast moves. Actor-local rectangles and spacing remain
unchanged; the combined transform positions all actors/manpu consistently and
centers the selected actor at X=640 without moving the wide camera. Active pause,
language switching and Lab checkpoint restoration preserve the pan. The Lab
checks target switching, mid-motion retargeting, Home, Reset, controls and
composition with a simultaneous local Quick Approach. Its interface remains
fixed. See the independent [visual review](../../../games/afterlight/tests/cast-pan/REVIEW.md) and
`/tmp/p91-cast-pan-native.log`. Existing raw-image warnings remain; there are no
script errors or ObjectDB leaks. This is desktop composition evidence, not
exported-build performance or arbitrary layer hierarchy validation.

The dictionary and host contract distinguish Cast Pan, local Actor Blocking and
world-camera movement, with an official Ren'Py named-layer reference. Ordinary
dictionary cues support actor/anchor targeting or numeric offset arrays; there
is no new text parser or public scenario schema. Documentation checks and all 89
documentation/media-rights tests pass. All 91 prompt/ledger IDs, 274 paired text
keys and placeholders, and 59 paired episode rows match. No new art was needed.

```sh
/Users/universe/.local/bin/Godot --headless --path /Users/universe/Documents/shared/stage-gen/godot/games/playground --script res://qa/layer_pan_checks.gd
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/godot/games/playground --script res://qa/cast_pan_integration_checks.gd -- --game bishoujo_afterlight
```

## P92 — looping Manpu and custom sampling

The shared sampler adds held-step interpolation and opt-in rotation. Manpu
cues can pin their own preset and supplied frame IDs; per-pair loop clocks
repeat without entering the finite one-shot pool. The optional `sample_with`
hook accepts bounded overrides from a host-owned callable. Focus/exit reject
unsupported rotation tracks and retain their existing behavior.

`qa/manpu_loop_checks.gd` passes exact step/frame boundaries, two/three-frame
playback, equivalent elapsed-time partitions, independent phases, replay,
removal, invalid catalog/cue rejection, custom sampling isolation/fallback,
and the legacy Manpu/Actor Focus/Character Exit controller checks. The existing
one-shot controller and integration checks also pass. Logs:
`/tmp/p92-manpu-loop-checks.log`, `/tmp/p92-one-shot-regression.log`, and
`/tmp/p92-one-shot-regression-console.log`.

The full 56-beat Afterlight regression passes headless at both logical/output
scales. The final verbose run reports no script errors or ObjectDB leaks in
`/tmp/p92-ensemble-verbose.log`. One preceding run reported four objects at
shutdown after passing its assertions; that warning did not reproduce in the
verbose rerun or focused native run. Existing raw-image export warnings remain.

The final focused native run passes at 1280×900 and 2560×1800 with 14 captures,
ten current runtime source hashes, and an empty error list in
`qa/looping-manpu/manifest.json`. It verifies both 2D renderers, raster selection,
centered rotation and one camera application, atomic unavailable-art rejection,
loop/puff coexistence and independent expiry, active story pause/language/Lab
continuity, and actual Lab Replay/Remove/frame-mode controls. The real Sprite3D
preview preserves frame choice and camera-facing rotation at a 25° camera angle.
The capture helper forces rendering so backgrounded native windows do not stall
on `frame_post_draw`. Log: `/tmp/p92-loop-native-console.log`.
See the [visual review](../../../games/afterlight/tests/looping-manpu/REVIEW.md) for artifact-bound evidence
and the distinction between direct adapter fixtures and normal study controls.

Three existing story marks select `step_loop`: Nami's early sweat reaction,
Riko's impatient arrival, and the reunion sparkle. The Lab also cycles existing
different marks as explicit frame fixtures; dedicated matching animation art
has not been generated. There is no provider spend, new route or production
module promotion. The project still has 22 studies, 56 beats and 59 paired
review rows. All 92 prompt/ledger IDs and 281 bilingual keys/placeholders match;
episode wording remains identical. Documentation checking and all 89
focused documentation/media-rights tests pass.

```sh
/Users/universe/.local/bin/Godot --headless --path /Users/universe/Documents/shared/stage-gen/godot/games/playground --script res://qa/manpu_loop_checks.gd
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/godot/games/playground --script res://qa/looping_manpu_integration_checks.gd -- --game bishoujo_afterlight --language ko
```

## P93 — Sweat Drop Fall

Sweat Drop Fall is a scalar-track preset in the existing One-Shot Manpu
controller. The prepared sweat raster falls from the temple with no lateral
travel and expires after 0.75 seconds. The existing one-shot controller check
now also verifies its downward direction, finite lifetime, independent duplicate
instances and coexistence with Sigh Puff and persistent loops. It passes, as
does the legacy Manpu animation runtime check with the appended catalog entry.
Logs: `/tmp/p93-one-shot-checks.log`, `/tmp/p93-manpu-checks-console.log`.

The existing one-shot integration script's `--falling-sweat-only` branch passes
six native captures at 1280×900 and 2560×1800, with seven current runtime source
hashes and an empty error list. It checks Sena's and Riko's after-reveal story
emissions, correct raster binding, exact downward displacement on a fixed actor,
expiry/node cleanup, pause/language continuity, and the same event in the angled
3D preview. A drop and a later Sigh Puff expire independently while a persistent
loop remains. See the [visual review](../../../games/afterlight/tests/falling-sweat/REVIEW.md) and
`/tmp/p93-falling-sweat-native-console.log`. Captures remain local and ignored.

The full 56-beat episode passes the existing headless 1x/2x regression in
`/tmp/p93-ensemble.log`, with no script errors or leaked-object warning. Existing
raw-image export warnings remain. Documentation checking and all 89 focused
documentation/media-rights tests pass. The 93 prompt/ledger IDs, 284 bilingual
keys/placeholders and 59 paired review rows match. Story wording, the four
Sigh Puff cues, the three P92 loop examples and all 22 study routes are retained.
There is no new controller, asset generation, provider spend or promotion.

```sh
/Users/universe/.local/bin/Godot --headless --path /Users/universe/Documents/shared/stage-gen/godot/games/playground --script res://qa/one_shot_manpu_checks.gd
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/godot/games/playground --script res://qa/one_shot_manpu_integration_checks.gd -- --game bishoujo_afterlight --language ko --falling-sweat-only
```

## P94 — Afterlight Fingertip Contact

Nami's new `a_touch_that_stays` beat follows the waking return and leads into
her existing relief dialogue and Sigh Puff. The dedicated pose reuses
[Point Contact](../../../games/command_link/presentation/interaction/README.md), extracted from the tactical
stage. Each host still owns its image geometry, input, readiness, response and
story progression. The Afterlight checkpoint records confirmation time so a
Lab detour restores the remaining 0.45-second feedback without synthetic input.

One explicitly authorized FAL Sunburst edit at maximum quality generated the
2048×1536 transparent pose. The provider receipt reports **$0.2822**, leaving
**$4.7178** of P94's separate $5 budget. The source and installed PNG share SHA-256
`867fa1903e83bf2ff2231e5dcbdcf8b09e1ddf45af3de6421c92633be56a6e3a`.
The [generation record](../../../games/command_link/art/rounds/afterlight-contact-v1/records/nami-contact.json),
[prompt](../../../games/command_link/art/rounds/afterlight-contact-v1/prompts/nami-contact.txt), and
[independent art review](../../../games/command_link/art/rounds/afterlight-contact-v1/REVIEW.md) record the
identity/style check, exact image, and manually measured fingertip at (948,882)
with a 54-pixel radius. This is a requested new local addition; it does not
replace earlier approved art or imply user quality/publication approval.
All fifteen pre-existing catalog files retain their digests.

The source has real transparency, with alpha 0–254 and 40.16% fully transparent
pixels. Its upper hood touches the top edge and some pink edge glow is baked
into the image. Native close framing keeps the face and finger clear; this
artwork glow is distinct from the reusable Actor Halo effect.

Point Contact's focused geometry/signal/reset checks pass in
`/tmp/p94-point-contact-checks.log`. Existing composition and Command Link
route suites pass in `/tmp/p94-contact-composition.log` and
`/tmp/p94-command-link-routes.log`, including all four mission branches,
contact gating, checkpoints and scaled input. The composition fixture was
corrected to include the already-existing ninth manpu, Sigh Puff.

The full Afterlight regression passes all **57 beats at both 1x and 2x** in
`/tmp/p94-ensemble-console.log`. It includes the required contact gate in normal
progression and preserves the late Sigh Puff/Sweat Drop scenes. Earlier seek
helpers now fulfill contact rather than skipping this new requirement. The
headless run retains the known macOS certificate diagnostic and two ObjectDB
instances reported at exit; it has no script or assertion failures. This pass
does not claim exported-build validation; existing loose-image export warnings
remain.

[Focused native contact checks](../../../games/afterlight/tests/afterlight_contact_checks.gd) cover real
viewport mouse/touch input, Space and missed-hit gates, one acknowledgement,
finite feedback, pause, English/Korean switching, Lab detours before/after
confirmation, and restart cleanup. Final capture evidence is recorded in
[the contact review](../../../games/afterlight/tests/contact-afterlight/REVIEW.md).

The native manifest binds six runtime/text sources and the new portrait, with
six captures and no assertion, script or exit-leak errors. Its SHA-256 is
`f342c0c49b24e41f287330276eff74496510db17c8e2e4e451350e9c4c405a71`.
Root independently inspected the ready and feedback frames: the ring sits on
the fingertip, the face remains clear, and Korean dialogue stays readable.
Documentation policy checks and all 89 documentation/media-rights tests pass
using the existing virtual environment; `uv run` could not access its external
cache in the sandbox. The 94 prompt/ledger entries, 285 paired text keys, 60
review rows, 13 active images and all preserved art digests are consistent.

## P95–P96 — Afterlight voiceovers and story-edit tolerance

[Focused voiceover checks](../../../games/afterlight/tests/voiceover_checks.gd) independently classify the
actual 57-beat English/Korean episode: 40 recorded text IDs per language across
six speakers, including both alternate replies, and 18 explicitly unvoiced
beats per language. The protagonist's narration beside Nami's contact portrait
stays unvoiced; Nami's offscreen rescue speech is voiced. Choice labels, menus
and Lab text are excluded. The authoritative inventory has 116 localized
records: 80 generated and 36 intentional `none`.

Provider-free stream fixtures verify full-text voice presentation, cinematic
caption timing, fallback and explicit silence, source/casting freshness,
pause, language restart, no typing overlap, no automatic story advance,
alternate replies, contact gating and restart. Lab restores the current clip's
position and completed state while retaining its existing resume-on-return
policy. Removing beats leaves old, well-formed scripts, overrides and recordings
inactive and visible in the offline status report, without blocking gameplay
or binding removed audio.

The native run exposed and then verified a cursor fix: Godot reports a paused
player as not playing, so the shared audio utility now snapshots its actual
position before pausing. The final proof retains a nonzero 0.1857596-second
cursor across pause and seeks exactly to the saved 0.1625397-second cursor after
a Lab detour. A checkpoint with a different recording revision starts at zero.

All 80 installed MP3s pass current source/hash matching and decode in Godot.
Actual English and Korean mixer captures produce nonzero PCM; four native
full-text/pause frames at 1x/2x were visually reviewed. The final native log
`/tmp/p95-voiceovers-native-console.log` has no assertion, script or exit-leak
errors. The evidence SHA-256 is
`672403cf22524989be50eb11ef5c17aced91dc62bd6c5ff22a9bd647c5a0f42c`;
[the focused review](../../../games/afterlight/tests/voiceovers/REVIEW.md) records its ten source hashes,
80 recording entries, frame references and mechanical audio measurements.
**Listening verdict remains not performed**; decoding and mixer levels do not
prove pronunciation, casting or emotional delivery.

The full 57-beat ensemble run passes both viewport sizes, including English/
Korean switches, required contact, the late Manpu events and Lab roundtrips,
in `/tmp/p95-ensemble-console.log`. The original Text Reveal Audio suite passes
in `/tmp/p95-text-fallback-console.log` with an explicit missing-recording
fixture, preserving typewriter coverage after voice assets are installed.
Headless checks retain the known macOS certificate diagnostic and loose-image
export warnings, with no script/assertion failures or exit leaks in these runs.

## P97 — Afterlight autoplay

[Autoplay checks](../../../games/afterlight/tests/autoplay_checks.gd) pass headless and in the native renderer.
They traverse all 57 beats using the fallback text path, choose the authored
default, require one real contact acknowledgement, and hold at the ending.
Prepared PCM fixtures separately prove that a playing voice blocks the timer
and actual audio completion releases a fresh reading delay. Reveal and finite
cinematic completion also precede the delay, including during large frame steps.

The tests cover the 3-second reading delay, 5-second default-choice countdown,
manual alternate selection, absent defaults, explicit input gates, pause,
language changes, old checkpoints, and an actual Lab round trip. Mouse and
focused Space activation toggle autoplay without advancing the story, including
over black monologues. Ten native captures at 1280×900 and 2560×1800 were
reviewed for English/Korean labels, clear countdowns, and persistent top controls.
[The focused review](../../../games/afterlight/tests/autoplay/REVIEW.md) records the final source hashes and
zero-error native evidence. No new recording or listening review was performed.

All 285 previous text values in each language are unchanged; three paired UI
keys bring each set to 288. The current offline voice status remains 80 ready,
36 intentional-none, with zero pending, missing, failed or stale recordings.
Documentation checks and 89 focused documentation/rights tests also pass.

## Ambient Particles and Transmission Voice (P99)

[Focused source-bound evidence](../../../games/afterlight/tests/ambient-transmission/REVIEW.md) records the
completed two-feature pass: seeded sustained particles with explicit world
framing and cleanup, plus private runtime voice processing coordinated by the
host with Eira's projection state. Three native integration groups and eight
main-story captures pass at 1280×900 and 2560×1800; eight more Lab captures
cover the two new studies and menu. Root inspected the rendered compositions.

Emitter contract checks pass deterministic reconstruction, art substitution,
bounds, stop/drain and invalid inputs. Native CoreAudio checks verify true
dry/zero bypass, frequency filtering, dry typing, no clipping and immutable
recordings. [Audio evidence](../../../games/afterlight/tests/transmission-audio/REVIEW.md) explicitly leaves
listening unreviewed. Scene/pause/language/replay/Lab continuity and stop-before-
bus-removal teardown pass. Fresh autoplay and voiceover regressions preserve
historical reports: all 57 beats, 80 ready recordings and 36 intentional skips.
The full ensemble and all 24 Lab studies pass their existing checks. Existing
platform/raw-image warnings remain; the accelerated ensemble reports two exit
ObjectDB instances, while the focused native integration has no leak warning.

Twenty-four new paired Lab labels preserve the previous 288 values, for 312
keys in each locale. Story wording, source recordings and standing framing are
unchanged. Provider operations and spend for this pass are zero. These checks
do not ratify upstream packages or establish export/mobile performance.

## Canonical actor anatomy / visual geometry proposal (P100)

This pass is documentation-only. The [canonical proposal](../../../../docs/research/actor-anatomy-visual-geometry.md)
compares primary-source landmark conventions, records an incumbent-source audit,
and defines an unratified sparse geometry sketch and future VLM-only evaluation.
Independent read-only reviews checked anatomy semantics, region/point availability,
coordinate conventions, calibration transfer and current runtime-path accuracy.
No assets were annotated, no provider calls ran, and no runtime or generation
contract changed. The illustrative JSON is syntactically checked only; there
is no implemented schema validator or annotation-reliability result. Repository
documentation checks and the scoped rights/docs tests pass; game tests were
not rerun for this prose-only change.

## Code-first SDK design and full request triage (P101–P106)

Documentation-only source/design audit. The [SDK design](../../../../docs/research/game-presentation-sdk-design.md)
classifies 36 feature groups and defines a proposed self-contained addon,
starter/example ownership, content-loading work and component-specific limits.
The [triage](../../../../docs/research/game-presentation-sdk-triage.md) covers all 106 exact
archived prompts, including the latest successor/Scenario/scope decisions.
Three independent audit assignments covered P01–P40, P41–P75 and P76–P100;
two subsequent design reviews checked source truth and package/lifecycle
boundaries. Their Quick Approach census and eye-closure-history findings were
addressed. No runtime, shader, asset or provider code changed.

Verification: documentation checker passed (183 Markdown files, 247 public text
files, two generated-media entries); scoped media-rights/documentation tests
passed, **89 tests**. A one-off coverage check confirmed 106 unique ordered IDs
in each of archive, ledger and triage, and 36 unique feature IDs with no unknown
feature references. Whitespace checks passed. These are documentation checks;
no new gameplay, installation, export, visual or listening result is claimed.
Package assembly, SDK release, runtime promotion, legacy deletion, automatic
annotation and generation integration remain unperformed.

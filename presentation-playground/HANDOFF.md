# Game Presentation SDK / Afterlight — agent handoff

Prepared 2026-09-11 for P108. The user is changing agents because of usage limits.
**P107 implementation is complete. There is no active unfinished feature request.**
Read this document, inspect the current checkout, then continue with the user's
next instruction. Do not restart the promotion review or implement deferred work
merely because it appears here. This handoff changes documentation only.

## Workspace and current status

- Repository: `/Users/universe/Documents/shared/stage-gen`.
- Development Godot project: `presentation-playground/`. The directory name and
  launch commands are retained; it is no longer under ignored `spikes/`.
- Installable SDK: `presentation-playground/addons/game_presentation/`, installed
  into another project at `res://addons/game_presentation/`.
- Local package version: `0.1.0-canary.1`; 25 public script entry points and two
  directly host-bound shaders. It is not a published or stable release.
- Verified engine: `/Users/universe/.local/bin/Godot`, version
  `4.7.2.stable.official.ed1daf0bf`, macOS desktop Compatibility renderer.
- Three existing roots: `command_link`, `bishoujo_afterlight`, `presentation_lab`.
  Command Link remains the default when no `--game` is supplied. Use the explicit
  Afterlight command below for the user's current main game.
- Git snapshot at handoff: branch `main`, HEAD `28436b1b`. **That commit is not a
  checkpoint containing this work.** The checkout has extensive staged,
  unstaged and untracked work; recheck status before editing.

No commit, push, tag, release, media publication or paid generation occurred in
P107/P108. Do not stage everything, reset files, clean the tree or discard missing
old paths: source moves appear as deletions plus new addon files, and earlier
turns left many staged additions. Preserve work from other tasks. In particular,
`docs/spec/portrait-motion.md` and `docs/spec/portrait-visemes.md` have concurrent
changes outside this task; `docs/README.md` also has mixed ownership.

## Decisions that must survive the handoff

1. **Code-first direct successor.** Reuse the implementation that already proves
   the experience. The SDK is primary; supported stable/canary surfaces must be
   explicit. There is no requirement to rebuild this within the incumbent runtime.
2. **Scenario is secondary and experimental.** It can lag, break, be bypassed or
   be abandoned while features evolve. Do not make serialization constrain SDK
   vocabulary or require every callback/feature to fit a common interpreter.
3. **The whole UI belongs to its host/route.** Layout, theme, hierarchy, controls,
   story and choreography are authored per game. Share useful utilities and
   independent behavior, not a common game UI, skin contract or mandatory facade.
4. A discoverable master composition per game is desirable. It may delegate to
   supporting files. Flexibility matters more than line count or minimizing glue.
   Do not impose a universal effect lifecycle or one module per named effect.
5. Legacy standalone point-and-click parity, the old case/room demos and a second
   genre proof are not SDK promotion prerequisites. Those old games have **not**
   been deleted. Point Contact remains a useful interaction in both current games.
6. This Godot-native SDK stays separate from gnode, generation recipes and the
   engine-free families under `godot/`. The host contract now states applicability
   explicitly. Do not migrate or rewrite those systems without another request.
7. Preserve the fixed logical canvas (1280x900), native window-resolution
   rendering, world-space actor/Manpu/particle framing, and screen-space UI.
8. Keep source identifiers/comments/diagnostics English. Afterlight's dedicated
   EN/KO text sets are explicitly authorized. Preserve approved display text and
   artwork; new image candidates require user review before replacement.
9. Record exact prompts and short outcomes. End every turn's summary with a game
   launch command; when implementing, share it early so the user can play in parallel.

Older promotion-memory notes and historical review documents predate P101–P107.
Their Scenario-first, second-genre or spike-only recommendations do not override
these newer accepted decisions.

## Read in this order

1. [Local guardrails](AGENTS.md), [current inventory](CURRENT_STATUS.md), and
   [implemented topology](TOPOLOGY.md).
2. [SDK README](addons/game_presentation/README.md),
   [public API](addons/game_presentation/API.md), and
   [canary manifest](addons/game_presentation/sdk.json).
3. [Packaging and external content](PACKAGING.md),
   [starter](starter_source/README.md), and
   [P107 verification](QA.md#sdk-package-and-content-boundary-p107).
4. [Exact prompts](USER_PROMPTS.md) and [concise request ledger](REQUESTS.md).
   P01–P106 are classified in the
   [complete design triage](../docs/research/game-presentation-sdk-triage.md).
   [SDK design](../docs/research/game-presentation-sdk-design.md) records why the
   boundaries were selected; current package docs describe the implemented API.
5. [Terminology dictionary](TERMINOLOGY.md) for effect names and example use cases.

## What P107 implemented

The reusable source was moved directly, with its shader dependencies, neutral
catalogs and existing UID sidecars, into one addon. All runtime references were
updated; there are no compatibility copies of old controller implementations.
The package has 73 files, including its own API/usage docs and BSD license.

| Addon directory | Responsibility |
| --- | --- |
| `motion/` | Scalar tracks, motion curves, layer translation |
| `actors/` | Actor Focus, Manpu animation, character exits, bounded cast handoff, neutral presets |
| `camera/` | Dialogue focus, establishing shot, walking approach, drift, impact shake |
| `transitions/` | Eye Opening/Closing/Blink/Waking and Background Blackout |
| `effects/` | Actor Halo, refraction/corruption, shader dependencies |
| `effects/particles/` | Radial Sprite Burst and sustained Sprite Particle Emitter |
| `text/` | Stable-ID text lookup and intertitle reveal state |
| `audio/` | Supplied voice/typing playback and isolated transmission DSP |
| `interaction/` | Point Contact hit test and confirmation |
| `content/` | Optional confined local JSON/image/audio/video loader |

Holographic Projection and Lens Flare are also direct public shader entry points;
no unnecessary controller wrapper was introduced. Walk-Away, Restless Bounce,
Sigh Puff and Sweat Drop Fall are motion presets. Quick Approach, Cast Pan,
location labels, ordinary sprite blinking, title video, autoplay and story cue
coordination remain host compositions.

Concrete `presentation/stage.gd`, its profile/overlay, opening, tactical UI and
curve graph remain example integration code. Afterlight owns its independent
`games/bishoujo_afterlight/root.gd`, `story.gd`, `story_beats.gd`, `cast_stage.gd`,
content adapter, localization and voice policy. Lab owns focused demonstrations.

`starter_source/` is an editable small VN called **The Signal Room**, with one
master `main.gd`, original procedural placeholders, two reconverging replies,
mandatory contact, pause, camera/Manpu/audio and a burst. Its `.gdignore` prevents
duplicate imports in this workspace. The assembler copies it and the unchanged
addon into a separate project, omitting that ignore file. The SDK requires no
Python runtime, example media, provider credentials or editor-plugin activation.

Track source UID sidecars with their owners. `.godot/` is disposable cache.
The SDK closure check verifies its own script/shader sidecars. Historical QA
scripts are largely outside the editor's ordinary import scan; do not mistake
that for missing runtime-package UIDs.

## Content and voice continuity

Both examples and Lab accept `--content-root /normalized/absolute/directory`.
The external directory mirrors their existing host bindings:

```text
assets/                                  Command Link art, contact layout, Manpu, OGV
games/bishoujo_afterlight/assets/        Afterlight cast and backgrounds
games/bishoujo_afterlight/text/          English and Korean display text
games/bishoujo_afterlight/voice/         Policy, casting, overrides and manifest
art/voiceovers-p95/clips/{en,ko}/         Bound MP3 recordings and provenance
```

All paths are relative to the same content root. This layout is an example-host
convention, not an SDK schema.
Bindings are confined relative paths. No URLs, traversal or symlink escapes.
Use `/private/tmp`, not the `/tmp` symlink, in external runtime-root commands.

Without an override, current prepared project media remains usable. The resource
backend preserves raw source pixels when available and falls back to imported
resources when only Godot remaps exist. Imported-only images honor their import
settings; exact source parity can use external raw files. The files backend never
falls back to a different root. JSON/runtime-named media must be included in exports.
Raw `.ogv` decoding completes asynchronously in the host's video player.

Afterlight remains a 57-beat bishōjo ensemble adventure, not a dating simulator.
There are 80 prepared character recordings (40 per language) and 36 localized
entries explicitly marked no-voice for the protagonist. Voices, alternate replies,
text, source revisions, pause/replay, language switching, autoplay, required input
and Lab continuity were preserved. The game loads recordings only; generation,
refresh and artistic retakes never occur during play/status/replay. Manual refresh
requires a new user instruction. Cached recordings still recheck source hashes.
No new listening approval is claimed.

The shell scopes Command Link's opening-video option to that host, while preserving
content root and language across switches. Bare `--content-root` arguments refuse
cleanly. Command Link still loops its opening and continues only on explicit click/tap.

## Evidence and actual limits

P107 validation is complete; do not repeat every historical check just to resume.
Run focused checks when the next edit affects a boundary.

- SDK closure: 37 source/resource files, 13 internal literal dependencies,
  complete unique package source UIDs; all 73 installed files matched source.
- 21 existing headless/controller/Command Link route suites passed. A stale
  Walk-Away test was corrected from five scalar channels to the existing six;
  runtime animation was unchanged.
- Native Halo, corruption coordinates, hologram defaults and Ominous VFX passed.
- External Afterlight matched source pixels/mipmaps, all 80 recording bytes and
  revisions, and 36 explicit no-voice entries. Full episode, autoplay, language,
  transmission and cross-game option checks passed.
- Native EN/KO mixer output and full subtitles passed; native required contact
  passed with real mouse/touch at 1280x900 and 2560x1800, including pause/Lab/replay.
  Final native logs were clean. This is playback evidence, not a listening verdict.
- Starter full flow passed in a fresh project and from its 177,468-byte PCK,
  both headless and native. Source checks covered 1x/2x and independent instances.
  No standalone native executable was built; export-template/platform coverage
  beyond the tested desktop setup is unproven.
- The credential-free repository gate ran all 30 steps: 27 initially passed.
  Two checker-format/lint findings and the source-archive text-size allowance
  were corrected and rechecked. The full test run had 2,829 passes and one
  archive-size failure; the subsequent targeted archive/starter suite passed
  nine tests. Documentation/rights checks and eight content-copy tests passed.
  Do not describe this as a second clean full-gate run; that was unnecessary.
- The Python sdist allowance was narrowly raised after inspecting added anatomy/
  SDK research text. Both Python distributions now explicitly exclude this Godot
  workspace. SDK-owned Python tests live under `qa/python/`, not in Python's sdist.

Local ignored evidence (may be absent in another checkout):

- `qa/sdk-package/starter-validation.json`: exact source/assembly/PCK hashes,
  reproduction commands, native checks and limitations.
- `qa/sdk/content/`: external-content, voice, autoplay, native audio and contact.
- `/private/tmp/sdk-component-checks-1789105904/final-results.json`.
- `/private/tmp/sdk-native-checks-1789105983/final-results.json`.
- `/private/tmp/sdk-full-offline-p107.log` and
  `/private/tmp/sdk-packaging-final-p107.log`.

Approved game images/audio and generation working files are local/ignored; Git
alone does not transfer them to another machine. Preserve existing files and
provenance. `prepare_example_content.py` makes a separate local prepared-content
copy without generation. A local copy is not media-publication authorization.

## Deliberately unfinished, not current blockers

- **Anatomy/visual geometry:** the
  [canonical proposal](../docs/research/actor-anatomy-visual-geometry.md) is
  unratified. Sparse COCO landmark vocabulary, explicit missing/occluded states,
  source/crop geometry, calibration and host attachment rules are proposed.
  A future general-purpose VLM evaluation is planned; no SAM/pose dependency,
  paid annotation call, runtime annotation or generation integration was done.
  Existing manual anchors remain valid and no reliability has been demonstrated.
- **Standing actor framing/calibration:** explicitly deferred by the user.
- **Scenario adapter:** experimental secondary surface, not implemented by P107.
- **Legacy retirement/upstream generation integration:** excluded from this pass;
  do not delete or reconcile old games automatically.
- **Stable release/publication:** not authorized. Current canary source is ready
  for further code-authored features; release support promises require a separate
  explicit decision. Persisted cross-version saves and arbitrary 3D/rotated
  composition are not promised.

The existing cast-handoff controller intentionally remains three registered actors,
two occupied slots and a 1280-wide stage. Most visual samplers are host-clocked;
audio nodes have their own pause/stop lifecycle. Snapshot methods do not uniformly
mean restorable durable state. Read each actual contract before composing it.

## Useful commands

Run the user's main game (Korean; use `en` for English):

```sh
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/presentation-playground -- --game bishoujo_afterlight --language ko
```

Run the independent Lab:

```sh
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/presentation-playground -- --game presentation_lab
```

The verified local starter and external copy still existed at handoff. They are
scratch outputs and can be recreated into a **new** directory:

```sh
/Users/universe/.local/bin/Godot --path /private/tmp/game-presentation-starter-p107
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/presentation-playground -- --game bishoujo_afterlight --language ko --content-root /private/tmp/game-presentation-content-p107
```

From the repository root, assemble a fresh starter/content directory if needed:

```sh
python3 presentation-playground/tools/assemble_starter.py --output /private/tmp/my-next-vn
python3 presentation-playground/tools/prepare_example_content.py --output /private/tmp/my-next-content
/Users/universe/.local/bin/Godot --headless --editor --path /private/tmp/my-next-vn --quit
```

Focused checks, when relevant:

```sh
python3 presentation-playground/tools/check_sdk_package.py
.venv/bin/python -m pytest presentation-playground/qa/python/test_starter_assembly.py presentation-playground/qa/python/test_example_content.py -q
.venv/bin/python scripts/check_docs.py
```

The normal required Python gate is `uv run python scripts/check.py`. In this
sandbox the default uv cache was inaccessible; the completed invocation used
`UV_CACHE_DIR=/private/tmp/stage-gen-uv-cache uv run --no-sync python scripts/check.py`.
Native macOS Godot checks hung under the default sandbox's LaunchServices access;
approved local native execution worked. Do not claim a native result from a
hung process or confuse headless decoding with listening.

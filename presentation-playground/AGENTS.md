# Presentation Playground development

P106 establishes the [SDK successor design](../docs/research/game-presentation-sdk-design.md)
and [historical request triage](../docs/research/game-presentation-sdk-triage.md).
P107 implements the canonical code-first addon at `addons/game_presentation/`.
Keep it dependency-closed, including shaders, catalogs, documentation and source
UIDs. SDK code must not import game roots, complete UI, Scenario, assets or provider
code. The source-only starter and complete games consume that one implementation.
The folder name is retained for launch compatibility; do not reintroduce duplicate
controllers under the former presentation directories.

Read [CURRENT_STATUS.md](CURRENT_STATUS.md), [TOPOLOGY.md](TOPOLOGY.md), and
[PACKAGING.md](PACKAGING.md) for current responsibilities and clean-copy checks.
Scenario is experimental and secondary. No universal host UI or effect lifecycle
is implied. P100 anatomy and standing framing remain deferred; upstream generation
and engine-free gameplay contracts are separate. No release is authorized merely
by changing the local SDK or its canary metadata.

- Favor practical flexibility. Judge components by explicit responsibilities,
  dependencies, state, and contracts. Integration size and file count alone are
  not reasons to refactor.
- Keep game story, cast/art bindings, direction, and decisions in its game root
  and supporting files. One discoverable master composition per game is useful;
  forcing every implementation into that file is not required.
- P64 authorizes English/Korean text values in Afterlight's dedicated JSON sets
  and paired story review. Keep code identifiers, comments, and diagnostics in
  English. Use stable text IDs; language changes must preserve the current beat,
  effect state, and actor/choice identities. The host owns fonts and language UI.
- The host/route owns its complete UI: hierarchy, controls, layout, theme/art,
  and action wiring. Configure it manually per game. Share optional utilities
  or independently reusable behaviors, not a whole game UI, interchangeable
  view contract, or skin framework. Similar layouts alone do not justify sharing.
  Existing stage/opening UI is concrete integration to untangle when customized;
  it is not a mandatory interface for other games.
- Reuse the existing controllers. Shared behavior must not import a game root,
  assume its cast or story, or depend on another game's mutable state. Declare
  component dependencies; Godot-specific behavior is allowed here.
- Treat `presentation/stage.gd` as a concrete integrated presenter. Adapt or
  extract at the boundary required by a feature. Avoid copying common behavior
  or inheriting Command Link's mission to create another game. Do not require a
  universal interface, second complete game, or package extraction first.
- For new presentation behavior, make inputs/outputs, time ownership, coordinate
  space, completion, interruption/reset, and any pause/resume limits explicit.
  Use the component's own API; do not impose a common lifecycle where it does
  not fit. Compose from base transforms and preserve final background coverage.
- Keep the fixed logical canvas and native-resolution window rendering. Actor
  effects and manpu follow world framing; dialogue and controls stay in screen
  space. Add a focused check when those boundaries change.
- Walking Approach (#2), Camera Drift with an authored portrait detail shot (#3),
  and Intertitle (#5) are implemented in Bishōjo: Afterlight. P63 uses intertitles
  for protagonist monologues and adds Actor Halo. The detail framing excludes
  the face; it does not turn the character into a black silhouette. P73 adds
  supplied-voice playback and the built-in typing fallback. P95/P96 add localized
  Afterlight voice policy, recording bindings and a manually invoked preparation
  pass. The protagonist is explicitly unvoiced; never generate or refresh speech
  during gameplay, replay, source edits, or status inspection. Preserve approved
  display text and keep optional speech-only direction in the host's voice data.
  Source revisions identify stale recordings for a later user-requested refresh.
  P99 implements Ambient Particles (#4) using the target-neutral Sprite Particle
  Emitter, and Transmission Voice as runtime audio processing. Keep particle
  presets and visual/audio coordination host-owned; never regenerate recordings
  to change a runtime effect. Standing-cast framing parameters remain explicitly
  deferred. Add behavior and necessary integration
  together, with a focused demonstration and appropriate checks. Preserve both
  stories and the independent Presentation Lab.
- Record exact requests in USER_PROMPTS.md and short outcomes in REQUESTS.md.
  Keep CURRENT_STATUS.md aligned with the implemented source and remaining work;
  distinguish deferred requirements from optional ideas and superseded directions.
  Maintain TERMINOLOGY.md with each new effect's name, scope, example use case,
  and demonstrated/deferred status; do not infer module boundaries from names.
  End each turn's summary with the game's launch command from README.md.
  When an in-progress game is runnable, share its command early so the user can
  try it in parallel; this does not require stopping verification work.

- Afterlight art revisions require the user's visual review before replacing
  active assets (P56). Generate candidates, show rendered previews, and await
  explicit selection/approval. Independent technical or visual review does not
  replace the user's quality decision. Preserve the active game meanwhile.

- P67/P68 replace Afterlight's guest-selection meeting with a linear bishōjo
  ensemble adventure. It is not a dating simulator. Story cues and the cast
  renderer are game-owned; no universal scenario language is introduced.
  Presentation Lab owns all focused study routes; real games keep story UI
  and small navigation menus. Preserve per-game in-session checkpoints and
  independent lab fixture language/settings when navigating among roots.

- P71 adds one brief reconverging story choice, with two distinct replies and
  the same continuing episode. Afterlight owns its gradient chrome, ready dot,
  screen input, choices, and checkpoint details. Keep this UI local to the game.
  P72 schedules story Sigh Puff cues after text reveal so they are noticeable;
  it does not change the shared one-shot motion or lifetime contract.

- P77 puts story and scene intent first. Existing backgrounds are replaceable
  fixtures, not constraints on the narrative. Choose or prepare environment
  assets to fit the authored setting when needed; a story edit does not itself
  require fresh image generation.

- P81/P82 give Eira a dedicated six-turn private transmission in the Relay
  Laboratory, as a portrait inside a floating framed display. Riko stays
  physical throughout the main episode. Keep the TV treatment within its feed,
  preserve face/dialogue readability, and clear the display when the call ends.

# Godot monorepo: the final shape

> **Status: P114 proposal, unratified.** Nothing has moved. P109–P111 arrived
> at three tiers under `godot/`, P113 named the middle tier `templates`; this
> document is the complete directory after the rule is enforced everywhere,
> including the later steps. Names in parentheses are what the files are today.

## 1. The whole tree

```text
godot/                                   not a Godot project; a directory of projects
├── README.md                            the three tiers, the link rule, how to run anything
├── tools/                               cross-project tooling only
│   ├── run_suite.py                     one process per suite file, over every project
│   ├── make_fixture_run.py              writes the 32 m survival package the gate reads
│   ├── compare.py  shot_png.py  frames_prefix.py  validate.sh
│   └── link_packages.py                 creates or verifies every addons/ link below
│
├── packages/                            shared code; each one is a Godot addon project
│   ├── game_runtime/                    the run-consumer kit
│   │   ├── project.godot                dev project for the package alone
│   │   ├── README.md  sdk.json  LICENSE
│   │   ├── addons/game_runtime/         the payload; the only thing consumers install
│   │   │   ├── kernel/                  (godot/legacy/runtime/kernel) events, fixed step, gauge, hash, rng, sealer, system
│   │   │   ├── families/                (godot/legacy/runtime/families) actor_ai, camera, checkpoints, clock, cues, director,
│   │   │   │                            effects, hud, intent, interaction, inventory, loot, navigation, particles,
│   │   │   │                            scenario, score, screen_fx, session, sideview, ui, vitals, block_gate
│   │   │   └── host/                    (godot/legacy/runtime/hosts/common) run_dir, args, actor, layer_texture, typeface,
│   │   │                                ui_sheets, atlas_button, panel_frame, gauge_bar, text_fit, outline,
│   │   │                                transition_view, cut_in_view, dialogue_leaf, room_leaf, shaders/
│   │   └── tests/                       (godot/legacy/runtime/tests) kernel, families, prng, ui_layers, input_map, masks …
│   │       ├── harness.gd  fixture.gd  run_tests.gd
│   │       └── fixtures/
│   ├── game_presentation/               the presentation SDK
│   │   ├── project.godot
│   │   ├── README.md  API.md  sdk.json  LICENSE
│   │   ├── addons/game_presentation/    (godot/packages/game_presentation/addons/game_presentation) unchanged payload:
│   │   │                                motion, actors, camera, transitions, effects, text, audio,
│   │   │                                interaction, content; component contracts beside their scripts
│   │   ├── tests/                       (godot/games/command_link/tests) the controller suites only:
│   │   │                                actor_focus, cast_transition, character_exit, eye_transition,
│   │   │                                manpu, layer_pan, sprite burst, emitter, halo, corruption, contact,
│   │   │                                local_content, hologram defaults …
│   │   ├── tools/check_sdk_package.py   closure, literal dependencies, UID sidecars
│   │   └── history/                     USER_PROMPTS.md, REQUESTS.md, QA.md, promotion reviews, HANDOFF.md
│   └── survival/                        the oblique-survival simulation and view, shared by its template and its game
│       ├── project.godot
│       ├── addons/survival/             (godot/legacy/runtime/genres/oblique_survival + godot/legacy/runtime/hosts/oblique_survival):
│       │   ├── sim/                     world, roster, sim, systems/, inventory, targeting, masks, document
│       │   └── view/  hud/  audio/  shell/  devtools/
│       └── tests/                       (godot/legacy/runtime/tests) world, matrix_*, survival_roster, drops, craft, weather …
│
├── templates/                           agnostic; one per recipe; plays a run of its recipe; copy one to brand it
│   ├── vn/                              (godot/templates/vn/) The Signal Room
│   │   ├── project.godot                1280×900, GL Compatibility
│   │   ├── addons/game_presentation → ../../../packages/game_presentation/addons/game_presentation
│   │   ├── main.tscn  main.gd           one master composition, editable
│   │   ├── content/                     original procedural placeholders
│   │   ├── export_presets.cfg
│   │   └── tests/
│   ├── oblique_survival/                thin: the previewer for survival runs; Ember Hollow was copied from here
│   │   ├── project.godot
│   │   ├── addons/game_runtime → …      addons/survival → ../../../packages/survival/addons/survival
│   │   ├── main.tscn  main.gd  input.gd README.md
│   │   ├── fixtures/                    (godot/legacy/runtime/tests/fixtures/oblique_survival)
│   │   ├── tests/                       the host-level checks that need this project
│   │   └── tools/                       capture.gd, parity.gd, smoke.gd
│   ├── sideview_runner/
│   │   ├── project.godot  README.md
│   │   ├── addons/game_runtime → …
│   │   ├── main.tscn  main.gd  input.gd
│   │   ├── sim/                         (godot/legacy/runtime/genres/sideview_runner) contract, world, roster, segments,
│   │   │                                encounter_state, dust, presentation, systems/
│   │   ├── view/  hud/  audio/          (godot/legacy/runtime/hosts/sideview_runner)
│   │   ├── fixtures/  tests/            runner_roster, runner_view, matrix_agents, music, mob, mobs …
│   │   └── tools/                       runner_capture.gd, runner_parity.gd, runner_shots_check.py, runner_parity_diff.py
│   ├── sideview_platformer/             same anatomy: sim/ view/ hud/ audio/ fixtures/ tests/ tools/
│   ├── pointclick_room/                 same anatomy; room_capture, room_parity, room_shots_check
│   ├── dialogue_scene/                  sim/ = bundle, framing, layout; dialogue_capture, dialogue_shots_check
│   └── case/                            plays the room's and the scene's leaves from game_runtime; case_capture, case_parity
│
└── games/                               branded; complete; free to consume any package; nothing else may consume them
    ├── afterlight/                      (godot/games/afterlight)
    │   ├── project.godot                1280×900, GL Compatibility; the game owns its canvas and renderer
    │   ├── README.md  AUTOPLAY.md  ACTOR_BLOCKING.md  CAST_PAN.md  CONTENT.md
    │   ├── addons/game_presentation → ../../../packages/game_presentation/addons/game_presentation
    │   ├── main.tscn  root.gd           the master composition
    │   ├── story.gd  story_beats.gd  cast_stage.gd  content_adapter.gd  transmission_display.gd  atmosphere_profile.gd
    │   ├── text/                        en.json, ko.json, STORY_REVIEW.md
    │   ├── voice/                       voice_policy.gd, cast.json, voices.json, manifest.json, reports; no clips
    │   ├── assets/                      catalog.json, placeholders.json; image bytes ignored
    │   ├── content/                     (godot/games/command_link/art/) rounds, prompts, records, REVIEW.md,
    │   │                                ACTIVE.json tracked; raw, previews, voiceovers-p95/clips ignored
    │   ├── lab/                         (games/presentation_lab/afterlight) the thirteen studies, a --lab route
    │   ├── tests/                       afterlight_*, autoplay, *_integration, external_content checks
    │   └── tools/                       prepare_afterlight_voice.py, prepare_example_content.py, AFTERLIGHT_VOICE_PREPARATION.md
    ├── command_link/                    (godot/games/command_link)
    │   ├── project.godot
    │   ├── addons/game_presentation → …
    │   ├── main.tscn  root.gd  game.gd  menu.gd  menu.tscn
    │   ├── stage.gd  stage_profile.gd  actor_overlay.gd  opening.gd  opening.tscn  motion_curve_graph.gd
    │   │                                (godot/games/command_link/presentation/) its integration code
    │   ├── assets/                      (godot/games/command_link/assets/) layout.json, locations/, manpu/, opening/; bytes ignored
    │   ├── lab/                         (games/presentation_lab tactical + demos/) the eleven studies
    │   └── tests/                       route_checks, route_option_checks, command_link_content_checks, composition_checks
    └── ember_hollow/                    the branded survival game
        ├── project.godot
        ├── addons/game_runtime → …      addons/survival → …
        ├── main.tscn  main.gd           branded shell, title, storefront hooks; whatever is not regularizable
        ├── content/                     the adopted run, by digest; bytes local until the publication gate says otherwise
        └── tests/
```

Outside `godot/`, unchanged in role:

```text
godot/legacy/inputs/<id>/       authored generation packages; ember-hollow stays here, merge deferred
out/<run>/                generated runs; what a template opens with --run
web/                      the run viewer for recipes without a host (universe, storefront)
docs/spec/game/           host contract: governs templates/ and the survival package
docs/spec/presentation/   composition, terminology, character effects, content root, packaging
tests/contract/           test_godot_boundaries.py rescoped per tier; test_packaged_resources.py renamed path
godot/games/command_link/  dissolved into packages, templates and games
```

## 2. Anatomy of a project, by tier

| Tier | Has | Never has |
| --- | --- | --- |
| `packages/<name>` | `project.godot`, `addons/<name>/` payload, `tests/`, its own docs and license, optional `tools/` | a link to another tier; art; a story; a brand |
| `templates/<recipe>` | `project.godot`, links under `addons/`, one main scene, its `sim/` when no game shares it, `fixtures/`, `tests/`, `tools/` | a brand; a link to a game or another template; bundled runs |
| `games/<id>` | `project.godot`, links under `addons/`, one master composition, complete UI, `content/`, `lab/`, `tests/`, `tools/` | a link to a template or another game; anything another project imports |

A package is laid out the way Godot addon repositories are, so its suites run
inside its own project against `res://addons/<name>`. A link is
`addons/<name> → ../../../packages/<name>/addons/<name>`; `link_packages.py`
creates and verifies them, and the boundary test refuses a link that points
anywhere else. The assembler turns links into copies at the ship boundary.

## 3. The rules the tree enforces

```text
games/*      --> packages/*                    never another game, never a template
templates/*  --> packages/*                    never a game, never another template
packages/*   --> declared packages             never a template, never a game
```

- Code that only one template uses stays in that template. The moment a
  branded game wants it, it becomes a package: that is why survival is a
  package and the runner is not.
- A template is named by its recipe id and carries no brand; it is the
  agnostic starting point a branded game is copied from, and the previewer
  for that recipe's runs. A game is named by its brand and may carry no contract.
- Every project owns its `project.godot`: canvas, renderer, main scene, input
  map. Nothing is applied at runtime to paper over a shared project file.
- Tests sit with the code they test. Cross-project tooling sits in
  `godot/legacy/runtime/tools/`; the Python contract tests stay in `tests/contract/`.
- Media bytes are ignored everywhere; catalogs, manifests, digests and reviews
  are tracked. Publishing bytes is the publication gate's decision, per root.

## 4. Order

1. Move today's `godot/` project down to `godot/legacy/runtime/` intact; repoint the
   boundary test and run commands. `godot/` stops being a project.
2. Land `packages/game_presentation`, `templates/vn`, `games/afterlight`,
   `games/command_link` from `godot/games/command_link/`; delete it. Commit the
   staged P107 work first.
3. Carve `packages/game_runtime` out of `runtime/`; give each template its
   own project; `runtime/` disappears.
4. Carve `packages/survival` and add `games/ember_hollow`.
5. Deferred by the user: whether a branded game and its `godot/legacy/inputs/<id>`
   authoring package share one home.

Gates and references that change: `ARCHITECTURE.md`, `README.md`, `docs/README.md`,
the host contract's applicability link, three research docs,
`tests/contract/test_packaged_resources.py`, `scripts/check_docs.py`,
`scripts/check.py` (suite entry points per project), and the root `.gitignore`.

Launch commands at the end:

```sh
Godot --path godot/games/afterlight -- --language ko
Godot --path godot/templates/oblique_survival -- --run <absolute run directory>
Godot --path godot/templates/vn
```

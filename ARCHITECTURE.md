# Architecture

`stage-gen` is a headless, general-purpose system for producing coherent game
assets — 2D today, with 3D as a deferred axis the
[asset taxonomy](docs/spec/asset-taxonomy.md) reserves a name for. The
reusable core stops at validated artifacts, manifests, and provenance. A
preview or game runtime is a downstream consumer, never the definition of the
generator.

It is built on `gnode`, an **asset graph** SDK: a build system for generative
assets whose contracts must be met. Nodes produce persistent, content-addressed
artifacts validated before they are accepted; correctness does not depend on
execution order; a failed provider operation is retried by exactly one owner and
never by the scheduler. `gnode` grows in rings ([gnode rings](docs/spec/gnode-rings.md)):
a media-free engine core, per-modality model specs and services above it, and
first-party provider adapters above those. A ring imports only rings below it,
and nothing game-, recipe-, or genre-specific belongs in any ring — `stage-gen`
is one application on top of the SDK.

## Repository boundaries

```text
src/gnode/                    ringed asset-graph SDK — ring 0: engine core
                              (topology, scheduling, trace, run view, model
                              bindings, exact route snapshots, reliability,
                              provenance; media-free);
                              ring 1 gnode/modalities/: per-modality model
                              specs and retry-owning services, including the
                              bounded tool-loop agent; ring 2
                              gnode/providers/: OpenAI, OpenRouter, fal, and
                              ElevenLabs behind declared per-provider surfaces
src/stage_gen/components/     application components and capability processing
src/stage_gen/providers/      adapters for application-owned component
                              protocols; never provider-route authority
src/stage_gen/media/          shared recipe-neutral inspection and transforms
src/stage_gen/recipes/        recipe-specific composition, processing, and manifests
src/stage_gen/orchestration/  run preparation, concrete composition, and summaries
src/stage_gen/interfaces/     argparse CLI, the only automation surface
src/stage_gen/resources/      wheel-packaged recipe resources
library/games/                source-checkout or external authored package workspace
web/                          optional browser run viewer and asset inspector
godot/                        Godot 4.7 monorepo: packages, templates, games; plus the legacy runtime
  packages/game_presentation/ the presentation SDK as an addon project: payload at
                              addons/game_presentation, its tests, tools and history
  templates/vn/               The Signal Room, the agnostic visual-novel starting point
  games/afterlight/           Bishōjo: Afterlight, a branded game with its own Lab
  games/command_link/         Command Link, a branded game with its own Lab
  runtime/                    legacy run consumer: one project, one host per genre,
                              loads a published run directory, starts no generation
```

Arrows below point from an importer to the layer it imports:

The [Game Presentation SDK](godot/packages/game_presentation/addons/game_presentation/README.md)
is Godot-native and separate from gnode and the generated-run runtime families.
Its hosts own story, complete UI, content policy and choreography. Its optional
local loader accepts prepared media without invoking generation. Scenario is
secondary and experimental; it does not define the SDK's behavior vocabulary.

```text
interfaces    --imports----------> orchestration
orchestration --imports/composes-> recipes   --imports----------> components
orchestration --imports/composes-> gnode/providers --implements-> gnode ring-1 model specs
stage_gen/providers --implements-----------> component-owned protocols
components    --imports----------> media
everything in stage_gen -------->  gnode (declared surfaces only)
gnode         --imports----------> nothing in stage_gen; ring N only rings < N
```

The last two lines are the engine boundary, and they are enforced mechanically
by `tests/contract/test_import_boundaries.py` in both directions. Declared import
surfaces keep the engine free to move its modules; importing no application
keeps it usable without one.

Optional consumers invoke an interface through its CLI or HTTP contract; they
are not imported by the Python package.

Components do not import recipes or `web/`. They accept explicit typed inputs,
validate outputs, and expose provider-neutral artifact information. Shared,
recipe-neutral media inspection and transforms live in `media/`; deterministic
processing specific to a capability stays with its component contract, and
recipe-specific canonicalization stays with its recipe.

Recipes may add generation-specific genre, composition, projection, framing,
sheet-layout, artifact, and validation constraints. Consumers may translate a
completed manifest into an engine's textures or import settings, and they own
runtime camera, scene, engine, movement, combat, and gameplay rules.

Provider routes are declared, not scattered. Ring 0 supplies provider-neutral
route, workload, policy, resolution, and exact-size contract shapes; the
application owns their actual catalog and capability vocabulary. A workload
policy names one exact route rather than a preference list. Each node instance
declares its real operation and requirements, and the selected route must admit
every feature, numeric limit, and `exact_size` constraint while planning,
offline, before any spend.

Planning seals an admitted route as a `ResolvedRouteSnapshotV1` in the execution
graph and stores its `binding_ref` on each routed node. That snapshot carries the
material provider/model/surface/endpoint/adapter identity, exact output options,
and supported and required capability facts, with fingerprints for route
behavior, contract, and output. Credentials, prices, pacing, and mutable
evidence dates are excluded. Runtime dispatch revalidates the snapshot against
the configured catalog and constructs only its selected backend; it never
discovers or falls back by credential availability.

`stage_gen.orchestration.runtime` is the application composition root. It may
import both provider-neutral component services and concrete providers; those
layers do not import it. An AST contract test enforces that reusable components
never import providers, recipes, orchestration, interfaces, or `web/`.

## Operational capabilities

The hosted adapters use OpenRouter for structured text/vision, image generation
and reference work without native-alpha requirements, and experimental music
generation; OpenAI Images and fal both provide explicitly selectable Sunburst
generation, reference edit, native transparency, and masked edit routes; fal
also provides background removal and video. Exact model identifiers, request
envelopes, environment variables, and verification status are documented in
[Provider operations](docs/models/providers.md). Those names are operational
configuration, not architectural dependencies: recipes consume capability
interfaces and provenance records rather than raw provider response types.

Image routing is quality-first and Sunburst-only. Checked-in capability policies
choose an exact provider route, and the optional scalar
`STAGE_GEN_IMAGE_PROVIDER=openai|fal|openrouter` replans all image workloads
onto one provider without changing their requirements. An unsupported
combination is refused; no Flare, Responses API, or automatic provider fallback
is registered. Only credentials for image providers actually sealed into the
graph are required.

Every AI operation has one retry owner. Transport failures and silent contract
failures—empty media, malformed JSON, schema mismatch, invalid containers, or
failed caller validation—remain inside that boundary. Successful artifacts
must be committed with their provenance and integrity metadata; credentials,
authorization headers, signed query strings, and embedded reference bytes are
never persisted.

## Headless path

The supported entry point is:

```sh
uv run stage-gen <args>
```

The CLI is the only automation surface: there is no HTTP service, and no
process outside it starts a run. Seven recipes compile onto the one engine —
`sideview-platformer` and `sideview-runner` build distinct prepared-game
members from a `game.toml` package, `dialogue-scene` builds a scene bundle from
an authored request document, `pointclick-room` builds a fixed painted
puzzle room from an authored package whose puzzle is proven finishable before generation is scheduled
(`stage-gen pointclick-room generate --input library/games/<id>
--output out/<tag>`), `oblique-survival` builds a billboard-sprite survival
world on a ground plane under a fixed elevated-oblique perspective camera from
its own authored package (`stage-gen oblique-survival generate --input
library/games/<id> --output out/<tag> --scope full`), `universe` builds an
explorable storyworld package — typed entities and one concept image each —
from a poster, a synopsis, and an expansion direction, and `storefront` builds
store images and listing copy from an authored brief and the game's own art.
Each declares its own graph document kind, so no recipe can read another's plan.

Generated runs live below the configured output directory. Recipe-specific
names and file layouts belong in recipe manifests, not in generic
orchestration. Shared, capability-specific, and recipe-specific deterministic
processing stays at its owning boundary, remains independently testable, and
is recorded in provenance.

Transparency is a per-node requirement, not a provider-global toggle. OpenAI
Images and fal can satisfy native transparent generation/edit routes;
OpenRouter declares no native-alpha capability and is admitted only for `auto`
or explicitly opaque generation and reference conditioning inside its verified
size envelope. Validated AI background removal and an explicit degraded chroma
fallback remain separate recipe strategies, the latter deterministic and local.
Opaque artifacts bypass both paths. The selected route or strategy and
raw-to-derived lineage travel in plans, manifests, and sidecars so consumers
load canonical outputs without guessing from colour.

## Hosts and the viewer

One gameplay engine is selected, for every genre: Godot 4.7
([decision 0061](docs/decisions/0061-every-genre-runs-on-godot-and-web-is-the-viewer.md),
[decision 0057](docs/decisions/0057-the-survival-game-runs-on-godot.md),
[engine evaluation](docs/game-engine-evaluation.md), [host
contract](docs/spec/game/host-contract.md), [host manual](docs/godot-host.md)).
A host owns scene composition, camera behaviour, collision, navigation, input,
gameplay, the interface and runtime effects for its genre; it loads one
published run directory, starts no generation, and is a dependency of no
provider adapter, artifact schema, or component boundary. A game is data applied
to a trusted template, and generated content is never accepted as engine script.

The `web/` application is the run viewer and asset inspector: it lists runs,
renders a run's derived `execution-view.json` read-only with its inspector,
shows the universe gallery, and serves one run's artifacts under path
confinement. It holds no gameplay and can start no run. It may embed a finished
export by its release record without parsing it. The browser gameplay runtimes
are being retired one genre per change, each in the change that lands its Godot
host; until then they are live surfaces documented at
[the web viewer](docs/web-viewer.md).

The Python packages are the sole headless implementation. Node and TypeScript are
confined to the optional `web/` viewer and GDScript to the Godot hosts; neither
launches a run.

## Storage and redistribution

Generated output, populated environment files, caches, and local verification
captures are ignored. Only small intentional fixtures with a documented
rights basis belong in version control. Generated music replaces the removed
legacy recording library; no third-party recording is retained as a fallback.
See [Repository storage policy](docs/repository-storage.md) and
[OSS and IP policy](docs/oss-ip.md).

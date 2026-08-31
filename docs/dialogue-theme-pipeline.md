# Dialogue theme pipeline

The shortest operator path starts in `web/` and keeps generation separate from
installation:

```sh
cd web
bun run stage-gen -- doctor --transparency native --json
bun run stage-gen -- dialogue-scene generate \
  --input ../library/games/larkfield \
  --output ../out/larkfield
bun run dialogue-theme -- install --bundle ../out/larkfield/bundle.json
bun run dialogue-theme -- status
```

The generate command prints the run's `scene_id`, graph digests, node count, and
per-capability provider-operation counts. Installation prints strict
lower_snake_case JSON with `bundle_id`, `installed`, and `activation_eligible`.

Verification of this workflow is credential-free: generation and orchestration
pass end to end with injected fake services and canonical bundle tests; the real
adapter's install, activate, load, rollback, and tamper paths pass in isolated
temporary directories; and public command, help, and sample parsing pass. A
provider-backed smoke was not authorized, was not run, and sent no data.

## Generate, review, and activate

The Python `dialogue-scene` recipe owns the adult/non-explicit policy,
expression taxonomy, prompts, node graph, generation, validation, retries, and
portable provenance. It writes only below the isolated generated run. The web
adapter validates and copies a completed bundle; it never calls a model, reads
provider credentials, edits generation provenance, or generates an asset.

```text
out/<run-dir>/
  execution-plan.json
  execution-projection.json
  execution-trace.jsonl
  execution-summary.json
  scene.json
  request.json
  request.json.meta.json
  character-profile.json              # wire V3 / recipe V4 only
  character-profile.json.meta.json     # wire V3 / recipe V4 only
  style-anchor.json
  style-anchor.json.meta.json
  plan.json
  plan.json.meta.json
  attempts/                            # one record per node
  attempts.json                        # merged in graph order by the bundle node
  raw/
  assets/
    concept.png
    background.png
    expression-neutral.png
    expression-delighted.png
    expression-flustered.png
    expression-concerned.png
    *.meta.json
  bundle.json
  bundle.json.meta.json
```

`bundle.json` is the only adapter input. The adapter accepts exactly one
contract: `dialogue-scene-bundle-v4` with `schema_version: 4` and
`recipe_version: "dialogue-scene-v5"`. Every persisted key is strict
lower_snake_case, and unknown versions or camelCase input are rejected. Its asset,
request, plan, attempt, and provenance references are run-relative POSIX paths
with SHA-256 bindings. Raw and rejected candidates are lineage, not runtime
assets. There is no prior-version branch: an older bundle is a different
document, not an older dialect to reinterpret.

The bundle binds the authored-source digest from a strict
`character-profile-binding-v1`, the canonical `character-profile-v1` artifact
and provenance, the authored identity plate the run republished, and matching
plan, bundle, and independent-review facts. The consumer checks that the plate
the run shipped is the one the package declared, by digest rather than by path.
The installer copies these records opaquely. Runtime fixture projection exposes
only `profileIdentity.profileId` and `profileIdentity.revision`; it never
exposes authored paths, absolute URLs, detector output, or provenance.

From the repository root, the complete authored scene package is:

```sh
uv run stage-gen dialogue-scene generate \
  --input library/games/larkfield \
  --output out/larkfield
```

The package names every member it depends on by exact relative path and exact
digest, so there is no library-root configuration to supply and nothing to
resolve outside that directory.

From `web/`, use the same public command through the stable forwarding script:

```sh
bun run stage-gen -- dialogue-scene generate \
  --input ../library/games/larkfield \
  --output ../out/larkfield
```

Before any image call, the `scene-style-select` node sends the request
concept and scene direction through the shared strict selector. The edge result
may name only an approved `style_mode`; local code materializes the tracked
medium, observable traits, per-asset treatment, and exclusions into
`style-anchor.json`. Anchor, skill, vocabulary, resource, and compiler digests
bind downstream caches, plan and bundle provenance, and run identity. Each
image request carries that anchor once with the appropriate `concept_art`,
`environment_background`, or `character_sprite` asset kind.

Within structured-plan provenance, `params.schema` preserves standard JSON
Schema vocabulary such as `$defs`, `$ref`, `additionalProperties`, `maxLength`,
and `minLength`. Only recipe-owned definition identifiers, reference targets,
and property names are normalized to lower_snake_case.

Generation deliberately emits `review.status=pending`,
`rights.aggregate=unreviewed`, and `publication_authorized=false`. Installation
may preserve that bundle for inspection, but activation fails closed. An
independent process must first bind a `pass` review record to the selected asset
digests and record `restricted` local-demo rights with
`publication_authorized=false`. Review PASS alone never grants rights. Local
activation never authorizes export, repository publication, or redistribution;
the web adapter exposes no publication command, and the separate generated-media
publication gate remains authoritative for those actions.

An independent reviewer supplies the strict review record and acceptance spec;
the headless transition preserves `bundle.json` and derives the digest-bound
`bundle.reviewed.json` consumed by the installer:

```sh
cd web
bun run stage-gen -- dialogue-scene review \
  --bundle <run-dir>/bundle.json \
  --review <independent-review.json> \
  --acceptance-spec <acceptance-spec.json> \
  --usage local-demo
```

For an independently reviewed, local-demo-eligible installed bundle, use the
exact `bundle_id` returned by `install`:

```sh
cd web
bun run dialogue-theme -- activate --bundle-id <bundle-id>
bun run dialogue-theme -- status
bun run dev
```

Installation does not activate. Wire-v2-only activation preserves historical
`active.json`. The first recipe-v4 activation stages complete `active.json`,
`migration.json`, and `bindings.json` files in an immutable
`states/<state_id>/` directory, then atomically publishes only
`active-commit.json`. Readers verify every state and install digest and fail
closed on partial or tampered state.

## Resume

A run directory is immutable: `--output` must not already exist. Reuse comes from
`--cache-dir` instead, and it is content-and-lineage validated rather than
path-based. A node is restored only when its cache key matches, the recorded
lineage still matches what its dependencies actually produced, and every restored
byte hashes to what was recorded:

```sh
uv run stage-gen dialogue-scene generate \
  --input library/games/larkfield \
  --output out/larkfield-v2 \
  --cache-dir .cache/dialogue
```

Editing the scene document changes its canonical digest, which changes every
node's cache key, so the edited run rebuilds rather than contaminating the
earlier one. Replacing an authored reference does the same: its digest rides
each image node's identity, so a new plate re-bills the scene deliberately. There is
no force flag and no per-stage bypass: a node whose inputs are unchanged is reused,
and a node whose inputs changed is not. Re-running an accepted artifact under the
same inputs would be a new identity, not a retry, and the graph has no verb for it
yet.

## Status and rollback

Status emits `dialogue-theme-status-v2` for historical state and
`dialogue-theme-status-v3` after commit-marker migration. It reports either the committed
fallback or the active installed theme, including `bundle_id`,
`previous_bundle_id`, `installed_bundles`, and `activation_eligible`:

```sh
cd web
bun run dialogue-theme -- status
```

Rollback is generation-free. It validates the previous installed bundle and
atomically swaps the pointer; it does not delete either bundle:

```sh
cd web
bun run dialogue-theme -- rollback
```

Rollback requires a locally activation-eligible previous bundle. If no valid
previous bundle exists, it exits without changing the active theme.

Historical receipts and loose pointers remain exact
`dialogue-theme-install-v2` / `dialogue-theme-active-v2`. Profile-enabled
installs use `dialogue-theme-install-v3`; committed activation uses
`dialogue-theme-active-v3` behind `dialogue-theme-active-commit-v1`. Every
state contract is strict lower_snake_case, and the adapter never reinterprets
prior state.

## Transparency and reusable references

`--transparency native` requires `OPENAI_API_KEY` for images and
`OPENROUTER_API_KEY` for structured generation. Explicit `ai` also requires
`FAL_KEY`; `chroma` is the degraded local-keying mode. Neither is an automatic
fallback from failed native alpha. The CLI rejects a command-line transparency
mode that conflicts with the request.

The tracked sample is the strict `dialogue-scene-v1` authored contract: all TOML
keys are lower_snake_case, and camelCase or unknown fields are rejected. The
identity plate is not generated at all - `[[references]]` names a package member
by relative path, exact SHA-256 digest, and rights state, and the run publishes
those bytes as its concept asset. The recipe copies them into the run, never
symlinks them, and never infers redistribution approval.

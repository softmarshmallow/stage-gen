# Dialogue theme pipeline

The shortest operator path starts in `web/` and keeps generation separate from
installation:

```sh
cd web
bun run stage-gen -- doctor --transparency native --json
bun run stage-gen -- generate --recipe dialogue-scene \
  --input ../examples/dialogue-theme/adult-university-date.json \
  --transparency native
bun run dialogue-theme -- install --bundle ../out/<generated-tag>/bundle.json
bun run dialogue-theme -- status
```

The generate command prints `<generated-tag>`. Installation prints strict
lower_snake_case JSON with `bundle_id`, `installed`, and
`activation_eligible`.

Verification of this workflow is credential-free: generation and orchestration
pass end to end with injected fake services and canonical bundle tests; the real
adapter's install, activate, load, rollback, and tamper paths pass in isolated
temporary directories; and public command, help, and sample parsing pass. A
provider-backed smoke was not authorized, was not run, and sent no data.

## Generate, review, and activate

The Python `dialogue-scene` recipe owns the adult/non-explicit policy,
expression taxonomy, prompts, stage DAG, generation, validation, retries, and
portable provenance. It writes only below the isolated generated run. The web
adapter validates and copies a completed bundle; it never calls a model, reads
provider credentials, edits generation provenance, or generates an asset.

```text
out/<generated-tag>/
  run.json
  request.json
  request.json.meta.json
  character-profile.json              # wire V3 / recipe V4 only
  character-profile.json.meta.json     # wire V3 / recipe V4 only
  style-anchor.json
  style-anchor.json.meta.json
  plan.json
  plan.json.meta.json
  attempts.json
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

`bundle.json` is the only adapter input. The adapter preserves exact wire-v2
branches for recipe v2/v3 and separately accepts only
`dialogue-scene-bundle-v3` with `schema_version: 3` and
`recipe_version: "dialogue-scene-v4"`. Every persisted key is strict
lower_snake_case, and unknown versions or camelCase input are rejected. Its asset,
request, plan, attempt, and provenance references are run-relative POSIX paths
with SHA-256 bindings. Raw and rejected candidates are lineage, not runtime
assets.

The web consumer retains already-installed `dialogue-scene-v2` compatibility
through an explicit `v2`/`v3` recipe-version allowlist. It validates v2 against
the historical contract without inventing style defaults. V3 additionally
requires matching digest-bound style facts in plan and bundle provenance;
unknown recipe versions fail closed.

Recipe v4 additionally binds the authored-source digest from a strict
`character-profile-binding-v1`, the canonical `character-profile-v1` artifact
and provenance, and matching plan, bundle, and independent-review facts. The
installer copies these records opaquely. Runtime fixture projection exposes
only `profileIdentity.profileId` and `profileIdentity.revision`; it never
exposes authored paths, absolute URLs, detector output, or provenance.

From the repository root, the complete repository profile-enabled request is:

```sh
uv run stage-gen generate --recipe dialogue-scene \
  --input examples/dialogue-theme/profile-enabled-date.toml \
  --character-library-root . --transparency native
```

From `web/`, use the same public command through the stable forwarding script:

```sh
bun run stage-gen -- generate --recipe dialogue-scene \
  --input ../examples/dialogue-theme/profile-enabled-date.toml \
  --character-library-root .. --transparency native
```

Before any image call, the resumable `style-selection` stage sends the request
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
bun run stage-gen -- review --recipe dialogue-scene \
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

## Resume and force

Rerun the identical generate command to resume. Canonical request content
selects the same tag; each stage reuses only artifacts whose bytes and
dependency digests still match. A request edit changes the digest and selects a
new run instead of contaminating the old one.

Force a complete dialogue recipe rebuild with the existing public cache
control. It retains the same isolated run identity but bypasses every valid
stage cache entry; unset it for normal resume behavior:

```sh
cd web
STAGE_GEN_FORCE=1 bun run stage-gen -- generate --recipe dialogue-scene \
  --input ../examples/dialogue-theme/adult-university-date.json \
  --transparency native
```

For a bounded retry, repeat `--force-stage` with exact stage IDs. The generic
runner validates each ID against the selected recipe before it constructs a
provider runtime, then computes the dependency-DAG descendants. Only requested
roots bypass their cache entries; descendants revalidate their normal input and
dependency digests, so byte-identical unaffected artifacts remain reusable:

```sh
cd web
bun run stage-gen -- generate --recipe dialogue-scene \
  --input ../examples/dialogue-theme/adult-university-date.json \
  --transparency native \
  --force-stage appearance-concept
```

The dialogue stage IDs are `prepare`, `style-selection`,
`appearance-concept`, `scene-plan`, `background`, `neutral`, `expressions`,
`canonicalize`, and `bundle`. Unknown, duplicate, and unsafe IDs fail before
provider calls. Programmatic callers may also use
`DialogueExecutorContext(force_stages=...)` for the same root-only cache
bypass behavior.

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

The tracked sample is the strict `dialogue-theme-request-v2` wire contract: all
JSON/TOML keys are lower_snake_case, and v1 or camelCase input is rejected. It
generates both concept and background. A reuse request instead
names a portable relative path, its exact SHA-256 digest, and its current rights
state. The recipe copies the bytes into the run, never symlinks them, and never
infers redistribution approval.

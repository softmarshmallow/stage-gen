# Mission

Build a reliable, headless pipeline and reusable component library for
generating coherent 2D game assets.

The product boundary is asset generation. It is not a browser game, a single
genre, a fixed camera, or a selected gameplay engine. A recipe can request a
specialized asset family, and a consumer can preview those artifacts, while
the underlying capabilities remain useful for side-view, top-down,
isometric, interface, animation, music, and other 2D production workflows.

## Primary outcomes

1. `src/stage_gen/components/`, `providers/`, and `media/` provide independently
   testable structured/image/music/removal operations, vendor adapters,
   validation, provenance, and deterministic processing.
2. `src/stage_gen/` provides the authoritative Python CLI and local HTTP
   surface, recipe composition, reproducible runs, and benchmarks.
3. Every successful artifact has a typed manifest, validated media contract,
   integrity hashes, provenance, and explicit output location.
4. Every AI call retries transport and contract failures through one bounded
   retry owner before surfacing a failure.
5. `web/` remains an optional adapter that consumes completed artifacts. It is
   not required for headless generation.

## Initial capability set

- Generate or edit 2D imagery through the configured image adapter.
- Produce schema-validated text/vision plans for recipe orchestration.
- Remove image backgrounds through the configured cutout adapter and verify
  the resulting alpha-bearing media.
- Generate original music through the configured music adapter and verify the
  returned container and audio facts before accepting it.
- Preserve enough non-secret evidence to reproduce, compare, and audit every
  run.

Provider-specific setup is intentionally isolated and documented in
[docs/providers.md](docs/providers.md). The initial adapters use OpenRouter and
fal, including the Lyria music route, because those are current operational
requirements. They are not endorsement claims and do not define component
interfaces.

## First reference recipe

The first demonstrated recipe produces assets for an optional 2D scrolling
preview. It exercises concept art, a structured world plan, depth layers,
tiles, characters, creatures, props, pickups, interface art, animation sheets,
and deterministic post-processing.

This recipe is evidence that the pipeline composes end to end. Its platformer
terms, horizontal projection, parallax values, fixed sheet roles, and browser
scene remain inside `src/stage_gen/recipes/scrolling_preview/` and `web/`. They are
not defaults for reusable components or future recipes.

## Acceptance criteria

### Offline gate

- Frozen dependency installation succeeds.
- Every workspace typecheck, test, documentation check, and production build
  succeeds.
- CLI help, recipe discovery, and the offline benchmark run without provider
  credentials.
- Static scans find no populated credentials, legacy recording paths, stale
  gateway wiring, or named-identity imitation prompts.
- Generic components import neither browser runtime code nor recipe-specific
  camera/gameplay concepts.

### Provider gate

- Image generation proves the live request/response envelope, reference input,
  media decoding, normalization, validation, and provenance.
- Background removal proves foreground preservation, alpha output, dimensions,
  and provenance on representative input.
- The default transparency path fails closed when removal is unavailable or
  invalid; explicit degraded chroma runs remain separately identifiable.
- Music generation proves the live response envelope and records container,
  duration, sample rate, channels, validation, and provenance.
- Structured generation proves vision input and schema rejection/retry using
  the configured text model.
- No credential value, authorization header, signed URL, or embedded input is
  present in logs, errors, manifests, or sidecars.

### Pipeline gate

- A completed run has no success marker until artifacts and provenance are
  atomically committed.
- Repeating an intact run is a verified no-op; missing or mismatched hashes
  invalidate only the affected work.
- Benchmarks retain neutral inputs, exact revisions, provider/model identity,
  parameters, timings, attempt records, deterministic validation, and explicit
  pass/fail reasons.
- Visual verification is performed by an independent verifier. Music combines
  deterministic inspection with a separately recorded listening verdict.

## Engine status

No gameplay engine decision is locked. The browser scrolling preview is useful
for inspection today, while Godot and other dedicated 2D runtimes may be
evaluated later. Evaluation must consider import automation, animation,
rendering, collision, portability, licensing, and the ability to consume the
same engine-agnostic manifests. Generation work must not wait for that choice.

## OSS and rights boundary

Repository prompts and fixtures describe original results with neutral visual
or musical properties. They do not imitate named franchises, products,
characters, artists, studios, games, albums, tracks, recordings, or a
recognizable creator style.

Inputs must be owned, licensed for the intended transformation, or verified as
public domain. Generated output is not automatically cleared for distribution.
Before committing or shipping media, record its provenance, artifact-specific
redistribution status, and stable rights basis; review applicable provider terms;
and inspect for protected names, marks, characters, text, melodies, or
recognizable copying. The source license does not grant rights to inputs,
outputs, models, or hosted services.

## Deferred work

- Selecting or building a production gameplay runtime.
- Expanding gameplay systems for the optional preview.
- User accounts, multiplayer, persistence, analytics, or remote telemetry.
- Treating a generated artifact as shippable without project-specific rights
  review.

Progress is measured by validated headless artifacts and reproducible evidence,
not by the amount of preview gameplay implemented.

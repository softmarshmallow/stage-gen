# Autonomous loop guide

This loop advances `stage-gen` as a headless, general 2D asset generator. The
shared state is `TODO.md`; the public product and operational contracts live in
`README.md`, `MISSION.md`, `ARCHITECTURE.md`, and `docs/`.

## Wake and ground

1. Read `TODO.md` and inspect the live Git state before planning.
2. Reconcile stale in-progress items against the working tree; the working
   tree is authoritative.
3. Identify independent work, dependencies, verification owners, and bounded
   return contracts before dispatch.
4. Keep the main context free of image payloads. Pass paths to specialized
   producers and independent verifiers.

## Build loop

1. A producer reads the relevant contract and creates an artifact plus complete
   reproducibility metadata.
2. A different verifier receives the artifact and its specification, but not
   the generation prompt, and returns a structured pass/fail verdict.
3. A failed visual stage receives at most two bounded regeneration attempts
   before its reason is surfaced. Provider-call retries remain owned by the
   implementation's shared retry boundary.
4. A peer audit checks code, manifests, validation, provenance, OSS/IP policy,
   and the headless path before work is marked complete.
5. Completed TODO sections are pruned; unresolved work keeps an explicit next
   action or blocking reason.

## Architectural rules

- Reusable components remain independent of genre, camera, gameplay loop,
  preview runtime, and future engine choice.
- Recipe-specific scrolling assumptions stay in
  `src/stage_gen/recipes/sideview_platformer/`. Browser scene assumptions stay in
  `web/`.
- The public command is `uv run stage-gen <args>`; the Python package is the
  authoritative backend.
- Provider adapters are configured at the headless application boundary.
  Operational OpenRouter/fal/Lyria details belong in `docs/providers.md`, not
  in generic component contracts.
- Every AI call has one bounded retry owner covering transport and silent
  contract failures. Do not stack hidden SDK retries.
- An artifact is successful only after media validation, atomic persistence,
  integrity metadata, and secret-free provenance.
- Fixtures are copied rather than symlinked. Generated outputs and populated
  environment files are never committed.
- Repository prompts use neutral original properties and never request
  imitation of named identities, catalogs, or recordings.

## Verification discipline

- Tests and schema checks do not replace live provider-contract evidence.
- Live evidence does not replace deterministic media inspection.
- Preview behavior does not define component quality; benchmark each component
  against its own declared artifact contract.
- Never expose credential values, signed URLs, embedded reference bytes, or
  private local paths in output, logs, errors, or reports.
- Do not skip validation to reduce provider calls. Context safety and bounded
  execution matter; token or API cost is not the optimization target.

Before the loop yields, every active item has a result or explicit next action,
and the next iteration can resume from paths and TODO state without re-deriving
the project.

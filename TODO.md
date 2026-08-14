# TODO — current migration state

This file is working memory for the active provider and topology migration. Keep it concise; completed detail belongs in the linked evidence reports.

## Active change — transparency strategy

- [x] Parameterize transparency generation as `ai` or `chroma`, defaulting to `ai`.
  - Evidence: `/tmp/stage-gen-bg-core-implementation.md`, `/tmp/stage-gen-bg-recipe-implementation.md`
- [x] In `ai` mode, use neutral backgrounds and require validated removal for transparency-producing assets.
  - Evidence: `/tmp/stage-gen-bg-recipe-implementation.md`, `/tmp/stage-gen-bg-live-verification-retry1.md`
- [x] In `chroma` mode, use exact magenta and deterministic local keying without calling the remover.
  - Evidence: `/tmp/stage-gen-bg-recipe-implementation.md`
- [x] Persist mode, raw/derived hashes, removal provenance, and failures in manifests and sidecars.
  - Evidence: `/tmp/stage-gen-bg-core-implementation.md`, `/tmp/stage-gen-bg-live-verification-retry1.md`
- [x] Cover configuration, prompts, opaque exclusions, missing keys, both branches, web, and docs.
  - Evidence: `/tmp/stage-gen-bg-core-implementation.md`, `/tmp/stage-gen-bg-recipe-implementation.md`, `/tmp/stage-gen-bg-docs-web-implementation.md`
- [x] Audit the repository, provider wiring, worktree, and audio history.
  - Evidence: `/tmp/stage-gen-repo-audit.md`, `/tmp/stage-gen-history-sanitize.md`
- [x] Verify the current image, background-removal, and music API contracts from primary sources.
  - Evidence: `/tmp/stage-gen-provider-research.md`
- [x] Establish the headless-first topology: `components/`, `stage-gen/`, optional `web/`, and `docs/`.
  - Evidence: `bun run stage-gen -- recipes`
- [x] Keep reusable contracts genre-, camera-, gameplay-, and engine-agnostic; isolate scrolling assumptions in the preview recipe/runtime adapter.
  - Evidence: `docs/component-contract.md`, `stage-gen/recipes/scrolling-preview/`, `docs/web-preview.md`
- [x] Add OpenRouter image, structured-output, and Lyria music components plus fal background removal.
  - Evidence: five component check/test suites pass; `.env.example` documents only names and non-secret defaults.
- [x] Enforce five retries after the initial attempt, contract validation before success, cancellation/timeouts, secret redaction, and atomic provenance sidecars on every AI path.
  - Evidence: component and `stage-gen` tests pass; `/tmp/stage-gen-static-review.md`
- [x] Generate, normalize, and independently validate the Lyria preview music placeholder and provenance.
  - Evidence: `stage-gen/recipes/scrolling-preview/assets/music/preview-loop.mp3.meta.json`, `/tmp/stage-gen-media-verification.md`
- [x] Rewrite public docs and reframe the web application as an optional preview adapter; defer and unlock the game-engine decision.
  - Evidence: `README.md`, `docs/game-engine-evaluation.md`, `docs/web-preview.md`
- [x] Pass the historical pre-transparency-strategy local offline gate: frozen install, component checks/tests, headless CLI/server/benchmark/research, web test/typecheck/build, docs, secret scan, and diff check.
  - Evidence: `/tmp/stage-gen-final-gate.md`
- [x] Purge the 12 audited recordings from local `main` history and the objects reachable from `main`.
  - Evidence: local `main` scan is empty at `5cc35b0`; `/tmp/stage-gen-history-sanitize.md`

## Active publish

- [x] Evaluate existing showcase candidates; skip the README image because none is representative and OSS-safe.
  - Evidence: `/tmp/stage-gen-showcase-scout.md`
- [x] Approve the loop's artifact-specific CC0 scope, notice, terms basis, and maintainer listening review (`preview-loop.LICENSE.md`, adjacent provenance, media inventory).
- [x] Re-run finished-state verification and the pre-push secret/history scan.
  - Evidence: focused component, pipeline, docs/media, web, diff, secret, and history gates passed on 2026-08-14.
- [x] Commit the complete migration intentionally on rewritten local `main`.
- [x] Force-with-lease publish sanitized `main`, then verify the remote head and absence of legacy audio paths.
  - Evidence: `/tmp/stage-gen-publish-report.md`

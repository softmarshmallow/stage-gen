# Contributing

Contributions should preserve `stage-gen` as a headless, general 2D asset
pipeline with optional consumers.

## Boundaries

- Put reusable media operations in `components/`.
- Compose them through `stage-gen/` pipelines and public manifests.
- Keep camera, movement, combat, scene, and engine assumptions inside a recipe
  or consumer adapter such as `web/`.
- Do not import `web/` from a reusable component.
- Keep source identifiers, comments, logs, tests, and user-facing strings in
  English.

## Provider work

Use documented env variable names and never commit or print credentials. Every
network/model call must use five blind retries with backoff and must retry
malformed, empty, or otherwise contract-invalid success responses. Persist
non-secret provenance and validate media before marking a run successful.

## Prompts and media

Follow [docs/oss-ip.md](docs/oss-ip.md). Prompts and examples must request
original work using neutral properties, without named franchises, brands,
artists, studios, games, recordings, or recognizable creator-style imitation.

Do not add binary media without documented provenance and a clear rights
basis. Repository code licensing does not grant rights to generated or
third-party assets.

Generated media in publication roots must follow the
[artifact-specific publication policy](docs/generated-media-publication.md).
A technically valid provider response remains runtime-unreviewed until its
sidecar rights, inventory status, and any required human review are approved.

## Checks

Run the checks relevant to your change. At minimum for public documentation:

```sh
bun docs/check.mjs
bun test docs/media-rights.test.mjs
```

For code, run the workspace's type, test, build, and headless smoke commands.
Provider-backed tests are opt-in: record the endpoint/model, returned usage,
validation, and provenance without leaking credentials.

Keep generated run output, populated env files, caches, local screenshots, and
OS metadata out of Git.

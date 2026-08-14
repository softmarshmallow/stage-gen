# Component contract

A component is one independently testable media operation beneath
`components/`. Examples include image generation, background removal, sheet
slicing, metadata inspection, or music generation. A pipeline is an ordered or
parallel composition of components. A runtime or preview is a consumer of the
pipeline's artifacts.

## Required properties

Every component must:

1. accept typed or schema-validated input;
2. write only below the caller-provided output directory;
3. return an artifact manifest rather than relying on implicit filenames;
4. validate media before reporting success;
5. wrap every provider/network call in five blind retries with capped backoff;
6. retry silent contract failures such as empty media or malformed JSON;
7. persist provenance and a content hash beside the artifact;
8. make deterministic post-processing explicit and independently testable;
9. support cancellation/timeouts without leaving a success marker; and
10. expose enough information for a headless benchmark.

## Independence rule

The reusable contract does not assume a genre, camera, engine, coordinate
system, movement model, combat model, or gameplay loop. Those may be explicit
inputs to a specialized recipe, but they are never ambient global state.

For example, a sprite-sheet component may accept `{ rows, columns, anchors }`.
It must not silently assume that row 2 is a jump animation. A depth-layer
component may accept a requested projection and loop axis. It must not assume a
horizontal follow camera because one preview happens to use one.

Components must not import `web/`. The optional web adapter consumes exported
manifests and may translate them into browser-engine textures or scene state.

## Artifact result

A successful result should provide this information, directly or through a
manifest:

```ts
interface ArtifactResult {
  component: string;
  artifactPath: string;
  provenancePath: string;
  mediaType: string;
  sha256: string;
  bytes: number;
  attempts: number;
  validation: Record<string, unknown>;
}
```

Image dimensions, audio duration, channel count, or other media-specific facts
belong in `validation`. Never infer success from HTTP 200 alone.

## Failure contract

Failures distinguish provider/transport errors, response-contract failures,
input validation errors, and deterministic post-processing failures. Error
messages may name environment variables but must never include credential
values or full authorization headers.

Partial outputs may remain for debugging only when clearly marked incomplete.
They must not satisfy skip-if-exists or cache checks.

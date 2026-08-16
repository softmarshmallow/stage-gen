# Benchmarking and research

Benchmarking belongs to the authoritative Python headless package, not the
optional web preview. The public entry point is:

```sh
uv run stage-gen --help
```

Use the CLI help as the source of truth for currently implemented pipeline and
benchmark arguments. Do not document an aspirational subcommand as shipped.

The current offline suite is runnable without provider calls:

```sh
uv run stage-gen benchmark list
uv run stage-gen benchmark smoke
```

## Evidence bundle

Every benchmark case preserves:

- a neutral, rights-safe case identifier and input manifest;
- exact component/pipeline revision;
- provider/model/endpoint identifiers and non-secret parameters;
- hashes of every reference input;
- raw provider metadata where policy permits;
- normalized artifact and provenance sidecar;
- attempt count, latency per attempt, and total wall time;
- deterministic validation output; and
- an explicit pass/fail reason.

Secrets, authorization headers, signed URLs, and populated env files never
belong in an evidence bundle.

## Evaluation layers

1. **Contract tests** use fixtures/mocks to exercise schemas, retries, path
   isolation, media parsing, and provenance without paid calls.
2. **Provider smoke tests** make the smallest useful key-backed call and prove
   the live envelope. They are opt-in and record cost/usage when returned.
3. **Component benchmarks** compare one operation against its declared media
   contract without a game runtime.
4. **Pipeline benchmarks** validate cross-asset consistency and resumability.
5. **Preview verification** checks only that an adapter can consume a complete
   manifest; it is not the quality oracle for the core pipeline.

Any visual output is independently reviewed by a verifier that sees the spec
and rendered output, not the generation prompt. Use bounded retries and retain
the verifier's structured verdict. Audio checks should combine deterministic
media inspection with a separately recorded human/agent listening verdict.

## Initial release gates

- Image: live request, reference input, returned media validation, deterministic
  normalization, and provenance all pass.
- Background removal: alpha-bearing output and optional mask behavior pass on
  representative edge detail.
- Music: live Lyria response envelope is captured and decoded; container,
  duration, channels, and sample rate come from the returned file rather than
  documentation assumptions.
- Secret scan and history scan find no credential or removed third-party media.
- A repeated completed run is a no-op unless force is explicit.

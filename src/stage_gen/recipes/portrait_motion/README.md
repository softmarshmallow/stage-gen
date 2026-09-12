# Portrait-motion recipe

This optional asset recipe prepares, executes, and verifies a bounded portrait
animation workflow. It owns its stage composition and checkpoints. Components own
the deterministic crop, registration, patch, playback, and validation mechanics.
Games consume the resulting assets using their own scripts and bindings.

```python
from stage_gen.recipes.portrait_motion import prepare, run, verify, PortraitMotionSpec

prepare(source_path, run_dir, spec)
result = await run(
    run_dir,
    image_service=my_retry_owning_image_service,
    structured_service=my_retry_owning_review_service,
)
verified = verify(run_dir)
```

`prepare_run`, `run_pipeline`, and `verify_run` remain available under their existing
names. `prepare(..., face_crop=True)` selects the contained workflow: face location,
deterministic working crop, the existing portrait graph, and reconstruction on the
original canvas. The public module also exports `RuntimeProfile`, `graph_for`, and
`load_plan` for inspection and host integration.

Injected services remain caller-owned and must match the prepared route and request
policy. A host can implement `PortraitServiceFactory` to admit live execution and
construct budget-aware services. The repository CLI explicitly supplies
`stage_gen.orchestration.portrait_services.ConfiguredPortraitServices`; the recipe
never imports that implementation. That host retains the existing allowlisted key
loader, `STAGE_GEN_RUN_LIVE=1` requirement, exact route credentials, and durable
per-attempt budget reservation before transport. Ordinary component services remain
the sole retry owners.

Preparation remains immutable. Content digests, implementation fingerprints,
dependency versions, exact route snapshots, stage receipts, submission markers,
and source provenance retain their existing admission semantics. An unresolved
provider submission is not automatically dispatched again. Local reconstruction
cannot expand an upstream semantic acceptance decision. The parent workflow
preflights all downstream keys before locating a face.

Historical preparation fingerprints bind source code and therefore require fresh
preparation after implementation changes, including this ownership move. Existing
artifacts remain on disk; their previous plans and traces remain historical evidence.
The contract identity/version pairs and artifact layouts have not been rewritten.

For provider-free experimentation, `examples/pipelines/portrait_processing.py`
composes the real face crop and restoration components through `stage_gen.pipeline`.
It creates a deterministic synthetic donor, preserves pixels outside the authored
mask and original alpha, and writes a two-frame WebP preview. It demonstrates
mechanical composition and cache reuse; it makes no semantic or temporal approval.

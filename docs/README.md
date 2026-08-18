# Documentation

Start here for the headless, general-purpose system:

- [System overview](spec/system-overview.md) — ownership and data flow.
- [Component contract](component-contract.md) — reusable-module requirements.
- [Endpoint-conditioned loop synthesis](loop-synthesis.md) — deferred masked
  bridge generation, seam gates, and runtime consumption.
- [Testing the Python reboot](testing.md) — focused, full, live, and web gates.
- [Verification rules](../VERIFICATION.md) — evidence and independent media
  verification requirements.
- [Provider operations](providers.md) — credentials, verified endpoints, and
  experimental boundaries.
- [Benchmarking and research](benchmarking.md) — evidence and evaluation.
- [OSS and IP policy](oss-ip.md) — acceptable inputs, prompts, and outputs.
- [Generated-media publication](generated-media-publication.md) — artifact
  rights records and the repository approval gate.
- [Repository storage](repository-storage.md) — generated files and Git LFS.
- [Game-engine evaluation](game-engine-evaluation.md) — deliberately open
  integration decision.
- [Web preview adapter](web-preview.md) — optional first consumer.

The documents under [`spec/`](spec/) that describe parallax, terrain,
characters, mobs, inventory, and portals are the first scrolling-preview
recipe. They are useful component/recipe evidence, not the definition of
`stage-gen` as a whole.

Provider facts in this repository were last verified on 2026-08-14. Re-check
capability metadata before changing adapters because hosted model contracts
can change independently of this source tree.

Run the documentation checks with:

```sh
uv run python scripts/check_docs.py
```

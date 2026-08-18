# Endpoint-conditioned loop synthesis

Horizontal loop synthesis is a provider-neutral Python component. It turns one
source strip into a repeat unit whose period contains the untouched source
pixels followed by a generated transition bridge. It is deliberately disabled
in the scrolling-preview recipe until a provider adapter implements the exact
`masked-image-edit` capability.

The default recipe manifest therefore records:

```json
{
  "loopSynthesis": {
    "enabled": false,
    "status": "deferred",
    "axis": "x",
    "algorithm": "endpoint-conditioned-bridge-v1",
    "requiresCapability": "masked-image-edit",
    "artifacts": []
  }
}
```

This is not prompt-only tiling and it is not a runtime blur or crossfade. A
provider-specific implementation is injected behind
`MaskedImageEditBackend`; the recipe and consumers never import a vendor SDK.

## Algorithm

For a source strip `S`, context width `C`, and requested bridge width `B`:

1. Decode and provenance-bind `S`; reject mismatched digests, unsupported
   media, symlinks, unsafe paths, and configured size limits before any model
   call.
2. Copy the last `C` columns of `S` to the left of a new conditioning canvas.
3. Copy the first `C` columns of `S` to the right. Leave exactly `B` columns in
   the middle.
4. Supply a mask that is white only for the middle bridge and black over both
   immutable context bands.
5. Ask a compatible edit provider to fill only the bridge. The component
   verifies exact PNG media and dimensions, then deterministically reimposes
   both original context bands even if the provider changed them.
6. Crop only the middle `B` columns. The published repeat unit is `[S | B]`, so
   its horizontal period is `sourceWidthPx + bridgeWidthPx`.
7. Measure and gate both joins independently: `S end → bridge start` and
   `bridge end → S start`.

The model receives the answer at both ends before filling the unknown middle.
The algorithm never smooths or blurs output pixels to manufacture a passing
seam.

## Acceptance and retries

Each join records three deterministic metric families:

- pixel difference in premultiplied RGBA;
- difference between the cross-join gradient and adjacent within-image
  gradients; and
- CIE Lab boundary distance after deterministic neutral compositing, with
  alpha discontinuity included.

Every family records a per-row mean, nearest-rank p95, and maximum. All nine
values must meet their request thresholds at both joins. The distribution-aware
gates prevent a severe defect confined to a small set of rows from disappearing
inside an acceptable mean. A malformed provider image, dimension change, or
failed join is a failed AI attempt and is retried by the shared policy: one
initial attempt plus five retries with cancellation and an attempt timeout. No
artifact or manifest is a success marker until a candidate passes every gate.

## Artifact and runtime contract

`LoopSynthesisService` writes four adjacent files under the caller-provided
output directory:

- a PNG repeat unit;
- its provenance-v1 sidecar;
- a typed `*.loop.json` manifest; and
- the manifest's provenance-v1 sidecar.

The loop manifest binds the source and repeat unit by path, SHA-256, byte size,
dimensions, period, provider/model, attempts, rights status, metrics, and
thresholds. Provider and model values are frozen at service construction and
must be safe identifier labels, never URLs or configured secret material.

The four output names must remain distinct after Unicode normalization and
case folding. Persistence stages every file, installs them without overwrite,
and rolls back the whole set on an error or caller/task cancellation at any
checkpoint. A returned result therefore means all four files exist; there is no
partially published success state.

The scrolling-preview manifest discovers only verified `*.loop.json` records
and keeps repeat units out of the ordinary canonical-image list. Collection
does not trust a re-signed manifest: it fully decodes source and repeat PNGs,
reconstructs the context bands, conditioning canvas, mask, and bridge, then
rechecks dimensions, period, pixels, all hashes, metrics, rights, and component
input lineage before publication.

A runtime that selects a verified `repeatUnit.path` consumes it as one texture
period. Place successive copies exactly `periodPx` source pixels apart on the
X axis (scaled by the same display transform as the texture); that verified
period is not overlapped, faded, mirrored, or cropped. Collision geometry
remains a separate terrain contract.

That exact-period rule is deliberately scoped to a verified repeat unit, not
an absolute ban on compatibility treatment of an unsynthesized source. Only
when no verified loop artifact exists, the browser may use the explicitly
temporary legacy preview fallback `repeat-x-seam-overlap` for a transparent
layer. It linearly multiplies the existing alpha in the left and right
256-source-pixel bands, leaving already-transparent pixels transparent, then
composites a same-texture partner at `sourceWidthPx - 256`. The complementary
edge tapers overlap with normal alpha blending; opaque layers instead use
plain `repeat-x`. This fallback is an in-memory preview adapter, does not alter
source bytes, does not publish a bridge, and is ineligible as soon as a
verified repeat unit is selected.

## Rights and provider activation

Generated loops default to `unreviewed`, even when the source was approved.
Redistribution approval must be passed explicitly and cannot broaden an
unapproved source. A restricted source remains restricted. Source,
conditioning, mask, bridge, and repeat hashes are retained in provenance;
credentials and configured secret values are redacted.

Activation requires all of the following:

1. a provider adapter whose declared capability is exactly
   `masked-image-edit`;
2. exact PNG input/output and white-edit/black-preserve mask semantics;
3. one provider call per shared retry attempt, with no hidden retry stack;
4. passing deterministic fake-adapter and provider contract tests; and
5. independent visual review for any generated artifact selected for
   publication.

No configured provider adapter currently satisfies that contract, so the
default runtime does not construct this component or call it from a recipe
stage.

Run the credential-free contract tests with:

```sh
uv run pytest tests/unit/components/loop_synthesis -q
```

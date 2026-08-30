# Verified single-axis image repeat

`image_repeat` is the provider-neutral Python component for the contract:

> one image in, one image proven to repeat on a declared axis out

It owns image admission, optional explicit repair, deterministic seam
measurement, independent visual judgment, lineage, and atomic publication. It
does not know whether the image will be used as a game background, foreground,
material, UI strip, or another repeating surface. Recipes select assets and
declare intended behavior; consumers decide how to render an accepted repeat
unit.

The public operations are deliberately separate:

```python
await service.admit(ImageRepeatAdmissionRequest(...))
await service.repair(ImageRepeatRepairRequest(...))
```

An admission rejection never invokes repair. Callers must request repair as a
new operation. This prevents a negative semantic verdict from silently becoming
permission to regenerate pixels.

## Admission

Admission keeps the source bytes unchanged and evaluates only the declared
`x` or `y` wrap:

1. Load the PNG and its digest-bound provenance through confined, non-symlink
   paths.
2. Measure the direct edge join at native and downsampled scales. The report
   covers color, local gradient, alpha, coverage, localized p95/max defects, and
   an internal-boundary baseline.
3. Stop with a deterministic rejection when the join fails. Edge alpha or an
   empty border is only one measured fact; it is never proof that the image
   loops in the intended way.
4. Build exactly three unmarked, pixel-identical copies on the declared axis
   and alpha-composite them over a versioned neutral checkerboard. The preview
   is opaque, so hidden RGB under zero alpha cannot affect the reviewer, while
   partial alpha remains visible.
5. Ask an independent VLM to judge both visible joins, the full-period cadence,
   and the caller-declared behavior. `reject`, `uncertain`, confidence below
   `0.90`, missing digest-bound review evidence, a missing reviewer, or a
   reviewer that is not independent all fail closed.
6. Publish a byte-identical repeat-unit PNG only after both gates pass.

The semantic reviewer sees the exact three-repeat checkerboard preview, axis,
intended behavior, and closed failure-code rubric. The checkerboard visualizes
transparency and is explicitly not candidate content. It does not see the
deterministic `pass` verdict, which avoids anchoring the visual judgment. The
deterministic report remains digest-bound in provenance.

## Explicit repair

Repair uses endpoint conditioning without rotating provider-visible pixels. For
source `S`, context span `C`, and repair span `R`, the component supplies:

- `x`: `[right/tail C | editable R | left/head C]`;
- `y`: `[bottom/tail C | editable R | top/head C]`.

The mask is white only over `R`. A provider adapter makes one edit call per
shared retry attempt. The component then:

- checks exact PNG media and conditioning dimensions;
- reimposes both immutable source contexts;
- crops the raw provider repair span;
- reconstructs repair alpha deterministically, for every cross-axis pixel, by
  fixed-point smoothstep interpolation between the exact source tail and head
  alpha profiles; the provider owns RGB appearance, not alpha topology;
- copies the exact source tail/head RGBA lines onto the repair endpoints and
  eases each correction to zero through a small, versioned linear-light
  premultiplied-RGBA anchor band;
- preserves provider RGB byte-for-byte through the visible central repair
  interior, while canonicalizing reconstructed zero-alpha non-endpoint RGB;
- appends it to the right (`x`) or below (`y`);
- proves every original source pixel is unchanged;
- retains the exact normalized provider candidate and its provenance in the
  same atomic success bundle;
- reconstructs the endpoint contexts, conditioning canvas, mask, raw provider
  repair, provider interior, alpha-reconstructed repair, anchored repair, and
  final repeat unit during verification and recomputes every lineage digest;
- validates source-to-repair and repair-to-source joins independently; and
- performs the same one-shot semantic review over the exact final repeat unit.

Transport, decoding, malformed media, and deterministic candidate failures are
inside the single six-attempt repair owner. A well-formed semantic rejection is
final and is not a provider retry.

The OpenRouter adapter implements `masked-image-edit` with `gpt-image-2` image
references. It submits the conditioning canvas and mask once, normalizes the
provider raster to the declared conditioning geometry, and leaves context
restoration, deterministic alpha-topology reconstruction, endpoint anchoring,
and acceptance to the component. Alpha reconstruction is not a semantic repair:
an incompatible provider RGB interior, cadence, recognizable repeated motif, or
intended-behavior mismatch still fails the unchanged gates.

## Artifact contract

A successful operation writes:

- one PNG repeat unit;
- its provenance sidecar;
- for a repaired result, the exact normalized provider-candidate PNG and its
  provenance sidecar as internal reconstruction evidence;
- one lower-snake-case `*.repeat.json` manifest; and
- the manifest provenance sidecar.

The manifest identity is `single_axis_repeat_unit`, schema version 2. It binds
the source and output paths, digests, byte sizes, geometry, axis, period,
intended behavior, deterministic policy/report, independent semantic review,
construction (`admitted` or `repaired`), complete lineage, and rights status.
When the VLM adapter persists its verdict, that review JSON and sidecar are also
digest-bound by the manifest.

The scrolling-preview producer reopens every discovered `*.repeat.json`,
revalidates source/output/review provenance, decodes every bound PNG, reconstructs
the repair split and retained provider candidate where applicable, recomputes the
endpoint anchor and deterministic report, rebuilds the exact three-repeat
preview and criteria digests, and only then projects the record into
`image_repeat.artifacts`.

The browser selects a horizontal record only when its `source.path` exactly
matches the canonical layer path. It loads `repeat_unit.path`, requires decoded
width to equal `period_px`, and renders one TileSprite. A verified repeat is
never faded, mirrored, cropped, overlapped, or paired with a seam-hiding sprite.
Legacy preview fallbacks are ineligible once the verified record is selected.
Collision and terrain geometry remain separate contracts.

## Scope and future challenge

The component supports one declared axis per operation: horizontal **or**
vertical. It intentionally does not claim or evaluate the other axis.

Two-axis tileability is a non-goal for this version. It is recorded as a future
challenge because satisfying four edges is not enough: all four corner
transitions, combined X/Y phase behavior, semantic cadence, and repair ordering
must also be proven without one axis invalidating the other. Do not represent a
single-axis result as a material tile that is safe on both axes.

## Verification

Credential-free gates:

```sh
uv run pytest tests/unit/components/image_repeat -q
```

Generated repeat units remain `unreviewed` for rights and publication unless a
separate authorized review records otherwise. A semantic loop verdict is a
usability gate, not redistribution approval.

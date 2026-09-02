# Sprite-sheet slicing and instance-recovery contract

> **Status: alpha-component instance recovery is implemented and is the prepared-game default;
> broader geometry and ownership recovery remain planned.**
> `src/stage_gen/media/sprite_sheets.py` implements the deterministic
> `alpha-component-repack-v3` subset used by prepared-game actor assets. Uniform-grid and
> padding-derived geometry, normalized per-cell artifacts, and ambiguous-instance ownership below
> remain the normative target rather than shipped behavior.

This document is the canonical record of the sprite-sheet slicing problem, the current production
decision, its known loss modes, and the boundary for future replacements. It distinguishes
**rectangular slicing** (cutting a canvas at predetermined X/Y coordinates) from **instance
recovery** (finding each rendered pose first) and **packing** (placing recovered poses into a
canonical runtime grid).

Sprite-sheet processing turns one validated, alpha-bearing image into explicit
cell geometry and, when requested, normalized cell artifacts. The operation is
provider-neutral and engine-neutral. A recipe supplies the sheet structure and
semantic cell identifiers; the processor owns deterministic pixel geometry.

## Decision summary

| Question | Current decision |
| --- | --- |
| What is generated? | One native-alpha source sheet containing a requested number of poses. |
| Is the requested count trusted? | No. It is an intent that local validation must test against observed pixels. |
| How are poses found? | Meaningful 8-connected alpha components are treated as candidate instances. |
| How are extras handled? | The default keeps the largest requested number and reports loss; `exact_required_slots` fails when any meaningful component would be discarded. |
| How are missing instances handled? | Try the deterministic higher-alpha-core partition only for low-alpha-fused support; otherwise fail closed. |
| What does the runtime consume? | A deterministic equal-cell canonical sheet produced by the repacker. |
| Is equal-X/Y slicing still the producer default? | No. It remains only the runtime decoding of an already canonical sheet. |
| Are detached effects guaranteed to follow their actor? | No. The core cannot assign ownership; strict recipes fail instead of publishing lossy output. |

## The problem

Image models understand a request such as “four animation poses in one row” semantically, but they
do not reliably obey exact arithmetic cell boundaries. A useful pose may cross an intended quarter
boundary, neighboring poses may occupy unequal widths, or a sword, shadow, particle, or other
detached element may sit outside the actor's main silhouette. Cutting that source at `width / n`
therefore produces amputated and mixed frames even when the image itself contains four usable
poses.

The requested cell count `n` is not evidence that the output contains `n` recoverable instances.
Two poses can touch and become one connected region, one requested cell can be visually empty, or
one pose plus a detached effect can become two regions. A VLM may later provide semantic count
evidence, but it does not supply trustworthy pixel ownership or crop geometry by itself. The local
pixel processor must record the observed candidate count and must never silently present it as the
requested count.

The production boundary is consequently:

```text
provider source sheet
    -> observe candidate instances
    -> select exactly n principal instances or fail
    -> pack selected instances into canonical equal cells
    -> runtime performs ordinary equal-cell frame decoding
```

This preserves a simple runtime contract while removing arithmetic X/Y cuts from the uncontrolled
model output.

## Shipped alpha-component baseline

`alpha-component-repack-v3` keeps the v1 base path byte-identical and strengthens one narrow
fallback:

1. Decode a native-alpha PNG and classify pixels with `alpha > 16` as occupied.
2. Find 8-connected occupied components.
3. Reject components smaller than the greater of 32 pixels or 2% of total thresholded visible
   area.
4. If fewer than `n` candidates remain, progressively raise the alpha threshold. Recovery is
   eligible only when exactly `n` principal high-alpha cores exist, one occupies each expected
   source lattice slot, and together they cover every principal base-threshold component.
5. Seed those cores in source reading order, then deterministically partition the original
   base-threshold 8-connected support by multi-source 8-neighbor geodesic flood. This preserves
   the real alpha values of antialiasing, fringes, and the weak bridge while assigning every pixel
   to exactly one core. Equal-distance ties go to the earlier source-ordered core.
6. If no higher threshold proves that ownership, fail without publishing a canonical sheet.
7. Under the default policy, if more than `n` base candidates remain, retain the `n` largest and
   report every rejected component. Under `exact_required_slots`, require exactly one principal
   component in every expected source slot and refuse any other unassigned component of at least
   the 32-pixel meaningful-area floor.
8. Recover source reading order using source-row bands and horizontal centroids.
9. Translate each selected component without scaling into a canonical equal cell with a
   transparent gutter. Motion poses are bottom-centered; dialogue expressions are centered.
10. Validate that every required output cell is nonempty and does not touch its cell boundary.

The canonical motion repacker preserves a 12-pixel transparent isolation gutter below each
bottom-anchored component. Runtime actor consumers register the visible component bottom, not the
canonical cell bottom, with the actor's logical foot coordinate. The gutter remains part of the
published artifact and must not silently raise a player, NPC, or mob above its collision surface.

The source is retained as `*.source.png`; the repacked `*.png` is the runtime-facing artifact. The
adjacent validation record binds the source and output digests, dimensions, thresholds, candidate
and selected component counts, placements, alpha retention, warnings, and implementation version.

## Known failure taxonomy

| Failure | Observable condition | v3 behavior | Consequence |
| --- | --- | --- | --- |
| Detached effect | Actor and effect form separate alpha components | Default policy may drop it; `exact_required_slots` refuses every unassigned meaningful component | Permissive recipes retain the documented loss risk; strict recipes regenerate |
| Touching poses | Two intended poses share an alpha-connected bridge | Exactly `n` stronger cores covering every principal base component are partitioned deterministically; all other cases fail | Weak bridges can be split without discarding their alpha; ambiguous fusion remains a hard failure |
| Fragmented pose | One pose contains multiple substantial disconnected regions | Largest-`n` has no semantic ownership; `exact_required_slots` fails closed | A strict recipe cannot silently separate a limb, rider, weapon, mount, or effect |
| Weak alpha | Important pixels remain at or below the threshold | Pixels are excluded from detection and retained-alpha accounting | Fine translucent detail may disappear from the selected bounds |
| Ambiguous reading order | Unequal rows or displaced poses defeat row-band ordering | Deterministic centroid order is still applied | Semantic frame order can be wrong despite valid geometry |
| Oversized pose | Recovered bounds cannot fit with the canonical gutter | Validation fails | Regeneration or a future explicit rescale policy is required |

These are accepted limitations, not hidden successes. A warning-bearing result is usable only when
the recipe permits lossy extras; the recorded alpha-retention fraction makes that loss reviewable.

## Explored alternatives

| Approach | Verdict | Reason |
| --- | --- | --- |
| Equal rectangular X/Y slicing | Retired as the source-sheet default | Deterministic but cuts useful poses whenever the model ignores exact cell rails. |
| Empty-row/column projection and inferred bands | Not promoted | Works only when full transparent gutters separate every pose; crossing silhouettes collapse bands. |
| Alpha components with growing distance tolerance until count equals `n` | Not promoted | Can join a detached effect to its actor, but can just as easily merge neighboring actors; reaching `n` does not prove correct ownership. |
| Generic sprite packers and third-party atlas slicers | Not sufficient | They pack or trim already-separated rectangles; they do not solve semantic ownership in a generated composite. |
| Semantic segmentation such as SAM | Deferred | More capable but materially more expensive and complex than the accepted baseline. |
| VLM instance counting | Possible future validation signal | It can challenge the requested count but does not yield precise, deterministic alpha ownership or crop geometry. |

The next replacement must beat the alpha-component baseline on a representative fixed corpus, not
merely solve one sheet. It must report observed instances, preserve actor-attached content more
reliably, retain deterministic lineage, and remain cheap enough for every generated sheet.

## Current Python capability boundary

The Python core provides image inspection, exact-dimension PNG normalization,
chroma-to-alpha conversion, alpha composition, and native-alpha connected-component repacking
under `src/stage_gen/media/`. Prepared-game actor generation retains each provider sheet, then its
local validation node calls `repack_alpha_components` to publish the runtime-facing sheet.

The shipped v3 repacker uses 8-connectivity, `alpha > 16`, a candidate area of at least 2% of
thresholded visible area with a 32-pixel floor, and the largest declared number of components. It
orders those components row-major using source-row bands and horizontal centroids, then translates
them without rescaling into equal cells with transparent gutters. It records all rejected
components and retained alpha. When that base pass is short, it searches higher alpha thresholds
for exactly the required number of strong cores, verifies that one core occupies every expected
source lattice slot and every base principal component is represented, and floods the original
support from those cores deterministically. It deliberately does not attach detached effects to a
body; it can drop them. It fails when the high-alpha evidence does not prove the requested frame
count, lattice distribution, and base-component coverage.

The Python core does **not** currently implement:

- generic uniform-grid cell extraction as described below;
- padding-derived row or column detection;
- per-cell tight alpha bounds;
- anchor-aligned common-canvas normalization; or
- semantic ownership of compound instances or a reusable sprite-sheet artifact manifest.

If implemented, pure detection, cropping, and packing belong under
`src/stage_gen/media/`. A provider-neutral component or recipe wrapper may own
typed requests, rollback-safe artifact persistence, provenance, and manifest
projection. Consumers receive completed artifacts; they do not define or
validate this core contract.

## Terminology

- **Canonical input** is a validated image whose alpha channel already carries
  the transparency decision.
- **Padding pixel** is a pixel classified as exterior by the declared padding
  predicate.
- **Projection** is a one-dimensional occupied/not-occupied value for every
  source column or row.
- **Run** is one maximal, half-open interval of occupied projection values.
- **Logical cell** is the source rectangle assigned to one row/column pair.
- **Tight bounds** are the smallest rectangle containing every nonzero-alpha
  pixel inside one logical cell.
- **Normalized cell** is a tight crop placed on a deterministic common canvas.
- **Required cell** must contain nonzero-alpha content; an optional cell may be
  empty when the recipe explicitly permits it.

Semantic labels such as `idle`, `jump`, `portal`, or `inventory` belong to a
recipe. The core operation sees only stable cell ids and explicit parameters.

## Input contract

A processing request must pass a strict schema validator before pixel work
begins. Extra fields, missing required fields, invalid types, and inconsistent
cross-field values are input-contract failures. A valid request must contain:

1. validated image bytes and their content digest;
2. positive expected `rows` and `columns`;
3. one grid mode: `uniform` or `padding-derived`;
4. exactly `rows * columns` stable cell entries, each with a unique id and
   required/optional status;
5. the requested output mode, such as geometry-only or normalized cells;
6. normalized horizontal and vertical anchors for every normalized output;
7. explicit padding and optional common-canvas dimensions; and
8. a processor contract version.

Cell entries are ordered row-major: list index `r * columns + c` identifies
row `r`, column `c`. Both grid modes use this same declared order. Detected
runs may resolve source geometry, but they never add, remove, reorder, or
rename cell ids.

The initial contract accepts canonical RGBA PNG input. Alpha value `0` is
padding; any alpha value greater than `0` is content. A future threshold or
alternate predicate must be explicit, versioned, and included in cache
identity. It must never be inferred from colours.

Background handling happens before this operation. In a `native` run, decoded
provider alpha is validated directly. In an `ai` run, validated background
removal produces canonical alpha. In an explicit degraded `chroma` run,
deterministic keying produces the same canonical alpha boundary. The sheet
processor never searches for magenta, chooses a transparency strategy, or
silently changes strategies.

## Grid resolution

### Uniform mode

Uniform mode divides the complete canvas by declared row and column counts.
For source width `W`, height `H`, column count `C`, and row count `R`:

```text
baseWidth  = floor(W / C)
baseHeight = floor(H / R)

x0(c) = c * baseWidth
x1(c) = W when c = C - 1, otherwise x0(c) + baseWidth
y0(r) = r * baseHeight
y1(r) = H when r = R - 1, otherwise y0(r) + baseHeight
```

The final column and row receive any integer remainder. A request fails when a
base dimension is zero or any logical cell is empty by construction.

Uniform mode does not inspect padding to move boundaries. It is appropriate
when a layout prior or recipe contract makes arithmetic cells authoritative.

### Padding-derived mode

Padding-derived mode detects occupied bands before constructing cells. It is
eligible only when padding separates every declared row and column.

For each source column, the processor emits `occupied = true` when at least one
pixel in that column has alpha greater than zero. It performs the equivalent
OR projection for every source row. Each projection is then reduced to maximal
half-open runs:

```text
columns -> [x_start, x_end)
rows    -> [y_start, y_end)
```

The number of column runs must equal expected `columns`, and the number of row
runs must equal expected `rows`. A mismatch is a hard contract failure, not a
fuzzy match. Cells are the Cartesian product of the resolved column and row
runs, ordered top-to-bottom and left-to-right.

Content that bridges a separator can fuse adjacent projection runs. Such a
sheet is ineligible for padding-derived mode and must fail. The processor must
not invent a cut, select the nearest requested count, or fall back silently to
uniform mode. A caller may explicitly submit a new uniform-mode request or
regenerate the source, but that is a separate operation and cache identity.

## Cell extraction

Each logical cell is scanned independently. Tight bounds are computed only
from nonzero-alpha pixels inside that cell and are clamped to its half-open
source rectangle. Both rectangles are retained:

```text
logicalCell = { x, y, width, height }
tightBounds = { x, y, width, height } | null
```

An empty required cell fails the request. An empty optional cell produces a
record with `tightBounds: null` and no normalized artifact unless the caller
declares a separate placeholder policy. Placeholder generation is not an
implicit part of this contract.

Extraction must be tight before any padding is added. Expanding a source crop
first can consume pixels from a neighboring cell when content touches a cell
edge. All output padding is therefore applied after the tight crop exists.

## Common-canvas normalization

Normalization places each nonempty tight crop onto a transparent RGBA canvas.
Every artifact in one normalization group uses the same target width and
height.

When target dimensions are omitted, derive them deterministically:

```text
contentWidth  = max(tightBounds.width)
contentHeight = max(tightBounds.height)
targetWidth   = paddingLeft + contentWidth + paddingRight
targetHeight  = paddingTop + contentHeight + paddingBottom
```

When dimensions are supplied, they must be positive and large enough for every
crop plus declared padding. The processor never rescales a crop to make it fit.
Resizing, if desired, is a separate explicit transform with separate lineage.

Anchors are finite normalized numbers in the inclusive range `[0, 1]`.
Aliases such as `left`, `center`, `right`, `top`, and `bottom` may be resolved
by the caller to `0`, `0.5`, and `1`; the persisted request records numeric
values. For a crop of width `w` and height `h`:

```text
availableWidth  = targetWidth - paddingLeft - paddingRight
availableHeight = targetHeight - paddingTop - paddingBottom

destX = paddingLeft + floor(anchorX * (availableWidth - w))
destY = paddingTop  + floor(anchorY * (availableHeight - h))
```

The floor rule makes half-pixel cases deterministic. `(0.5, 1)` centers a crop
horizontally and aligns it to the bottom of the available area; this may be a
useful recipe policy for grounded character frames, but it is not a global
default or a physics guarantee.

Normalized canvases use transparent pixels outside the placed crop. They do
not restore a chroma-key colour. The source image remains unchanged.

## Failure contract

The operation fails without publishing successful outputs when any of these
conditions holds:

- the input is empty, undecodable, unsupported, or lacks the required alpha
  contract;
- row/column counts, dimensions, padding, or anchors are invalid;
- padding-derived projection counts do not exactly match the request;
- a logical cell is zero-sized, out of bounds, or overlaps another cell;
- required content is empty;
- a target canvas cannot contain a crop plus declared padding;
- a crop would read outside its logical cell or a placement would write outside
  its target; or
- encoded output fails deterministic image inspection.

The processor does not repair, guess, or downgrade a failed contract. A recipe
may use the failure as evidence for an explicit regeneration attempt, subject
to that recipe's retry boundary.

Every failed attempt must persist sanitized processing provenance with a
stable machine-readable failure code and an explicit human-readable failure
reason. When available, that record also includes the source digest, grid mode,
expected row and column counts, detected row and column counts, and the stage
at which processing stopped. A failed attempt must not publish successful
artifacts or a success manifest.

## Outputs, provenance, and cache identity

A successful geometry result records, at minimum:

- processor contract and tool versions;
- source media facts, byte count, and digest;
- grid mode, expected row and column counts, detected row and column counts,
  alpha predicate, and resolved projections/runs;
- stable cell ids, required/optional status, logical rectangles, and tight
  bounds; and
- validation results and warnings, if any.

A successful normalization result additionally binds:

- normalization-group id;
- target dimensions and four padding values;
- numeric anchors and integer placement coordinates per cell;
- artifact path, media type, byte count, and digest per nonempty output; and
- source-to-output lineage.

Artifact writes must be rollback-safe. A manifest must not report success
until every required artifact and adjacent provenance record is committed.

Cache identity includes the source digest, processor contract/version, grid
mode, expected counts, padding predicate, cell ids and requirement flags,
output mode, target-size policy, padding, anchors, and encoding parameters.
Recipe semantic mappings may live outside core artifacts and manifests, but
they do not alter neutral transform identity unless represented by an explicit
core request field. Every explicit request field that affects processing or
output selection is identity-bearing. Changing any identity-bearing input
invalidates the cached result. File existence alone is never a cache hit.

## Acceptance tests for a future implementation

A conforming implementation needs deterministic tests covering:

1. schema rejection plus exactly `rows * columns` unique row-major cell ids;
2. exact uniform division and final-row/final-column remainder handling;
3. padding-derived projections with unequal row and column band sizes;
4. exact expected-count rejection for missing, extra, and fused runs;
5. bridged-cell rejection with no guessed separator;
6. required-empty failure and explicit optional-empty behavior;
7. content touching every logical-cell edge without neighboring-pixel bleed;
8. tight bounds for partially transparent pixels where alpha is greater than
   zero;
9. crop-before-pad behavior and transparent output padding;
10. deterministic derived dimensions across differently sized crops;
11. anchor placements at `0`, `0.5`, `1`, and rejected out-of-range/non-finite
    anchors;
12. supplied target dimensions that are exact, larger, and too small;
13. byte-stable PNG output and identical processing records for identical
    requests;
14. cache invalidation for every identity-bearing parameter;
15. artifact/provenance digest binding, explicit failed-attempt code/reason,
    and rollback on partial failure; and
16. import-boundary proof that the operation has no provider, recipe, engine,
    or optional-consumer dependency.

These deterministic tests establish geometry and persistence correctness. They
do not replace independent semantic verification of generated visual content.

# Provider-neutral sprite-sheet processing contract

> **Status: planned deterministic core operation — not implemented.**
> This document is a normative target for reusable Python media processing. It
> does not describe a shipped component, CLI command, recipe stage, or consumer
> capability.

Sprite-sheet processing turns one validated, alpha-bearing image into explicit
cell geometry and, when requested, normalized cell artifacts. The operation is
provider-neutral and engine-neutral. A recipe supplies the sheet structure and
semantic cell identifiers; the processor owns deterministic pixel geometry.

## Current Python capability boundary

The Python core currently provides image inspection, exact-dimension PNG
normalization, chroma-to-alpha conversion, and alpha composition under
`src/stage_gen/media/`. The scrolling-preview recipe separately generates five
canonical 2400 x 800 character-state strips, crops each strip to its top
2400 x 688 rectangle, and composes those rectangles into one 2400 x 3440
master. Its following stage splits that master into five fixed 2400 x 688 row
artifacts. This is recipe-specific composition and fixed-coordinate slicing,
not an implementation of the generic operation specified here.

The Python core does **not** currently implement:

- generic uniform-grid cell extraction;
- padding-derived row or column detection;
- per-cell tight alpha bounds;
- anchor-aligned common-canvas normalization; or
- a reusable sprite-sheet artifact manifest.

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

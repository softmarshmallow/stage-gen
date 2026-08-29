# Asset scale study

> **Status: study.** Every measurement below was taken from artifacts already in this repository
> and can be re-derived from them. Nothing here is an implementation commitment, an approved
> prompt input, or a rights grant. The contracts this study motivates are
> [Asset unit](../spec/asset-unit.md) and [Motion rebase](../spec/motion-rebase.md); this file
> records the evidence and, more usefully, the approaches that were tried and rejected.

## Why this exists

An image model given the same character reference twice does not draw it at the same size twice.
That is not a defect in any one generation — it is a property of composing each asset in its own
call, with no frame shared between them. A package assembled from such calls has no scale
vocabulary at all unless something outside the pixels supplies one.

The interesting result is not that a unit is needed. It is *which* candidate units fail, and the
specific reason each one fails, because three of the four obvious answers look correct against a
super-deformed cast and stop working the moment the art style changes.

## What the artwork actually encodes

Measured across every landed subject in a prepared package — eight props, five items, four NPCs,
six mobs, one player.

| Observation | Value | Consequence |
| --- | --- | --- |
| Subject fill of its own canvas | **0.55 – 0.97** | The model normalizes the subject's longest dimension to the frame, so a published asset encodes its **aspect ratio and nothing else** about its size. |
| Cross-state extent spread, one actor | **1.79×** | An actor's alpha extent conflates pose with draw scale and cannot separate them. |
| Same subject, two views, one canvas | **1.005** | Within-canvas ratios are reliable. |
| Same character, four cells, one atlas | **1.008 – 1.051** | Still reliable across a composed strip. |
| Two instances of one object type, one canvas | **1.051 – 1.189** | Fidelity degrades as the two subjects diverge. |
| Same character, separate calls | **≥ 1.6** | Pose-confounded, and the reason this study exists. |

The first row is load-bearing and easy to miss. **There is no size signal in the pixels to
recover**, which is why a scale marker embedded in a generation could not have rescued these
assets even if one had been present, and why measurement alone can never produce intent.

## What a size constant produces

With magnitude supplied by per-class constants applied to the untrimmed canvas, every subject in
the game falls between **0.95 and 2.29 tiles** — a 2.41× range covering a coin, a market stall, a
beetle and a boss. Three consequences are visible without instrumentation:

- the boss resolves *shorter than the player it threatens*;
- every NPC resolves to within 3% of every other, erasing the authored `by_body_kind` build; and
- props are uniformly too small, because the constant is applied to a canvas the subject fills
  only partially, so the padding silently eats the difference.

Correcting magnitude per entity, with no regeneration and no change to the artwork, opens the
range to **0.70 – 3.20 tiles** and moves characters by only **0.95 – 1.10×**. That split is the
result worth keeping: a correct ruler is nearly a no-op on the subjects that were already close,
and a large correction on the ones that were not. A ruler that moved everything would be noise.

![The same map, camera and artwork rendered under both rules: above, a per-class pixel constant on each untrimmed canvas; below, each subject's declared height_units projected through the asset unit](../media/asset-unit-calibration.webp)

## Units evaluated

### Tile — rejected as the *asset* unit

The tile is the render projection and is correct in that role. It is not an asset unit, because it
says nothing about how many source pixels a given piece of artwork spent on it. A package that
declares magnitude in tiles still needs the measurement step, and gains no invariance for it.

Retained as the projection: `player_height_tiles` is where the unit meets the grid, exactly once.

### Head — rejected: style-dependent

A head is an appealing quantum against a super-deformed cast, and it works there. It works
*coincidentally*: at `heads_tall = 2.25` a head is 0.44 of the figure, which lands it near one
tile and near a quarter of the player.

Holding one prop catalogue fixed and varying only the game's build:

| `heads_tall` | One head | Legibility floor | Buckets spanned by 8 props |
| --- | --- | --- | --- |
| 2.00 | 76.8 px | 76.8 px | 3 |
| 2.25 | 68.3 px | 68.3 px | 3 |
| 3.00 | 51.2 px | 51.2 px | 4 |
| 4.00 | 38.4 px | 38.4 px | 4 |
| 6.00 | 25.6 px | 25.6 px | 6 |
| 8.00 | 19.2 px | 19.2 px | **8** |

It degrades backwards: the more realistic the proportions, the finer the quantum and the weaker
the floor. At realistic proportions the same catalogue spans eleven buckets, so a judge must
separate nine heads from eleven — which is the precision problem a quantum exists to remove — and
the floor falls to 19 px, protecting nothing.

### Shoulder width — rejected: better, still wrong

Shoulder width as a fraction of stature drifts from roughly 0.25 at realistic proportions to
roughly 0.35 in a super-deformed build. That is a 1.4× spread against the head's 3.5×, so it is a
genuine improvement and still not invariant. It carries three further costs the player does not:
it is a *width* used to measure *heights*; it is the body part most often occluded, by arms,
cloaks, packs and pauldrons; and it does not match how anyone reasons about a scene.

### Player height — adopted

Invariant by construction: the player is `1.0` whatever their build, so no art-style parameter
enters the vocabulary. It is also the vocabulary the wider field already uses — published
platformer metrics are stated in player heights and grid cells, never in anatomical sub-units.

A quantum is still required. Whole players is catastrophic, since a bench would resolve to player
height. Quarter-player steps at the small end are coarse enough to be selected rather than
estimated, and fine enough to separate a coin from a bench.

## Estimation versus recognition

The measurement half of this problem is deterministic and free. The half that requires judgement —
what magnitude was *intended* — is the only place a vision model belongs, and the form of the
question decides whether the answer is usable.

Asking for a magnitude requires the model to hold an absolute mental ruler. Asking it to pick
between rendered options, with the canonical player drawn beside each, is a comparison — the
operation this repository's own artifacts measure at **1.005 – 1.05** fidelity, as against the
≥ 1.6 spread of anything cross-canvas.

Two plates built this way, on a well and a bench, were each resolved in about a second with no
instrumentation, and **both revised a free numeric estimate made earlier by the same judge** — the
well from 2.60 to 2.40 tiles, the bench from 1.10 to 1.20. The corrections are small, and their
direction is the point: selection beat estimation even holding the judge constant.

The judgement stays advisory. It proposes a declaration for review; it is never multiplied into
pixels.

## What a scale marker can and cannot do

The instinct to place a known reference in the frame is sound, and its physical analogues are
sound for a reason that does not transfer. A coin in a photograph works because a camera has
projective geometry: one factor scales everything in the subject plane, so a known length transfers
to an unknown one beside it. A generative model has no projective geometry. It composes. A marker
it draws is therefore a *rubber ruler* — a record of what the model chose to draw.

Two corollaries, both verified against this repository's own round trips:

- A marker composited into a reference before generation is re-synthesized along with the rest of
  the canvas. Provider guidance in this repository already records that a mask is treated as a
  strong hint rather than a protected region, and that callers must reimpose anything they need
  preserved.
- A printed lattice that *does* survive an edit legibly is a **rectification** fiducial, not a
  scale one. Cell extraction crops between the detected guides and resamples to a canonical cell,
  discarding the spacing. Surviving legibly and carrying magnitude are different properties.

What does work is a plate assembled **locally, after generation, from published bytes**. It is
exact, costs no provider operation, and cannot be redrawn.

## External anchors

Recorded for orientation. Unlike everything above, these were **not** verified against this
repository and should be re-checked before any threshold is derived from them; see
[Prior-art register](prior-art.md) for how such entries are governed.

| Anchor | Reported finding | Bearing |
| --- | --- | --- |
| Instrument-reading benchmarks for frontier vision models | High accuracy identifying what an instrument shows; substantially lower accuracy reading its value | Supports posing scale as selection rather than estimation. |
| Measure-an-object-against-a-reference studies | Sizeable mean error with systematic underestimation; two-stage prompting that names the reference reduces it | Supports naming the reference explicitly and keeping the output space coarse. |
| Archaeological and photogrammetric scale-bar protocol | Purpose-built calibrated bars over opportunistic objects; more than one known distance, because a single wrong one rescales everything silently | Supports redundancy and reject-rather-than-clamp admission. |
| Microscopy publication guidance | A burned-in bar rather than a declared magnification, because downstream resizing destroys a declared number | Supports measuring on the bytes that ship. |
| Model-sheet and cast-comparison practice in game art | Shared horizontal rails and a standing reference view; a scale reference kept permanently in the master scene | Supports both plates: the cast comparison for magnitude, the model sheet for cross-state coherence. |

## Coherence within one actor

Magnitude is a question between entities. There is a second, independent question inside a single
actor — whether its motion states are drawn at the same scale as each other — and the two failed
separately in the shipped consumer.

![All forty frames of one actor at one uniform source scale: the shipped per-state scale beside the same frames rebased onto the idle baseline](../media/motion-rebase-ab.webp)

**The consumer amplifies the disagreement rather than carrying it.** An actor's ten motion atlases
were generated in ten calls, and their source head extents cluster within **1.16x**. Drawn on
screen they spanned **1.58x**. The artwork is markedly more consistent than the result, because
scaling by an atlas's cell height is anticorrelated with pose: the model composes each state to
fill its own frame, so a compact pose gets a short cell and is then scaled up to compensate for a
shortness that was never scale.

Two distinct mechanisms produced that, pulling opposite ways:

| Class | Mechanism | Effect |
| --- | --- | --- |
| Player | Reference synthesised per state from the atlas's cell height | Every state pinned near one height. A crouch drew *taller* than the rest pose — pose erased. |
| Player, two states | Two states omitted from that fill and left on the rest pose's factor | Drew 25% and 42% short. |
| Mob | Display size set once from the rest atlas and never re-applied | Scale froze while frames changed, so drawn size tracked each texture's cell. One creature lost **25%** of its height whenever it attacked. |

**Within one atlas, scale is constant.** Read across all forty frames of one actor, head mass, limb
bulk and line weight hold constant down each state while only the pose changes — including where
the painted box collapses to 27% of the rest pose. Four frames share one generation canvas and
therefore share one scale. The correction is per state; a frame's height is pose, and preserving it
is the point.

**Equalising one anatomical feature is worse than judging the set.** Measuring a single feature per
sheet and matching it carried roughly &plusmn;8% per reading, and each error landed straight on that
state's scale with nothing positioned to catch it — it produced a climb taller than the rest pose
and a collapse 20 px short. A deterministic silhouette proxy was tried alongside it and disagreed by
up to 21% precisely where a limb approaches the head, independently reproducing the conclusion this
repository had already recorded: a head is a semantic feature and is not recoverable from alpha.

Composing every frame onto one plate at a uniform source scale, naming the baseline, and reading the
whole set in a single pass tightened the rest-frame spread from **1.64x to 1.46x**, with the residual
being pose. It also makes the judgement auditable, because the plate is the evidence and a reader can
disagree with one named state.

**Plate capacity is bounded by pixels, not by frame count.** The constraint is the vision input's
budget after downscaling, so a near-square grid is worth far more than a strip: forty frames laid out
as paired state groups hold roughly two hundred pixels each, and the practical ceiling is near sixty.
Since a plate is intra-actor by construction it never holds a cast, so nothing in a current package
approaches the limit.

## Open questions

- **A composited scale marker was ruled out, and a second approach with it.** An earlier design
  gave every actor atlas a generated pose-free reference cell. It was retired before promotion: a
  single plate carrying an actor's whole motion set answers the same question, works on artwork
  already on disk, needs no canvas change, no prompt clause, and no regeneration, and removes the
  only unverified provider dependency in the design. See [Motion rebase](../spec/motion-rebase.md).
- **Single-feature matching was tried and is worse than the plate.** Measuring one anatomical
  feature per sheet and equalising it carried roughly &plusmn;8% per reading, and those errors landed
  directly on the scale with nothing able to catch them: it produced a climb taller than the
  baseline and a death 20 px short. Judging every frame together against a visible baseline
  tightened the rest-frame spread from 1.64x to 1.46x, and the residual is pose.
- **Recovered magnitudes are one judge, once.** They are a starting catalogue for review, not
  ground truth, and at least one is arguable on its face: a well scored on its A-frame rather than
  its rim reads very differently from one scored on the rim.
- **Uniform rescaling cannot repair internal proportion.** A handcart at the right overall
  magnitude may still have a wheel wrong against its own bed. That defect needs proportion review,
  not scale admission.
- **Midground and foreground plates carry an implied object scale this study does not reach.**
  Bringing foreground subjects into agreement makes any disagreement with a painted layer more
  visible, not less.

## Reproducing the measurements

Every figure above derives from a published package under `out/` plus the consumer's own sizing
code. The measurements are: alpha bounding box at the runtime's painted-alpha threshold, per cell
for a strip; canvas fill as bbox height over canvas height; and drawn height as the consumer's
constant times that fill. No provider operation and no credential is involved in reproducing any
of them.

The two embedded images are deterministic local composites of that same package: no provider
call, no retouching, and no pixel the pipeline did not already produce. Both were composited from
`out/bellweather-prepared-v11-bound`, whose manifest digest is
`e75a5a3657241cbac4d087b56268cb13f808bc7ce5f9cb2402088043da51c4b2`, so the heights drawn in the
figures and the numbers quoted above come from one build.

`scripts/render_asset_scale_figures.py` composites both figures and prints the manifest digest it
rendered from, so a reader can confirm a figure against the build quoted here. That proves the
sizing arithmetic and the composition; it does not approve generated appearance, and it authors
no contract. The judged heights and per-state multipliers live in the script as the figure inputs
they are — the study is where they are argued, the specs are where the vocabulary is ratified, and
neither reads them back from the renderer.

```sh
uv run python scripts/render_asset_scale_figures.py \
    --package out/bellweather-prepared-v11-bound --output docs/media
```

Glyph rasterization depends on the fonts installed on the rendering machine, so the committed
bytes are one author's render rather than a cross-machine reproducible artifact.

# Prior-art register

> **Status: research anchors.** Every entry is someone else's published work, recorded so
> contributors can find it and — more importantly — know whether it applies to our inputs before
> spending provider budget re-deriving it. Nothing here is an approved prompt input, a rights
> grant, or an implementation commitment.

## Why this exists

Most published work on a problem that looks like ours does not transfer, and the reason is almost
never a flaw in the work. It is a property of *our* inputs that the authors had no reason to
consider. A register that lists only titles invites contributors to over-trust it; a register that
records the disqualifier alongside the citation saves the spike.

An entry earns its place by being genuine, relevant prior art. It does not have to be adoptable.
Knowing that a sound method is blocked, and by exactly what, is the more valuable half of this file.

## How to read an entry

Each entry carries one applicability tag and zero or more limit tags.

| Applicability | Meaning |
| --- | --- |
| `adoptable` | Implementable against our inputs today, with no unresolved blocker. |
| `blocked` | Sound method, blocked by a named property of our inputs or our provider access. |
| `context` | Vocabulary, orientation, consumer requirement, or cautionary result. Not a technique we would implement. |

| Limit | Meaning |
| --- | --- |
| `stationary` | Assumes a stationary texture — statistics roughly uniform across the image. Breaks on a composed scene with named subjects at authored positions. |
| `opaque-only` | Assumes a fully opaque raster. Has no alpha semantics, and no notion of a partially covered edge. |
| `no-api` | Requires access to model internals we do not have through a hosted endpoint. |
| `2d-torus` | Wraps on both axes. Our scrolling layers wrap in x only. |
| `unreachable` | Exists only inside a GUI tool or product we cannot call from the graph, whatever its merits. |

An applicability tag is a claim about **our** inputs, not a judgement of the work, and it may be
revised. When you revise one, say why in the entry.

**A limit tag on an `adoptable` entry is not a blocker.** It records what the authors assumed, so a
reimplementation knows what it must handle itself. `opaque-only` on a published algorithm means the
paper works in RGB; it does not mean alpha defeats the method. Read the entry's verdict before
concluding a technique is closed to us — the tags narrow the search, the prose decides.

## Governance

- **Research anchors never reach prompts.** Same rule as the
  [game visual reference](../game-visual-reference.md): a citation is a place to read, not a token
  to send to a provider.
- **Citing is not a redistribution grant.** Do not vendor figures, sample textures, datasets, or
  code from a cited work into this repository without a separate documented rights basis. See
  [OSS and IP policy](../oss-ip.md) and [AGENTS.md](../../AGENTS.md).
- **Record the disqualifier, not just the verdict.** `blocked` with no named limit is not an entry.

Links last verified 2026-08-28.

---

## 1. Horizontal loop construction and seamless tiling

Our scrolling map layers differ from the tiling literature's subject on two axes at once. They are
**semantic composed scenes** — a village, a fence, a bridge, with named subjects at authored
positions — rather than stationary textures; and they are **alpha-bearing**, wrapping in x only.
Nearly every work below assumes the opposite on both counts. That is the recurring reason a
technique that reads as directly applicable is not.

Our own implementation and its measured behaviour live in
[Horizontal loop construction](../loop-construction.md) and
[Verified single-axis image repeat](../image-repeat.md).

One orienting fact before reading further, because it decides which of these works could ever help.
A repair method joins two ends; it cannot make ends that disagree agree. Where a layer's own ends
differ in the source art — our village layer's ground line sits 21 px lower at its tail than at its
head, against 0 or −1 px for every other layer — **no method in this section applies, because the
input is unloopable as authored.** A human artist handed that strip would repaint the ground
baseline rather than repair the seam. Reach for the works below only once a layer's ends already
agree; otherwise the fix belongs upstream, in the layer brief.

### 1.1 Authoring-time methods — the seam is prevented, not repaired

The load-bearing insight of this whole section: production art is painted on a cylinder from the
first stroke, so no seam ever exists to repair. Our generated-bridge construction is solving a
problem the industry designed away.

**[Krita Wrap Around Mode](https://docs.krita.org/en/tutorials/common_workflows.html)** — Krita
manual. `View > Wrap Around Mode` (Shift+W) tiles the canvas live in the viewport; a stroke near
one edge appears simultaneously on the other.
→ `context`. Records the capability we cannot buy from a hosted endpoint: the canvas topology is a
cylinder at paint time. A hosted image model paints on a plane. This is a structural account of our
bridge difficulty, not a prompting deficit.

**[Draw tiling patterns with the wrap around mode](https://www.gdquest.com/tutorial/krita/legacy/krita-from-zero/chapter-5/40-wrap-around-mode/)**
— GDQuest. Practical walkthrough of the above, aimed at game artists.
→ `context`.

**[Create a Seamless Texture Repeat](https://www.melarmstrong.com/blog/photoshop-tutorial-create-a-seamless-texture-repeat)**
and [Create Seamless Textures in Photoshop](https://photoshoptrainingchannel.com/create-seamless-textures/)
— the Offset technique. `Filter > Other > Offset` with *Wrap Around*, shift by half the width, then
heal the seam that is now in the interior.
→ `adoptable` as a mechanism. The roll is exact and lossless, and moving the seam to the interior is
precisely what our `repaint_seam` construction does. Recording it here because our construction was
arrived at independently and it is worth knowing it matches the practitioner standard.

**[Tiled Mode](https://www.aseprite.org/docs/tiled-mode/)** — Aseprite manual. The same live-tiling
canvas for pixel art.
→ `context`.

### 1.2 Repair-time methods — removing a seam that already exists

**[Image Quilting for Texture Synthesis and Transfer](https://www.ipol.im/pub/art/2017/171/article_lr.pdf)**
— Efros & Freeman, SIGGRAPH 2001; linked here as the IPOL reimplementation, which carries the
algorithm in reproducible detail. Introduces the **minimum-error boundary cut**: given two patches
with an overlap, find the least-cost cut path through the overlap by dynamic programming rather
than blending.
→ `adoptable` · `stationary` `opaque-only`. Deterministic, offline, zero provider calls. The
`opaque-only` tag is an assumption of the paper, **not a blocker for us**: the cut is driven by a
per-pixel cost function, so premultiplied RGBA or a cut path restricted to fully covered rows
handles alpha without changing the method.

The real limit is different and it is structural: on a composed layer this routes the visible
discontinuity through low-contrast content, but it **cannot correct a global mismatch**. Our village
layer's ends differ by a 21 px ground-height step in the source art; a min-error cut would hide the
cut, not level the ground.

**[Graphcut Textures: Image and Video Synthesis Using Graph Cuts](https://dl.acm.org/doi/10.1145/882262.882264)**
— Kwatra et al., SIGGRAPH 2003. Replaces the dynamic-programming cut with max-flow/min-cut, using a
distance metric that stops the path taking shortcuts through high-cost regions and spreads residual
error over a longer path.
→ `adoptable` · `stationary` `opaque-only`. Strictly better than the quilting cut on the same
inputs, with the same alpha caveat (assumed, not blocking) and the same global-mismatch limit.
**Currently the highest-value untried item in this section:** free, deterministic, reimplementable
against our own inputs, and never yet measured against our layers.

**[Make It Tile Photo](https://helpx.adobe.com/substance-3d-designer/substance-compositing-graphs/nodes-reference-for-substance-compositing-graphs/node-library/filters/tiling/make-it-tile-photo.html)**
— Adobe Substance 3D Designer. Edge fix-up for an image that does not tile due to non-continuous
edges; the documentation states it "does not affect anything other than the input image's edges."
→ `context` · `unreachable`. Read it before changing our bridge node — it is the closest shipped
commercial equivalent to our `generated_bridge` and its parameterization is mature — but it is a
node inside a commercial GUI tool, not a library or endpoint the graph can call. That is what closes
it to us, not any question about alpha; its transparency behaviour is **unverified here** and does
not affect the verdict. The reimplementable algorithms in this section are the ones to pursue.

**[Make It Tile Patch](https://helpx.adobe.com/substance-3d-designer/substance-compositing-graphs/nodes-reference-for-substance-compositing-graphs/node-library/filters/tiling/make-it-tile-patch.html)**
and [Make it Tile (Sampler)](https://experienceleague.adobe.com/en/docs/substance-3d-sampler/using/filters/tools/make-it-tile)
— grid-based semi-random stamping of a source patch into a larger tiling image.
→ `context` · `stationary`. Noted mainly for a structural observation: Substance ships **two**
separate nodes, fix-the-edges and restamp-the-content. That is the same split as our
`generated_bridge` versus `repaint_seam`, arrived at independently, and it is an argument for
selecting the method per layer rather than per map.

**[Tiling](http://wiki.polycount.com/wiki/Tiling)** and
[Seams in tiling textures](https://polycount.com/discussion/146897/seams-in-tiling-textures)
— Polycount wiki and forum. The practitioner canon: Offset plus Clone brush, the High Pass trick,
and Make It Tile.
→ `context`. Useful for terminology and for what artists actually reach for first.

### 1.3 Edge-matched tile sets

**[Wang Tiles for Image and Texture Generation](https://dl.acm.org/doi/10.1145/882262.882265)**
— Cohen, Shade, Hiller & Deussen, SIGGRAPH 2003
([PDF](https://www.cs.jhu.edu/~misha/Spring25/Readings/Cohen03.pdf)). Tiles carry colored edges;
any arrangement whose shared edges match is valid, so a small set covers an arbitrarily long
non-repeating run.
→ `adoptable`. The 1D specialization is far smaller than the 2D one: a horizontal strip needs only
vertical-edge classes, so two classes give four segments, and any closed walk through them loops.
This is the closest thing to the "47-tile equivalent" for our problem. It buys **non-repetition**,
which single-strip looping cannot give at any quality. The original formulation is `stationary`, but
the scheme itself is content-agnostic — the only requirement is that segments share an edge profile,
which authored layers can satisfy.

**[Content-aware Tile Generation using Exterior Boundary Inpainting](https://arxiv.org/abs/2409.14184)**
— 2024. Reformulates tile generation as inpainting *constrained by exterior boundary conditions*
plus a text prompt, using pretrained diffusion inpainters without retraining. Supports Wang tiles
and introduces a Dual Wang scheme for better continuity.
→ `blocked` · `no-api`, but **read it for the reformulation**. Its central move is the inverse of
our bridge: constrain the exterior boundary and inpaint inward, rather than inpainting an interior
seam between frozen neighbours. That inversion is transferable even where its stack is not.

### 1.4 Model-side generation

**[Seamless tiling / circular padding](https://www.runcomfy.com/comfyui-nodes/ComfyUI-seamless-tiling)**
— ComfyUI node documentation, and the same technique in other diffusion front-ends. Patching
`Conv2d` `padding_mode` to `circular` makes every convolution wrap, so the network generates on a
torus natively. Asymmetric variants wrap one axis only — exactly our case.
→ `blocked` · `no-api`. This is the honest, load-bearing explanation for why extended prompt
engineering against a hosted endpoint plateaus: **the capability gap is architectural, not
promptable.** Record any future prompt-only spike against this entry before funding it.

**[Generating Tilesets with Stable Diffusion](https://www.boristhebrave.com/2025/02/04/generating-tilesets-with-stable-diffusion/)**
— Boris the Brave, 2025. Parallel denoising of a whole tile set, each tile inpainted inside a 3x3
neighbour context, with VAE GroupNorm statistics computed across all tiles jointly.
→ `context`, cautionary. Results were recognizable but carried visible transition lines and
inconsistent appearance across tiles, degrading at detail level. Read before promising that
edge-matched generation is a solved problem.

### 1.5 Hiding repetition — the inverse problem

**[Texture repetition](https://iquilezles.org/articles/texturerepetition/)** — Inigo Quilez. The
canonical treatment of making a correctly tiling surface *stop looking* tiled.
→ `context`. Not our problem yet; it becomes our problem the moment looping works and the period is
visible.

Vocabulary note: **"detiling" is not established terminology.** The phrasings practitioners
recognize are "breaking up tiling" and "hiding texture repetition."

### 1.6 Consumer requirements

**[2D Parallax](https://github.com/godotengine/godot-docs/blob/master/tutorials/2d/2d_parallax.rst)**
and [Parallax2D](https://docs.godotengine.org/en/stable/classes/class_parallax2d.html) — Godot
documentation. `repeat_size` repeats and offsets child textures so the node's position loops. The
tutorial requires "an image designed to repeat seamlessly and is the same size or larger than your
viewport **before** setting the repeat_size."
→ `context`, but normative for any consumer we target. No mainstream engine repairs a seam. Period
correctness is a producer obligation, which is why it is carried explicitly in our manifest.

**[Pixelblog 23 — Parallax Scrolling](https://www.slynyrd.com/blog/2019/11/12/pixelblog-23-parallax-scrolling)**
— SLYNYRD. Practitioner account: scroll rates chosen as exact divisors of the canvas width so every
layer loops on a common period, layers painted as extended strips against a screen-width guide.
→ `context`. The divisor discipline is a cheap constraint we do not currently impose.

### 1.7 Adjacent vocabulary

**[Edge padding](http://wiki.polycount.com/wiki/Edge_padding)** — Polycount wiki — and
[Texture dilation or padding](https://experienceleague.adobe.com/en/docs/substance-3d-painter/using/technical-support/workflow-issues/export-issues/texture-dilation-or-padding)
— Adobe Substance. Dilating pixels outward past a coverage boundary so sampling never pulls in
empty space; the gaps between islands are "gutters," and the failure is "bleed."
→ `context`. Different geometry from ours — these describe UV islands in 3D — but this is the
established vocabulary for the transparent-margin failures we hit on layer ends. Write "insufficient
edge padding," not an invented term.

---

## Adding an entry

Place it under the topic section it belongs to, creating a new `##` topic section if none fits. This
register is not limited to tiling and is expected to grow.

An entry is:

1. A **link and attribution** — author or publisher, venue, year where they exist.
2. **What it actually does**, in one or two sentences, in the authors' terms.
3. **One applicability tag and any limit tags**, followed by the verdict *in our terms* — what it
   would mean for our inputs, and, when `blocked`, exactly what blocks it.

Prefer a primary source over a summary, and an open-access mirror alongside a paywalled record.
Verify a link before adding it, and update the "links last verified" date when you sweep them.

Do not add an entry you have not read enough of to write point 3 honestly. A citation with an
invented verdict is worse than no entry, because it will be trusted.

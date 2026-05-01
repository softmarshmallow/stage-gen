# Platformer terrain tileset spec

## Compact 4×4 essentials (current target)

16 cells, one role each. 1024×1024 canvas → 256 px per cell — enough headroom
for the model to render clean geometric primitives.

```
Row 1 — TOP SURFACE (sky above):
  c0 top-left corner    (magenta on TOP + LEFT)
  c1 top middle         (magenta on TOP only)
  c2 top-right corner   (magenta on TOP + RIGHT)
  c3 top single         (magenta on TOP + LEFT + RIGHT — 1-tile platform top)

Row 2 — SLOPES + INNER CORNERS:
  c0 slope up 45°       (rises from bottom-left to top-right; magenta in top-left triangle)
  c1 slope down 45°     (rises from top-left to bottom-right; magenta in top-right triangle)
  c2 inner corner TL    (concave: magenta in top-left QUADRANT only, dirt elsewhere)
  c3 inner corner TR    (concave: magenta in top-right QUADRANT only)

Row 3 — SIDES + BOTTOM EDGES:
  c0 side-left          (vertical cliff face; magenta on LEFT only)
  c1 side-right         (vertical cliff face; magenta on RIGHT only)
  c2 bottom-left corner (magenta on BOTTOM + LEFT)
  c3 bottom-right corner (magenta on BOTTOM + RIGHT)

Row 4 — FILL + FLOATING PLATFORM:
  c0 interior fill      (solid dirt edge-to-edge, no magenta)
  c1 float platform L   (grass top, rounded bottom-left, magenta on TOP + LEFT + BOTTOM)
  c2 float platform M   (grass top, flat bottom, magenta on TOP + BOTTOM)
  c3 float platform R   (grass top, rounded bottom-right, magenta on TOP + RIGHT + BOTTOM)
```

Stage builder picks tiles by inspecting the 4-neighbour solid/sky pattern of
each (x, y), with slopes for ±1 height transitions.

---

## (legacy) 8×8 spec — kept for reference

Reference for an 8×8 grass-on-dirt tileset. Each of the 64 cells has a
unique structural role — no redundant duplicates.

## Conventions in 2D platformer tilesets (industry reference)

- **47-tile autotile** is the gold standard for side-scrollers — handles every
  combination of solid neighbors (4-way + diagonals).
- **16-tile autotile** covers 4-way only; common in top-down games.
- **Slopes are not part of standard autotile sets** — usually authored
  separately as 1-tile (45°) and 2-tile (22.5°) variants in both directions.
- **Kenney's pixel platformer pack** (the de-facto open-source convention) ships:
  surface L/M/R + fill + sides + 1-tile slopes per biome.

We adapt this into a denser layout that fits 64 cells, focusing on a single
biome (grass-on-dirt) so every cell is meaningful.

## Sheet layout (8 rows × 8 cols, magenta = sky)

| Row | Section | Purpose |
|---|---|---|
| 1 | Top surface | Where ground meets sky horizontally — corners, middles, single |
| 2 | Slopes | Diagonal transitions: 45° up/down + 2-tile gentle up/down |
| 3 | Corners | Inner (concave) + outer (convex) corners for cliff geometry |
| 4 | Side & bottom edges | Vertical cliff faces and floating-platform bottoms |
| 5 | Fill A | Interior dirt, edge-to-edge (8 subtle variants) |
| 6 | Fill B | More fill variants (slightly different rocks/texture) |
| 7 | Floating platforms | Self-contained 1- and 2-tile floating platform pieces |
| 8 | Special | Stair-step + extra slope joinery |

### Per-cell roles

```
Row 1 — TOP SURFACE (sky above):
  c0 top-left-corner       (sky above + left side)
  c1 top-mid               (sky above only) — clean
  c2 top-mid-flower        — same surface, with a flower decoration on top
  c3 top-mid-grass-tuft    — same surface, with a grass tuft
  c4 top-mid-pebble        — same surface, with a small pebble
  c5 top-mid-clean-2       — another clean variant
  c6 top-right-corner      (sky above + right side)
  c7 top-single            (sky above + left + right; 1-tile-wide platform top)

Row 2 — SLOPES:
  c0 slope-up-gentle-A     (2-tile gentle slope going up-right; left half)
  c1 slope-up-gentle-B     (same slope; right half)
  c2 slope-up-steep        (1-tile 45° going up to the right)
  c3 slope-up-cap          (slope meets flat going right — junction tile)
  c4 slope-down-cap        (flat meets slope going down to the right)
  c5 slope-down-steep      (1-tile 45° going down to the right)
  c6 slope-down-gentle-A   (2-tile gentle going down-right; left half)
  c7 slope-down-gentle-B   (same slope; right half)

Row 3 — CORNERS:
  c0 inner-corner-TL       (concave: sky in top-left, ground rest)
  c1 inner-corner-TR       (concave: sky in top-right)
  c2 inner-corner-BL       (concave: sky in bottom-left)
  c3 inner-corner-BR       (concave: sky in bottom-right)
  c4 outer-corner-TL       (convex: ground ONLY in top-left, sky rest — overhang)
  c5 outer-corner-TR       (convex)
  c6 outer-corner-BL       (convex)
  c7 outer-corner-BR       (convex)

Row 4 — SIDE & BOTTOM EDGES:
  c0 side-left             (vertical cliff face, sky on left)
  c1 side-right            (vertical cliff face, sky on right)
  c2 bottom-left-corner    (cliff bottom-left, sky below + left)
  c3 bottom-mid            (cliff bottom mid, sky below only)
  c4 bottom-mid-2          (variant of c3)
  c5 bottom-right-corner   (cliff bottom-right, sky below + right)
  c6 wall-vertical-1       (interior vertical cliff slice, no edges)
  c7 wall-vertical-2       (variant)

Row 5 & 6 — INTERIOR FILL (16 cells):
  Solid edge-to-edge dirt with subtle pebble/rock variations.
  No magenta. Used under the surface and inside cliffs.

Row 7 — FLOATING PLATFORMS:
  c0 float-left            (left half: grass top + curved bottom-left)
  c1 float-mid             (mid: grass top + flat bottom)
  c2 float-mid-2           (variant)
  c3 float-right           (right half)
  c4 float-single          (1-tile platform: all 4 edges)
  c5 float-2-tile-L        (2-tile platform; left)
  c6 float-2-tile-R        (2-tile platform; right)
  c7 float-cloud           (alternative cloud-style floating tile)

Row 8 — SPECIAL JOINERY:
  c0 stair-up-1            (small step up; flat → 1-tile rise)
  c1 stair-up-2            (continuation)
  c2 stair-down-1
  c3 stair-down-2
  c4 ramp-up-long-A        (wider 3-tile gentle ramp; first third)
  c5 ramp-up-long-B        (middle third)
  c6 ramp-up-long-C        (last third)
  c7 spacer                (pure magenta — used as a sentinel / not painted)
```

### Geometric conventions

- All ground tiles share a single colour palette (mossy green grass, warm
  brown dirt with darker rocks).
- The grass top sits at the same Y across all "top" tiles in row 1, so
  laying them side by side produces a continuous horizon.
- Slopes use a 22.5° (2-tile run) or 45° (1-tile run) pitch — no other angles.
- Inner-corner tiles are diagonal cuts: the diagonal goes through the cell
  centre, leaving a quarter-circle of sky in the labelled quadrant.

## Stage builder consumes this spec

The terrain stage builder will:

1. Plan a level as a sequence of segments: `flat(L)`, `slope_up`, `slope_down`,
   `gap(L)`, `cliff_up`, `cliff_down`, etc.
2. Realise the plan as a heightmap with metadata.
3. Pick the right tile per (x, y) using the section/cell roles above.

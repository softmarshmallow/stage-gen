# Godot 3x3-minimal 47-cell terrain reference

This document explains the topology encoded by
[`terrain_atlas_godot_topology_reference.png`](terrain_atlas_godot_topology_reference.png).
It is a cell-by-cell companion to the image, not an alternative lookup contract.
The authoritative machine-readable mapping is
`src/stage_gen/resources/terrain/godot_3x3_minimal_lookup_v1.json`.

The atlas uses the 47 reachable masks of Godot's historical **3x3 (minimal)**
autotile mode. It is a 12-column by 4-row terrain atlas with 47 selectable
terrain cells and one reserved checker placeholder. It is not a 9-slice, a set
of precomposed platform shapes, or a smooth-slope contract.

## How a mask is selected

For each occupied gameplay-map cell, inspect its eight neighbors:

```text
NW  N  NE
 W  C   E
SW  S  SE
```

The stored mask uses this exact order:

```text
nw, n, ne, w, center, e, sw, s, se
```

- `C` is always `1` because the selector runs only for an occupied map cell.
- A cardinal bit (`N`, `E`, `S`, or `W`) is `1` when that side-adjacent cell is
  occupied and `0` when it is empty or outside the map.
- A diagonal bit is `1` only when the diagonal cell **and both cardinal cells
  adjacent to that corner** are occupied. Otherwise it is `0`. For example,
  `NE = N and E and occupancy(x + 1, y - 1)`.
- Consequently, a diagonal can never be `1` while either adjacent cardinal bit
  is `0`. Diagonals behind an open side do not create additional masks.

This gating produces exactly 47 reachable masks:

| Cardinal-side pattern | Patterns | Eligible corners per pattern | Masks |
| --- | ---: | ---: | ---: |
| No connected sides | 1 | 0 | 1 |
| One connected side | 4 | 0 | 4 |
| Two opposite connected sides | 2 | 0 | 2 |
| Two adjacent connected sides | 4 | 1 | 8 |
| Three connected sides | 4 | 2 | 16 |
| Four connected sides | 1 | 4 | 16 |
| **Total** |  |  | **47** |

## Reading the cell table

Coordinates are zero-based `(column, row)`, measured from the atlas's top-left
cell. “Connected sides” lists cardinal neighbors whose occupancy bit is `1`.
“Filled corners” lists eligible diagonal neighbors whose gated bit is `1`.

For rendering:

- a connected side must meet compatible terrain at the same grid-relative
  connector band;
- an exposed side faces empty space;
- a filled corner continues terrain through that diagonal;
- a notched corner has both adjacent sides connected but its diagonal empty,
  so it represents a concave opening at that corner; and
- a corner behind an exposed side is part of the outer contour, not an
  independently selectable diagonal state.

The descriptions below state selection topology, not material. A cap is not
necessarily grass, and fill is not necessarily dirt. Biome art may use stone,
ice, sand, masonry, roots, metal, or another coherent material while preserving
the same connectors and exposed contours.

## All 48 atlas cells

| Coordinate | Mask | Connected sides | Filled corners | Selector role |
| --- | --- | --- | --- | --- |
| `(0, 0)` | `000010010` | `S` | `—` | End piece connected S; exposed on N, E, W. |
| `(1, 0)` | `000011010` | `E+S` | `—` | Adjacent-side corner connected E and S; exposed on N and W; SE is a concave notch. |
| `(2, 0)` | `000111010` | `E+S+W` | `—` | Three-side junction open N; SW and SE are notched. |
| `(3, 0)` | `000110010` | `S+W` | `—` | Adjacent-side corner connected S and W; exposed on N and E; SW is a concave notch. |
| `(4, 0)` | `110111010` | `N+E+S+W` | `NW` | Four-side interior; NW filled; NE, SW, and SE notched. |
| `(5, 0)` | `000111011` | `E+S+W` | `SE` | Three-side junction open N; SW notched and SE filled. |
| `(6, 0)` | `000111110` | `E+S+W` | `SW` | Three-side junction open N; SW filled and SE notched. |
| `(7, 0)` | `011111010` | `N+E+S+W` | `NE` | Four-side interior; NE filled; NW, SW, and SE notched. |
| `(8, 0)` | `000011011` | `E+S` | `SE` | Adjacent-side corner connected E and S; exposed on N and W; SE filled. |
| `(9, 0)` | `010111111` | `N+E+S+W` | `SW+SE` | Four-side interior; SW and SE filled; NW and NE notched. |
| `(10, 0)` | `000111111` | `E+S+W` | `SW+SE` | Three-side junction open N; SW and SE filled. |
| `(11, 0)` | `000110110` | `S+W` | `SW` | Adjacent-side corner connected S and W; exposed on N and E; SW filled. |
| `(0, 1)` | `010010010` | `N+S` | `—` | Vertical connector; exposed on E and W. |
| `(1, 1)` | `010011010` | `N+E+S` | `—` | Three-side junction open W; NE and SE notched. |
| `(2, 1)` | `010111010` | `N+E+S+W` | `—` | Four-side interior; all four corners notched. |
| `(3, 1)` | `010110010` | `N+S+W` | `—` | Three-side junction open E; NW and SW notched. |
| `(4, 1)` | `010011011` | `N+E+S` | `SE` | Three-side junction open W; NE notched and SE filled. |
| `(5, 1)` | `011111111` | `N+E+S+W` | `NE+SW+SE` | Four-side interior; NE, SW, and SE filled; NW notched. |
| `(6, 1)` | `110111111` | `N+E+S+W` | `NW+SW+SE` | Four-side interior; NW, SW, and SE filled; NE notched. |
| `(7, 1)` | `010110110` | `N+S+W` | `SW` | Three-side junction open E; NW notched and SW filled. |
| `(8, 1)` | `011011011` | `N+E+S` | `NE+SE` | Three-side junction open W; NE and SE filled. |
| `(9, 1)` | `011111110` | `N+E+S+W` | `NE+SW` | Four-side interior; NE and SW filled; NW and SE notched. |
| `(10, 1)` | — | — | — | Reserved checker placeholder; never selected by the terrain lookup. |
| `(11, 1)` | `110111110` | `N+E+S+W` | `NW+SW` | Four-side interior; NW and SW filled; NE and SE notched. |
| `(0, 2)` | `010010000` | `N` | `—` | End piece connected N; exposed on E, S, and W. |
| `(1, 2)` | `010011000` | `N+E` | `—` | Adjacent-side corner connected N and E; exposed on S and W; NE is a concave notch. |
| `(2, 2)` | `010111000` | `N+E+W` | `—` | Three-side junction open S; NW and NE notched. |
| `(3, 2)` | `010110000` | `N+W` | `—` | Adjacent-side corner connected N and W; exposed on E and S; NW is a concave notch. |
| `(4, 2)` | `011011010` | `N+E+S` | `NE` | Three-side junction open W; NE filled and SE notched. |
| `(5, 2)` | `111111011` | `N+E+S+W` | `NW+NE+SE` | Four-side interior; NW, NE, and SE filled; SW notched. |
| `(6, 2)` | `111111110` | `N+E+S+W` | `NW+NE+SW` | Four-side interior; NW, NE, and SW filled; SE notched. |
| `(7, 2)` | `110110010` | `N+S+W` | `NW` | Three-side junction open E; NW filled and SW notched. |
| `(8, 2)` | `011111011` | `N+E+S+W` | `NE+SE` | Four-side interior; NE and SE filled; NW and SW notched. |
| `(9, 2)` | `111111111` | `N+E+S+W` | `NW+NE+SW+SE` | Fully surrounded interior; all sides and corners filled. |
| `(10, 2)` | `110111011` | `N+E+S+W` | `NW+SE` | Four-side interior; NW and SE filled; NE and SW notched. |
| `(11, 2)` | `110110110` | `N+S+W` | `NW+SW` | Three-side junction open E; NW and SW filled. |
| `(0, 3)` | `000010000` | `—` | `—` | Isolated occupied cell; every side is exposed. |
| `(1, 3)` | `000011000` | `E` | `—` | End piece connected E; exposed on N, S, and W. |
| `(2, 3)` | `000111000` | `E+W` | `—` | Horizontal connector; exposed on N and S. |
| `(3, 3)` | `000110000` | `W` | `—` | End piece connected W; exposed on N, E, and S. |
| `(4, 3)` | `010111110` | `N+E+S+W` | `SW` | Four-side interior; SW filled; NW, NE, and SE notched. |
| `(5, 3)` | `011111000` | `N+E+W` | `NE` | Three-side junction open S; NW notched and NE filled. |
| `(6, 3)` | `110111000` | `N+E+W` | `NW` | Three-side junction open S; NW filled and NE notched. |
| `(7, 3)` | `010111011` | `N+E+S+W` | `SE` | Four-side interior; SE filled; NW, NE, and SW notched. |
| `(8, 3)` | `011011000` | `N+E` | `NE` | Adjacent-side corner connected N and E; exposed on S and W; NE filled. |
| `(9, 3)` | `111111000` | `N+E+W` | `NW+NE` | Three-side junction open S; NW and NE filled. |
| `(10, 3)` | `111111010` | `N+E+S+W` | `NW+NE` | Four-side interior; NW and NE filled; SW and SE notched. |
| `(11, 3)` | `110110000` | `N+W` | `NW` | Adjacent-side corner connected N and W; exposed on E and S; NW filled. |

## What this topology can compose

The lookup selects one cell for every occupied map cell using all eight
neighbors. A binary occupancy map can therefore compose:

- solid terrain;
- genuinely one-cell-high floating platforms;
- orthogonal stair-step terrain;
- outer corners and ends; and
- concavities and enclosed holes.

It does not create a geometrically smooth slope. Smooth visual slopes and their
collision shapes require a separate contract.

## Godot terminology and provenance

Godot 3.x documented this as **3x3 (minimal)** autotile bitmask mode: four side
bits, four conditionally meaningful corner bits, and one center bit, with 47
complete arrangements. Godot 4.x describes tile selection through terrain sets
and terrain peering bits; this repository retains the historical topology name
to identify the exact locked lookup.

The topology reference is derived from the official Godot documentation and is
distributed under its documented CC BY 3.0 basis. Attribution and modification
details are recorded in `docs/terrain-atlas-provenance.md`.

Sources:

- <https://docs.godotengine.org/en/3.4/tutorials/2d/using_tilemaps.html#x3-minimal>
- <https://docs.godotengine.org/en/latest/tutorials/2d/using_tilesets.html>
- `docs/spec/terrain-atlas.md`
- `src/stage_gen/recipes/scrolling_preview/terrain_atlas.py`
- `src/stage_gen/resources/terrain/godot_3x3_minimal_lookup_v1.json`

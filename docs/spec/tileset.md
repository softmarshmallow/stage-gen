# Scrolling-preview terrain sheet

This is a recipe contract for the optional side-view scrolling preview. It is
not a required asset family for every `stage-gen` pipeline and it does not make
tile coordinates, gravity, or a horizontal camera part of the reusable
component contract.

## Sheet geometry

- Output: `tileset_<tag>.png`.
- Normalized canvas: 2400 x 800.
- Grid: 12 columns x 4 rows.
- Cell: 200 x 200 after normalization.
- Columns 0-3 are canonical roles; 4-7 and 8-11 repeat those four roles as
  visual variants.

| Row | Columns 0-3 |
|---|---|
| 0 | top-left, top-middle, top-right, isolated top |
| 1 | slope-up, slope-down, inner top-left, inner top-right |
| 2 | side-left, side-right, bottom-left, bottom-right |
| 3 | interior fill, platform-left, platform-middle, platform-right |

The layout prior communicates cell boundaries, air, surface material, and
interior fill. Surface appearance comes from the recipe's concept reference;
the geometry remains stable enough to slice deterministically.

## Role behavior

- Air/outside regions use the recipe's background-removal/chroma convention.
- Interior fill is opaque edge to edge.
- Surface roles share a consistent ground line.
- Slopes express one-cell transitions for the preview's one-dimensional
  heightmap.
- Platform pieces share a top line and compatible left/middle/right edges.

The preview may deliberately consume only a validated subset when a generated
sheet does not satisfy every role. Such fallback is a preview-adapter decision
and must be recorded; it must not silently redefine the generator component.

## Generic seam

A reusable sheet generator accepts explicit rows, columns, semantic cell
descriptions, anchors, reference inputs, and output-validation rules. The
labels above are supplied by this recipe. Another recipe can use the same
component for top-down terrain, effects, portraits, or UI without inheriting
platformer role names.

The consumer maps semantic roles to cell rectangles through its own adapter.
No component imports the browser preview's heightmap or texture-registration
code.

## Validation

1. normalized dimensions and grid divisibility are exact;
2. every canonical cell exists;
3. required opaque/transparent regions meet the recipe contract;
4. anchors align across compatible roles;
5. provenance records prompt, references, normalization, and attempts; and
6. a failed sheet is retried or reported, never accepted only because a file
   exists.

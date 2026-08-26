# Scrolling-preview prompt contract

This page documents how the recipe assembles prompts. It is a recipe-specific
contract, not a reusable component default. The executable prompt builders
under `src/stage_gen/recipes/scrolling_preview/` are the source of truth.

## Shared rules

Every prompt must:

1. request an original, brand-neutral result with no text or logos;
2. use the world concept only for palette, material, lighting, and shape
   continuity;
3. describe layout, anchors, cells, and forbidden regions independently from
   visual style;
4. state whether the asset is opaque or transparency-producing; and
5. include exactly one background instruction selected from the run mode.

Prompts must not request imitation of a franchise, brand, character, artist,
studio, game, album, track, or recognizable creator style.

## Transparency prompt variants

`native` is the default. Request a transparent background and no painted
backdrop, floor, exterior shadow, matte, or layout marks. Subjects may retain
intentional soft edge coverage, hair, foliage, glow, and translucent material;
decoded output must prove nontrivial alpha before it becomes canonical.

`ai` is an explicit compatibility mode. For sheets and isolated sprites,
request a uniform neutral grey field with clear subject separation, hard
readable silhouettes, no cast shadow crossing into the field, and no text or
layout marks in the final art.
For a depth layer where a flat field would obscure the intended band, request a
naturally isolated foreground region with clear separation from an uncluttered
background. Never request magenta in this variant. The generated opaque image
must pass validated background removal before it becomes canonical.

`chroma` is an explicit degraded fallback. Request a uniform exact `#FF00FF`
field everywhere outside intended content, with hard readable edges and no
shadow, glow, or antialias haze bleeding into the field. Deterministic local
keying converts that field to alpha. This mode never calls the remover.

The opaque world concept and designated opaque parallax backdrop use neither
variant. They remain full-bleed and unchanged.

## Layout references

Layout references communicate geometry only: grid cells, top/bottom rails,
feet baselines, slot rectangles, and reserved padding. Their exterior is
adapted to the selected strategy before use. A reference must not force a
`native` run to paint a matte or an `ai` run back to magenta.

The prompt tells the model to use rails and outlines as positional guides, not
painted output. Every subject stays inside its cell and respects shared anchor
lines. Final validation checks normalized dimensions and grid divisibility.

## Stage-specific content

### World concept

Request one fully opaque, wide 2D scene establishing palette, materials,
lighting, atmosphere, foreground, middle distance, and distant depth. It is a
style/reference root, not a sprite and not a candidate for removal.

### World plan

The structured prompt asks for a world-specific name and brief, an ascending
creature ladder, distinct obstacle themes, eight semantically distinct item
categories, and three to five parallax layers. Exactly one layer is opaque at
z-index 0 with parallax 0. Other layers describe the canvas fraction they paint
and the exterior region they leave for the selected transparency strategy;
the structured schema never hard-codes a colour.

### Parallax layers

The opaque layer fills the canvas. Every other layer paints only its declared
region against the strategy background. Content is sharp and edge-to-edge;
the preview applies edge fades, overlap, blur, and scroll speed at runtime.

### Tileset

Request the canonical 12-by-4 role grid with consistent surface and underground
materials. Air/outside regions use the strategy background. Interior-fill
cells remain opaque edge to edge. Slopes, sides, corners, and floating platforms
must have unambiguous silhouettes after transparency derivation.

### Character and creature sheets

Turnarounds, idle/hurt strips, the character motion master, and attack strip
preserve identity, scale, shared top/feet rails, and frame count. Each frame is
isolated against the strategy background. Derived alpha must leave meaningful
padding and preserve intentional interior colours.

### Obstacles, items, inventory, and portals

Grid and panel prompts preserve cell count, contact baselines, slot geometry,
and dramatic size variation. Exterior regions use the strategy background.
Glows and apertures stay inside hard subject boundaries; labels, dividers, and
reference rails are not painted.

## Failure, cache, and provenance

Mode is part of the run identity and cache contract. A cached artifact is valid
only when its prompt, mode, dimensions, hashes, and derivation metadata match.
For transparency-producing assets, provenance records the selected mode,
provider/raw path and hash, canonical path and hash, derivation kind,
component/tool, alpha validation, attempts, and failure state. Opaque artifacts
omit transparency derivation metadata.

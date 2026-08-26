# Illustrated map renderer

This module is the web-owned rendering boundary for the technical Universe
planner and explorer demo at `/universe/demo`. It consumes an already-authored
map package; it does not generate artwork or labels.

## Runtime contract

`illustrated-map-manifest-v1` binds one static PNG image to a versioned
image-pixel coordinate space and point features. Persisted fields use
`lower_snake_case`. Coordinates originate at the top left with `x` increasing
rightward and `y` increasing downward. The OpenLayers adapter performs the only
conversion to its bottom-left map coordinate space.

Each point feature carries stable identity, kind, image coordinates, label
placement and priority, minimum visible scale, hit radius, summary, and tags.
The renderer owns view controls, collision-aware labels, selection, and input
handling. It does not infer missing feature data.

The demo loader verifies that the manifest, PNG bytes, digest, and intrinsic
dimensions agree before rendering. The committed atlas is a bounded renderer
fixture, not evidence of an automated generation pipeline.

## Generation boundary

Any future system that asks a model to create map artwork or labels remains an
experiment under `spikes/universe-generation/`. The repository already ignores
all of `spikes/`. Do not import that spike from this module or commit its runs.

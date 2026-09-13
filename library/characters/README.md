# Canonical characters

This collection holds the repository's shared cast for documentation,
demonstrations, and asset pipelines.

Each character has a folder containing a short profile and its representations. Descriptive
filenames identify the pose or visual style, such as `full_body.webp` or
`sd_flat.webp`. Documentation and demonstrations can pick the image they need.
The profiles, artwork and textured GLB models are self-contained: browsing or reusing them requires
no game project, generator setup, or generated run output.

Each image should add a distinct angle, pose, outfit, or visual representation.
Crops, resized copies, and near-duplicate detail views do not count as additional
canonical images. Demonstrations and pipelines can derive those from the library
originals as needed.

The current cast:

| Character | Identity | Available representations |
| --- | --- | --- |
| [Nami](nami/README.md) | Repository mascot; human character in a charcoal and pink rabbit hood | Full-body and reaching poses, detailed and flat SD concepts, 3D SD model and preview |
| [Riko](riko/README.md) | Adult human woman with exaggerated hourglass proportions and contemporary streetwear | Fitted and loose sweater illustrations, flat SD concept, 3D SD model and preview |

Each 3D representation pairs `sd_3d.glb` with a studio render, `sd_3d.webp`.
The adjacent `sd_3d.json` binds the exact source, model, preview and independent
review. See the character's README for supported behavior and limitations, and
the [storage policy](../../docs/repository-storage.md#canonical-character-models)
for the publication contract.

A male character and an anthropomorphic animal character are planned next.

# Character pipeline figures

Uncurated observations from runs the pipeline already made, composited for
`docs/character-3d.md` on 2026-09-13 and encoded as lossy WebP. Every source run lives
under the ignored `spikes/3d-character-pipeline/` tree; paths below are relative to it.
The exports behind the accepted-character figures were each judged by an independent
final reviewer from its own renders (report paths noted); the composites were checked only
for correct labelling by their producer. Nothing here is published as art.

## `character-3d-lineup.webp`

- What: Six accepted cohort-09 exports at rest and cheer, front view.
- Size: 1139×652, 51,642 bytes; SHA-256 `545dff011b1e7490ef74dbe5b69a576eb2a6eb7b871ee421ffc898bddb4246b1`
- Source: renders made by the independent reviewers under evidence/provider-v1/qualification-whole-09/independent-final/<run>/renders/; exports fenn-01 b5b65203…, coro-01 0b20667c…, sela-01 08eb2c91…, fenn-02 3c1fea47…, coro-02 6853d64c…, sela-02 802d3a9f…
- Review status: each export accepted by an independent final review (report.json beside the renders), zero provider calls

## `character-3d-references.webp`

- What: Wren's canonical reference sheet, front view and back view.
- Size: 1383×670, 54,614 bytes; SHA-256 `cdb4c6996a6ce780e787da4cb7ca6658282bbfaa63c427062dd160411eeb712b`
- Source: runs/m3-canary-01/wren-01: upstream/operations/ref_image_002/reference.image, references/assets/ref_0004/image.png, references/assets/ref_0005/image.png
- Review status: references admitted by the run's reference review; the export they led to was independently confirmed (evidence/provider-v1/m3-canary-01/independent-final/wren-01/report.json)

## `character-3d-mesh-review.webp`

- What: The raw provider mesh in the matte preview, five views.
- Size: 906×470, 27,856 bytes; SHA-256 `2475a2f14739794c74e3227296b2310f7d7f1cc57b886dad4d30c9df99bab8b6`
- Source: runs/m3-canary-01/wren-01/observations/render-0001/{positive_z,negative_z,negative_x,positive_x,three_quarter}.png
- Review status: the part reviewer's own evidence; the final export was independently confirmed

## `character-3d-rig-atlas.webp`

- What: Rig atlas rows rest, shoulder_raise 0.75 s and cheer 1.5 s, unmodified.
- Size: 1405×883, 52,930 bytes; SHA-256 `482df2784d9cede3b7e64304521c9568556a4d15897fe8dbebc6b0a6a15fc920`
- Source: runs/m3-canary-01/wren-01/observations/atlas-0011/row-01.png, row-02.png, row-06.png
- Review status: the rig reviewer's evidence for export 33b1092e…, independently confirmed

## `character-3d-face-strip.webp`

- What: The 600 px face strip, unmodified.
- Size: 638×333, 13,812 bytes; SHA-256 `d001b11cc4fbe58ffe8e5ed64d318cb67daee831b56429a250de61fa0c31944b`
- Source: runs/m3-canary-01/wren-01/observations/atlas-0011/face.png
- Review status: as above

## `character-3d-refusals.webp`

- What: The three low-bar calibration controls: head gap, one-sided shoulder spike, scrambled face.
- Size: 1700×364, 36,396 bytes; SHA-256 `b83440b31d8845c2b141f536a401afcbbb6eb6f189466e17fd1a9fde7644c251`
- Source: runs/m1-calibration-14/{review_9ef584178d79,review_88ba9545e655,review_839d820060cf}/review_space/observations/atlas-0001 (cells cut by the atlas manifests)
- Review status: negative controls, refused by the reviewer in calibration 14 for the expected criterion; not accepted art

## `character-3d-recovery.webp`

- What: Sela-01's refused first rig and accepted second rig, shoulder_raise front, back and left.
- Size: 960×804, 23,254 bytes; SHA-256 `07080b3ac37c651a0c0d2ee1c45e72f3b64002051c7e3d32f500ea95e78fc078`
- Source: runs/qualification-whole-09/sela-01/observations/atlas-0013/row-02.png (rig_01) and atlas-0032/row-02.png (rig_02)
- Review status: rig_01 refused by the contained reviewer; rig_02 (export 08eb2c91…) independently confirmed

## `character-3d-godot-viewer.webp`

- What: The canary export in the disposable Godot viewer: rest, walk, run, samba.
- Size: 1598×328, 30,220 bytes; SHA-256 `ea0aeb00c5e3a297a4c08f3741f11429ff6406e85f970624c2a72d567d66ee5c`
- Source: evidence/provider-v1/m3-canary-01/consumer/stills/{rest,walk,run,samba}.png from capture.gd over the baked scratch asset
- Review status: the export was independently confirmed; the stills themselves are a consumer smoke check, not a review

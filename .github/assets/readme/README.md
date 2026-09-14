# README presentation media

## 3D character comparison

[`stagegen-3d-characters.gif`](stagegen-3d-characters.gif) illustrates the
[3D SD characters](../../../README.md#3d-sd-characters) section: reference art
above the corresponding rigged Nami, Helix and Riko models. The character sources
and representation records are in the [library](../../../library/characters/README.md)
at repository revision `e44f78042b666c1c845f5d295508df33231ff0c5`.

The motion is existing Mixamo Samba retargeted in Blender, after local rig cleanup.
The GIF is a six-second excerpt of the reviewed comparison video, repeated with a
pose cut at the boundary. It is not a seamless animation clip or a model download.
No caption, arrow or audio was added to the image.

- Output: 720 × 405, 72 frames over 6 seconds; 2,484,700 bytes.
- GIF SHA-256: `432d481a4faa791ee7e18d179b626fc1304529473d1fbbffb7e625d6ffa950b8`.
- Source: 1920 × 1080, 24 fps comparison video, SHA-256
  `7a04513330cf5ee98e31f184dfa6355dd48a8b2d7344621d95056475bf5c3227`.
- Transform: first 6 seconds, Lanczos resize, 12 fps sampling, 192-color
  difference palette, Bayer dithering (scale 3), rectangle differences, infinite
  repeat. GIF timing alternates 80/90 ms delays to total exactly 6 seconds.
- Review: independent inspection of decoded first and sampled frames on
  September 14, 2026 passed for complete bodies, reference/model correspondence,
  readable composition and retained colors. Every frame decoded successfully.
- Publication: the project owner explicitly authorized this README animation on
  September 14, 2026. This presentation uses the reviewed project character art
  and model renders with retargeted motion; the repository source-code license
  does not grant rights to the media or redistribute the underlying Mixamo clip.

Lossless working files and the full video stay outside the tracked presentation
assets, following the [storage policy](../../../docs/repository-storage.md).

## Movie sprite preview

[`movie-sprite.gif`](movie-sprite.gif) illustrates the
[Movie sprites](../../../README.md#movie-sprites) section. Yuzu and Riko retain
gentle body motion while separate facial patches animate a bilateral blink for
Yuzu, a canvas-left wink for Riko, and A/O mouth states for both. They are
composited over the Afterlight reading-lounge background. The preview is silent;
it does not demonstrate synchronized speech or a complete viseme set.

- Output: 720 × 405, all 192 frames over 12 seconds; 2,350,922 bytes.
- GIF SHA-256: `c6936c9e436dd8b5992d31eea4fa4b64ae845a88f07e0e54845c77b849fb65fc`.
- Source: final paired facial v2 review MP4, 1920 × 1080, 16 fps, 12 seconds;
  SHA-256 `03e1c340d6aa4a8af79565929af9f2309f4706c2330781d1ab91c41c515ad233`.
- Transform: complete source loop, Lanczos resize, 256-color difference palette,
  Bayer dithering (scale 3), rectangle differences, infinite repeat. GIF timing
  uses 144 delays of 60 ms and 48 of 70 ms to retain the full 12-second period.
  No captions, cropping, new motion or audio were added during conversion.
- Format comparison: the same-size, same-frame WebP trial at quality 85 and
  method 6 was 5,702,192 bytes. This GIF is smaller and fits the image budget.
- Review: independent source-versus-GIF inspection on September 14, 2026 passed
  across 12 facial samples, 6 whole-scene samples and 8 loop-boundary samples.
  All 192 frames decoded. Bodies and facial states remain legible; sampled wrap
  poses align without a new visible seam. Mild palette dithering is visible at
  enlargement. This is sampled review, not continuous playback acceptance or
  a claim of byte-identical encoded endpoint frames.
- Publication: the project owner explicitly requested this README showcase on
  September 14, 2026. This authorization covers the presentation derivative of
  the reviewed project character art and background; it does not promote the
  generation module or grant a blanket media license. Historical source rights
  and review records remain unchanged.

This is an experimental workflow result. The final video-derived first frame is
the canonical for the existing facial repaint pipeline, whose implementation is
unchanged. Source selection, stabilization and loop finishing remain experimental;
the image does not establish automatic success for arbitrary characters.
Native edge softness and Riko's wink-only eye coverage remain limitations.

The source video, comparison encodes and detailed reviews stay in ignored local
working output. Only this bounded README animation crosses into presentation
media; runtime assets and generation code retain their existing ownership.

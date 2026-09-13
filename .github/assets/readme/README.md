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

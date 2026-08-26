# Game concept style library

This is a prompt-writing map, not a schema or closed menu. It condenses the repository's global
game visual reference, illustration research, and runtime vocabulary into orthogonal decisions.
Read `docs/game-visual-reference.md` and
`concept-studio/style-dictionary/README.md` when deeper evidence exists in the checkout;
read `src/stage_gen/resources/prompting/image_style_vocabulary_v1.json` when exact shipped runtime
anchors matter. Do not depend on ignored `out/` evidence for a durable handoff.

## Describe style by facets

Select only the facets that materially define this concept:

- medium or production process: pixel raster, inked raster, cel illustration, gouache, watercolor
  and ink, painterly digital, pre-rendered 3D raster, or natural photography;
- character grammar and shape: grounded anatomy, head-heavy compact proportions, rounded geometry,
  angular silhouettes, mechanical modularity, or deliberately exaggerated action anatomy;
- line language: no contour, fine tapered ink, clean continuous ink, bold dark contour, broken dry
  brush, or dense hatching;
- shading and value: flat fills, one-band cel shadows, multi-band cel shadows, graphic shadow
  masses, continuous tonal modeling, or luminous rim separation;
- palette and light: bounded indexed palette, high-key pastel, muted earth pigments, jewel tones,
  saturated emissive accents, monochrome values, warm natural light, or theatrical contrast;
- surface: clean digital fill, paper grain, dry-brush opacity, screentone, analog cel texture,
  weathered material grain, or polished photographic texture;
- depth finish: flat graphic overlap, distinct painted planes, atmospheric value depth, volumetric
  haze, or physically plausible optical depth;
- camera and composition: keep this separate from rendering style;
- production role: cover key art, world concept, character study, mood painting, or UI exploration;
  and
- content presentation: keep genre, violence, sexuality, wardrobe/exposure, and audience separate
  from rendering style. Any depicted person must be unambiguously adult when adult presentation is
  requested.

## Useful compound directions

These neutral compounds have produced recognizable game-art behavior in repository experiments.
They are starting points, not mandatory names:

- explosive aura combat key art: bold contour, extreme foreshortening, hard cel shadows, saturated
  energy fields, radial debris, and a diagonal attack composition;
- super-deformed tactical mecha: modular toy-like machinery, compact proportions, readable team
  colors, orthographic-like staging, and restrained metallic highlights;
- operator-promotion portrait: fine tapered line, mature stylized anatomy, painterly cel hybrid,
  controlled asymmetry, dense costume materials, and atmospheric graphic motifs;
- luminous creature evolution: readable central silhouette, jewel-toned emission, layered magical
  effects, and a clear before/after power fantasy without interface chrome;
- adult sci-fi combat glamour: clearly adult anatomy, rear or over-shoulder action framing, fitted
  technical wardrobe, hard-surface weapon language, crisp cel-painterly rendering, and focused
  emissive accents;
- adult summer costume cut-in: clearly adult fashion styling, bright resort light, confident gaze
  and pose, polished cel-painterly finish, and uncluttered promotional composition.

Broad words such as `anime`, `cartoon`, `retro`, `Japanese`, `moe`, `shonen`, or `high detail` are
weak alone. Expand them into visible line, shade, palette, surface, proportion, depth, and role
choices. Never send a game, franchise, character, artist, or studio name as a style shortcut.

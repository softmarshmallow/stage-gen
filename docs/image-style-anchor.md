# Image style anchor

The style anchor fixes the *rendering medium* of generated images so it cannot
drift between calls. A free-text instruction like "make it anime" is re-read by
the model on every request, and long runs slide toward semi-realistic output.
The anchor replaces that instruction with a tracked, versioned clause.

## What it does

An edge LLM may return exactly one field — the chosen `style_mode`. It cannot
write prose, invent a medium keyword, name an artist, or reference a brand.
Local code expands that single token into the clause appended to the prompt:

```text
A weary cartographer resting at a roadside shrine at dusk.

Canonical style anchor — medium: clean 2D Japanese anime illustration.
Observable traits: crisp inked linework; flat cel-shaded color regions;
  discrete hard-edged shadow shapes; restrained gradients.
Asset treatment: visual novel character sprite with a readable silhouette
  and expression.
Exclude: photorealistic rendering; semi-realistic rendering; live-action
  imagery; 3D rendering; painterly realism; skin-pore detail; subsurface
  scattering; photographic depth of field; lens bokeh.
```

Everything after the author's first line comes from
`stage_gen/resources/prompting/image_style_vocabulary_v1.json`, not from the
model. Only the `Asset treatment` line varies across the eight asset kinds;
medium, traits, and exclusions stay byte-identical across a whole run.

## Vocabulary

Three modes ship in v1: `cel_shaded_anime_2d`, `photorealistic_natural`, and
`gouache_illustration_2d`. Each defines one medium keyword, four observable
traits, per-asset treatments for the eight `ImageAssetKind` values, and an
exclusion list. The selection skill is
`stage_gen/resources/skills/anchor-image-style/SKILL.md`.

## Opt in

Scrolling preview keeps its historical prompt path by default. Request the
selector with a JSON or TOML input:

```json
{
  "prompt": "original rain-dark stone ruins with pale moss",
  "style_anchor": { "schema_version": 1, "kind": "automatic_style_anchor_v1" }
}
```

## Binding

`append_style_anchor_once` applies the clause exactly once at the image
boundary. The anchor digest and the vocabulary digest are recorded in artifact
provenance and in the compiler cache key, so two images can be proven to share
a style contract, and editing the vocabulary correctly invalidates cached work.

# Visual Content Direction content controls v1

This document is the normative author-input contract for the six controls used
by the optional Visual Content Direction stage in `scrolling-preview`.
The shipped field name is `theme`; the normalized Python model is
`ThemeHandles`; and `THEME_SCHEMA_VERSION` is `1`.

The contract directs visible generation. It is not an age rating, content
classification, moderation verdict, legal determination, or promise that two
models will render equal distances between adjacent values.

## Input shape

For a `scrolling-preview` input object, `theme` is optional. When present, it
must be an object containing only these fields:

```text
theme:
  sexual_content:       integer 0..4, default 0
  nudity_exposure:      integer 0..4, default 0
  hostile_action:       integer 0..4, default 0
  injury_detail:        integer 0..4, default 0
  substance_depiction: integer 0..4, default 0
  threat_disturbance:   integer 0..4, default 0
```

Integers are strict. Booleans, fractional values, strings, values outside
`0..4`, a non-object `theme`, and unknown fields are invalid. Omitted control
fields default to `0`.

The presence of the object is identity-bearing:

- no `theme` key preserves the historical graph and prompt path;
- `theme = {}` and six explicit zeroes both invoke compilation and request the
  restrained endpoint; and
- callers must not treat absence and an all-zero object as equivalent.

`[content_controls]` is not a v1 alias and does not enable compilation. Callers
must use the exact shipped `theme` key rather than expecting the recipe to
guess or translate a different name.

## Axes

The axes were selected as independently steerable, observable qualities in a
still game asset. They resemble vocabulary used by regional classification
systems, but they were not adopted or empirically calibrated from one such
system.

| Field | Visible quality it directs |
| --- | --- |
| `sexual_content` | Adult romantic or suggestive pose, gaze, gesture, spacing, framing, and atmosphere. |
| `nudity_exposure` | Adult wardrobe coverage and designed exposure, independently of expression or intent. |
| `hostile_action` | Active aggression, attacks, combat posture, and force. |
| `injury_detail` | Visible wounds, blood, and physical damage. |
| `substance_depiction` | Visible intoxicants, consumption, and intoxication cues. |
| `threat_disturbance` | Menace, fear, horror, and disturbing atmosphere. |

This taxonomy is deliberately appearance-first and biased toward qualities an
image generator can show in a still. It does not cover language, gambling,
discrimination, self-harm, player agency, rewards, narrative centrality,
accessibility, or the complete regional-classification obligations of a game.

## Level interpretation

Every value is interpreted relative to the supplied scene and independently
of the other axes:

| Value | Target |
| --- | --- |
| `0` | Observable restrained counterstate. |
| `1` | Mild or indirect treatment. |
| `2` | Clear but restrained treatment. |
| `3` | Strong treatment. |
| `4` | Strongest coherent treatment admitted by the current compiler and provider boundary. |

Independence is load-bearing. Suggestive staging does not authorize increased
exposure; active combat does not authorize wounds; wounds do not authorize
additional aggression; intoxicants do not authorize threat; and ominous
atmosphere does not authorize an attack. A sword swing belongs to
`hostile_action`, a visible wound to `injury_detail`, and ominous lighting
without an attack to `threat_disturbance`.

For the two adult-presentation axes, value `4` remains a present-tense adult
fashion or editorial treatment within the compiler's admitted boundary. It
does not direct sexual activity, post-intimate context, clothing removal, or a
person who is not clearly adult and willingly present. In particular:

- `sexual_content = 4` with `nudity_exposure = 0` remains fully covered; and
- `nudity_exposure = 4` with `sexual_content = 0` uses neutral editorial or
  catalog posture rather than suggestive intent.

## Base brief, style, and hard locks

The base `prompt` owns subject matter and artistic language. Style terms,
character identity, reference-image bytes, rights, provider choice, recipe
layout, and publication decisions are not fields in this control object.

Formal hard locks are authored in the base prompt, not as new control keys.
The v1 compiler recognizes `MUST KEEP`, `HARD LOCK`, `KEEP EXACTLY`, and
`DO NOT CHANGE`. Prefer one scoped declaration per subject:

```toml
prompt = """
original bright 2D anime game art of a clearly adult character.
MUST KEEP the mint hair ribbon EXACTLY on the left side of the bob.
MUST KEEP the chestnut bob EXACTLY at chin length.
"""
```

Ordinary setup prose such as “centered,” “holding a cup,” or “fixed camera” is
soft direction. Only a formal marker creates a binding lock, and its scope ends
at punctuation or a coordination boundary. Repeat the marker for each
additional locked subject or placement.

## Compilation and image boundary

The recipe serializes the normalized controls in fixed order with schema and
compiler identity, then gives that canonical record and the base brief to the
structured compiler. The canonical record is retained in compiler provenance.

Raw field names, numeric control assignments or ratings, aliases, TOML/JSON
envelopes, and canonical control records must not appear in downstream planner
or image prompts. This restriction does not ban unrelated numerals such as
dimensions or “2D” in ordinary art direction. Image providers receive validated
prose selected from the
[scrolling content direction plan](scrolling-content-direction-plan-v1.md),
deterministic recipe instructions, and any recipe-owned references or templates
required by the asset stage.

Control values remain targets rather than semantic proof. A fresh plan or
image still requires independent review appropriate to its use; successful
schema validation alone is not a visual verdict.

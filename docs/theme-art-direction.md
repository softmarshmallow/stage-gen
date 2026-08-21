# Theme art-direction controls

Theme controls are an optional, pre-image art-direction layer for the
`scrolling-preview` recipe. They let an author keep one base visual brief while
requesting different visible content intensities. The feature is opt-in: a
plain prompt keeps the historical scrolling-preview path, and the
`dialogue-scene` recipe does not currently consume these controls.

This is a generation control, not an age rating. The six-axis set was not
adopted or empirically validated from a single study or classification standard.
Its names resemble common content descriptors, but the axes were selected for
asset generation: each controls a visible quality, can move independently, is
often accidentally coupled to another quality, and can be translated into
observable image direction. They do not map directly to ESRB, PEGI, IARC, BBFC,
GRAC, ACB, USK, CERO, or another regional classification. Those systems also
consider context and topics outside this contract, including language,
gambling, discrimination, self-harm, player agency, rewards, and how central
content is to the experience.

## Authoring a themed run

Give `stage-gen` a JSON or TOML input document. Every theme value is a strict
integer from `0` through `4`; omitted values default to `0`. Boolean, fractional,
out-of-range, and unknown fields are rejected.

```toml
prompt = "original bright 2D anime game art of a clearly adult café patron"

[theme]
sexual_content = 4
nudity_exposure = 4
hostile_action = 0
injury_detail = 0
substance_depiction = 0
threat_disturbance = 0
```

```sh
uv run stage-gen generate --recipe scrolling-preview \
  --input ./theme.toml --transparency ai
```

Live generation remains an explicit provider operation; see
[Provider operations](providers.md). A `style_anchor` may select a tracked
rendering-medium vocabulary independently of the theme controls.

## Axes and levels

The axes are independent conditional targets, not a single maturity score.
Their separation is intentional: suggestive staging need not increase exposure,
action need not add wounds, and an ominous environment need not add combat.
They may co-occur in one asset, but co-occurrence does not make them aliases: a
sword swing belongs to `hostile_action`, a visible wound to `injury_detail`, and
ominous lighting without an attack to `threat_disturbance`.

| Handle | Visible quality it directs |
| --- | --- |
| `sexual_content` | Adult romantic or suggestive pose, gaze, gesture, spacing, framing, and atmosphere. |
| `nudity_exposure` | Adult wardrobe coverage and designed exposure, independently of expression or intent. |
| `hostile_action` | Active aggression, attacks, combat posture, and force. |
| `injury_detail` | Visible wounds, blood, and physical damage. |
| `substance_depiction` | Visible intoxicants, consumption, and intoxication cues. |
| `threat_disturbance` | Menace, fear, horror, and disturbing atmosphere. |

This is deliberately a narrow, appearance-first taxonomy. It is biased toward
qualities an image generator can show in a still asset, especially adult
presentation, physical conflict, intoxication, and threat. It is not a complete
social, cultural, accessibility, legal, or consumer-rating analysis. A shipped
game still needs the applicable regional classification process over the whole
experience.

Each level is interpreted within the requested scene:

- `0` is an observable restrained counterstate;
- `1` is mild or indirect;
- `2` is clear but restrained;
- `3` is strong; and
- `4` is the strongest coherent treatment supported by the active provider and
  this compiler boundary.

For adult sexuality and exposure, level `4` stops at a present-tense,
non-explicit fashion or editorial treatment. It may use several coherent cues
across pose, gaze, gesture, wardrobe, crop, lighting, and atmosphere. It does
not direct sexual activity, post-intimate context, or clothing removal. All
people must remain clearly adult and willingly present. For example,
`sexual_content = 4` with `nudity_exposure = 0` remains fully covered, while the
inverse uses neutral catalog/editorial posture rather than suggestive intent.

## Why an LLM sits in the middle

Passing numbers or control names directly to an image model leaves their visual
meaning underspecified. Theme compiler v6 instead uses a structured text model
to translate the base brief and numeric targets into concrete, scene-aware art
direction. Deterministic code still owns parsing, schema validation, prompt
composition, leak checks, cache identity, and persistence:

```text
TOML or JSON brief + handles
  -> strict local normalization
  -> structured theme compiler + repository art-direction skill
  -> validated seven-field plan
  -> deterministic recipe and asset composition
  -> image provider
```

The image model receives compiled natural-language art direction plus the
recipe's asset-specific instructions. It does not receive the raw theme object,
numeric levels, handle names, or their serialized TOML/JSON. The compiler is
therefore an LLM-in-the-middle rewrite seam inside a deterministic orchestration
boundary, not literal value leakage into the image prompt.

The strict compiled plan contains seven complete, affirmative prose fields:

- `concept`: the self-contained final concept-image direction;
- `world_spec`: constraints for structured world planning;
- `environment`: backgrounds, layers, and set dressing;
- `characters`: character design, pose, state, and interaction;
- `items`: props, pickups, and obstacle sheets;
- `portals`: portals and transition effects; and
- `hard_exclusions`: an affirmative observable baseline that remains binding
  across assets.

Each field is validated for its schema, length, complete terminal sentence,
raw-control leakage, and known unsafe cue combinations before it can be used.

## Identity, soft staging, and hard locks

The compiler preserves the source subject, clearly adult identity, defining
design, visual language, and formal hard locks. With a reference image,
recognizable identity, design, and art style are anchored by default. Pose,
hands, props, camera, crop, and other staging remain soft so the compiler can
make the requested intensity visible across the whole composition.

A hard lock is recognized only from an explicit source declaration using
`MUST KEEP`, `HARD LOCK`, `KEEP EXACTLY`, or `DO NOT CHANGE`. Prefer the
repeatable form `MUST KEEP <subject> EXACTLY <placement>`. Its scope ends at
punctuation or a conjunction. Repeat the formal marker for every additional
subject or placement:

```toml
prompt = """
original bright 2D anime game art of a clearly adult character.
MUST KEEP the mint hair ribbon EXACTLY on the left side of the bob.
MUST KEEP the chestnut bob EXACTLY at chin length.
"""
```

Ordinary prose such as “centered,” “holding a cup,” or “fixed camera” is not a
lock. This prevents incidental setup language from freezing the very pose,
hands, prop, or framing that may need to change.

## Models, retries, and reproducibility

The current defaults are OpenRouter `openai/gpt-5.6` for structured compilation
and `openai/gpt-image-2` for image generation. These are configurable adapter
settings, not architectural dependencies; components and recipes consume
provider-neutral contracts.

The runtime packages the tracked
[`compile-theme-art-direction` skill](../src/stage_gen/resources/skills/compile-theme-art-direction/SKILL.md).
Every compiler request and relevant downstream cache identity records compiler
version `6`, the skill name, and the SHA-256 digest of the exact skill bytes.
Changing the handles, compiler version, or skill content changes theme identity
and invalidates stale themed cache entries while leaving the unset-theme path
unchanged.

Each AI operation has exactly one retry owner and at most six attempts: one
initial call plus five retries. Transport, decoding, schema, media, and caller
validation failures stay inside that owner. A semantic regeneration after an
independent visual failure is a new bounded candidate, not another nested
provider retry. See [Verification](../VERIFICATION.md).

## Shared-seed example and current result

The development experiment used one 1024 × 1536 reference as the sole image
input. It depicts one clearly adult, bright moe-style character with a chestnut
bob and mint ribbon. The provider surface exposed no numeric seed, so the exact
reference digest, rather than a claimed RNG seed, anchors the comparison.

The maximum variant used `sexual_content = 4` and `nudity_exposure = 4`, with
the other four handles at `0`. Compiler v6 preserved adult identity, face,
hair, ribbon, and bright anime language while moving the unlocked cup to the
table and redesigning hands, body line, gaze, crop, wardrobe, lighting, and
staging toward an adult fashion/editorial composition. This demonstrates why
whole-scene freedom matters: a clothing-only edit would leave major intensity
cues unchanged.

The compiler plan was accepted on GPT-5.6 attempt 5 and passed independent
text/provenance review. This was a compiler-only plus reference-edit proof, not
an end-to-end recipe run. The built-in image tool exposed neither its exact
image-model identifier nor a numeric generation seed. The left panel below is
a manually authored neutral shared seed representing the observable zero
endpoint; it is not an all-zero output from compiler v6. The right panel is the
compiler-v6 maximum treatment with the other four handles at `0`.

![Shared seed at low treatment beside the compiled maximum treatment](media/theme-art-direction-example.webp)

This published comparison is a deterministic crop and side-by-side lossy WebP
derivative of those two exact source images, chosen for compact Git and browser
delivery. A reviewer independent from the media producer gave the exact
derivative a digest-bound **pass**, including the adult-identity,
whole-scene-change, fidelity, and no-readable-text criteria.

The raw maximum output remains a useful limitation: it and both bounded
image-candidate regenerations passed identity, style, whole-scene change,
adult-fashion treatment, and low-unrelated-axis review, but all three introduced
readable café signage and therefore received strict **fail** verdicts. Cropping
the selected source outside that defective sign produced a separately reviewed
documentation artifact; it does not retroactively pass or publish the raw
output. Every raw PNG source and retry remains ignored and unpublished.

## Limits and publication

- Theme levels are targets, not guarantees of equal visual distance between
  adjacent values or identical behavior across models.
- Model support and safety boundaries may cap a requested treatment.
- Field-local validation catches known cue combinations, but every fresh plan
  still needs cross-field semantic review before a live image call.
- A reference-conditioned result may preserve identity while changing any
  staging that was not formally locked.
- Provider/model provenance supports auditability; it does not grant rights.

Generated output stays unapproved until the exact artifact passes independent
semantic review and the repository's rights and storage gates. Follow
[Generated-media publication](generated-media-publication.md),
[Repository storage](repository-storage.md), and [OSS and IP policy](oss-ip.md)
before committing or publishing any visual.

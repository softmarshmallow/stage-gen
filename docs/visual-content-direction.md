# Visual Content Direction

> **Status:** implemented as an optional `scrolling-preview` recipe stage. The
> shipped v1 wire contract still uses `[theme]` and related `theme` identifiers.

Visual Content Direction compiles a base visual brief and six numeric content
controls into validated, recipe-specific prose before any image request is
assembled. It gives authors a compact way to request visible content intensity
while leaving the language model in the middle to express that intent through
scene-aware pose, wardrobe, action, damage, props, lighting, and atmosphere.

At this version, Visual Content Direction is a **recipe stage backed by the
provider-neutral structured-generation component**. It is not itself a reusable
component, standalone image pipeline, character pipeline, rating system,
moderation service, or benchmark harness. The only supported consumer is the
`scrolling-preview` recipe.

## Names and compatibility

Visual Content Direction is the canonical capability name. The implementation
retains its shipped v1 vocabulary so existing inputs, artifacts, caches, and
published evidence remain valid:

| Concept | Shipped v1 identifier |
| --- | --- |
| Author content controls | `[theme]` input object; `ThemeHandles` in Python |
| Compilation stage | `theme-compile` |
| Compiled scrolling plan | `CompiledThemePlan` |
| Plan artifact | `theme_plan_<tag>.json` and its sidecar |
| Executable compiler policy | `compile-theme-art-direction` skill |
| Identity metadata | `canonical_theme_json`, `theme_digest`, and `theme_compilation` |

These identifiers are compatibility vocabulary, not a claim that the feature
controls artistic style or narrative theme. `[content_controls]`, a direct
compiler command, and renamed Python contracts are not implemented interfaces.

## What crosses each boundary

```text
caller brief + v1 [theme] controls
  -> scrolling-preview input validation
  -> theme-compile recipe stage
  -> StructuredGenerationService + tracked policy
  -> validated seven-field scrolling plan
  -> deterministic recipe prompt composition
  -> ImageGenerationService
```

The original brief and normalized control record do not enter downstream
world-planner or image-provider prompts for a controlled run. They remain in
run and compiler provenance for auditability. Downstream calls receive validated
plan prose, deterministic recipe instructions, and any recipe-selected image
references or templates required by that stage. A final leak check rejects raw
control names, numeric control assignments or ratings, and serialized control
records before an image call; it does not ban unrelated numerals in ordinary
art direction.

The compiled plan is intentionally specific to `scrolling-preview`: it directs
the concept, world planner, environment, characters, items, and portals, plus
one affirmative binding baseline. It is not a cross-recipe character or image
schema. See the normative [content-control contract](spec/content-controls-v1.md)
and [scrolling plan contract](spec/scrolling-content-direction-plan-v1.md).

## Responsibilities

| Owner | Current responsibility |
| --- | --- |
| Caller/operator | Supplies the base brief, six controls, and formal prompt locks; authorizes live operation and later review or publication decisions. Configured provider loading supplies credentials separately. |
| `scrolling-preview` recipe | Parses input, inserts the optional stage, owns the seven-field target schema, artifact path, cache dependencies, stage mapping, prompt composition, and downstream provenance. |
| `stage_gen.theme` | Normalizes controls, loads and hashes the tracked policy, builds the strict structured request, validates returned prose, and detects control leakage. It is an internal request/validation module, not a compiler service. |
| Structured-generation component | Owns the provider-neutral call, the single retry boundary, schema decoding, caller validation, atomic artifact persistence, and sidecar. |
| Image-generation component | Receives composed natural-language direction and references selected by the recipe; it never interprets numeric content controls. |
| Orchestration | Constructs the concrete services and provider adapters and manages the run lifecycle. It does not define content semantics. |
| Review and publication | Bind semantic and rights decisions to exact artifact digests. Neither review nor approval is performed by the compiler. |

The tracked `SKILL.md` is executable compiler policy. It is not the public API,
the user guide, or the architecture contract.

## Use it today

Create a TOML input document:

```toml
prompt = "original bright 2D anime game art of a clearly adult cafe patron"

[theme]
sexual_content = 4
nudity_exposure = 4
hostile_action = 0
injury_detail = 0
substance_depiction = 0
threat_disturbance = 0
```

The equivalent JSON input is:

```json
{
  "prompt": "original bright 2D anime game art of a clearly adult cafe patron",
  "theme": {
    "sexual_content": 4,
    "nudity_exposure": 4,
    "hostile_action": 0,
    "injury_detail": 0,
    "substance_depiction": 0,
    "threat_disturbance": 0
  }
}
```

Run the recipe through its supported interface:

```sh
uv run stage-gen generate --recipe scrolling-preview \
  --input ./content-direction.toml --transparency ai
```

The CLI parses files ending in `.toml` as TOML and other input files as JSON.
The loopback HTTP interface accepts the same recipe input through
`POST /v1/runs`, nested under `input`:

```json
{
  "recipe": "scrolling-preview",
  "input": {
    "prompt": "original bright 2D anime game art of a clearly adult cafe patron",
    "theme": {
      "sexual_content": 4,
      "nudity_exposure": 4,
      "hostile_action": 0,
      "injury_detail": 0,
      "substance_depiction": 0,
      "threat_disturbance": 0
    }
  },
  "transparencyMode": "ai"
}
```

Omitting `theme` preserves the exact legacy stage graph and prompt path. A
present empty object or six explicit zeroes still runs the compiler and asks
for an observable restrained baseline. The generated
`theme_plan_<tag>.json` and sidecar are audit inputs to the recipe, not runtime
image assets.

There is no supported compile-only or approval/resume command. A normal
`generate` call proceeds from deterministic plan validation into concept
generation. Human plan review before image generation is not a supported v1
checkpoint, and callers must not treat normal `generate` as an approval/resume
interface. Generated images still require independent review before acceptance
or publication. The standalone `generate-image` capability bypasses Visual
Content Direction and cannot consume its controls.

## Reuse it correctly

Supported reuse today means invoking `scrolling-preview` through the normal CLI
or HTTP recipe interface. Direct imports from `stage_gen.theme`, including
`build_theme_plan_request`, are internal and unstable; they omit the
recipe-owned cache, stage-routing, prompt-boundary, and provenance behavior
needed for a complete integration.

A future recipe should adopt the pattern only when it can:

1. declare its own fixed, versioned output plan and supported control envelope;
2. use the existing structured-generation component rather than call a provider
   from recipe policy code;
3. map every plan field deterministically to its own assets;
4. bind compiler model, request, policy digest, plan digest, and downstream
   cache/provenance identity;
5. reject unsupported or conflicting values instead of silently clamping or
   ignoring them;
6. prove that raw controls never cross its image boundary; and
7. preserve its historical path exactly when controls are absent.

A character-reference recipe would be a separate future consumer. It should
own reference validation, identity bindings, pose/crop composition, candidate
selection, and a smaller character-specific plan. It must not reuse the
scrolling plan's unused world, item, or portal fields. The current
`scrolling-preview` input does not accept a caller reference image; the
published shared-reference experiment is evidence, not a shipped reference
pipeline.

Do not promote Visual Content Direction into `components/` until a second real
recipe proves a provider-neutral request/result contract. At that point, only
the common controls, policy loading, request construction, and deterministic
validation should move. Recipe schemas, stage mappings, image composition,
references, review, and publication remain with their current owners.

## Evidence, limits, and review

The [shared-seed A/B case study](visual-content-direction-case-study.md)
demonstrates the LLM-in-the-middle behavior and its limitations. It is a
compiler-plus-reference-edit experiment, not an end-to-end scrolling recipe
run and not evidence that adjacent numeric levels are visually calibrated.

Content-direction levels are conditional targets. Provider/model policy may
cap a requested treatment, and deterministic validators cannot prove that an
image expresses the intended level. Fresh generated media remains unapproved
until its exact bytes pass independent semantic review and the repository's
rights and storage gates. Follow [Generated-media publication](generated-media-publication.md),
[Repository storage](repository-storage.md), and [OSS and IP policy](oss-ip.md).

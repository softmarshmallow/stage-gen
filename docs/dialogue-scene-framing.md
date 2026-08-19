# Dialogue-scene framing control

> **Status: implemented in the deterministic demo; research only for provider
> generation.** The demo parses `presentation.framingZoom` and applies a
> deterministic viewport crop. No Python recipe, provider invocation,
> transparency stage, or manifest-backed generation path consumes this control
> today.

## Question

Can one numeric control reliably request full-shot through close-up standing
sprite framing from an image model, and should prompt output or presentation
own the exact final crop?

The experiment found no prompt-only exact-crop winner. Prompting is suitable
only for coarse source framing. The presentation viewport is the final framing
authority.

## Matched methodology

All candidates used the same appearance reference, portrait canvas, neutral
backdrop, pose, expression, identity constraints, and style constraints. The
only intentional variable was the framing instruction at three anchors: `25`,
`60`, and `85`. Higher values mean tighter framing.

Round one compared:

- `term-only-v1`: a conventional camera term plus identity/style invariants;
  and
- `hybrid-bounds-v1`: the same term plus the numeric value, explicit crop
  landmark and visible anatomy, face-height/headroom bands, and positive and
  negative boundary constraints.

Round two compared the existing `hybrid-bounds-v1` outputs with
`hybrid-crop-first-v2` at only `60` and `85`. Crop-first moved the mandatory
canvas crop to the first sentence, treated off-frame anatomy as intentional,
removed contradictory full-body pose language, and made percentages secondary
audit targets.

Independent reviewers received the specification and blinded, hash-bound
candidates, but not generation prompts. An exact-framing pass required the
identity, crop landmark, required/forbidden anatomy, face-height band,
headroom band, and shared invariants all to pass.

## Strict results

| Prompt method | Exact-framing passes | Preference evidence | Result |
|---|---:|---|---|
| `term-only-v1` | 1/3 | Passed only at `25`. | Not acceptable across anchors. |
| `hybrid-bounds-v1` | 0/3 | Preferred over term-only at `60` and `85` in round one, while still failing. | Not an exact-crop method. |
| `hybrid-crop-first-v2` | 0/2 | Preferred over hybrid-bounds at both `60` and `85` in round two, while still failing. | Closest coarse source-generation strategy only. |

No prompt-only method passed both `60` and `85`, so there is no exact-framing
prompt winner. `hybrid-crop-first-v2` is retained as coarse generation
guidance because it was preferred at both bounded round-two anchors, not
because it met the exact crop contract.

## Numeric contract and deterministic mapping

The demo fixture shape is:

```json
{
  "presentation": {
    "framingZoom": 70,
    "sourceFramingZoom": 70
  }
}
```

The public value is a finite number from `0` through `100`; higher means
tighter. The mapper clamps public input to that range, then clamps effective
geometry to the evidence-backed range `25` through `85`. Values below `25` or
above `85` therefore saturate to the nearest tested geometry. The public
clamped value is still reported in the coarse prompt. The current demo controls
expose only the effective `25..85` range. The default is `70`.

`sourceFramingZoom` records how tightly the committed sprite pixels were
authored. The anime expression variants are upper-body sources authored at
`70`, so the demo divides target scale by the mapper's scale at `70`. Target
`70` therefore renders at CSS scale `1`; targets `25` and `85` render at
`0.308` and `1.37`. This preserves deterministic relative zoom while avoiding
the old full-body-source scale of `3.244` at the default.

A target below the source baseline can make that upper-body sprite smaller in
the composition, but it cannot reveal legs, shoes, or any other pixels that
were never authored. The UI marks those values `source-limited`. A future
provider path seeking a real full shot must generate overscan or a full-body
variant; presentation transforms cannot reconstruct missing anatomy.

| Anchor | Semantic tier | Camera term | Intended final crop | Face-height band | Headroom band | Presentation x |
|---:|---|---|---|---:|---:|---:|
| `25` | `full-body` | `full shot` | Entire figure and boots, with `2%..6%` floor margin | `7%..11%` | `4%..8%` | `72%` |
| `60` | `waist-up` | `medium shot` | Bottom edge at the natural waist; hips and legs off-frame | `18%..26%` | `4%..8%` | `62%` |
| `85` | `head-and-shoulders` | `close-up` | Bottom edge below clavicles with complete shoulders | `34%..46%` | `3%..7%` | `52%` |

The nearest semantic tier changes at `42.5` and `72.5`, choosing the tighter
tier on an exact tie. Face-height, headroom, and horizontal position interpolate
linearly between anchors. Presentation scale is the interpolated face-height
band midpoint divided by the full-shot midpoint (`9`); vertical position is the
interpolated headroom midpoint. Values are applied with a `top center`
transform origin inside an overflow-clipped stage.

At the default `70`, the current mapper returns `medium shot`, face-height
`24.4%..34%`, headroom `3.6%..7.6%`, scale `3.244`, position `58% 5.6%`, and
`top center` transform origin.

## Exact coarse-generation string template

This is the exact `hybrid-crop-first-v2` renderer template. It is implemented
and hash-tested as a pure string mapper, but no provider consumes it today.

```ts
`FINAL CANVAS CROP IS MANDATORY: ${tier.cropDirective}. Anatomy outside this crop is intentionally off-frame; do not reconstruct it, reveal it, or shrink the character to fit it into the canvas. Create one ${tier.cameraTerm} of the exact character in the supplied reference image with framingZoom=${formatZoom(zoom)}/100, where higher means tighter. The crop landmark overrides every percentage target and all other framing guidance. Required visible anatomy: ${tier.visibleAnatomy}. Apply identity invariants only to features that are in frame: ${promptContext.identity.join("; ")}. Preserve style: ${promptContext.style.join("; ")}. In-frame pose only: ${tier.inFramePose}. Expression: ${promptContext.expression}. Secondary audit targets only, never reasons to loosen the crop: face height ${formatBand(faceHeightPercent)}; headroom ${formatBand(headroomPercent)}. Canvas: ${CANVAS}. Backdrop: ${BACKGROUND}. Output: ${OUTPUT}. Exclusions: ${EXCLUSIONS}.`
```

Variable resolution is deterministic:

- `tier` is the nearest semantic anchor for effective zoom;
- `zoom` is the public-clamped value;
- `faceHeightPercent` and `headroomPercent` are interpolated at effective zoom;
- `promptContext.identity`, `promptContext.style`, and
  `promptContext.expression` are strict, non-empty, trimmed strings supplied by
  the fixture or by the mapper's retained default test vector;
- optional `promptContext.tierOverrides` may specialize attire-specific crop
  landmarks and visible-anatomy wording without changing numeric presentation
  geometry;
- `CANVAS` is `portrait-oriented 2:3 canvas`;
- `BACKGROUND` is a flat, uniform neutral middle-gray backdrop without scene
  details, shadow, or floor line;
- `OUTPUT` is one opaque RGB image with no transparency or post-processing;
  and
- `EXCLUSIONS` forbids text, captions, logos, signatures, and watermarks.

The tested prompt-text SHA-256 values below use the retained original default
context, so adding fixture-specific context did not invalidate the matched crop
experiment:
`aaabbe85d5d6e1a8828b9384e334318784a308810eda36274cb6bcbea328daa5`
at `60` and
`86dc758f8a94cf8ef2f8f71f80a927a5042683f2000213ad74a661a3be3a22f0`
at `85`.

The anime showcase passes Mio's age-23 identity and art direction plus the
active beat's expression-variant description into `promptContext`, and replaces
the default courier-coat landmarks with her cardigan and shoes where relevant.
That only specializes coarse prompt text; the numeric tier, bands, position,
and scale remain identical for the same `framingZoom`.

## Final-crop authority and source acceptance

The generated source, if this research is later connected to a provider, is
overscan rather than the final crop. Accept it for presentation cropping when:

- identity and style invariants pass;
- all anatomy required in the final frame is fully present and unobstructed;
  and
- the target landmark and enough source resolution exist for the deterministic
  viewport crop.

Extra lower anatomy beyond the intended crop is allowed. Reject missing,
clipped, or obstructed required anatomy; identity/style failure; a missing crop
landmark; or insufficient crop resolution. Exact source-image crop and
face-height percentages alone do not reject an otherwise crop-safe source.

The demo keeps the selected expression-variant source unchanged and
deterministically applies the mapper's scale and position inside the clipped
presentation stage. Changing expression state never changes placement math.
This viewport behavior is the only implemented framing authority today. A
future headless recipe must persist resolved placement/crop data in its
manifest rather than treating this browser behavior as provider or artifact
evidence.

## Evidence

| Evidence | SHA-256 |
|---|---|
| [Experiment specification](../output/imagegen/dialogue-scene-framing/experiment-spec.json) | `cdaa96e244b3aeda5fb819f7e75b1247bf427960ef271226aa13112ec0ff1d3b` |
| [Round-one blind map](../output/imagegen/dialogue-scene-framing/blind-map.json) | `ed5e3cf4ef5d1bc5c5a97a1554d0c2778fcd7d2f83f0788471224d0d68bfcd10` |
| [Round-one blind verdict](../output/imagegen/dialogue-scene-framing/blind-verdict.json) | `b04fbbb137a308067ef2135c989298b441f92bd2cce36b0b68901d00c3b0d66e` |
| [Round-two blind map](../output/imagegen/dialogue-scene-framing/round-2-blind-map.json) | `80368f34cb79c44ec11dc01c24a4e89a1df022e29094130b53323d1977a93ea7` |
| [Round-two blind verdict](../output/imagegen/dialogue-scene-framing/round-2-blind-verdict.json) | `c968a44cf31683c7cd87bd412c148d4efabb602c007e73d196f9df10aec05272` |
| [Decoded experiment results](../output/imagegen/dialogue-scene-framing/experiment-results.json) | `3dbd2eb0ae8f3647201c922395343546025a621b7c70824a28cfd7a7caef0934` |
| [Pure mapper](../web/lib/dialogue-scene/framing.ts) | `298b91e176f7a206b83143dc3e4c7077928b4bdf9e1c2c3115f88a073f0e13c7` |
| [Focused mapper tests](../web/lib/dialogue-scene/framing.test.ts) | `a6905c7eee3cb459eb66af28fee15acf77913d2a3df6a112026ddf4b78a915b1` |
| [Current browser QA](../web/output/playwright/dialogue-scene-anime/qa-summary.json) | `bd6cfa0be5087d177aa585ea1a66000cbe79c5226897e2aabd02ffc5db599dc0` |

The browser record verifies that range and number controls synchronize at
`25`, `60`, `70`, and `85`, but it does not claim a new visual verdict for all
four framing geometries. The earlier full-body-source screenshots were retired
when the demo moved to an upper-body anime source; their visual claims do not
apply to the current source-limited presentation.

## Deferred work

- Connecting the prompt mapper to any runtime or provider generation pipeline.
- Provider-side crop validation, retry, provenance, and manifest integration.
- Transparency production, background removal, chroma keying, and alpha
  acceptance.
- New evidence for values outside effective `25..85`, including looser
  establishing compositions and tighter extreme close-ups.

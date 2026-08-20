# Theme art-direction controls (legacy path)

The capability formerly described as “theme art-direction controls” is now
documented as [Visual Content Direction](visual-content-direction.md).

This path remains as a compatibility pointer because the shipped v1 runtime
still uses `[theme]`, `ThemeHandles`, `CompiledThemePlan`, `theme-compile`,
`theme_plan_<tag>.json`, and `compile-theme-art-direction`. Those implementation
names have not been replaced by new input fields or public Python APIs.

Use the canonical guide for current usage and responsibility boundaries. The
normative v1 contracts are:

- [Content controls v1](spec/content-controls-v1.md)
- [Scrolling content direction plan v1](spec/scrolling-content-direction-plan-v1.md)

The published experiment and its limitations are preserved in the
[shared-seed A/B case study](visual-content-direction-case-study.md).

The headings below preserve the most likely anchors from the former guide.

## Authoring a themed run

See [Use it today](visual-content-direction.md#use-it-today).

## Axes and levels

See [Content controls v1](spec/content-controls-v1.md).

## Why an LLM sits in the middle

See [What crosses each boundary](visual-content-direction.md#what-crosses-each-boundary).

## Identity, soft staging, and hard locks

See [Base brief, style, and hard locks](spec/content-controls-v1.md#base-brief-style-and-hard-locks).

## Models, retries, and reproducibility

See [Identity, cache, and provenance](spec/scrolling-content-direction-plan-v1.md#identity-cache-and-provenance).

## Shared-seed example and current result

See the [shared-seed A/B case study](visual-content-direction-case-study.md).

## Limits and publication

See [Evidence, limits, and review](visual-content-direction.md#evidence-limits-and-review).

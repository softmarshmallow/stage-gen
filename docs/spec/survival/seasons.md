# Survival seasons

> **Checked by:** `tests/contract/test_generation_pipeline_docs.py`.

> **Contract maturity: exact-current authored contracts.** Executable
> authority: `src/stage_gen/recipes/oblique_survival/survival_request.py` and
> `src/stage_gen/recipes/oblique_survival/prepared_survival.py`; the authored
> file is `seasons.toml` in an
> [oblique-survival package](generation-v1.md).

## What a season is

A **weather condition** is a spell the clock rolls; a **season** is a condition
the calendar holds for days. Both drive presentation across the screen, the
ground and the light at once, and neither is a screen-effect moment — the
screen-effect family is plates slammed over the frame at a moment, and a season
is not a moment.

A season owns what a weather condition cannot: the factor a weather condition is
held at, the cold that drains warmth, the look every prop shows, the share of
the day that is night, how fast anything regrows, and what the ground offers.

## What is authored, and where

| File | Table | What it says |
| --- | --- | --- |
| `seasons.toml` | `[calendar]` | the seasons in order and how many days each lasts; the world begins on day 1 in the first and goes round |
| `seasons.toml` | `[[seasons]]` | per season: `snow` (the factor the snow condition is held at), `cold` (scales the warmth drain), `night_share`, `regrow_scale`, `hidden_forage`, `barren` (props whose gather is refused), and an optional `[seasons.look]` naming the look after the season |
| `props.toml` | `[props.season_prompt.<look>]` | per state, a brief that replaces the look's shared clause for that one paintover; read by the look prompt alone, never by the summer prompt |
| `survival.toml` | `[gameplay.warmth]`, `[gameplay.torch]`, `[gameplay.campfire]` | the cold's drain, the night's addition, the dark's own drain (`dark_drain_per_second`, optional, 0–10), the freeze damage, the torch's scale, the fire's heat radius and rate |
| `items.toml` | `use = { kind = "wear" }`, `{ kind = "warm" }`, `consume.warmth` | insulation while carried, heat seconds once lit, warmth a food gives |
| `weather.toml` | the ice condition and the wind sound | the frozen water — a look on the water route, adoptable by `take` — and the ambience |
| `sounds.toml` | a snow footstep cue | the walk under snow, cut at its onsets like the ordinary footstep |

**The loader refuses, offline, before a run directory exists:** an order naming
an undeclared season; a barren prop with nothing to refuse; a hidden item nobody
declared; a season prompt naming a look no season shows, or a state the prop
lacks; a cold season with no fire that warms; a snowy season with no snow
condition to hold; and ice declared on rain.

## Warmth: the third vital

The cold drains warmth at the authored rate times the season's `cold`, and more
by night. The dark is a cold of its own, in every season: at night, out of every
light — no torch lit, no lit fire within its light radius — warmth goes at
`dark_drain_per_second` times the night, so a summer night away from the fire
costs most of the bar and the fire is the night's answer. A worn item takes its
insulation off the drain; a lit torch scales it; a lit warm item holds it off for
its heat seconds; a lit campfire within its heat radius gives warmth back. At
zero, whatever is still draining the bar — the winter's cold or the dark's — takes
health at the freeze rate, and the death names its cause; an empty bar under a
summer sun costs nothing and comes back only at a fire. At
a full bar inside a fire's heat there is nothing to gain, and the world says so
(`hot`) for the screen. A package with no calendar never shows the bar.

## The look: a paintover per prop state

Every prop state has a per-season twin at
`package/props/<id>/<state>.<look>.png`, drawn as a paintover of the summer
sprite: the summer sprite rides as reference image 1, the style plate as image 2,
and the clause says what the season adds and that nothing else moves. One image
operation per state. The look node hangs off the summer state's **gated** sprite,
so the summer's digest is in the look's key: redraw a summer state and its twin
redraws; edit the shared clause and only the states that read it move; a state
with its own `season_prompt` override holds.

**A look is measured as fractions of its canvas, not in pixels.** A summer sprite
cut to 512 px and a paintover drawn at 1024 are the same drawing at two pixel
scales, and the first winter run refused sixteen honest looks on that arithmetic
alone. Scale and placement are therefore **corrected, not refused**: the look is
resized to the summer's painted width and its foot set on the summer's, on a
canvas the summer's size, so the state's ruler and its anchor hold by
construction. What cannot be corrected is the shape: `LOOK_ASPECT_RATIO =
(0.72, 1.2)` refuses a look whose width-to-height moved past that band, because
that is a different drawing. The band leans below one because a cap adds height
and not width.

A sheet takes the same road at sheet scale: one paintover of the whole summer
sheet, guide lines and all, reading the same clause, gated on the same lattice
and carrying the look's own cell windows — a cap grows a plant's box, so the
consumer swaps atlas and windows together.

The `seasons` review family judges every pair on one contact sheet, the summer
first, and asks whether it is the same drawing with the season added.

## What else a season moves

- **The ground** is the condition's cover plate, laid over every biome by the
  factor the season holds ([ground](ground.md)).
- **The water freezes** as a look, not as a floor: the ice plate is mixed over
  the water by the same factor with the waves stilled, and the land mask stays
  the collision truth.
- **The ground goes lean.** Hidden forage goes to zero scale and returns through
  the regrow timer; `regrow_scale` at zero stops regrowth; a barren prop refuses
  its gather. The player stockpiles or starves.
- **The ear.** The wind's gain follows the factor, and the walk crunches when the
  package declares the cue.
- **The table answers.** Warm clothing and a warm stone are recipes, and a
  cooked food may carry warmth ([crafting](crafting.md)).

## Non-goals

- More than the authored seasons: each additional one is a `[[seasons]]` entry
  plus one look per prop state, and the calendar takes it as written.
- Walkable ice, and a far shore worth crossing.
- Hunting for hides and meat, which needs a combat pass first.
- A per-season music cue.
- Snow drifts as decals or piled props.

## Dated log

- **2026-09-06.** The calendar, the warmth vital, the season looks and their
  drift gate, the ice look, the `seasons` review family and the manifest's
  season blocks landed in one pass. The first run refused sixteen looks six
  times each on a gate that compared pixel widths across two canvas sizes; the
  normalisation rule above is what replaced it.

# Example: concept gallery (a user recreates "universe")

**The ask:** "From my synopsis, a poster and a short direction, propose the people, places and
objects of this world. Have a different model check the proposal against the synopsis. Then draw
one concept image per entity, reviewed by another model. I'll reroll the ones I don't like."

**Status:** the project plans and prices today. Its admission and image reviews use
`structured.review` and `vision.review`, which are planned, so those steps run once their bodies
land. Stage Gen's own universe workflow does the same with `structured.generate` answers that
judges read.

```
concept-gallery/
  gnode.yaml
  workflows/concept-gallery.yaml      # the whole workflow: no Python needed for the flow
  nodes/world_checks.py               # one deterministic judge (~40 lines)
  prompts/propose.md, admit.md, grammar.md, direct-entity.md, review-concept.md
  schemas/world.json, grammar.json, entity-direction.json
  views/gallery.html                  # optional whole-run page: a grid with verdict badges
  inputs/tidebell/{synopsis.md, direction.md, poster.png}
```

## Run it

```bash
gnode plan concept-gallery --synopsis inputs/tidebell/synopsis.md \
  --direction inputs/tidebell/direction.md --poster inputs/tidebell/poster.png
#   phase 1: 5 steps, 3–9 calls (with regeneration), $0.30–$1.10
#   phase 2: up to 48 entities × 3 calls, ≤ $14.40, priced exactly after phase 1

gnode run concept-gallery --inputs inputs/tidebell.yaml --live --max-usd 12
gnode view
gnode reroll runs/concept-gallery/2026-10-02-1 "entity['bellwright'].draw"
```

## The node the user wrote

```python
# nodes/world_checks.py
from gnode import node, Ctx


@node("well_formed", inputs={"world": "json"}, params={"max_entities": int}, outputs={}, judge=True)
def well_formed(ctx: Ctx) -> dict:
    world = ctx.read.json("world")
    ids = [e["id"] for e in world["entities"]]
    problems = []
    if len(ids) != len(set(ids)):
        problems.append("duplicate entity ids")
    if not 4 <= len(ids) <= ctx.params["max_entities"]:
        problems.append(f"{len(ids)} entities, outside 4..{ctx.params['max_entities']}")
    for rel in world["relationships"]:
        if rel["from"] not in ids or rel["to"] not in ids:
            problems.append(f"relationship {rel['from']}→{rel['to']} names an unknown entity")
    ctx.fact("problems", problems)
    ctx.fact("verdict", "reject" if problems else "accept")
    return {}
```

## What the user did not have to write, compared with our universe workflow today

- **A "source lock" node.** Inputs are keyed by content automatically.
- **A proxy node before each review.** `vision.review` reviews a reduced copy by itself.
- **An executor with two phases and a hand-off file.** The repeat over `propose`'s entities is the
  phase boundary.
- **A reroll ledger.** That is `gnode reroll`, plus the takes file.
- **Record and close handlers, a manifest reducer, attempt ledgers.** That is `gnode/package@1`
  with a manifest laid out in YAML, and the run record.
- **A bespoke viewer page.** That is the default overview, or the 60-line `views/gallery.html`.

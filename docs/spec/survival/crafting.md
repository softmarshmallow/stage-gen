# Survival crafting and items

> **Checked by:** `tests/contract/test_generation_pipeline_docs.py`.

> **Contract maturity: exact-current authored contracts.** Executable
> authority: `src/stage_gen/recipes/oblique_survival/survival_request.py`; the
> authored files are `items.toml` and `crafting.toml` in an
> [oblique-survival package](generation-v1.md).

The mechanism the genre is named for: an author-defined crafting table, two
pictures for every item, a slot inventory, tools that wear, stations, and a
closure proved before any of it is paid for.

## What is authored, and where

| File | Table | What it says |
| --- | --- | --- |
| `items.toml` | `[[items]]` | every item: its pickup brief (the one field a node digests), `display_name`, `height_units`, `stack_max`, an optional `use` (a consumable that moves hunger, health or warmth; a light that burns; a carried pack that adds slots; worn insulation; a warm item that holds the cold off once lit), an optional `tool` (the verb it serves and how many uses it lasts), an optional icon brief |
| `items.toml` | `[icons]` | the inventory icon sheet: its lattice, its style emphasis, glyphs for any cell the items leave over, and an optional `take` |
| `crafting.toml` | `[inventory]`, `[start]`, `[stations]`, `[[recipes]]` | the pack's base slots, the starting inventory, the stations (a prop, a state, a reach) and the recipes: ingredients in, exactly one product out, an item with a count or a prop to build, at a station or by hand |
| `ground.toml` | `[forage]` | the forage sheet: a lattice of pickups lying on the ground, each cell naming the item it yields, how many, and how long the spot takes to regrow |
| `props.toml` | `[props.interaction].tool` | the tool a verb wants: the item, the hits with it, and whether it is required |

## Mixing versus spend

`crafting.toml` in its entirety, an item's `use`, `tool` and `stack_max`, and an
interaction's `tool` reach the manifest and **no cache key**. A recipe edit
re-bills nothing, the way a music fade does not. What bills is a picture: a new
item's pickup sprite, the forage sheet, the icon sheet, a new prop.

`display_name` is the exception, and it is not one: names are painted into the
icon sheet, so changing one moves the icons.

## The reachability closure

The loader refuses, offline and before any spend: an unknown key on an item or a
recipe; a recipe with two products, or a station nobody declared; a station whose
prop nobody can build; a tool whose item serves another verb; an icon lattice
the items and glyphs do not fill exactly; and **any item nothing reaches**.

Reachable means: in the start inventory, yielded by a prop, lying on the forage
sheet, or the product of a recipe whose ingredients are all reachable and whose
station either stands in the camp or is itself a reachable product.

This is the same discipline the room recipe applies to a puzzle: an unreachable
item is art nobody can obtain, and the cheapest place to find that out is before
the first image is drawn.

## Two pictures for one item

An item has a world representation and an inventory representation, and they are
different drawings on purpose.

- **In the world**, a per-item pickup sprite at `package/items/<id>.png`, drawn a
  size up from the real thing with a bold closed contour, a step brighter than
  the scenery — seen bouncing out of a gathered prop and lying where it was
  dropped. A forageable item is also a cell of the **forage sheet**, scattered
  flat by the layout with the litter's contacts and light, hidden while its spot
  regrows. A twig that can be taken has to read apart from a twig that is
  decoration, so the forage is drawn a step brighter and heavier than the litter.
- **In the pack**, one **icon sheet**: every item in order, then the glyphs,
  painted together on one lattice so the set shares one scale and one contour
  weight. The pickup sprites are drawn one at a time and never quite agree with
  each other; that is the reason the sheet exists rather than a crop of the
  sprites. The manifest publishes each item's window on the sheet under
  `items.<id>.icon`.

## The pack

- The slot list is the truth: one entry per slot holding an item, a count and a
  tool's remaining uses, or empty. The base count is authored, plus every
  carried pack's own slots. Stacks fill to `stack_max`; a tool never stacks and
  carries its own wear.
- **Tools are carried, not equipped.** The first tool in slot order that serves
  the verb is the one used; the target shows the tool's hits; a required tool
  that is missing leaves the target offered with the prompt saying what is
  missing. One completed interaction wears the tool by one; at zero it breaks.
- Every helper answers with what it could **not** do, so a full pack leaves the
  piece on the ground and says so rather than dropping it silently.
- **Stations are proximity**, resolved against the nearest prop with the
  station's id and state within its authored reach — so a fire cooks only while
  it is lit.
- A built prop is placed clear of the player and of every footprint; a made item
  that does not fit falls at the feet.

## Non-goals

- **An authored craft time nobody reads.** Recipes are instant. An authored
  field with no consumer is what this repository refuses, so there is no
  `craft_seconds`.
- Storage beyond the pack; the pack's rules would carry over to a chest
  unchanged.
- A held item that follows the selection — the drawn tool in an actor's hand is
  part of the actor's art, not a socket.
- Combat and hunting, and therefore hides and meat.

## Dated log

- **2026-09-06.** The table, the two pictures per item, the slot pack, tools
  that wear, stations, the torch and the reachability closure landed in one
  pass, with the forage and icon nodes sharing the recipe's lattice template.
  The prior pickup keys and the litter's adopt key held: the plan listed exactly
  the new nodes before the spend.

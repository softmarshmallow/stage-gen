# 0001 — Scenario is a component, not a recipe

*Ruled with M1 increment 1.*

## Fact

The authored narrative contract, the Ren'Py-shaped script surface, the compiler and the
reachability proof landed under `src/stage_gen/components/scenario/`, with the authored
script in `library/games/larkfield/scenarios/` and a `stage-gen scenario check` command.

## Challenge

Narrative is the visual novel's whole subject, so the obvious home for it is the visual-novel
recipe. Every other genre-specific authored shape lives under the recipe that reads it.

## Ruling

Scenario is a component. Two genres are meant to consume one authored shape, so
recipe-neutrality is structural rather than a courtesy: a recipe that owned the contract would
make the second consumer a dependent of the first.

## Evidence

Both consumers walk one runtime, `web/lib/scenario/`: the visual novel is registered in
`web/lib/shell/scene-modules.ts`, and bellweather's conversations are authored scenarios
proven finishable offline by the same admission proof.

## Falsifier

A second genre that needs a materially different authored shape — not a superset, a different
statement vocabulary — and cannot be served by the component without a mode flag. That would
mean the shared shape was the visual novel's after all.

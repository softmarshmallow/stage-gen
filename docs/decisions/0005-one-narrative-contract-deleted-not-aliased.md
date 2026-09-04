# 0005 — One authored narrative contract: the parallel shapes were deleted, not aliased

*Ruled with the narrative collapse.*

## Fact

`game-sequence-v1` and `game-sequence-catalog-v2` held a second authored narrative shape
beside the scenario, and the platformer walked an untyped inline graph reached through
`as unknown as` rather than the scenario runtime.

## Challenge

A compatibility reader over the old catalog costs one adapter and keeps every existing run
playable; deleting a contract drops runs.

## Ruling

Delete rather than alias. Both catalogs are gone, bellweather's four conversations are
authored scenarios proven finishable offline, and the platformer walks
`web/lib/scenario/runtime.ts`. The dialogue-box module and the conversation module went with
them. One authored narrative contract, one runtime, two genres.

## Evidence

Dialogue text is now authored in exactly one place; the retired catalog and the dialogue
recipe's own copy of caller-authored beats could each hold a version of the same line and
drift while their images continued to validate.

## Falsifier

A consumer that must read an authored narrative shape the scenario cannot express, and that
cannot be served by widening the scenario's statement vocabulary.

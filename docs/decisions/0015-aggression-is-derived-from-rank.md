# 0015 — Aggression is derived from rank, with an optional authored override

*Ruled 2026-09-02 with the passive-archetype thread.*

## Fact

No archetype wandered without either fleeing or attacking, so the reference's mostly-passive
low-level mobs were unsayable. `passive` was added to the archetype table in
`web/lib/sideview-platformer/combat.ts` with zero aggro radius, zero damage and no flee.

## Challenge

If a package wants passive creatures it should say so; deriving behaviour from rank hides a
design decision inside a consumer table.

## Ruling

Aggression is derived from `rank` by default — common to passive, uncommon to territorial,
elite to hunting, boss to relentless — and an optional authored `aggression` field overrides
it, read as `spec.aggression ?? rankDefault`. The default is what makes a package that names
nothing still play correctly; the override is what makes the published-archetype claim true
for the first time.

## Evidence

Bellweather names no aggression, so its play is the rank map; contact damage already worked
independently, so passive creatures still hurt on touch.

## Falsifier

A package where the rank map is wrong often enough that every mob carries an override — which
would mean rank is not a proxy for aggression.

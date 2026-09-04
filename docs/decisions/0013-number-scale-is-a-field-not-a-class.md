# 0013 — Number scale is a field, because scale is orthogonal to reach

*Ruled 2026-09-02 with the reach thread.*

## Fact

The reference kills common mobs in one hit and prints six-digit numbers; the shipped game gave
common mobs 2 HP against 1 damage. Making numbers read large without faking the resolution
needed a named damage-scale profile.

## Challenge

Reach had just been published as a weapon *class*. The cheapest consistency is to fold scale
into the same class, so one authored word selects a whole combat feel.

## Ruling

Scale is a separate field, `number_scale` on the combat policy in
`src/stage_gen/components/platformer_gameplay/models.py`, defaulting to `unit_v1`, with the
consumer table in `web/lib/sideview-platformer/number-scale.ts`. Scale is orthogonal to reach:
folding it into the class would multiply the vocabulary by every combination and make a
package unable to keep its reach while changing its numbers.

## Evidence

`arcade_v1` multiplies player damage and mob health by one factor with per-hit variance from
the blow seed, so balance is unchanged because both sides scale together — which is only
expressible as a dimension of its own.

## Falsifier

A scale profile that is only meaningful for one weapon class, which would mean the two axes
are not independent after all.

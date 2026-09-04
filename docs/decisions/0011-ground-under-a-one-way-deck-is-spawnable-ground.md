# 0011 — Ground under a one-way deck is spawnable ground

*Ruled 2026-09-03 while reshaping the hunting map.*

## Fact

The scene reserved every ground column that a deck floated over. When the road became three
interlocking storeys, all three of its spawn zones came back with no spawnable columns and the
population projection rejected the map.

## Challenge

The reservation was written deliberately: a body standing under a set piece reads as a body
inside the scenery, and refusing those columns is the conservative choice.

## Ruling

Ground under a deck is still ground. A hunting map *is* mobs on the floor beneath stacked
ledges, and decks are one-way, so a body below one never collides with it. The reservation now
covers only the map's two ends and the portal doorways.

## Evidence

The old rule dated from a demo selector where decks were a rare set piece; under storeys it
excluded the whole floor. The storey case is pinned as a regression test beside
`reservedSpawnColumns` in `web/lib/sideview-platformer/prepared-population.ts`.

## Falsifier

A deck kind that is not one-way — solid from below — under which a spawned body would be
trapped rather than merely overshadowed.

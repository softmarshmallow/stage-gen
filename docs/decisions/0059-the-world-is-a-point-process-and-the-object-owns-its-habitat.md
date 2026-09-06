# 0059 — The world is a point process, and the object owns its habitat

## Fact

The survival world was laid by one random stream: uniform darts inside a
biome, thinned by a per-family weight table in `survival.toml [world]`, kept
apart by a hard core, with the camp hard-coded in the layout and the canopy
shade keyed on the family name `tree`. At 256 m it held 2,471 entities and
12,000 ground pieces, evenly spread, so every forest was the same forest.
Raising one density moved every other object, because everything after it
read later numbers from the same stream. The picture gate that proved the
Godot port compared the host's frames against frozen web-viewer frames of that
one world, at absolute coordinates (`tools/capture.gd`, the `junction` and
`coast` shots).

The user asked for a world that is a place: objects that belong to their
biomes, spawn rates and uniqueness, a larger map, sparse-but-clumped
placement, all parameterised so the author's attributes drive a generator
that does not know what game it is making.

## Challenge

The first reading is to grow the scatter: add a clump radius, a rarity, a
per-biome roster table the way Don't Starve's rooms list their prefabs, and
keep the stream. Every one of those is a few lines on the old code.

It fails three ways. A roster owned by the biome means every new object edits
every biome, and the generator has to merge rosters, so it learns the words.
A clump on a single stream still reshuffles the world on every tuning edit,
so tuning by eye is impossible. And the obvious gate for clumping, Clark and
Evans' aggregation index, measures the support rather than the pattern on a
habitat shattered into islets: a plain Poisson scatter on the bog reads as
regular at R = 1.3 to 1.6, and Donnelly's edge correction under-corrects
there and over-corrects on the tree mix. A gate built on it would refuse
correct groves and pass everything on the shore.

## Ruling

The world is a marked point process over solved fields, laid by a component
with no vocabulary (`src/stage_gen/components/worldgen/`): regions are
integers, objects are ids, and everything else is a number. **The object owns
its habitat.** A prop, the mob and each ground sheet carry a `placement`
block (`docs/spec/survival/world.md`); a biome never lists a roster. The
world's extent, coast, biome rules, set pieces and spawn are `world.toml`, and
the free `[world]` table, `density_share`, `biome_weights`, `mob_count` and a
sheet's density map are refused by name. The package kind is
`oblique-survival-package-v2`; there is no compatibility path.

Every draw is addressed by (seed, object, cell, index). Acceptance is
order-free within an object, the object's own spacing is one hard core, and
the cross-object footprint core only ever deletes, so an edit to one object's
block moves that object's points and, within one footprint of them, nothing
else. That locality is a tested invariant, not a tendency.

Clumping is gated against a Monte-Carlo null: the same object, the same
fields, its process replaced by Poisson, nine hashed replicates. A cluster
block that came out random is a refusal. The analytic index is not used.

The world is 512 m at the first world's card count, with two set pieces from
existing art. The viewer picture gate is retired with this record: the host's
capture sheet is its own regression reference, its shots derived from the
record rather than typed in, and the web viewer, which cannot open the
promoted manifest, keeps nothing to compare against.

## Evidence

- The component's 50 unit tests, including the locality invariants (L1 the
  candidate lists, L2 the tier-1 sets, L3 the reach bound with zero cascade)
  and the estimator on synthetic Poisson, Matérn and jittered-grid patterns.
- On the library package at 512 m: 2,365 entities, every quota met, no
  refusal, every cluster object measured `clustered` (r_mc 0.27 to 0.40), the
  spaced grass `spaced` (1.28), the Poisson objects `random` (0.88 to 1.00);
  the plates at 1024 cells; the whole layout in about nine seconds and a
  pinned digest.
- The measured failure of the analytic gate, from the design review: on the
  real 512 m fields a pure Poisson pattern reads R = 0.90 to 1.05 on the tree
  mix, 1.14 to 1.34 on the forest alone, 1.34 to 1.63 on the bog, 1.40 to
  1.71 on the water band; the Monte-Carlo null reads 0.86 to 1.07 on all of
  them, and a Matérn cluster 0.23 to 0.69.
- The transfer: `import-run` restored 274 of 277 nodes from the previous run
  and `generate` re-ran the three local ones, at zero provider operations.
- Cost: none. The art is untouched.

## Falsifier

A world whose authored clusters read as clustered under the null gate but
look uniform to a player at play zoom, or the reverse, would mean the null is
measuring the wrong scale; the cluster radius, not the estimator, is the first
suspect, and the gate's thresholds live in one place (`measure.py`) with this
record as the reason to move them. An object that an author cannot place
without naming a biome's roster would mean the object-owned habitat is the
wrong owner after all, and a biome-level exclusives table would be the
smallest honest addition, not a roster.

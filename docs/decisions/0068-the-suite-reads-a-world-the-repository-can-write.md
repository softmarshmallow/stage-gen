# 0068 — The suite reads a world the repository can write

Status: adopted, 2026-09-09. Completes step 6 of
[the Godot promotion](../plans/godot-promotion-plan.md) and follows
[0061](0061-every-genre-runs-on-godot-and-web-is-the-viewer.md), which made
Godot the engine for every genre and left its suite outside the only gate that
runs on every push.

## Fact

The Godot suite is forty-two files and, against the promoted run, 14,274 checks.
Not one of them ran in CI. `uv run python scripts/check.py` is the locked
offline gate and it ran the Python, web and documentation checks and stopped
there — so every port that has landed since 0061 has been protected by a suite
that only ever ran on the machine that happened to have a run on it.

The reason is not neglect. Twenty-nine of the forty-two files open a run
package, through `TestFixtures.world()` if not directly, and `out/` is
gitignored: a fresh clone has nothing to point them at. A gate that needs an
artifact the repository does not carry is not a gate.

## Challenge

Two ways out, and both are worse than they look.

**Commit a run.** A pipeline run is media, and media in the tree is the thing
[the storage rules](../repository-storage.md) exist to prevent; a pruned one is
a derived file that inherits its producer's bugs and still needs that producer
to have run.

**Skip when there is no run.** This is the failure 0066 is about, in a new
place: a check that quietly does nothing when its input is missing reads exactly
like a check that passed.

And a third problem sits under both. Some of those checks are pinned to
numbers a *producer* decided — 2,271 entities, 1,533 forage pieces, a 512 m
world, a plate 6.6 m wide, 119 PNGs. Those can only be true of one run. Any
document a gate can carry makes them false.

## Ruling

The run is **authored**, and the assertions are **two tiers**.

`godot/tools/make_fixture_run.py` writes a small survival package into the
gate's own scratch directory: a hand-written manifest at the contract's floor
and synthesised plates at exactly the sizes it declares. It is not a pruned run
and it is not a mock — it is the smallest package this host will play, which is
worth having written down for its own sake.

It shares the *vocabulary* of a real package and the authored constants a test
names as the contract's own — a stack of ten, a swing of four frames at twelve,
a rain that reaches full in fourteen seconds, the `consume`/`wear`/`carry`/
`light`/`warm` words a `use` block is allowed. It does not share what a producer
decides: it is thirty-two metres where the run is five hundred and twelve, and
it places twenty-four things where the run places 2,271.

So a count is guarded:

    if h.pinned("out/ember-hollow-v13's placement counts"):
        h.assert_eq(rows, 2271, "entity rows")

`TestHarness.pinned()` is true only when the suite is reading the package those
numbers were measured against. It is false on the fixture, and what it refused
is **named** at the end of the run rather than counted — sixteen lines, one per
guarded block. A tier that silently empties is the failure this record exists to
avoid, so it says out loud what it did not read.

Where a pin could be replaced by a *reading* rather than moved, it was, and
those are the better assertions: the mask's size is now checked against the size
the document declares rather than against 512; the splat's width against the
resolution it publishes; the flame's lift against the anchor and the contact on
the lit card, rather than against 0.0804. A test that names where the scree is
now finds a flat patch of scree on whatever plate it was handed, and one that
wanted "the moss cell" asks for the moss cell instead of cell 11.

## Evidence

**The suite is in the gate.** Two steps, in `scripts/check.py`: write the
fixture into scratch, then run the suite against it. A missing engine is a
failure and says so — `run_suite: no Godot at …`, exit 1 — never a skip. The CI
job installs Godot before the gate runs, so the engine's absence is a red job
rather than a surprise.

**Both documents are green.**

    fixture run          3,081 checks in 42 files
    out/ember-hollow-v13 14,274 checks in 42 files

The gap is not lost coverage so much as lost *rows*: most of it is per-entity
checks over 3,804 things instead of 36. What is genuinely tier 2 is sixteen
guarded blocks holding thirty assertions, listed by name every time the fixture
runs — by the runner, and by the supervisor that gathers its children's lists,
because a tier that is invisible under the supervisor is a tier that empties
unnoticed.

**The fixture.** Thirty-two metres at two mask cells to the metre; four biomes,
seven props in sixteen states — every one of them with a winter look — two
actors, eighteen items, eleven recipes, four forage cells; twenty-four placed
things and twelve forage pieces, none of them decorative (decision 0060 holds
here too). 105 PNGs and a 73 KB manifest, 592 KB in all, written in about three
seconds with nothing but the standard library — which, with the suite's own
four, is the whole cost of the two steps the gate gained. Two runs of the
generator are byte-identical, so the world under the suite does not move. No sound and no video: neither an mp3 nor an
mp4 can be synthesised from it, so the document publishes no `sounds`, `music`
or `shell` block, and the two tests that read those say so and pass rather
than skipping in silence.

**Tier one is not vacuous.** Eight defects planted across all four layers, each
one found by the fixture-run suite alone:

    kernel   the generator advances one draw too far      3 files red
    family   the luminance weights swap red and green     1 file red
    family   the first legible candidate stops winning    1 file red
    genre    a placed mob is no longer an entity          2 files red
    genre    a stack holds one more than it may           3 files red
    genre    an optional field written as null            1 file red
    host     the card's foot ignores the bottom gutter    1 file red
    host     the winter look is never resolved            1 file red

Two of those eight are in the table because the first attempt *passed*, and
what was wrong was the check rather than the break. `FamilyContrast` — which
decides what colour a word is drawn in on generated art — had no headless test
at all: the picture sheets catch a wrong answer and the picture sheets need a
window, so nothing that runs in the gate could see it. It has one now, against
the browser's own numbers. And the first version of that test could not tell
"the first candidate that clears the bar wins" from "the best candidate wins",
because every case it named agreed on both readings; the case that separates
them — 6.38 clearing a bar of 4.5 with a 12.97 behind it — is the one that
belongs there.

**And the gap is real, so here it is measured.** A break that stops the
manifest walker after the first image passes the fixture run — the fixture
names images too, just not 119 of them — and fails the real run on the pinned
count. That is the shape of everything tier 2 holds, and it is the price of a
gate that can run anywhere.

**The fixture found a defect on its first draft.** Its layout published
`set_piece: null` where the pipeline omits the key. `String(null)` is an invalid
constructor call, and meeting one inside the dictionary literal in
`_build_entities` aborted the function: the world came back with no entities at
all, no error, and nothing to connect it to the row that caused it. The layout
is JSON and a null there is legal, so every field of a row is read as the
absence it means, and `test_world.gd` builds one row of each kind with every
optional explicitly null. Restoring the inline call turns that check red.

**One threshold moved, and here is why.** The sdist's uncompressed-entry
ceiling was 9,800,000 B and the archive measured 9,804,359 — over by 4,359. Of
the 88,802 B this change adds, 57,732 is the generator itself and 8,936 is this
record; the rest is the two tiers across sixteen test files. The ceiling is
9,900,000 now, with the reading that moved it written beside it. Nothing the
generator *writes* is in the archive: it writes into the gate's scratch
directory and is deleted with it.

**The supervisor** — one process per test file, so a hard death costs one
file's results and a hang is a named file rather than a silence — landed
earlier in this step with its own two proofs, in the commit that holds them.

## Falsifier

A defect that reaches a port through CI green. If one is found, the question to
ask is which tier it belonged in: a defect the fixture *could* have caught means
the fixture is missing a shape (a prop with no winter look, an item with no
`use`, a facing drawn at one size), and the fix is to author that shape. A
defect only a real run's numbers could catch is tier 2 working as designed, and
the fix is a local run, not a wider fixture.

The second: a pin that was moved when it should have been rewritten. Every one
of the thirty was read once and asked whether it names a number or reads a
document. If a guarded assertion turns out to have been checking the reader
rather than the run, it belongs back in tier one as a reading — which is what
happened to a dozen of them on the way here, and why the eight files that hold
pins came out of this with more assertions than they went in with.

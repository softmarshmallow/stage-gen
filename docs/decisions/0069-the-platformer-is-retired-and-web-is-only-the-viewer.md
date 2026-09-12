# 0069 — The platformer is retired, and the web is only the viewer

Status: adopted, 2026-09-09. Closes
[0061](0061-every-genre-runs-on-godot-and-web-is-the-viewer.md), which made Godot
the engine for every genre, after
[0065](0065-the-runner-is-retired-from-the-browser.md) took the runner and
[0067](0067-the-room-the-scene-and-the-case-are-retired-from-the-browser.md) took
the room, the scene and the case. It is the last of the four, the largest, and
the one [0066](0066-a-state-proof-is-not-a-picture-proof.md) was written about.

## Fact

`web/lib/sideview-platformer/`, `web/lib/families/`, `web/lib/manifest/`,
`web/lib/kernel/`, `web/lib/sideview/`, `web/lib/scenario/`, `web/lib/hosts/`,
`web/lib/device-pixels/`, `web/app/preview/[tag]/` and five files under
`web/lib/shell/` were the game: 67,356 lines across 324 files, carrying 1,240 of
the web suite's 1,385 tests. `phaser` leaves `package.json` with them, so the
viewer now names no game engine at all.

A Godot genre and host play the same documents. The genre is
`godot/genres/sideview_platformer/`, the families it composes are
`godot/families/`, and the host is `godot/hosts/sideview_platformer/`.

This deletion also ends the split ownership the other three retirements left
behind: the kernel, the fifteen families and the scenario runtime stayed in
`web/` after 0065 and 0067 only because the platformer still composed them.
Nothing composes them here now.

## Challenge

0066 is the challenge, and it was written after this repository published 0065
on a proof that could not see the picture. The rule it set is that a genre is not
ported until its picture is measured. The obvious way to satisfy it was a picture
gate: a fixed-frame capture on each side, compared. That was proposed here and
**rejected**, on the ground that it is a test harness invented for the port
rather than a feature of the game — and that the reference half of the comparison
is the thing being deleted, so the gate would be built, run once, and become
dead weight the moment the browser went.

That leaves the question 0066 asked genuinely open: if not a gate, then what
holds the drawing?

## Ruling

The browser platformer is deleted. The Godot genre and host replace it.

**The drawing is held by playing it, and the record says so.** No picture gate
was built. What stands in its place is two rounds of play by the person who owns
the game, against the browser original they kept a screenshot of — seventeen
defects reported, sixteen fixed under this record, one referred back as a
package defect. That is a weaker instrument than a hash in one respect and a
much stronger one in every other: it is the only instrument that found any of
what follows.

## Evidence

**State parity is exact, on both runs.** The browser's own replay goldens —
`01-village-600` and `02-defeat-600`, six hundred frames each, carrying a
conversation, a portal, a fight, a death and a recovery — replay on the Godot
side to **600 of 600** per-frame sha256 hashes identical and **30 of 30** sampled
world digests identical, field for field, on both. Both sides write a float as a
nine-decimal string, so this is equality rather than a tolerance.

**And state parity saw none of what was actually broken.** Before any of it was
played, twelve published facts were found that the host drew nothing at all for —
found by reading the twenty-six browser modules no Godot file claimed, not by any
gate. Damage numbers were drawn at `unit_v1` while the package publishes
`arcade_v1`, so a blow that should read `103` read `1`. There was no defeat card,
no portrait in a conversation, no hit flash, no spark fan, no kill burst, no
swing arc, no experience or level line, no spawn or death fade, no map-name
banner, and no flash on the player's own health bar. Every one of those is
invisible to a frame hash by construction: the world hashes identically whether
or not anything draws it.

**Then playing it found the largest single defect of the port.** Every motion but
`idle` and `hurt` was drawn at the wrong size, because `calibration.state_rebase`
is published per state and the host read only the actor-level multiplier —
`climb_ladder` at 0.35 and `basic_attack` at 1.33 of the size they were authored
at. Two rounds of feedback also found: the inventory closing on the frame it
opened, mobs refusing to spawn on platforms, double-jump height depending on
timing, the climb anchored below the ground, no portal prompt, a dialogue panel
sized and placed by the wrong rectangle, the player's own face missing from
conversations, a climb that translated without animating, every piece of screen
furniture drawn outside the world's letterbox, and no audio playing at all.

**What the host is measured by now.** The Godot suite is 15,522 checks in 47
files. `tests/contract/test_godot_boundaries.py` holds the four layers apart.
The web gates are green after the deletion: `tsc` clean, 145 tests in 17 files,
and a build that emits eleven routes, none of them a preview.

**What this record does not cover, said plainly.** Two things are open, and
neither is a port defect.

The first is the numeral face. [0063](0063-a-typeface-is-a-package-input.md) made
a typeface a package input; the host half landed and resolves a published face,
but `godot/games/bellweather/inputs/default` declares no `fonts/` and the platformer recipe
publishes no typeface block, so the damage numbers are still drawn in a system
fallback. That is pipeline work, not host work.

The second is the boss. `crowncrag_page_eater` is authored as a boss encounter at
`anchor = "castle_gate"`, and that string appears exactly once in the entire run —
in the encounter itself. No map publishes the anchor, so the gate is retired at
load with a diagnostic. The browser did the same thing: its `setPieceAnchorX`
returns null for an unresolved anchor. This is a package defect that predates the
port and survives it, and it is fixed in the recipe rather than in either host.

## Falsifier

A drawing defect in the Godot platformer that the browser did not have, found
after this record, that neither the state proof nor two rounds of play caught. If
one is found, the ruling above was wrong in a specific way — not that play is a
bad instrument, but that a single player's two passes over one package is too
thin a net for a genre this size, and the answer is more play against more
packages rather than the gate that was rejected.

The prior is not favourable. This exact class of miss has now happened twice:
0065 shipped a runner with no boss, no cut-in, no dust and no sound behind a
600-frame proof, and this port had twelve of them behind two. What changed is
that the second time, somebody played it.

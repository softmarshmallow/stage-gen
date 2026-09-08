# 0067 — The room, the scene and the case are retired from the browser

Status: adopted, 2026-09-09. Follows
[0061](0061-every-genre-runs-on-godot-and-web-is-the-viewer.md), which made Godot
the engine for every genre, and
[0066](0066-a-state-proof-is-not-a-picture-proof.md), which set the bar these
three had to clear. It retires three surfaces at once because they were never
three: `/room/<tag>` and `/scene/<tag>` were `/case/<tag>` with a single beat.

## Fact

`web/lib/pointclick/`, `web/lib/dialogue-scene/`, `web/lib/narrative/`, the two
shell readers, four routes and three player components were a point-and-click
room, a visual novel and the container that plays them in order: 9,619 lines
across 40 files, carrying 134 of the web suite's tests.

Their simulations were ported first and separately, and were exact before
tonight: fourteen clicks, twenty-six actions and twenty actions, digest for
digest against the browser's own goldens. What none of them had was a picture.

## Challenge

0066 is the whole difficulty. The runner was retired on six hundred exact frame
hashes and shipped with no boss, no cut-in, no dust and no sound, because not one
of those can move a hash. A room's state proof is fourteen clicks; a scene's is
twenty-six actions; a case's is twenty. Every one of them is exact, and between
them they say nothing about whether a backdrop is drawn, which way round the
speaker and the listener are, whether the line is on the panel or off the bottom
of it, or whether the backlog is over the game or under it.

And the view is the half where the browser was *wrong*. Its HUD constants were
authored when its panels were drawn rectangles; the panels became generated
nine-slice art whose corners eat `insets / draw_scale` on every side, and nothing
was re-measured. A faithful port would have reproduced three visible faults in
the room and one in the scene, and passed any gate that only compared the two.

## Ruling

The three browser surfaces are deleted. Three Godot hosts replace them, and each
one carries a measured picture gate. Every threshold in them carries the reading
that set it, and every check but one was shown to fail on the defect it exists to
catch; the exception is named below and in its own file, with the reading that
explains why it cannot fail on the packages that exist.

`web/lib/scenario/` stays: the browser platformer still imports it from
`prepared-scene.ts`, `npc.ts` and `dialogue-choices.ts`. It retires with the
platformer, in that record and not this one.

**The view is corrected against the browser rather than copied from it**, and
every correction carries the reading that motivated it. That is a departure from
how the runner and survival were ported, and it is deliberate: a port whose
reference is wrong cannot be proved by agreeing with it.

## Evidence

**The simulations did not move.** 14/14 clicks, 26/26 actions and 20/20 actions,
byte-identical, before and after. Adding a beat's display name to the case
document does not reach them: the digest hashes state and events.

**Three picture gates, each falsified.** Seventeen named states, `boot` through
`finished`, taken against `out/the-grain-window-a4`,
`out/the-grain-scene-a` and `out/the-grain-episode-one`.

    room      5 of 5 pictures carry what they must
    dialogue  6 of 6
    case      6 of 6

Every threshold carries the reading that set it, and every check but one was
shown to fail by breaking the host on purpose and re-shooting the whole sheet —
nineteen deliberate breaks, nineteen caught:

    room      no canvas ground, no panels, ink the colour of the plate,
              no selected verb, no hotspot markers, no end card      (6 of 6)
    dialogue  no panel, invisible ink, no emphasis, no cast,
              the raw framing scale, no choice row, no end card      (7 of 7)
    case      no ground, a blank bar, no leaf, a stretched leaf,
              no Continue, a blank curtain                           (6 of 6)

The exception is named in its own file: on both published room packages the
narration plate's interior is 168px and the longest sentence either can produce
is four lines at the top of the ladder, so the words cannot leave the plate
however badly the fitting is done. It is a guard, it says so, and it would fire
on a package with heavier border art.

**Three of the seventeen cost a correction rather than a threshold**, and the
corrections are the reason to trust the rest. The first draft of the room's
clipping check looked *inside* the text box for a cut glyph, and the build with
the ladder defeated passed it — a paragraph cut cleanly between two lines looks
exactly like a paragraph that ended there. The dialogue's emphasis window was
wide enough to be mostly backdrop and read 7.6 for a change that is really 18.9.
The case's bar check read the whole bar and passed a build whose title was blank,
because the backlog toggle's own word is ink too. In each the axis was changed,
not the number.

**What a picture cannot say, said where it can be falsified.** Whether a
paragraph is *whole* is not visible in a still, so the fitting lives in
`godot/tests/test_room_layout.gd` and `godot/tests/test_dialogue_layout.gd`. At
the browser's own plate sizes both report:

    the longest sentence a shipped room can produce fits the plate it is written on
    the longest line a published scenario carries fits the box it is written in

**Four faults corrected, with their measurements.**

- The room's narration plate is 156px with a 52px interior; the window room's
  longest single-click sentence is 516 characters, which is four wrapped lines at
  the ladder's floor. The tail rendered past the plate onto the backdrop and the
  control bar.
- The room's control hint is placed on the bar panel's interior, which is inside
  inventory slot 0.
- A 132x60 verb button under the published sheet's insets has a 55x10 interior,
  so its glyph draws at ten pixels.
- The scene's 208px panel has a 112px interior, of which the speaker's row and
  the paddings take 48. Sixty-four pixels is one wrapped line; the longest of the
  1,207 lines the six published scenarios carry is 288 characters, which is
  three.

All four have one cause and one fix: a rectangle's size is now its *interior*
plus the package's own insets, which is self-correcting for any art rather than
true for the art it was measured against.

**Three smaller ones, and two absences.** A sprite hotspot's marker and its hit
area are one rectangle, so the overlay no longer points at somewhere you cannot
click; the long-press stamp is reset on every press; the end card is the
published `panel_frame`, which is what this specification always said it was.
`FamilyScenarioProgram.SLOTS` said three where the contract publishes five, and
The Grain uses `far_left` and `far_right` heavily — the constant was never
referenced, so nothing had gone wrong, and the first view to lay three out would
have put half a cast in the middle of the stage. And `restoreScenarioState` and
`scenarioProgress` had no port at all.

**Two runs the plan named cannot be played by anything.**
`out/clockmakers-attic-v7` is `pointclick-room-runtime-v2` where the contract
demands v3 at `schema_version` 3; the browser 404s on it and on every other
`clockmakers-attic-*`. `out/larkfield` is `dialogue-scene-bundle-v6`, two
generations behind: its `scene_data` publishes a single `scenario` object where
v8 requires a `scenarios` array, and it carries no `ui` block, so no version bump
reaches it. The runs that play are `the-grain-window-a4`,
`the-grain-motor-court-a4`, `the-grain-scene-a` and `the-grain-episode-one`.

**And one route was dead before this record.** `/scene/<tag>` reads a run's
bundle with no scenario id, and all three v8 runs publish six scenarios, so it
throws on every run that exists. The Godot host takes the pair.

**Check counts.** The Godot suite is 14,236 checks in 42 files, up from 14,125 in
40. The web suite is 1,387 tests across 130 files, down from 1,521 across 144 —
the 134 the deleted surfaces carried, and no others.

## Falsifier

A drawing defect in one of these three that the browser did not have, and that
the sheet passes. If one is found, the seventeen measurements are measuring the
wrong seventeen states, and the fix is an eighteenth shot rather than a wider
tolerance on the existing ones.

The second, and the one this record is more exposed to: a *correction* that was
not one. Four numbers here were changed away from the browser's on the strength
of a measurement rather than a comparison. If a package turns up whose art makes
one of those corrections wrong — a panel whose interior is generous and now
draws a plate half the frame tall — the rule "the interior is the constant" is
what should be revisited, not the number.

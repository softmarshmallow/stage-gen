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

**The simulations did not move.** Fourteen clicks, twenty-five actions and
nineteen actions, byte-identical before and after — 14, 26 and 20 hashes,
because a scene's and a case's frame files open with the state before the first
action and a room's do not. Adding a beat's display name to the case document
does not reach them: the digest hashes state and events.

**Three picture gates, each falsified.** Seventeen named states, `boot` through
`finished`, taken against `out/the-grain-window-a4`,
`out/the-grain-scene-a` and `out/the-grain-episode-one`.

    room      5 of 5 pictures carry what they must
    dialogue  6 of 6
    case      6 of 6

Every threshold carries the reading that set it, and every check but one was
shown to fail by breaking the host on purpose and re-shooting the whole sheet.
Nineteen breaks at first; thirty-two after an adversarial pass showed how much
the first nineteen were not looking at (see below):

    room      no canvas ground, no panels, ink the colour of the plate,
              no selected verb, no hotspot markers, no end card      (6 of 6)
    dialogue  no panel, invisible ink, no emphasis, no cast,
              the raw framing scale, no choice row, no end card      (7 of 7)
    case      no ground, a blank bar, no leaf, a stretched leaf,
              no Continue, a blank curtain                           (6 of 6)

The exception is the room's "ink beside the plate", and it is a guard rather
than a discriminator: `clip_text` keeps the words inside the art by
construction, so on any package the ink cannot reach the canvas whatever the
fitting does. It would fire on a build that removed the clip, which is the
browser's own state.

The first draft of this record justified that exception differently and was
wrong: it said the longest sentence either room can produce is four lines at the
top of the ladder and so cannot escape. It is six lines at the top and five at
the floor, and at the plate this port first shipped it did not fit at all — see
below.

**Several checks cost a correction rather than a threshold**, and the
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
  longest single-click sentence is 516 characters — `inspect stage_door`, which
  requires nothing and is reachable on the first click — and it needs 162px at
  the ladder's floor. The tail rendered past the plate, over its own bottom
  border art and down into the canvas beneath it. (Not upward onto the backdrop:
  the browser anchored its narration at the plate's top and grew downward only.)
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
demands v3 at `schema_version` 3, so the browser 404s on it — as it does on
`clockmakers-attic-v1` through `-v6`. Thirteen further rooms declare kind v3 at
`schema_version` 1, which passes the kind guard and throws inside the parser, so
those were a 500 rather than a 404: `clockmakers-attic-ui-v1`, six
`the-grain-window*` and six `the-grain-motor-court*`. `out/larkfield` is
`dialogue-scene-bundle-v6`, two generations behind: its `scene_data` publishes a
single `scenario` object where v8 requires a `scenarios` array, and it carries no
`ui` block, so no version bump reaches it.

Six runs play: the rooms `the-grain-window-a4` and `the-grain-motor-court-a4`,
the scenes `the-grain-scene-a`, `-4` and `-5`, and the case
`the-grain-episode-one`. The gates use the first, the third and the last.

**And one route was dead before this record.** `/scene/<tag>` reads a run's
bundle with no scenario id, and all three v8 runs publish six scenarios, so it
throws on every run that exists. The Godot host takes the pair.

**Check counts.** The Godot suite is 14,237 checks in 42 files, up from 14,123
in 40, and the three picture sheets carry thirty-two measurements between them. The web suite is 1,387 tests across 130 files, down from 1,521 across
144 — the 134 the deleted surfaces carried, and no others.

## What an adversarial pass found after this record was first written

Five independent readings of the three hosts, the three gates and this record,
each asked to refute rather than confirm. What they returned is the reason this
section exists rather than a second record.

**The room's plate was two pixels too short, and the test written to catch that
used a stand-in eighty-one characters short of the sentence it named.** The
window room's longest single-click narration is 516 characters; at the plate
this port first shipped it needed 162px in a 160px box, came all the way down
the ladder, and `clip_text` ate the bottom of its last line — silently, because
that is what clipping is for. The stand-in in `test_room_layout.gd` was 435
characters and named the wrong interaction, so the assertion passed.

The plate is 184px of interior now, which holds that sentence at 20px with a step
of the ladder still in reserve; the test's stand-in is held to the measured
length by an assertion rather than by a comment, and the size it fits at must be
*strictly above* the floor — because `fitted_size` returns the floor when nothing
fits, so "it fits at the floor" is exactly what a plate too small also reports.
At the plate that shipped, the corrected test reports both:

    test_room_layout.gd: the longest sentence a shipped room can produce fits
                         the plate it is written on
    test_room_layout.gd: with a step of the ladder still in reserve, rather than
                         clamped against its floor

And the sheet's `narrated` shot is that sentence now, rather than a middling one.

**A track with no sound would have silenced the scene.** `_players` caches a
null against a track whose mp3 is missing, and `stop` on that aborts the
function before it records what is playing — so the dead track stays in the set
and nothing sounds again. The browser skipped a missing source and kept the rest
of the soundtrack.

**Three refusals the browser had and the port had dropped.** A `show` at a slot
outside the published five was taken silently and drawn at the centre's offset
*and* the centre's stacking — the same fault the three-valued slot constant would
have caused, by another road. A case edge naming a beat the document does not
publish left the player on a bare stage with a save that offered a Continue back
into it. And a case with no terminal beat was admitted. All three refuse now, and
the host says so rather than drawing nothing.

**Three smaller differences from the browser, none of them deliberate.** The
scene's progress readout measured contrast at 3.0, which is the *room's* number
for its control hint; a choice option's label did not wrap, so a long one would
have hung off both ends of its button; and an atlas button offered pure white as
the light end of its range where each genre draws its own paper. All three are
the browser's values now.

**And the sheets themselves were the larger finding.** A lens asked only to
break the *gates* rebuilt each sheet with a defect in it and showed what still
passed: a room with no backdrop at all; an overlay outlining empty wall beside
each of the fourteen things it names, which read *higher* than the correct one;
an inverted emphasis rule cooling the speaker and lighting the listener, which
read identically because the check measured how far two frames differ and not
which way; a backlog open and holding nothing, which read *better*, because the
only thing asked of it was how dark the stage went; two choice buttons with no
words on them; an end card drawn blank; a control bar that never says which of
eight beats you are in; a curtain with nothing to press; and a narration cut to
its opening line.

Thirteen measurements were added and every one was shown to fail on the defect
it exists to catch — thirty-two breaks now, thirty-two caught. Three of the
thirteen cost a second attempt, and those are the ones worth reading: brightness
cannot tell a speaker from a listener, because one actor's coat is lighter than
another's, so the reading is the *cool tint* a listener carries and the sign of
its change between two frames. A fixed band under a curtain cannot find its
buttons, because taking the buttons away lets the centred column move the words
down into the band — the reading went **up** — so it is the buttons' own border
colour instead. And a narrow band across a choice button passed a build whose
labels had flown off the buttons entirely, which was a regression this pass
introduced and this pass then caught: the band has to be the whole interior.

None of this moved the simulations: fourteen clicks, twenty-five actions and
nineteen actions still replay byte for byte, and the three sheets still read
5 of 5, 6 of 6 and 6 of 6.

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

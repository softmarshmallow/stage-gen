# 0032 — The crouch buys the avatar state and the hazard anchor as one change

*Ruled with the slide increment — the only paid one.*

## Fact

With one verb there is exactly one question per obstacle ("when?"), one sentence in the
collectible language, and two difficulty dials. A hazard was `{prop_id, column}` and the
validator actively refused a hazard whose column is unsupported, so "a thing at head height
with clearance beneath it" was literally unsayable.

## Challenge

An avatar motion state and a track contract field are separate contracts owned by separate
modules, and shipping them separately is the smaller review each time.

## Ruling

They are bought as ONE change, never two: an overhead prop with nothing to duck under is one
image operation of dead art, and a slide state with nothing to slide under is a pose nobody
can author against. Three contracts move together with no aliases — the track gains a required
hazard anchor with no default plus a clearance, the gameplay contract gains a closed duck
profile whose constants make the overhead proof the ground proof with the anchor flipped, and
the avatar contract bumps. While bumping the avatar contract the *shape* is fixed rather than
extended: the required motion set becomes a FUNCTION of what the track declares, or every
future runner pays one image operation forever including games with no overhead hazards.

## Evidence

Slide is the only verb in the reference set that *punishes* a jump, which is what stops "be
airborne as much as possible" from being dominant, and it is the first thing that makes hazard
artwork load-bearing on the vertical axis. The motion-state vocabulary was declared in three
independent places with no test tying them — the frozenset that validates, the tuple that
drives node fan-out, and the runtime's own copy — so editing one alone either refuses every
avatar or generates a strip the contract will not admit; all three move in one commit and a
test now ties them. Cost was corrected by rebuilding the graph rather than counting by hand:
25 nodes to 31, twelve image operations to fifteen, and the topology digest moves.

## Falsifier

A genre in this family whose overhead hazards are worth drawing before it has a ducking verb,
or vice versa — which would mean the two contracts are separable after all.

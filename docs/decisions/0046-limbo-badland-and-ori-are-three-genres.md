# 0046 — Limbo, Badland and Ori are three genres, and the first is the cinematic platformer

*Ruled while reserving future genres.*

## Fact

"Atmospheric side-view adventure" was proposed as one genre covering all three references. The
taxonomy defines the genre slot as the gameplay composition profile the module assumes.

## Challenge

The three share an art direction, a camera and a plane, and naming them together is how players
and store pages group them.

## Ruling

The premise is refused first: that phrase names the art direction, not the gameplay
composition, so mood words are structurally disqualified as segments. The decomposition is
three genres. Limbo and Inside are a **cinematic platformer**, subtype puzzle-platformer, with
the failure mode Playdead itself calls "trial and death". Badland is a one-touch physics
side-scroller whose avatar is a rigid body never grounded by design, where standing on terrain
is a failure state rather than the base case — closer to the runner than to Limbo, and not a
platformer at all; it *consumes* the painted-terrain module rather than being homed there,
because conflating a genre with a module it uses is the exact confusion the taxonomy exists to
prevent. Ori is a metroidvania. Build the cinematic platformer first, bound to the same
side-plane presentation profile as the platformer and the runner, with members under a matching
package prefix so the segment and the prefix are identical and the name is greppable once.

## Evidence

Specificity means ruling things out. `adventure` names nothing checkable.
`puzzle_platformer` over-claims: the word promises a solvability proof, and these puzzles are
physics contraptions whose solvability is not decidable offline — putting a claim in a contract
name that no validator can honour is the opposite of what a named jump profile does.
`metroidvania` is a different game. Mood words are style facets the visual taxonomy already
owns. Bare `cinematic` collides with the cutscene namespace the namespace table already
assigns. The compound disambiguates and is the established term anyway. It does not commit us
to a rotoscoped animation budget, because the taxonomy separates genre from the motion
treatment facet. Why this one first, decisively: it is the only one of the three whose new
requirement is *authoring vocabulary* rather than a new simulation substrate — a finite
non-looping level with an authored end, a gap the asset taxonomy already reserved.

## Falsifier

A gameplay composition shared by all three that no other genre has — which would make one
family honest and the three-way split a distinction without a difference.

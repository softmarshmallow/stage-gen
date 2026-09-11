# P90 Quick Approach - native integration and independent visual review

**PASS for the inspected story and laboratory compositions.** This reviewer
implemented the focused QA runner, not the actor movement API, story cue or
study controls. No artwork was generated or changed.

Yuzu now makes a short horizontal approach toward Sena during their existing
exchange. The before, midpoint and held frames show a clear reduction in their
separation while Sena remains in place. Yuzu retains her height, scale, color
and pose, and her sweat-drop manpu moves with her. The closer composition keeps
both faces and the dialogue readable. It reads as a quick change of blocking,
with no walking bounce, disappearance or camera push-in mixed into the motion.

The Actor Motion study demonstrates approach from either side. Its duration,
center gap and interpolation controls remain distinct and readable. English
and Korean labels fit at both native sizes. The existing two Walk-Away modes
and Restless Bounce remain available in the same study.

## Focused evidence

[`quick_approach_integration_checks.gd`](../quick_approach_integration_checks.gd)
passes with **12 captures at 1280 x 900 and 2560 x 1800**, zero failed assertions,
and no script errors or leaked-object warning. Logs are
`/tmp/p90-quick-approach-native.log` and
`/tmp/p90-quick-approach-native-console.log`. Existing runtime PNG import/export
warnings remain unchanged.

- The existing `the_useful_kind` beat follows the completed handoff with Yuzu
  at world center X=410 and Sena at X=890. After a 0.25-second delay, Yuzu moves
  to X=610 over 0.32 seconds with `ease_in_out`; her midpoint is X=510. Sena
  stays at X=890 throughout, giving the authored 280-pixel center gap.
- Both hosts preserve mover Y, sprite size, scale, rotation, material,
  modulation, self-modulation and visibility. The stationary partner's complete
  presentation snapshot stays unchanged. Story camera framing stays wide.
- At an active story sample, camera presentation transforms the posed actor
  and attached manpu exactly once without advancing movement time. The active
  cue survives pause, English/Korean switching and an actual detour to the
  independent Presentation Lab with identical movement state and world framing.
- The final position holds until explicit continuation. Entering the following
  actor-free establishing shot clears movement state. Continuing early during
  the approach also clears the pair and prevents retained hidden movement.
- Actual study inputs select the actor and approach mode, pause/replay/reset,
  reverse direction, choose linear interpolation and adjust duration/spacing.
  The reversed case moves Yuzu from X=890 toward stationary Sena at X=410,
  stopping at X=695 with a 285-pixel gap over the selected 0.33 seconds.
- Parameter changes reset the prior display for a clean replay. Language and
  pause preserve active study motion. All three existing motion modes are
  played to completion after Quick Approach with their original solo staging
  and no errors; no separate regression capture matrix was added.

The stopping distance is center-to-center blocking, not silhouette collision
avoidance or pathfinding. These checks establish the bounded native 2D use and
in-session continuity; they do not claim arbitrary choreography, live target
tracking, durable save compatibility or a performance benchmark.

## Digest-bound captures

[The manifest](manifest.json) records all 12 capture hashes, five runtime source
hashes, movement samples and the empty error list. All recorded source hashes
match the inspected final files. Its SHA-256 is
`56ef54432a8c73aef59a23670c328414d30a7e053c61e8f700ca96b94379b477`.

| Inspected capture | SHA-256 |
| --- | --- |
| [Story before approach](story-before-1.png) | `248bb19bc1112512cb561cb75cca4dd5c005fe94ef7e3666039456ef76777b71` |
| [Story midpoint](story-midpoint-1.png) | `204052ef5254915b46433cf6ae1bebe9d0a4012e10b58b820dd116e270b6331c` |
| [Story held position](story-settled-1.png) | `acfe4bb1ee8a3079498f7a0dbda247c70209e702c0f27ac85d8edc37579fe9c3` |
| [Story held position at 2560 x 1800](story-settled-2.png) | `c9c9bc1c9f4249b4c5c203c5e25f071bcee4e1d51ad7aeb48b3773061be7f4b9` |
| [Study approach from left](lab-from-left-midpoint-1.png) | `6d188903a2b7233efc161096b0c599517fd5788543146d5627c2f8381aab0b79` |
| [Study approach from right](lab-from-right-midpoint-1.png) | `5b06c6cdf6f9868a3181b9cd8274baa6e13b855fd7f8e66845755f8a01e55f9e` |
| [Study held position and controls in English](lab-from-right-settled-en-2.png) | `b23a940f72326ccbd7a0f9c95853c36f454d6f27eaf50e0f42026f2065140800` |

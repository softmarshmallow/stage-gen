# 0009 — A consumer policy proves itself in play before it becomes an authored field

*Ruled 2026-09-02 with the density thread.*

## Fact

Clumped spawning landed as `placement: "uniform" | "clustered"` on the zone shape inside
`web/lib/sideview-platformer/spawn-director.ts`, a consumer-internal manifest with no package
contract behind it. Step 4 — promoting `placement` to the Python `SpawnZone` model as a
defaulted field — was written and then deliberately not taken.

## Challenge

A knob the consumer honours and the package cannot name is invisible to authors, and the
promotion is a defaulted optional field: additive, cheap, and reversible.

## Ruling

The promotion waits on play, not on the code being ready. A field in the authored contract is
a promise to every future package; a consumer default is a policy that can still be wrong. The
field lands once the policy has proven itself in play.

## Evidence

Three constants that shape the same behaviour — the uniform pick, the minimum separation and
the off-screen preference — all sat in the consumer's default policy rather than in TOML, and
raising the populations was pure authoring against fields that already existed.

## Falsifier

A package that needs per-zone placement to differ from the consumer default before anyone has
played it — at which point the default is not a default.

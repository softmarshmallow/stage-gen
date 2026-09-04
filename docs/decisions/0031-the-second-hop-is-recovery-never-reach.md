# 0031 — The second hop is recovery, never reach

*Ruled with `double_arc_v1`.*

## Fact

The design condition is content the player cannot memorise, 1.67s of lookahead fully ramped,
and one-hit death. A mistimed first jump is terminal at the moment of takeoff.

## Challenge

A second jump is more capability, and more capability normally means more reach: a designer
who has it will place gaps that need it, and admission then has to search over
(launch column, air-jump column) pairs rather than over launch columns.

## Ruling

The encoding is the whole ruling and is not optional: the double-arc profile declares the
*single-hop* worst case unchanged — the same maximum clear gap and the same maximum rise. The
second hop is pure forgiveness and never reach, so admission stays a one-dimensional
existential over launch columns. The road to a reachability solver is the one property not for
trade. No authored chunk ever demands both hops, so a player who spends the air jump early is
never stranded, and soundness is preserved by construction because strictly more capability
keeps every admitted chunk clearable. The hop count does not go on the jump profile: by the
SDK rule, admission reads it for nothing, so the closed *name* is the entire contract surface
and the count belongs in the runtime profile table.

## Evidence

The forgiveness is what lets a designer place tight patterns without being cruel, and it gives
the trail a second altitude band for free — a high flat token line is uncollectable with a
single hop, so the collectible teaches the input by being unreachable otherwise. One bug was
fixed in the same change: the runtime swapped texture and animation only on a state change and
the jump strip plays once, so a second hop inside the same jump state would have found the
atlas already finished and holding its last frame. Replay is now on the impulse, and the
state-to-animation rule is table-driven.

## Falsifier

An authored chunk that is clearable only with the air jump — which would make the second hop
reach, and admission unsound.

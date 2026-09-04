# 0027 — A number belongs in the SDK table iff a refusal depends on it

*Ruled while completing the declared arithmetic.*

## Fact

Admission proved gaps and rises from two integers, but the arc the player actually flies is
shaped by five numbers the SDK had never seen: a jump peak margin, an airtime headroom, a base
speed, an avatar half width and a hazard column inset. The offline proof and the runtime arc
agreed only by convention — the runtime test asserted its arc against hard-coded literals,
never against the manifest's published clearable gap.

## Challenge

Those five are game-feel constants living beside the code that uses them, and moving them into
a published contract is a large diff for no observable change.

## Ruling

**A number belongs in the SDK constant table iff a REFUSAL depends on it; it stays
consumer-owned iff only the FEEL depends on it.** That correctly leaves the ramp numbers with
the consumer and moves the five above. Published values equal the constants exactly, so the
change is observation-neutral by construction — a large diff with nil behaviour delta, which
makes it trivially reviewable.

## Evidence

Retuning the airtime headroom for game feel would have made every "provably clearable" claim
in the repository silently false with no gate catching it. Two traps found in review: the
manifest bump moves the topology digest, because a node's ports are hashed including their
kind, so the generated graph contract and its embedded block move in the same change or the
docs contract test fails inside the gate; and the node cache key does not include ports, so
regenerating is a cache hit that replays the old manifest byte-identically and is still
refused by the new parser — the manifest node's contract version must be bumped too.

## Falsifier

A refusal that is correct while depending on a number the consumer owns, or a feel constant
that a gate has to read — either would mean the predicate does not partition the constants.

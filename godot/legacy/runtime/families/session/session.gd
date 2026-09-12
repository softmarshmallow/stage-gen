class_name FamilySession
extends RefCounted

## A run's lifecycle: it starts, it ends, and the player asks for another.
##
## A port of `web/lib/families/session/session.ts`. The slice is `{phase, seed,
## runIndex, endedBy}` plus whatever the genre adds — the runner keeps its
## generator there too.
##
## The seed lineage is the part that matters for a replay. A restart does not
## invent a seed from the clock; it draws the next one from the run's own
## generator, so a chain of runs is as reproducible as a single one and "the
## third run of seed N" is a thing that can be replayed.

const SCOPE_RUN := "run"
const SCOPE_SESSION := "session"


## The next run's seed, drawn from this run's stream. One draw, always.
static func next_session_seed(rng: KernelRng) -> int:
	return int(floor(rng.next() * 4294967296.0)) & 0xFFFFFFFF

class_name FamilyParticles
extends RefCounted

## Seeded noise and a bounded ring, for effects that must replay.
##
## A port of `web/lib/families/particles/particles.ts`. A puff of dust is
## presentation, but it is presentation *derived from the seed*, so two runs of
## one seed throw the same dust and a picture comparison means something.
##
## The browser wrote this hash three times — here, in the loot family's drop
## bounce, and aliased in the runner's dust. It is one function and is ported
## once.

const MASK := 0xFFFFFFFF
const DIVISOR := 4294967296.0


## A float in [0, 1) from a seed and a channel. Deterministic, cheap, and not a
## generator: nothing advances, so two readers of one channel agree.
static func unit_noise(seed_value: int, channel: int) -> float:
	var hash := (KernelHash.imul(seed_value ^ channel, 0x9e3779b1) ^ (seed_value >> 15)) & MASK
	hash = KernelHash.imul(hash ^ (hash >> 13), 0x85ebca6b) & MASK
	hash = KernelHash.imul(hash ^ (hash >> 16), 0xc2b2ae35) & MASK
	return float(hash) / DIVISOR


static func ease_out_cubic(progress: float) -> float:
	var inverted := 1.0 - progress
	return 1.0 - inverted * inverted * inverted


static func unit_progress(value: float) -> float:
	return maxf(0.0, minf(1.0, value))


## The hardest cap a ring will take, whatever a caller asks for. A run that lays
## thousands of puffs must cost a bounded amount of memory and a bounded amount
## of drawing, or a long run is a slower run.
const RING_CEILING := 256


## Add one record to a bounded ring, oldest first, evicting while over the cap.
##
## The ring is a plain Array and is mutated in place, which is the port of the
## browser's `ParticleRing.remember`. Records are read oldest-first, so an
## eviction takes from the front.
static func ring_remember(live: Array, record: Dictionary, max_records: int) -> void:
	live.append(record)
	var cap := maxi(1, mini(RING_CEILING, max_records))
	while live.size() > cap:
		live.remove_at(0)


## Drop every record `spent` answers true for.
##
## Walked backwards so an index stays valid across a removal — the same reason
## the browser's version counts down.
static func ring_prune(live: Array, spent: Callable) -> void:
	var index := live.size() - 1
	while index >= 0:
		if bool(spent.call(live[index])):
			live.remove_at(index)
		index -= 1

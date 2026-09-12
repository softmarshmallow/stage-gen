class_name FamilyShuffleBag
extends RefCounted

## What plays next: a deterministic, cyclic shuffle bag.
##
## A port of `ShuffleBag` in `web/lib/families/soundtrack/selection.ts`. Every
## multi-track bag is exhausted once before it refills, and the first item after
## a refill cannot equal the one before it — so a pool of two alternates and a
## pool of five never repeats inside a cycle. A one-track pool ends after one
## play, because a repeat-free cycle is impossible for it; that is a stated
## contract rather than an oversight.
##
## Seeded off the package digest, so two runs of one package hear the same order,
## two packages do not, and nothing about the order depends on when the run
## started.
##
## **The arithmetic is JavaScript's, and it has to be.** The order is part of the
## published state a digest compares, so this reproduces FNV-1a and the
## browser's small generator exactly — including `Math.imul`, which is a signed
## 32-bit multiply that a 64-bit engine will silently get right for small inputs
## and wrong for the ones that matter.

const MASK := 0xFFFFFFFF
const DIVISOR := 4294967296.0

const FNV_OFFSET := 0x811C9DC5
const FNV_PRIME := 0x01000193

var _catalog: PackedStringArray = PackedStringArray()
var _admitted: PackedStringArray = PackedStringArray()
var _bag: Array = []
var _last: Variant = null
var _state: int = 0


## A bag over `catalog`, seeded from a string, optionally narrowed at once.
static func of(catalog: PackedStringArray, seed: String, pool: PackedStringArray = PackedStringArray()) -> FamilyShuffleBag:
	var made := FamilyShuffleBag.new()
	made._catalog = catalog
	made._admitted = _resolve(catalog, pool)
	made._state = seed_from_string(seed)
	made._refill()
	return made


## What `take` would return, without consuming it. Empty when nothing is planned.
func planned() -> String:
	return "" if _bag.is_empty() else String(_bag[0])


## Consume the next track, or "" once the selection is exhausted.
func take() -> String:
	if _bag.is_empty():
		return ""
	var track := String(_bag.pop_front())
	_last = track
	_refill()
	return track


## Narrow to a named pool. `retain` is a track the caller intends to keep playing
## across the change, which counts as the destination's first consumed item.
## False when the pool is the one already bound.
func bind_pool(pool: PackedStringArray, retain: String = "") -> bool:
	var next := _resolve(_catalog, pool)
	if next == _admitted:
		return false
	_admitted = next
	_bag = []
	_refill(retain)
	return true


func admits(track_id: String) -> bool:
	return _admitted.has(track_id)


func _refill(excluded: String = "") -> void:
	if not _bag.is_empty():
		return
	# A one-track pool that has already played is finished. Refilling it would
	# be the immediate repeat the policy exists to prevent.
	if excluded.is_empty() and _admitted.size() == 1 and _last != null:
		return
	var next: Array = []
	for track in _admitted:
		if track != excluded:
			next.append(track)
	var index := next.size() - 1
	while index > 0:
		var swap := int(_next_random() * float(index + 1))
		var held: Variant = next[index]
		next[index] = next[swap]
		next[swap] = held
		index -= 1
	# The shuffle may have put the last-played track back at the front, which is
	# the one order the policy forbids. Swap it with the first that differs.
	if _last != null and not next.is_empty() and String(next[0]) == String(_last):
		for position in range(next.size()):
			if String(next[position]) != String(_last):
				if position > 0:
					var first: Variant = next[0]
					next[0] = next[position]
					next[position] = first
				break
	_bag = next


## FNV-1a over a string, in thirty-two bits.
static func seed_from_string(value: String) -> int:
	var seed := FNV_OFFSET
	for code in value.to_utf8_buffer():
		seed = (seed ^ int(code)) & MASK
		seed = _mul32(seed, FNV_PRIME)
	return seed


## The browser's small generator, one draw on [0, 1).
func _next_random() -> float:
	_state = (_state + 0x6D2B79F5) & MASK
	var value := _state
	value = _mul32(value ^ (value >> 15), value | 1)
	value = (value ^ (value + _mul32(value ^ (value >> 7), value | 61))) & MASK
	return float((value ^ (value >> 14)) & MASK) / DIVISOR


## A thirty-two bit multiply that cannot overflow sixty-four.
##
## `a * b` with both near 2^32 is 2^64, which wraps in this engine and does not
## in the one the golden came from. Splitting the left operand at sixteen bits
## keeps every partial product inside the range and gives `Math.imul`'s answer.
static func _mul32(a: int, b: int) -> int:
	var low := a & 0xFFFF
	var high := (a >> 16) & 0xFFFF
	return ((low * b) + (((high * b) & 0xFFFF) << 16)) & MASK


## The catalog narrowed to a pool, in the catalog's own order. An empty pool is
## the whole catalog, which is what a genre that authors no place wants.
static func _resolve(catalog: PackedStringArray, pool: PackedStringArray) -> PackedStringArray:
	if pool.is_empty():
		return catalog
	var made := PackedStringArray()
	for track in catalog:
		if pool.has(track):
			made.append(track)
	return made

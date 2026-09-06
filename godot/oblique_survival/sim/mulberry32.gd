class_name Mulberry32
extends RefCounted

## The pipeline's PRNG, so one seed means the same thing on both sides.
##
## A verbatim port of the viewer's `mulberry32` (index.html:235). JavaScript's
## `>>>` and `Math.imul` are 32-bit operations on a 64-bit engine; here every
## intermediate is kept as an unsigned 32-bit value with an explicit mask, and
## the multiply is split into halves so nothing relies on 64-bit overflow.

const MASK := 0xFFFFFFFF
const DIVISOR := 4294967296.0

var _state: int = 0

## How many values this generator has produced. Nothing in the simulation
## reads it; it is the parity harness's cheapest divergence signal, because two
## runtimes that drew a different number of times have already parted company
## whatever their positions still say. Free to reset (`draws = 0`).
var draws: int = 0

func _init(seed_value: int = 0) -> void:
	_state = seed_value & MASK

## The next float in [0, 1).
func next() -> float:
	draws += 1
	_state = (_state + 0x6d2b79f5) & MASK
	var t: int = _state
	t = _imul(t ^ (t >> 15), t | 1)
	t = t ^ ((t + _imul(t ^ (t >> 7), t | 61)) & MASK)
	return float((t ^ (t >> 14)) & MASK) / DIVISOR

## What `next()` would return, without advancing the state or the count. A
## read-only window on the generator, for a digest that wants to compare the
## state itself rather than only how often it has been used.
func peek() -> float:
	var state: int = (_state + 0x6d2b79f5) & MASK
	var t: int = state
	t = _imul(t ^ (t >> 15), t | 1)
	t = t ^ ((t + _imul(t ^ (t >> 7), t | 61)) & MASK)
	return float((t ^ (t >> 14)) & MASK) / DIVISOR

## A Callable drawing from a fresh generator. The caller must keep the
## generator alive (a Callable holds no reference to its object), which is why
## `World` stores both `rng` and `rand`.
static func stream(seed_value: int) -> Array:
	var generator := Mulberry32.new(seed_value)
	return [generator, Callable(generator, "next")]

## `Math.imul`: a 32-bit multiply whose bit pattern is all that survives.
static func _imul(a: int, b: int) -> int:
	var low := (a & 0xFFFF) * b
	var high := ((a >> 16) * b) & 0xFFFF
	return (low + (high << 16)) & MASK

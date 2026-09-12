class_name KernelHash
extends RefCounted

## The two 32-bit mixers a replay digest depends on.
##
## Both are verbatim ports of `web/lib/kernel/hash.ts`. JavaScript's `Math.imul`
## and `>>>` are 32-bit operations on a 64-bit engine, so every intermediate here
## is masked explicitly and the multiply is split into halves — the same
## discipline `KernelRng` uses, and for the same reason: a hash that overflows
## differently is a different hash, and the divergence surfaces as a field that
## never matches rather than as an arithmetic error anyone can see.
##
## `fnv1a32` was written twice on the browser side — once here and once as
## `seedFromString` in the soundtrack's selector. It is one function and is
## ported once.

const MASK := 0xFFFFFFFF

## FNV-1a over a string's UTF-16 code units, which is what the browser hashed.
static func fnv1a32(value: String) -> int:
	var hash: int = 0x811c9dc5
	for index in value.length():
		hash = (hash ^ value.unicode_at(index)) & MASK
		hash = imul(hash, 0x01000193)
	return hash & MASK


## Mix two 32-bit values into a third, avalanching both.
static func mix32(a: int, b: int) -> int:
	var mixed: int = (a ^ b) & MASK
	mixed = imul(mixed ^ (mixed >> 16), 0x45d9f3b)
	mixed = imul(mixed ^ (mixed >> 16), 0x45d9f3b)
	return (mixed ^ (mixed >> 16)) & MASK


## `Math.imul`: a 32-bit multiply whose bit pattern is all that survives.
static func imul(a: int, b: int) -> int:
	var low := (a & 0xFFFF) * b
	var high := ((a >> 16) * b) & 0xFFFF
	return (low + (high << 16)) & MASK

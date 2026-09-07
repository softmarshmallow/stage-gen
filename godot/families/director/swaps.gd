class_name FamilySwapLedger
extends RefCounted

## Changes made for the duration of a set piece, and undone when it ends.
##
## A port of `web/lib/families/director/swaps.ts`. A boss fight swaps the
## runner's locomotion; when it ends the swap is reverted to whatever was
## standing before, not to a constant — so a fight that begins during another
## fight's swap cannot strand the world in a state nothing chose.
##
## Reverting happens in reverse order, which is what makes nesting safe.
##
## A ledger holds Callables, so it lives *beside* the world rather than in it: a
## slice that carried a closure would be a slice a digest cannot hash.

var _applied: Array = []


## Apply a swap unless one with that id is already standing. Returns whether it
## was applied, so a caller can tell "done" from "already done".
func apply(swap: Dictionary) -> bool:
	var id := String(swap.get("id", ""))
	for entry: Variant in _applied:
		if String((entry as Dictionary).get("id", "")) == id:
			return false
	var doer: Callable = swap["apply"]
	doer.call()
	_applied.append(swap)
	return true


func in_force(id: String) -> bool:
	for entry: Variant in _applied:
		if String((entry as Dictionary).get("id", "")) == id:
			return true
	return false


## Undo everything, newest first.
func revert_all() -> void:
	for index in range(_applied.size() - 1, -1, -1):
		var entry: Dictionary = _applied[index]
		var undoer: Callable = entry["revert"]
		undoer.call()
	_applied.clear()


func ids() -> PackedStringArray:
	var made := PackedStringArray()
	for entry: Variant in _applied:
		made.append(String((entry as Dictionary).get("id", "")))
	return made

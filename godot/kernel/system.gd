class_name KernelSystem
extends RefCounted

## What one system declares about itself, and nothing else.
##
## This is the runtime analogue of a generation node: a node declares what it
## reads and writes and the planner refuses an impossible graph before any
## spend; a system declares which world slices it reads and writes and
## `KernelSealer` refuses an impossible frame before any tick. The order the
## sealer derives is data — inspectable, assertable, and a consequence of the
## declarations rather than of the order somebody happened to register in.
##
## A system is a script, never an instance: `static func declaration()` returns
## one of these and `static func update(world, step)` does the work. GDScript
## has no interfaces, so the sealer checks the two methods are there and refuses
## by name when they are not, which is the same refusal an unimplemented
## interface would have been.
##
## **`reads` and `writes` are same-frame dataflow.** A system that consumes a
## slice another system wrote *this frame* declares the read, and sealing puts
## every writer of a slice before every reader of it. A feedback read — last
## frame's value, the way a difficulty ramp samples the distance the avatar
## wrote a frame ago — is deliberately not declared, because declaring it would
## assert an ordering no loop can satisfy. Where feedback still needs a
## definite position, `after` carries the edge and says so. A read declared to
## buy an ordering edge is a lie the next reader of the file believes.
##
## **`owns` is the authority channel.** A slice with an owner has exactly one
## author, refused at seal rather than discovered when two systems disagree
## about what is in it. `writes` without `owns` is the weaker claim: this system
## writes here, and so may others.
##
## **`emits` and `consumes` carry occurrences rather than state.** They order
## exactly the way reads and writes do — every emitter of a type before every
## consumer of it — and refuse exactly the way they do, so a queue is not an
## escape from sealing: an event loop is still a cycle and still fails at seal
## time. `consumes_deferred` is the event channel's feedback read: the
## occurrence is heard on the frame after it is emitted, so it constrains
## nothing about this frame's order and cannot close a cycle. It is how a system
## sealed *before* an emitter hears it at all.

## Stable identity, `<family>/<verb>` or `<genre>/<verb>` — "vitals/drain",
## "runner/avatar", "survival/interact".
var id: String = ""
## The version of this system's world contract, e.g. "vitals-system-v1".
var contract_version: String = ""
## Slices read this frame, after every writer of them has run.
var reads: PackedStringArray = PackedStringArray()
## Slices written. Shared unless also owned.
var writes: PackedStringArray = PackedStringArray()
## Slices this system is the sole author of.
var owns: PackedStringArray = PackedStringArray()
## Event types this system may append to the frame queue.
var emits: PackedStringArray = PackedStringArray()
## Event types this system reads out of this frame's queue.
var consumes: PackedStringArray = PackedStringArray()
## Event types this system reads out of the previous frame's queue.
var consumes_deferred: PackedStringArray = PackedStringArray()
## Explicit edges, for where reads and writes underdetermine the order.
var after: PackedStringArray = PackedStringArray()
## The script that carries `update` and, optionally, `reset`. Set by the sealer
## from the roster, so a declaration never has to name its own file. Not called
## `script`: that is a member of every Object and cannot be shadowed.
var handler: GDScript = null


## Build a declaration from a dictionary, so a system's own `declaration()` reads
## as a table rather than as eight assignments. Every key is optional but `id`
## and `contract_version`.
static func of(fields: Dictionary) -> KernelSystem:
	var made := KernelSystem.new()
	made.id = String(fields.get("id", ""))
	made.contract_version = String(fields.get("contract_version", ""))
	made.reads = _words(fields.get("reads", []))
	made.writes = _words(fields.get("writes", []))
	made.owns = _words(fields.get("owns", []))
	made.emits = _words(fields.get("emits", []))
	made.consumes = _words(fields.get("consumes", []))
	made.consumes_deferred = _words(fields.get("consumes_deferred", []))
	made.after = _words(fields.get("after", []))
	return made


## Everything this system may write: what it owns, plus what it shares.
func authority() -> PackedStringArray:
	var all := PackedStringArray()
	for slice in writes:
		if not all.has(slice):
			all.append(slice)
	for slice in owns:
		if not all.has(slice):
			all.append(slice)
	return all


static func _words(value: Variant) -> PackedStringArray:
	var made := PackedStringArray()
	if value is PackedStringArray:
		return (value as PackedStringArray).duplicate()
	if value is Array:
		for entry: Variant in value:
			made.append(String(entry))
	return made

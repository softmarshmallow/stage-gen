class_name FamilyEffects
extends RefCounted

## The operations an authored outcome may perform, and the handlers that answer
## them.
##
## A port of `web/lib/families/effects/vocabulary.ts`. Sealing a vocabulary is
## what turns "this room authored an operation nothing implements" from an
## effect that quietly does nothing into a refusal somebody sees.
##
## **Order is the caller's and it is load-bearing.** An outcome that grants an
## item and then completes a quest counting it is a different outcome from the
## same two the other way round.


## Check every declared operation has a handler and every handler answers a
## declared operation. Returns the sealed vocabulary or a `KernelRefusal`.
static func seal(operations: PackedStringArray, handlers: Dictionary) -> Variant:
	for operation in operations:
		if not handlers.has(operation):
			return KernelRefusal.of(
				"effects/vocabulary",
				"effect operation \"%s\" is declared with no handler" % operation,
				operation
			)
	for key: Variant in handlers:
		var name := String(key)
		if not operations.has(name):
			return KernelRefusal.of(
				"effects/vocabulary",
				"effect handler \"%s\" answers an operation nothing declares" % name,
				name
			)
	return {"operations": operations.duplicate(), "handlers": handlers}


## Perform lowered operations in order, reporting what was performed.
##
## `lowered` is an array of `{operation, payload}`. An operation the vocabulary
## does not carry is skipped rather than refused: closure is the package
## validator's job, and a runtime that refused here would turn a producer's
## mistake into a crash in the middle of a conversation.
static func apply(vocabulary: Dictionary, lowered: Array) -> PackedStringArray:
	var applied := PackedStringArray()
	var handlers: Dictionary = vocabulary["handlers"]
	for entry: Variant in lowered:
		var step: Dictionary = entry
		var operation := String(step["operation"])
		if not handlers.has(operation):
			continue
		var handler: Callable = handlers[operation]
		handler.call(step["payload"])
		applied.append(operation)
	return applied


## Resolve authored effect ids against a table, in the order they were named.
##
## An id that does not resolve is skipped, for the same reason.
static func resolve(table: Array, effect_ids: PackedStringArray, id_key: String) -> Array:
	var resolved: Array = []
	for effect_id in effect_ids:
		for entry: Variant in table:
			if String((entry as Dictionary).get(id_key, "")) == effect_id:
				resolved.append(entry)
				break
	return resolved

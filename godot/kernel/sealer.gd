class_name KernelSealer
extends RefCounted

## Order a roster of systems, or refuse it, before the first frame.
##
## The order is Kahn's algorithm over writes-before-reads plus emits-before-
## consumes plus `after` edges, with registration order breaking every tie — so
## the result is total, deterministic, and stable under edits that do not change
## the declarations. It is exposed as data (`KernelSealed.order`) so a genre can
## assert its frame order rather than trust it.
##
## Seven refusals, all at seal time, exactly the way the generation graph refuses
## at plan time. A duplicate id, two owners of one slice, a write into a slice
## another system owns, an `after` edge naming a system that is not registered,
## a consumed occurrence nothing emits, an event-declaring roster with no queue
## (or a queue no system uses), and a dependency cycle are programming errors
## that no amount of ticking recovers from, so none of them reaches a frame.
##
## GDScript has no exceptions, so a refusal is a value: `seal` returns either a
## `KernelSealed` or a `KernelRefusal`, and never a half-ordered roster.

## The one refusal code family this module reports under.
const CODE_DUPLICATE := "kernel/duplicate-system"
const CODE_OWNERSHIP := "kernel/ownership-conflict"
const CODE_UNEMITTED := "kernel/unemitted-event"
const CODE_UNKNOWN := "kernel/unknown-system"
const CODE_CYCLE := "kernel/cycle"
const CODE_EVENTS := "kernel/event-accessor"
const CODE_CONTRACT := "kernel/system-contract"


## Seal a roster. `scripts` is the roster in registration order: each entry is a
## `GDScript` carrying `static func declaration() -> KernelSystem` and
## `static func update(world, step)`. `has_events` says whether the world the
## roster will tick carries a frame queue.
static func seal(scripts: Array, has_events: bool = false) -> Variant:
	var declared: Array[KernelSystem] = []
	var by_id: Dictionary = {}
	for entry: Variant in scripts:
		if not (entry is GDScript):
			return KernelRefusal.of(CODE_CONTRACT, "a roster entry is not a script", "")
		var script := entry as GDScript
		if not script.has_method("declaration"):
			return KernelRefusal.of(
				CODE_CONTRACT,
				"a roster entry has no `static func declaration() -> KernelSystem`",
				script.resource_path,
			)
		if not script.has_method("update"):
			return KernelRefusal.of(
				CODE_CONTRACT,
				"a roster entry has no `static func update(world, step)`",
				script.resource_path,
			)
		var declaration: Variant = script.call("declaration")
		if not (declaration is KernelSystem):
			return KernelRefusal.of(
				CODE_CONTRACT, "declaration() did not return a KernelSystem", script.resource_path
			)
		var system := declaration as KernelSystem
		system.handler = script
		if by_id.has(system.id):
			return KernelRefusal.of(
				CODE_DUPLICATE, "two systems share the id %s" % system.id, system.id
			)
		by_id[system.id] = system
		declared.append(system)

	var uses_events := false
	for system in declared:
		if not system.emits.is_empty() or not system.consumes.is_empty() \
				or not system.consumes_deferred.is_empty():
			uses_events = true
			break
	if uses_events and not has_events:
		return KernelRefusal.of(
			CODE_EVENTS,
			"systems declare events but the world carries no frame queue: "
			+ "a channel with nothing to clear it leaks the whole run into one array",
			"",
		)
	if not uses_events and has_events:
		return KernelRefusal.of(
			CODE_EVENTS,
			"the world carries a frame queue no system uses: declare emits/consumes or drop it",
			"",
		)

	# Ownership first: it is the claim every other declaration is checked
	# against, and a slice with two authors has no order worth deriving.
	var owner_by_slice: Dictionary = {}
	for system in declared:
		for slice in system.owns:
			if owner_by_slice.has(slice):
				return KernelRefusal.of(
					CODE_OWNERSHIP,
					"two owners of %s: %s and %s both declare it. One slice, one author — "
					% [slice, owner_by_slice[slice], system.id]
					+ "the second asks the first for the change through an event",
					slice,
				)
			owner_by_slice[slice] = system.id
	for system in declared:
		for slice in system.writes:
			var owner: Variant = owner_by_slice.get(slice)
			if owner != null and String(owner) != system.id:
				return KernelRefusal.of(
					CODE_OWNERSHIP,
					"%s writes %s, which %s owns. Ask the owner through an event it consumes"
					% [system.id, slice, owner],
					slice,
				)

	var ids := PackedStringArray()
	for system in declared:
		ids.append(system.id)
	var edges: Dictionary = {}
	for id in ids:
		edges[id] = PackedStringArray()
	var writers_by_slice: Dictionary = {}
	var emitters_by_type: Dictionary = {}
	for system in declared:
		for slice in system.authority():
			var writers: PackedStringArray = writers_by_slice.get(slice, PackedStringArray())
			writers.append(system.id)
			writers_by_slice[slice] = writers
		for type in system.emits:
			var emitters: PackedStringArray = emitters_by_type.get(type, PackedStringArray())
			emitters.append(system.id)
			emitters_by_type[type] = emitters

	for system in declared:
		for slice in system.reads:
			for writer in writers_by_slice.get(slice, PackedStringArray()) as PackedStringArray:
				if writer != system.id:
					_add_edge(edges, writer, system.id)
		for type in system.consumes:
			if not emitters_by_type.has(type):
				return KernelRefusal.of(
					CODE_UNEMITTED,
					"%s consumes %s, which no system emits" % [system.id, type],
					type,
				)
			for emitter in emitters_by_type[type] as PackedStringArray:
				if emitter != system.id:
					_add_edge(edges, emitter, system.id)
		# A deferred consume is last frame's occurrence: it constrains nothing
		# about this frame's order, which is exactly why it cannot close a
		# cycle, and it needs no emitter. An in-frame consume with no emitter is
		# a channel with no other end and a defect; a deferred one is a mailbox,
		# and an empty mailbox is not.
		for dependency in system.after:
			if not by_id.has(dependency):
				return KernelRefusal.of(
					CODE_UNKNOWN,
					"%s has an after edge naming unregistered %s" % [system.id, dependency],
					dependency,
				)
			if dependency != system.id:
				_add_edge(edges, dependency, system.id)

	var indegree: Dictionary = {}
	for id in ids:
		indegree[id] = 0
	for from: String in edges:
		for to in edges[from] as PackedStringArray:
			indegree[to] = int(indegree[to]) + 1

	var order := PackedStringArray()
	var emitted: Dictionary = {}
	while order.size() < ids.size():
		# Registration order breaks ties: scan for the first ready system.
		var ready := ""
		for id in ids:
			if not emitted.has(id) and int(indegree[id]) == 0:
				ready = id
				break
		if ready == "":
			var remaining := PackedStringArray()
			for id in ids:
				if not emitted.has(id):
					remaining.append(id)
			return KernelRefusal.of(
				CODE_CYCLE,
				"a dependency cycle among %s: break it with an explicit after edge "
				% ", ".join(remaining)
				+ "or a narrower reads/writes declaration",
				"",
			)
		emitted[ready] = true
		order.append(ready)
		for to in edges[ready] as PackedStringArray:
			indegree[to] = int(indegree[to]) - 1

	var sequence: Array[KernelSystem] = []
	for id in order:
		sequence.append(by_id[id])
	return KernelSealed.of(order, sequence)


static func _add_edge(edges: Dictionary, from: String, to: String) -> void:
	var targets: PackedStringArray = edges[from]
	if not targets.has(to):
		targets.append(to)
		edges[from] = targets

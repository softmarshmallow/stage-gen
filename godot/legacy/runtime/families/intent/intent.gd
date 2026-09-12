class_name FamilyIntent
extends RefCounted

## What the player asked for this step, sampled once.
##
## A port of `web/lib/families/intent/intent.ts`. An intent has two kinds of
## key and the difference is the whole point:
##
## - an **edge** is a request. It is spent by the sample that reports it and is
##   gone whether or not anything acted on it. A jump is an edge.
## - a **level** is a condition. It is true for as long as it is held. A duck is
##   a level.
##
## Declaring which is which is what stops a held key re-firing a one-shot verb,
## and it is the defect a panel button reintroduced on the survival host: a
## button that latched a key as held stopped the keyboard being read at all.
##
## `sample_held` is the sample taken while the world is frozen: levels are
## reported, edges are **spent and reported unasked**. A jump pressed under a
## cut-in is discarded rather than queued, so the world does not lurch into a
## jump the moment the picture clears.


var _edges: PackedStringArray = PackedStringArray()
var _levels: PackedStringArray = PackedStringArray()
var _neutral: Dictionary = {}
var _pending: Dictionary = {}
var _held: Dictionary = {}


## Declare the shape. Every key of `neutral` must be named exactly once across
## `edges` and `levels`; the refusal is returned rather than thrown, because a
## genre's shape is checked at boot and a boot refusal is a value like any other.
static func of(
	neutral: Dictionary, edges: PackedStringArray, levels: PackedStringArray
) -> Variant:
	for key in edges:
		if levels.has(key):
			return KernelRefusal.of(
				"intent/shape",
				"intent key \"%s\" is declared as both an edge and a level" % key
			)
	for key: Variant in neutral:
		var name := String(key)
		if not edges.has(name) and not levels.has(name):
			return KernelRefusal.of(
				"intent/shape",
				(
					"intent key \"%s\" is declared as neither an edge nor a level: a request "
					+ "nothing spends and a condition nothing holds are the same defect"
				) % name
			)
	for key in edges + levels:
		if not neutral.has(key):
			return KernelRefusal.of(
				"intent/shape",
				"intent declares \"%s\", which the record does not carry" % key
			)
	var made := FamilyIntent.new()
	made._neutral = neutral.duplicate()
	made._edges = edges.duplicate()
	made._levels = levels.duplicate()
	return made


## Ask for an edge. Setting one is a defect and is refused by name.
func request(key: String) -> void:
	if not _edges.has(key):
		push_error("\"%s\" is a level; set it rather than requesting it" % key)
		return
	_pending[key] = true


## Hold or release a level. Requesting one is a defect and is refused by name.
func set_level(key: String, value: bool) -> void:
	if not _levels.has(key):
		push_error("\"%s\" is an edge; request it rather than setting it" % key)
		return
	_held[key] = value


## The intent for a step that runs: levels, plus the edges asked for since the
## last sample.
func sample() -> Dictionary:
	return _build(true)


## The intent for a step the world is frozen for: levels only, and the edges are
## spent all the same.
func sample_held() -> Dictionary:
	return _build(false)


func reset() -> void:
	_pending.clear()
	_held.clear()


func _build(with_edges: bool) -> Dictionary:
	var made := _neutral.duplicate()
	for key: Variant in _held:
		made[key] = _held[key]
	if with_edges:
		for key: Variant in _pending:
			made[key] = _pending[key]
	_pending.clear()
	return made

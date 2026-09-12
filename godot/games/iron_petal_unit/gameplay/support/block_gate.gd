class_name FamilyBlockGate
extends RefCounted

## The one seam between a document and the code that reads it.
##
## A port of `web/lib/families/block-gate.ts` and `web/lib/manifest/blocks.ts`.
## A manifest publishes a `blocks` table naming, per block, the version it was
## written at. A family states the version it reads. A mismatch is refused by
## name before anything is drawn, which is the difference between "this build
## plays a different game from the one the run describes" and "this build says
## so".
##
## An **optional** block may be absent — the fx block is, for a package with no
## cut-ins — but a block that is present at the wrong version is refused even
## when it is optional. Absence is a choice; a wrong version is a mistake.


## Returns `{version, published}` or a `KernelRefusal`.
static func gate(blocks: Variant, block: String, version: String, optional: bool) -> Variant:
	if not (blocks is Dictionary):
		return KernelRefusal.of(
			"manifest/blocks",
			"manifest blocks table is missing; this build reads per-block versions"
		)
	var table: Dictionary = blocks
	if not table.has(block):
		if optional:
			return {"version": null, "published": false}
		return KernelRefusal.of(
			"manifest/block",
			"manifest block \"%s\" is not published; this build reads %s" % [block, version],
			block
		)
	var found: Variant = table[block]
	if not (found is String) or String(found).is_empty():
		return KernelRefusal.of(
			"manifest/block",
			"manifest block \"%s\" declares an invalid version" % block,
			block
		)
	if String(found) != version:
		return KernelRefusal.of(
			"manifest/block",
			(
				"manifest block \"%s\" is published as %s; this build reads %s"
				% [block, String(found), version]
			),
			block
		)
	return {"version": version, "published": true}


## Gate several in order; the first mismatch is the refusal. Returns an Array of
## the gated views, or a `KernelRefusal`.
static func gate_all(blocks: Variant, bindings: Array) -> Variant:
	var views: Array = []
	for binding: Variant in bindings:
		var entry: Dictionary = binding
		var view: Variant = gate(
			blocks,
			String(entry["block"]),
			String(entry["version"]),
			bool(entry.get("optional", false))
		)
		if KernelRefusal.is_refusal(view):
			return view
		views.append(view)
	return views

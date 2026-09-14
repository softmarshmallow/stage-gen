extends RefCounted
## The ledger document: one player's balances, level tracks, source records, a capped entry log and
## the mailbox, as a plain dictionary the host persists as JSON. Static functions over that document:
## create one, validate one that came back from disk, grant or spend a concrete bundle atomically.
## Balances are counts by item id and nothing more: no slots, no equipment, no weight. Whether the
## game shows them as money, a bag or a stash is the game's inventory, not this ledger's business.

const SCHEMA_VERSION := 2
const ENTRIES_CAP := 200
const MAIL_CAP := 100


static func create(now: int) -> Dictionary:
	return {
		"schema_version": SCHEMA_VERSION,
		"created_at": now,
		"balances": {},
		"tracks": {},
		"records": {},
		"entries": [],
		"mail": [],
		"mail_seq": 0,
		"delivered_once": [],
	}


static func validate(doc: Variant) -> Array[String]:
	var errors: Array[String] = []
	if not doc is Dictionary:
		return ["The ledger must be a dictionary"]
	if int(doc.get("schema_version", 0)) != SCHEMA_VERSION:
		return ["The ledger declares schema_version %s, this package reads %d" % [str(doc.get("schema_version", "none")), SCHEMA_VERSION]]
	for field in ["created_at", "mail_seq"]:
		if not _whole(doc.get(field, null)) or int(doc.get(field, -1)) < 0:
			errors.append("The ledger field %s must be a whole number of zero or more" % field)
	for table in ["balances", "tracks", "records"]:
		if not doc.get(table, null) is Dictionary:
			errors.append("The ledger field %s must be a dictionary" % table)
	for list in ["entries", "mail", "delivered_once"]:
		if not doc.get(list, null) is Array:
			errors.append("The ledger field %s must be a list" % list)
	if not errors.is_empty():
		return errors
	for id: Variant in doc["balances"]:
		if not _whole(doc["balances"][id]) or int(doc["balances"][id]) < 0:
			errors.append("The ledger holds a bad balance for %s" % id)
	for name: Variant in doc["tracks"]:
		var track: Variant = doc["tracks"][name]
		if not track is Dictionary or not _whole(track.get("level", null)) or int(track.get("level", 0)) < 1 or not _whole(track.get("exp", null)) or int(track.get("exp", -1)) < 0:
			errors.append("The ledger track %s is malformed" % name)
	for id: Variant in doc["records"]:
		var record: Variant = doc["records"][id]
		if not record is Dictionary or not _whole(record.get("claims", null)) or int(record.get("claims", -1)) < 0:
			errors.append("The ledger record %s is malformed" % id)
	for mail: Variant in doc["mail"]:
		if not mail is Dictionary or not _whole(mail.get("id", null)) or not mail.get("attachments", null) is Array:
			errors.append("The ledger holds a malformed mail")
	return errors


static func balance(doc: Dictionary, id: String) -> int:
	return int(doc["balances"].get(id, 0))


static func grant(doc: Dictionary, catalog: RefCounted, bundle: Array, source: String, now: int) -> Dictionary:
	## Adds a concrete bundle. Returns {granted, lost, errors}: `lost` is what a stack limit refused,
	## so a claim never silently drops part of itself. A bundle with an unresolved table is refused whole.
	if not catalog.is_concrete(bundle):
		return {"granted": [], "lost": [], "errors": ["A bundle with a table must be resolved before it is granted"]}
	var granted: Array = []
	var lost: Array = []
	for entry: Dictionary in catalog.merge([bundle]):
		var id := String(entry["item"])
		var spec: Dictionary = catalog.item(id)
		if spec.is_empty():
			return {"granted": [], "lost": [], "errors": ["Unknown item: " + id]}
		var have := balance(doc, id)
		var room := maxi(int(spec["stack"]) - have, 0)
		var added := mini(int(entry["count"]), room)
		if added > 0:
			doc["balances"][id] = have + added
			granted.append({"item": id, "count": added})
		if added < int(entry["count"]):
			lost.append({"item": id, "count": int(entry["count"]) - added})
	if not granted.is_empty():
		_entry(doc, "grant", source, granted, now)
	return {"granted": granted, "lost": lost, "errors": []}


static func spend(doc: Dictionary, catalog: RefCounted, bundle: Array, source: String, now: int) -> Dictionary:
	## Removes a concrete bundle, all or nothing. Returns {spent, shortfall, errors}: with any shortfall
	## nothing moves and `shortfall` says what was missing per item.
	if not catalog.is_concrete(bundle):
		return {"spent": [], "shortfall": [], "errors": ["A bundle with a table cannot be spent"]}
	var wanted: Array = catalog.merge([bundle])
	var shortfall: Array = []
	for entry: Dictionary in wanted:
		var id := String(entry["item"])
		if catalog.item(id).is_empty():
			return {"spent": [], "shortfall": [], "errors": ["Unknown item: " + id]}
		var missing := int(entry["count"]) - balance(doc, id)
		if missing > 0:
			shortfall.append({"item": id, "count": missing})
	if not shortfall.is_empty():
		return {"spent": [], "shortfall": shortfall, "errors": []}
	for entry: Dictionary in wanted:
		doc["balances"][String(entry["item"])] = balance(doc, String(entry["item"])) - int(entry["count"])
	_entry(doc, "spend", source, wanted, now)
	return {"spent": wanted, "shortfall": [], "errors": []}


static func entries(doc: Dictionary, kind: String = "") -> Array:
	## The log, newest first; `kind` filters to grant or spend.
	var out: Array = []
	for i in range(doc["entries"].size() - 1, -1, -1):
		var entry: Dictionary = doc["entries"][i]
		if kind == "" or String(entry["kind"]) == kind:
			out.append(entry)
	return out


static func _entry(doc: Dictionary, kind: String, source: String, items: Array, now: int) -> void:
	doc["entries"].append({"at": now, "kind": kind, "source": source, "items": items.duplicate(true)})
	while doc["entries"].size() > ENTRIES_CAP:
		doc["entries"].remove_at(0)


static func _whole(value: Variant) -> bool:
	return value is int or (value is float and value == floorf(value))

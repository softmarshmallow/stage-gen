extends RefCounted
## Code authoring of a design: the same dictionary a JSON design parses to, built by calls. A game
## that prefers code to files, or that computes part of its design, uses this and hands build() to
## design/catalog.gd; the validation is the catalog's, not this builder's. Every method returns the
## builder so calls chain. Not a node, not a resource: no engine involved.

var _design := {"schema_version": 2, "items": {}, "curves": {}, "measurements": {}, "tables": {}, "sources": {}, "mails": {}}


func item(id: String, type: String, rarity: String, stack: int, name_key: String) -> RefCounted:
	_design["items"][id] = {"type": type, "rarity": rarity, "stack": stack, "name_key": name_key}
	return self


func curve(name: String, steps: Array) -> RefCounted:
	_design["curves"][name] = steps.duplicate()
	return self


func measurement(name: String, type: String) -> RefCounted:
	_design["measurements"][name] = type
	return self


func table(id: String, entries: Array) -> RefCounted:
	## entries: [{item, count, weight}, ...]
	_design["tables"][id] = entries.duplicate(true)
	return self


func source(id: String, trigger: String, claims: String, name_key: String, bundle: Array, options: Dictionary = {}) -> RefCounted:
	## options: exp {curve, amount}, objectives [objective()], objective_bonus {"N": bundle}, period_s,
	## mail_on_claim.
	var spec := {"trigger": trigger, "claims": claims, "name_key": name_key, "bundle": bundle.duplicate(true)}
	for field in ["exp", "objectives", "objective_bonus", "period_s", "mail_on_claim"]:
		if options.has(field):
			spec[field] = options[field].duplicate(true) if options[field] is Dictionary or options[field] is Array else options[field]
	_design["sources"][id] = spec
	return self


static func objective(name_key: String, kind: String, measure: String = "", value: Variant = null) -> Dictionary:
	var condition := {"kind": kind}
	if measure != "":
		condition["measure"] = measure
	if value != null:
		condition["value"] = value
	return {"name_key": name_key, "condition": condition}


func mail(id: String, sender_key: String, title_key: String, body_key: String, attachments: Array, expires_days: Variant = null) -> RefCounted:
	_design["mails"][id] = {"sender_key": sender_key, "title_key": title_key, "body_key": body_key, "attachments": attachments.duplicate(true), "expires_days": expires_days}
	return self


func build() -> Dictionary:
	return _design.duplicate(true)

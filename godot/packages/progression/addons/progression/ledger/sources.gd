extends RefCounted
## Triggers into claims. The game reports a trigger ("stage:arena", "login") with the measurements it
## promised; every source listening to that trigger answers whether it can be claimed (once ever,
## every time, or once per period), which objectives the report met, and what it would pay. claim()
## then resolves the tables, grants, adds the EXP per curve, delivers the sources' mails and writes
## the records, in that order, or writes nothing when any step refuses. Pure and static over the
## ledger document; randomness only through the host's `draw` callable.

const CATALOG := preload("../design/catalog.gd")
const TABLES := preload("../design/tables.gd")
const LEDGER := preload("ledger.gd")
const LEVELS := preload("levels.gd")
const CONDITIONS := preload("conditions.gd")
const MAILBOX := preload("mailbox.gd")


static func record(doc: Dictionary, id: String) -> Dictionary:
	## The source's record, created empty on first sight (a reference into the document).
	if not doc["records"].has(id):
		doc["records"][id] = {"claims": 0, "first_claimed_at": null, "last_claimed_at": null, "best_met": 0}
	return doc["records"][id]


static func can_claim(doc: Dictionary, catalog: RefCounted, id: String, now: int) -> Dictionary:
	## {ok, reason, next_at}: reason is "" | "unknown_source" | "already_claimed" | "period_not_elapsed".
	var spec: Dictionary = catalog.source(id)
	if spec.is_empty():
		return {"ok": false, "reason": "unknown_source", "next_at": null}
	var existing: Dictionary = doc["records"].get(id, {})
	var claims := int(existing.get("claims", 0))
	match String(spec["claims"]):
		"once":
			return {"ok": claims == 0, "reason": "" if claims == 0 else "already_claimed", "next_at": null}
		"periodic":
			var last: Variant = existing.get("last_claimed_at", null)
			if last == null:
				return {"ok": true, "reason": "", "next_at": null}
			var next_at := int(last) + int(spec["period_s"])
			return {"ok": now >= next_at, "reason": "" if now >= next_at else "period_not_elapsed", "next_at": next_at}
	return {"ok": true, "reason": "", "next_at": null}


static func preview(doc: Dictionary, catalog: RefCounted, trigger: String, measurements: Dictionary, now: int) -> Dictionary:
	## What a report would claim, before anything is written. Returns {rows, errors}; a row is
	## {id, name_key, claims, claimable, reason, next_at, bundle, objectives: [{name_key, condition, met}],
	## objectives_met, bonus, exp: {curve, amount}, mail_on_claim, record}. A trigger no source listens
	## to is an error: the game reported something its design never named.
	var rows: Array = []
	var errors: Array[String] = []
	var ids: Array = catalog.sources_for(trigger)
	if ids.is_empty():
		return {"rows": rows, "errors": ["No source listens to the trigger " + trigger]}
	for id: String in ids:
		var spec: Dictionary = catalog.source(id)
		var allowed := can_claim(doc, catalog, id, now)
		var scored: Dictionary = CONDITIONS.objectives_met(spec["objectives"], measurements, catalog)
		errors.append_array(scored["errors"])
		var objectives: Array = []
		for i in spec["objectives"].size():
			objectives.append({"name_key": spec["objectives"][i]["name_key"], "condition": spec["objectives"][i]["condition"], "met": bool(scored["met"][i])})
		var bonus: Array = []
		for count: int in spec["objective_bonus"]:
			if int(scored["count"]) >= count:
				bonus = CATALOG.merge([bonus, spec["objective_bonus"][count]])
		rows.append({
			"id": id,
			"name_key": spec["name_key"],
			"claims": spec["claims"],
			"claimable": bool(allowed["ok"]),
			"reason": allowed["reason"],
			"next_at": allowed["next_at"],
			"bundle": spec["bundle"].duplicate(true),
			"objectives": objectives,
			"objectives_met": int(scored["count"]),
			"bonus": bonus,
			"exp": spec["exp"].duplicate(),
			"mail_on_claim": spec["mail_on_claim"],
			"record": doc["records"].get(id, {}).duplicate(),
		})
	return {"rows": rows, "errors": errors}


static func claim(doc: Dictionary, catalog: RefCounted, trigger: String, measurements: Dictionary, now: int, draw: Callable = Callable()) -> Dictionary:
	## Claims every claimable source of the trigger. Returns {claimed: [ids], granted, lost, exp: [per
	## curve {track, level_before, exp_before, level, exp, level_ups}], mails: [mail ids sent], rows,
	## errors}. Every table is rolled and every refusal found before the first write.
	var seen := preview(doc, catalog, trigger, measurements, now)
	if not seen["errors"].is_empty():
		return {"claimed": [], "granted": [], "lost": [], "exp": [], "mails": [], "rows": seen["rows"], "errors": seen["errors"]}
	var resolved: Array = []   # [row, concrete bundle]
	var errors: Array[String] = []
	for row: Dictionary in seen["rows"]:
		if not bool(row["claimable"]):
			continue
		var whole: Dictionary = TABLES.resolve(CATALOG.merge([row["bundle"], row["bonus"]]), catalog, draw)
		errors.append_array(whole["errors"])
		resolved.append([row, whole["bundle"]])
	if not errors.is_empty():
		return {"claimed": [], "granted": [], "lost": [], "exp": [], "mails": [], "rows": seen["rows"], "errors": errors}
	var claimed: Array = []
	var granted: Array = []
	var lost: Array = []
	var exp_by_curve := {}
	var mails: Array = []
	for pair: Array in resolved:
		var row: Dictionary = pair[0]
		var outcome: Dictionary = LEDGER.grant(doc, catalog, pair[1], String(row["id"]), now)
		granted = CATALOG.merge([granted, outcome["granted"]])
		lost = CATALOG.merge([lost, outcome["lost"]])
		var rec := record(doc, String(row["id"]))
		rec["claims"] = int(rec["claims"]) + 1
		if rec["first_claimed_at"] == null:
			rec["first_claimed_at"] = now
		rec["last_claimed_at"] = now
		rec["best_met"] = maxi(int(rec["best_met"]), int(row["objectives_met"]))
		if not row["exp"].is_empty():
			var curve := String(row["exp"]["curve"])
			exp_by_curve[curve] = int(exp_by_curve.get(curve, 0)) + int(row["exp"]["amount"])
		if String(row["mail_on_claim"]) != "":
			var sent: Dictionary = MAILBOX.deliver(doc, catalog, String(row["mail_on_claim"]), now)
			if sent["errors"].is_empty():
				mails.append(int(sent["mail"]["id"]))
		claimed.append(String(row["id"]))
	var exp_results: Array = []
	for curve: String in exp_by_curve:
		exp_results.append(LEVELS.add_exp(doc, catalog, curve, int(exp_by_curve[curve])))
	return {"claimed": claimed, "granted": granted, "lost": lost, "exp": exp_results, "mails": mails, "rows": seen["rows"], "errors": []}

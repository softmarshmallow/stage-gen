extends SceneTree
## Progression package checks: the design half over literal tables (and the builder), the ledger half
## over the document, and the store over a scratch path. Offline, no scene, no media.

const CATALOG := preload("res://addons/progression/design/catalog.gd")
const BUILDER := preload("res://addons/progression/design/builder.gd")
const TABLES := preload("res://addons/progression/design/tables.gd")
const LEDGER := preload("res://addons/progression/ledger/ledger.gd")
const LEVELS := preload("res://addons/progression/ledger/levels.gd")
const CONDITIONS := preload("res://addons/progression/ledger/conditions.gd")
const SOURCES := preload("res://addons/progression/ledger/sources.gd")
const MAILBOX := preload("res://addons/progression/ledger/mailbox.gd")
const STORE := preload("res://addons/progression/store.gd")

const DAY := 86400
const KEYS := ["n.gold", "n.gem", "n.core", "r.first", "r.clear", "r.daily", "r.hp", "o.cleared", "o.fast", "o.clean", "o.hp",
	"s.v", "m.w.t", "m.w.b", "m.t.t", "m.t.b", "m.n.t", "m.n.b"]

var _errors: Array[String] = []
var _checks := 0


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	_design_refusals()
	_builder_matches_json()
	_tables()
	_ledger_grant_spend()
	_levels()
	_conditions()
	_sources_lifecycle()
	_mail()
	_store()
	for issue in _errors:
		printerr("FAIL progression: " + issue)
	if _errors.is_empty():
		print("progression: %d checks passed" % _checks)
	quit(0 if _errors.is_empty() else 1)


func _expect(condition: bool, message: String) -> void:
	_checks += 1
	if not condition:
		_errors.append(message)


func _design() -> Dictionary:
	return {
		"schema_version": 2,
		"items": {
			"gold": {"type": "currency", "rarity": "common", "stack": 1000, "name_key": "n.gold"},
			"gem": {"type": "currency", "rarity": "rare", "stack": 100, "name_key": "n.gem"},
			"core": {"type": "material", "rarity": "epic", "stack": 2, "name_key": "n.core"},
		},
		"curves": {"account": [100, 150, 200]},
		"measurements": {"fight_s": "number", "hits_taken": "integer", "hp_fraction": "number", "died": "boolean"},
		"tables": {"drops": [{"item": "gem", "count": 5, "weight": 70}, {"item": "core", "count": 1, "weight": 30}]},
		"sources": {
			"boss.first": {"trigger": "stage:boss", "claims": "once", "name_key": "r.first",
				"bundle": [{"item": "gem", "count": 60}, {"item": "core", "count": 1}], "mail_on_claim": "thanks"},
			"boss.clear": {"trigger": "stage:boss", "claims": "repeat", "name_key": "r.clear",
				"bundle": [{"item": "gold", "count": 150}, {"table": "drops", "rolls": 2}],
				"exp": {"curve": "account", "amount": 120},
				"objectives": [
					{"name_key": "o.cleared", "condition": {"kind": "always"}},
					{"name_key": "o.fast", "condition": {"kind": "below", "measure": "fight_s", "value": 120}},
					{"name_key": "o.clean", "condition": {"kind": "at_most", "measure": "hits_taken", "value": 3}}],
				"objective_bonus": {"3": [{"item": "core", "count": 1}]}},
			"daily": {"trigger": "login", "claims": "periodic", "period_s": DAY, "name_key": "r.daily", "bundle": [{"item": "gold", "count": 50}]},
			"hp_stage": {"trigger": "stage:hp", "claims": "repeat", "name_key": "r.hp", "bundle": [],
				"objectives": [{"name_key": "o.hp", "condition": {"kind": "above", "measure": "hp_fraction", "value": 0.5}},
					{"name_key": "o.cleared", "condition": {"kind": "is_true", "measure": "died"}}]},
		},
		"mails": {
			"welcome": {"sender_key": "s.v", "title_key": "m.w.t", "body_key": "m.w.b", "attachments": [{"item": "gold", "count": 500}], "expires_days": null},
			"thanks": {"sender_key": "s.v", "title_key": "m.t.t", "body_key": "m.t.b", "attachments": [{"item": "gem", "count": 40}], "expires_days": 30},
			"note": {"sender_key": "s.v", "title_key": "m.n.t", "body_key": "m.n.b", "attachments": [], "expires_days": 7},
		},
	}


func _catalog() -> RefCounted:
	var c := CATALOG.new()
	var errors: Array[String] = c.configure(_design(), KEYS)
	_expect(errors.is_empty(), "the literal design configures: " + "; ".join(errors))
	return c


static func _fixed(value: float) -> Callable:
	return func() -> float: return value


func _design_refusals() -> void:
	var d := _design()
	d["items"]["odd"] = {"type": "weapon", "rarity": "mythic", "stack": 0}
	var errors: Array[String] = CATALOG.new().configure(d, KEYS)
	_expect(errors.size() == 4, "a bad type, rarity, stack and a missing name_key are four refusals, got %d: %s" % [errors.size(), "; ".join(errors)])
	d = _design()
	d["sources"]["boss.clear"]["objectives"][1]["condition"] = {"kind": "below", "measure": "speed", "value": 1}
	d["sources"]["boss.clear"]["objectives"][2]["condition"] = {"kind": "is_true", "measure": "fight_s"}
	d["sources"]["boss.clear"]["bundle"] = [{"item": "silver", "count": 3}, {"table": "nothing", "rolls": 1}]
	d["sources"]["boss.clear"]["objective_bonus"] = {"5": []}
	d["sources"]["boss.clear"]["exp"] = {"curve": "season", "amount": 10}
	errors = CATALOG.new().configure(d, KEYS)
	_expect(errors.size() == 6, "an undeclared measure, a type mismatch, an unknown item, an unknown table, an unreachable bonus count and an unknown curve are six refusals, got %d: %s" % [errors.size(), "; ".join(errors)])
	d = _design()
	d["sources"]["daily"].erase("period_s")
	d["sources"]["boss.first"]["mail_on_claim"] = "missing"
	d["mails"]["thanks"]["title_key"] = "m.missing"
	errors = CATALOG.new().configure(d, KEYS)
	_expect(errors.size() == 3, "a periodic source without a period, an unknown mail and a text key the set lacks are three refusals: " + "; ".join(errors))
	var c := CATALOG.new()
	errors = c.configure({"schema_version": 1, "items": {}}, KEYS)
	_expect(errors.size() == 1 and errors[0].contains("schema_version") and c.items.is_empty(), "a foreign schema version is refused and nothing is kept")
	errors = CATALOG.new().configure(_design(), [])
	_expect(errors.is_empty(), "with no key list the names are not checked")
	c = _catalog()
	_expect(c.sources_for("stage:boss") == ["boss.clear", "boss.first"] and c.sources_for("nothing").is_empty(), "a trigger lists its sources in id order")
	_expect(c.exp_to_leave("account", 1) == 100 and c.exp_to_leave("account", 9) == 200 and c.exp_to_leave("season", 1) == 0, "the curve's last step repeats; an unknown curve is 0")


func _builder_matches_json() -> void:
	var b := BUILDER.new()
	b.item("gold", "currency", "common", 1000, "n.gold").item("gem", "currency", "rare", 100, "n.gem").item("core", "material", "epic", 2, "n.core")
	b.curve("account", [100, 150, 200])
	for name in ["fight_s", "hp_fraction"]:
		b.measurement(name, "number")
	b.measurement("hits_taken", "integer").measurement("died", "boolean")
	b.table("drops", [{"item": "gem", "count": 5, "weight": 70}, {"item": "core", "count": 1, "weight": 30}])
	b.source("boss.first", "stage:boss", "once", "r.first", [{"item": "gem", "count": 60}, {"item": "core", "count": 1}], {"mail_on_claim": "thanks"})
	b.source("boss.clear", "stage:boss", "repeat", "r.clear", [{"item": "gold", "count": 150}, {"table": "drops", "rolls": 2}], {
		"exp": {"curve": "account", "amount": 120},
		"objectives": [BUILDER.objective("o.cleared", "always"), BUILDER.objective("o.fast", "below", "fight_s", 120), BUILDER.objective("o.clean", "at_most", "hits_taken", 3)],
		"objective_bonus": {"3": [{"item": "core", "count": 1}]}})
	b.source("daily", "login", "periodic", "r.daily", [{"item": "gold", "count": 50}], {"period_s": DAY})
	b.source("hp_stage", "stage:hp", "repeat", "r.hp", [], {"objectives": [BUILDER.objective("o.hp", "above", "hp_fraction", 0.5), BUILDER.objective("o.cleared", "is_true", "died")]})
	b.mail("welcome", "s.v", "m.w.t", "m.w.b", [{"item": "gold", "count": 500}])
	b.mail("thanks", "s.v", "m.t.t", "m.t.b", [{"item": "gem", "count": 40}], 30)
	b.mail("note", "s.v", "m.n.t", "m.n.b", [], 7)
	var built := CATALOG.new()
	var errors: Array[String] = built.configure(b.build(), KEYS)
	_expect(errors.is_empty(), "the built design configures: " + "; ".join(errors))
	var parsed := _catalog()
	_expect(JSON.stringify(built.sources) == JSON.stringify(parsed.sources) and JSON.stringify(built.items) == JSON.stringify(parsed.items) and JSON.stringify(built.mails) == JSON.stringify(parsed.mails), "the builder's design reads the same as the JSON design")


func _tables() -> void:
	var c := _catalog()
	var low := TABLES.roll(c.table("drops"), _fixed(0.1))
	var high := TABLES.roll(c.table("drops"), _fixed(0.95))
	_expect(low == {"item": "gem", "count": 5} and high == {"item": "core", "count": 1}, "a low draw picks the heavy entry, a high draw the light one")
	var whole: Dictionary = TABLES.resolve([{"item": "gold", "count": 1}, {"table": "drops", "rolls": 2}], c, _fixed(0.2))
	_expect(whole["errors"].is_empty() and whole["bundle"] == [{"item": "gold", "count": 1}, {"item": "gem", "count": 10}], "two rolls merge into one concrete entry: " + str(whole))
	whole = TABLES.resolve([{"table": "drops", "rolls": 1}], c, Callable())
	_expect(whole["errors"].size() == 1, "a table with no draw is an error, not a skip")
	_expect(not CATALOG.is_concrete([{"table": "drops", "rolls": 1}]) and CATALOG.is_concrete([{"item": "gold", "count": 1}]), "is_concrete tells a rolled bundle from an authored one")


func _ledger_grant_spend() -> void:
	var c := _catalog()
	var doc := LEDGER.create(1000)
	_expect(LEDGER.validate(doc).is_empty(), "a fresh ledger validates")
	var outcome: Dictionary = LEDGER.grant(doc, c, [{"item": "gold", "count": 30}, {"item": "core", "count": 1}, {"item": "gold", "count": 20}], "test", 1000)
	_expect(outcome["granted"] == [{"item": "gold", "count": 50}, {"item": "core", "count": 1}] and LEDGER.balance(doc, "gold") == 50, "a bundle is merged by item before it is granted: " + str(outcome))
	outcome = LEDGER.grant(doc, c, [{"item": "core", "count": 5}], "test", 1001)
	_expect(outcome["granted"] == [{"item": "core", "count": 1}] and outcome["lost"] == [{"item": "core", "count": 4}] and LEDGER.balance(doc, "core") == 2, "a full stack refuses the rest and reports it")
	outcome = LEDGER.grant(doc, c, [{"table": "drops", "rolls": 1}], "test", 1002)
	_expect(outcome["errors"].size() == 1, "an unresolved table cannot be granted")
	outcome = LEDGER.spend(doc, c, [{"item": "gold", "count": 30}, {"item": "core", "count": 1}], "shop", 1003)
	_expect(outcome["shortfall"].is_empty() and LEDGER.balance(doc, "gold") == 20 and LEDGER.balance(doc, "core") == 1, "a spend within the balances moves everything: " + str(outcome))
	outcome = LEDGER.spend(doc, c, [{"item": "gold", "count": 25}, {"item": "core", "count": 1}], "shop", 1004)
	_expect(outcome["shortfall"] == [{"item": "gold", "count": 5}] and LEDGER.balance(doc, "gold") == 20 and LEDGER.balance(doc, "core") == 1, "a spend short on one item moves nothing and names the shortfall: " + str(outcome))
	var log: Array = LEDGER.entries(doc)
	_expect(log.size() == 3 and log[0]["kind"] == "spend" and log[2]["kind"] == "grant" and LEDGER.entries(doc, "spend").size() == 1, "the log keeps grants and spends newest first: " + str(log.size()))
	for i in 300:
		LEDGER.grant(doc, c, [{"item": "gold", "count": 1}], "drip", 2000 + i)
	_expect(doc["entries"].size() == LEDGER.ENTRIES_CAP and int(LEDGER.entries(doc)[0]["at"]) == 2299, "the log is capped and keeps the newest")
	_expect(LEDGER.validate(doc).is_empty(), "a mutated ledger validates")
	var bad := LEDGER.create(1)
	bad["balances"]["gold"] = -1
	bad["tracks"]["account"] = {"level": 0, "exp": 0}
	_expect(LEDGER.validate(bad).size() == 2, "a negative balance and a level below 1 are refused")


func _levels() -> void:
	var c := _catalog()
	var doc := LEDGER.create(1000)
	var state: Dictionary = LEVELS.state(doc, c, "account")
	_expect(state == {"level": 1, "exp": 0, "to_next": 100}, "a track starts at level 1: " + str(state))
	var result: Dictionary = LEVELS.add_exp(doc, c, "account", 90)
	_expect(result["level"] == 1 and result["exp"] == 90 and result["level_ups"] == 0, "EXP below the step keeps the level")
	result = LEVELS.add_exp(doc, c, "account", 10 + 150 + 200 + 200 + 5)
	_expect(result["level"] == 5 and result["exp"] == 5 and result["level_ups"] == 4 and result["level_before"] == 1 and result["exp_before"] == 90, "EXP rolls through four levels, the last step repeating: " + str(result))
	_expect(not LEVELS.add_exp(doc, c, "season", 1)["errors"].is_empty(), "an unknown curve is refused")


func _conditions() -> void:
	var c := _catalog()
	var bag := {"fight_s": 80.0, "hits_taken": 3, "hp_fraction": 0.5, "died": true}
	_expect(CONDITIONS.evaluate({"kind": "always"}, {}, c)["met"], "always is met with an empty bag")
	_expect(CONDITIONS.evaluate({"kind": "below", "measure": "fight_s", "value": 120}, bag, c)["met"], "below")
	_expect(not CONDITIONS.evaluate({"kind": "below", "measure": "fight_s", "value": 80}, bag, c)["met"], "below is strict")
	_expect(CONDITIONS.evaluate({"kind": "at_most", "measure": "hits_taken", "value": 3}, bag, c)["met"], "at_most includes the value")
	_expect(not CONDITIONS.evaluate({"kind": "above", "measure": "hp_fraction", "value": 0.5}, bag, c)["met"], "above is strict")
	_expect(CONDITIONS.evaluate({"kind": "at_least", "measure": "hp_fraction", "value": 0.5}, bag, c)["met"], "at_least includes the value")
	_expect(CONDITIONS.evaluate({"kind": "equals", "measure": "hits_taken", "value": 3}, bag, c)["met"] and CONDITIONS.evaluate({"kind": "equals", "measure": "died", "value": true}, bag, c)["met"], "equals on a number and on a boolean")
	_expect(CONDITIONS.evaluate({"kind": "is_true", "measure": "died"}, bag, c)["met"], "is_true")
	var missing: Dictionary = CONDITIONS.evaluate({"kind": "below", "measure": "fight_s", "value": 1}, {}, c)
	_expect(not missing["met"] and missing["errors"].size() == 1, "a bag missing the measurement is an error, not a false")
	var wrong: Dictionary = CONDITIONS.evaluate({"kind": "is_true", "measure": "died"}, {"died": 1}, c)
	_expect(wrong["errors"].size() == 1, "a measurement of the wrong type is an error")
	_expect(CONDITIONS.label_values({"kind": "below", "measure": "fight_s", "value": 120.0}) == {"value": "120"} and CONDITIONS.label_values({"kind": "always"}).is_empty(), "label values drop a whole float's .0")


func _sources_lifecycle() -> void:
	var c := _catalog()
	var doc := LEDGER.create(1000)
	var fast := {"fight_s": 90.5, "hits_taken": 2, "hp_fraction": 0.8}
	var seen: Dictionary = SOURCES.preview(doc, c, "stage:boss", fast, 1000)
	_expect(seen["errors"].is_empty() and seen["rows"].size() == 2, "the boss trigger previews two sources")
	var clear: Dictionary = seen["rows"][0]
	var first: Dictionary = seen["rows"][1]
	_expect(clear["id"] == "boss.clear" and clear["claimable"] and clear["objectives_met"] == 3 and clear["bonus"] == [{"item": "core", "count": 1}], "a fast clean clear meets all three and earns the bonus: " + str(clear))
	_expect(first["id"] == "boss.first" and first["claimable"] and first["reason"] == "", "the first clear is claimable once")
	_expect(SOURCES.preview(doc, c, "stage:nowhere", {}, 1000)["errors"].size() == 1, "a trigger no source listens to is an error")
	_expect(SOURCES.preview(doc, c, "stage:boss", {}, 1000)["errors"].size() == 2, "a report missing the measurements two objectives need is refused")
	var outcome: Dictionary = SOURCES.claim(doc, c, "stage:boss", fast, 1000, _fixed(0.2))
	_expect(outcome["errors"].is_empty() and outcome["claimed"] == ["boss.clear", "boss.first"], "both sources claim: " + str(outcome["errors"]))
	_expect(outcome["granted"] == [{"item": "gold", "count": 150}, {"item": "core", "count": 2}, {"item": "gem", "count": 70}], "the clear, the bonus, the first clear and two rolled drops are granted merged (authored entries first, rolls after): " + str(outcome["granted"]))
	_expect(outcome["exp"].size() == 1 and outcome["exp"][0]["level"] == 2 and outcome["exp"][0]["exp"] == 20, "120 EXP on the account track lands at level 2 with 20")
	_expect(outcome["mails"].size() == 1 and MAILBOX.find(doc, 1)["template"] == "thanks", "the first clear delivered its mail")
	var rec: Dictionary = doc["records"]["boss.clear"]
	_expect(rec["claims"] == 1 and rec["best_met"] == 3 and rec["first_claimed_at"] == 1000, "the record is written: " + str(rec))
	_expect(LEDGER.balance(doc, "core") == 2, "the core stack of 2 holds the first clear's and the bonus (the drop lost nothing else)")
	outcome = SOURCES.claim(doc, c, "stage:boss", {"fight_s": 300.0, "hits_taken": 9, "hp_fraction": 0.1}, 2000, _fixed(0.2))
	_expect(outcome["claimed"] == ["boss.clear"] and outcome["granted"] == [{"item": "gold", "count": 150}, {"item": "gem", "count": 10}] and outcome["mails"].is_empty(), "a repeat claims only the repeat source, no bonus, no mail: " + str(outcome["granted"]))
	_expect(doc["records"]["boss.clear"]["best_met"] == 3 and doc["records"]["boss.clear"]["claims"] == 2, "a worse repeat keeps the best objectives")
	_expect(SOURCES.can_claim(doc, c, "boss.first", 3000)["reason"] == "already_claimed", "the once source refuses a second claim")
	outcome = SOURCES.claim(doc, c, "login", {}, 5000)
	_expect(outcome["claimed"] == ["daily"] and LEDGER.balance(doc, "gold") == 350, "the daily gift claims on the first login")
	outcome = SOURCES.claim(doc, c, "login", {}, 5000 + DAY - 1)
	_expect(outcome["claimed"].is_empty() and outcome["rows"][0]["reason"] == "period_not_elapsed" and outcome["rows"][0]["next_at"] == 5000 + DAY, "inside the period nothing claims and the row says when")
	outcome = SOURCES.claim(doc, c, "login", {}, 5000 + DAY)
	_expect(outcome["claimed"] == ["daily"], "at the period it claims again")
	outcome = SOURCES.claim(doc, c, "stage:boss", fast, 6000, Callable())
	_expect(outcome["errors"].size() == 1 and doc["records"]["boss.clear"]["claims"] == 2 and LEDGER.balance(doc, "gold") == 400, "a claim with a table and no draw refuses before any write")
	var hp: Dictionary = SOURCES.preview(doc, c, "stage:hp", {"hp_fraction": 0.51, "died": false}, 1)
	_expect(hp["rows"][0]["objectives"][0]["met"] and not hp["rows"][0]["objectives"][1]["met"], "above and is_true score per objective")
	_expect(LEDGER.validate(doc).is_empty(), "the claimed ledger validates")


func _mail() -> void:
	var c := _catalog()
	var doc := LEDGER.create(1000)
	var now := 1000
	var once: Dictionary = MAILBOX.deliver_once(doc, c, "welcome", now)
	_expect(once["delivered"], "the welcome mail is delivered once")
	once = MAILBOX.deliver_once(doc, c, "welcome", now)
	_expect(not once["delivered"] and doc["mail"].size() == 1, "and never twice")
	var sent: Dictionary = MAILBOX.deliver(doc, c, "thanks", now + 10)
	_expect(sent["errors"].is_empty() and sent["mail"]["id"] == 2 and sent["mail"]["expires_at"] == now + 10 + 30 * DAY, "a template mail carries its expiry")
	MAILBOX.deliver(doc, c, "note", now + 20)
	_expect(MAILBOX.deliver(doc, c, "missing", now)["errors"].size() == 1, "an unknown template is refused")
	var inbox: Array = MAILBOX.inbox(doc, now + 30)
	_expect(inbox.size() == 3 and inbox[0]["id"] == 3 and inbox[2]["id"] == 1, "the inbox lists newest first")
	_expect(MAILBOX.unread_count(doc, now + 30) == 3 and MAILBOX.claimable(doc, now + 30).size() == 2, "every mail is unread; a mail with no attachment is not claimable")
	MAILBOX.mark_read(doc, 3)
	_expect(MAILBOX.unread_count(doc, now + 30) == 2, "reading the note clears its count")
	var claim: Dictionary = MAILBOX.claim(doc, c, 2, now + 30)
	_expect(claim["errors"].is_empty() and claim["granted"] == [{"item": "gem", "count": 40}] and LEDGER.balance(doc, "gem") == 40, "claiming grants the attachment")
	_expect(MAILBOX.find(doc, 2)["claimed"] and MAILBOX.find(doc, 2)["read"] and MAILBOX.claim(doc, c, 2, now + 30)["errors"].size() == 1, "a claimed mail is kept as read and refuses a second claim")
	_expect(MAILBOX.inbox(doc, now + 30)[2]["id"] == 2, "a claimed mail sorts last")
	var all: Dictionary = MAILBOX.claim_all(doc, c, now + 30)
	_expect(all["claimed_ids"] == [1] and all["granted"] == [{"item": "gold", "count": 500}] and MAILBOX.unread_count(doc, now + 30) == 0, "claim all takes what is left")
	_expect(MAILBOX.days_left(MAILBOX.find(doc, 3), now + 20) == 7 and MAILBOX.days_left(MAILBOX.find(doc, 1), now) == -1, "days left rounds up, a keeper says -1")
	var later := now + 20 + 7 * DAY
	_expect(MAILBOX.is_expired(MAILBOX.find(doc, 3), later) and not MAILBOX.is_expired(MAILBOX.find(doc, 2), later) and MAILBOX.inbox(doc, later).size() == 2, "the note expires after seven days and leaves the inbox")
	_expect(MAILBOX.prune_expired(doc, later) == 1 and doc["mail"].size() == 2, "pruning drops it")
	for i in 120:
		MAILBOX.deliver(doc, c, "note", later + i)
	_expect(doc["mail"].size() == LEDGER.MAIL_CAP and MAILBOX.find(doc, 1).is_empty() and MAILBOX.find(doc, 2).is_empty(), "the box is capped and the claimed mails were evicted first")
	var custom: Dictionary = MAILBOX.deliver_custom(doc, {"sender_key": "s.v", "title_key": "m.n.t", "body_key": "m.n.b", "attachments": [{"item": "gold", "count": 5}], "template": "compensation"}, later + 500, 3)
	_expect(custom["mail"]["template"] == "compensation" and custom["mail"]["expires_at"] == later + 500 + 3 * DAY, "a custom mail carries its own expiry")
	_expect(LEDGER.validate(doc).is_empty(), "the mailed ledger validates")


func _store() -> void:
	var c := _catalog()
	var dir := OS.get_temp_dir().path_join("progression-store-%d" % Time.get_ticks_usec())
	var path := dir.path_join("ledger.json")
	var validate := Callable(LEDGER, "validate")
	var create := Callable(LEDGER, "create")
	var loaded: Dictionary = STORE.load_document(path, validate, create, 5000)
	_expect(loaded["fresh"] and loaded["refused"] == "" and loaded["document"]["created_at"] == 5000, "no file: a fresh document")
	var doc: Dictionary = loaded["document"]
	LEDGER.grant(doc, c, [{"item": "gem", "count": 7}], "test", 5000)
	MAILBOX.deliver(doc, c, "thanks", 5000)
	var errors: Array[String] = STORE.save_document(path, doc)
	_expect(errors.is_empty() and FileAccess.file_exists(path) and not FileAccess.file_exists(path + ".tmp"), "the document saves and the temp file was renamed into place")
	loaded = STORE.load_document(path, validate, create, 6000)
	_expect(not loaded["fresh"] and loaded["document"]["balances"]["gem"] == 7 and loaded["document"]["mail"].size() == 1 and loaded["document"]["created_at"] == 5000 and LEDGER.validate(loaded["document"]).is_empty(), "the round trip keeps balances, mail and the creation time")
	var foreign := doc.duplicate(true)
	foreign["schema_version"] = 7
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(JSON.stringify(foreign))
	file.close()
	loaded = STORE.load_document(path, validate, create, 7000)
	_expect(loaded["fresh"] and loaded["refused"].contains("schema_version 7") and loaded["document"]["created_at"] == 7000 and FileAccess.file_exists(dir.path_join("ledger.v7.json")) and not FileAccess.file_exists(path), "a foreign schema is refused, moved aside as v7, and a fresh document starts")
	file = FileAccess.open(path, FileAccess.WRITE)
	file.store_string("{not json")
	file.close()
	loaded = STORE.load_document(path, validate, create, 8000)
	_expect(loaded["fresh"] and loaded["refused"].contains("not a JSON") and FileAccess.file_exists(dir.path_join("ledger.bad.json")), "an unreadable file is moved aside too")
	for name in DirAccess.get_files_at(dir):
		DirAccess.remove_absolute(dir.path_join(name))
	DirAccess.remove_absolute(dir)

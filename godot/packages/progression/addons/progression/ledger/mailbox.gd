extends RefCounted
## The mailbox: mail delivered into the ledger, read, claimed, expired and evicted. A mail is copied
## out of its template at delivery (sender, title and body keys, attachments, expiry), so a later
## template edit never changes what was already sent. Claimed mail stays as read until it expires or
## the box is full; the box keeps at most LEDGER.MAIL_CAP mails and evicts claimed ones first, oldest
## first. Time is an integer unix second the host passes in; nothing here reads a clock.

const LEDGER := preload("ledger.gd")
const CATALOG := preload("../design/catalog.gd")
const DAY_S := 86400


static func deliver(doc: Dictionary, catalog: RefCounted, template_id: String, now: int) -> Dictionary:
	## Sends one mail from a template. Returns {mail, errors}.
	var template: Dictionary = catalog.mail_template(template_id)
	if template.is_empty():
		return {"mail": {}, "errors": ["Unknown mail template: " + template_id]}
	var expires_days: Variant = template.get("expires_days", null)
	var mail := {
		"template": template_id,
		"sender_key": template["sender_key"],
		"title_key": template["title_key"],
		"body_key": template["body_key"],
		"attachments": template.get("attachments", []).duplicate(true),
		"expires_at": null if expires_days == null else now + int(expires_days) * DAY_S,
	}
	return {"mail": _push(doc, mail, now), "errors": []}


static func deliver_custom(doc: Dictionary, mail: Dictionary, now: int, expires_days: Variant = null) -> Dictionary:
	## Sends a mail the host built (compensation, an event): sender_key, title_key, body_key and
	## concrete attachments the host already validated against the design.
	var record := mail.duplicate(true)
	record["template"] = String(mail.get("template", "custom"))
	record["expires_at"] = null if expires_days == null else now + int(expires_days) * DAY_S
	return {"mail": _push(doc, record, now), "errors": []}


static func deliver_once(doc: Dictionary, catalog: RefCounted, template_id: String, now: int) -> Dictionary:
	## Delivers a template at most once per ledger (a welcome mail). Returns {delivered: bool, errors}.
	if template_id in doc["delivered_once"]:
		return {"delivered": false, "errors": []}
	var sent := deliver(doc, catalog, template_id, now)
	if not sent["errors"].is_empty():
		return {"delivered": false, "errors": sent["errors"]}
	doc["delivered_once"].append(template_id)
	return {"delivered": true, "errors": []}


static func inbox(doc: Dictionary, now: int) -> Array:
	## The mails to show: unexpired, unclaimed first, newest first within each group. References into
	## the document, so mark_read on one is seen by the next inbox() call.
	var live: Array = []
	for mail: Dictionary in doc["mail"]:
		if not is_expired(mail, now):
			live.append(mail)
	live.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		if bool(a["claimed"]) != bool(b["claimed"]):
			return not bool(a["claimed"])
		return int(a["sent_at"]) > int(b["sent_at"]) or (int(a["sent_at"]) == int(b["sent_at"]) and int(a["id"]) > int(b["id"])))
	return live


static func find(doc: Dictionary, id: int) -> Dictionary:
	for mail: Dictionary in doc["mail"]:
		if int(mail["id"]) == id:
			return mail
	return {}


static func unread_count(doc: Dictionary, now: int) -> int:
	## Mails that still want attention: unread, or holding an unclaimed attachment.
	var n := 0
	for mail: Dictionary in inbox(doc, now):
		if not bool(mail["read"]) or (not bool(mail["claimed"]) and not mail["attachments"].is_empty()):
			n += 1
	return n


static func claimable(doc: Dictionary, now: int) -> Array:
	var out: Array = []
	for mail: Dictionary in inbox(doc, now):
		if not bool(mail["claimed"]) and not mail["attachments"].is_empty():
			out.append(mail)
	return out


static func mark_read(doc: Dictionary, id: int) -> void:
	var mail := find(doc, id)
	if not mail.is_empty():
		mail["read"] = true


static func claim(doc: Dictionary, catalog: RefCounted, id: int, now: int) -> Dictionary:
	## Claims one mail's attachments into the ledger. Returns {granted, lost, errors}.
	var mail := find(doc, id)
	if mail.is_empty():
		return {"granted": [], "lost": [], "errors": ["No mail with id %d" % id]}
	if is_expired(mail, now):
		return {"granted": [], "lost": [], "errors": ["Mail %d has expired" % id]}
	if bool(mail["claimed"]):
		return {"granted": [], "lost": [], "errors": ["Mail %d was already claimed" % id]}
	var outcome: Dictionary = LEDGER.grant(doc, catalog, mail["attachments"], "mail:" + String(mail.get("template", "")), now)
	if not outcome["errors"].is_empty():
		return {"granted": [], "lost": [], "errors": outcome["errors"]}
	mail["claimed"] = true
	mail["read"] = true
	return {"granted": outcome["granted"], "lost": outcome["lost"], "errors": []}


static func claim_all(doc: Dictionary, catalog: RefCounted, now: int) -> Dictionary:
	## Claims every claimable mail; the granted lists are merged so a panel shows one total per item.
	var granted: Array = []
	var lost: Array = []
	var ids: Array = []
	var errors: Array[String] = []
	for mail: Dictionary in claimable(doc, now):
		var one := claim(doc, catalog, int(mail["id"]), now)
		errors.append_array(one["errors"])
		if one["errors"].is_empty():
			granted = CATALOG.merge([granted, one["granted"]])
			lost = CATALOG.merge([lost, one["lost"]])
			ids.append(int(mail["id"]))
	return {"granted": granted, "lost": lost, "claimed_ids": ids, "errors": errors}


static func is_expired(mail: Dictionary, now: int) -> bool:
	var expires: Variant = mail.get("expires_at", null)
	return expires != null and now >= int(expires)


static func days_left(mail: Dictionary, now: int) -> int:
	## Whole days until expiry, rounded up; -1 when the mail keeps.
	var expires: Variant = mail.get("expires_at", null)
	if expires == null:
		return -1
	return maxi(int(ceilf(float(int(expires) - now) / float(DAY_S))), 0)


static func prune_expired(doc: Dictionary, now: int) -> int:
	## Drops expired mail (claimed or not; an expired attachment is gone). Returns how many went.
	var kept: Array = []
	var removed := 0
	for mail: Dictionary in doc["mail"]:
		if is_expired(mail, now):
			removed += 1
		else:
			kept.append(mail)
	doc["mail"] = kept
	return removed


static func evict(doc: Dictionary, cap: int = LEDGER.MAIL_CAP) -> int:
	## Keeps the box at `cap` mails: claimed ones go first, oldest first; then unclaimed, oldest first.
	var removed := 0
	while doc["mail"].size() > cap:
		var victim := -1
		for pass_claimed in [true, false]:
			for i in doc["mail"].size():
				var mail: Dictionary = doc["mail"][i]
				if bool(mail["claimed"]) == pass_claimed and (victim < 0 or int(mail["sent_at"]) < int(doc["mail"][victim]["sent_at"])):
					victim = i
			if victim >= 0:
				break
		doc["mail"].remove_at(victim)
		removed += 1
	return removed


static func _push(doc: Dictionary, mail: Dictionary, now: int) -> Dictionary:
	doc["mail_seq"] = int(doc["mail_seq"]) + 1
	mail["id"] = int(doc["mail_seq"])
	mail["sent_at"] = now
	mail["read"] = false
	mail["claimed"] = false
	doc["mail"].append(mail)
	evict(doc)
	return mail

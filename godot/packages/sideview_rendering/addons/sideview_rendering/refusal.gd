extends RefCounted

## Plain structured failure; no dependency on a consumer's error class.
## A failed layout/image transform has no partially layout or image.

static func of(code: String, message: String, path: String = "") -> Dictionary:
	return {"error": {"code": code, "message": message, "path": path}}


static func is_refusal(value: Variant) -> bool:
	return value is Dictionary and value.get("error") is Dictionary


static func line(value: Dictionary) -> String:
	var error: Dictionary = value["error"]
	var location := "" if error["path"] == "" else " (%s)" % error["path"]
	return "%s: %s%s" % [error["code"], error["message"], location]

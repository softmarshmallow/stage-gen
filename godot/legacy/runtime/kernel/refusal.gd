class_name KernelRefusal
extends RefCounted

## A refusal is a value, never a partial result.
##
## GDScript has no exceptions, and the two habits that fill the gap both lose
## the refusal: `push_error` plus `null` says nothing a caller can act on, and a
## half-filled dictionary says nothing at all. Every parser and every sealer in
## this project returns the parsed value or one of these, so a caller always has
## either a thing or a reason.
##
## The host shows the reason before it draws anything, and reports it through
## the bridge's `load_error`, so a refused run is a card with a sentence rather
## than a black window.

## A stable, greppable code: `<layer>/<what>`, e.g. `kernel/cycle`,
## `survival/manifest-kind`.
var code: String = ""
## One sentence a person can act on. Names what was wrong and, where there is
## one, what to do about it.
var message: String = ""
## Where it was wrong: a slice, an event type, a document path, a JSON pointer.
## Empty when the refusal is about the roster as a whole.
var path: String = ""


static func of(code: String, message: String, path: String = "") -> KernelRefusal:
	var made := KernelRefusal.new()
	made.code = code
	made.message = message
	made.path = path
	return made


## True when `value` is a refusal, for the one-line check at every call site.
static func is_refusal(value: Variant) -> bool:
	return value is KernelRefusal


## The line a host prints, a card shows, and `load_error()` returns.
func line() -> String:
	if path == "":
		return "%s: %s" % [code, message]
	return "%s: %s (%s)" % [code, message, path]

class_name PlatformerCombatText
extends Node2D

## The numbers a fight is read by.
##
## World space, so a number stays over the body it came off while the view
## scrolls. The motion is `FamilyCombatText`'s and the clock is the frame's, so a
## number freezes with the world during a hitstop rather than running on through
## it.
##
## **Drawn, not built.** A number is up for two thirds of a second and a fight
## produces dozens; one digit was one `Label`, so a busy exchange was creating and
## freeing hundreds of nodes a second, each with its own theme overrides, and every
## one of them entered the tree, laid itself out and left again. `draw_string` puts
## the same glyph on the canvas with no node behind it, which is both faster and
## the only way to draw what this number actually is.
##
## **A number is three passes, not one.** The identity colour sits inside a white
## ring inside a near-black edge, and a `Label` draws one outline. The outer edge
## goes down first at its own thickness, the ring over it at a thinner one, and the
## core last — so the dark edge appears from behind the ring rather than being
## swallowed by it, which is why the outer thickness must exceed the inner.
##
## One thing the browser drew that is not here: a vertical gradient through the
## core, light collecting at the top of a glyph and the hue deepening into its
## foot. `draw_string` fills flat, and faking it would mean a shader pass that
## tinted the ring and the edge along with the core.

## Hot pink for what the player did, red for what was done to them, and white for
## a critical with the identity colour demoted to the ring — so a critical is a
## different *kind* of number rather than a bigger one.
const OUTGOING := {
	"core": Color(1.0, 0.180, 0.545),
	"ring": Color(1.0, 1.0, 1.0),
	"edge": Color(0.141, 0.067, 0.051),
}
const INCOMING := {
	"core": Color(0.898, 0.141, 0.122),
	"ring": Color(1.0, 1.0, 1.0),
	"edge": Color(0.141, 0.067, 0.051),
}
const CRITICAL_OUTGOING := {
	"core": Color(1.0, 1.0, 1.0),
	"ring": Color(1.0, 0.180, 0.545),
	"edge": Color(0.157, 0.016, 0.078),
}
const CRITICAL_INCOMING := {
	"core": Color(1.0, 1.0, 1.0),
	"ring": Color(0.898, 0.141, 0.122),
	"edge": Color(0.157, 0.016, 0.078),
}

## The two edges, as shares of the size the number is set at. The outer must
## exceed the inner or the dark edge never appears from behind the ring.
const RING_SHARE := 0.055
const EDGE_SHARE := 0.115

## How far above the drawn top of a body a number starts.
const RISE_ABOVE := FamilyCombatText.RISE_ABOVE

## Enough for six targets times three blows, twice over, before the oldest number
## is recycled.
const ACTIVE_CAP := 64

var _live: Array = []
var _now_ms: float = 0.0
var _scroll: Vector2 = Vector2.ZERO
## The face the package set its numerals in, or the engine's own. Decision 0017:
## a stroke eats a glyph's counters from both sides, so the face a double-outlined
## numeral is drawn in is a constraint and not a preference.
var _face: Font = null
## Names the numbers in the order they were raised. It is the phase every
## deterministic displacement is drawn from — the shake pattern, the per-digit
## jitter, the column's sideways nudge — so two blows in the same place never
## agree, and the same blow always displaces the same way.
var _next_event_id: int = 1


static func of(face: Font = null) -> PlatformerCombatText:
	var made := PlatformerCombatText.new()
	made.z_index = PlatformerStage.DEPTHS["foreground"] + 20
	made._face = face if face != null else ThemeDB.fallback_font
	return made


## Raise one number over a body.
##
## The stack offset is decided here, once, and folded into the anchor: a number
## that lands where another is still standing is lifted clear of it rather than
## drawn through it, and the rise and the fade never have to know it happened.
func show_damage(
	amount: int, critical: bool, incoming: bool, at: Vector2, now_ms: float
) -> void:
	var event_id := _next_event_id
	_next_event_id += 1
	var size := FamilyCombatText.size_for(incoming, critical)
	var text := FamilyCombatText.text_for(amount, critical)

	var peers: Array = []
	for entry: Variant in _live:
		var record: Dictionary = entry
		var anchor: Vector2 = record["at"]
		peers.append({"x": anchor.x, "y": anchor.y, "startedMs": record["startedMs"]})
	var lift := FamilyCombatText.stack_offset(peers, event_id, at.x, at.y, now_ms, size)

	# Measured once, when the number is raised, because the advance of a glyph is a
	# question about the face and the size it is set in and neither moves while the
	# number is up.
	var advances := PackedFloat64Array()
	for index in range(text.length()):
		var measured := _face.get_string_size(
			text[index], HORIZONTAL_ALIGNMENT_LEFT, -1.0, int(size)
		).x
		advances.append(
			measured if measured > 0.0
			else FamilyCombatText.nominal_glyph_advance(size, text[index])
		)

	_live.append(
		{
			"eventId": event_id,
			"text": text,
			"advances": advances,
			"centres": FamilyCombatText.glyph_layout(
				advances, size * FamilyCombatText.GLYPH_TRACKING_SHARE
			),
			"size": size,
			"critical": critical,
			"palette": _palette(incoming, critical),
			"startedMs": now_ms,
			# The unstacked anchor, so a column measured against it does not drift
			# upward as it grows.
			"at": at,
			"drawnAt": at + Vector2(float(lift["x"]), float(lift["y"])),
		}
	)
	while _live.size() > ACTIVE_CAP:
		_live.pop_front()


## Advance every number and retire the ones that are over.
func sync(scroll: Vector2, now_ms: float) -> void:
	_scroll = scroll
	_now_ms = now_ms
	var standing: Array = []
	for entry: Variant in _live:
		var record: Dictionary = entry
		if now_ms - float(record["startedMs"]) < FamilyCombatText.LIFETIME_MS:
			standing.append(record)
	_live = standing
	queue_redraw()


func _draw() -> void:
	for entry: Variant in _live:
		var record: Dictionary = entry
		var elapsed := _now_ms - float(record["startedMs"])
		var run := FamilyCombatText.sample(
			elapsed, int(record["eventId"]), bool(record["critical"])
		)
		if run.is_empty():
			continue
		var size := float(record["size"])
		var run_scale := float(run["scale"])
		var palette: Dictionary = record["palette"]
		var anchor: Vector2 = record["drawnAt"]
		var origin := Vector2(
			anchor.x - _scroll.x + float(run["shakeX"]),
			anchor.y - _scroll.y + float(run["riseY"])
		)
		var text := String(record["text"])
		var centres: PackedFloat64Array = record["centres"]
		var advances: PackedFloat64Array = record["advances"]
		for index in range(text.length()):
			var digit := FamilyCombatText.glyph_sample(
				int(record["eventId"]), index, text.length(), centres[index], size, elapsed
			)
			var alpha := float(run["alpha"]) * float(digit["alpha"])
			if alpha <= 0.0:
				continue
			var glyph_scale := run_scale * float(digit["scale"])
			var set_at := int(maxf(1.0, size * glyph_scale))
			# The displacement is in the number's own space, so it scales with the
			# run: a number set larger has to arc and drop further or it reads as a
			# big number sitting still. The baseline is the foot of the glyph, so
			# half its set size puts the drawn body on the anchor.
			var place := (
				origin
				+ Vector2(float(digit["offsetX"]), float(digit["offsetY"])) * run_scale
				+ Vector2(-float(advances[index]) * glyph_scale / 2.0, float(set_at) * 0.35)
			)
			_draw_glyph(text[index], place, set_at, palette, alpha)


## One digit: the dark edge, then the ring over it, then the core.
##
## Three passes rather than one outlined draw, because the identity colour sits
## inside a white ring inside a near-black edge and an engine label carries one
## outline. Ordered outward-in, so each pass covers the middle of the one under it
## and leaves its rim showing.
func _draw_glyph(
	glyph: String, at: Vector2, set_at: int, palette: Dictionary, alpha: float
) -> void:
	var edge: Color = palette["edge"]
	var ring: Color = palette["ring"]
	var core: Color = palette["core"]
	edge.a = alpha
	ring.a = alpha
	core.a = alpha
	draw_string_outline(
		_face,
		at,
		glyph,
		HORIZONTAL_ALIGNMENT_LEFT,
		-1.0,
		set_at,
		int(maxf(2.0, float(set_at) * EDGE_SHARE)),
		edge
	)
	draw_string_outline(
		_face,
		at,
		glyph,
		HORIZONTAL_ALIGNMENT_LEFT,
		-1.0,
		set_at,
		int(maxf(1.0, float(set_at) * RING_SHARE)),
		ring
	)
	draw_string(_face, at, glyph, HORIZONTAL_ALIGNMENT_LEFT, -1.0, set_at, core)


static func _palette(incoming: bool, critical: bool) -> Dictionary:
	if critical:
		return CRITICAL_INCOMING if incoming else CRITICAL_OUTGOING
	return INCOMING if incoming else OUTGOING

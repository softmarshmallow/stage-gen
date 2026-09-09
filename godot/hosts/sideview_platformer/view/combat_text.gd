class_name PlatformerCombatText
extends Node2D

## The numbers a fight is read by.
##
## World space, so a number stays over the body it came off while the view
## scrolls. The motion is `FamilyCombatText`'s and the clock is the frame's, so
## a number freezes with the world during a hitstop rather than running on
## through it.
##
## One label per **digit**, not one per number. That is the whole difference
## between a damage number and a damage effect: a single text object can only pop
## as a block, while a row of digits arrives left to right, each landing a little
## off the line its neighbours sit on. The arithmetic is the family's; what is
## here is the font, the colours, and the measuring the family cannot do — a
## renderer knows how wide a glyph it actually drew is, and nothing below a host
## may ask.

## Outgoing is what the player did; incoming is what was done to them.
## How far above the drawn top of a body a number starts.
const RISE_ABOVE := FamilyCombatText.RISE_ABOVE

const OUTGOING_COLOR := Color(1.0, 0.941, 0.804)
const INCOMING_COLOR := Color(1.0, 0.478, 0.416)
const CRITICAL_COLOR := Color(1.0, 0.812, 0.353)
const OUTLINE_COLOR := Color(0.055, 0.043, 0.039, 0.94)

var _live: Array = []
## Names the numbers in the order they were raised. It is the phase every
## deterministic displacement is drawn from — the shake pattern, the per-digit
## jitter, the column's sideways nudge — so two blows in the same place never
## agree, and the same blow always displaces the same way.
var _next_event_id: int = 1


static func of() -> PlatformerCombatText:
	var made := PlatformerCombatText.new()
	made.z_index = PlatformerStage.DEPTHS["foreground"] + 20
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
	var color: Color = (
		CRITICAL_COLOR if critical else (INCOMING_COLOR if incoming else OUTGOING_COLOR)
	)
	var outline := int(maxf(4.0, size * 0.115))

	var peers: Array = []
	for entry: Variant in _live:
		var record: Dictionary = entry
		var anchor: Vector2 = record["at"]
		peers.append({"x": anchor.x, "y": anchor.y, "startedMs": record["startedMs"]})
	var lift := FamilyCombatText.stack_offset(peers, event_id, at.x, at.y, now_ms, size)

	var glyphs: Array = []
	var advances := PackedFloat64Array()
	for index in range(text.length()):
		var label := Label.new()
		label.text = text[index]
		label.add_theme_font_size_override("font_size", int(size))
		label.add_theme_color_override("font_color", color)
		label.add_theme_color_override("font_outline_color", OUTLINE_COLOR)
		label.add_theme_constant_override("outline_size", outline)
		add_child(label)
		# Measured after the overrides are on, because the width of a glyph is a
		# question about the face and the size it was actually set in.
		var measured := label.get_minimum_size().x
		advances.append(
			measured if measured > 0.0 else FamilyCombatText.nominal_glyph_advance(size, text[index])
		)
		glyphs.append(label)
	var centres := FamilyCombatText.glyph_layout(
		advances, size * FamilyCombatText.GLYPH_TRACKING_SHARE
	)
	# The label's own box is placed from its corner, so half its measured size is
	# what turns a centre into a position.
	var half: Array = []
	for entry: Variant in glyphs:
		half.append((entry as Label).get_minimum_size() / 2.0)

	_live.append(
		{
			"eventId": event_id,
			"glyphs": glyphs,
			"centres": centres,
			"half": half,
			"size": size,
			"critical": critical,
			"startedMs": now_ms,
			# The unstacked anchor, so a column measured against it does not drift
			# upward as it grows.
			"at": at,
			"drawnAt": at + Vector2(float(lift["x"]), float(lift["y"])),
		}
	)


## Advance every number and retire the ones that are over.
func sync(scroll: Vector2, now_ms: float) -> void:
	var standing: Array = []
	for entry: Variant in _live:
		var record: Dictionary = entry
		var elapsed := now_ms - float(record["startedMs"])
		var run := FamilyCombatText.sample(
			elapsed, int(record["eventId"]), bool(record["critical"])
		)
		var glyphs: Array = record["glyphs"]
		if run.is_empty():
			for glyph: Variant in glyphs:
				(glyph as Label).queue_free()
			continue
		var anchor: Vector2 = record["drawnAt"]
		var run_scale := float(run["scale"])
		var origin := Vector2(
			anchor.x - scroll.x + float(run["shakeX"]),
			anchor.y - scroll.y + float(run["riseY"])
		)
		var centres: PackedFloat64Array = record["centres"]
		var half: Array = record["half"]
		for index in range(glyphs.size()):
			var label: Label = glyphs[index]
			var digit := FamilyCombatText.glyph_sample(
				int(record["eventId"]),
				index,
				glyphs.size(),
				centres[index],
				float(record["size"]),
				elapsed
			)
			var scale_of := run_scale * float(digit["scale"])
			# The displacement is in the number's own space, so it scales with the
			# run: a number set larger has to arc and drop further or it reads as a
			# big number sitting still.
			label.scale = Vector2.ONE * scale_of
			label.position = (
				origin
				+ Vector2(float(digit["offsetX"]), float(digit["offsetY"])) * run_scale
				- (half[index] as Vector2) * scale_of
			)
			label.modulate.a = float(run["alpha"]) * float(digit["alpha"])
		standing.append(record)
	_live = standing

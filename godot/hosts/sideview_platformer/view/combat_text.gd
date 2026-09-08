class_name PlatformerCombatText
extends Node2D

## The numbers a fight is read by.
##
## World space, so a number stays over the body it came off while the view
## scrolls. The motion is `FamilyCombatText`'s and the clock is the frame's, so
## a number freezes with the world during a hitstop rather than running on
## through it.

## Outgoing is what the player did; incoming is what was done to them.
## How far above the drawn top of a body a number starts.
const RISE_ABOVE := FamilyCombatText.RISE_ABOVE

const OUTGOING_COLOR := Color(1.0, 0.941, 0.804)
const INCOMING_COLOR := Color(1.0, 0.478, 0.416)
const CRITICAL_COLOR := Color(1.0, 0.812, 0.353)
const OUTLINE_COLOR := Color(0.055, 0.043, 0.039, 0.94)

var _live: Array = []


static func of() -> PlatformerCombatText:
	var made := PlatformerCombatText.new()
	made.z_index = PlatformerStage.DEPTHS["foreground"] + 20
	return made


## Raise one number over a body.
func show_damage(
	amount: int, critical: bool, incoming: bool, at: Vector2, now_ms: float
) -> void:
	var label := Label.new()
	var size := FamilyCombatText.size_for(incoming, critical)
	label.text = FamilyCombatText.text_for(amount, critical)
	label.add_theme_font_size_override("font_size", int(size))
	label.add_theme_color_override(
		"font_color", CRITICAL_COLOR if critical else (INCOMING_COLOR if incoming else OUTGOING_COLOR)
	)
	label.add_theme_color_override("font_outline_color", OUTLINE_COLOR)
	label.add_theme_constant_override("outline_size", int(maxf(4.0, size * 0.115)))
	label.pivot_offset = Vector2(size / 2.0, size / 2.0)
	add_child(label)
	_live.append({"node": label, "startedMs": now_ms, "at": at})


## Advance every number and retire the ones that are over.
func sync(scroll: Vector2, now_ms: float) -> void:
	var standing: Array = []
	for entry: Variant in _live:
		var record: Dictionary = entry
		var frame := FamilyCombatText.sample(now_ms - float(record["startedMs"]))
		var label: Label = record["node"]
		if frame.is_empty():
			label.queue_free()
			continue
		var at: Vector2 = record["at"]
		label.position = Vector2(at.x - scroll.x, at.y - scroll.y + float(frame["riseY"]))
		label.scale = Vector2.ONE * float(frame["scale"])
		label.modulate.a = float(frame["alpha"])
		standing.append(record)
	_live = standing

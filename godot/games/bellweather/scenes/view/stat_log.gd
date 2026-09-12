class_name PlatformerStatLog
extends Control

## What the player just gained, said on the screen.
##
## Screen space, not world space, and that is the whole distinction from the
## combat number: experience and levels are facts about the character, not about a
## spot in the world, and a number rising off a corpse the player has already
## walked away from is a fact delivered to nobody.
##
## No panel and no frame. Lines stack upward from a fixed anchor, the newest
## nearest it, and each fades on its own clock, so a burst of three kills reads as
## three lines rather than as one line flickering three times. The motion is
## `FamilyStatLog`'s and the clock is the frame's.

## Where the column starts, in the 1280x720 the manifest publishes its rectangles
## in: low on the left, clear of the health readout and of the dialogue panel.
const ANCHOR := Vector2(40.0, 470.0)
const LINE_WIDTH := 320.0

var _live: Array = []


static func of() -> PlatformerStatLog:
	var made := PlatformerStatLog.new()
	made.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return made


## Take this frame's lines. Newest first in the column, which is why the existing
## lines are pushed up rather than the new one appended below them.
func say(notices: Array, now_ms: float) -> void:
	for entry: Variant in notices:
		var notice: Dictionary = entry
		var kind := str(notice.get("kind", FamilyStatLog.KIND_NOTICE))
		var text := ""
		if kind == FamilyStatLog.KIND_LEVEL_UP:
			text = FamilyStatLog.level_up_line(int(notice.get("level", 0)))
		else:
			text = FamilyStatLog.experience_line(int(notice.get("amount", 0)))
		if text.is_empty():
			continue
		var style := FamilyStatLog.style(kind)
		var label := Label.new()
		label.text = text
		label.add_theme_font_size_override("font_size", int(style["sizePx"]))
		label.add_theme_color_override("font_color", _color(style["color"]))
		label.add_theme_color_override("font_outline_color", _color(style["outline"]))
		label.add_theme_constant_override("outline_size", int(style["outlinePx"]))
		label.size = Vector2(LINE_WIDTH, FamilyStatLog.LINE_HEIGHT_PX)
		add_child(label)
		_live.push_front({"node": label, "startedMs": now_ms})
	# The oldest go first, so a long fight does not build a column that covers the
	# game it is reporting on.
	while _live.size() > FamilyStatLog.MAX_LINES:
		var dropped: Dictionary = _live.pop_back()
		(dropped["node"] as Label).queue_free()


## Advance every line and retire the ones that are over.
func sync(now_ms: float) -> void:
	var standing: Array = []
	for index in range(_live.size()):
		var record: Dictionary = _live[index]
		var label: Label = record["node"]
		var frame := FamilyStatLog.sample(now_ms - float(record["startedMs"]), index)
		if bool(frame["complete"]):
			label.queue_free()
			continue
		label.position = Vector2(ANCHOR.x, ANCHOR.y + float(frame["offsetY"]))
		label.modulate.a = float(frame["alpha"])
		standing.append(record)
	_live = standing


static func _color(channels: Array) -> Color:
	return Color(float(channels[0]), float(channels[1]), float(channels[2]))

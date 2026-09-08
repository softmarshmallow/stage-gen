class_name PlatformerHud
extends CanvasLayer

## What a run is read by: the health it has left, and the map it is on.
##
## Deliberately small. The panels a published `ui` block would furnish — the
## inventory, the defeat card, the dialogue box — are not here yet, and drawing
## a placeholder for them would be worse than drawing nothing: a plain box is a
## claim that the generated frame is not needed.

const BAR_RECT := Rect2(28.0, 24.0, 320.0, 22.0)
const LABEL_COLOR := Color(1.0, 1.0, 1.0, 0.82)

var _bar: HostGaugeBar = null
var _label: Label = null
var _panel: PlatformerInventoryPanel = null
var _dialogue: PlatformerDialogueBox = null


static func of(package: HostRunDir, manifest: Dictionary) -> PlatformerHud:
	var made := PlatformerHud.new()
	made._panel = PlatformerInventoryPanel.of(package, manifest)
	if made._panel != null:
		made.add_child(made._panel)
	made._dialogue = PlatformerDialogueBox.of(package, manifest)
	if made._dialogue != null:
		made.add_child(made._dialogue)
	made._bar = HostGaugeBar.of(BAR_RECT.size.x, BAR_RECT.size.y)
	made._bar.position = BAR_RECT.position
	made.add_child(made._bar)
	made._label = Label.new()
	made._label.add_theme_font_size_override("font_size", 18)
	made._label.add_theme_color_override("font_color", LABEL_COLOR)
	made._label.position = Vector2(BAR_RECT.position.x, BAR_RECT.end.y + 6.0)
	made.add_child(made._label)
	return made


func sync(world: PlatformerWorld) -> void:
	if _dialogue != null:
		_dialogue.sync(world)
	if _panel != null:
		if bool(world.intent.get("toggleInventory", false)):
			_panel.toggle()
		_panel.sync(world)
	_bar.show_gauge(float(world.player["hp"]), float(world.player["maxHp"]), false)
	_label.text = "%s   %d / %d" % [
		world.map_id, int(world.player["hp"]), int(world.player["maxHp"])
	]

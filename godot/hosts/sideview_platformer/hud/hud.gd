class_name PlatformerHud
extends CanvasLayer

## What a run is read by: the health it has left, the place it is in, and the
## card that names that place as it is entered.
##
## Deliberately small otherwise. A panel a published `ui` block would furnish and
## this build does not draw is better left undrawn than filled with a placeholder:
## a plain box is a claim that the generated frame is not needed.

const BAR_RECT := Rect2(28.0, 24.0, 320.0, 22.0)
const LABEL_COLOR := Color(1.0, 1.0, 1.0, 0.82)

## The banner, across the upper third rather than the middle: a place is named
## over the sky it is entered under, not over the body walking into it.
const BANNER_Y := 168.0
const BANNER_SIZE := 44
const BANNER_COLOR := Color(1.0, 0.945, 0.855)
const BANNER_OUTLINE := Color(0.063, 0.055, 0.078, 0.9)

var _bar: HostGaugeBar = null
var _label: Label = null
var _panel: PlatformerInventoryPanel = null
var _dialogue: PlatformerDialogueBox = null
var _banner: Label = null
## The map the banner is announcing, and when it was raised. Empty until the run
## has entered somewhere.
var _banner_map: String = ""
var _banner_at_ms: float = -1.0


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
	made._banner = Label.new()
	made._banner.add_theme_font_size_override("font_size", BANNER_SIZE)
	made._banner.add_theme_color_override("font_color", BANNER_COLOR)
	made._banner.add_theme_color_override("font_outline_color", BANNER_OUTLINE)
	made._banner.add_theme_constant_override("outline_size", 6)
	made._banner.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	made._banner.position = Vector2(0.0, BANNER_Y)
	made._banner.size = Vector2(PlatformerStage.VIEW_WIDTH, float(BANNER_SIZE) * 1.4)
	made._banner.visible = false
	made.add_child(made._banner)
	return made


func sync(world: PlatformerWorld, now_ms: float) -> void:
	_sync_banner(world, now_ms)
	if _dialogue != null:
		_dialogue.sync(world)
	if _panel != null:
		if bool(world.intent.get("toggleInventory", false)):
			_panel.toggle()
		_panel.sync(world)
	_bar.show_gauge(float(world.player["hp"]), float(world.player["maxHp"]), false)
	# The name the package published, not the id it files the map under. A player
	# reading `road-map` in the corner is reading a database key.
	_label.text = "%s   %d / %d" % [
		_map_name(world), int(world.player["hp"]), int(world.player["maxHp"])
	]


## Raise the card when the run enters somewhere, and take it down on its own
## clock.
##
## The map is watched rather than an event subscribed to, because entering is the
## only thing that changes it and a watch cannot miss one: a gate, a recovery and
## the opening spawn all arrive here the same way.
func _sync_banner(world: PlatformerWorld, now_ms: float) -> void:
	if world.map_id != _banner_map:
		_banner_map = world.map_id
		_banner_at_ms = now_ms
		_banner.text = _map_name(world)
	if _banner_at_ms < 0.0 or _banner.text.is_empty():
		_banner.visible = false
		return
	var card := FamilyBanner.sample(now_ms - _banner_at_ms)
	_banner.visible = not bool(card["done"])
	_banner.modulate.a = float(card["alpha"])


static func _map_name(world: PlatformerWorld) -> String:
	var map: Dictionary = (world.package["maps"] as Dictionary).get(world.map_id, {})
	var named := str(map.get("displayName", "")).strip_edges()
	return world.map_id if named.is_empty() else named

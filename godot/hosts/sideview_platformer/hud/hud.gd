class_name PlatformerHud
extends Control

## What a run is read by: the place it is in, and the card that names it on the way
## in.
##
## The health is deliberately not here any more. It was a three-hundred-pixel bar
## pinned to the top left, which is a different game's interface; this one reads its
## health at the body, under the feet, where the eye already is during a fight. See
## `PlatformerBodyBars`.
##
## Deliberately small otherwise. A panel a published `ui` block would furnish and
## this build does not draw is better left undrawn than filled with a placeholder:
## a plain box is a claim that the generated frame is not needed.

const LABEL_COLOR := Color(1.0, 1.0, 1.0, 0.82)
## Where the map's name sits when the banner has gone.
const LABEL_AT := Vector2(28.0, 24.0)

## The banner, across the upper third rather than the middle: a place is named
## over the sky it is entered under, not over the body walking into it.
const BANNER_Y := 168.0
const BANNER_SIZE := 44
const BANNER_COLOR := Color(1.0, 0.945, 0.855)
const BANNER_OUTLINE := Color(0.063, 0.055, 0.078, 0.9)

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
	made.mouse_filter = Control.MOUSE_FILTER_IGNORE
	made._panel = PlatformerInventoryPanel.of(package, manifest)
	if made._panel != null:
		made.add_child(made._panel)
	made._dialogue = PlatformerDialogueBox.of(package, manifest)
	if made._dialogue != null:
		made.add_child(made._dialogue)
	made._label = Label.new()
	made._label.add_theme_font_size_override("font_size", 18)
	made._label.add_theme_color_override("font_color", LABEL_COLOR)
	made._label.position = LABEL_AT
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


## Set every string this layer draws in the run's own face.
##
## A CanvasLayer is not a Control and carries no theme, so it is handed down to the
## Controls under it rather than inherited — which is also why this is a method and
## not a field: forgetting one is how a panel ends up in a different typeface from
## the panel beside it.
## Open or close the bag.
##
## Called from the *simulation* tick rather than read off the intent here, and
## that is the whole fix: `sync` runs once per drawn frame and the world steps
## thirty times a second, so on any display faster than that the same edge was
## seen several times and the bag opened and shut again before it was ever drawn.
## An edge belongs to the tick that produced it.
func toggle_inventory() -> void:
	if _panel != null:
		_panel.toggle()


func wear(run_theme: Theme) -> void:
	if run_theme == null:
		return
	for child in get_children():
		if child is Control:
			(child as Control).theme = run_theme


func sync(world: PlatformerWorld, now_ms: float) -> void:
	_sync_banner(world, now_ms)
	if _dialogue != null:
		_dialogue.sync(world)
	if _panel != null:
		_panel.sync(world)
	# The name the package published, not the id it files the map under. A player
	# reading `road-map` in the corner is reading a database key.
	_label.text = _map_name(world)


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

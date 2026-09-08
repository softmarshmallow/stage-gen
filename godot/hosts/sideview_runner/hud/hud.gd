class_name RunnerHud
extends CanvasLayer

## The readout: distance, score, the chain, the run's own gauge and the death
## card.
##
## A port of the layout half of `web/lib/sideview-runner/hud.ts`. Every rectangle
## is in the browser's 1280x720 design space, because that is what the manifest's
## published geometry is in.
##
## It reads and never writes. The restart the death card offers is not a button
## this draws: the session system listens for a jump or a restart on the latch,
## so the card says which keys and the keys go through the same path a running
## player's do.

const SCREEN_PIXELS_PER_METER := 100.0

var _readout: Label = null
var _score: Label = null
var _combo: Label = null
var _vitals: HostGaugeBar = null
var _card: Control = null
var _card_text: Label = null
var _max_points: int = 0


## How far the run has come, in whole metres.
static func run_distance_meters(distance_columns: float, tile_px: float) -> int:
	return int(maxf(0.0, floor(distance_columns * tile_px / SCREEN_PIXELS_PER_METER)))


static func format_run_distance(meters: int) -> String:
	return "%d m" % meters


static func format_score(score: float) -> String:
	return "✦ %d" % int(maxf(0.0, floor(score)))


## Nothing at all when the chain is cold: an empty readout is quieter than a
## zero, and a zero invites a player to wonder what they broke.
static func format_combo(chain: int, multiplier: int) -> String:
	if chain <= 0:
		return ""
	if multiplier > 1:
		return "×%d · %d chain" % [multiplier, chain]
	return "%d chain" % chain


static func readout_rect(view_width: float = RunnerContract.VIEW_WIDTH) -> Rect2:
	return Rect2(24.0, 18.0, minf(420.0, view_width - 48.0), 44.0)


## The run's own gauge: half the canvas wide, centred along the top edge.
##
## The browser drew it 180 by 10 in the corner above the distance readout, and
## carried across at that size it was a thing you had to already know was there —
## reported here as "there is no HP bar" on a build that was drawing one. It is
## the only reading a player must not miss, so it gets the top of the screen and
## a width nothing else on it competes with, and the fight's own bar leaves the
## interface entirely to make room.
static func vitals_bar_rect(view_width: float = RunnerContract.VIEW_WIDTH) -> Rect2:
	var width := view_width * 0.5
	return Rect2((view_width - width) / 2.0, 20.0, width, 22.0)


static func death_panel_rect(
	view_width: float = RunnerContract.VIEW_WIDTH,
	view_height: float = RunnerContract.VIEW_HEIGHT
) -> Rect2:
	var width := minf(560.0, view_width * 0.6)
	var height := minf(230.0, view_height * 0.4)
	return Rect2((view_width - width) / 2.0, (view_height - height) / 2.0, width, height)


func build(config: Dictionary) -> void:
	_max_points = int(config["maxVitalPoints"])
	var readout := readout_rect()
	_readout = _label(readout.position + Vector2(0.0, 8.0), 20)
	_score = _label(readout.position + Vector2(0.0, 30.0), 16)
	_combo = _label(readout.position + Vector2(140.0, 30.0), 14)
	# A one-hit-kill package has nothing to draw: a bar that can only ever read
	# full is a promise about mistakes the player does not have.
	if _max_points > 0:
		var bar := vitals_bar_rect()
		_vitals = HostGaugeBar.of(bar.size.x, bar.size.y)
		_vitals.position = bar.position
		add_child(_vitals)
	_build_card()


func sync(world: RunnerWorld) -> void:
	var config := world.config
	_readout.text = format_run_distance(
		run_distance_meters(float(world.avatar["distanceColumns"]), float(config["tilePx"]))
	)
	_score.text = format_score(float(world.score["total"]))
	_combo.text = format_combo(int(world.score["chain"]), int(world.score["multiplier"]))
	if _vitals != null:
		var gauge: Dictionary = world.vitals["gauge"]
		# The bar fades with the immunity window, so the readout itself says a
		# blow connected rather than only the avatar saying it.
		_vitals.show_gauge(
			0.0 if gauge.is_empty() else float(gauge["value"]),
			1.0 if gauge.is_empty() else float(gauge["max"]),
			FamilyVitals.body_is_immune(world.vitals)
		)
	var dead := String(world.run["phase"]) == "dead"
	_card.visible = dead
	if dead:
		var cause: Variant = world.run["endedBy"]
		_card_text.text = "%s\n\n%s\n\nspace or R to run again" % [
			format_score(float(world.score["total"])),
			"the run ended" if cause == null else "ended by %s" % String(cause),
		]


func _build_card() -> void:
	var panel := death_panel_rect()
	_card = Control.new()
	_card.position = panel.position
	_card.size = panel.size
	_card.visible = false
	add_child(_card)
	var backdrop := ColorRect.new()
	backdrop.color = Color(0.05, 0.05, 0.07, 0.86)
	backdrop.size = panel.size
	_card.add_child(backdrop)
	_card_text = Label.new()
	_card_text.size = panel.size
	_card_text.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_card_text.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_card_text.add_theme_font_size_override("font_size", 20)
	_card.add_child(_card_text)


func _label(at: Vector2, size: int) -> Label:
	var label := Label.new()
	label.position = at
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", Color(0.96, 0.95, 0.92))
	label.add_theme_color_override("font_shadow_color", Color(0.0, 0.0, 0.0, 0.7))
	label.add_theme_constant_override("shadow_offset_y", 2)
	add_child(label)
	return label

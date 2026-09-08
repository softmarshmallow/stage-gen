class_name RunnerHud
extends CanvasLayer

## The readout: distance, score, the chain, the two gauge bars and the death card.
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
var _boss: HostGaugeBar = null
var _boss_label: Label = null
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


static func vitals_bar_rect(view_width: float = RunnerContract.VIEW_WIDTH) -> Rect2:
	var readout := readout_rect(view_width)
	return Rect2(readout.position.x, readout.position.y - 12.0, minf(180.0, readout.size.x), 10.0)


## The boss's own bar: top right, opposite the run's readout.
##
## Deliberately not beside the vitals gauge. The two answer different questions —
## how much of the run is left, and how much of the fight is — and stacking them
## would invite reading one for the other at the moment both are moving.
##
## The port drew neither this nor the name above it, so a fight gave the player
## no way to tell a boss two hits from dead from one at full health.
static func boss_bar_rect(view_width: float = RunnerContract.VIEW_WIDTH) -> Rect2:
	var width := minf(320.0, view_width * 0.3)
	return Rect2(view_width - 24.0 - width, 26.0, width, 14.0)


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
	var encounter: Dictionary = config.get("encounter", {})
	if not encounter.is_empty():
		var bar := boss_bar_rect()
		_boss = HostGaugeBar.of(bar.size.x, bar.size.y)
		_boss.position = bar.position
		_boss.visible = false
		add_child(_boss)
		_boss_label = _label(Vector2(bar.position.x, bar.position.y - 22.0), 18)
		_boss_label.add_theme_color_override("font_color", Color(1.0, 0.706, 0.635))
		# The authored band is the 22 pixels above the bar. Seating the text at
		# its bottom keeps it off the bar whatever line height the font has.
		_boss_label.size = Vector2(bar.size.x, 22.0)
		_boss_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		_boss_label.vertical_alignment = VERTICAL_ALIGNMENT_BOTTOM
		_boss_label.visible = false
	_build_card()


## Name the boss the bar is about. Read from the manifest rather than the config,
## because a display name is for a reader and no rule depends on it.
func name_boss(display_name: String) -> void:
	if _boss_label != null:
		_boss_label.text = display_name.to_upper()


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
	if _boss != null:
		# The boss bar exists only while there is a boss to read it about, and
		# goes as soon as the fight is decided rather than lingering through the
		# retreat.
		var fighting: Dictionary = (world.encounter.get("boss", {}) as Dictionary)
		var showing := (
			not fighting.is_empty()
			and String(world.encounter.get("phase", "")) == RunnerEncounterState.PHASE_BATTLE
		)
		_boss.visible = showing
		_boss_label.visible = showing
		if showing:
			var hp: Dictionary = fighting["hp"]
			var struck: Variant = fighting.get("lastHitAtMs")
			_boss.show_gauge(
				float(hp["value"]),
				float(hp["max"]),
				(
					struck != null
					and float(world.vitals.get("clockMs", 0.0)) - float(struck)
					< RunnerEncounterState.HIT_FLASH_MS
				)
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

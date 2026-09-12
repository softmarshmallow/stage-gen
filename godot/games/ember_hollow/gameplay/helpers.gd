class_name SurvivalHelpers
extends RefCounted

## The simulation's pure functions: the ones with no state of their own, ported
## from the viewer's PURE section (index.html:230-478).
##
## `world` parameters are deliberately untyped: `SurvivalWorld` reads this file for
## `NO_SEASON`, and naming `SurvivalWorld` back here would be a cyclic dependency.

## The season a run with no calendar gets, and the season on tick 0.
const NO_SEASON := {
	"season_id": "",
	"display_name": "",
	"snow": 0.0,
	"cold": 0.0,
	"night_share": 0.38,
	"regrow_scale": 1.0,
	"hidden_forage": [],
	"barren": [],
	"look": "",
}

## The two one-line helpers the viewer keeps beside the systems (index.html:586,
## 588): a message for the HUD, and an event for the view and the ear. Both
## also exist as methods on `SurvivalWorld`; these are the free-function spelling the
## systems use.
static func say(world, text: String) -> void:
	world.message = text
	world.message_at = world.time

static func emit(world, event: Dictionary) -> void:
	world.events.append(event)

## 0 at midday, 1 in the deep of the night, with dusk and dawn ramps. The share
## is how much of the day is night (the season's `night_share`): dawn always
## ends at the day's turn, so a longer night is an earlier dusk.
static func night_factor(phase: float, share: float = 0.38) -> float:
	var p := fposmod(phase, 1.0)
	var dusk := maxf(0.2, minf(0.76, 1.0 - share - 0.12))
	if p < dusk:
		return 0.0
	if p < dusk + 0.12:
		return (p - dusk) / 0.12
	if p < 0.88:
		return 1.0
	return 1.0 - (p - 0.88) / 0.12

## The night share the clock should use: the season's, wherever a caller would
## otherwise fall back to the summer default. (The viewer's `N` key and its dev
## clock slider call `nightFactor(phase)` bare and so compute the summer curve
## in winter; the host uses this instead — see the README's deviations.)
static func night_share_of(world) -> float:
	var spec: Dictionary = world.season.get("spec", NO_SEASON)
	var share: Variant = spec.get("night_share")
	if share is float or share is int:
		return float(share)
	return 0.38

## `nightFactor` for a world, always with that world's season share.
static func night_for(world, phase: float) -> float:
	return night_factor(phase, night_share_of(world))

## The season for a day of the world, or the forced one.
## Returns `{id, index, day_in_season}`.
static func season_for(season: Dictionary, day: int) -> Dictionary:
	var calendar: Variant = season.get("calendar")
	var order: Array = []
	if calendar is Dictionary and (calendar as Dictionary).get("order") is Array:
		order = (calendar as Dictionary)["order"]
	if order.is_empty():
		return {"id": "", "index": 0, "day_in_season": day}
	var days := maxi(1, int((calendar as Dictionary).get("days_per_season", 1)))
	var index := int(floor(float(day - 1) / float(days))) % order.size()
	var day_in_season := ((day - 1) % days) + 1
	var force := String(season.get("force", "auto"))
	var specs: Dictionary = season.get("specs", {})
	if force != "auto" and specs.has(force):
		return {"id": force, "index": index, "day_in_season": day_in_season}
	return {"id": String(order[index]), "index": index, "day_in_season": day_in_season}

static func clamp01(value: float) -> float:
	return clampf(value, 0.0, 1.0)

## GLSL smoothstep, the curve the shaders and the fades share.
static func smoothstep01(edge0: float, edge1: float, x: float) -> float:
	if edge1 == edge0:
		return 0.0 if x < edge0 else 1.0
	var t := clamp01((x - edge0) / (edge1 - edge0))
	return t * t * (3.0 - 2.0 * t)

## The dev panel's weather line.
static func describe_weather(world) -> String:
	var w: Dictionary = world.weather
	if String(w.get("condition", "")) == "":
		return "none"
	var next := ""
	var next_strike: float = w.get("next_strike_at", INF)
	if is_finite(next_strike):
		next = " strike in %ds" % int(round(maxf(0.0, next_strike - world.time)))
	return "%s rain %.2f wet %.2f%s (%d)" % [
		String(w.get("mode", "auto")),
		float(w.get("rain", 0.0)),
		float(w.get("wet", 0.0)),
		next,
		int(w.get("strikes", 0)),
	]

## The dev panel's season line.
static func describe_season(world) -> String:
	var s: Dictionary = world.season
	if s.get("calendar") == null:
		return "none"
	var forced := "" if String(s.get("force", "auto")) == "auto" else "forced "
	var look := String(world.look)
	if look == "":
		look = "summer"
	return "%s%s day %d look %s warmth %d" % [
		forced,
		String(s.get("id", "")),
		int(s.get("day_in_season", 1)),
		look,
		int(round(world.player.warmth)),
	]


## Whether a look is the one a `light` interaction leads to: the prop's own lit
## look, the one that IS the fire. A thing placed or built in it is burning
## from the first frame, which is what makes a lit fireplace a light and a
## warmth without anyone having struck it.
static func lit_look(spec: Variant, look: String) -> bool:
	if not (spec is Dictionary):
		return false
	var rows: Variant = (spec as Dictionary).get("interactions", null)
	if not (rows is Array):
		return false
	for row: Variant in (rows as Array):
		if not (row is Dictionary):
			continue
		var block := row as Dictionary
		if str(block.get("verb", "")) == "light" and str(block.get("next_state", "")) == look:
			return true
	return false


## How long a fireplace burns, from the run's rules.
static func campfire_burn_seconds(manifest: Dictionary) -> float:
	var campfire: Variant = (manifest.get("gameplay", {}) as Dictionary).get("campfire", null)
	var burn := 0.0
	if campfire is Dictionary:
		burn = float((campfire as Dictionary).get("burn_seconds", 0.0))
	return burn if burn != 0.0 else 60.0


## How far a burning thing throws its light: twice its own height, and never
## less than the fireplace's authored radius. Fire is the one thing in the
## world whose size the player sets — a torched pine is a bonfire and a tuft is
## a flare — and a pool that ignored that would put a hearth-sized ring under a
## burning wood. `height` is the thing's current look in metres; 0 is the
## fireplace's own answer.
static func fire_radius(manifest: Dictionary, height: float) -> float:
	var campfire: Variant = (manifest.get("gameplay", {}) as Dictionary).get("campfire", null)
	var authored := 0.0
	if campfire is Dictionary:
		authored = float((campfire as Dictionary).get("light_radius_meters", 0.0))
	if authored == 0.0:
		authored = 6.0
	return maxf(authored, height * 2.0)


## The height of the look a prop entity is standing in, in metres, or 0.
static func look_height(spec: Variant, state: String) -> float:
	if not (spec is Dictionary):
		return 0.0
	var states: Variant = (spec as Dictionary).get("states", null)
	if states is Dictionary:
		var look: Variant = (states as Dictionary).get(state, null)
		if look is Dictionary:
			return float((look as Dictionary).get("height_meters", 0.0))
	return float((spec as Dictionary).get("height_meters", 0.0))

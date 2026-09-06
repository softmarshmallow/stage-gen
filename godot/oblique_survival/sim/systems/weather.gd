class_name SysWeather
extends RefCounted

## Weather: a condition of the world, driven on [0, 1] like the clock. The
## world owns the factor, the wetness and the strike clock; every layer of
## presentation reads them. Reads `clock` and `season`, writes `weather` and
## `look` (index.html:1525-1587).

const FORCED_RAIN := {"clear": 0.0, "rain": 0.4, "storm": 1.0, "snow": 0.0}
## Snow is a season, not a spell: the clock never rolls it. In `auto` the
## season holds its factor; the mode or the hold forces it; either way it
## arrives and leaves at its own authored onset and decay.
const FORCED_SNOW := {"clear": 0.0, "rain": 0.0, "storm": 0.0, "snow": 1.0}

static func update(world: World, dt: float) -> void:
	var w := world.weather
	var condition := String(w["condition"])
	if condition == "":
		return
	var weather_block: Dictionary = world.manifest.get("weather", {})
	var spec: Variant = weather_block.get(condition)
	if not (spec is Dictionary):
		return
	var rain_spec: Dictionary = spec
	var season_spec: Dictionary = world.season["spec"]
	var mode := String(w["mode"])

	if mode == "auto":
		if world.time >= float(w["spell_ends_at"]):
			w["wet_spell"] = not bool(w["wet_spell"])
			var key := "wet_spell_seconds" if w["wet_spell"] else "dry_spell_seconds"
			var range_seconds: Array = rain_spec.get(key, [0.0, 0.0])
			var low := float(range_seconds[0])
			var high := float(range_seconds[1])
			w["spell_ends_at"] = world.time + low + float(world.rand.call()) * (high - low)
			w["peak"] = (0.45 + float(world.rand.call()) * 0.55) if w["wet_spell"] else 0.0
		# No rain under the snow: a snowy season's spells fall as the flakes.
		var peak := float(w["peak"]) if w["wet_spell"] else 0.0
		w["target"] = peak * (1.0 - float(season_spec.get("snow", 0.0)))
	elif mode == "hold":
		w["target"] = w["hold"]
	else:
		w["target"] = float(FORCED_RAIN.get(mode, 0.0))

	# The condition arrives at the authored onset and leaves at the decay.
	var target := float(w["target"])
	var rain := float(w["rain"])
	var onset := float(rain_spec.get("onset_seconds", 1.0))
	var decay := float(rain_spec.get("decay_seconds", 1.0))
	var rate := (1.0 / onset) if target > rain else (1.0 / decay)
	if rain < target:
		rain = minf(target, rain + rate * dt)
	else:
		rain = maxf(target, rain - rate * dt)
	w["rain"] = rain

	# The ground soaks over one onset of full rain and dries over dry_seconds.
	var dry := 60.0
	if rain_spec.get("wet") is Dictionary:
		dry = float((rain_spec["wet"] as Dictionary).get("dry_seconds", 60.0))
	if rain > 0.05:
		w["wet"] = minf(1.0, float(w["wet"]) + (rain / onset) * dt)
	else:
		w["wet"] = maxf(0.0, float(w["wet"]) - dt / dry)

	var strike: Variant = rain_spec.get("strike")
	if strike is Dictionary and rain >= float((strike as Dictionary).get("above", 1.0)):
		var interval: Array = (strike as Dictionary).get("interval_seconds", [0.0, 0.0])
		if not is_finite(float(w["next_strike_at"])):
			w["next_strike_at"] = world.time + float(interval[0]) * (0.3 + float(world.rand.call()) * 0.7)
		if world.time >= float(w["next_strike_at"]):
			strike_now(world, strike)
	else:
		w["next_strike_at"] = INF

	var pending: Array = w["pending"]
	if not pending.is_empty():
		var due: Array = []
		var later: Array = []
		for entry: Dictionary in pending:
			if world.time >= float(entry["at"]):
				due.append(entry)
			else:
				later.append(entry)
		if not due.is_empty():
			w["pending"] = later
			for entry: Dictionary in due:
				world.emit({"type": "thunder", "distance": entry["distance"]})

	var snow_spec: Variant = weather_block.get("snow")
	if snow_spec is Dictionary:
		if mode == "hold":
			w["snow_target"] = w["hold_snow"]
		elif mode == "auto":
			w["snow_target"] = float(season_spec.get("snow", 0.0))
		else:
			w["snow_target"] = float(FORCED_SNOW.get(mode, 0.0))
		var snow_target := float(w["snow_target"])
		var snow := float(w["snow"])
		var snow_onset := float((snow_spec as Dictionary).get("onset_seconds", 1.0))
		var snow_decay := float((snow_spec as Dictionary).get("decay_seconds", 1.0))
		var snow_rate := (1.0 / snow_onset) if snow_target > snow else (1.0 / snow_decay)
		if snow < snow_target:
			snow = minf(snow_target, snow + snow_rate * dt)
		else:
			snow = maxf(snow_target, snow - snow_rate * dt)
		w["snow"] = snow

	# The look: the season's once the snow is past a half, the summer sprites
	# otherwise. An instant swap under falling snow; every prop rebuilds once.
	var look := String(season_spec.get("look", "")) if float(w["snow"]) >= 0.5 else ""
	if look != world.look:
		world.look = look
		for entity: Dictionary in world.entities:
			if entity["kind"] == "prop":
				entity["dirty"] = true

## A bolt lands near the player, on land; the thunder follows at the speed of
## feel (index.html:451-471). The eighth failed attempt still strikes, and the
## `cell` draw consumes a value whether or not the search found land.
static func strike_now(world: World, strike: Dictionary) -> void:
	var w := world.weather
	var player := world.player
	var x := player.x
	var z := player.z
	var distance := 0.0
	for _attempt in 8:
		var angle: float = float(world.rand.call()) * TAU
		distance = 5.0 + float(world.rand.call()) * 16.0
		x = player.x + cos(angle) * distance
		z = player.z + sin(angle) * distance
		if world.is_land(x, z):
			break
	world.emit({
		"type": "strike",
		"x": x,
		"z": z,
		"cell": int(floor(float(world.rand.call()) * 4.0)),
		"distance": distance,
	})
	w["flash_at"] = world.time
	w["strikes"] = int(w["strikes"]) + 1
	w["last_strike"] = {"x": x, "z": z, "at": world.time}
	(w["pending"] as Array).append({"at": world.time + 0.2 + distance * 0.05, "distance": distance})
	var interval: Array = strike.get("interval_seconds", [0.0, 0.0])
	var low := float(interval[0])
	var high := float(interval[1])
	w["next_strike_at"] = world.time + low + float(world.rand.call()) * (high - low)

## The flash: two pulses and a tail, the way a real strike reads. Feel, not
## contract (index.html:442-448). The view reads it; the simulation does not.
static func flash_envelope(age: float, seconds: float) -> float:
	if age < 0.0 or age > seconds:
		return 0.0
	if age < 0.05:
		return 1.0
	if age < 0.09:
		return 0.3
	if age < 0.16:
		return 0.9
	return maxf(0.0, 0.9 * (1.0 - (age - 0.16) / maxf(0.01, seconds - 0.16)))

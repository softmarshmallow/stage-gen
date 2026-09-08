class_name PlatformerWorld
extends RefCounted

## Everything one frame of the platformer is, and the shape the golden hashes.
##
## The browser has no object like this: its world *is* a Phaser scene, and the
## twenty-four things below are scene members — some of them sprites, some of
## them closures, some of them text. `replaySnapshot()` in `prepared-scene.ts` is
## the only place they are ever gathered in one record, and that record is the
## contract this class exists to hold. So the port's first move is to make the
## record the thing itself rather than a view taken of a scene.
##
## Two of the twenty-four are a host's business rather than a body's — the
## panel's laid-out slots and the loader's diagnostics — and they are here for
## the same reason the browser publishes them: the golden hashes them, so a port
## that does not carry them cannot be compared. Where they belong once the
## picture exists is the host's question, not this one's.
##
## Nothing here reads a clock, opens a file or draws a random number. A world
## built from one package with one seed is the same world every time, which is
## what lets six hundred frames be compared rather than sampled.

## The map the body is standing in, and whether the package is playable yet.
var ready: bool = false
var loading: bool = true
var map_id: String = ""

## The weapon the run is played with, and the item its shots are spent from.
var weapon_class: String = ""
var ammo_item_id: Variant = null

## Where the view sits. `zoom` is the browser's device-pixel business and is
## dropped by `PARITY_EXCLUDE`, so it is not carried here at all.
var camera: Dictionary = {"scrollX": 0.0, "scrollY": 0.0}

var player: Dictionary = {}
var platforms: Array = []
var climbables: Array = []
var mobs: Array = []
var world_items: Array = []
var projectiles: Array = []
var portals: Array = []

## The bag, and only the bag. Where a panel puts a slot is the panel's, and the
## browser publishes that too — but the golden stopped hashing it the moment a
## second runtime tried to reproduce it, because an icon's laid-out position is
## a reading of one renderer.
var inventory: Dictionary = {"carried": []}

var impact: Dictionary = {}
var stat_log: Dictionary = {}
var defeat_panel: Dictionary = {}
var defeated_at_ms: Variant = null
var progression: Dictionary = {}
var quest_states: Array = []
## The conversation on screen, or null. `dialogue_state` is the runtime session
## behind it and `scenario` the program it walks; neither is published, because
## a session carries bookkeeping only the runtime reads.
var dialogue: Variant = null
var dialogue_state: Dictionary = {}
var scenario: Dictionary = {}

## Every scenario the package publishes, by id. Read when a conversation opens
## and never after.
var scenarios: Dictionary = {}

## The bag behind `inventory.carried`: counts by item id, which is the shape
## `FamilyBag` works in. The published pairs are a reading of it.
var bag: Dictionary = {}

## True while a conversation holds the frame. Every system below the dialogue
## returns early on a held frame, which is how a run stops for a villager.
var hold: bool = false
var npc_prompts: Array = []
var soundtrack: Dictionary = {}

## The package this world was built from, and the frame queue every system
## speaks through. Neither is hashed: one never moves and the other is written
## out separately as the frame's occurrences.
var package: Dictionary = {}
var manifest: Dictionary = {}
var events: KernelEventQueue = null

## The scripted intent for this frame, written by the intent system and read by
## the body. Neutral until something asks for a key.
var intent: Dictionary = {}


## The class a package that names none is played as.
const DEFAULT_WEAPON_CLASS := "melee_dps_v1"

## How tall a gate is drawn, in tiles.
const PORTAL_HEIGHT_TILES := 3.6

## The three readouts a run opens with, before anything has happened to report.
## They are published from the first frame because the browser builds them in
## `create()` and the golden hashes them from frame one.
const IMPACT_AT_REST := {
	"activeCount": 0,
	"disposed": false,
	"enabled": true,
	"entries": [],
	"hitstopUntilMs": 0,
	"reducedMotion": false,
	"swingCount": 0,
}
const STAT_LOG_AT_REST := {"activeCount": 0, "enabled": true, "entries": []}
const DEFEAT_PANEL_AT_REST := {
	"buttonLabel": "Return to safety",
	"buttonState": "normal",
	"confirmRequested": false,
	"title": "You were defeated",
}


## The default a frame starts from: no key down, nothing pressed.
static func neutral_intent() -> Dictionary:
	return {
		"left": false,
		"right": false,
		"up": false,
		"down": false,
		"run": false,
		"jump": false,
		"attack": false,
		"useHealing": false,
		"toggleInventory": false,
	}


## Build the world one package opens on.
##
## `package` is `PlatformerMaps.parse`'s answer and `manifest` the document it
## read, because two of the slices below are declared outside the map half —
## the soundtrack names its first track, and the loader's diagnostics are a
## reading of the presentation block.
static func create(package_in: Dictionary, manifest_in: Dictionary) -> PlatformerWorld:
	var made := PlatformerWorld.new()
	made.package = package_in
	made.manifest = manifest_in
	made.events = KernelEventQueue.new()
	made.intent = neutral_intent()

	var spawn := PlatformerMaps.spawn_position(
		package_in, String(package_in["entrySpawnId"])
	)
	if spawn.is_empty():
		return made
	made.map_id = String(spawn["mapId"])
	made.player = PlatformerPlayer.create(
		float(spawn["x"]), float(spawn["y"]), int(package_in["startingHealth"])
	)
	made.ready = true
	made.loading = false
	made._open_on(made.map_id)
	made.camera = PlatformerCameraSystem.snapped(
		float(made.player["x"]), PlatformerCameraSystem.bounds_of(made)
	)
	made.weapon_class = String(
		(package_in["combat"] as Dictionary).get("weapon_class", DEFAULT_WEAPON_CLASS)
	)
	made.bag = _counts(package_in["startingItemIds"])
	made.inventory = {"carried": bag_as_pairs(made.bag)}
	made.scenarios = _scenarios(manifest_in)
	made.progression = _progression(package_in)
	made.impact = IMPACT_AT_REST.duplicate(true)
	made.stat_log = STAT_LOG_AT_REST.duplicate(true)
	made.defeat_panel = DEFEAT_PANEL_AT_REST.duplicate(true)
	return made


## Everything that changes when the body arrives on a map: the terrain it walks,
## the gates out of it, who is standing on it, and what is playing.
##
## Called at construction and again at every transition, because a map entry is
## the one moment in this genre where most of the world is replaced at once.
func _open_on(opened: String) -> void:
	var map: Dictionary = (package["maps"] as Dictionary).get(opened, {})
	if map.is_empty():
		return
	map_id = opened
	platforms = map["platforms"]
	climbables = map["climbables"]
	portals = _portals(map)
	npc_prompts = _prompts(opened)
	soundtrack = _first_track(map)


## The gates, where they stand and how tall they are drawn.
##
## Height is 3.6 tiles by construction, which any host can compute. Width is not
## here at all: the browser scans the portal artwork's opaque bounding box and
## scales the mouth to its aspect, so a gate's width follows the picture rather
## than the package. That is a thing to gate with a shot, not with a hash.
func _portals(map: Dictionary) -> Array:
	var made: Array = []
	for entry: Variant in (map["endpoints"] as Array):
		var endpoint: Dictionary = entry
		var x := float(endpoint["normalizedX"]) * float(map["worldWidthPx"])
		made.append(
			{
				"portalId": endpoint["anchor"],
				"kind": endpoint["role"],
				"x": x,
				"y": PlatformerMaps.surface_at_x(map, x),
				"h": PORTAL_HEIGHT_TILES * PlatformerMaps.TILE_PX,
			}
		)
	return made


## Who can be spoken to on this map. `visible` is the browser's own reading of a
## text object and `PARITY_EXCLUDE` drops it, so a prompt is its name alone.
func _prompts(opened: String) -> Array:
	var made: Array = []
	for entry: Variant in (package["npcPlacements"] as Array):
		var placement: Dictionary = entry
		if String(placement.get("map_id", "")) != opened:
			continue
		made.append({"npcId": String(placement.get("npc_id", ""))})
	return made


## What this map asks for, queued rather than started: a track begins when the
## audio system is told to begin it, and a world with no sound still says which
## one it would have played.
func _first_track(map: Dictionary) -> Dictionary:
	var tracks: PackedStringArray = map["trackIds"]
	return {
		"current_track_id": null,
		"next_track_id": null if tracks.is_empty() else tracks[0],
		"started": false,
	}


## What the run opens carrying, counted by kind.
static func _counts(item_ids: PackedStringArray) -> Dictionary:
	var made := {}
	for item_id in item_ids:
		made[item_id] = int(made.get(item_id, 0)) + 1
	return made


## The bag as the golden writes it: one `[id, count]` pair per kind, sorted by
## id, because the browser's is a Map walked in sorted key order.
static func bag_as_pairs(counts: Dictionary) -> Array:
	var keys := counts.keys()
	keys.sort()
	var made: Array = []
	for key: Variant in keys:
		made.append([String(key), int(counts[key])])
	return made


## Every scenario the package publishes, parsed once. A program that refuses is
## left out rather than half-read, and the conversation that names it simply is
## not offered — which is the honest answer for a villager with nothing to say.
static func _scenarios(manifest_in: Dictionary) -> Dictionary:
	var made := {}
	for entry: Variant in (manifest_in.get("scenarios", []) as Array):
		var parsed: Variant = FamilyScenarioProgram.parse(entry)
		if KernelRefusal.is_refusal(parsed):
			push_warning("platformer world: %s" % (parsed as KernelRefusal).line())
			continue
		made[String((parsed as Dictionary)["scenarioId"])] = parsed
	return made


## The rank a run opens at, and what the next one costs.
static func _progression(package_in: Dictionary) -> Dictionary:
	var policy: Dictionary = package_in["progression"]
	var level := int(package_in["startingLevel"])
	var maximum_level := int(policy.get("maximum_level", 1))
	return {
		"level": level,
		"totalExperience": 0,
		"experienceIntoLevel": 0,
		"experienceForNext": _cost_of_next(level, maximum_level, policy),
		"maximumHealth": _maximum_health(package_in, level, policy),
	}


## The record the golden hashes: the browser's `replaySnapshot()`, field for
## field, in the browser's own spelling.
##
## `zoom`, `alpha`, `active`, `visible`, `liveSprite`, `renderBounds`,
## `climbAnimationPaused`, `mapLabel`, `banner`, `combatText`, the laid-out
## `slots`, the loader's `diagnostics` and a gate's drawn `w` are what the
## browser publishes and `PARITY_EXCLUDE` drops — every one of them a reading
## taken off a sprite, a camera, a text object or a picture. They are not
## produced here at all, which is the difference between a port and a
## re-implementation of a renderer.
func snapshot() -> Dictionary:
	return {
		"ammoItemId": ammo_item_id,
		"camera": camera,
		"climbables": climbables,
		"defeatPanel": defeat_panel,
		"defeatedAtMs": defeated_at_ms,
		"dialogue": dialogue,
		"impact": impact,
		"inventory": inventory,
		"loading": loading,
		"mapId": map_id,
		"mobs": mobs,
		"npcPrompts": npc_prompts,
		"platforms": platforms,
		"player": PlatformerPlayer.snapshot(player) if not player.is_empty() else null,
		"portals": portals,
		"progression": progression,
		"projectiles": projectiles,
		"questStates": quest_states,
		"ready": ready,
		"soundtrack": soundtrack,
		"statLog": stat_log,
		"weaponClass": weapon_class,
		"worldItems": world_items,
	}


## What the next rank costs, or null at the ceiling. A curve this build does not
## implement is left null rather than guessed: the refusal is the progression
## module's and a world does not overrule it.
static func _cost_of_next(level: int, maximum_level: int, policy: Dictionary) -> Variant:
	if maximum_level <= 1:
		return null
	var cost: Variant = PlatformerProgression.cost_of_next(
		level, String(policy.get("experience_curve", ""))
	)
	return null if KernelRefusal.is_refusal(cost) else cost


## The pool this rank carries, falling back to the authored one when the growth
## is a name this build does not implement.
static func _maximum_health(package_in: Dictionary, level: int, policy: Dictionary) -> int:
	var base_health := int(package_in["startingHealth"])
	var pool: Variant = PlatformerProgression.maximum_health(
		base_health, level, String(policy.get("stat_growth", PlatformerProgression.DEFAULT_GROWTH))
	)
	return base_health if KernelRefusal.is_refusal(pool) else int(pool)

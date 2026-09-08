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

## The gate this frame asked for, taken at the end of it. Empty when none was.
var pending_map: Dictionary = {}

## Every gate this run has already walked through. A door fired once offers
## nothing for the rest of the run — see `PlatformerMapEntrySystem`.
var spent_gates: Dictionary = {}

## The director for the map the run is on, and how many creatures it has stood
## up. The instance number is the seed a creature's own tempo comes from, so it
## counts across the whole run rather than per map.
var population: Dictionary = {}
var next_mob_instance: int = 1

## And how many it has *named*, which is not the same number. Every creature that
## stands up gets a bot id; only the ones the director manages get an instance.
## A gate's boss is stood up by nobody's director, so the two counters part
## company the moment one fires — and a run that used one number for both would
## give the next director creature the name the boss already has.
var next_mob_bot_id: int = 1

## The authored gates, by encounter id, for the life of the session rather than
## of the map: a gate that has ended stays ended when the player walks back onto
## the map it stood on. What *is* map-scoped is the body standing in it, which is
## torn down with the rest of the map.
var set_pieces: Dictionary = {}
var set_piece_bodies: Dictionary = {}

## The rounds in the air, and the next one's name.
var next_shot_id: int = 1

## How many blows this run has resolved. Never reset, because a blow's seed is
## drawn from it and two blows in one place must still differ.
var blow_sequence: int = 0

## What is lying on the ground, and the next drop's name.
var world_items: Array = []
var next_drop_id: int = 0

## What is shaking the view: one entry per kill, for as long as it shakes. Not
## published — the golden drops the spark records these live beside — but the
## offset they produce lands in the camera's own scroll, which is.
var shakes: Array = []

## The offset the view is currently carrying, so the next one replaces it rather
## than adding to it. A tremor that accumulated would walk the view off the map.
var shake_carried: Dictionary = {"x": 0.0, "y": 0.0}

## The blows this frame landed, for a host that draws numbers over them.
##
## Not published and not hashed: the golden records a kill and a blow on the
## body, and says nothing about the ordinary hits between them. A view still has
## to draw those, so they are carried on their own channel rather than smuggled
## into the record a second runtime is compared against.
var blows: Array = []

## The bag that decides what plays next, seeded off the package digest.
var music: FamilyShuffleBag = null

## True while a conversation holds the frame. Every system below the dialogue
## returns early on a held frame, which is how a run stops for a villager.
var hold: bool = false

## This frame's simulation delta, in milliseconds: the frame's own, or zero
## while something is holding it. Written by `clock/step` and read by everything
## that moves.
var simulation_dt: float = 0.0
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
## The impact register at rest. Its sparks are the host's — positioned off a
## scaled sprite's bounds, and excluded from the golden for exactly that reason —
## so what a world carries is the hold: how long a blow stops the frame.
const IMPACT_AT_REST := {
	"disposed": false,
	"enabled": true,
	"hitstopUntilMs": 0,
	"reducedMotion": false,
}
## The stat log's own records go the same way and for the same reason: they are
## floating numbers positioned on a sprite. What is left is whether it is on.
const STAT_LOG_AT_REST := {"enabled": true}
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
	made.music = FamilyShuffleBag.of(
		_track_ids(manifest_in), String(manifest_in.get("package_sha256", ""))
	)
	made.open_on(made.map_id)
	made.camera = PlatformerCameraSystem.snapped(
		float(made.player["x"]),
		PlatformerCameraSystem.bounds_of(made),
		float(made.player["y"])
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
func open_on(opened: String) -> void:
	var map: Dictionary = (package["maps"] as Dictionary).get(opened, {})
	if map.is_empty():
		return
	map_id = opened
	platforms = map["platforms"]
	climbables = map["climbables"]
	portals = _portals(map)
	npc_prompts = _prompts(opened)
	soundtrack = _bind_music(map)
	# A map's creatures are its own: nothing walks through a gate with the body.
	mobs = []
	projectiles = []
	world_items = []
	population = PlatformerPopulation.project(package, opened)
	PlatformerSetPieceSystem.open_on(self)


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


## What this map asks for. The bag is narrowed to the map's own pool and the
## next track is planned rather than started: a track begins when something
## starts it, and a world with no sound still says which one it would have
## played.
##
## A map that has already started the music takes its new track at once, because
## the pool it was playing from is no longer the pool it is standing in.
func _bind_music(map: Dictionary) -> Dictionary:
	var tracks: PackedStringArray = map["trackIds"]
	if tracks.is_empty():
		return soundtrack
	music.bind_pool(tracks)
	if not bool(soundtrack.get("started", false)):
		return {
			"current_track_id": null,
			"next_track_id": _or_null(music.planned()),
			"started": false,
		}
	var playing := music.take()
	return {
		"current_track_id": _or_null(playing),
		"next_track_id": _or_null(music.planned()),
		"started": true,
	}


## Every track the package publishes, in the order it published them.
static func _track_ids(manifest_in: Dictionary) -> PackedStringArray:
	var made := PackedStringArray()
	var block: Dictionary = manifest_in.get("soundtrack", {})
	for entry: Variant in (block.get("tracks", []) as Array):
		made.append(String((entry as Dictionary).get("track_id", "")))
	return made


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
		"mobs": PlatformerMobsSystem.snapshots(self),
		"npcPrompts": npc_prompts,
		"platforms": platforms,
		"player": PlatformerPlayer.snapshot(player) if not player.is_empty() else null,
		"portals": portals,
		"progression": progression,
		"projectiles": PlatformerProjectiles.snapshots(projectiles),
		"questStates": quest_states,
		"ready": ready,
		"soundtrack": soundtrack,
		"statLog": stat_log,
		"weaponClass": weapon_class,
		"worldItems": PlatformerItemsSystem.snapshots(self),
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
		base_health,
		level,
		PlatformerProgression.named(policy, "stat_growth", PlatformerProgression.DEFAULT_GROWTH)
	)
	return base_health if KernelRefusal.is_refusal(pool) else int(pool)


## An exhausted bag plans nothing, and the golden writes that as `null` rather
## than as an empty name. A one-track pool exhausts after one play by design.
static func _or_null(track_id: String) -> Variant:
	return null if track_id.is_empty() else track_id

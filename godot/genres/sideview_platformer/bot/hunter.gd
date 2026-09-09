class_name PlatformerBotHunter
extends RefCounted

## The hunter — the first bot personality, written against the kernel like any
## other.
##
## A port of `web/lib/sideview-platformer/bot-hunter.ts`. Its loop is the one an
## idle RPG runs: stay alive, hit what is in front of you, pick up what falls out
## of it, walk to the next thing, and if there is nothing at all, keep moving so
## the character does not read as broken. Six behaviours, each declining most
## frames.
##
## Every behaviour that has somewhere to be delegates the getting there to
## navigation and never mentions a jump. That is the arrangement worth protecting:
## when the graph learns a new move, the hunter starts using it without being
## touched, and a bot written next week inherits it too.
##
## Targets are chosen by travel cost rather than by distance on screen, so a mob
## two paces away behind a wall loses to one across the shelf that can actually be
## reached. A target that cannot be reached at all is not a target — the behaviour
## declines, and something else takes the frame.

## The numbers a bot is tuned with, all in one record rather than scattered as
## module constants: tuning is the knob a second personality turns, and a
## personality that has to fork constants is not a personality.
##
## How far a swing reaches, how far off the level it still connects, and how close
## the bot walks in are deliberately absent. They are the weapon class's numbers,
## so they arrive on the view as `weaponBand` and no personality forks them.
const TUNING := {
	## Drink at or below this share of the health pool.
	"healAtHealthFraction": 0.45,
	## How far the bot will travel to reach a mob.
	"pursuitRangeUnits": 1400.0,
	## How far it will detour for a drop on the ground.
	"pickupRangeUnits": 520.0,
	## Below this speed while asking to move, the bot counts itself stuck.
	"stuckSpeedUnits": 12.0,
	## Consecutive stuck frames before it tries jumping out.
	"stuckFramesBeforeJump": 12,
	## How close to the map edge a patrol turns around.
	"patrolMarginUnits": 96.0,
	"navSteer": FamilyNavSteering.DEFAULT_TUNING,
}

const PROFILE_ID := "hunter_v1"


## A jump as a last resort, when the world disagrees with the graph.
##
## The graph models terrain, decks and declared climbables — not props, not other
## actors, not a corner the collision resolver rounds differently than the
## derivation did. Something the model does not contain can still wedge the
## character against it, and no amount of replanning helps, because the plan is
## correct and the world is the surprise. A hop costs a fraction of a second when
## it was unnecessary and frees the character when it was.
static func _unstick(intent: Dictionary, context: Dictionary) -> Dictionary:
	var tuning: Dictionary = context["tuning"]
	if int((context["memory"] as Dictionary)["stuckFrames"]) < int(tuning["stuckFramesBeforeJump"]):
		return intent
	if bool(intent["left"]) == bool(intent["right"]):
		return intent
	var hopped := intent.duplicate()
	hopped["jump"] = true
	return hopped


## How to move one step toward a point, or an empty dictionary when there is no
## way there at all.
##
## The plan is recomputed from scratch every frame. There is no stored path to
## invalidate when the target moves, the character is knocked back, or the shelf it
## was heading for turns out to be the wrong one — which for a graph this size is
## both simpler and cheaper than keeping one honest. Returns `{intent, cost}`,
## where the cost is seconds of travel by the navigation model's own reckoning.
static func plan_travel(context: Dictionary, target: Dictionary) -> Dictionary:
	var view: Dictionary = context["view"]
	var standing_on := String(context["standingOn"])
	var destination := FamilyNavGraph.locate(
		view["navigation"], float(target["x"]), float(target["y"])
	)
	if destination.is_empty() or standing_on.is_empty():
		return {}
	var found := FamilyNavGraph.reach_of(context["reach"], String(destination["id"]))
	if found.is_empty():
		return {}
	var link: Dictionary = {} if String(destination["id"]) == standing_on else found["firstLink"]
	var self_view: Dictionary = view["self"]
	var capabilities: Dictionary = context["capabilities"]
	var approach := (
		absf(float(target["x"]) - float(self_view["x"])) / float(capabilities["runSpeed"])
	)
	var steered := PlatformerBotNavigation.steer(
		PlatformerBotNavigation.agent_state(self_view),
		link,
		float(target["x"]),
		capabilities,
		(context["tuning"] as Dictionary)["navSteer"]
	)
	return {"intent": _unstick(steered, context), "cost": float(found["cost"]) + approach}


## The cheapest candidate to travel to, keeping the current one when it is still
## worth keeping.
##
## Stickiness matters more than it looks: two mobs at nearly equal cost would
## otherwise swap the lead every few frames as the character moves, and a bot that
## turns around twice a second never arrives anywhere. The incumbent is dropped
## only when it is gone or out of range. Returns `{target, plan}` or an empty
## dictionary.
static func _select_target(context: Dictionary, candidates: Array, range_units: float) -> Dictionary:
	var self_view: Dictionary = (context["view"] as Dictionary)["self"]
	var incumbent_id := String((context["memory"] as Dictionary)["targetId"])
	var in_range: Array = []
	for entry: Variant in candidates:
		var candidate: Dictionary = entry
		if PlatformerBotView.horizontal_distance(self_view, candidate) <= range_units:
			in_range.append(candidate)
	for entry: Variant in in_range:
		var candidate: Dictionary = entry
		if String(candidate["id"]) != incumbent_id:
			continue
		var plan := plan_travel(context, candidate)
		if not plan.is_empty():
			return {"target": candidate, "plan": plan}
		break
	var best: Dictionary = {}
	for entry: Variant in in_range:
		var candidate: Dictionary = entry
		var plan := plan_travel(context, candidate)
		if plan.is_empty():
			continue
		if best.is_empty():
			best = {"target": candidate, "plan": plan}
			continue
		var best_cost := float((best["plan"] as Dictionary)["cost"])
		var cost := float(plan["cost"])
		var better := (
			cost < best_cost
			or (
				cost == best_cost
				and String(candidate["id"]) < String((best["target"] as Dictionary)["id"])
			)
		)
		if better:
			best = {"target": candidate, "plan": plan}
	return best


## Do nothing, loudly.
##
## Defeat is not a state the other behaviours are asked to know about; this one
## outbids all of them so they never see it. The host owns what happens next — the
## death animation runs, recovery is timed, and the world is rebuilt around a fresh
## character — and a bot pressing keys through any of that would be arguing with it.
static func consider_stand_down(context: Dictionary) -> Dictionary:
	var view: Dictionary = context["view"]
	var self_view: Dictionary = view["self"]
	var nodes: Array = (view["navigation"] as Dictionary)["nodes"]
	var defeated := bool(self_view["defeated"])
	if not (defeated or String(context["standingOn"]).is_empty() or nodes.is_empty()):
		return {}
	return {
		"goal": PlatformerBotKernel.GOAL_STAND_DOWN,
		"priority": PlatformerBotKernel.PRIORITY[PlatformerBotKernel.GOAL_STAND_DOWN],
		"intent": PlatformerWorld.neutral_intent(),
		"targetId": PlatformerBotKernel.NO_TARGET,
		"reason": "defeated" if defeated else "nowhere to stand",
	}


## Drink when low, and only when a drink would land.
##
## The request is refused by the health pool at full health and while defeated, and
## the consumables system only opens the bag once the restore connects, so a
## mistimed bid costs nothing. Bidding above combat rather than below it is the
## whole reason the bot survives a hunting ground: a heal deferred until the mob in
## front is dead is a heal that arrives after the character does.
static func consider_heal(context: Dictionary) -> Dictionary:
	var view: Dictionary = context["view"]
	var self_view: Dictionary = view["self"]
	if not bool(view["healingCarried"]) or int(self_view["hp"]) >= int(self_view["maxHp"]):
		return {}
	var tuning: Dictionary = context["tuning"]
	if PlatformerBotView.health_fraction(self_view) > float(tuning["healAtHealthFraction"]):
		return {}
	return {
		"goal": PlatformerBotKernel.GOAL_HEAL,
		"priority": PlatformerBotKernel.PRIORITY[PlatformerBotKernel.GOAL_HEAL],
		"intent": PlatformerBotNavigation.intent_of({"useHealing": true}),
		"targetId": PlatformerBotKernel.NO_TARGET,
		"reason": "hp %d/%d" % [int(self_view["hp"]), int(self_view["maxHp"])],
	}


## Attack what is already in range, and hold the distance the weapon wants.
##
## `attack` is edge-triggered and the controller refuses a fresh action while one
## is running, so asking every frame is not mashing: it produces exactly the
## animation's own rate, the same cap a person hits. Facing is corrected by
## pressing a direction for a frame, because facing follows movement in this
## controller and there is no other way to turn on the spot.
##
## The three distances come from the weapon class on the view, not from this
## behaviour. A swinging class has no minimum, so its back-off branch can never
## fire and it walks all the way in; a throwing class stops at arm's length of the
## creature it is killing. Nothing here knows which class it is holding, which is
## what makes a third one free.
static func consider_engage(context: Dictionary) -> Dictionary:
	var view: Dictionary = context["view"]
	if not bool(view["combatEnabled"]):
		return {}
	var self_view: Dictionary = view["self"]
	var band: Dictionary = view["weaponBand"]
	# A class that spends a round and is carrying none does not stand there
	# pressing the key. It declines outright, so collect, pursue and patrol can win
	# the auction instead — otherwise an unattended run stops forever the moment the
	# bag empties, with nothing logged and no gate red.
	if bool(band["requiresAmmo"]) and not bool(view["ammoCarried"]):
		return {}
	var release := float(band["releaseHeightUnits"])
	var reachable: Array = []
	for entry: Variant in (view["threats"] as Array):
		var threat: Dictionary = entry
		if PlatformerBotView.horizontal_distance(self_view, threat) > float(band["maximumUnits"]):
			continue
		if not PlatformerBotView.same_foot_level(
			self_view, threat, float(band["verticalToleranceUnits"])
		):
			continue
		# Distance and foot level say a creature is worth attacking; they say
		# nothing about what is between the two. A creature on a ledge satisfies
		# both while the ledge face stands in the way, and every throw dies in it —
		# so a class that throws asks the terrain too. Melee declares no release
		# height and skips the test: a swing has no flight path.
		if release >= 0.0:
			var clear := PlatformerBotView.line_of_fire_clear(
				view["terrain"],
				float(self_view["x"]),
				float(threat["x"]),
				float(self_view["y"]) - release
			)
			if not clear:
				continue
		reachable.append(threat)
	if reachable.is_empty():
		return {}
	var incumbent_id := String((context["memory"] as Dictionary)["targetId"])
	var target: Dictionary = {}
	for entry: Variant in reachable:
		if String((entry as Dictionary)["id"]) == incumbent_id:
			target = entry
			break
	if target.is_empty():
		reachable.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
			var left := PlatformerBotView.horizontal_distance(self_view, a)
			var right := PlatformerBotView.horizontal_distance(self_view, b)
			if left != right:
				return left < right
			return String(a["id"]) < String(b["id"]))
		target = reachable[0]
	var distance := PlatformerBotView.horizontal_distance(self_view, target)
	var want_facing := PlatformerBotView.facing_toward(self_view, float(target["x"]))
	var turning := want_facing != String(self_view["facing"])
	var closing := distance > float(band["approachUnits"])
	var backing := distance < float(band["minimumUnits"])
	# The step and the facing are separate requests, and they disagree while
	# backing away. Facing otherwise follows the movement key, so pressing away from
	# the target would turn the character around — and the blow is resolved against
	# the facing at the frame it leaves, so the whole retreat would be spent
	# attacking in the wrong direction. `face` is what keeps the target in front.
	var step_facing := want_facing
	if backing:
		step_facing = (
			PlatformerBotView.FACING_RIGHT
			if want_facing == PlatformerBotView.FACING_LEFT
			else PlatformerBotView.FACING_LEFT
		)
	var stepping := turning or closing or backing
	var reason := "in reach"
	if turning:
		reason = "turning onto target"
	elif backing:
		reason = "holding distance"
	return {
		"goal": PlatformerBotKernel.GOAL_ENGAGE,
		"priority": PlatformerBotKernel.PRIORITY[PlatformerBotKernel.GOAL_ENGAGE],
		"intent": PlatformerBotNavigation.intent_of(
			{
				"left": stepping and step_facing == PlatformerBotView.FACING_LEFT,
				"right": stepping and step_facing == PlatformerBotView.FACING_RIGHT,
				"face": want_facing,
				"attack": true,
			}
		),
		"targetId": String(target["id"]),
		"reason": reason,
	}


## Walk over what fell out of the last kill.
##
## Above pursuit and below combat, which is the order that actually banks loot:
## finish the mob in front, sweep up what it dropped, then go find the next one.
## Ranked above combat it would break off a fight to stand on a drop; ranked below
## pursuit it would walk away from every one of them.
static func consider_collect(context: Dictionary) -> Dictionary:
	var view: Dictionary = context["view"]
	var tuning: Dictionary = context["tuning"]
	var selection := _select_target(
		context, view["pickups"], float(tuning["pickupRangeUnits"])
	)
	if selection.is_empty():
		return {}
	var plan: Dictionary = selection["plan"]
	return {
		"goal": PlatformerBotKernel.GOAL_COLLECT,
		"priority": PlatformerBotKernel.PRIORITY[PlatformerBotKernel.GOAL_COLLECT],
		"intent": plan["intent"],
		"targetId": String((selection["target"] as Dictionary)["id"]),
		"reason": "drop %.2fs away" % float(plan["cost"]),
	}


## Go to the cheapest mob that can actually be reached from here.
static func consider_pursue(context: Dictionary) -> Dictionary:
	var view: Dictionary = context["view"]
	if not bool(view["combatEnabled"]):
		return {}
	var tuning: Dictionary = context["tuning"]
	var selection := _select_target(
		context, view["threats"], float(tuning["pursuitRangeUnits"])
	)
	if selection.is_empty():
		return {}
	var plan: Dictionary = selection["plan"]
	return {
		"goal": PlatformerBotKernel.GOAL_PURSUE,
		"priority": PlatformerBotKernel.PRIORITY[PlatformerBotKernel.GOAL_PURSUE],
		"intent": plan["intent"],
		"targetId": String((selection["target"] as Dictionary)["id"]),
		"reason": "mob %.2fs away" % float(plan["cost"]),
	}


## When there is nothing to do, walk.
##
## The floor of the roster, and the only behaviour that never declines. Its job is
## partly to find mobs that have not spawned into range yet and partly to be
## visibly alive: a character standing perfectly still reads as a hung frame, and
## someone watching cannot tell the difference. Direction is flipped by the map
## edge in the kernel's bookkeeping, not decided here.
static func consider_patrol(context: Dictionary) -> Dictionary:
	var sign_of := int((context["memory"] as Dictionary)["patrolSign"])
	var walking := PlatformerBotNavigation.intent_of(
		{"left": sign_of < 0, "right": sign_of > 0}
	)
	return {
		"goal": PlatformerBotKernel.GOAL_PATROL,
		"priority": PlatformerBotKernel.PRIORITY[PlatformerBotKernel.GOAL_PATROL],
		"intent": _unstick(walking, context),
		"targetId": PlatformerBotKernel.NO_TARGET,
		"reason": "sweeping right" if sign_of > 0 else "sweeping left",
	}


## Declaration order is the tiebreak between equal bids, so it is part of the
## design.
static func roster() -> Array:
	return [
		{"id": "stand_down", "consider": Callable(PlatformerBotHunter, "consider_stand_down")},
		{"id": "heal", "consider": Callable(PlatformerBotHunter, "consider_heal")},
		{"id": "engage", "consider": Callable(PlatformerBotHunter, "consider_engage")},
		{"id": "collect", "consider": Callable(PlatformerBotHunter, "consider_collect")},
		{"id": "pursue", "consider": Callable(PlatformerBotHunter, "consider_pursue")},
		{"id": "patrol", "consider": Callable(PlatformerBotHunter, "consider_patrol")},
	]


## A named bot: a repertoire, a temperament, and a body.
static func profile() -> Dictionary:
	return {
		"id": PROFILE_ID,
		"tuning": TUNING,
		"roster": roster(),
		"capabilities": PlatformerBotNavigation.capabilities(),
	}


## A profile with some behaviours switched off.
##
## This is the whole of per-behaviour toggling: the roster is a list, and a bot
## that should not loot is a bot whose roster has no `collect` in it. No behaviour
## gains an `enabled` flag, and none of them learns that it can be disabled.
static func profile_without(base: Dictionary, disabled_ids: PackedStringArray) -> Dictionary:
	if disabled_ids.is_empty():
		return base
	var kept: Array = []
	for entry: Variant in (base["roster"] as Array):
		var behavior: Dictionary = entry
		if not disabled_ids.has(String(behavior["id"])):
			kept.append(behavior)
	var sorted := disabled_ids.duplicate()
	sorted.sort()
	var made := base.duplicate()
	made["id"] = "%s-%s" % [base["id"], "-".join(sorted)]
	made["roster"] = kept
	return made

class_name PlatformerBot
extends RefCounted

## The bot as the host sees it: hand it a view, get back an intent.
##
## A port of `web/lib/sideview-platformer/bot.ts`, and deliberately a thin shell
## over `PlatformerBotKernel.decide`. Everything that decides anything is a static
## function in the kernel, the roster or the navigator; this class only holds the
## two frames' worth of state those functions need handed back to them, and turns
## the per-frame navigation queries into one call. Keeping it thin is what makes
## the system portable — a runtime with a different object model reimplements this
## file and reuses everything under it.

## How long a person keeps the controls after their last input.
##
## Without a hold the bot would resume on the very first frame a key is released
## and drag the character back to whatever it was doing, which makes manual
## inspection impossible. With one, a touch of any key is a takeover that lasts as
## long as it takes to think, and walking away from the keyboard returns control on
## its own — no mode to enter, none to remember to leave.
const HUMAN_OVERRIDE_HOLD_MS := 1500.0

const SOURCE_HUMAN := "human"
const SOURCE_BOT := "bot"

## No input yet this session. Negative rather than null, the same convention the
## traversal family uses for a coyote window that is not open.
const NEVER := -1.0

var _profile: Dictionary = {}
var _memory: Dictionary = PlatformerBotKernel.initial_memory()
var _previous_intent: Dictionary = PlatformerWorld.neutral_intent()
var _decision: Dictionary = {}


static func of(profile: Dictionary) -> PlatformerBot:
	var made := PlatformerBot.new()
	made._profile = profile
	return made


## Whether a source is asking for nothing at all this frame.
##
## Every field of the record handed in, not merely the ten the body reads. A host
## samples the four scene keys onto the same record — opening a conversation,
## advancing it, asking a gate to open — and those are a person at the keyboard as
## surely as a movement key is. Checking only the body's fields would let someone
## talk to a villager while the bot walked them away from it.
static func is_neutral_intent(intent: Dictionary) -> bool:
	var neutral := PlatformerWorld.neutral_intent()
	for key: Variant in intent:
		# A field the body's own record does not name is a request, and a request
		# is neutral only when it is not being made.
		var at_rest: Variant = neutral[key] if neutral.has(key) else false
		if intent[key] != at_rest:
			return false
	return true


## Decide who is driving this frame, before either of them is asked for anything.
##
## The rule is one sentence — a person who is touching the keys, or who touched
## them recently, has the controls; otherwise the bot does. It answers with a
## source rather than with an intent so the bot is never asked to think on a frame
## it does not own: a decision it did not drive would still advance its memory, and
## the next frame it did own would be reasoning from a move it never made.
##
## Returns `{source, humanInputAtMs}`, the second carried forward as the next
## frame's `last_human_input_at_ms`.
static func resolve_control(
	human_intent: Dictionary,
	enabled: bool,
	now_ms: float,
	last_human_input_at_ms: float,
	hold_ms: float = HUMAN_OVERRIDE_HOLD_MS
) -> Dictionary:
	var human_acting := not is_neutral_intent(human_intent)
	var human_input_at_ms := now_ms if human_acting else last_human_input_at_ms
	if not enabled:
		return {"source": SOURCE_HUMAN, "humanInputAtMs": human_input_at_ms}
	var holding := human_input_at_ms >= 0.0 and now_ms - human_input_at_ms < hold_ms
	return {
		"source": SOURCE_BOT if not (human_acting or holding) else SOURCE_HUMAN,
		"humanInputAtMs": human_input_at_ms,
	}


func last_decision() -> Dictionary:
	return _decision


func profile_id() -> String:
	return String(_profile.get("id", ""))


## Swap the repertoire without losing the map bearings the memory holds.
func set_profile(profile: Dictionary) -> void:
	_profile = profile


func decide(view: Dictionary) -> Dictionary:
	var self_view: Dictionary = view["self"]
	var standing := FamilyNavGraph.locate(
		view["navigation"], float(self_view["x"]), float(self_view["y"])
	)
	var standing_id := "" if standing.is_empty() else String(standing["id"])
	var reach: Array = [] if standing.is_empty() else FamilyNavGraph.reach(
		view["navigation"], standing_id
	)
	var decision := PlatformerBotKernel.decide(
		view, _memory, _previous_intent, _profile, reach, standing_id
	)
	_memory = decision["memory"]
	_previous_intent = decision["intent"]
	_decision = decision
	return decision


## Stand down for a frame a person owns.
##
## The stuck counter and the current target are cleared because both describe what
## *the bot* was doing, and neither survives someone else walking the character
## somewhere. The patrol direction survives on purpose: it is a fact about the map,
## and forgetting it makes a resumed bot walk back into the wall it just turned
## away from.
func suspend() -> void:
	_memory = _memory.duplicate()
	_memory["targetId"] = PlatformerBotKernel.NO_TARGET
	_memory["stuckFrames"] = 0
	_previous_intent = PlatformerWorld.neutral_intent()
	_decision = {}


## Forget everything. Called when the world under the bot is replaced.
func reset() -> void:
	_memory = PlatformerBotKernel.initial_memory()
	_previous_intent = PlatformerWorld.neutral_intent()
	_decision = {}

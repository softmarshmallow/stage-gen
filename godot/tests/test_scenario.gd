extends RefCounted

## The scenario runtime: the machine both the dialogue scene and the case play.
##
## Like the room, a scenario has no clock — a transition is a keypress, not a
## step — so there is no roster and no sealed order to assert. What there is
## instead is the **settle**, and most of what is checked here is that: the walk
## through invisible statements that makes "what is drawn" a pure function of
## the state rather than something a view re-derives by peeking ahead.
##
## The scripted run is proved elsewhere and harder: `tools/scene_parity.gd`
## replays the browser's own twenty-five actions and every digest is identical.

func run(h: TestHarness) -> void:
	var parsed: Variant = FamilyScenarioProgram.parse(_fixture())
	h.assert_true(not KernelRefusal.is_refusal(parsed), "the ferry program parses")
	if KernelRefusal.is_refusal(parsed):
		return
	var program: Dictionary = parsed
	_contract(h, program)
	_settle(h, program)
	_branching(h, program)


func _contract(h: TestHarness, program: Dictionary) -> void:
	h.assert_eq(String(program["entry"]), "opening", "the ferry opens on the pier")
	h.assert_eq((program["blocks"] as Array).size(), 11, "and has eleven blocks")
	h.assert_eq((program["endings"] as Array).size(), 3, "and three ways it can end")
	var raw: Dictionary = _fixture()
	var wrong := raw.duplicate(true)
	wrong["kind"] = "pointclick-room-runtime-v3"
	h.assert_true(
		KernelRefusal.is_refusal(FamilyScenarioProgram.parse(wrong)),
		"a document of another kind is refused rather than half-read"
	)
	# A scenario that enters a block it does not publish would settle nowhere and
	# draw nothing, so it is refused by name at the door.
	var lost := raw.duplicate(true)
	lost["entry"] = "nowhere"
	var refusal: Variant = FamilyScenarioProgram.parse(lost)
	h.assert_true(KernelRefusal.is_refusal(refusal), "an entry nothing publishes is refused")
	if KernelRefusal.is_refusal(refusal):
		h.assert_eq((refusal as KernelRefusal).path, "entry", "and the refusal names the field")


func _settle(h: TestHarness, program: Dictionary) -> void:
	var opening := FamilyScenarioRuntime.initial_turn(program)
	var state: Dictionary = opening["state"]
	# The opening block begins with a stage, an audio cue and a line. Only the
	# line stops, and the two invisible statements before it have already run.
	h.assert_eq(String(state["stage"]), "pier_dusk", "the settle staged the pier")
	h.assert_true((state["tracks"] as Array).has("harbor_wind"), "and started the wind")
	var view := FamilyScenarioRuntime.view(program, state)
	h.assert_eq(String(view["kind"]), "line", "and stopped on a line")
	h.assert_true(
		(state["seen"] as Array).has(FamilyScenarioRuntime.statement_id("opening", int(state["index"]))),
		"the line it stopped on is marked seen"
	)
	# Every invisible statement it walked through is an occurrence, so a consumer
	# knows what changed without diffing two states.
	var kinds := PackedStringArray()
	for entry: Variant in (opening["events"] as Array):
		kinds.append(String((entry as Dictionary)["type"]))
	h.assert_true(kinds.has("scenario/staged"), "the settle reports what it staged")
	h.assert_true(kinds.has("scenario/audio-changed"), "and what it played")
	h.assert_eq(
		kinds[kinds.size() - 1], "scenario/presented", "and ends by saying what is on screen"
	)

	# An action a moment does not offer moves nothing and says nothing, which is
	# what makes "nothing happened" checkable rather than an unchanged object a
	# caller has to notice by identity.
	var stray := FamilyScenarioRuntime.reduce_turn(program, state, {"kind": "choose", "option": 0})
	h.assert_eq((stray["events"] as Array).size(), 0, "a choice at a line reports nothing")

	# Two advances: the opening is a stage, a cue, a line, a `show`, a second
	# line and then the choice, and only the two lines stop.
	var once: Dictionary = FamilyScenarioRuntime.reduce(program, state, {"kind": "advance"})
	h.assert_eq(
		String(FamilyScenarioRuntime.view(program, once)["kind"]),
		"line",
		"the first advance reaches the second line, walking the `show` on the way"
	)
	var at_choice: Dictionary = FamilyScenarioRuntime.reduce(program, once, {"kind": "advance"})
	var choice := FamilyScenarioRuntime.view(program, at_choice)
	h.assert_eq(String(choice["kind"]), "choice", "and the second reaches the choice")
	h.assert_eq((choice["options"] as Array).size(), 2, "with both options offered")
	# A line that names an expression re-dresses its speaker; a `show` staged her.
	var mara := FamilyScenarioRuntime.actor(at_choice, "mara")
	h.assert_true(not mara.is_empty(), "Mara is on stage by the time she speaks")
	h.assert_eq(String(mara["slot"]), "center", "where the author put her")


func _branching(h: TestHarness, program: Dictionary) -> void:
	var state := FamilyScenarioRuntime.initial_state(program)
	state = FamilyScenarioRuntime.reduce(program, state, {"kind": "advance"})
	state = FamilyScenarioRuntime.reduce(program, state, {"kind": "advance"})
	# Ring the bell: the first option, which sets a flag the ending reads.
	var rang := FamilyScenarioRuntime.reduce_turn(program, state, {"kind": "choose", "option": 0})
	var after: Dictionary = rang["state"]
	h.assert_eq(String(after["label"]), "ringing", "choosing the bell goes to the bell")
	var causes := PackedStringArray()
	for entry: Variant in (rang["events"] as Array):
		var event: Dictionary = entry
		if String(event["type"]) == "scenario/branched":
			causes.append(String(event["cause"]))
	h.assert_true(causes.has("choice"), "and the branch says a choice caused it")

	# Walk to an ending and check the run stops there: an action past an outcome
	# moves nothing, because the scenario is over.
	#
	# The walk answers choices as well as advancing, and it has to: advancing at
	# a choice is one of the actions that deliberately moves nothing, so a walk
	# that only advanced would spin against the first branch rather than reach an
	# ending.
	var walked := after
	for _step in 60:
		if FamilyScenarioRuntime.is_finished(walked):
			break
		var showing := FamilyScenarioRuntime.view(program, walked)
		var action := (
			{"kind": "choose", "option": 0}
			if String(showing.get("kind", "")) == "choice"
			else {"kind": "advance"}
		)
		walked = FamilyScenarioRuntime.reduce(program, walked, action)
	h.assert_true(FamilyScenarioRuntime.is_finished(walked), "the run reaches an ending")
	var end_view := FamilyScenarioRuntime.view(program, walked)
	h.assert_eq(String(end_view["kind"]), "end", "and draws the end card")
	h.assert_true(String(end_view["label"]) != "", "which is labelled")
	var past := FamilyScenarioRuntime.reduce_turn(program, walked, {"kind": "advance"})
	h.assert_eq((past["events"] as Array).size(), 0, "and nothing happens after it")

	# A restart is the opening again, whatever was set before it.
	var restarted := FamilyScenarioRuntime.reduce(program, walked, {"kind": "restart"})
	h.assert_eq(String(restarted["label"]), String(program["entry"]), "a restart re-enters")
	h.assert_true(restarted["outcome"] == null, "and the outcome is gone")
	h.assert_eq((restarted["flags"] as Array).size(), 0, "and so are the flags")


func _fixture() -> Variant:
	var file := FileAccess.open("res://tests/fixtures/dialogue_scene/program.json", FileAccess.READ)
	if file == null:
		return null
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	file.close()
	return parsed

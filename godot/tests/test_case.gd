extends RefCounted

## The case: several leaves played in order, with facts crossing between them.
##
## What is checked here is the layer none of the leaves can see — the beat order,
## the facts that survive a boundary, the save written the moment a beat is
## entered, and the Continue a save offers. The scripted episode itself is proved
## by `tools/case_parity.gd`, which replays the browser's own nineteen actions.

func run(h: TestHarness) -> void:
	var parsed: Variant = CaseDocument.parse(_fixture())
	h.assert_true(not KernelRefusal.is_refusal(parsed), "the demo case parses")
	if KernelRefusal.is_refusal(parsed):
		return
	var document: Dictionary = parsed
	_contract(h, document)
	_facts(h, document)
	_episode(h, document)


func _contract(h: TestHarness, document: Dictionary) -> void:
	h.assert_eq((document["beats"] as Array).size(), 3, "the demo case has three beats")
	h.assert_eq(String(document["entry"]), "demo_supper", "and opens on the supper")
	h.assert_eq(CaseDocument.beat_number(document, "demo_room"), 2, "the room is the second")
	var raw: Dictionary = _fixture()
	var wrong := raw.duplicate(true)
	wrong["kind"] = "scenario-program-v2"
	h.assert_true(
		KernelRefusal.is_refusal(CaseDocument.parse(wrong)),
		"a document of another kind is refused rather than half-read"
	)
	var lost := raw.duplicate(true)
	lost["entry"] = "nowhere"
	h.assert_true(
		KernelRefusal.is_refusal(CaseDocument.parse(lost)),
		"an entry nothing publishes is refused"
	)


func _facts(h: TestHarness, document: Dictionary) -> void:
	# A fact is the only thing that crosses a boundary, and only a name the case
	# declared: a leaf's own flag cannot become a fact by being exported.
	var merged := CaseDocument.merge_facts(
		document,
		PackedStringArray(["saw_the_card"]),
		PackedStringArray(["heard_the_toast", "a_flag_the_leaf_invented"])
	)
	h.assert_true(merged.has("heard_the_toast"), "a declared export crosses")
	h.assert_true(merged.has("saw_the_card"), "and what was already carried stays")
	h.assert_true(
		not merged.has("a_flag_the_leaf_invented"),
		"a name the case never declared does not become a fact by being exported"
	)
	h.assert_eq(merged[0], "heard_the_toast", "and the set is sorted")

	# An outcome the case declares no edge for ends it, rather than stranding a
	# player on a screen with nothing to press. That is the producer's proof
	# failing, not the player's problem.
	var progress := CaseDocument.initial_progress(document)
	h.assert_true(
		CaseDocument.advance(document, progress, "an_outcome_nothing_names", PackedStringArray()).is_empty(),
		"an outcome with no edge ends the case"
	)


func _episode(h: TestHarness, document: Dictionary) -> void:
	var at := "2026-09-08T04:00:00.000Z"
	var state := CaseRuntime.initial(document)
	h.assert_eq(String(state["phase"]), "reading_save", "a case opens by looking for a save")

	# Opened with nothing saved: straight to playing.
	var opened := CaseRuntime.reduce(document, "demo", state, {"kind": "opened", "saved": null}, at)
	state = opened["state"]
	h.assert_eq(String(state["phase"]), "playing", "with no save it plays")
	h.assert_true(state["resume"] == null, "and offers no Continue")

	# A save whose beat this build no longer carries is not a save.
	var stale := CaseRuntime.reduce(
		document,
		"demo",
		CaseRuntime.initial(document),
		{"kind": "opened", "saved": {"beatId": "a_beat_that_went_away", "backlog": []}},
		at
	)
	h.assert_eq(
		String((stale["state"] as Dictionary)["phase"]),
		"playing",
		"a save naming a beat this build dropped offers a fresh episode, not a dead Continue"
	)

	# Finishing the first beat writes the facts and enters the second, and the
	# save is written the moment it is entered — before anything is drawn.
	var finished := CaseRuntime.reduce(
		document,
		"demo",
		state,
		{
			"kind": "finish",
			"beatId": "demo_supper",
			"outcome": "to_the_room",
			"flags": PackedStringArray(["heard_the_toast"]),
		},
		at
	)
	var after: Dictionary = finished["state"]
	h.assert_eq(
		String((after["progress"] as Dictionary)["beatId"]),
		"demo_room",
		"finishing the supper enters the room"
	)
	h.assert_true(finished["write"] != null, "and a save is written on entry")
	h.assert_eq(
		String((finished["write"] as Dictionary)["beatId"]),
		"demo_room",
		"naming the beat just entered, so a reload does not replay the beat before it"
	)
	var kinds := PackedStringArray()
	for entry: Variant in (finished["events"] as Array):
		kinds.append(String((entry as Dictionary)["type"]))
	h.assert_true(kinds.has("facts/established"), "the facts it established are announced")
	h.assert_true(kinds.has("beat/entered"), "and the beat it entered")

	# A finish naming a beat that is not the one playing moves nothing: a stale
	# leaf reporting an outcome cannot advance an episode past it.
	var stray := CaseRuntime.reduce(
		document,
		"demo",
		after,
		{"kind": "finish", "beatId": "demo_supper", "outcome": "to_the_room", "flags": []},
		at
	)
	h.assert_eq((stray["events"] as Array).size(), 0, "a finish for another beat does nothing")

	# The backlog remembers a line once, however many times a leaf redraws it.
	var scenario := {"label": "table", "index": 1, "flags": PackedStringArray()}
	var line := {"speaker": "Nao", "text": "The soup is going cold."}
	var drawn := CaseRuntime.reduce(
		document,
		"demo",
		state,
		{
			"kind": "presented",
			"statementId": "table#1",
			"line": line,
			"scenario": scenario,
			"outcome": null,
		},
		at
	)
	h.assert_eq(((drawn["state"] as Dictionary)["backlog"] as Array).size(), 1, "a line is kept")
	var redrawn := CaseRuntime.reduce(
		document,
		"demo",
		drawn["state"],
		{
			"kind": "presented",
			"statementId": "table#1",
			"line": line,
			"scenario": scenario,
			"outcome": null,
		},
		at
	)
	h.assert_eq(
		((redrawn["state"] as Dictionary)["backlog"] as Array).size(),
		1,
		"and the same line redrawn is not kept twice"
	)


func _fixture() -> Variant:
	var file := FileAccess.open("res://tests/fixtures/case/document.json", FileAccess.READ)
	if file == null:
		return null
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	file.close()
	return parsed

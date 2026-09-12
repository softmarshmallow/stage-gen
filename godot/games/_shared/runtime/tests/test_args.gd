extends RefCounted

func run(h: TestHarness) -> void:
	var parsed := HostArgs.tokens(PackedStringArray([
		"--value=-2", "--flag", "--unknown=x", "loose", "--value", "last"
	]), ["--value", "--flag"])
	h.assert_eq(parsed.values, {"--value": "last", "--flag": ""}, "inline, bare and repeated token spelling")
	h.assert_eq(Array(parsed.unknown), ["--unknown", "loose"], "unaccepted tokens remain visible")
	var empty := HostArgs.tokens(PackedStringArray(["--world", "night"]), [])
	h.assert_true(empty.values.is_empty(), "the tokenizer owns no default game flags")
	h.assert_eq(Array(empty.unknown), ["--world", "night"], "game options require an owning declaration")
	h.done()

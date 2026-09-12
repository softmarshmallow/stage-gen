class_name GrainOptions
extends RefCounted

## Options interpreted by this game; token syntax is private shared support.
var run: String = ""
var scenario: String = ""
var beat: String = ""
var runs: String = ""
var unknown := PackedStringArray()

static func parse(argv: PackedStringArray) -> GrainOptions:
	var args := GrainOptions.new()
	var parsed := HostArgs.tokens(argv, ["--run", "--scenario", "--beat", "--runs"])
	args.unknown = parsed.unknown
	for token: String in parsed.values:
		var value: String = parsed.values[token]
		match token:
			"--run": args.run = value
			"--scenario": args.scenario = value
			"--beat": args.beat = value
			"--runs": args.runs = value
	args.run = args.run.rstrip("/")
	return args

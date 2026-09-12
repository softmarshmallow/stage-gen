extends SceneTree

const Program = preload("res://addons/scenario_runtime/program.gd")
const Runtime = preload("res://addons/scenario_runtime/runtime.gd")
const Refusal = preload("res://addons/scenario_runtime/refusal.gd")
const Example = preload("program.gd")

func _initialize() -> void:
	var program: Variant = Program.parse(Example.document())
	if Refusal.is_refusal(program):
		_fail(program)
		return
	var turn := Runtime.initial_turn(program)
	for action in [{"kind": "advance"}, {"kind": "choose", "option": 0}]:
		if Refusal.is_refusal(turn):
			_fail(turn)
			return
		print(Runtime.view(program, turn["state"]))
		turn = Runtime.reduce_turn(program, turn["state"], action)
	if Refusal.is_refusal(turn):
		_fail(turn)
		return
	print(Runtime.view(program, turn["state"]))
	quit(0)

func _fail(failure: Dictionary) -> void:
	printerr(Refusal.line(failure))
	quit(1)

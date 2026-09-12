extends RefCounted

## Every script in the project parses.
##
## This exists because of a defect it would have caught. `FamilyParallax` was
## written with a `PackedStringArray` in a `const`, which this build does not
## accept as a constant expression, so the script failed to parse — and *nothing
## said so*. The global class name is registered from the file's `class_name`
## line whether or not the body compiles, so `FamilyParallax.layer_layout(...)`
## resolved to a script object and failed at the call, at runtime, in a host
## nobody had run yet. The suite was green the whole time, because no test
## touched that family.
##
## A script that did not parse has no methods, no constants and no properties.
## One that has any of the three is a script the engine read.

func run(h: TestHarness) -> void:
	var checked := 0
	if FileAccess.file_exists("res://main.gd"):
		h.assert_true(load("res://main.gd").can_instantiate(), "the game entry script parses")
	for root in ["res://addons/demo_support", "res://gameplay", "res://scenes", "res://tools"]:
		for path in _walk(root):
			checked += 1
			var script: GDScript = load(path)
			h.assert_true(script != null, "%s loads" % path)
			if script == null:
				continue
			var empty := (
				script.get_script_method_list().is_empty()
				and script.get_script_constant_map().is_empty()
				and script.get_script_property_list().is_empty()
			)
			h.assert_false(empty, "%s parses" % path)
	h.assert_true(checked > 20, "the sweep found the project's scripts (%d)" % checked)
	h.done()


func _walk(dir: String) -> PackedStringArray:
	var found := PackedStringArray()
	if not DirAccess.dir_exists_absolute(dir):
		return found
	for name in DirAccess.get_files_at(dir):
		if name.ends_with(".gd"):
			found.append(dir + "/" + name)
	for name in DirAccess.get_directories_at(dir):
		found.append_array(_walk(dir + "/" + name))
	return found

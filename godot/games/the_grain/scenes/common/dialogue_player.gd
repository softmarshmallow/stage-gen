class_name GrainDialoguePlayer
extends RefCounted

## The installed game's content selection. Rich direction is supplied by the
## named sequence; this table selects its reader and contains no story rules.
const RICH_SEQUENCES := ["e1_way_in"]
const RichLeaf = preload("res://scenes/common/rich_dialogue_leaf.gd")


static func open(
	run_dir: String,
	scenario_id: String = "",
	carried: PackedStringArray = PackedStringArray(),
	resume: Variant = null
) -> Variant:
	if RICH_SEQUENCES.has(scenario_id):
		return RichLeaf.open_rich(run_dir, scenario_id, carried, resume)
	return HostDialogueLeaf.open(run_dir, scenario_id, carried, resume)

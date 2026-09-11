class_name RunnerRoster
extends RefCounted

## Every system this genre composes, and the order that falls out of them.
##
## The list below is **registration** order, not frame order. The frame order is
## derived by `KernelSealer` from what each system declares it reads, writes,
## owns, emits and consumes; registration only breaks ties. Two of these move:
## the moment system is registered second and runs sixth, the difficulty system
## is registered fourth and runs third. That the two differ is the point — a
## roster somebody re-ordered by hand is a roster whose order is an opinion.

static func system_classes() -> Array:
	return [
		RunnerClockSystem,
		RunnerIntentSystem,
		RunnerFxSystem,
		RunnerDifficultySystem,
		RunnerAvatarSystem,
		RunnerEncounterSystem,
		RunnerSegmentsSystem,
		RunnerObstaclesSystem,
		RunnerVitalsSystem,
		RunnerScoreSystem,
		RunnerSessionSystem,
		RunnerCameraSystem,
		RunnerParallaxSystem,
		RunnerHudSystem,
		RunnerAudioSystem,
		RunnerDustSystem,
	]


## Seal the roster. Returns a `KernelSealed` or a `KernelRefusal`.
##
## The world carries a frame queue, and saying so is not a formality: the sealer
## refuses a roster that speaks events over a world with nothing to clear them,
## because a channel nobody empties leaks the whole run into one array.
static func seal() -> Variant:
	return KernelSealer.seal(system_classes(), true)


## Build the fight's binding from the manifest and two measured numbers.
##
## `boss_height_rows` is the boss's authored height in the world's own rows;
## `hover_cell_aspect` is the width-to-height ratio of one cell of its hover
## atlas, which is the only way to know how wide the thing actually is. A host
## that has not loaded the atlas passes nothing and the run plays without
## fights rather than guessing a hit box.
static func bind_encounter(
	config: Dictionary, boss_height_rows: float, hover_cell_aspect: float
) -> Dictionary:
	var authored: Dictionary = config["encounter"]
	if authored.is_empty():
		return {}
	var binding := authored.duplicate(true)
	binding["bossHeightRows"] = boss_height_rows
	binding["bossHalfWidthColumns"] = (boss_height_rows * hover_cell_aspect) / 2.0
	return binding

extends RefCounted

## The plate levelling the ground, the water and the decals all share.
##
## A verbatim port of `levelGain` (viewer/index.html:3295-3301): a plate's
## measured sRGB mean is lifted to the value the package authored for it, as a
## linear gain, clamped so a wildly off plate reads wrong rather than being
## silently rescued. `[blend] level` overrides a biome's own `value_target`,
## which is mixing over the brief; full-v66 carries such a table, so the
## override is not the dead branch the rendering map guessed it was.

static func to_linear(v: float) -> float:
	return v / 12.92 if v <= 0.04045 else pow((v + 0.055) / 1.055, 2.4)

## `plate` is a manifest plate block (`luma_mean`, `value_target`, and for a
## biome the `biome_id` the caller stamped on it); `level` is `[blend] level`.
static func level_gain(plate: Variant, level: Dictionary = {}) -> float:
	if not (plate is Dictionary):
		return 1.0
	var block: Dictionary = plate
	if block.get("luma_mean") == null:
		return 1.0
	var target: Variant = null
	var biome_id: Variant = block.get("biome_id")
	if biome_id != null and level.get(String(biome_id)) != null:
		target = level[String(biome_id)]
	else:
		target = block.get("value_target")
	if target == null:
		return 1.0
	return clampf(to_linear(float(target)) / maxf(0.01, to_linear(float(block["luma_mean"]))), 0.5, 2.5)

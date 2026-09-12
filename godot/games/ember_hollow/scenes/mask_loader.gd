class_name SurvivalMaskLoader
extends RefCounted

## Game adapter: decode run plates and metadata before simulation sampling.
static func from_package(pkg: HostRunDir,
		inset_meters: float = SurvivalMasks.DEFAULT_INSET_METERS) -> SurvivalMasks:
	if pkg == null: return SurvivalMasks.new()
	var ground: Dictionary = pkg.manifest.get("ground", {})
	var size := float(ground.get("size_meters", 0.0))
	var land := {}
	var biome_data := {}
	var splat: Dictionary = ground.get("splat", {}) if ground.get("splat") != null else {}
	if size > 0.0 and splat.has("image"):
		var image := pkg.image(String(splat["image"]))
		if image != null:
			land = {"pixels": _rgba8_bytes(image), "width": image.get_width(), "height": image.get_height()}
			var cell: Variant = splat.get("cell_meters")
			land["cell_meters"] = float(cell) if cell is float or cell is int else size / float(image.get_width())
	var biome_splat: Variant = ground.get("biome_splat")
	var biomes: Variant = ground.get("biomes")
	if size > 0.0 and biome_splat is Dictionary and biomes is Dictionary:
		var ids := {}
		var frictions := {}
		for id: String in biomes:
			var biome: Dictionary = biomes[id]
			var channel := String(biome["weight_channel"]) if biome.get("weight_channel") != null else "base"
			ids[channel] = id
			var friction: Variant = biome.get("friction")
			frictions[channel] = float(friction) if friction is float or friction is int else SurvivalMasks.DEFAULT_FRICTION
		biome_data = {"ids": ids, "friction": frictions}
		var ref: Variant = biome_splat.get("image")
		if ref != null:
			var image := pkg.image(String(ref))
			if image != null:
				biome_data.merge({"pixels": _rgba8_bytes(image), "width": image.get_width(), "height": image.get_height()})
	return SurvivalMasks.from_data(size, land, biome_data, inset_meters)

static func _rgba8_bytes(image: Image) -> PackedByteArray:
	var copy := Image.new()
	copy.copy_from(image)
	if copy.get_format() != Image.FORMAT_RGBA8:
		copy.convert(Image.FORMAT_RGBA8)
	return copy.get_data()

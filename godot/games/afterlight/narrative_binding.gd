extends RefCounted

## Afterlight's installed front-stage geometry, prepared resources and theme.
const ATMOSPHERE = preload("res://atmosphere_profile.gd")
const CAST = preload("res://cast_stage.gd")


static func settings(content: Dictionary) -> Dictionary:
	var result := content.duplicate(true)
	result["design_size"] = [1280, 900]
	result["actors"] = content.get("guests", []) + content.get("supporting_cast", [])
	result["cast_geometry"] = CAST.default_layout()
	result["geometry"] = {"eye_anchor_y": 280.0, "detail_zoom": 1.24,
		"heat_rect": Rect2(60, 80, 1160, 790), "barrier_rect": Rect2(240, 90, 800, 800)}
	result["clear_color"] = Color("15121d")
	result["overlay_color"] = Color(0.07, 0.045, 0.1, 0.08)
	result["atmosphere_profiles"] = {}
	for profile: String in ["quiet_interior", "infernal_hall", "relay_alcove"]:
		result["atmosphere_profiles"][profile] = ATMOSPHERE.profile(profile)
	return result

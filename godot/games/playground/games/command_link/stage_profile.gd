extends "res://presentation/stage_profile.gd"

## Command Link's prepared cast, scenery, and demonstration content.
## Original source images stay local; presentation components know only these bindings.
const LOCAL_CONTENT = preload("res://addons/game_presentation/content/local_content.gd")


func _init(content_root: String = "res://", backend: String = "resources") -> void:
	content_loader = LOCAL_CONTENT.new()
	content_errors.assign(content_loader.configure(content_root, backend))
	display_title = "Command Link"
	asset_paths = {
		"open": "res://assets/character_full_open.png",
		"closed": "res://assets/character_full_closed.png",
		"touch": "res://assets/character_touch.png",
		"second": "res://assets/character_second_standing.png",
		"third": "res://assets/character_third_standing.png",
	}
	portrait_actor_id = "mira"
	portrait_open_texture = "open"
	portrait_closed_texture = "closed"
	contact_actor_id = "mira"
	contact_texture = "touch"
	contact_layout_path = "res://assets/layout.json"
	default_hologram_actor_id = "sera"
	location_catalog_path = "res://assets/locations/catalog.json"
	manpu_catalog_path = "res://assets/manpu/catalog.json"
	preview_copy = {
		"standing_line": "Standing by, Commander.",
		"standing_hint": "When you're ready, connect the squad channel.",
		"contact_line": "One touch, Commander. Then we're connected.",
		"connected_line": "Command link confirmed. I hear you clearly.",
		"connected_hint": "Squad channel connected.",
	}
	actors = [
		{"id": "mira", "name": "Mira", "texture": "open"},
		{"id": "lena", "name": "Lena", "texture": "second"},
		{"id": "sera", "name": "Sera", "texture": "third"},
	]
	manpu_head_anchors = {"mira": Vector2(0.80, 0.10), "lena": Vector2(0.22, 0.11), "sera": Vector2(0.80, 0.10)}
	dialogue_eye_anchors = {"mira": Vector2(0.51, 0.102), "lena": Vector2(0.52, 0.115), "sera": Vector2(0.51, 0.113)}
	dialogue_head_top = {"mira": 0.0085, "lena": 0.0, "sera": 0.0}
	dialogue = [
		{"speaker": "Mira", "line": "Commander, the squad is ready for your briefing.", "manpu": [{"actor": "mira", "id": "surprise"}]},
		{"speaker": "Lena", "line": "Perimeter checks are complete. I ran the sweep twice.", "manpu": [{"actor": "lena", "id": "sweat_drop"}]},
		{"speaker": "Mira", "line": "The northern relay is still silent?", "manpu": [{"actor": "mira", "id": "confusion"}]},
		{"speaker": "Lena", "line": "Six minutes. I marked the gap on your tactical map.", "manpu": [{"actor": "lena", "id": "anger_vein"}, {"actor": "mira", "id": "sweat_drop"}]},
		{"speaker": "Mira", "line": "Then their last report may already be out of date.", "manpu": [{"actor": "mira", "id": "gloom_lines"}]},
		{"speaker": "Lena", "line": "We'll verify it before the squad crosses the perimeter.", "manpu": [{"actor": "lena", "id": "sigh"}]},
		{"speaker": "Mira", "line": "I recovered a clean signal from the coastal staging point.", "manpu": [{"actor": "lena", "id": "sparkle"}]},
		{"speaker": "Lena", "line": "Good. That gives us a route they have not seen.", "manpu": [{"actor": "lena", "id": "heart"}]},
		{"speaker": "Mira", "line": "Let's choose our approach and move on your command.", "manpu": []},
		{"speaker": "Lena", "line": "Orders received. I'll take the forward position.", "manpu": []},
		{"speaker": "Sera", "line": "Overwatch online. Commander, you have my full support.", "manpu": [{"actor": "sera", "id": "sparkle"}]},
	]
	location_ids = ["forward_command", "perimeter_overlook", "coastal_staging"]
	manpu_ids = ["surprise", "confusion", "sweat_drop", "anger_vein", "sparkle", "heart", "gloom_lines", "sigh", "sigh_puff"]

extends RefCounted

const TEXT_SET = preload("res://addons/game_presentation/text/text_set.gd")
const EPISODE = preload("res://games/bishoujo_afterlight/story_beats.gd")
const VOICE_POLICY = preload("res://games/bishoujo_afterlight/voice/voice_policy.gd")
const LOCAL_CONTENT = preload("res://addons/game_presentation/content/local_content.gd")
const CONTENT_ADAPTER = preload("res://games/bishoujo_afterlight/content_adapter.gd")
const LANGUAGES := ["en", "ko"]
var _language := "en"
var _language_initialized := false
var _voice_policy: RefCounted
var _content_loader: RefCounted = LOCAL_CONTENT.new()
var _manpu_textures: Dictionary = {}

## Afterlight's master composition: prepared assets, direction, and route choice.
## UI is authored by this game's route, with no dependency on Command Link.
const SCENES := {
	"game": "res://games/bishoujo_afterlight/game.tscn",
}
const CONTENT := {
	"backgrounds": [
		{
			"id": "conservatory_lounge",
			"path": "res://games/bishoujo_afterlight/assets/locations/conservatory_lounge.png",
		},
		{
			"id": "reading_lounge",
			"path": "res://games/bishoujo_afterlight/assets/locations/reading_lounge.png",
		},
		{
			"id": "keeper_hall",
			"path": "res://games/bishoujo_afterlight/assets/locations/keeper_hall.png",
		},
		{
			"id": "relay_alcove",
			"path": "res://games/bishoujo_afterlight/assets/locations/relay_lab.png",
		},
	],
	"default_guest_id": "nami",
	"guests": [
		{
			"id": "nami",
			"proportion_style": "flat",
			"path": "res://games/bishoujo_afterlight/assets/characters/nami_standing.png",
			"eye_uv": [0.493, 0.146],
			"eye_close_path": "res://games/bishoujo_afterlight/assets/characters/nami_close.png",
			"eye_close_uv": [0.487, 0.334],
			"eye_close_height": 1050.0,
			"detail_path": "res://games/bishoujo_afterlight/assets/characters/nami_detail.png",
			"detail_height": 1600.0,
			"detail_y": -200.0,
			"contact_path": "res://games/bishoujo_afterlight/assets/characters/nami_contact.png",
			"contact_height": 960.0,
			"contact_y": 0.0,
			"contact_uv": [0.462890625, 0.57421875],
			"contact_radius_ratio": 0.03515625,
		},
		{
			"id": "yuzu",
			"proportion_style": "flat",
			"path": "res://games/bishoujo_afterlight/assets/characters/yuzu_standing.png",
			"eye_uv": [0.510, 0.141],
		},
		{
			"id": "sena",
			"proportion_style": "exaggerated_feminine",
			"path": "res://games/bishoujo_afterlight/assets/characters/sena_standing.png",
			"eye_uv": [0.496, 0.137],
		},
		{
			"id": "riko",
			"proportion_style": "exaggerated_feminine",
			"path": "res://games/bishoujo_afterlight/assets/characters/riko_standing.png",
			"eye_uv": [0.494, 0.118],
		},
	],
	"supporting_cast": [
		{
			"id": "keeper",
			"path": "res://games/bishoujo_afterlight/assets/characters/keeper_standing.png",
			"eye_uv": [0.49, 0.09],
		},
		{
			"id": "eira",
			"path": "res://games/bishoujo_afterlight/assets/characters/eira_portrait.png",
			"eye_uv": [0.47, 0.28],
			"transmission_display": {
				"frame_rect": Rect2(332, 135, 616, 472),
				"face_uv_rect": Rect2(0.35, 0.14, 0.25, 0.33),
				"camera_zoom": 1.06,
				"hologram_strength": 0.70,
				"voice_effect": "transmission_voice",
			},
		},
	],
	"approach": {"duration_seconds": 5.5, "target_zoom": 1.24, "bob_amplitude": 12.0, "bob_cycles_per_second": 1.6},
	"eye_transition": {"opening_seconds": 2.2, "closing_seconds": 0.14, "closed_hold_seconds": 0.08, "peek_seconds": 0.22, "peek_openness": 0.42},
	"eye_mask": {"edge_softness": 28.0},
	"background_blackout": {"fade_seconds": 0.45, "restore_seconds": 0.4},
	"quick_approach": {"duration_seconds": 0.32, "stop_distance": 280.0, "curve": "ease_in_out", "frequency": 1.5, "damping_ratio": 0.8},
	"cast_pan": {"duration_seconds": 0.45, "curve": "ease_in_out", "frequency": 1.5, "damping_ratio": 0.8},
	"intertitle": {"chars_per_second": 32.0},
	"ambient_particles": {"conservatory_lounge": "quiet_interior", "reading_lounge": "quiet_interior", "keeper_hall": "infernal_hall", "relay_alcove": "relay_alcove"},
	"transmission_voice": {"preset": "transmission_voice", "strength": 0.65, "parent_bus": "Master", "bypass": true},
	"text_audio": {"mode": "auto", "typing_volume_db": -18.0},
	"autoplay": {"enabled": false, "delay_seconds": 3.0, "choice_delay_seconds": 5.0},
	"contact": {"feedback_seconds": 0.45},
	# The host binds only ready recordings: language -> stable text ID -> stream.
	"voiceovers": {},
	"sprite_burst": {
		"sprites": {"sparkle": "res://assets/manpu/sparkle.png", "heart": "res://assets/manpu/heart.png"},
		"options": {"count": 18, "duration": 1.35, "distance": 230.0, "start_radius": 42.0, "sprite_size": 38.0, "seed": 88},
	},
	"heat_haze": {"mode": "heat", "amplitude_px": 18.0, "tint_strength": 0.0},
	"barrier": {"mode": "barrier", "amplitude_px": 18.0, "tint_strength": 0.12},
	"world_corruption": {"screen": true, "darkness": 0.82, "mist_strength": 0.95, "refraction_px": 3.0, "glow_strength": 0.65, "tint": Color(0.85, 0.025, 0.055)},
	"local_corruption": {"darkness": 0.48, "mist_strength": 1.0, "glow_strength": 0.9, "refraction_px": 1.0, "aura_px": 140.0, "tint": Color(1.0, 0.035, 0.075)},
	"drift": {"amplitude_x": 7.0, "amplitude_y": 4.0, "period_x": 7.0, "period_y": 9.0, "phase_y": 0.7},
	"halo": {"radius": 24.0, "color": Color(1.0, 0.8, 0.65, 0.85), "intensity": 0.85},
	"choices": [{"id": "see_you"}, {"id": "together"}],
}


func id() -> String:
	return "bishoujo_afterlight"


func title() -> String:
	return "Bishōjo: Afterlight"


func entry_route() -> String:
	return "game"


func scene_path(route_id: String) -> String:
	return String(SCENES.get(route_id, ""))


func validate_options(options: Dictionary) -> Array[String]:
	var errors: Array[String] = []
	if options.has("opening-variant"):
		errors.append("Bishōjo: Afterlight has no opening video configured.")
	if options.has("language") and options["language"] not in LANGUAGES:
		errors.append("Afterlight language must be en or ko.")
	if options.has("content-root"):
		if not options["content-root"] is String:
			errors.append("--content-root requires an absolute local directory.")
		else:
			var loader := LOCAL_CONTENT.new()
			errors.append_array(loader.configure(options["content-root"], "files"))
	return errors


func prepare_scene(scene: Control, route_id: String, options: Dictionary, saved_state: Dictionary) -> void:
	var next_loader := LOCAL_CONTENT.new()
	var loading_errors: Array[String] = next_loader.configure(str(options.get("content-root", "res://")), "files" if options.has("content-root") else "resources")
	if not loading_errors.is_empty():
		scene._load_errors.append_array(loading_errors)
		return
	_content_loader = next_loader
	if not _language_initialized:
		_language = str(options.get("language", "en"))
		_language_initialized = true
	var sets := {}
	for language: String in LANGUAGES:
		var parsed: Dictionary = _content_loader.read_json("games/bishoujo_afterlight/text/" + language + ".json")
		if not parsed.errors.is_empty() or not parsed.value is Dictionary:
			scene._load_errors.append("Cannot read Afterlight text set: " + language)
			scene._load_errors.append_array(parsed.errors)
			return
		sets[language] = parsed.value
	var marks := CONTENT_ADAPTER.load_manpu(_content_loader)
	scene._load_errors.append_array(marks.errors)
	if not marks.errors.is_empty(): return
	_manpu_textures = marks.textures
	scene.text_set = TEXT_SET.new()
	scene._load_errors.append_array(scene.text_set.configure(sets, _language))
	_voice_policy = VOICE_POLICY.new()
	scene._load_errors.append_array(_voice_policy.load_project(EPISODE.BEATS, sets, _content_loader))
	scene.content_factory = localize_content
	scene.content = localize_content(scene.text_set)
	scene.language_changed.connect(_remember_language)
	var font := SystemFont.new()
	font.font_names = PackedStringArray(["Apple SD Gothic Neo", "Noto Sans CJK KR", "Noto Sans KR", "Malgun Gothic", "sans-serif"])
	scene.theme = Theme.new()
	scene.theme.default_font = font
	if route_id == "game":
		scene.voice_policy = _voice_policy
		scene.beats = EPISODE.BEATS.duplicate(true)
		scene.saved_state = saved_state.duplicate(true)


func _remember_language(language: String) -> void:
	_language = language


func localize_content(words: RefCounted, authored: Dictionary = CONTENT) -> Dictionary:
	var result := authored.duplicate(true)
	result["content_loader"] = _content_loader
	result["manpu_textures"] = _manpu_textures.duplicate()
	if _voice_policy != null: result["voiceovers"] = _voice_policy.bind_voiceovers()
	for background: Dictionary in result["backgrounds"]:
		background["name"] = words.text("location." + str(background["id"]))
	for guest: Dictionary in result["guests"]:
		for field: String in ["name", "greeting", "detail_line", "conversation_line"]:
			guest[field] = words.text("guest." + str(guest["id"]) + "." + field)
	for field: String in ["arrival", "greeting", "question"]:
		result[field] = words.text("story." + field)
	result["monologues"] = {}
	for key: String in ["first_impression", "resolve"]:
		result["monologues"][key] = words.text("story.monologue." + key)
	for choice: Dictionary in result["choices"]:
		for field: String in ["label", "reply"]:
			choice[field] = words.text("story.choice." + str(choice["id"]) + "." + field)
	return result

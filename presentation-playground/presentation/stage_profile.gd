extends RefCounted

## A game's local Godot composition supplies prepared art and cast landmarks.
## This is an in-process object, not a persisted game format or provider contract.
## Create a fresh instance for each stage and assign it before adding the stage.
var display_title := "Presentation"
var asset_paths: Dictionary = {}
var actors: Array[Dictionary] = []
var manpu_head_anchors: Dictionary = {}
var dialogue_eye_anchors: Dictionary = {}
var dialogue_head_top: Dictionary = {}
var dialogue: Array[Dictionary] = []
var location_catalog_path := ""
var location_ids: Array[String] = []
var manpu_catalog_path := ""
var manpu_ids: Array[String] = []
var portrait_actor_id := ""
var portrait_open_texture := ""
var portrait_closed_texture := ""
var contact_actor_id := ""
var contact_texture := ""
var contact_layout_path := ""
var default_hologram_actor_id := ""
var preview_copy: Dictionary = {}
# Optional local-content backend supplied by this concrete host's root.
var content_loader: RefCounted
var content_errors: Array[String] = []


func validation_errors() -> Array[String]:
	var errors: Array[String] = content_errors.duplicate()
	var seen := {}
	for actor: Dictionary in actors:
		var id := String(actor.get("id", ""))
		if id.is_empty() or not id.is_valid_identifier() or id != id.to_lower() or seen.has(id):
			errors.append("Stage profile needs unique lower_snake_case actor ids: " + id)
		seen[id] = true
		if String(actor.get("name", "")).is_empty() or not asset_paths.has(String(actor.get("texture", ""))):
			errors.append("Stage profile actor needs a display name and bound texture: " + id)
		var manpu_anchor: Variant = manpu_head_anchors.get(id)
		var eye_anchor: Variant = dialogue_eye_anchors.get(id)
		var head_top: Variant = dialogue_head_top.get(id)
		if not (manpu_anchor is Vector2) or not manpu_anchor.is_finite() or not (eye_anchor is Vector2) or not eye_anchor.is_finite():
			errors.append("Stage profile actor needs finite manpu and eye landmarks: " + id)
		if not (head_top is float or head_top is int) or not is_finite(float(head_top)):
			errors.append("Stage profile actor needs a finite numeric head landmark: " + id)
	for id: String in [portrait_actor_id, contact_actor_id, default_hologram_actor_id]:
		if not id.is_empty() and not seen.has(id):
			errors.append("Stage profile role names an unknown actor: " + id)
	if not portrait_actor_id.is_empty() and not asset_paths.has(portrait_open_texture):
		errors.append("Stage profile portrait needs its open-eye texture binding.")
	if not portrait_closed_texture.is_empty() and not asset_paths.has(portrait_closed_texture):
		errors.append("Stage profile closed-eye texture is not bound.")
	if not contact_actor_id.is_empty() and (not asset_paths.has(contact_texture) or contact_layout_path.is_empty()):
		errors.append("Stage profile contact needs its texture and source-image coordinates.")
	if contact_actor_id.is_empty() and (not contact_texture.is_empty() or not contact_layout_path.is_empty()):
		errors.append("Stage profile contact data needs an actor owner.")
	if not location_ids.is_empty() and location_catalog_path.is_empty():
		errors.append("Stage profile locations need a prepared location catalog.")
	if not manpu_ids.is_empty() and manpu_catalog_path.is_empty():
		errors.append("Stage profile manpu need a prepared mark catalog.")
	return errors

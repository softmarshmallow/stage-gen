extends Control

# This template owns the binding. It does not parse a pipeline or gameplay manifest.
const ASSET_PATH := "res://content/preview.png"
var loaded_size := Vector2i.ZERO
var errors: Array[String] = []


func _ready() -> void:
	var frame := TextureRect.new()
	frame.name = "SuppliedImage"
	frame.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	frame.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	frame.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	add_child(frame)
	var caption := Label.new()
	caption.position = Vector2(16, 16)
	caption.text = "Supply an image with this template's prepare.py script."
	add_child(caption)
	if not FileAccess.file_exists(ASSET_PATH):
		return
	var image := Image.new()
	if image.load(ASSET_PATH) != OK:
		errors.append("Supplied image could not be decoded.")
		caption.text = errors[0]
		return
	loaded_size = image.get_size()
	frame.texture = ImageTexture.create_from_image(image)
	caption.text = "Supplied image · %d × %d" % [loaded_size.x, loaded_size.y]

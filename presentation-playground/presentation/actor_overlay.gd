extends Control

# A local foreground canvas keeps dialogue backing, painted manpu, and touch
# feedback above the actors, outside each character's ShaderMaterial.
func _draw() -> void:
	get_parent()._draw_character_overlay(self)

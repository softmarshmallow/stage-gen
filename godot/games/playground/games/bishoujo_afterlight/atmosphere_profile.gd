extends RefCounted

## Afterlight owns the meaning, density, art, and depth of each atmosphere.
## The shared emitter only knows sprites, geometry, motion, and an explicit clock.
const EMITTER = preload("res://addons/game_presentation/effects/particles/ambient_particles.gd")
const REGION := Rect2(-160, -100, 1600, 1200)


static func profile(id: String) -> Array:
	match id:
		"quiet_interior":
			return [_layer("dust", "dust", {
				"seed": 103, "rate": 7.0, "max_particles": 96,
				"lifetime_min": 6.0, "lifetime_max": 10.0,
				"velocity_min": Vector2(-6, -12), "velocity_max": Vector2(8, -3),
				"drift": Vector2(14, 9), "size_min": 4.0, "size_max": 12.0,
				"tint": Color(1.0, 0.89, 0.69, 0.42), "additive": true,
			})]
		"relay_alcove":
			return [_layer("dust", "dust", {
				"seed": 211, "rate": 5.0, "max_particles": 72,
				"lifetime_min": 6.0, "lifetime_max": 9.0,
				"velocity_min": Vector2(-4, -9), "velocity_max": Vector2(6, -2),
				"drift": Vector2(10, 4), "size_min": 3.0, "size_max": 9.0,
				"tint": Color(0.55, 0.8, 1.0, 0.35), "additive": true,
			})]
		"infernal_hall":
			return [
				_layer("smoke", "smoke", {
					"seed": 313, "rate": 9.0, "max_particles": 96,
					"lifetime_min": 4.0, "lifetime_max": 7.0,
					"velocity_min": Vector2(-30, -95), "velocity_max": Vector2(25, -45),
					"drift": Vector2(48, 12), "size_min": 110.0, "size_max": 220.0,
					"scale_end": 1.6, "tint": Color(0.17, 0.07, 0.09, 0.5),
				}),
				_layer("embers", "ember", {
					"seed": 419, "rate": 27.0, "max_particles": 192,
					"lifetime_min": 3.0, "lifetime_max": 5.5,
					"velocity_min": Vector2(-42, -170), "velocity_max": Vector2(35, -65),
					"drift": Vector2(32, 8), "drift_frequency": 0.4,
					"size_min": 9.0, "size_max": 25.0, "scale_end": 0.45,
					"spin_min": -45.0, "spin_max": 45.0,
					"tint": Color(1.0, 0.38, 0.055, 0.9), "additive": true,
				}),
				_layer("sparks", "spark", {
					"seed": 521, "rate": 12.0, "max_particles": 64,
					"lifetime_min": 0.8, "lifetime_max": 2.0,
					"velocity_min": Vector2(-65, -280), "velocity_max": Vector2(60, -150),
					"drift": Vector2(10, 3), "size_min": 10.0, "size_max": 27.0,
					"spin_min": -12.0, "spin_max": 12.0, "scale_end": 0.25,
					"tint": Color(1.0, 0.73, 0.24, 0.85), "additive": true,
				}),
			]
	return []


static func _layer(id: String, kind: String, options: Dictionary) -> Dictionary:
	return {"id": id, "region": REGION, "textures": EMITTER.fallback_textures(kind), "options": options}

class_name RunnerCameraSystem
extends RefCounted

## Where the view sits. The avatar is pinned to a fixed screen column and the
## world slides past it, which is what an auto-runner is.

static func declaration() -> KernelSystem:
	return KernelSystem.of({
		"id": "runner/camera",
		"contract_version": "camera-system-v2",
		"reads": ["avatar"],
		"owns": ["camera"],
		"after": ["session/run"],
	})


static func update(world: RunnerWorld, _step: Dictionary) -> void:
	world.camera["scrollX"] = RunnerWorld.camera_scroll_x(
		float(world.avatar["distanceColumns"]), world.config
	)

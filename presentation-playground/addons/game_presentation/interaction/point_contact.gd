extends RefCounted

## One acknowledged point contact. Hosts own input, current target geometry,
## readiness gates and feedback; no coordinates, textures or clock are retained.
signal confirmed(point: Vector2)

var _confirmed := false


static func hit_test(point: Vector2, center: Vector2, radius: float) -> bool:
	if not point.is_finite() or not center.is_finite() or not is_finite(radius) or radius <= 0.0:
		return false
	# Scalar arithmetic avoids overflow in Vector2's lower-precision difference
	# for finite extreme inputs. Ordinary canvas coordinates keep the same circle.
	var dx := float(point.x) - float(center.x)
	var dy := float(point.y) - float(center.y)
	return sqrt(dx * dx + dy * dy) <= radius


## Every valid hit returns true, permitting a host to replay tactile feedback.
## The confirmed signal fires only on the first hit after an unconfirmed reset.
func confirm_at(point: Vector2, center: Vector2, radius: float) -> bool:
	if not hit_test(point, center, radius):
		return false
	if not _confirmed:
		_confirmed = true
		confirmed.emit(point)
	return true


func is_confirmed() -> bool:
	return _confirmed


## A host may silently restore an acknowledged checkpoint. No input or signal
## is synthesized, and changing a target's geometry never requires this call.
func reset(confirmed_state: bool = false) -> void:
	_confirmed = confirmed_state

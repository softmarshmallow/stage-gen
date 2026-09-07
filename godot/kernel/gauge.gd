class_name KernelGauge
extends RefCounted

## A bounded quantity with a refractory window: vitals, a boss's health, any
## pool that is drained, refills, and refuses to be drained twice in a moment.
##
## A verbatim port of `web/lib/kernel/gauge.ts`. Two rules carry across and are
## the reason this is a kernel type rather than a field on a slice:
##
## **A gauge is replaced, never mutated.** Every operation returns a new gauge
## beside its change record, so a slice that holds one holds a value and a
## digest of that slice is a digest of the number rather than of an object
## somebody else may still be writing to.
##
## **A refusal is a value.** `drain` on a depleted or refractory gauge returns a
## change whose `connected` is false, and the caller decides what that means —
## the runner calls it "absorbed" and says so out loud. Nothing throws, so a
## contact during invulnerability is an outcome rather than an error.
##
## Fields are a Dictionary rather than a class so a gauge serialises into a
## digest without a conversion step.

const DIVISOR := 1.0

## A fresh gauge, full. `maximum` must be a positive integer; anything else is a
## refusal returned as `null`, because a gauge with no ceiling is not a gauge.
static func create(maximum: int) -> Dictionary:
	if maximum <= 0:
		return {}
	return {
		"value": float(maximum),
		"max": float(maximum),
		"refractoryUntilMs": 0.0,
		"depleted": false,
	}


## Is the window still closed at this instant?
static func is_refractory(gauge: Dictionary, now_ms: float) -> bool:
	return now_ms < float(gauge.get("refractoryUntilMs", 0.0))


## Take `amount` off, opening a window of `refractory_ms` if one is asked for.
##
## The window is `max` of the new one and the one already standing, so a second
## source in the same frame cannot shorten the first source's protection.
static func drain(
	gauge: Dictionary, amount: float, now_ms: float, refractory_ms: float
) -> Dictionary:
	var value := float(gauge.get("value", 0.0))
	if bool(gauge.get("depleted", false)):
		return _refused(gauge, amount)
	if not is_finite(value) or value <= 0.0:
		return _refused(gauge, amount)
	if not is_finite(amount) or amount <= 0.0:
		return _refused(gauge, amount)
	if is_refractory(gauge, now_ms):
		return _refused(gauge, amount)
	var after := maxf(0.0, value - amount)
	var window := 0.0
	if is_finite(refractory_ms) and refractory_ms > 0.0:
		window = now_ms + refractory_ms
	var next := {
		"value": after,
		"max": float(gauge.get("max", 0.0)),
		"refractoryUntilMs": maxf(window, float(gauge.get("refractoryUntilMs", 0.0))),
		"depleted": after <= 0.0,
	}
	return {
		"connected": true,
		"attempted": amount,
		"applied": value - after,
		"before": value,
		"after": after,
		"depleted": after <= 0.0,
		"gauge": next,
	}


## Put `amount` back, never above the ceiling. The window is deliberately left
## alone: healing does not end invulnerability.
static func restore(gauge: Dictionary, amount: float) -> Dictionary:
	var value := float(gauge.get("value", 0.0))
	var ceiling := float(gauge.get("max", 0.0))
	if bool(gauge.get("depleted", false)):
		return _refused(gauge, amount)
	if not is_finite(amount) or amount <= 0.0:
		return _refused(gauge, amount)
	if value >= ceiling:
		return _refused(gauge, amount)
	var after := minf(ceiling, value + amount)
	if after <= value:
		return _refused(gauge, amount)
	var next := {
		"value": after,
		"max": ceiling,
		"refractoryUntilMs": float(gauge.get("refractoryUntilMs", 0.0)),
		"depleted": false,
	}
	return {
		"connected": true,
		"attempted": amount,
		"applied": after - value,
		"before": value,
		"after": after,
		"depleted": false,
		"gauge": next,
	}


## Raise the ceiling and fill to it. A lower or equal ceiling is a no-op rather
## than a shrink, because nothing in these genres takes a maximum away.
static func grow(gauge: Dictionary, maximum: int) -> Dictionary:
	if maximum <= 0:
		return gauge
	if float(maximum) <= float(gauge.get("max", 0.0)):
		return gauge
	return {
		"value": float(maximum),
		"max": float(maximum),
		"refractoryUntilMs": float(gauge.get("refractoryUntilMs", 0.0)),
		"depleted": bool(gauge.get("depleted", false)),
	}


## The blink a hurt body draws during its window.
##
## The phase counts *down* from the time remaining rather than up from the
## drain, so the flicker ends on the same beat the protection does however long
## the window was.
static func refractory_blink_alpha(
	gauge: Dictionary, now_ms: float, interval_ms: float, dim_alpha: float
) -> float:
	if bool(gauge.get("depleted", false)):
		return 1.0
	if not is_refractory(gauge, now_ms):
		return 1.0
	if not is_finite(interval_ms) or interval_ms <= 0.0:
		return dim_alpha
	var phase := int(floor((float(gauge.get("refractoryUntilMs", 0.0)) - now_ms) / interval_ms))
	return dim_alpha if phase % 2 == 0 else 1.0


## How full, in [0, 1]. A gauge with no ceiling reads as empty rather than full.
static func fraction(gauge: Dictionary) -> float:
	var value := float(gauge.get("value", 0.0))
	var ceiling := float(gauge.get("max", 0.0))
	if not is_finite(value) or not is_finite(ceiling) or ceiling <= 0.0:
		return 0.0
	return minf(1.0, maxf(0.0, value / ceiling))


static func _refused(gauge: Dictionary, attempted: float) -> Dictionary:
	var raw := float(gauge.get("value", 0.0))
	var value := maxf(0.0, raw) if is_finite(raw) else 0.0
	return {
		"connected": false,
		"attempted": attempted if is_finite(attempted) else 0.0,
		"applied": 0.0,
		"before": value,
		"after": value,
		"depleted": bool(gauge.get("depleted", false)) or value <= 0.0,
		"gauge": gauge,
	}

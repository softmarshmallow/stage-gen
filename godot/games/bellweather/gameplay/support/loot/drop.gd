class_name FamilyDrop
extends RefCounted

## A thing that fell out of something, in flight and at rest.
##
## A port of `web/lib/families/loot/drop.ts`. A drop pops away from the blow that
## knocked it loose, falls, bounces exactly once, settles, and then bobs where it
## lies. Every part of that is decided by the drop's own sequence number rather
## than by a stream, so two things falling in one frame land differently and the
## same kill drops the same way every time it is replayed.
##
## The bob's phase is the catalogue kind, which is not an accident: two tarts
## resting side by side rise together and a tart beside a dart does not.

## Acceleration on a drop in flight, in pixels per second squared.
const GRAVITY := 1500.0
const POP_VX_MIN := 60.0
const POP_VX_SPAN := 80.0
const POP_VY_MIN := 260.0
const POP_VY_SPAN := 120.0
const BOUNCE_RESTITUTION := 0.35

## A landing slower than this settles outright; bouncing a crawl reads as jitter.
const BOUNCE_MIN_VY := 120.0
const BOUNCE_VX_RETAINED := 0.5

## How far a settled drop rises and falls, and the divisor that gives its period
## — one cycle every one and a quarter seconds.
const BOB_AMPLITUDE := 2.0
const BOB_MS := 200.0

## How far apart the units of one stack land.
const SPACING_PX := 28.0


## A fresh body, popped away from the blow. `dir_sign` is 0 for a caller with no
## blow to point away from, which alternates instead.
static func launch(x: float, y: float, sequence: int, dir_sign: int, bob_phase: int) -> Dictionary:
	var pop := pop_velocity(sequence, dir_sign)
	return {
		"x": x,
		"y": y,
		"vx": pop["vx"],
		"vy": pop["vy"],
		"settled": false,
		"bounces": 0,
		"groundY": y,
		"bobPhase": bob_phase,
	}


## How hard and which way one drop is thrown.
static func pop_velocity(sequence: int, dir_sign: int) -> Dictionary:
	var direction := dir_sign
	if direction == 0:
		direction = 1 if sequence % 2 == 0 else -1
	return {
		"vx": float(direction) * (POP_VX_MIN + _unit_noise(sequence, 0x11) * POP_VX_SPAN),
		"vy": -(POP_VY_MIN + _unit_noise(sequence, 0x22) * POP_VY_SPAN),
	}


## Advance one drop, or bob it if it has already come to rest. In place, because
## a drop is stepped every frame and a value rebuilt thirty times a second per
## item is a lot of rubbish for no argument gained.
##
## Returns what the step did: `flying`, `bounced`, `settled` or `resting`.
static func step(
	body: Dictionary, dt_ms: float, now_ms: float, surface_at: Callable, clamp_x: Callable
) -> String:
	if bool(body["settled"]):
		body["y"] = float(body["groundY"]) + sin(now_ms / BOB_MS + float(body["bobPhase"])) * BOB_AMPLITUDE
		return "resting"
	var dt := dt_ms / 1000.0
	body["vy"] = float(body["vy"]) + GRAVITY * dt
	body["y"] = float(body["y"]) + float(body["vy"]) * dt
	body["x"] = float(body["x"]) + float(body["vx"]) * dt
	if clamp_x.is_valid():
		body["x"] = float(clamp_x.call(float(body["x"])))
	var surface := float(surface_at.call(float(body["x"])))
	if float(body["y"]) < surface:
		return "flying"
	body["y"] = surface
	if int(body["bounces"]) < 1 and float(body["vy"]) > BOUNCE_MIN_VY:
		body["vy"] = -float(body["vy"]) * BOUNCE_RESTITUTION
		body["vx"] = float(body["vx"]) * BOUNCE_VX_RETAINED
		body["bounces"] = int(body["bounces"]) + 1
		return "bounced"
	body["settled"] = true
	body["vy"] = 0.0
	body["vx"] = 0.0
	body["groundY"] = surface
	return "settled"


## Where the units of one stack land relative to the body that dropped them.
## Centred on the corpse, so a stack of one lands on it and a stack of four
## straddles it evenly.
static func spread(quantity: int, spacing: float = SPACING_PX) -> PackedFloat32Array:
	var made := PackedFloat32Array()
	for index in range(quantity):
		made.append((float(index) - float(quantity - 1) / 2.0) * spacing)
	return made


## What one creature's authored rules decided it drops.
##
## One seed for every rule the creature carries, deliberately: that is the
## difference between "this creature's death was lucky" and "each of its drops
## was rolled separately". Changing it is a balance decision with an authored
## surface of its own, not an extraction.
static func resolve(rules: Array, mob_id: String, seed_value: int) -> Array:
	var roll := float(seed_value) / 4294967295.0
	var made: Array = []
	for entry: Variant in rules:
		var rule: Dictionary = entry
		if String(rule.get("mob_id", "")) != mob_id:
			continue
		if roll > float(rule.get("chance", 0.0)):
			continue
		var minimum := int(rule.get("quantity_min", 1))
		var span := maxi(1, int(rule.get("quantity_max", minimum)) - minimum + 1)
		made.append({"itemId": String(rule.get("item_id", "")), "quantity": minimum + seed_value % span})
	return made


static func _unit_noise(sequence: int, channel: int) -> float:
	var hash_value := KernelHash.imul(sequence ^ channel, 0x9e3779b1)
	hash_value = (hash_value ^ ((sequence & KernelHash.MASK) >> 15)) & KernelHash.MASK
	hash_value = KernelHash.imul(hash_value ^ (hash_value >> 13), 0x85ebca6b)
	hash_value = KernelHash.imul(hash_value ^ (hash_value >> 16), 0xc2b2ae35)
	return float(hash_value) / 4294967296.0

class_name PlatformerImpact
extends RefCounted

## What a connected blow looks like beyond the number.
##
## A port of the sampling half of
## `web/lib/sideview-platformer/impact-presentation.ts`. Combat decides whether a
## blow connected, how much it removed and whether it killed; this only presents
## that resolution, exactly as `FamilyCombatText` presents the number. Every
## motion is a pure sample over caller-supplied simulation time, so ordinary play
## and a fixed-frame replay draw the same frame from the same blow, and nothing
## here owns a tween, a timer or an emitter.
##
## Five presentations, one event. A **flash** fills the target white for a few
## frames. A **spark** fans short rays out from the point of contact in the
## direction of the blow. A **burst** scatters shards under gravity when the blow
## killed. A **hitstop** holds the simulation so the blow has weight, and a
## **shake** nudges the camera on a kill — the last two are already the world's,
## so what is new here is the three that are drawn.
##
## No asset is involved in any of it. The sprites the generator publishes are the
## actor's own strips; everything here is geometry from the blow's own seed, which
## is what lets it ship without a provider call and stay identical between two
## replays of one run.

const FLASH_MS := 64.0
const SPARK_MS := 150.0
const BURST_MS := 420.0

const SPARK_RAYS := 5
const SPARK_LENGTH_PX := 30.0
const SPARK_SPREAD_RADIANS := PI * 0.55
## How much of the spark's life is spent growing. After it, the rays hold their
## length and fade.
const SPARK_GROWTH_FRACTION := 0.45

const BURST_SHARDS := 8
const BURST_SPEED_PX := 190.0
const BURST_GRAVITY_PX := 620.0
const BURST_RADIUS_PX := 5.0
## Shards leave with a lift on them, so a burst reads as thrown up off the body
## rather than as a ring expanding on the ground.
const BURST_UPWARD_BIAS_PX := 80.0

## A critical throws further, wider and brighter, by one number rather than three.
const CRITICAL_SCALE := 1.35

const SWING_MS := 140.0
const SWING_SPAN_RADIANS := PI * 0.7
const SWING_TRAIL_FRACTION := 0.45

## The noise channels, kept apart so a ray's angle and its length are two draws
## from one seed rather than the same draw twice.
const CHANNEL_RAY_ANGLE := 0x1000
const CHANNEL_RAY_LENGTH := 0x2000
const CHANNEL_SHARD_ANGLE := 0x3000
const CHANNEL_SHARD_SPEED := 0x4000
const CHANNEL_SHARD_RADIUS := 0x5000


## How long one blow's presentation lasts, so a caller knows when to retire it.
static func lifetime_ms(died: bool) -> float:
	var longest := maxf(FLASH_MS, SPARK_MS)
	return maxf(longest, BURST_MS) if died else longest


## Whether the body struck is still filled white.
static func flash(elapsed_ms: float) -> bool:
	return elapsed_ms >= 0.0 and elapsed_ms < FLASH_MS


## The spark fan, as line segments in world pixels.
##
## Each entry is `{x1, y1, x2, y2, alpha, width}`. Empty once the spark is spent,
## which is what a caller retires it on.
static func rays(
	seed_value: int, x: float, y: float, dir_sign: int, critical: bool, elapsed_ms: float
) -> Array:
	var progress := elapsed_ms / SPARK_MS
	if progress < 0.0 or progress >= 1.0:
		return []
	var growth := FamilyParticles.ease_out_cubic(
		clampf(progress / SPARK_GROWTH_FRACTION, 0.0, 1.0)
	)
	var alpha := 1.0
	if progress >= SPARK_GROWTH_FRACTION:
		alpha = 1.0 - (progress - SPARK_GROWTH_FRACTION) / (1.0 - SPARK_GROWTH_FRACTION)
	var emphasis := CRITICAL_SCALE if critical else 1.0
	var base_angle := 0.0 if dir_sign == 1 else PI
	var made: Array = []
	for index in range(SPARK_RAYS):
		var fan := (float(index) / float(SPARK_RAYS - 1) - 0.5) * SPARK_SPREAD_RADIANS
		var jitter := (
			FamilyParticles.unit_noise(seed_value, CHANNEL_RAY_ANGLE + index) - 0.5
		) * 0.25
		var angle := base_angle + fan + jitter
		var length := (
			SPARK_LENGTH_PX
			* (0.7 + 0.6 * FamilyParticles.unit_noise(seed_value, CHANNEL_RAY_LENGTH + index))
			* emphasis
			* growth
		)
		var cos_of := cos(angle)
		var sin_of := sin(angle)
		made.append(
			{
				# The ray starts short of the contact point rather than on it, so
				# the fan reads as struck sparks and not as a star drawn on the body.
				"x1": x + cos_of * length * 0.35,
				"y1": y + sin_of * length * 0.35,
				"x2": x + cos_of * length,
				"y2": y + sin_of * length,
				"alpha": alpha,
				"width": (3.5 if critical else 2.5) * (1.0 - progress * 0.5),
			}
		)
	return made


## The shards a kill throws, as `{x, y, radius, alpha}` in world pixels.
##
## Empty for a blow that did not kill: a burst is what a death looks like, and
## scattering one on every hit would spend the reading on nothing.
static func shards(
	seed_value: int, x: float, y: float, critical: bool, died: bool, elapsed_ms: float
) -> Array:
	if not died:
		return []
	var progress := elapsed_ms / BURST_MS
	if progress < 0.0 or progress >= 1.0:
		return []
	var seconds := elapsed_ms / 1000.0
	var emphasis := CRITICAL_SCALE if critical else 1.0
	var made: Array = []
	for index in range(BURST_SHARDS):
		var angle := (
			(float(index) / float(BURST_SHARDS)) * TAU
			+ (FamilyParticles.unit_noise(seed_value, CHANNEL_SHARD_ANGLE + index) - 0.5) * 0.5
		)
		var speed := (
			BURST_SPEED_PX
			* (0.6 + 0.7 * FamilyParticles.unit_noise(seed_value, CHANNEL_SHARD_SPEED + index))
			* emphasis
		)
		var vx := cos(angle) * speed
		var vy := sin(angle) * speed - BURST_UPWARD_BIAS_PX
		made.append(
			{
				"x": x + vx * seconds,
				"y": y + vy * seconds + 0.5 * BURST_GRAVITY_PX * seconds * seconds,
				"radius": (
					BURST_RADIUS_PX
					* (
						0.6
						+ 0.6
						* FamilyParticles.unit_noise(
							seed_value, CHANNEL_SHARD_RADIUS + index
						)
					)
					* emphasis
					* (1.0 - progress * 0.6)
				),
				"alpha": 1.0 - progress * progress,
			}
		)
	return made


## The arc a swing has drawn so far, or an empty dictionary once it is spent.
##
## The head of the arc travels from up-front to down-front over the swing's life
## and a trailing fraction follows it, so the shape reads as a blade passing
## rather than as a ring appearing. Angles are the engine's: zero is right and
## positive is down. Facing left mirrors about the vertical, which is why the arc
## is walked the other way there rather than by negating the span.
##
## Returns `{x, y, radius, startAngle, endAngle, alpha, width}`.
static func swing_arc(
	x: float, y: float, dir_sign: int, radius_px: float, elapsed_ms: float
) -> Dictionary:
	var progress := maxf(0.0, elapsed_ms) / SWING_MS
	if progress >= 1.0:
		return {}
	var span := SWING_SPAN_RADIANS
	var head := -span / 2.0 + span * FamilyParticles.ease_out_cubic(progress)
	var tail := maxf(-span / 2.0, head - span * SWING_TRAIL_FRACTION)
	var forward := dir_sign == 1
	return {
		"x": x,
		"y": y,
		"radius": radius_px,
		"startAngle": tail if forward else PI - tail,
		"endAngle": head if forward else PI - head,
		"alpha": 1.0 - progress * progress,
		"width": 4.0 - 2.0 * progress,
	}

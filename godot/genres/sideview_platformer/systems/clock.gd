class_name PlatformerClockSystem
extends RefCounted

## What is holding the frame, and there are two answers.
##
## A port of `platformerClockHolders` in `web/lib/sideview-platformer/clock.ts`.
## A conversation holds the frame while it is on screen; a blow holds it for a
## few tens of milliseconds so the hit reads as a hit. Both write the same
## `hold`, and every system below returns early on it, which is why the two are
## one holder list rather than two flags nobody remembered to check together.
##
## **The hitstop is a feedback read.** The deadline it asks about was armed by a
## blow landed on an *earlier* frame, because the systems that arm one — the
## player's swing and the shot pool — run after this. Declaring the read would
## close the cycle clock -> player -> clock, so it is written down here instead.
##
## It is asked against the frame's own clock and not against the one it is
## holding: a hold measured against the clock it stops would never end.
##
## **The two holds do different things, and the difference is the whole system.**
## A conversation *skips* the systems below it — the world stops being stepped at
## all. A blow instead sets the simulation delta to zero: every system still
## runs, so a blow still resolves and a knockback still eases, because the ease
## is sampled from the wall of the frame clock rather than stepped by a delta.
## Collapsing the two into one flag freezes a hitstop solid, and the frame the
## blow lands on then never lands it.

static func declaration() -> KernelSystem:
	return KernelSystem.of(
		{
			"id": "clock/step",
			"contract_version": "clock-system-v1",
			"reads": ["hold"],
			"owns": ["clock"],
		}
	)


static func update(world: PlatformerWorld, step: Dictionary) -> void:
	var held := (
		world.hold or float(step["now"]) < float(world.impact.get("hitstopUntilMs", 0.0))
	)
	world.simulation_dt = 0.0 if held else float(step["dt"])

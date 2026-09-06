class_name KernelFixedStep
extends RefCounted

## The tick is the only clock.
##
## A frame delta is wall time and varies; a simulation step is a fixed slice and
## does not. The accumulator turns one into the other: it banks the frame's real
## time and pays out whole steps, so the same seed and the same intents replay
## the same world whatever the frame rate did. Nothing in a simulation may read
## the wall clock, an engine tween or an engine timer; they all sample the
## frame, and a frame is the one thing that is not the same twice.
##
## `now` is the integral, not the wall clock, so a refractory window stamped
## against it cannot be burned through by a stall. `frame` counts steps, which
## is what a replay indexes by.

## Seconds per step. 1/60 unless a genre says otherwise; the browser platformer
## ran at 1/30 and that is a genre parameter rather than a house number.
var dt: float = 1.0 / 60.0
## At most this many steps in one frame. On hitting the cap the accumulator is
## zeroed, so a stall drops time rather than spiralling: a frame that owes two
## seconds of simulation would take two seconds to render and owe more.
var max_substeps: int = 5
## A frame delta longer than this is clamped before it reaches the bank. A
## breakpoint, a window drag or a swapped-out process is not gameplay time.
var max_frame_delta: float = 0.25

## Simulated seconds since the last session reset.
var now: float = 0.0
## Steps since the last session reset.
var frame: int = 0

var _banked: float = 0.0


static func of(dt: float, max_substeps: int = 5, max_frame_delta: float = 0.25) -> KernelFixedStep:
	var made := KernelFixedStep.new()
	made.dt = dt
	made.max_substeps = max_substeps
	made.max_frame_delta = max_frame_delta
	return made


## Bank a frame's real time and return how many whole steps it bought.
## The caller ticks that many times, calling `advance` once per step.
func take(delta: float) -> int:
	_banked += minf(delta, max_frame_delta)
	var steps := 0
	while _banked >= dt and steps < max_substeps:
		_banked -= dt
		steps += 1
	if steps == max_substeps:
		_banked = 0.0
	return steps


## Move the clock on by one step. Called once per step the caller ticks, so the
## clock counts steps that ran rather than steps that were owed.
func advance() -> void:
	now += dt
	frame += 1


## Whole steps for a span of simulated time, at least one. What a harness uses
## to say "advance two seconds" without pretending to be a frame.
func steps_for(seconds: float) -> int:
	return maxi(1, int(round(seconds / dt)))


## Rewind. A run reset keeps the clock — a moment playing over the restart is
## timed from a clock that never went backwards — and a session reset does not.
func reset() -> void:
	now = 0.0
	frame = 0
	_banked = 0.0

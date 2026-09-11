class_name PlatformerLoadingCard
extends Control

## The card that stands in front of a map being built.
##
## Entering a map tears the whole stage down and puts a new one up: a ground sheet
## cut into hundreds of squares, four parallax bands, the gates, the climbables,
## and every actor's strips decoded the first time they are asked for. Measured at
## sixty milliseconds with the textures already warm and seconds without — and it
## all happened inside one `_process`, so the last frame of the old map simply sat
## there while it did, which reads as the game having hung.
##
## The fix is not to make the work faster; it is to stop lying about it. The card
## goes up on the frame the map changes and the rebuild waits for the frame after,
## so there is always a drawn frame saying what is happening before the stall
## begins. It stays up for a minimum after that, because a load that finishes in
## forty milliseconds should not flash.
##
## **The world does not step while it is up.** A player who cannot see the game
## cannot play it, and a creature that walked up and hit them during a load landed
## a blow they had no way to answer. It also keeps the frame the stall stole out of
## the simulation's banked time, which would otherwise be spent in a burst of catch
## -up steps the moment the card came down.
##
## Deliberately code and no art. A published loading plate is a thing a package
## could author later; a veil, the name of the place, and a line that moves are
## what the moment actually needs, and drawing them costs nothing to ship.

## How long the card stays up once the work behind it is done.
const MINIMUM_MS := 420.0

## How long one sweep of the line takes.
const SWEEP_MS := 900.0

const VEIL_COLOR := Color(0.031, 0.027, 0.043, 1.0)
const TITLE_COLOR := Color(0.996, 0.945, 0.855)
const HINT_COLOR := Color(0.996, 0.945, 0.855, 0.55)
const BAR_COLOR := Color(1.0, 0.812, 0.478)
const BAR_TRACK := Color(1.0, 1.0, 1.0, 0.12)

const TITLE_SIZE := 40
const HINT_SIZE := 16
const BAR_WIDTH := 420.0
const BAR_HEIGHT := 4.0
## How much of the track the moving segment covers.
const BAR_SWEEP_SHARE := 0.28

var _veil: ColorRect = null
var _title: Label = null
var _hint: Label = null
var _bar: Node2D = null
## When the card went up, and whether the work behind it has finished. Negative is
## "not up".
var _raised_at_ms: float = -1.0
var _released_at_ms: float = -1.0
var _sweep: float = 0.0


static func of() -> PlatformerLoadingCard:
	var made := PlatformerLoadingCard.new()
	made.mouse_filter = Control.MOUSE_FILTER_IGNORE
	made._veil = ColorRect.new()
	made._veil.mouse_filter = Control.MOUSE_FILTER_IGNORE
	made._veil.color = VEIL_COLOR
	made._veil.size = Vector2(PlatformerStage.VIEW_WIDTH, PlatformerStage.VIEW_HEIGHT)
	made.add_child(made._veil)

	made._title = _centred(TITLE_SIZE, TITLE_COLOR, PlatformerStage.VIEW_HEIGHT / 2.0 - 60.0)
	made.add_child(made._title)
	made._hint = _centred(HINT_SIZE, HINT_COLOR, PlatformerStage.VIEW_HEIGHT / 2.0 + 44.0)
	made._hint.text = "entering"
	made.add_child(made._hint)

	made._bar = Node2D.new()
	made.add_child(made._bar)
	made._bar.draw.connect(made._draw_bar)

	made.visible = false
	return made


static func _centred(size: int, color: Color, y: float) -> Label:
	var made := Label.new()
	made.mouse_filter = Control.MOUSE_FILTER_IGNORE
	made.add_theme_font_size_override("font_size", size)
	made.add_theme_color_override("font_color", color)
	made.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	made.position = Vector2(0.0, y)
	made.size = Vector2(PlatformerStage.VIEW_WIDTH, float(size) * 1.4)
	return made


## Put the card up for a place about to be built.
func raise_for(place: String, now_ms: float) -> void:
	_title.text = place
	_raised_at_ms = now_ms
	_released_at_ms = -1.0
	visible = true


## Say the work behind the card is done. It comes down on its own after that.
func release(now_ms: float) -> void:
	if _raised_at_ms >= 0.0 and _released_at_ms < 0.0:
		_released_at_ms = now_ms


## Whether the card is standing in front of the game right now.
func showing() -> bool:
	return visible


## Whether the frame behind the card has been drawn, which is what makes it safe to
## do the expensive work: the card is only honest once it is actually on screen.
func settled() -> bool:
	return visible and _raised_at_ms >= 0.0


func sync(now_ms: float) -> void:
	if not visible:
		return
	_sweep = fmod(maxf(0.0, now_ms - _raised_at_ms), SWEEP_MS) / SWEEP_MS
	_bar.queue_redraw()
	if _released_at_ms < 0.0:
		return
	if now_ms - _released_at_ms < MINIMUM_MS:
		return
	visible = false
	_raised_at_ms = -1.0
	_released_at_ms = -1.0


## A segment sweeping a track: motion without a claim.
##
## Deliberately not a percentage. Nothing here knows how much of the work is done —
## the rebuild is one synchronous call — and a bar that filled to a number it made
## up would be a worse lie than no bar.
func _draw_bar() -> void:
	var left := (PlatformerStage.VIEW_WIDTH - BAR_WIDTH) / 2.0
	var top := PlatformerStage.VIEW_HEIGHT / 2.0 + 6.0
	_bar.draw_rect(Rect2(left, top, BAR_WIDTH, BAR_HEIGHT), BAR_TRACK)
	var span := BAR_WIDTH * BAR_SWEEP_SHARE
	# Eased at both ends so the segment slows into the turn rather than snapping
	# back, which is the difference between a thing moving and a thing flickering.
	var travel := (1.0 - cos(_sweep * TAU)) / 2.0
	_bar.draw_rect(
		Rect2(left + (BAR_WIDTH - span) * travel, top, span, BAR_HEIGHT), BAR_COLOR
	)

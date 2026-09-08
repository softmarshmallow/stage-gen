class_name HostTransitionView
extends CanvasLayer

## The drawn half of `FamilyTransition`: one black rectangle over everything.
##
## It covers the **window** rather than the design box, because the thing it is
## hiding is a cut and a cut is not hidden by a cover with the letterbox showing
## down either side of it. That is also why it takes no scale from the host:
## there is nothing in it whose proportions could be wrong.
##
## The clock is the caller's. Nothing here reads a wall clock or runs a tween,
## so a capture handing it fixed steps draws the same cover on the same frame.
##
## Under `hosts/common` rather than one genre's view: every host cuts between
## runs, and the family this draws is the shared screen-effects one.

const COVER_COLOR := Color(0.0, 0.0, 0.0)

var _cover: ColorRect = null
var _choreography: Dictionary = {}
var _elapsed_ms: float = 0.0


static func of(layer: int) -> HostTransitionView:
	var view := HostTransitionView.new()
	view.layer = layer
	view._cover = ColorRect.new()
	view._cover.color = COVER_COLOR
	view._cover.visible = false
	view.add_child(view._cover)
	return view


## Start a cut under a named choreography.
##
## This is the seam a published `transitions` binding would arrive through: the
## caller names what it wants rather than assuming the only one that exists. An
## unknown name draws nothing at all, which is the honest answer for a cover
## nobody described — a black screen is the one thing worse than no transition.
func begin(name: String) -> void:
	var asked := FamilyTransition.choreography(name)
	if asked.is_empty():
		push_warning("transition view: no choreography named %s; cutting with no cover" % name)
		return
	_choreography = asked
	_elapsed_ms = 0.0
	_cover.visible = true
	_cover.modulate.a = 1.0


## Advance the cover by `dt` seconds of the caller's clock.
func advance(dt: float) -> void:
	if _choreography.is_empty():
		return
	_elapsed_ms += dt * 1000.0
	var frame := FamilyTransition.frame(_elapsed_ms, _choreography)
	if frame.is_empty():
		return
	_cover.modulate.a = float(frame["cover"])
	if bool(frame["finished"]):
		_choreography = {}
		_cover.visible = false


## Fill the window. Called whenever the host is told its size changed.
func fit(size: Vector2) -> void:
	_cover.size = size

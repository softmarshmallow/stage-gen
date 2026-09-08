class_name FamilyDefeatPrompt
extends RefCounted

## Whether the card asking a defeated player what to do next is up yet, and how
## far in it has faded.
##
## A port of `defeatPromptState` in `web/lib/families/checkpoints/defeat.ts`.
## Sampled from the caller's simulation time rather than tweened, so ordinary
## play and a fixed-frame replay follow the same path with nothing to drift
## between them.


## `{visible, alpha}` at `now_ms`, for a body that went down at `defeated_at_ms`.
static func prompt_state(
	defeated_at_ms: float, now_ms: float, delay_ms: float, fade_ms: float
) -> Dictionary:
	var elapsed := now_ms - defeated_at_ms - delay_ms
	if elapsed < 0.0:
		return {"visible": false, "alpha": 0.0}
	if is_zero_approx(fade_ms):
		return {"visible": true, "alpha": 1.0}
	return {"visible": true, "alpha": clampf(elapsed / fade_ms, 0.0, 1.0)}


## Whether a run with nobody at the keyboard has waited long enough to accept the
## card itself. A prompt is the right answer for a person, who wants to know what
## happened; it is the wrong answer for a run nobody is watching, which would
## otherwise stop at its first death and stay stopped.
static func automated_confirm_due(
	defeated_at_ms: float, now_ms: float, delay_ms: float
) -> bool:
	return now_ms - defeated_at_ms >= delay_ms

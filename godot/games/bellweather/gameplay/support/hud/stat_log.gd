class_name FamilyStatLog
extends RefCounted

## What just happened to the character, in words, briefly.
##
## A port of the arithmetic half of `web/lib/sideview-platformer/stat-log.ts`.
## Floating combat text answers "how much damage", anchored to the body that took
## it. This answers "what did I gain", and it belongs to the screen instead:
## experience and levels are facts about the player, not about a spot in the
## world, and a number rising off a corpse the player has already walked away from
## is a fact delivered to nobody.
##
## No panel, no frame, no background. The log is meant to be readable while it
## matters and gone afterwards, which a persistent box cannot do. Lines stack
## upward from a fixed anchor, the newest nearest it, and each fades on its own
## clock — so a burst of three kills reads as three lines rather than as one line
## flickering three times.
##
## Sampled from caller-supplied simulation time, exactly like the combat number,
## so ordinary play and a fixed-step replay follow the same path with no tween or
## timer to drift between them.

const KIND_EXPERIENCE := "experience"
const KIND_LEVEL_UP := "level_up"
const KIND_NOTICE := "notice"

const LIFETIME_MS := 2400.0
const FADE_START_MS := 1500.0
## How far a line drifts up over its whole life, on top of the step its place in
## the stack already gives it.
const RISE_PX := 26.0
const LINE_HEIGHT_PX := 26.0
## Beyond this the oldest line is retired early, so a long fight does not build a
## column that covers the game.
const MAX_LINES := 6

## Warmer, larger and heavier-outlined for a level: it is the one line worth
## interrupting for.
const STYLES := {
	KIND_EXPERIENCE:
	{
		"color": [0.812, 0.914, 1.0],
		"outline": [0.086, 0.125, 0.169],
		"outlinePx": 4,
		"sizePx": 20,
	},
	KIND_LEVEL_UP:
	{
		"color": [1.0, 0.843, 0.467],
		"outline": [0.227, 0.141, 0.031],
		"outlinePx": 5,
		"sizePx": 26,
	},
	KIND_NOTICE:
	{
		"color": [0.910, 0.910, 0.910],
		"outline": [0.102, 0.102, 0.102],
		"outlinePx": 4,
		"sizePx": 20,
	},
}


static func style(kind: String) -> Dictionary:
	return STYLES.get(kind, STYLES[KIND_NOTICE])


## Where a line sits and how visible it is, given only its age and its place in
## the stack. Returns `{offsetY, alpha, complete}`, the offset negative because a
## line rises off its anchor.
static func sample(elapsed_ms: float, line_index: int) -> Dictionary:
	var elapsed := maxf(0.0, elapsed_ms)
	if elapsed >= LIFETIME_MS:
		return {"offsetY": 0.0, "alpha": 0.0, "complete": true}
	var alpha := 1.0
	if elapsed > FADE_START_MS:
		alpha = 1.0 - (elapsed - FADE_START_MS) / (LIFETIME_MS - FADE_START_MS)
	var offset := float(line_index) * LINE_HEIGHT_PX + (elapsed / LIFETIME_MS) * RISE_PX
	return {"offsetY": -offset, "alpha": alpha, "complete": false}


## `+12 XP`, and nothing else. The kill it came from is already on screen.
static func experience_line(amount: int) -> String:
	return "" if amount <= 0 else "+%d XP" % amount


static func level_up_line(level: int) -> String:
	return "" if level < 1 else "LEVEL %d" % level

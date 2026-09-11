# Afterlight autoplay (P97)

Optional autoplay belongs to Afterlight's [story host](story.gd). It continues
ready beats after a reading delay, selects only an authored default choice,
and waits for mandatory player input. It has no provider or generation work
and introduces no shared narrative module.

## Authored inputs and ownership

The [root](root.gd) configures:

```gdscript
"autoplay": {
    "enabled": false,
    "delay_seconds": 3.0,
    "choice_delay_seconds": 5.0,
}
```

The host owns the persistent top **Autoplay** on/off button, its English/Korean
labels, delay clock and progression. The control remains accessible during
monologues, cinematic shots and contact. It starts off; toggling it restarts
the delay. It changes no audio policy or story wording.

Beat data can supply an `autoplay` dictionary:

| Field | Meaning |
| --- | --- |
| `default_choice` | Exact ID of an option on this beat. Only that authored option can be selected automatically. The episode's `courier_offer` uses `help_first`. |
| `require_input` | When `true`, automatic progression is blocked on the beat even if it has a valid default. Manual input follows that beat's existing rules. |
| `delay_seconds`, `choice_delay_seconds` | Optional per-beat overrides for the root's reading and choice delays. |

A pending choice without `default_choice` waits for selection. An authored
default that names no option is a configuration error. The host never infers
a default from option order. Existing manual selection remains available
throughout the countdown. Delays must be finite, positive and at most 120
seconds; flags must be booleans, and unknown fields are rejected. `enabled`
is a root setting, not a per-beat override.

`set_autoplay_enabled()` changes the mode and resets the timer.
`get_autoplay_state()` exposes enabled state, elapsed/delay/remaining seconds,
the default-choice ID and any blocking reason for the host's UI and checks.

## Timing and completion

The delay begins only after the complete text is visible, the beat's finite
cinematic motion has finished, and any bound voice has finished playing.
Ordinary dialogue, monologues, intertitles and cinematic captions then wait
`delay_seconds`. A pending choice with a valid authored default instead waits
`choice_delay_seconds`; its default button displays the remaining seconds.

The clock consumes unpaused host time. Monologues still hold world animation,
but their text and autoplay delay can finish. Autoplay observes existing
completion state; it never invokes manual skip to reveal text, cut off speech
or finish a cinematic early. Persistent ambient loops, Camera Drift and held
effects do not prevent a ready beat from continuing.

Any loss of readiness resets accumulated delay. Manual advance/reveal and
choice selection also reset it so a timer expiring alongside input cannot
carry its old delay into the next beat. Switching autoplay off clears its
delay. Pausing freezes it; returning from pause continues from the same time.

## Mandatory interaction and ending

`require_input` blocks autoplay progression. After the player performs the
required action, enabled autoplay continues on later eligible beats.

The contact beat always waits for a real pointer or touch hit on Nami's offered
fingertip, after its text is revealed. Neither an authored choice default nor
autoplay can synthesize that hit. After acknowledgement, the existing
0.45-second contact feedback finishes and the story continues. This contact
completion behavior also applies with autoplay off.

Once the final beat's text, motion and voice have finished, autoplay disables
itself and clears the delay. It never presses restart; a later episode restart
is an explicit player action.

## Language and checkpoint continuity

Changing to a different language clears the delay and waits for the localized
current line to become ready, including its replacement recording. Selecting
the current language preserves the timer.

The existing version-4 in-session checkpoint may include an optional
`autoplay` dictionary with `enabled` and `elapsed_seconds`. A Lab detour
preserves eligible elapsed time without advancing the story while it is away.
Historical cue reconstruction does not run autoplay. Saved elapsed time is
discarded when language or the current voice source changes, or restored
readiness no longer holds. Older checkpoints without autoplay data remain
valid and use the root's initial enabled setting (currently false) with zero
elapsed delay. This adds no durable save migration contract.

## Composition and verification

[Intertitle](../../packages/game_presentation/addons/game_presentation/text/INTERTITLE.md) owns text reveal;
[Text Reveal Audio](../../packages/game_presentation/addons/game_presentation/audio/TEXT_REVEAL_AUDIO.md) owns
playback. Neither advances this game's story. Autoplay's host observes both
and applies the authored delay and input gates. Point Contact continues to
own only hit testing and acknowledged state. Command Link and Presentation
Lab retain their own gameplay controls and independent state.

P97 adds three paired UI text keys; the 57 beats, 60 paired story-review rows,
approved display text and 80 prepared character recordings remain unchanged.
Focused verification and any native captures are recorded in
[the project QA record](../../packages/game_presentation/history/QA.md). This contract defines behavior; it does
not imply new audio listening approval or upstream promotion.

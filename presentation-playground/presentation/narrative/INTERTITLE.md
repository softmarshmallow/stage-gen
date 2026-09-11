# Intertitle

`intertitle.gd` owns plain-text typewriter reveal and explicit continuation.
It is a `RefCounted` controller, independent of games, scenes, speakers, and UI.
Its first use is a protagonist's internal monologue between dialogue beats.
Chapter headings, elapsed-time cards, and other narration can use the same API.

The host owns the black screen, centered text, fonts, layout, fade transitions,
input, and the decision to pause and resume the scene beneath it. This controller
does not create a shared game UI, advance a story, play audio, or load assets.
Hosts can separately compose [Text Reveal Audio](TEXT_REVEAL_AUDIO.md) from its
visible-character sample, with their own voice/fallback/silent policy.

## Contract

| Call | Behavior |
|---|---|
| `start(text, settings = {}) -> Array[String]` | Start a new reveal from zero. Valid starts replace the previous cue. Errors leave it untouched. |
| `advance(delta)` | Consume explicit seconds during reveal only. Negative, zero, and nonfinite deltas have no effect. |
| `sample() -> Dictionary` | Return `text`, integer `visible_characters`, and `phase`. Sampling has no side effects. |
| `request_advance() -> bool` | During reveal, show the whole text and return `false`. While holding, finish and return `true`. Idle or already finished returns `false`. |
| `is_active() -> bool` | True while revealing or holding. |
| `clear()` | Cancel the cue and reset to empty idle state. |
| `get_state() -> Dictionary` | Return a detached, JSON-compatible snapshot. |
| `restore(state) -> Array[String]` | Atomically restore a validated snapshot, without advancing time or triggering completion. |

The phases are `idle`, `revealing`, `holding`, and `finished`. Revealing the last
character enters `holding`, which lasts indefinitely. A continuation action
returns `true` exactly once; the host can then resume dialogue. Finished samples
retain the completed text until the next start or clear.

The sole setting is `chars_per_second`, default `32.0`, allowed range `0.1–240.0`.
Text must contain 1–16,384 Unicode codepoints. Unknown settings, malformed state,
unsupported versions, and inconsistent phase/time combinations are refused.
Bounds protect accidental input while leaving ordinary authored cues flexible.

## Time, text, and composition

Call `advance(delta)` from the host's chosen clock. Do not call it during a route
detour when the intertitle should pause. For route recreation, save `get_state()`
and restore it later. The snapshot carries fractional reveal time, so a detour
does not discard progress toward the next character. A tiny numeric tolerance
at character boundaries prevents frame accumulation from delaying one character.

The count follows Godot `String.length()`: **Unicode codepoints**, including
spaces and newlines. It is not a byte count or a grapheme count. Combining marks
and multi-codepoint emoji may appear in stages. Bind plain `Label.text` and
`Label.visible_characters`; if using `RichTextLabel`, disable BBCode or adapt
markup separately. This controller does not parse markup or punctuation pauses.

```gdscript
var intertitle = preload("res://addons/game_presentation/text/intertitle.gd").new()

func begin_monologue() -> void:
    if intertitle.start("I did not expect anyone to be waiting for me.").is_empty():
        monologue_overlay.show() # Host-owned backdrop and centered Label.

func tick_monologue(delta: float) -> void:
    intertitle.advance(delta)
    var frame = intertitle.sample()
    monologue_label.text = frame.text
    monologue_label.visible_characters = frame.visible_characters

func on_monologue_input() -> void:
    if intertitle.request_advance():
        monologue_overlay.hide()
        resume_dialogue() # A host decision, never a controller side effect.
```

The host must consume the action that starts or dismisses an intertitle so that
one click does not also advance the underlying scene. It may route keyboard and
pointer actions to the same method. Rendering, route input, and scene pause are
integration responsibilities; controller checks do not prove those behaviors.

Focused offline check:

```sh
/Users/universe/.local/bin/Godot --headless --path presentation-playground --script res://qa/intertitle_checks.gd
```

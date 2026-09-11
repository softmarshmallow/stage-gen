# Text Reveal Audio

`text_reveal_audio.gd` is an optional Godot `Node` presenter for dialogue or
intertitle audio. It accepts the visible Unicode codepoint count from a host's
text reveal; it never advances text, dismisses a cue, or owns game/UI state.
Its two child `AudioStreamPlayer` nodes produce non-positional audio.

## Host decisions

`configure(settings) -> Array[String]` atomically replaces configuration and
stops an existing cue. Invalid settings leave playback and settings unchanged.
Omitted settings use these defaults:

| Setting | Default | Meaning |
| --- | --- | --- |
| `mode` | `auto` | Use a supplied voice, otherwise typing. `typing` explicitly selects typing; `silent` suppresses both. |
| `typing_stream` | `null` | Null selects the built-in procedural tap; otherwise supply an `AudioStream`. |
| `typing_volume_db` | `-14.0` | Typing gain, from -80 to +6 dB. |
| `voice_volume_db` | `0.0` | Voice gain, from -80 to +6 dB. |
| `min_interval_seconds` | `0.06` | Minimum typing pulse spacing, from 0.02 to 1 second. |
| `bus` | `Master` | An existing Godot audio bus for typing and, by default, voice. |
| `voice_bus` | Same as `bus` | Optional existing bus for voice only; typing keeps `bus`. |

Hosts should supply short, non-looping typing samples and finite, non-looping
voice clips. Voice assets, language selection, volume UI, and whether a host
uses this component are host decisions. This is playback support, not TTS.
Voice and typing never overlap for a cue; voice completion does not switch to
typing while the same text continues revealing.

Hosts can compose [Voice Processing](../audio/VOICE_PROCESSING.md) by supplying
its private output as `voice_bus`. This presenter owns no DSP effects or bus
lifecycle. Both routing names validate before the current cue is interrupted;
omitting `voice_bus` preserves the existing shared-bus behavior.

## Lifecycle and timing

1. Add the node to a scene tree, optionally configure it, then call
   `begin(text, voice = null, visible_characters = 0, resume_voice_seconds = 0)`.
   This interrupts the prior cue and starts a supplied voice once in `auto`.
   Already-visible text is silent. Empty text is supported for host cleanup.
2. After each natural text advance, call
   `update_reveal(visible_characters, delta, audible = true)`. Spaces and Unicode
   whitespace do not trigger sound. Multiple new glyphs coalesce to at most one
   tap per update; the cadence cap drops intervening events rather than queueing
   them. Invalid time deltas are ignored. Typing remains silent while held.
3. Use `sync_reveal(visible_characters)` for manual full reveal or other silent
   cursor jumps. It stops the current typing tap and never interrupts a voice.
   `audible = false` also consumes revealed glyphs silently; it is not a voice
   mute control. Use `stop()` or configure `silent` for that.
4. `set_paused(true)` pauses both playback streams. The host should also suspend
   its text clock. `set_paused(false)` resumes. Pause state survives `begin` and
   `configure`; `stop()` clears the cue, and tree removal stops both streams.

Typing timing follows host-supplied deltas. Voice playback follows Godot's audio
clock and is only synchronized at begin/resume/pause; this is not phoneme or
word timing. Text completion does not automatically cut off a longer voice.
Advancing to a new cue explicitly interrupts the old voice.

## In-session checkpoints

`get_state()` reports policy, active mode, revealed count, pause state, the current
cue's typing pulse count, voice playback position, and voice completion. It does
not serialize audio resources or define a game save format.

The host stops audio while reconstructing a checkpoint, then calls `begin` with
the restored text, selected stream, visible count, and saved voice position.
Pass `resume_voice_seconds = -1` for an already-finished voice; supplying a
position at/after a known clip duration also keeps it finished. For language
changes, the host chooses the replacement stream and resume policy. No old
typing events replay. Seek accuracy depends on the supplied audio format.

## Afterlight host composition (P95/P96)

Afterlight selects localized prepared recordings using its own stable-line
voice policy and source revisions. In `auto`, it sets complete subtitle reveal
before starting a ready voice; intentionally unvoiced lines use the typewriter
and the configured fallback. This presenter does not implement either content
policy or subtitle selection. A cinematic's caption must become visible before
its host starts speech. A language switch restarts the selected language's line;
a same-source checkpoint resumes its saved position. Missing or stale recordings
fall back without requesting generation. See the
[host contract](../../games/bishoujo_afterlight/voice/README.md).

## Built-in sound

`create_default_typing_stream()` creates an original deterministic, mono 44.1 kHz
16-bit PCM tap lasting 26 ms, with a tapered envelope and two restrained tones.
It uses no image/audio generation service and stores no binary asset. It is a
fallback that the host can replace with any suitable sound. Listening quality
and the host's final mix are separate from timing/control-flow checks.

Godot supports [dynamically generated PCM in AudioStreamWAV](https://docs.godotengine.org/en/stable/classes/class_audiostreamwav.html)
and [non-positional playback with AudioStreamPlayer](https://docs.godotengine.org/en/stable/classes/class_audiostreamplayer.html).

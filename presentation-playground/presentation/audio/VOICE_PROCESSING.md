# Voice Processing

`voice_effects.gd` owns an optional non-positional audio bus. The working
taxonomy is **Audio Effects -> Voice Processing -> Transmission Voice**.
Transmission Voice is a preset of this processor. Hologram is a separate visual
effect; the host coordinates both from its own scene and character decisions.
The processor knows no actors, stories, recording paths, subtitles, or languages.

## Configuration and routing

`configure(settings) -> Array[String]` replaces settings with defaults for
omitted fields. Every type, range, preset, and destination is checked before
allocating or changing a bus. Invalid configuration preserves the live state.

| Setting | Default | Meaning |
| --- | --- | --- |
| `preset` | `transmission_voice` | The supported Voice Processing preset. |
| `parent_bus` | `Master` | Existing destination bus, to the left of this private bus. |
| `strength` | `0.65` | Finite number in `[0, 1]`; zero is completely dry. |
| `bypass` | `true` | Boolean; true disables all processing effects. |

After successful configuration, `get_output_bus() -> StringName` gives the
instance's unique bus. Bind selected `AudioStreamPlayer.bus` values to it, or
pass it as Text Reveal Audio's `voice_bus`. The latter keeps typing on its
existing `bus`. Before configuration and after cleanup the output name is empty.
Multiple instances own separate buses and effect resources. The processor never
modifies the parent, Master, another player's routing, or source audio files.

The bus is appended after existing destinations. Reconfiguration rejects itself
and destinations to its right, matching Godot's leftward audio-send rule. Hosts
must leave the processor's bus name, order, and effects under its ownership.
When authoring a new destination after a processor, clean up and configure the
processor again after stopping or rerouting its players.

## Controls, timing, and cleanup

`set_strength(value)` and `set_bypassed(value)` validate and return error lists.
They adjust the current stream without replaying it. `get_state()` exposes the
preset, configuration state, destination/output names, strength, bypass,
effective `processing` state, and filter cutoffs for host diagnostics.

Godot's mixer owns DSP time. This node has no frame clock, coordinate space,
duration, completion event, generated speech, or automatic visual synchronization.
The host owns voice selection, start/stop, subtitles, pause/resume, and checkpoints.
Pause the voice player to pause playback; preserve processor settings. There is
no delay or reverb, so it does not create a long audible tail.

For cue replacement, language change, or replay, stop the prior player and call
`reset()` before starting the selected stream. Reset discards short filter
history while retaining the bus and settings. Stop/reroute all attached players
before `cleanup()`. Cleanup is idempotent; tree exit and deletion also invoke it,
including deletion of a configured node that never entered the tree. Configure
can allocate a new route after cleanup. Checkpoints save host settings and source
playback position, never ephemeral bus names or DSP history.

## Transmission preset and evidence

The chain is a 12 dB/octave high-pass, mild waveshaping saturation, and a
12 dB/octave low-pass. Strength changes the high-pass from 100 to 420 Hz and
low-pass from 9000 to 2800 Hz, with bounded distortion and output attenuation.
The default uses 308 Hz and 4970 Hz cutoffs. This aims for a contained electronic
voice while retaining speech; actual intelligibility remains a listening judgment.
Bypass and zero strength disable the entire chain, retaining unity bus gain.

Godot documents [filter cutoffs and slopes](https://docs.godotengine.org/en/stable/classes/class_audioeffectfilter.html),
[distortion behavior including coloration at zero drive](https://docs.godotengine.org/en/stable/classes/class_audioeffectdistortion.html),
and [runtime audio-bus controls](https://docs.godotengine.org/en/stable/classes/class_audioserver.html).

`qa/transmission_audio_checks.gd` checks private-bus isolation, atomic failures,
cleanup/reuse, pause and replacement, typing's actual dry route, dry and zero PCM
equality, native bass/voice/treble response, and unchanged hashes of the existing
English/Korean Eira recordings. It captures a dry/processed pair per language
under the ignored `qa/transmission-audio/` directory. These are runtime DSP
measurements and audition artifacts, not an independent listening verdict or
approval of the recorded performances.

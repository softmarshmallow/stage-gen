# Transmission Voice runtime evidence

P98 adds a reusable Voice Processing component with the Transmission Voice
preset. This report covers native audio measurements and lifecycle behavior;
it is not a listening verdict or approval of the recorded performances.

On 2026-09-11, `qa/transmission_audio_checks.gd` passed with Godot 4.7.2,
CoreAudio at 48 kHz. The offline run used deterministic PCM tones and the
existing English/Korean `episode.eira_on_the_relay` recordings. No provider
calls or source-audio changes were made.

| Measurement | Result |
| --- | --- |
| Bypass versus direct dry PCM, maximum aligned sample difference | `0.0` |
| Zero strength versus direct dry PCM, maximum aligned sample difference | `0.0` |
| 80 Hz wet/dry gain at strength 1 | `0.00124` |
| 1000 Hz wet/dry gain at strength 1 | `0.555` |
| 12000 Hz wet/dry gain at strength 1 | `0.00105` |
| English dry / wet peak at default strength 0.65 | `0.910 / 0.561` |
| Korean dry / wet peak at default strength 0.65 | `0.774 / 0.443` |

The checks also prove validation before bus allocation, unchanged live state
after invalid control/configuration values, unique concurrent buses and effects,
parent routing checks, repeat cleanup, deletion before tree attachment, reuse
after cleanup, reset preserving the bus, actual typing PCM only on its dry route,
separate voice routing, existing shared-bus fallback, pause/cursor preservation,
replacement completion, and zero leaked buses. All eight selected Eira recording
hashes match the existing manifest; both processed source hashes remain unchanged.

The existing `qa/text_reveal_audio_checks.gd` regression also passed, covering
Unicode reveal, cadence, silent jumps, voice completion, host modes, language
replacement, and Lab checkpoint continuity after the optional voice-bus addition.

The ignored `validation.json` stores detailed measurements and hashes.
`en-dry.wav`, `en-transmission.wav`, `ko-dry.wav`, and `ko-transmission.wav`
contain captures for later audition. DSP was captured before the QA sink's mute;
the measurement run did not perform a human listening review. Band shaping and
safe peaks establish signal behavior, not speech intelligibility or artistic
quality. The Presentation Lab provides the host's live dry/wet comparison.

```sh
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/godot/games/playground --script res://qa/transmission_audio_checks.gd --log-file /tmp/transmission-audio-native.log
```

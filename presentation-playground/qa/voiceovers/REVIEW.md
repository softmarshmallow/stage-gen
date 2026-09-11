# Afterlight voiceovers — P95 review

This review separates source-text classification, runtime playback and recording
integrity from performance quality. **Listening verdict: not performed.** No
claims about pronunciation, emotion, casting quality or translation delivery are
made from file decoding, metadata or screenshots.

## Independent text audit

The actual English and Korean text sets and all 57 authored beats were read.
Each locale has 39 voiced beats and 40 distinct voiced text IDs because both
`courier_reply` alternatives are recorded. The inventory therefore contains 116
localized policy records: **80 generated recordings and 36 intentional `none`
records**. Menus, Lab routes and choice-option labels are outside that inventory.
The spoken choice prompt itself remains Nami's dialogue.

| Speaker | English clips | Korean clips |
| --- | ---: | ---: |
| Nami | 14 | 14 |
| Yuzu | 9 | 9 |
| Sena | 5 | 5 |
| Riko | 6 | 6 |
| Eira | 4 | 4 |
| Keeper | 2 | 2 |

Two cases require semantic classification rather than copying the visual actor:

- `episode.a_hand_to_hold` shows Nami but is the courier's narration. It stays
  explicitly unvoiced.
- `episode.nami_beyond_the_wall` has no visible speaking actor but is Nami's
  offscreen rescue dialogue. It uses Nami's voice.

The 18 unvoiced beats per locale are `undeliverable`, `across_the_threshold`,
`one_more_minute`, `reading_room`, `hold_the_message`, `a_voice_in_the_glass`,
`one_private_question`, `relay_return`, `scarlet_pressure`, `between_addresses`,
`the_unlit_house`, `a_name_is_not_consent`, `the_room_refuses`,
`follow_the_warmth`, `the_return`, `a_hand_to_hold`, `back_to_the_house` and
`the_next_arrival`. The protagonist's dialogue-form lines are included in these
exclusions; a dialogue UI does not imply a generated voice.

## Focused verification

The executable proof is [voiceover_checks.gd](../voiceover_checks.gd). It uses
prepared synthesized streams for provider-free playback tests, then optionally
checks installed generated recordings. These fixtures do not overwrite voice
documents or generated audio.

- The exact cast counts and text exceptions are asserted independently.
- `none`, `pending`, `missing`, `failed`, `stale` and `ready` remain distinct.
  A supplied stream cannot bypass intentional silence, recording status or
  source revision. Text, speech-script and casting changes invalidate recordings.
- Ready ordinary dialogue shows full text and plays one voice. Cinematic speech
  waits until its caption appears. The voice player suppresses typing audio and
  finishing audio does not advance the story or start a fallback tail.
- Real playback pauses with the menu. A different language starts its recording
  at zero; selecting the same language preserves position. Lab returns retain
  the existing resume-on-return behavior and seek the current clip exactly;
  completed voices remain completed. A changed recording revision starts at zero.
- Alternate replies select their own text keys. After-reveal Manpu now appears
  at full-text entry for voiced lines. Contact still requires its actual point
  hit; explicit advance, contact completion and restart replace or stop audio.
- Missing recordings retain the original typewriter/fallback path, and an
  explicit host silent mode overrides ready voice.
- Removing a beat does not make retained, well-formed speech annotations or
  old recordings fatal. The offline status report lists unused configuration
  and media; neither can enter current inventory or playback bindings. The
  focused removal fixture covers two localized scripts, one override and two
  old recordings.

The original [Text Reveal Audio checks](../text_reveal_audio_checks.gd) now run
their episode section with an explicit missing-recording fixture. This retains
the original fallback regression without relying on the absence of assets.
Existing ensemble, contact, Sigh Puff and falling-sweat checks accept either
actual reveal mode while retaining their lifecycle and input assertions.

## Reproduce

```sh
/Users/universe/.local/bin/Godot --headless --path presentation-playground --script res://qa/voiceover_checks.gd -- --game bishoujo_afterlight
/Users/universe/.local/bin/Godot --path presentation-playground --script res://qa/voiceover_checks.gd -- --game bishoujo_afterlight --require-recordings --capture
```

## Final evidence — 2026-09-11

The final native run passes in `/tmp/p95-voiceovers-native-console.log`, with
no assertion, script or exit-leak errors. Its ignored `validation.json` SHA-256
is `672403cf22524989be50eb11ef5c17aced91dc62bd6c5ff22a9bd647c5a0f42c`.
It binds ten runtime/configuration/text sources, all 80 MP3 hashes and four
full-text/pause PNGs at 1280×900 and 2560×1800. Every recorded digest was checked
against the final files. The installed recording-manifest digest is
`73831acb8fd23baaef587abb7faba8a83061c5f15491e18e42bf8c70bb4093e6`.

All 80 current recordings decode in Godot, with durations from 5.12 to 13.20
seconds. The actual mixer produced 75,264 English frames (peak 0.7562, RMS
0.1026) and 121,856 Korean frames (peak 0.8360, RMS 0.1755) for Nami's
`no_ordinary_post` line. These are mechanical playback measurements, not a
listening or pronunciation verdict.

An independent audit of the first passing run exposed an insufficient pause
assertion: Godot reports `playing == false` while paused, so the component
returned its initial cursor rather than its current one. The runtime owner
fixed this by caching the cursor before pausing. The stricter final proof
retains 0.1857596 seconds exactly across pause, and saves/seeks 0.1625397 seconds
exactly through Lab before normal playback resumes. Repeated pause remains
idempotent. An old recording revision restarts from zero.

The independent QA reviewer inspected the English and Korean native full-text
frames and pause menus: dialogue remains readable, all text fits the existing
bottom sheet, the actors remain unobscured above it, and Korean scales cleanly
at 2x. The final full-text frames were re-inspected after the cursor fix. No
audio performance quality is inferred from those images.

The full ensemble regression passes all 57 beats at both viewport sizes with
EN/KO switches and Lab checkpoints in `/tmp/p95-ensemble-console.log`. The
original fallback/audio suite passes in `/tmp/p95-text-fallback-console.log`.
Headless runs retain the known macOS certificate diagnostic and existing
loose-image export warnings, with no assertion/script failures or exit leaks
in these runs. Exported builds and listening remain outside this evidence.

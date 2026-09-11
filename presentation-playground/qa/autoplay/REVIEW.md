# P97 Afterlight Autoplay review

Reviewed on 2026-09-11. The focused host suite and final native run pass with
zero assertion failures. The final native run records ten captures at 1280×900
and 2560×1800 in [validation.json](validation.json), including source and image
SHA-256 values. No provider operation, voice generation, or story-text edit was
performed by this check.

The host suite verifies:

- A new game starts with autoplay off. Natural full reveal, completed cinematic
  motion, and completed prepared voice precede the complete three-second reading
  delay. A frame that begins before readiness contributes no earlier time.
- Real PCM playback blocks accelerated story time; a short PCM fixture ends on
  the audio clock and releases the reading delay. These fixtures establish
  playback behavior, not a voice-quality or listening verdict.
- The authored `help_first` choice fires after five readable seconds. A manual
  `tea_first` choice wins before timeout and selects its own reply. Missing
  defaults and explicit required input hold; an invalid default is rejected.
- The fingertip contact cannot be synthesized by autoplay. An explicit target
  hit retains the existing 0.45-second feedback, then starts a fresh next-line
  timer. The complete 57-beat episode reaches its held ending through the default
  choice and exactly one explicit contact, without dropped or duplicate beats.
- Pause freezes the countdown. A real language change restarts it; selecting the
  same language retains it. Manual continuation and toggle changes reset it.
- A real Presentation Lab detour preserves the enabled setting and a partial
  1.25-second countdown, then continues after the remaining time. The Lab remains
  independent. Version-four checkpoints without autoplay restore manual mode.
- Native mouse activation and focused Space activation toggle autoplay without
  also advancing the story at both tested resolutions. The persistent toggle
  remains available above black monologues; clicking it does not reveal text.

Independent visual inspection of the English/Korean header, Korean choice, and
revealed Korean monologue accepts the UI composition. The autoplay label fits
beside language/menu controls, the selected default and remaining seconds are
readable, and the monologue control stays separate from centered story text.
The rendered checks reuse the existing approved art and do not reassess it.

Final checked source SHA-256:

| Source | SHA-256 |
| --- | --- |
| `games/bishoujo_afterlight/story.gd` | `5dd8ead2283fd80916d4eb94d076a6f6825f095e2f9cfaf818cdda628aa90763` |
| `qa/autoplay_checks.gd` | `6b1955f20bb20a5ea1e4d2c5d498ade637ea6775f0efc1bf7c1265da667838fb` |

The native renderer required normal macOS app access outside the filesystem
sandbox. The stalled sandboxed renderer was stopped. Godot's existing direct
image-loading/export warnings remain; this pass verifies the local experiment,
not an exported game. Audio recording quality was not reviewed.

Reproduce the focused native checks from the repository root:

```sh
Godot --path presentation-playground --script res://qa/autoplay_checks.gd -- --game bishoujo_afterlight --capture-autoplay
```

For a provider-free headless run, add `--headless` before `--path` and omit
`--capture-autoplay`. Captures are overwritten only by native capture mode.

Launch the game:

```sh
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/presentation-playground -- --game bishoujo_afterlight --language ko
```

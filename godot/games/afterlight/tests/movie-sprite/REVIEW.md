# Movie sprite diagnostic: native review

**Accepted for this local diagnostic, with the limits below.** Reviewed on
2026-09-14 by the independent integration reviewer, who did not produce the
prepared body/face assets, runtime player, shader or Lab scene.

The final [native suite](../movie_sprite_integration_checks.gd) passed **259
checks and saved 42 captures**, using Godot 4.7.2 Compatibility on Apple M4 Pro.
The captures use actual 1280 by 900 and 2560 by 1800 window pixels. The separate
headless integration pass completed 105 checks. The coordinator's 18 Python
regression tests passed, including optional diagnostic-media prerequisite reporting.
The final headless-only addition exercises the four actual selector signals and
passed 109 checks. It changes tests only; the reviewed runtime and images are
unchanged. The synthetic player's `PASS` output marker was aligned with the
coordinator and its focused coordinator run passed.

## Observed presentation

- Both characters are clearly separated and readable over the existing Reading
  Lounge background. Heads, hair decorations and hands remain within the scene;
  the lower diagnostic controls deliberately overlap their legs.
- The reviewed face contact sheet contains all nine Yuzu combinations and all
  six Riko combinations. Eyes and A/O mouths are distinct and register with the
  original face without an obvious replacement rectangle, duplicate feature or
  new edge halo. Riko closes only the eye on the canvas left, as declared.
- Native 2x Yuzu half-closed/O and Riko wink/O captures retain registration and
  proportional framing. UI controls reflect the selected manual states.
- Checkerboard captures preserve transparent space around the body, between
  hair strands and around the hands. Existing source edge softness remains.
- Samples at body frames 0, 48, 96, 144 and 191 retain held closed-eye/wink and
  A-mouth states while the cloth and hair positions vary. The English/Korean
  speech captures keep readable subtitles and animate the selected speaker's
  mouth. This is coarse speaking activity, not phoneme alignment.

These are sampled visual observations, not an exhaustive human review of every
frame. The native checker separately compares 1,169 source-transparent locations
at each window size against the rendered background: zero unexpected opaque
samples. Rendered closed-eye/O-mouth differences remain confined to the recorded
facial support: zero changed samples outside that region for either actor at
either size.

## Playback and lifecycle evidence

Both body clocks completed two full loops in **24.003 seconds of native wall
time**, with no new buffering holds during that measured interval. Each decoded
48 pages during the interval and retained at most two resident pages. Earlier
deliberate clock jumps exercise buffering separately; their cumulative counters
must not be mistaken for stalls during the wall-time run.

The suite also verifies repeated wraps under explicit deltas, independent face
selection without body retiming, pause/resume, replay, per-speaker mouth control,
English/Korean line selection, stopping speech, scene removal, a fresh diagnostic
re-entry and restoration of the untouched story's Scenario checkpoint. Removal
releases the route and both player nodes. The player-owned synthetic suite
separately exercises worker/cache cleanup and malformed content refusal.

The first checkpoint assertion failure was a test-harness issue: Godot enabled
processing after node insertion. The check now uses the same ready-time freeze
and settle policy as the existing ensemble suite; no runtime checkpoint change
was needed.

## Evidence and limits

Local ignored evidence lives beside this review:

- `native-summary.json`: final assertions, clock snapshots and all 42 capture hashes.
- `summary.json`: headless assertions and checkpoint comparison.
- `visual-review.json`: independently recorded runtime/manifest hashes and sampled capture hashes.
- `face-review-sheet.png`, `moving-review-sheet.png`: inspection contact sheets.

The final native log is `/private/tmp/afterlight-movie-native-final.log`, with no
script, shader or rendering errors. The headless process emitted the existing
macOS certificate-store environment warning; this is separate from its passing
runtime assertions.

No new generation, audio listening verdict, general facial-animation contract,
bilateral Riko blink, viseme timing or generation-module promotion is established.
The existing private/local media rights and publication status are preserved.

Run the diagnostic from the repository root:

```sh
godot --path godot/games/afterlight -- --game lab --route movie_sprite_study --language en
```

## Package extraction verification, 2026-09-14

The player and compositor now belong to the independent
[Movie Sprite Actor package](../../../../packages/movie_sprite_actor/README.md).
The integration owner inspected the rendered samples after extraction; the
independent artwork review above remains the original acceptance record.
There were no asset or provenance changes.

The final Compatibility run on Godot 4.7.2/Apple M4 Pro passed **263 checks** and
saved 42 captures. Both actors completed two native loops in **24.013 seconds**,
with zero new buffering holds and 48 page decodes each during the measured
interval. Headless integration passed 109 checks against both the normal game
content and its existing external copy. An earlier Forward+ Metal run passed
263 checks too; final lifecycle/cache fixes were verified on Compatibility.
These observations are scoped to this machine and do not certify other backends.

Seven fixed-frame game-region comparisons against the preserved pre-extraction
Compatibility captures are pixel-identical, excluding the host UI. They cover
bilateral eyes/O mouth, canvas-left wink/O mouth, checkerboard transparency,
both window sizes, and moving-body frames 48 and 144. Inspection also found no
new face rectangle, doubled feature, clipping or alpha halo in these samples.
The SDK still relies on preparation to prove fixed face registration; these
assets do not demonstrate moving-head tracking or phoneme alignment.

The package's synthetic suite separately passed **247 assertions**, including
non-Afterlight dimensions/timebases, partial final pages, source refusal,
shutdown/reconfiguration from readiness/failure callbacks, and accounting for the
held displayed texture during seeks within the two-page cache. The independent
copied consumer and its synthetic rendering evidence belong to the package.

Ignored local evidence: `pre-package/` preserves the original captures and
review hashes; `package-comparison.json` records the seven comparisons;
`package-review.json` binds this observation to the runtime, compositor and host
hashes. The final log is `/private/tmp/movie-actor-package-afterlight-native-final.log`.
No new listening, generation or public-media verdict is made.

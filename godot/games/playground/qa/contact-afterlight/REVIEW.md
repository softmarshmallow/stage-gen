# P94 Afterlight fingertip contact - native integration review

**PASS for the required interaction and inspected presentation.** This
reviewer authored QA changes, not the contact controller, story integration
or generated portrait. Nami's fingertip pad and face remain clear above the
dialogue gradient. The target ring sits on the pad at both native sizes, and
its expanding confirmation feedback stays centered. The upper hood crop
fits the close framing. Returning to the ensemble removes the portrait and
contact feedback and resumes Nami's relief line.

## Focused evidence

[`afterlight_contact_checks.gd`](../afterlight_contact_checks.gd) passes with
**six captures at 1280 x 900 and 2560 x 1800**, exactly two confirmation
signals, and an empty error list. Logs are `/tmp/p94-contact-native.log` and
`/tmp/p94-contact-native-console.log`. No script errors or leaked-object
warning occurred in this focused native run.

- The new `a_touch_that_stays` beat requires its line to finish revealing
  before it accepts contact. A viewport mouse event at 1x or touch event at
  2x on the target during reveal finishes the words without confirming.
  Further Space, outside-target input and generic story continuation remain
  gated on the fingertip hit.
- The accepted viewport input confirms exactly once. Repeated hits and Space
  neither emit another confirmation nor reset its timestamp. Feedback holds
  for the authored 0.45 seconds, then advances once to `only_a_second`.
- The target follows the supplied portrait's fingertip UV after projection.
  Its logical center is `(592.5, 551.25)` and radius is 33.75. The target and
  feedback centers both become `(1185, 1102.5)` at 2x; input uses that same
  native viewport projection.
- English/Korean switching, pause and an actual Presentation Lab detour
  preserve both the waiting state and the partially elapsed confirmation
  feedback. Restoring acknowledgement is silent: no additional confirmation
  signal occurs. The restored feedback completes its remaining delay.
- A fresh episode creates an unconfirmed interaction. Restart while awaiting
  contact clears its target and latch and returns to the opening monologue.

The existing
[`afterlight_ensemble_checks.gd`](../afterlight_ensemble_checks.gd) also passes
the complete **57-beat** episode at both window sizes. Contact is included in
its checkpoint families, and its traversal now explicitly fulfills the hit
instead of skipping the gate. Affected downstream seek helpers use the same
required interaction before continuing. This run is recorded in
`/tmp/p94-ensemble-console.log`; it reports the existing macOS certificate
diagnostic and **two ObjectDB instances at process exit**, with no script
failure. The focused native run has neither an exit leak warning nor a
failed assertion; the full-run cleanup warning is not presented as resolved.

## Artifact boundary

The active portrait is the separately reviewed generated asset. This report
verifies its placement and interaction, not a new assessment of raw alpha
cleanup or baked artwork effects. The tests cover the present fixed logical
canvas and in-session checkpoints; they do not establish mobile-device
coverage, durable checkpoint compatibility or a performance benchmark.

[The manifest](manifest.json) binds six capture files, six runtime/text files
including both English and Korean sets, and the active portrait. All hashes
match the final files. Manifest SHA-256:
`f342c0c49b24e41f287330276eff74496510db17c8e2e4e451350e9c4c405a71`.

The 2048 x 1536 portrait's SHA-256 is
`867fa1903e83bf2ff2231e5dcbdcf8b09e1ddf45af3de6421c92633be56a6e3a`.

| Capture | SHA-256 |
| --- | --- |
| [Waiting for contact at 1x](ready-1.png) | `af85e7de6808ff2473d55f1903f1fb367a03ec6b343a293d9ac3d858fbe80904` |
| [Confirmation feedback at 1x](feedback-1.png) | `d4334ca452fde49fbcb73ab594adee43c4725e825080626cbc5b9acc329705f6` |
| [Returned to the ensemble at 1x](returned-1.png) | `6f5cf2b5efff39f62f5a90ced0469e6ea0c1e18b6bfe06934aea4b2bc6f2ae43` |
| [Waiting for contact at 2x](ready-2.png) | `7644ea2bcb4611df75d6efa83d36e265016e9eaa932e9cf9ba76f36679b474a9` |
| [Confirmation feedback at 2x](feedback-2.png) | `a24e3c637c4d3f374227ebd945fff3ee3ed95655e074535843cb10173acc89d5` |
| [Returned to the ensemble at 2x](returned-2.png) | `3e05819f6d0d6a7579c08b0975ed8bfcb98c00aab314d5c795acc70471b5a2f4` |

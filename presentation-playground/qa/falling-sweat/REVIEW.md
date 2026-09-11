# P93 Falling Sweat Drop - focused native review

**PASS.** This reviewer authored the verification changes, not the preset,
story cues or Lab controls. The existing blue sweat-drop raster is readable
beside Sena and Riko, including Riko's closer story framing. The Lab selector,
status and description remain readable in English and Korean. The drop stays
beside the character in the angled 3D preview. No new artwork or renderer was
introduced.

The existing
[`one_shot_manpu_integration_checks.gd`](../one_shot_manpu_integration_checks.gd)
now has a bounded `--falling-sweat-only` native mode. It passes with **six
captures at 1280 x 900 and 2560 x 1800**, seven current source hashes and an
empty error list. Logs are `/tmp/p93-falling-sweat-native.log` and
`/tmp/p93-falling-sweat-native-console.log`; no script errors or leaked-object
warning occurred. Existing raw-PNG import/export warnings remain unchanged.

- `a_modest_name` and `a_proper_hello` wait until their dialogue reveal
  completes, then emit one `sweat_drop` event. Each event selects the existing
  raster and expires after 0.75 seconds without leaving a rendered node.
- On the Lab's fixed actor anchor, the native 2D rectangle moves downward
  between 0.1 and 0.3 seconds by exactly the sampled mark-height displacement.
  Its center X and the actor's posed rectangle remain unchanged.
- Pause and language changes retain event identity and phase. Switching the
  live event to 3D and orbiting the camera by 25 degrees retains the same
  sample; the sprite uses the selected drop texture and remains in the
  camera-facing plane. The 3D viewport uses native window resolution.
- A direct adapter fixture overlaps the falling drop, a later Sigh Puff and
  a persistent stepped loop. Each finite event expires independently, and
  the loop survives. The Lab's variant selector intentionally resets prior
  events when changing attachment anchors; the coexistence assertion uses
  the underlying cast adapter rather than claiming mixed Lab selection.

The extended
[`one_shot_manpu_checks.gd`](../one_shot_manpu_checks.gd) also passes, verifying
the new preset's small invisible opening, zero lateral drift, positive
vertical movement and independent deadlines. The existing
[`manpu_animation_checks.gd`](../manpu_animation_checks.gd) passes through
`--validate-manpu-animation` with the appended preset order and its existing
persistent-animation checks. These are focused data-example checks, not a
new animation framework or performance benchmark.

[The manifest](manifest.json) binds all six images and seven runtime files to
their SHA-256 hashes. Every hash matches the final file. Manifest SHA-256:
`76ed6fe4cb191bb2d99fe7e32a4208e652132469f6af5f55ff8a0f2bf5853644`.

| Capture | SHA-256 |
| --- | --- |
| [Sena story reaction](story-a_modest_name-1.png) | `f496c441fa63571a7c10e514b14674d41476db9342381b60c1767c86c0bf29a1` |
| [Riko story reaction at 2x](story-a_proper_hello-2.png) | `cf7e21316db9bdeca783d627e0828430d8efca49f71cee7c5349999176d189fc` |
| [Lab 2D in English](lab-2d-1.png) | `f6c4f5537bf1d6b4311224e1263afb66574ed81108169c6725669773c667a0ce` |
| [Lab angled 3D in English](lab-3d-angled-1.png) | `e3dbb43b80872ccdfdd7ccc7bc365fe7a1b740d427742e8afad645aa4053b2a0` |
| [Lab 2D in Korean at 2x](lab-2d-2.png) | `621dfe0141e264f7576c55b761299a7592d02264083b593f34f57db0b101e230` |
| [Lab angled 3D in Korean at 2x](lab-3d-angled-2.png) | `941d926a1e94e7c994aff2b8a214ec7364fbcab37ad94b7a31efbd32d65afbcb` |

## Independent visual verdict

**PASS — root reviewer, 2026-09-11.** Inspected `story-a_modest_name-1.png`
and `lab-2d-1.png` at 1280×900, and `lab-3d-angled-2.png` at 2560×1800.
The prepared blue drop is readable beside the temple and stays clear of the
face and dialogue. The angled 3D view retains the same local placement.
English/Korean variant controls and the complete explanation fit. Motion and
expiry are established by the fixed-anchor and lifetime assertions; these
stills establish the resulting appearance and layout.

This verdict binds all six captures and seven current runtime sources in
manifest SHA-256
`76ed6fe4cb191bb2d99fe7e32a4208e652132469f6af5f55ff8a0f2bf5853644`.

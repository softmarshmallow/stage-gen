# Floating transmission display — independent native capture review

Reviewed 2026-09-11 by `transmission_story`. This reviewer inspected the five
native Godot captures listed below and did not produce the artwork or implement
the display renderer. **Visual result: PASS for the inspected compositions.**
This is an independent integration review, not the user's visual approval.

## Inspected captures

Paths are relative to this review. Digests identify the exact images inspected,
because the ensemble capture directory can be refreshed by a later run.

| Capture | Native dimensions | SHA-256 |
| --- | --- | --- |
| [Eira introduction](eira_on_the_relay-1280.png) | 1280 × 900 | `2e5d450fefc0590fa1d9cc8bfd1d0d1a87845ae64fec963412fb06cd19e5f828` |
| [Eira relay instructions](the_return_channel-1280.png) | 1280 × 900 | `1f3879df62b8b04431bad484b3054bd998ffb129863e93c31504c219347e7512` |
| [Eira introduction at double resolution](eira_on_the_relay-2560.png) | 2560 × 1800 | `ff4dea32046b15e565f21fccf6ae440a6da493a42326a658677828d5117484d2` |
| [Eira relay instructions at double resolution](the_return_channel-2560.png) | 2560 × 1800 | `2a77dfee489a14257f3bb71843926e661b1d411979c9dc667598142be262b644` |
| [Return to the group](follow_the_diagram-1280.png) | 1280 × 900 | `cd82561225445a6ce53f03c3ab992dfe751c50324b5a08dcd709126bc67ca65d` |

## Findings

- The floating display is a distinct rectangular object above the laboratory
  emitter. Its perimeter, dark frame, corner marks, and portrait inset remain
  readable against the room. The laboratory is visible around all four sides,
  making the remote feed and the player's environment spatially distinct.
- Eira's portrait and its scanlines remain confined to the inset. Her hair,
  shoulders, and remote workstation do not spill outside the display or appear
  as a second full-body actor in the laboratory. No other character appears in
  either inspected call beat.
- The amber eyes, smile, human face, technical underlayer, white research
  jacket, and communication accessories remain readable under the Hologram
  treatment. Scanlines and the cooler transmission color are noticeable without
  erasing her expression. The face is fully inside the feed at both camera
  positions and both captured window sizes.
- The later instruction beat makes a modest move toward the whole floating
  display. The frame remains fully on screen, with space above the dialogue;
  neither its corners nor Eira's face collide with the title or Korean text.
  The camera retains enough surrounding equipment to establish the laboratory.
- Korean name, location, and dialogue text fit the inspected compositions.
  The longer relay instructions occupy two readable lines without clipping or
  being hidden behind the frame. The bottom gradient separates text from the
  foreground bench. The ready indicator is visible in the instruction capture.
- The double-resolution captures preserve the same composition, frame
  containment, and dialogue hierarchy. No extra clipping or uncovered world
  edge is visible in those images.
- On `follow_the_diagram`, the reading-room background and physical group
  return. Sena is focused, with the neighboring cast partially visible at the
  edges. Eira, the display frame, its scanlines, and the laboratory are absent.
  This inspected return frame shows no visible transmission leakage.

## Limits

These are still-image checks. They do not independently prove float motion,
flicker timing, pause/resume behavior, language-switch continuity, or every
intermediate camera position. The root agent reports a passing native 56-beat
run with 40 captures; this reviewer inspected only the five images above and
did not rerun or re-certify that complete suite.

The source portrait's tiny upper hair tuft still meets its image boundary;
the runtime preserves that source framing. The face and main hairstyle are
intact. The display's camera move is restrained rather than an extreme crop
into the face, which preserves the framed-call context. Final artistic taste
and preferred transmission intensity remain for the user's feedback.

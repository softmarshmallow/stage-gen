# Point Contact

[Point Contact](../../addons/game_presentation/interaction/point_contact.gd) owns one acknowledged contact and a circular
hit test. **Fingertip Contact** is an authored use: the host places that target
over a character's offered finger and reacts when the player touches it.

| API | Contract |
| --- | --- |
| `hit_test(point, center, radius)` | Static, read-only circular test with an inclusive edge. Point and center must be finite and radius finite and positive; invalid geometry is a miss. |
| `confirm_at(point, center, radius)` | Returns whether the point hits. The first hit latches confirmation and emits `confirmed(point)`. Repeated hits remain true so the host can replay feedback, but do not emit duplicate confirmation signals. |
| `is_confirmed()` | Whether contact has been acknowledged. |
| `reset(confirmed_state = false)` | Clears confirmation, or silently restores a host's acknowledged checkpoint when true. Never emits a signal. |

All coordinates and the radius must use the same space. The host derives the
target from its currently presented image and maps mouse or touch input into
that space. Geometry is passed on each call instead of cached, so panning,
window scaling and replacement images do not leave a stale target behind.
Normalized image coordinates are a host art binding, not part of this behavior.

The host decides when contact is available, whether repeated hits are allowed,
what confirmation means for its story, and when to reset. Actor visibility,
entry/reveal gates, cursor/ring appearance, feedback animation, sounds, timing,
pointer routing and dialogue progression all remain host-owned. This controller
has no autonomous processing, time-dependent state, texture or UI dependency.
Independent instances represent independent contacts; no target registry or
general interaction framework is introduced.

Command Link's existing stage maps its `_connected` checkpoint property to this
state and retains its existing entry gate and visual response. Afterlight uses
the same behavior with its own art, story gate and feedback.

[point_contact_checks.gd](../../qa/point_contact_checks.gd) covers circle edges,
coordinate changes, signal/reset semantics and instance isolation. Existing
composition and tactical route checks cover their host integration.

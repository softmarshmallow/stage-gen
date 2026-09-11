# Third actor runtime check

Sera is the right-hand standing actor in the dialogue view. Mira, Lena, and
Sera share the existing active-speaker emphasis. The original ten dialogue
lines retain their indices; Sera's eleventh line owns a sparkle manpu and
returns to Mira with **Read again**. No new transition or shader behavior is
introduced.

Focused Godot validation passed at 1280×900, 720×900, 960×580, and 640×560.
See `validation.log`. It covers three separate standing rectangles, stage
containment, all neighboring face bounds for manpu, the third speaker's
viewport-routed turn and wraparound, text fit, and the existing interaction,
blink, gallery, restart, and location checks. The first draft of Sera's line
failed the smallest-window text-fit check; the installed shorter line passes.

The real OpenGL renderer captured 22 states at 1280×900 in `normal/` and the
same 22 states at 640×560 in `smallest/`; both capture runs completed with exit
code zero and run the focused checks before rendering. Logs:
`capture-normal.log`, `capture-smallest.log`.

Visual inspection of normal and smallest `dialogue_sera.png` and
`manpu_both.png`, normal `dialogue_mira.png`, and smallest `manpu_gloom.png`,
`manpu_sigh.png`, and `terrace_title.png` found complete standing silhouettes,
distinct speaker emphasis, unobscured faces, clear location labels, and fitted
dialogue/controls. At the minimum window, the full-body cast is necessarily
smaller; all three actors and their manpu remain separated and visible.

Installed Sera sprite SHA-256:
`e07ed408cef9f3bd41d8f1f936d3044d6ce1452620b8fe1d008bcd67446d93c0`.
The separate art verdict and source binding are in
`../../art/rounds/third-actor-v1/REVIEW.md` and
`../../art/THIRD_ACTOR_ACTIVE.json`.

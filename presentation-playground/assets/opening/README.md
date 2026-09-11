# Opening videos

The user selected **Deployment** (`command-link-a.mp4`) as the game opening.
Godot plays its matching silent 1920×1080, 24 fps Ogg Theora encode,
`title.ogv`: 22.5 seconds with 18 edited segments.

The alternate edit, Link Under Fire, remains available as `title_b.ogv`
(22 seconds, 20 segments) with `--opening-variant b`. These are two edits
of shared footage. MP4 viewing copies, raw clips, exact prompts, edit decisions,
cost receipts, and review evidence are in [the opening art folder](../../art/opening-v1/README.md).
The earlier local coastal placeholder is retained as `title_placeholder.ogv`.

Godot fits the video into the fixed 1280×900 canvas with letterboxing. The final
video contains the code-authored title and actor names. One understated Begin
Briefing control sits below the footage. The opening loops until the player
explicitly left-clicks or taps the control or scene. Keyboard input, playback
completion, and missing media never enter the story automatically.

Godot fades the footage to black over its final 0.8 seconds and reveals the next
loop over 0.35 seconds. The button remains visible throughout. Fade timing uses
the decoded stream length, so it follows either variant or a replacement clip.
This treatment is applied at playback; the reviewed video files are unchanged.
Missing media leaves a black title screen with the same clickable control.
Video audio remains muted, and the final files contain no audio track.

Normal startup plays Deployment. Explicit `--route game`, `--route menu`, and
demo routes bypass the opening; `--route opening` replays it. Returning from the
menu and starting a new briefing do not replay the opening. Unknown or missing
variant values are refused.

Replace either OGV to change the opening without changing story or demo code.
These remain local prototype assets. Semantic review and local binding do not
authorize publication, fixture promotion, or distribution.

```sh
/Users/universe/.local/bin/Godot --path /Users/universe/Documents/shared/stage-gen/presentation-playground
```

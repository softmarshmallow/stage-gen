# Opening video

`title.ogv` is the game's opening: Deployment, a silent 1920×1080, 24 fps Ogg
Theora encode of 22.5 seconds in 18 edited segments, carrying the code-authored
title and actor names.

Godot fits the video into the fixed 1280×900 canvas with letterboxing. One
understated Begin Briefing control sits below the footage. The opening loops
until the player explicitly left-clicks or taps the control or scene. Keyboard
input, playback completion, and missing media never enter the story
automatically. Godot fades the footage to black over its final 0.8 seconds and
reveals the next loop over 0.35 seconds; the button remains visible throughout.
Fade timing uses the decoded stream length, so it follows a replacement clip.
Missing media leaves a black title screen with the same clickable control.

Normal startup plays the opening. Explicit `--route game`, `--route menu`, and
demo routes bypass it; `--route opening` replays it. Returning from the menu and
starting a new briefing do not replay the opening.

Replace the OGV to change the opening without changing story or demo code.

```sh
Godot --path godot/games/command_link
```

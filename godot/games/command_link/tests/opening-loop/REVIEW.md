# Opening loop verification

2026-09-10. Independent runtime review by the opening-loop QA agent, which did not edit the opening route.

Both native Godot runs passed. A played its 22.5-second cycle and restarted; B played its 22-second cycle and restarted. Neither entered the story automatically. Each second cycle reached full opacity and decoded at 1920×1080 with the original 1280×720 aspect fit inside the fixed canvas.

The sampled end opacity reached 0.0 for A and 0.0015 for B, then returned to 1.0 after restarting. The end-fade captures visibly darken the complete video, including its title, while the Begin Briefing control remains readable. The second-cycle capture restores the opening footage without a changed layout. This is native playback and sampled-frame evidence; the interpolation is the runtime's continuous smoothstep, not a new video encode.

Enter, keypad Enter, Space, Escape, and right-click leave the opening active. A left click on the button, a left click on the video, and a touch each enter the `arrival` story beat without advancing it. The missing-media route remained in place after 2.3 seconds, retained its one button, ignored Enter, and navigated exactly once following an explicit click.

Machine evidence: `a.json`, `b.json`. Captures: `a-*.png`, `b-*.png`. Existing direct-PNG import warnings still occur when the checks enter the game; this pass neither changed exports nor claims export verification.

Re-run either variant with:

```sh
Godot --path godot/games/command_link --script res://tests/opening-loop/native_smoke.gd -- --opening-variant a
```

Use `b` for the alternate opening. The older `qa/opening-v1/native_smoke.gd` records the superseded automatic-completion and keyboard-skip contract and is historical evidence.

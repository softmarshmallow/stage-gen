# 0058 — The night is black, and the picture gate keeps the viewer's

*Ruled 2026-09-06, making the survival game playable on its Godot host.*

## Fact

The web viewer's shared shading chunk kept 38 % of the washed daylight colour
under a blue tint everywhere the fire did not reach (`NIGHT_CHUNK`, `* 0.38`),
so its midnight was a blue dusk in which every tree stayed legible. The Godot
host ported that number verbatim, and its ten-shot picture gate measures the
port against frames the viewer rendered, three of them at night. The user's
ruling on play: "the dark should be darker, completely dark (unless without
fire)."

## Challenge

Two readings. Change the number and let the night shots of the gate diverge,
recording the divergence; or keep the gate's number and add a second one for
play. The first is honest about what the game shows but turns three gate rows
into permanent failures that measure nothing; the second keeps two nights in
the code.

## Ruling

The number is a uniform, `u_night_floor`, and the host owns it: 0 by default,
which is the game, and the viewer's 0.38 under the capture harness, which is
the gate. With no floor everything that would otherwise raise a black frame —
the grade's black lift, the paper grain, the rain's 55 % night factor, the
night vignette's tint — stands down past the light's reach, so the night is
black rather than a grey haze. The gate is a parity gate for the port and it
keeps rendering the viewer's night; it says nothing about the game's darkness,
which is judged by the user from the HUD contact sheet (`tools/ui_shots.gd`).

## Evidence

- `godot/oblique_survival/view/shaders/night.gdshaderinc`: `u_night_floor`
  and the reach gate; `view/shaders/rain.gdshader`: `u_night_keep`;
  `view/vignette.gd`: `active`; `tools/capture.gd`: `VIEWER_NIGHT_FLOOR`.
- The picture gate against the viewer's references after the change: every
  row where it was, night rows included (host README, "Verified against the
  run").
- `ui-night-fire.png` / `ui-night-dark.png` on the contact sheet: a 6 m pool
  round the fire, black beyond it; black with the HUD alone away from it.

## Falsifier

A frame at deep night, no fire lit and no torch, with any pixel of the world
above black, or a gate row for a night shot that moved from its recorded value
because the harness rendered the game's floor rather than the viewer's.

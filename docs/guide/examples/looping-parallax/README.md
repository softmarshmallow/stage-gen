# Example: looping parallax (a user recreates "looping-parallax")

**The ask:** "I have background layers. Make each one repeat horizontally. Mirror it by default.
For layers I mark `repaint`, have a model repaint the seam instead, and fall back to mirroring if
the repaint isn't seamless. Then give me a manifest and a preview I can scroll."

```
looping-parallax/
  workflows/looping-parallax.yaml
  nodes/seams.py          # loops_already (judge), layer_repaint (paid), seam_check (judge)
  nodes/compose.py        # manifest + preview frame (~60 lines of Pillow)
  prompts/seam.md
  views/parallax.html     # a scrolling preview (~80 lines of canvas code)
  inputs/harbor.yaml + art/*.png
```

```bash
gnode plan looping-parallax --inputs inputs/harbor.yaml     # 0 paid calls if every layer mirrors
gnode run  looping-parallax --inputs inputs/harbor.yaml --live --max-usd 2
```

## What this example tests

- **Plan-time facts and assertions.** Width and opacity are read from the files while planning,
  so a narrow layer is refused before anything runs.
- **Conditions on run-time verdicts.** `repaint` and `mirror` are *maybe* steps. The plan prices
  the repaint as worst case and shows both dashed.
- **Fallback without magic.** A judge with `regenerate … then: continue`, a conditional `mirror`,
  and an explicit `select`.
- **Paid work inside a user's node.** `layer_repaint` calls `ctx.image_edit`. Editing the seam math
  re-runs the node, but an identical edit request is answered from the cache.
- **A custom view on a step.** It shows the composed layers scrolling, and replaces our viewer's
  built-in parallax player.

## Friction found while writing it

- **The `if:` on `mirror` is the hardest line in the file.** It restates the logic of the steps
  above. A `fallback:` shorthand on the judge (`on_reject: { regenerate: …, then: { use: mirror } }`)
  would read better, but it hides an edge. Recorded in FINDINGS as an open choice.
- **`select` needs to know "accepted".** `first_of` skips outputs whose step was skipped or
  rejected-with-continue. That rule has to be stated precisely.

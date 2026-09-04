# 0038 — Guide residue was a publication defect, not a painting defect

*Ruled 2026-09-03.*

## Fact

Published ground tiles carried a hairline of the guide's own cap colour along the top of every
slab. The recorded diagnosis was that the model was painting *around* the guide.

## Challenge

That diagnosis is the intuitive one, and the obvious repairs follow from it: strengthen the
prompt, or tighten the residue gate that refuses a returned conditioning image.

## Ruling

The diagnosis was wrong. The prompt already named the lighter top band and demanded it be
painted over, and the residue gate already refused two of the three attempts behind the shipped
tile. Publication was the cause: a returned painting ramps its alpha from nothing to opaque
over four or five pixels along the top of every slab, and the canonicalizer composited that
ramp straight onto a base built from the guide's own cap and fill colours — so the hairline was
the fallback showing through the paint's own soft edge. The painting is now laid down twice:
its solid core grown outward to put material colour under the whole rim, then the painting
itself at true alpha, so the edge keeps the softness the provider drew and fades into its own
material.

## Evidence

Over all twelve tiles, re-canonicalized offline with no provider spend, the guide's cap colour
went from up to 0.924 of a row to at most 0.003. Two other shapes were tried and are worse:
hardening the feather publishes whatever the encoder left where nobody could see it, as a line
of yellow and magenta speckle, and growing the core over the whole rim stretches the slab's
dark ink contour into a heavy band.

## Falsifier

Residue on a tile whose painting has no alpha ramp at its top edge, which would put the cause
back on the returned art.

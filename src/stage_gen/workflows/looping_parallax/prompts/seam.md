Image repair task. The supplied image is one horizontal strip of scrolling background art, formed by placing the end of the layer directly against its own beginning. The centre of the image is therefore a hard cut: the artwork does not line up there.

Repaint only the marked middle ${{ span_px }} pixels so the artwork flows through the cut as one unbroken band, with no visible seam, step, or discontinuity.

Everything outside that middle region is FINISHED ARTWORK: reproduce it exactly as given, pixel for pixel, same position, same scale, same vertical alignment. Do not move, shift, rescale, recompose, or restyle it.

Match the existing line weight, palette, lighting, ground line, and horizon exactly. Do not introduce a landmark, a centrepiece, a frame, or text.

Paint the span at full strength edge to edge. Do not fade, feather, blur, ghost, or ramp opacity toward either boundary, and do not use a gradient, haze, glow, or vignette to blend into the neighbours. If the two sides differ, resolve it with drawn content, not with transparency or a soft wash. Empty space inside the span is allowed only where the neighbouring artwork is genuinely empty; elsewhere keep the same density of drawn detail as the sides.${{ description && '

Material reference, describing what this layer is made of and not how to compose it: ' + description + '
Ignore anything in that reference about landmarks, rhythm, centring, or composition.' || '' }}

${{ transparent && 'This is a cut-out layer. Every region that is transparent in the supplied image must stay fully transparent in yours: above the content, below it, and around it. Paint only the same band of content the left and right sides occupy, at the same top and bottom extent. Add no ground, no water, no horizon fill, no backdrop, no matte, and no vignette. Use true alpha, not a colour approximating emptiness.' || 'Keep the plate completely opaque.' }}
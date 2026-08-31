---
name: movie-poster
description: Create original theatrical movie posters from an approved synopsis or precise brief, with story-faithful composition, exact titles, and medium-specific direction for live action, animation, anime, or other chosen film forms. Use for movie one-sheets and their iterations; not for general key art, game covers, or universe generation itself.
---

# Movie Poster

Treat the poster as evidence for an already chosen story, not as a substitute
for choosing the story. A successful poster looks like the film exists; it does
not advertise how much worldbuilding the prompt contains.

This skill teaches selection and review judgment, not one composition or prompt
template. Let the film's medium, genre, audience, and synopsis determine the
poster form.

## Establish the source first

Identify the approved title, synopsis facts, desired visual medium, narrative
focus, allowed copy, and relevant rights constraints before generation. If the
user is still comparing premises or calls the story forced, return to synopsis
work. Do not use image generation to make a weak premise feel important.

Keep the synopsis authoritative. The poster may select, frame, and compress a
real story moment, but it must not silently add a disaster, institution,
costume, symbol, technology, or mystery merely to create a stronger image.

## Choose the film medium

Honor an explicit medium first. A live-action film, stop-motion feature,
hand-drawn animation, painterly animation, and literal anime require different
surface logic and should not be blended automatically. When the user gives no
medium, photographed live action is the default—not a universal quality
standard.

Read [references/medium-direction.md](references/medium-direction.md) when the
medium is unspecified, animated, anime, hybrid, or otherwise consequential.
Name the chosen medium in observable production terms rather than using a loose
style adjective. In particular, when the user asks for anime, make an original
anime theatrical poster; do not translate the request into photorealism or a
generic Western illustration with superficial anime traits.

## Find the truthful visual proposition

Choose one source-supported visual proposition rather than trying to summarize
the whole universe. Depending on the chosen medium and film, it may be a
diegetic scene, portrait, ensemble, object-centered image, character
arrangement, or non-diegetic graphic one-sheet. Let the synopsis and theatrical
intent determine the form.

Every story-bearing person, place, object, costume, symbol, and event must come
from the approved source. A non-diegetic color field, shape, type treatment, or
graphic emblem may be designed for the poster only when it is explicitly
approved as presentation rather than canon; do not let it become an invented
story fact downstream.

Prefer economy and implication over a census of the film. Avoid lore-shaped
props, oversized emblems, colossal scenery, villain tableaux, floating-head
collages, and generic spectacle unless the approved source or user explicitly
calls for that mode. The image should derive its force from the film's actual
human, spatial, material, or graphic logic.

## Live-action realism

When the chosen medium is photographed live action, read
[references/live-action-realism.md](references/live-action-realism.md) before
writing the image prompt. Request plausible location photography, optics,
scale, skin, fabric, weather, and production design. `Photorealistic` alone is
not sufficient; explicitly reject illustration, game concept art, matte
painting, and obvious CGI when those are failure modes.

Use the available image-generation skill and its default built-in tool unless
the user explicitly selects another supported path. Generate one candidate at
a time unless variants were requested. Preserve rejected candidates and make
the current approval candidate unambiguous.

## Typography

Quote every required string verbatim. Unless the user supplied more copy,
request the title exactly once and exclude taglines, credits, billing blocks,
studio marks, pseudo-text, and watermarks. Inspect the rendered pixels: a title
with a missing, substituted, repeated, or invented character is a rejected
candidate, not a close-enough success.

## Review and iterate

Inspect the actual poster against the source and classify any failure before
retrying:

- **story failure:** forced premise, invented meaning, or synopsis conflict;
- **medium failure:** the result does not use the requested medium or drifts
  unintentionally into another;
- **craft failure:** inconsistent anatomy or character construction,
  perspective, scale, materials, texture, lighting, or color;
- **composition failure:** environment unreadable, generic hero pose, clutter,
  or weak hierarchy; or
- **typography failure:** incorrect title or unwanted text.

Change one cause at a time. A story failure returns to the synopsis; it is not
fixed with a larger landscape or more symbolic objects. A technically valid
image that misses the art direction is a rejected semantic candidate, not a
transport retry.

Before presenting an approval candidate, verify:

- exact title and absence of unwanted text;
- requested medium and theatrical composition;
- source fidelity without invented canon;
- medium-appropriate character construction, spatial logic, objects,
  materials, scale, light, and color;
- original, brand-neutral imagery without recognizable public figures or
  protected franchise elements; and
- saved image, prompt, and provenance paths in the project workspace.

Show the candidate with the synopsis and ask for explicit approval before using
it as downstream universe input, promoting it, or publishing it. Until then,
label it exploratory and unapproved.

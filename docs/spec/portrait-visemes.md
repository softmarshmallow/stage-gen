# Portrait visemes

> **Checked by:** none.

> **Contract maturity: proposed canonical TO-BE; unimplemented.** This is the
> target for evolving mouth authoring and playback. Requirements below describe
> that future contract. The [promoted portrait-motion specification](portrait-motion.md)
> remains the authority for current behavior and its four-card limit. This
> document does not change the CLI, authorize implementation, or claim new live
> generation results.

## Decision and scope

Adopt an established nine-shape mouth vocabulary, document our exact profile,
and evolve the existing portrait-motion component to produce it. A viseme is a
visible speech shape; several sounds can share one shape. Familiar terminology
does not establish interchangeable identifiers, timing, or asset contracts.

[Rhubarb](https://github.com/DanielSWolf/rhubarb-lip-sync#mouth-shapes) defines six
basic shapes and three optional extensions. Our proposed full profile includes
all nine. Other tools differ: [Harmony](https://docs.toonboom.com/help/harmony-25/essentials/sound/about-lip-sync.html)
uses eight chart entries, and [Adobe Animate](https://helpx.adobe.com/animate/desktop/multimedia-and-video/symbol-instances.html)
provides twelve viseme slots. These are vocabularies to map explicitly, not one
universal wire format.

The target remains fixed-pose 2D characters, independent blinking, and local
mouth replacement. It does not extend into jaw or head motion, hidden anatomy,
gaze, body animation, or video generation. Nine states are a practical dialogue
target, not a guarantee of phonetic accuracy in every language or art style.
Smiling, angry, or other expressive speech sets are separate future extensions.

## Canonical profile

The proposed profile identifier is `portrait_visemes_9_v1`. Its logical states
use lower_snake_case IDs. External Rhubarb codes retain their exact spelling
only at the adapter boundary; their letters are identifiers, not vowel names.
The drawing vocabulary and mapping follow the
[Rhubarb mouth chart](https://github.com/DanielSWolf/rhubarb-lip-sync#mouth-shapes).

| Canonical state ID | Rhubarb code | Drawing intent / example use |
| --- | --- | --- |
| `rest` | X | Accepted original resting mouth; pauses. |
| `mouth_closed` | A | Sealed, lightly pressed lips; M/B/P. |
| `mouth_narrow` | B | Small opening with teeth close together; many consonants and EE. |
| `mouth_open` | C | Medium opening; EH/AE. |
| `mouth_wide` | D | Wider opening; AA. |
| `mouth_round` | E | Rounded opening; AO/ER. |
| `mouth_pucker` | F | Puckered lips; OO/W. |
| `mouth_fv` | G | Upper teeth contact the lower lip; F/V. |
| `mouth_l` | H | Raised tongue behind upper teeth; L. |

These examples guide drawing; they are not a complete phoneme-to-viseme table.
Speech context, language, and cue smoothing belong to the lip-sync adapter.
Rhubarb compatibility does not require using its recognizer.

`rest` retains the source pixels and must be reviewed as suitable idle artwork
for this profile. An unsuitable source rest makes the profile unsupported;
never silently repaint it. Rest is not automatically interchangeable with
`mouth_closed`: an original smile or parted resting mouth does not prove an
M/B/P closure. Their semantic IDs remain distinct even if a reviewed character
can explicitly bind both to identical artwork. The existing `mouth_a` names an
open vowel drawing and must never be mapped to Rhubarb A by string similarity.
Existing `mouth_smile` and `mouth_a` outputs require review against the chosen
shape definition before any reuse; neither is automatically profile-compliant.

## Assets and generation

The profile identifies meanings independently of atlas packing. A future asset
manifest must declare the profile, bind each available canonical state to its
reviewed source or patch, and record unsupported states and any explicit aliases.
Unknown IDs or missing bindings must be detected before playback. An adapter
may apply a declared reduced-vocabulary mapping; it must not silently invent one
or report the result as a complete nine-state set.

Full profile support requires all nine meanings to have accepted bindings.
Feature admission and vocabulary coverage are separate: today's `partial`
result concerns usable eyes or mouth, not an implemented per-viseme coverage
contract. A usable mouth alone does not establish nine-state support.

Nine logical states normally mean eight new mouth drawings plus source rest.
They do not require nine atlas cells, a 3×3 grid, or a single image job. The
preferred first extension retains four-card generation batches and combines
their bindings under one profile, preserving the current per-card resolution.
Eight new mouths would occupy two mouth atlases; any authored blink cards are
additional. Cross-batch registration and common mouth support must be verified
against the same source before those patches can form one usable set.

Keep the existing pixel-preservation and semantic review rules. Shape openings
must fit local replacement without moving the jaw or repainting foreground
hair. A shape that cannot meet those rules is unsupported. Review must check
the requested shape and transitions at the intended display size; still-image
acceptance alone does not establish speech timing or temporal quality. This
adds shape-specific criteria, not a separate review architecture.

## Timed mouth selection

Keep reusable character art separate from each utterance's timing. A future
mouth track identifies its profile, exact audio artifact and duration, and
ordered cues containing `start_ms`, `end_ms`, and `viseme_id`. Times are integer
milliseconds from the beginning of that audio; intervals include the start and
exclude the end. Cues must satisfy `0 <= start_ms < end_ms <= audio_duration_ms`
and must not overlap. Gaps and completion select `rest`; adjacent equal states
may be merged. External adapters convert time units once at this boundary.

The audio playback position determines the selected mouth; there is no required
render frame rate. Seeking recomputes that selection, pausing holds it, and
stopping restores rest. Eye selection remains independent. All bindings and
audio identity must validate before playback. This future track is not today's
bounded preview timeline and introduces no new accepted CLI fields yet.

A replaceable adapter supplies cues from audio, optionally with a transcript.
Its supported languages and timing limitations must be declared. Generating
another dialogue line reuses the character's accepted mouth art; it does not
require repainting the character. Atlas authoring cost and per-utterance
alignment cost remain separate.

## Evolution boundary

The implementation should first establish the profile and asset bindings,
support atlas batches in the existing contained face workflow, then connect
timed mouth tracks through an explicit adapter. Concrete persisted schemas and
their executable checks arrive with that implementation. Current arbitrary
state IDs, example timelines, and existing manifests retain their meanings;
they are not retroactively labeled as full lip-sync support.

Before claiming this target is implemented, demonstrate a complete reviewed
mouth set, independent blinking, source-preserving reconstruction, and actual
audio-synchronized playback on held-out dialogue. Record unsupported inputs
and language limits. The current promotion remains complete on its existing
scope while this extension is pursued separately.

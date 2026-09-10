# Add blink and mouth states to a fixed sprite

The portrait-motion CLI takes one original character image and produces
selectable facial drawings: a half blink, closed eyes, a smile, and an A-mouth.
Face-crop mode locates the face, authors the four states in one atlas, and
returns an animation at the original sprite size. The source supplies the rest
state, all original alpha, and every pixel outside the active facial patches.

This is a standalone Python pipeline. Its output can be used by a future
consumer without a game package, scene, or runtime host. It animates facial
drawings on a fixed image; it does not create speech audio, infer phonemes,
animate a body, or perform IK.

## Prepare your source

Use a PNG with RGB or RGBA pixels and a matching canonical provenance sidecar
beside it, such as `character.png` and `character.png.meta.json`. Face-crop mode
accepts arbitrary source proportions, including transparent full-body sprites.
Both dimensions must be at most 16383 pixels so the resulting full-size WebP
can be encoded. Keep a source whose face has readable artwork at its native
size: enlargement of a tiny face does not recover missing feature detail.

The sidecar binds the image bytes to their origin and rights record. Keep the
sidecar produced by the original generator or importer. A renamed image needs
its adjacent sidecar renamed with it; edited image bytes require updated,
truthful provenance. Preparation rejects missing or mismatched records.

For a PNG you drew yourself that has no provenance yet, the public gnode
utilities can register the unchanged image locally. The example below records
manual authorship and leaves redistribution approval unreviewed. Use it only
when those statements are true; it must not replace a generated image's actual
provider history. Replace the input path and author attribution first:

```python
from pathlib import Path

from gnode import (
    ArtifactRights,
    BinaryArtifact,
    ProvenanceInput,
    SoftwareIdentity,
    build_artifact_provenance,
    serialize_provenance,
)

source = Path("/path/to/character.png")
record = build_artifact_provenance(
    BinaryArtifact(source.read_bytes(), "image/png"),
    ProvenanceInput(
        provider="local",
        model="manual-artwork-import",
        prompt="Register an unchanged original illustration drawn by its author.",
        component=SoftwareIdentity(name="artwork-import", version="1"),
        tool=SoftwareIdentity(name="personal-artwork-workflow", version="1"),
        attempts=1,
        rights=ArtifactRights(
            status="unreviewed",
            attribution=["Your name"],
            basis=["Original illustration authored by the attributed artist."],
            reviewed_at=None,
        ),
    ),
)
with Path(str(source) + ".meta.json").open("xb") as output:
    output.write(serialize_provenance(record))
```

Run this snippet in the repository's Python environment, for example from a
local script with `uv run python`. It writes only a new sidecar and refuses to
overwrite an existing one. It makes no provider call and does not grant
publication approval.

## Plan the face workflow

From a repository checkout with dependencies installed, choose a new run
directory and prepare it offline:

```sh
uv run stage-gen-portrait-motion prepare --face-crop \
  --source /path/to/character.png \
  --spec docs/examples/portrait-motion/face-four-card.json \
  --run /path/to/new-face-run
```

The [face example](examples/portrait-motion/face-four-card.json) declares a
1024×1024 internal working image and atlas with four 512×512 cards. Those
dimensions describe the face workspace, not your original sprite. The example
requests both eyes and the mouth and includes an eight-second timeline with
independent eye and mouth selections. No character image is bundled with it.
The face workspace and its cards must be square: this mode supports one card
in a 1×1 grid or four cards in a 2×2 grid. Direct-portrait mode retains the
general one-to-four-card layouts described in the specification.

Preparation validates the source and configuration and records an immutable
plan. It does not locate the face yet. The source and run paths must not
traverse symlinks, and the run directory must not already exist.

To keep the existing direct opaque-portrait mode, omit `--face-crop` and use
[four-card.json](examples/portrait-motion/four-card.json). That example requires
an opaque 1024×1536 PNG because its source and atlas share the declared canvas.

## Generate and verify

Paid execution requires explicit live opt-in and provider credentials:

```sh
STAGE_GEN_RUN_LIVE=1 uv run stage-gen-portrait-motion run \
  --run /path/to/new-face-run --live --dotenv .env
```

Use `OPENROUTER_API_KEY` for face localization and structured review. The
default atlas route uses `OPENAI_API_KEY`; preparing with
`STAGE_GEN_IMAGE_PROVIDER=fal` selects the supported fal route and requires
`FAL_KEY` instead. Keys can come from the environment; `--dotenv` is optional
and reads an existing allowlisted local file. See
[provider configuration](models/providers.md) for the route contract.

The locator returns only a spatial face box. It chooses the principal face,
then the caller adds context padding of 35 percent of the longest face
dimension on each side. The existing portrait pipeline decides which eyes or
mouth can safely animate. A located face can therefore yield a partial result
or a refusal; localization is not animation approval.

The usual accepted path contains five provider operations: face location,
feature admission, one atlas image edit, feature geometry, and still-image
quality review. Registration, cropping, patch assembly, and playback are local.
An earlier refusal stops dependent work, and retryable failures stay within
each service's existing attempt limit. Replaying an accepted animation does
not pay for another blink.

The portrait subrun retains its default $6 allowance and $1.50 reservation per
attempt. The locator has a separate $3 allowance and $0.50 reservation per
attempt. Reported dollar costs settle their reservations when available;
unknown costs retain the reservation. These are local accounting allowances,
not invoices or guaranteed provider price caps. Cost varies with usage and
retries. Stage-specific VLM controls and reference optimization are deferred in
[issue #12](https://github.com/softmarshmallow/stage-gen/issues/12).

Check the resulting run without provider calls:

```sh
uv run stage-gen-portrait-motion verify --run /path/to/new-face-run
uv run stage-gen-portrait-motion run --run /path/to/new-face-run
```

The first command verifies retained evidence; the second reuses validated
checkpoints. Missing work fails without live services. A fully verified replay
has zero new provider operations. Code, source, or configuration changes
require a fresh preparation so an old verdict cannot silently apply to new
inputs.

## Use the Python API

The CLI delegates to the same reusable preparation, execution, and verification
functions available to Python callers. For example, prepare a face run offline:

```python
from pathlib import Path

from stage_gen.components.portrait_motion import PortraitMotionSpec
from stage_gen.orchestration.portrait_motion import prepare_run

spec = PortraitMotionSpec.model_validate_json(
    Path("docs/examples/portrait-motion/face-four-card.json").read_bytes()
)
prepare_run(
    Path("/path/to/character.png"),
    Path("/path/to/new-face-run"),
    spec,
    face_crop=True,
)
```

The module's async `run_pipeline` and synchronous `verify_run` recognize both
face-crop and direct-portrait preparations. Live execution uses the same
opt-in and credentials as the CLI. Ordinary gnode services can also be supplied
by a programmatic host under the prepared binding and service-lifetime rules in
the [technical specification](spec/portrait-motion.md#cli-workflow).
An injected face run can provide a separate `locator_service`; otherwise its
supplied `structured_service` handles both localization and portrait review.

## Read the result

Inspect the returned JSON status:

| Status | Meaning |
| --- | --- |
| `complete` | Every requested feature was admitted and passed still review. |
| `partial` | A nonempty subset passed; excluded features keep their source drawing. |
| `refused` | A valid location, feature, registration, or quality decision refused the result. |
| `failed` | Execution or integrity checks failed. |

The CLI exits unsuccessfully for `failed`; inspect the status rather than
assuming that process success means every requested feature is usable. A
wide-open source mouth may be unsupported while both eyes produce an accepted
blink. Selecting a mouth state then keeps the original mouth. The retained
full-body face-crop demonstration exercised that partial result; it does not
establish a success rate for arbitrary new characters.

Accepted face-crop runs expose these parent-run outputs:

| Output | Use |
| --- | --- |
| `render/manifest.json` | Relative artifact references, state selections, placement, and the authored `timeline`. |
| `render/animation.webp` | Local preview at the original full sprite size. |
| `render/states/*.png` | Full-source PNG combinations, including unchanged rest/rest. |
| `render/patches/*.png` | Native padded-face patches to place at the manifest's integer offset. |
| `crop/transform.json` and `crop/work.png` | Recorded crop mapping and opaque internal face workspace. |
| `locator/` | Face-location plan, request, verdict, and spend ledger. |
| `portrait/` | The contained eight-stage atlas run, including donor, geometry, quality, and provenance evidence. |

Paths in the parent manifest resolve from the parent run directory. A patch's
RGB already includes its edge blending; its binary alpha marks pixels to
replace. The manifest declares
`patch_application: "replace_selected_rgb_preserve_original_alpha"` and gives
`offset_xy` for placement. Retain the original sprite alpha and do not resize
or alpha-blend the patch a second time. PNG
states preserve original hidden RGB under zero alpha; the WebP encoder may
normalize that invisible RGB.

Still-image review and pixel checks do not establish temporal quality. Results
retain `temporal_review: "not_performed"` and `publication_authorized: false`.
Full-source output inherits the contained face still verdict; native
reconstruction adds deterministic pixel checks, not another semantic review.
Review actual playback separately before accepting a generated animation as
art. The pipeline keeps the existing registration refusal behavior; the
experimental context-registration continuation, foreground restoration, and
hidden-anatomy reconstruction are not part of this workflow.

## Select a state from native patches

Use the supplied full-source PNG states when that is sufficient. For independent
patch playback, each manifest patch identifies its `state_id` and `feature_id`.
The `mouth` feature belongs to the mouth group; both canvas-side eye features
belong to the eyes group. The manifest's `timeline` holds the authored eyes,
mouth, and duration selections, while `playback` records WebP encoding facts.

The public `apply_offset_patch` helper performs the required RGB replacement
while retaining original alpha. This example constructs closed eyes with the
original mouth from a verified run:

```python
import json
from pathlib import Path

from PIL import Image

from stage_gen.components.portrait_motion import apply_offset_patch
from stage_gen.orchestration.portrait_motion import verify_run

run = Path("/path/to/new-face-run")
result = verify_run(run)
if result["status"] not in {"complete", "partial"}:
    raise ValueError("The run has no accepted facial states")
manifest = json.loads((run / result["manifest_ref"]).read_text())
with Image.open(run / manifest["source_ref"]) as original:
    frame = original.convert("RGBA")

selected = {"eyes": "eyes_closed", "mouth": "rest"}
for item in manifest["patches"]:
    group = "mouth" if item["feature_id"] == "mouth" else "eyes"
    if item["state_id"] == selected[group]:
        with Image.open(run / item["ref"]) as patch:
            frame = apply_offset_patch(frame, patch, manifest["offset_xy"])
```

Start each new selection from the original source, then apply only that
selection's admitted patches. Rest and excluded features require no patch.
The resulting `frame` is a Pillow image that a caller may render or encode
locally; this operation makes no provider call.

The [technical specification](spec/portrait-motion.md) describes the graph,
pixel ownership, budgets, provenance, and programmatic service boundaries.

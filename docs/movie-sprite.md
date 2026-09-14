# Movie sprites

`movie_sprite/body/idle` turns a character illustration into a transparent,
recurring body animation. It is a supported asset workflow: generate a candidate,
review its motion, then finish the selected footage. The reviewed body result
provides the canonical image for the existing, separate facial repaint pipeline.
Games decide how to display the resulting videos and images.

Install the Python dependencies with `uv sync --frozen`, and install `ffmpeg` and
`ffprobe` on PATH. The CLI is `stage-gen-movie-sprite`; the Python factory is
`stage_gen.recipes.movie_sprite_body_idle.create_pipeline`. See the
[recipe contract](../src/stage_gen/recipes/movie_sprite_body_idle/README.md) for
its graph, cache behavior and executable example.

## Author motion

Place a character PNG with a transparent background and an `authoring.json`
beneath your chosen input root:

```json
{
  "canonical_image": "character.png",
  "prompt": "A relaxed listening idle with subtle overlapping movement.",
  "positive_prompts": [
    "Loose hair ends settle gently; hair roots stay anchored.",
    "The forearms and fingers make tiny relaxed adjustments.",
    "The chest rises and falls slowly and vertically below fixed shoulders.",
    "Loose fabric settles softly, with little displacement."
  ],
  "negative_prompts": [
    "Keep the head, bangs, face, neck and shoulders still.",
    "No sideways chest motion, body rocking, external wind or expression change."
  ]
}
```

Only `canonical_image` is required. The three prompt sections are optional;
positive and negative sections accept either text or an ordered list of text.
Unknown fields are rejected. A static system template and these sections become
**one video prompt**. The prepared canonical is passed as both the explicit start
and end frame. This route exposes no middle-frame or extra-reference inputs.

Preparation fits the transparent subject on a 720×1280 portrait or 1280×720
landscape green plate. This conditioning size is independent of the requested
video output resolution; finishing retains the video's native dimensions.

The system defaults to anchored head, neck and shoulders, local motion elsewhere,
a fixed camera and green backing, and no sound. Directions can explicitly request
blinking or mouth movement when separate facial control is unnecessary. Prompts
guide generation; they cannot guarantee pixel locks or a useful motion take.

The original canonical supplies identity and pose. **A video model may redraw it,
including the first frame.** After finishing, `body/canonical.png` is the exact
first frame of the transparent loop. Use that new canonical and its sidecar for
facial repaint. Existing eye and mouth processing needs no change.

## Plan, generate and finish

Start with `finish.json`:

```json
{
  "source_mode": "chroma",
  "playback_seconds": 12,
  "loop_closure": "flow"
}
```

Planning is offline. Use a new output directory for every invocation:

```sh
uv run stage-gen-movie-sprite body idle plan \
  --input-root /path/to/inputs --authoring authoring.json --finish finish.json \
  --output-root /path/to/plan --cache-root /path/to/cache \
  --resolution 720p --aspect-ratio 9:16 --duration 8
```

Run only generation first when you want to review a take before authoring spatial
corrections. The budget directory must be separate from input, output and cache
directories, and should persist across attempts:

```sh
uv run stage-gen-movie-sprite body idle run \
  --input-root /path/to/inputs --authoring authoring.json --finish finish.json \
  --output-root /path/to/candidate-run --cache-root /path/to/cache \
  --resolution 720p --aspect-ratio 9:16 --duration 8 --target generate \
  --candidate take-01 --live --budget-root /path/to/budget --budget-usd 10
```

The application binds fal's Gemini Omni Flash 1.1 image-to-video route. It supports
integer durations from 3 to 10 seconds, `360p`, `720p`, `1080p` or `4k`, and `9:16`
or `16:9`. No source frame-rate control is exposed. These limits and the combined
prompt length are checked before spending. Credentials use `FAL_KEY`; optionally
add `--dotenv /path/to/.env` to load an existing allowlisted key file.

The host keeps one retry owner, at most six attempts, with a reservation for each
dispatch. Permanent refusals stop immediately. Interrupted submissions retain
their budget liability and require inspection before another candidate. A new
`--candidate` is a deliberate new draw, not a retry. Recorded costs distinguish
provider-reported amounts from retained estimates; see
[provider configuration](models/providers.md).

Once the footage is selected, adjust `finish.json` and finish from the validated
generation cache without opening a provider:

```sh
uv run stage-gen-movie-sprite body idle replay \
  --input-root /path/to/inputs --authoring authoring.json --finish finish.json \
  --output-root /path/to/finished-run --cache-root /path/to/cache \
  --resolution 720p --aspect-ratio 9:16 --duration 8 --candidate take-01
```

Alternatively, `--source selected.mp4` or `--source selected.mkv` accepts footage
relative to the input root. Add `--source-provenance selected.mp4.meta.json` when
the original sidecar is available. This is a local `run`, without `--live`.
Original provenance remains recorded; supplied footage is never attributed to
the current prompt template. Imported provenance must be portable and sanitized.

## Control the finishing

Finishing applies green chroma extraction, optional fixed regions and local
repairs, a bounded optical-flow loop closure, then playback retiming. It preserves
native dimensions and source frame count. An eight-second, 192-frame source
retimed to twelve seconds still has **192 frames**, played at 16 fps; it is not
two concatenated loops.

`fixed_regions` pins caller-selected polygons to the first keyed frame.
`moving_guards` subtracts regions such as loose hair or ears from those pins.
The fixed field uses a feather outside its boundary; keep it compact so it does
not suppress desired body motion. `local_repairs` optionally aligns and pins a
small opaque attachment. Spatial controls require both `source_sha256` and native
`coordinate_size`, preventing geometry for one take from silently affecting another.
See the [component settings](../src/stage_gen/components/movie_sprite/README.md).

`source_mode: "rgba"` skips chroma extraction. Already finished transparent
footage can use `source_mode: "finished"` with `loop_closure: "none"` and no
spatial corrections; every RGBA pixel is retained. Its endpoint frames must
already match. Each frame must include transparent background and fully opaque
foreground pixels. Use `playback_seconds: null` to retain the source playback rate.

## Consume the assets

| Artifact | Purpose |
| --- | --- |
| `body/loop.mkv` | Native lossless FFV1 video with straight RGBA and no audio |
| `body/canonical.png` | Exact first frame, for the next facial pipeline |
| `body/loop-preview.mp4` | Opaque viewing preview over a dark background |
| `body/contact-sheet.png` | Sampled frames for inspection |
| `body/manifest.json` | Dimensions, frame count, exact playback rate and canonical/source digests |
| `body/processing-report.json` | Settings, per-frame pixel hashes and structural verification |
| `body/frames.zip` | Optional numbered PNG sequence when `export_frames` is true |

All outputs have portable provenance sidecars. FFV1 is the lossless interchange
master; consumers may select their own playback codec or use the PNG sequence.
MP4 previews do not carry transparency. Structural verification checks every
decoded native output frame and the loop endpoints. Visual review still chooses
whether a new character's motion and keyed edges are acceptable, including over
the intended background. That review does not require a game runtime.

For independent eyes and mouth, pass the finalized canonical to the unchanged
[portrait pipeline](portrait-motion.md):

```sh
uv run stage-gen-movie-sprite face repaint prepare --face-crop \
  --source /path/to/finished-run/body/canonical.png \
  --spec docs/examples/portrait-motion/face-four-card.json \
  --run /path/to/face-run
```

`face repaint` is a CLI alias for `stage-gen-portrait-motion`; its input contracts,
generation, validation, budgets and outputs are unchanged. The two pipelines
exchange an image and its provenance, not game state or a combined runtime.

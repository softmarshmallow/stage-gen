# Canonical actor anatomy and visual geometry — proposal

> **Status: proposal only; not ratified or implemented.** Researched 2026-09-11.
> This is the canonical proposal location for this subject. Runtime changes,
> asset annotation, schemas/validators, and generation-pipeline integration are
> deliberately deferred. No annotation calls or reliability experiment ran.

## Recommendation and limits

Use **COCO's 17 human-keypoint names as a baseline vocabulary**, with a small
local definition profile and optional `mouth_center` and `face_region` additions.
Do **not** require seventeen coordinates on every image. Request only the subset
a consumer needs, and permit explicit unavailable observations. The vocabulary
describes humanoid anatomy; image geometry remains useful for other subjects,
which must not be forced into human labels.

This recommendation is conditional on the semantic and accuracy review below.
COCO supplies familiar coarse landmarks, not a complete anatomical measurement
standard, face model, body-size ruler, or guaranteed convention for every point's
exact placement. Reusing its vocabulary requires no COCO-trained detector. The
future automatic annotator is a general-purpose VLM. SAM, a separate pose model,
a deformable skeleton, joint hierarchy, skinning and inverse kinematics are out
of scope.

### Foundation comparison

| Foundation | Useful contribution | Limit and proposed choice |
| --- | --- | --- |
| [COCO keypoint format](https://github.com/cocodataset/cocodataset.github.io/blob/master/dataset/format-data.htm) | Sparse human landmarks and an established image-annotation convention. | Keep the names as the baseline. Mouth, facial extent, fingertips and anatomical stature are absent. Its visibility flags do not distinguish all our missing-data cases. |
| [MPII Human Pose annotations](https://www.mpi-inf.mpg.de/departments/computer-vision-and-machine-learning/software-and-datasets/mpii-human-pose-dataset/download) | Sixteen joints including pelvis, thorax, upper neck and head top, plus a head rectangle. | Shows that COCO is not the only useful minimum. Prefer deriving midpoints to adding redundant center labels; MPII's head rectangle is not our face region. |
| [MediaPipe Pose landmarks](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker#pose_landmarker_model) | Thirty-three landmarks, including eye corners, mouth corners and foot details. | Useful naming references for later additions. Requesting the entire set adds work we do not presently need; no MediaPipe dependency is proposed. |
| [VRM 1.0 humanoid specification](https://github.com/vrm-c/vrm-specification/blob/master/specification/VRMC_vrm-1.0/humanoid.md) | Humanoid bone semantics mapped to glTF nodes for avatars. | A head node is not a face center; eye and limb nodes describe rig transforms. Any projection into surface/image landmarks needs an explicit adapter. VRM is a specification, not merely a paper implementation, and is not a universal 2D anatomy standard. No adoption claim is inferred from stars. |
| [ISO 7250-1 scope](https://www.iso.org/standard/65246.html) | Anthropometric measurements tied to defined physical measurement practice. | Useful discipline for separating landmarks and measurements. A stylized projected drawing does not establish those physical measurements; this proposal claims no ISO conformance. |

The inspected COCO format/evaluation documentation does not settle pupil center
versus eye-opening center, or an exact nasal surface definition. Our operational
definitions below are **local refinements**, not quotations from COCO. Matching
names alone must not be advertised as exact COCO-coordinate compatibility.
Likewise, its [OKS evaluation](https://github.com/cocodataset/cocodataset.github.io/blob/master/dataset/keypoints-eval.htm)
is not a ready-made acceptance threshold for a Manpu attachment or a close-up.

## Five separate concerns

| Concern | What it records | What it does not decide |
| --- | --- | --- |
| Anatomical landmark | A semantically defined projected point and the evidence for its placement. | A bone pivot, parent-child hierarchy, or artistic attachment. |
| Anatomical region | A meaningful area, initially the face, with defined extent and evidence. | The sprite's alpha silhouette or a ready-to-use cinematic crop. |
| Image geometry | Exact image identity/dimensions, crop/trim transform and a named alpha measurement. | Head size, body stature, or anatomical visibility. |
| Scale calibration | A declared reference, measurement definition, units and applicability. | True body size inferred from a bent or foreshortened pose. |
| Consumer attachment rule | Selection of geometry plus artistic offset, scale, fallback and override. | New anatomical truth written back into the asset. |

Anatomy describes the depicted subject, including stylized proportions. It does
not prescribe an ideal human body. An annotation's `observed` placement means
that visible depiction supports the estimate; it is not a claim of ground truth
or direct observation of an internal joint.

## Existing contracts and duplication

This inventory was checked against local source. None of these incumbents is
migrated, reinterpreted or deprecated by this proposal.

| Incumbent | Current behavior | Relationship to the proposal |
| --- | --- | --- |
| Afterlight [root](../../godot/games/playground/games/bishoujo_afterlight/root.gd) and [cast presenter](../../godot/games/playground/games/bishoujo_afterlight/cast_stage.gd) | `eye_uv`, separate `eye_close_uv`, `contact_uv`, and `face_uv_rect` are authored per binding. Standing size uses `HEIGHT = 960`, `TOP = 140`. `_present_mark` offsets a single eye target by fractions of the image rectangle, with a separate sigh offset. | One target currently serves several approximate meanings. Separate eye landmarks/derived eye midpoint, face extent and consumer offsets could reduce duplication. Texture height is presentation scale, not anatomical height. Standing framing remains deferred. |
| Command Link [stage profile](../../godot/games/playground/games/command_link/stage_profile.gd) and integrated [stage](../../godot/games/playground/presentation/stage.gd) | Separate `manpu_head_anchors`, `dialogue_eye_anchors`, and `dialogue_head_top`; sigh/gloom placement has more special coordinates. Camera headroom intentionally protects the upper hair boundary. | Eye targets overlap with Afterlight's concept but not necessarily its definition. Manpu anchors and hair-safe headroom are artistic/visual constraints, not additional anatomy points. |
| Fingertip [layout](../../godot/games/playground/assets/layout.json) and Afterlight contact binding | Mira stores normalized and pixel point/radius values plus image size; Nami has a separate pose-specific point. [Point Contact](../../godot/games/playground/presentation/interaction/README.md) consumes a resolved center/radius. | Pixel/normalized forms duplicate a transform. COCO's wrist cannot replace a fingertip. A later anatomical fingertip addition or explicit interaction extension supplies evidence; the host still owns the hit radius and gesture. |
| [Portrait face locator](../../src/stage_gen/components/portrait_motion/face_location.py) and [face crop](../../src/stage_gen/components/portrait_motion/face_crop.py) | A structured vision call estimates a forehead-to-chin/cheek box in whole-image integer 0–1000 coordinates, then deterministic code adds context and records crop/scale/padding. It allows underlying-boundary inference. | Already close to the proposed face region and acquisition split. `located` alone does not distinguish inferred extent or clipped anatomy. A later adapter must normalize explicitly, preserve lineage, and retain uncertainty. |
| Portrait-motion [review geometry](../../src/stage_gen/components/portrait_motion/review.py) and [contract](../spec/portrait-motion.md) | Eye/mouth replacement polygons use registered-panel pixels and `canvas_left_eye`/`canvas_right_eye` viewer-side labels. | Replacement coverage is not an anatomical point. Viewer-side names cannot be relabeled anatomical-side without view/facing evidence. Keep crop transforms and edit masks separate. |
| [Asset unit](../spec/asset-unit.md), [calibration source](../../src/stage_gen/components/sideview_actor/asset_unit.py), [prepared manifest](../../src/stage_gen/recipes/sideview_platformer/prepared_manifest.py) | Intended magnitude uses `player_height` units; the first baseline frame supplies measured alpha extent and a digest-bound source-pixel scale. Alpha measurement uses values greater than 64. Motion rebasing has separate per-state scale evidence. | Preserve the existing magnitude authority. Anatomy could later support a separately defined body/reference measurement; it must not silently change `subject_extent_px` or create another per-pose world-size estimate. |
| [Sprite processing](../../src/stage_gen/media/sprite_sheets.py), [runtime trimming](../../godot/hosts/common/run_dir.gd), [actor rendering](../../godot/hosts/common/actor.gd) | Ground contact uses alpha greater than 16 and principal-component filtering. Runtime `trimmed_texture` uses nonzero alpha for props/items; `HostActor` separately draws uniform atlas cells without that trim. | Existing “bounds” are already different measurements. Every new bound needs a definition/threshold and coordinate frame. Alpha remains the authority for painted pixels. |
| [Motion presentation](../../src/stage_gen/components/actor_content/models.py), [ADR 0047](../decisions/0047-a-bbox-edge-is-not-an-anchor.md), [ADR 0055](../decisions/0055-a-calibrated-actor-is-measured-by-its-alpha.md) | Per-motion top/bottom anchoring is an explicit stopgap. Interior/per-frame anchors and silhouette-versus-body measurement are recorded gaps; a trailing silhouette already required an inflated height declaration. | Confirms the motivation. Observing a pelvis/wrist does not choose the contact or locomotion pivot. Changes would require later producer **and** consumer contract work. |
| Survival [manifest](../../src/stage_gen/recipes/oblique_survival/manifest.py) and [fire placement](../../godot/hosts/oblique_survival/view/fire.gd) | Separate per-state prop anchors place flames. | Evidence of specialized attachment paths, not human anatomy. Keep such rules/extensions explicit rather than absorbing them into human landmarks. |

The existing [character direction/observation research](dialogue-character-direction.md)
already separates intent from evidence but proposes a dialogue-specific
observation envelope. This document is the canonical proposal for the **generic
anatomy/geometry portion**. Broader direction/consistency work remains separate.
The prose `calibration.cells` example in the asset-unit document is not a field
in the current `SubjectCalibration` output; it is not an implemented general
anatomical-anchor contract.

## Proposed semantic vocabulary

Stable identifiers have stable definitions once ratified. Adding a new landmark
must not change an old one's meaning; a changed meaning needs a new identifier
and explicit mapping. The initial vocabulary is intentionally incomplete.
Retain a versioned definition profile independently of model/prompt versions.

COCO's available names are `nose`, `left_eye`, `right_eye`, `left_ear`,
`right_ear`, `left_shoulder`, `right_shoulder`, `left_elbow`, `right_elbow`,
`left_wrist`, `right_wrist`, `left_hip`, `right_hip`, `left_knee`, `right_knee`,
`left_ankle`, and `right_ankle`. Records use named keys rather than requiring
the dataset's flattened array. Skeleton connections are unnecessary.

The following are proposed placement instructions, requiring ratification:

| Identifier/group | Operational meaning in the depicted view |
| --- | --- |
| `left_eye`, `right_eye` | Midpoint between the depicted medial and lateral eye corners, including a closed eyelid. Excludes eyebrow, gaze-dependent pupil location and eyelash tips. Never substitutes an eyeball rotation pivot. |
| `nose` | Depicted nasal tip, when identifiable. A stylized mark may support an estimate; absence of a clear nose allows unknown. |
| `left_ear`, `right_ear` | Center of the anatomical ear's attachment/root to the head, estimated in projection. Excludes earring and decorative/costume ears. True nonhuman ears require a separately defined profile. |
| Shoulders, elbows, wrists, hips, knees, ankles | Estimated projected articulation centers at the named junctions, not clothing extremities, fingertips, soles or visible outline corners. Covered joints use anatomical inference; these are 2D estimates and do not become rig pivots. |
| `mouth_center` — optional addition | Projected midpoint of the mouth corners (labial commissures), not chin, lower-lip edge, teeth or center of an open-mouth cavity. If corners are supplied by a future richer profile, derive this midpoint instead of annotating both. |
| `face_region` — optional region | Tight axis-aligned envelope of the depicted facial surface: upper forehead/hairline to chin, lateral temples/cheeks/jaw. Exclude hair volume, ears, hat, neck, equipment and padding. Occluded boundaries may be inferred only when labeled as such. This is a local practical region, not an ISO measurement. |

Anatomical **left/right belongs to the character**, regardless of screen
position. Crossing arms, turning away or mirroring cannot be resolved by sorting
x coordinates. Unresolvable sidedness yields unknown labels. A display mirror
transforms points without renaming their original anatomical identity; a new
artwork whose anatomy has deliberately been reflected needs its own declared
side mapping. A COCO augmentation adapter would own any label swap it requires.

`face_region` separates **extent** from visibility. `extent: complete` estimates
the full region inside the reference image, possibly with occlusion. `extent:
clipped` bounds a nonempty in-frame intersection and must never be used as a
full face-size ruler. Evaluate visibility against that intersection: a partly
covered, cropped face can be `occluded` and `clipped`. If any required boundary
is inferred, the whole region uses `placement: inferred`. Reserve region
`out_of_frame` for a wholly outside region. If no envelope can be supported,
use null `bounds` and null `extent`, with the appropriate absence/unknown state.
Hairline/cheek ambiguity can make a complete estimate uncertain; it must not
silently change the region into a hair or head box.

Derive `eye_midpoint`, `shoulder_midpoint`, and `hip_midpoint` from available
pairs. Name them as midpoints: shoulder midpoint is not neck, eye midpoint is
not face center, and hip midpoint is not a pelvis bone transform. The center of
a face box is geometric and need not coincide with an anatomical point. Derived
results inherit uncertainty; one missing endpoint does not become a guessed
symmetrical pair. No crown, chin, hand skeleton, or body-outline annotation is
required initially.

## Image identity, coordinates and missing information

One record belongs to **one subject in one exact sprite/view/frame**, not to an
actor identity forever. Bind the reference image digest, decoded dimensions,
subject selection, definition profile and annotation revision. A frame in an
atlas also needs an unambiguous frame rectangle/index. Expressions can share
registered geometry only through an explicit, reviewed transform/reuse claim;
image changes invalidate that claim. An actor ID alone is never a cache key.

Use continuous source-image edge coordinates: origin at top left, x right,
y down; pixel `(i, j)` has center `(i + 0.5, j + 0.5)`. Store semantic points
and regions normalized to the **complete reference image**, `u = x / W`,
`v = y / H`, not to alpha bounds or the face crop. In-frame coordinates are in
`[0, 1]`; pixel index coordinates must be converted explicitly. Boxes use
`[left, top, right, bottom]` with exclusive right/bottom edges. Do not mix this
with `[x, y, width, height]`.

The reference is the exact image actually available for annotation. If the
original art is already a close crop, anatomy beyond it is unavailable; there
is no invented full-body canvas. Storage trim/crop/resize is a separate mapping:
for crop origin `(cx, cy)` and scale `(sx, sy)`, stored pixels are
`((u * W - cx) * sx, (v * H - cy) * sy)`. For example, source `(400, 200)`
cropped from `(100, 40)` and resized by `0.5` becomes `(150, 80)`; normalized
source coordinates do not change. Retain the inverse mapping, any padding,
atlas placement and reflection. Transform all region corners before bounding
them. Trimming transparent margins preserves content; a crop may hide it.
Runtime clipping changes **current display visibility**, not the source record.

Image dimensions, transforms and alpha bounds come from deterministic inspection,
not VLM guesses. A measured alpha box names the reference raster, channel/range,
threshold/comparison, and component filtering. An opaque image has a whole-image
alpha box; that is not a person segmentation. No alpha channel means unavailable
alpha measurement. Alpha geometry and face-region estimates are distinct.

Keep two small axes per requested point/region:

| Field | Values and use |
| --- | --- |
| `visibility` | `visible`, `occluded`, `out_of_frame`, `unknown`. This describes the source depiction, not certainty. |
| `placement` | `observed` for visible-feature evidence, `inferred` for anatomical completion, `unresolved` when there is no usable estimate. Internal joint centers are estimates even with clear surrounding body evidence. |
| `point` / `bounds` | Normalized geometry or `null`. `out_of_frame` and `unknown` have null geometry; occluded locations may also remain null. No `(0, 0)` sentinel or mandatory invention. |
| `review_needed` | A review flag, not a calibrated probability. Use a short reason for uncertainty/absence. VLM confidence must not be advertised as statistical accuracy. |

Explicit `requested_landmarks` and `requested_regions` lists make omission
meaningful: each list has exactly its requested result keys, even when unresolved
with null geometry. Unrequested keys mean **not assessed**,
not absent anatomy. `observed` requires visible evidence and non-null geometry;
inferred points require an inference reason. Visible/occluded but unresolved
results are permitted. Out-of-frame classification itself is an assertion to
review, not a license to extrapolate. COCO's three flags cannot encode this
entire distinction: its unlabeled state combines causes. Future interchange
must be an explicit, potentially lossy adapter, never reuse zero sentinels.

## Scale calibration and consumer rules

Projected distances are **view measurements**, not physical stature. Hair/gear
do not enlarge a face measurement, but turning, crouching, perspective and
foreshortening still change it. Do not sum joint distances to recover height,
infer a head-to-body ratio, or normalize each pose to its alpha height.

Keep calibration optional, separate and explicit: `unavailable`, or a referenced
calibration identifying its source view/digest, measurement endpoints/definition,
declared length/unit, authority, and applicable asset views. Distinguish a
physical measurement from an artist-declared reference; neither is inferred by
the annotator. A verified uniform-scale registration may transfer a scalar calibration, with
source/target identity and transform evidence. Anisotropic, projective or
deforming mappings cannot transfer one pixels-per-unit value unchanged.
A different pose/camera cannot inherit scale merely because it depicts the
same actor. If no justified transfer exists, the host chooses framing.

For current side-view packages, their authored `player_height` magnitude stays
the authority. A future body-based calibration would require explicit contract
ratification; it is not a replacement hidden inside this metadata. Face-relative
mark sizing is useful **artistic scaling**, not a universal world unit.

| Consumer | Possible rule using geometry | Deliberate host decision retained |
| --- | --- | --- |
| Manpu | Start beside a face-region edge or eye midpoint; sigh starts near `mouth_center`. Scale an offset by face width. | Side, spacing, animation, obstruction avoidance and minimum legibility. A large hat may require an additional visual clearance constraint. |
| Camera | Target the eye midpoint, frame a face region, then obey background coverage. | Crop/headroom, duration, zoom limits and inclusion of hair/equipment. Cropped bounds cannot promise complete-head framing. |
| Character VFX | Use face/body reference points for a local emitter; continue using source alpha for halo coverage. | Effect shape, layer, radius, intensity and timing. An anatomical point does not replace an alpha mask. |
| Interaction | Resolve a specifically named fingertip/contact extension in the correct pose. | Hit area, required gesture, artistic correction and accessibility margin. A wrist is not a fingertip. |
| Registration | Select an available pelvis/foot/grip reference under a later contract. | Which point is stable for that motion and how animation/root motion behaves. This proposal supplies no rig or locomotion solver. |

Resolve in this order: explicit host override; permitted reviewed geometry plus
rule; explicit fallback/omit/reject policy. Do not silently use inferred geometry
for a precision interaction. Apply source-to-storage, actor placement/pose,
group transform and camera exactly once. Specify whether offsets are in source,
actor-relative or screen space. Clamping for UI clearance is a consumer decision,
not a modification of an anatomical coordinate.

## Illustrative record — not an annotation or accepted wire format

All values and the digest below are fictitious. This sketch deliberately shows a
sparse request, observed features, an inferred occluded wrist, a cropped ankle,
and unresolved anatomy. A fuller request could name all seventeen baseline keys.

```json
{
  "proposal_revision": 1,
  "definition_profile": "human_landmarks_draft",
  "subject_id": "subject_0",
  "view_id": "three_quarter_crop",
  "image_geometry": {
    "source_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "width_px": 1000,
    "height_px": 1200,
    "coordinate_space": "source_image_edges_normalized",
    "visible_alpha": {
      "bounds_px": [110, 30, 910, 1200],
      "channel": "alpha_8bit",
      "comparison": "greater_than",
      "threshold": 0,
      "component_filter": "none"
    }
  },
  "annotation": {"method": "vlm_estimate", "review_status": "unreviewed"},
  "requested_landmarks": ["left_eye", "right_eye", "mouth_center", "left_wrist", "right_ankle", "right_hip"],
  "requested_regions": ["face_region"],
  "landmarks": {
    "left_eye": {"visibility": "visible", "placement": "observed", "point": [0.55, 0.18], "review_needed": false},
    "right_eye": {"visibility": "visible", "placement": "observed", "point": [0.43, 0.19], "review_needed": false},
    "mouth_center": {"visibility": "visible", "placement": "observed", "point": [0.50, 0.28], "review_needed": false},
    "left_wrist": {"visibility": "occluded", "placement": "inferred", "point": [0.72, 0.65], "review_needed": true, "reason": "Sleeve and held object hide the wrist; forearm direction supports only an approximate placement."},
    "right_ankle": {"visibility": "out_of_frame", "placement": "unresolved", "point": null, "review_needed": false, "reason": "The depicted leg continues beyond the bottom crop."},
    "right_hip": {"visibility": "unknown", "placement": "unresolved", "point": null, "review_needed": true, "reason": "The coat and pose do not support a reliable position or visibility classification."}
  },
  "regions": {
    "face_region": {"visibility": "visible", "placement": "observed", "bounds": [0.36, 0.08, 0.64, 0.34], "extent": "complete", "review_needed": false}
  },
  "scale_calibration": {"status": "unavailable"},
  "extensions": {}
}
```

In this sketch the derived eye midpoint is `(0.49, 0.185)`; it is not separately
annotated. A low review flag does not turn an unreviewed record into accepted
metadata. The full future envelope must bind annotator/model configuration,
prompt/definition revision and independent review to exact source/output digests;
the example omits those implementation details deliberately.

Extensions use explicit namespaces with their own definitions, units and
versions, for example an `example_game_weapon` entry containing a muzzle
attachment. They cannot override `left_wrist` or redefine its coordinate space.
Anatomical additions such as an index fingertip belong in a documented anatomy
profile/extension until adopted into the core, whereas a muzzle is never anatomy.
Readers may ignore optional extensions; a consumer that requires one must report
its absence. Wire evolution and unknown-field admission still require ratification.

## Stress cases

| Example | Expected interpretation and limit |
| --- | --- |
| Large hair, horns or decorative ears | Face geometry excludes them; anatomical ears are not costume ears. Visual clearance remains host-authored. Hidden hairline/ears may be unresolved. |
| Equipment outside the body | Alpha captures the gear; anatomy does not grow with it. A weapon muzzle is an extension. Body scale cannot be inferred from either bounding rectangle. |
| Full-body standing sprite | Request body points when useful; distinguish ankle articulation from floor contact. A separately authored reference may support calibration, but being upright is not proof of true size. |
| Portrait or close-up | Request face points/region. Outside limbs get explicit unavailable results only if requested. A chin-to-chest shot may have no usable eyes or complete face region. |
| Turned, crouched or foreshortened pose | Preserve anatomical sidedness and record projection/inference limits. Never rescale to an assumed upright stature or swap left/right by x order. |
| Occlusion | Label it; infer only supported positions with a reason or leave null. A distant hidden eye must not be mirrored automatically from the visible one. |
| Expression/animation changes | Bind each changed frame; closed eyes can still have an eye-opening midpoint. Registered unchanged regions may be reused only with explicit evidence; mouth changes and pose changes require their own geometry. Consumer smoothing must not conceal incorrect annotation. |

## Ownership and future VLM-only evaluation

The **asset metadata contract** owns semantic definitions, source coordinates,
uncertainty and reference identity. It contains no engine vectors, game names,
provider routing, animation graph or generated-art prompt policy. Packaging may
bind a record to an asset; it must not recalculate its anatomical meaning.

The **annotation process** owns VLM prompting, requested subsets, model/config
identity, validation and annotation provenance. Deterministic inspection supplies
dimensions/alpha/transforms. Integration into a generation recipe would be a
separate explicit change; generic gnode services remain unaware of actor anatomy.
Manual source artwork must be annotatable through the same future boundary.
Existing structured-vision face localization is evidence of an available route,
not evidence that the broader annotation task is reliable.

The **runtime consumer** owns placement rules, permission to use inferred points,
fallbacks, temporal smoothing, transform composition and overrides. It never
calls a provider to play or repairs missing metadata by inventing anatomy.

Propose a small evaluation **after separate authorization**, using one selected
general-purpose VLM and no SAM/pose-estimator oracle:

1. Select twelve source views with exact digests: Nami/Yuzu/Riko/Keeper standing,
   Mira open/closed, Nami close/detail/contact, Eira's portrait, and two contrasting
   frames from an existing side-view motion strip. These bindings already exist
   in the [playground roots](../../godot/games/playground/games/bishoujo_afterlight/root.gd)
   and [tactical profile](../../godot/games/playground/games/command_link/stage_profile.gd);
   select the strip/frame pair from the existing package at evaluation time.
   Cover large hair, gear, facial crop, turned/foreshortened pose, occlusion and
   frame variation. If a true crouch or occlusion case is absent, report the
   coverage gap instead of claiming that stratum was tested.
2. Before calls, two human reviewers define usable point tolerances and region
   extents on those sources, keeping disagreement/unknown cases. These are
   review references, not asserted 3D ground truth. They are not supplied as
   answers to the VLM. Compare time for the same requested geometry and final
   consumer placement: manual authoring from scratch versus reviewing/correcting
   VLM output, including its review and override work. Counterbalance order and
   report model latency separately. Existing finished anchors are references,
   not measured manual timing. No reference annotation is created in this task.
3. Request the small facial subset on eight views and the full body vocabulary
   on four views where body evidence is relevant; nulls are legitimate. Freeze
   prompts first. Repeat four hard views once to measure instability: sixteen
   successful annotation calls planned, with any technical attempts separately
   counted under the existing retry policy. No iterative success-chasing or
   new art generation. Set a spend cap in that later authorization.
4. Validate finite coordinates, requested-key closure, state/geometry consistency,
   side meaning, box extent, digests and exact crop/inverse mapping locally.
   Successful JSON parsing is not semantic acceptance.
5. Review an overlay per source: distinct observed/inferred markers, face box,
   labelled anatomical sides, crop outline, and a list for null results. Show
   candidate camera/Manpu/contact placement at intended display scales beside
   the current manual placement. Inspect blink/pose pairs as flipbooks; never
   draw a skeleton unless useful strictly as a diagnostic connection overlay.

Provisional **consumer-based** acceptance targets, to be calibrated before the
study rather than reported as achievements:

| Measurement | Starting useful-accuracy target |
| --- | --- |
| Eye/mouth placement | 95% of assessed visible face points within 5% of reviewed face width, **and** the selected consumer's screen-error budget. |
| Camera framing | Projected target error at most 8 logical pixels on the 1280×900 review canvas; no unintended eye/chin clipping in the reviewed shot. |
| Manpu/sigh placement | Final rule position within 10 logical pixels of the reviewed acceptable placement, with no unwanted eye/mouth overlap. Report anatomy error separately from artistic offset changes. |
| Precision contact | An anatomical fingertip extension, if separately included, must place the target within 4 logical pixels or 10% of the host's hit radius, whichever is stricter. Failure retains the current manual override; wrist accuracy is irrelevant to this test. |
| Face region | Suggested IoU at least 0.8 against reviewer extent, plus inclusion of required facial features and exclusion of hair/gear. Evaluate complete and clipped regions separately. |
| Body points / animation | Visible articulation estimates within 5% of a clearly visible reviewed torso reference span; undefined spans are excluded and counted. Registered unchanged facial points should not introduce more than 3 logical pixels of attachment jitter. Different poses are evaluated against their own references. |
| Uncertainty and workload | No silent side swaps or invented coordinates for out-of-frame/unknown results; report availability and correction time alongside error. A target is at least 80% of consumer-eligible views usable without moving points and lower median authoring time than current manual placement. |

Report errors/availability by landmark and difficult-case stratum, not just an
overall average. Abstention is preferable to invention but is not free success:
unknown output on usable visible anatomy reduces coverage. Occluded estimates
are reported separately and remain review-only until justified. Twelve views
cannot establish general reliability; repeated-call agreement also cannot prove
correctness. If face points work and body points do not, ratify only the useful
subset. The study may justify keeping manual calibration and contact forever.

## Ratification questions and explicit deferral

Before implementation, decide:

1. Accept COCO-name reuse with these local placement definitions, particularly
   eye center, ear root and projected articulation centers? Do stricter names
   need separate IDs before any data is persisted?
2. Accept optional mouth center and the face-region boundary/complete-versus-
   clipped rule? Hidden forehead/cheek ambiguity is the key expected review cost.
3. Which requested subsets and consumer error budgets justify automatic use;
   when may inferred geometry be consumed without manual correction?
4. What reviewed reference can calibrate body scale, and which views have an
   evidenced transfer? This does **not** decide standing-character framing.
5. Where will metadata be packaged, how will definition/schema versions and
   extension requirements be admitted, and who can approve annotation reuse?

No runtime implementation, asset annotation, paid calls, generation graph,
manifest/schema change, dependency installation, migration or module promotion
is authorized by this document. Standing framing parameters remain deferred.
The next decision is whether to ratify the vocabulary and authorize the bounded
evaluation, not whether to build a humanoid rigging framework.

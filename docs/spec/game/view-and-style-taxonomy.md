# Game view and style taxonomy

> **Contract maturity: proposed TO-BE.**
>
> This specification defines canonical target terminology, profile identity,
> and namespace rules for game view, camera, gameplay space, asset view, and
> visual style. It does not claim that a profile is implemented, record support
> status, or define a project plan.

The [Game contract](../../game-contract.md) owns the game-wide domain model.
The [authored contract schema](authored-contract-schema.md) documents the
currently executable `game.toml` vocabulary. Until a new executable schema is
ratified and implemented, `side_view_2d` remains the only accepted projection
of the scrolling-preview recipe.

## Purpose

Camera-dependent game generation needs more precision than labels such as
“side view,” “top-down,” “three-quarter,” or “isometric.” Those labels commonly
mix several independent facts:

- how world points are projected into an image;
- where the camera is posed relative to the world;
- which dimensions gameplay occupies;
- how depth and occlusion are resolved;
- which direction a subject faces inside an asset; and
- how the image is rendered aesthetically.

A module that depends on one of those facts must not infer it from another. A
side-oriented actor strip, an orthographic camera, a side-plane collision model,
and a hand-painted background are compatible choices, but they are not
synonyms.

The words **MUST**, **MUST NOT**, **SHOULD**, and **MAY** below are normative for
future contract and module design. They do not alter current runtime behavior.

## Coordinate conventions

Taxonomy values describe semantic axes rather than engine-specific `x`, `y`,
or `z` names:

- **world up** is the local gravity-opposing axis;
- the **ground plane** is perpendicular to world up;
- **screen horizontal** and **screen vertical** are image-plane axes;
- the **view direction** is the ray from the camera toward its target; and
- **subject forward** is the intrinsic forward direction of an actor or prop.

Camera pose can be measured with three angles:

- **azimuth** rotates the view direction around world up;
- **elevation** is the magnitude of the view direction's angle below the ground
  plane: `0°` is horizontal and `90°` is vertical nadir; and
- **roll** rotates the image plane around the view direction.

Contracts SHOULD preserve numeric pose when exact reconstruction matters.
Qualitative labels classify pose families; they are not substitutes for numeric
calibration.

## Orthogonal taxonomy axes

### Scene dimensionality

| Term | Definition |
| --- | --- |
| `planar_2d` | Geometry and interaction are represented in one mathematical plane. |
| `layered_2d` | Several 2D image layers produce parallax or ordered depth without a navigable depth volume. |
| `spatial_2_5d` | 2D presentation or constrained motion is produced from a 3D scene or depth-bearing representation. |
| `spatial_3d` | Geometry, camera, occlusion, and interaction occupy a 3D volume. |
| `screen_space` | Composition is placed directly in the image/UI plane and does not imply a navigable world projection. |

“2.5D” describes a relationship between representation and interaction. It is
not a projection type, camera angle, or visual style.

### Projection model

| Term | Definition | Diagnostic property |
| --- | --- | --- |
| `orthographic` | Parallel projection with viewing rays perpendicular to the image plane. | Apparent scale does not change with camera depth; parallel lines remain parallel. |
| `oblique_parallel` | Parallel projection with viewing rays not perpendicular to the image plane. | Parallelism is preserved, but receding axes are sheared. |
| `perspective` | Central projection through a finite camera center. | Apparent scale changes with depth and parallel lines may converge. |
| `screen_space` | Direct image-plane composition without a world-to-image projection. | Placement is defined in viewport or layout coordinates. |

The word **oblique** is overloaded. `oblique_parallel` names a projection model;
`elevated_oblique` below names camera pose. An elevated camera may use either
orthographic or perspective projection.

Painted assets may contain local perspective cues even when a runtime composes
them as layered 2D sprites. The asset's **pictorial projection** and the
runtime's **scene projection** MUST therefore be recorded separately whenever
they differ.

### Camera-pose family

| Term | Definition |
| --- | --- |
| `lateral` | View direction is approximately horizontal; the image primarily shows elevation against screen horizontal and vertical. |
| `overhead_nadir` | View direction is aligned with gravity toward the ground plane; elevation is `90°`. |
| `high_elevation_oblique` | View direction is steeply downward but not nadir; object side faces remain visible. |
| `elevated_oblique` | View direction has both horizontal and downward components, exposing ground and vertical faces. |
| `ground_level_oblique` | View is near ground level and rotated away from a principal world axis. |
| `frontal_stage` | Subjects are composed toward the viewer in a fixed presentation stage; this is a composition family, not necessarily a world camera. |

“Top-down” MAY be used as informal product language, but a canonical profile
MUST distinguish `overhead_nadir` from a merely high-elevation oblique view.

### Camera behavior

| Term | Definition |
| --- | --- |
| `fixed` | Pose and framing remain fixed for the lifetime of the composition. |
| `tracking` | Camera position follows one or more targets while preserving a framing policy. |
| `scrolling_axis` | Camera advances primarily along one world or screen axis. |
| `rail` | Camera motion is constrained to an authored path. |
| `room_snap` | Camera changes among discrete authored frames or rooms. |
| `free` | Consumer input may continuously change camera pose within constraints. |
| `authored_move` | Camera pose or framing changes through typed cues inside one shot. |

Camera behavior belongs to a consumer adapter. Generation may depend on its
declared framing envelope, but generic media transforms MUST NOT implement the
runtime controller. Cuts and transitions among shots belong to the
[dialogue and cutscene sequence contract](dialogue-and-cutscene-sequences.md),
not to one camera-behavior value.

### Gameplay space

| Term | Degrees of player freedom | Typical collision domain |
| --- | --- | --- |
| `side_plane` | Longitudinal movement plus world-up movement or jumping | 2D elevation plane |
| `ground_plane` | Two independent axes on the ground | 2D planimetric plane |
| `lane_plane` | Ground-plane movement quantized or constrained into lanes | Lanes plus local offsets |
| `depth_belt` | Screen horizontal plus limited walkable depth, as in a belt-scrolling arena | Bounded 2D ground strip |
| `volume_3d` | Three spatial degrees of freedom, subject to game constraints | 3D volumes |
| `screen_space` | Selection or dialogue interaction without navigable world movement | UI or composition regions |

Gameplay space MUST NOT be inferred from camera pose. An elevated oblique camera
can observe ground-plane, lane, or full-volume gameplay; a lateral camera can
observe a side plane or a depth belt.

### Depth and occlusion policy

| Term | Definition |
| --- | --- |
| `explicit_layers` | Author-declared layer order determines occlusion. |
| `ground_depth_sort` | A ground-space coordinate, often actor foot position, determines draw order. |
| `grid_order` | Tile or cell order determines draw order with explicit exceptions. |
| `depth_buffer` | Projected 3D depth determines visibility. |
| `screen_order` | UI or authored composition order determines visibility. |

Parallax is a camera-relative layer motion policy, not an occlusion policy or a
projection model.

### Ground-grid geometry

| Term | Definition |
| --- | --- |
| `continuous` | No gameplay grid is exposed by the contract. |
| `cartesian` | Orthogonal ground axes form rectangular cells. |
| `diamond` | Two projected ground axes form rhombic cells. |
| `staggered` | Offset rows or columns encode a diamond-like adjacency graph. |
| `hexagonal` | Cells use six-neighbor hexagonal adjacency. |

Grid geometry describes adjacency and coordinates. It MUST NOT be used as
evidence that the camera is isometric.

## Axonometric classification

An **axonometric** view is an orthographic projection of a scene rotated away
from its principal planes. It is classified by the projected scale of the three
principal unit axes.

For projected axis vectors `p_x`, `p_y`, and `p_z`, let
`s_i = length(p_i)`:

- `isometric` requires `s_x = s_y = s_z` within a declared tolerance;
- `dimetric` requires exactly two of the three scales to be equal; and
- `trimetric` has three distinct scales.

In an ideal isometric construction, the projected positive axes are separated
by `120°`. A familiar diamond grid or a “2:1 isometric” pixel tile does not by
itself prove equal foreshortening; many game assets conventionally called
isometric are mathematically dimetric.

A profile MUST use `isometric` only when its axis geometry is specified or
measured. Otherwise it MUST use `axonometric_unspecified`, `dimetric`, or
`trimetric` as appropriate.

## Asset-view taxonomy

Asset view is subject-relative and independent from scene camera pose. Define
subject yaw from subject forward:

- `0°` is `front`;
- approximately `30°–60°` is a `three_quarter_front` view;
- `90°` is `profile`;
- approximately `120°–150°` is a `three_quarter_rear` view; and
- `180°` is `rear`.

Every off-center categorical value MUST include `_left` or `_right` from the
subject's own perspective: `left_profile`, `right_profile`,
`three_quarter_front_left`, `three_quarter_front_right`,
`three_quarter_rear_left`, or `three_quarter_rear_right`. A contract SHOULD
store numeric yaw when frame-to-frame alignment or multi-view reconstruction
requires it.

Pitch-relative asset terms are `above`, `level`, and `below`; exact work SHOULD
store numeric pitch. `top` is reserved for a view aligned with the subject's
vertical axis and MUST NOT be used merely because the scene camera is elevated.

“Three-quarter” without `front` or `rear`, `left` or `right`, subject yaw, or
scene context is ambiguous and MUST NOT appear in a new persisted contract.

### Directional coverage and mirroring

An asset contract MUST state how many subject directions are actually supplied:

| Term | Definition |
| --- | --- |
| `single_direction` | One authored subject view; no other direction is implied. |
| `two_way_authored` | Independent left and right views are supplied. |
| `two_way_mirrored` | One profile view is supplied and its opposite is produced by horizontal reflection. |
| `four_way` | Front, rear, left-profile, and right-profile views are supplied. |
| `eight_way` | Four cardinal and four diagonal subject views are supplied. |
| `continuous` | View is produced from continuous geometry or a view-conditioned representation. |

`two_way_mirrored` requires an explicit mirroring policy. It is invalid when
handed attacks, asymmetric clothing, readable text, held props, lighting, or
silhouette direction would change meaning under reflection.

Directional coverage applies independently to each semantic motion. An idle
strip with two-way coverage does not prove that `attack` or `hurt` has the same
coverage.

### Framing

Framing describes subject extent inside the image, not camera projection:

| Term | Intended extent |
| --- | --- |
| `extreme_long_shot` | Subject is small relative to environment. |
| `long_shot` | Full subject with substantial environment. |
| `full_shot` | Complete subject with functional action margin. |
| `medium_shot` | Approximately waist or torso upward. |
| `close_up` | Head and shoulders or an equivalently tight focal subject. |
| `extreme_close_up` | A detail smaller than the complete head or object. |

Deterministic generation SHOULD replace qualitative framing with measurable
occupancy, crop landmarks, headroom, footroom, and action-safe margins. Dialogue
framing and full-body sprite framing are separate asset contracts even when
both use front-facing subjects.

## Visual-style taxonomy

Visual style is orthogonal to camera and gameplay. A style profile MUST describe
typed facets rather than relying on one genre label.

| Facet | Question answered | Example value forms |
| --- | --- | --- |
| `medium` | What rendering medium is simulated? | gouache, ink, pixel raster, cel illustration |
| `mark_making` | How are visible marks constructed? | flat fill, dry brush, stipple, clustered pixels |
| `contour_model` | How are silhouettes and internal edges treated? | no outline, uniform outline, tapered ink, colored edge |
| `shading_model` | How is form shaded? | unshaded, one-band cel, multi-band cel, continuous tonal |
| `palette_model` | How are colors constrained? | indexed palette, bounded gamut, value-keyed palette |
| `lighting_model` | Which light assumptions shape the image? | flat ambient, soft diffuse, directional key, emissive |
| `texture_model` | What image-surface texture is intentionally visible? | smooth raster, paper grain, canvas tooth, clustered noise |
| `material_model` | How are depicted materials differentiated? | matte, diffuse, metallic highlight, translucent |
| `shape_language` | What geometric tendencies govern forms? | rounded, angular, elongated, compact |
| `proportion_model` | What measurable build governs subjects? | `heads_tall`, limb-to-torso ratios, feature scale |
| `detail_density` | At what spatial frequency does meaningful detail occur? | sparse, focal, uniform, dense, or numeric bands |
| `depth_cue_model` | Which pictorial cues imply depth? | none, overlap, value separation, atmospheric, perspective |
| `optical_treatment` | Which image-plane or lens-like effects are present? | no blur, depth of field, bloom, vignette |
| `motion_treatment` | How is movement visually sampled? | held poses, smear frames, stepped timing, continuous |
| `mood` | What semantic affect is intended? | calm, ominous, playful |

Where automated acceptance depends on a style facet, the profile SHOULD add a
measurable property, such as:

- `heads_tall` and landmark ratios for anatomy;
- palette size or gamut bounds;
- number of discrete shadow bands;
- contour width relative to head width;
- texture energy by spatial-frequency band;
- value-range and saturation bounds; or
- frame cadence and hold counts for motion.

Semantic adjectives remain useful generation direction, but they MUST NOT be
presented as deterministic validation unless a measurement and tolerance are
defined.

`optical_treatment` does not determine the scene projection. A screen-space
composition can simulate depth of field, and a perspective scene can forbid it.
Content exclusions such as lettering, watermarks, borders, or sprite-grid
furniture are artifact constraints and SHOULD remain separate from visual
style.

The current executable vocabulary exposes six facets—`medium`, `palette`,
`light`, `shape`, `surface`, and `mood`. This proposed taxonomy is broader, but
does not add executable values to the current contract.

## Canonical presentation profiles

A **presentation profile** is the immutable composition of selected taxonomy
axes. It is not a style profile and MUST reference style separately.

Profile IDs:

- MUST use `lower_snake_case` and end in `_v<major>`;
- MUST be treated as opaque identifiers by consumers;
- MUST NOT be parsed to recover authoritative field values;
- MUST change major version when an axis or invariant changes incompatibly; and
- SHOULD contain concise diagnostic terms for human recognition.

The initial target profiles are:

### `lateral_orthographic_side_plane_v1`

- layered or planar 2D scene;
- lateral camera pose;
- orthographic-equivalent runtime composition;
- side-plane gameplay;
- explicit layer occlusion;
- side/profile animated actor assets; and
- fixed, tracking, or scrolling-axis camera behavior declared separately.

Background paintings MAY include shallow pictorial depth, but collision and
actor scale do not acquire ground-plane depth from those painted cues.

### `overhead_nadir_orthographic_ground_plane_v1`

- overhead-nadir pose;
- orthographic projection;
- ground-plane gameplay;
- cartesian, continuous, or explicitly declared grid geometry; and
- asset views compatible with nadir composition.

This profile excludes a camera that visibly exposes vertical object faces. That
camera belongs to a high-elevation or elevated-oblique profile.

### `elevated_oblique_perspective_ground_plane_v1`

- elevated-oblique pose;
- perspective projection;
- ground-plane gameplay;
- ground-depth sort or depth-buffer occlusion; and
- perspective-aware environment and actor scale.

This is the precise scene-camera family often called “three-quarter view.” The
unqualified phrase is not its canonical name.

### `axonometric_isometric_diamond_grid_v1`

- orthographic axonometric projection;
- verified equal foreshortening of all three principal axes;
- diamond-grid ground-plane gameplay; and
- grid order or ground-depth sort with declared tall-object exceptions.

### `axonometric_dimetric_diamond_grid_v1`

- orthographic axonometric projection;
- verified equality of two principal-axis scales and a distinct third scale;
- diamond or staggered grid gameplay; and
- explicit tile geometry and draw-order policy.

This is the likely home for many conventional 2:1 pixel-art “isometric” games.

### `screen_space_dialogue_stage_v1`

- frontal-stage composition;
- screen-space placement rather than navigable world projection;
- fixed or shot-sequence camera behavior;
- screen-order occlusion; and
- front or explicitly directed three-quarter subject assets.

A perspective-painted room background does not turn this composition into a
navigable perspective game camera.

## Common-label corrections

Reference sheets and product discussions often use convenient labels that are
too broad for contracts:

| Informal label | Canonical interpretation rule |
| --- | --- |
| Side view | Classify scene pose, projection, gameplay space, and actor view independently. |
| Top-down | Use `overhead_nadir` only for a vertical view; visible object sides imply an oblique pose. |
| Three-quarter camera | Replace with a measured elevated-oblique scene pose; reserve three-quarter for subject-relative asset yaw. |
| Isometric | Verify projected axis scales; otherwise classify as dimetric, trimetric, or unspecified axonometric. |
| Front view | State whether this means subject-front asset view or a frontal screen-space stage. |
| 2.5D | State which representation is 3D and which interaction or presentation remains constrained. |

These distinctions are visible in actual asset compositions. A lateral
platforming scene may use overlapping architecture, atmospheric value shifts,
and painted perspective while gameplay still occupies a side plane and runtime
occlusion remains layered. A dialogue composition may place a perspective room
behind a front or three-quarter medium shot while interaction remains entirely
screen-space. Likewise, attack and hurt strips for one actor can differ in
subject yaw, silhouette, and frame occupancy, so directional coverage and
framing must be stated per motion rather than inferred once from the role.

## Current executable projection

The one current executable value, `side_view_2d`, has the following exact
projection in the scrolling-preview adapter:

```text
scene_dimensionality = layered_2d
camera_pose_family   = lateral
projection_model     = orthographic
gameplay_space       = side_plane
depth_policy         = explicit_layers
actor_asset_view     = side
```

This mapping does not add another accepted profile or prove that every painted
asset is metrically orthographic. The adapter rejects every other projection.

The current role value `three_quarter` is interpreted as subject-relative asset
view only. It must not be reused as a scene-camera projection.

## Namespace and module rules

Modules MUST be named for the narrowest taxonomy dependency they actually own:

| Namespace | Owns | Must not own |
| --- | --- | --- |
| `game_view_*` | Presentation-profile composition and view-dependent generation | Aesthetic style or gameplay simulation |
| `game_camera_*` | Camera pose, framing envelope, or consumer camera behavior | Asset rendering medium |
| `game_asset_view_*` | Subject-relative orientation and multi-view asset requirements | World navigation topology |
| `game_style_*` | Typed aesthetic direction and style measurements | Camera or collision behavior |
| `game_motion_*` | Semantic actor states and animation coverage | Runtime combat rules |
| `game_sequence_*` | Portable sequence graphs, nodes, cues, outcomes, and checkpoints | Engine object paths or renderer internals |
| `game_dialogue_*` | Utterances, speakers, choices, and dialogue advance semantics | Authoritative quest or relationship state |
| `game_cutscene_*` | Shots, blocking, temporal tracks, control leases, and transitions | Generic media transforms |
| `gameplay_*` | Simulation, navigation, interaction, and combat semantics | Image-generation style |

If a module is presentation-profile-specific, its public identifier SHOULD use
the complete profile ID, for example
`game_view_lateral_orthographic_side_plane_v1`. It MUST NOT shorten that to
`side`, `top_down`, `three_quarter`, or `isometric`.

A module that is genuinely view-neutral MUST NOT acquire a view prefix merely
because its first consumer uses one camera. Generic media inspection and
deterministic sprite-sheet transforms remain view-neutral; recipes or consumer
adapters supply profile-specific expectations.

## Ownership boundaries

- The game contract owns profile selection, shared identity, cast-wide
  direction, and cross-contract invariants.
- Taxonomy specifications own semantic terms and profile definitions.
- Generic components own provider-neutral generation and deterministic media
  operations.
- Recipes own which profiles they implement and the artifact assumptions of
  those profiles.
- Consumer adapters own runtime camera controllers, engine coordinates,
  navigation, collision, and rendering behavior.
- Web is one optional consumer and MUST NOT become the authority for game-view
  vocabulary.

## Non-goals

This specification does not:

- declare any target profile implemented;
- select a game engine or engine coordinate convention;
- accept any executable projection other than `side_view_2d`;
- combine visual style with camera identity;
- authorize generated media for fixtures or publication; or
- replace per-recipe asset contracts and acceptance gates.

## Technical references

- [ISO 5456-3:1996 — Axonometric representations](https://www.iso.org/standard/11503.html)
  establishes the technical-drawing projection family used by this taxonomy.
- [Godot `Camera3D`](https://docs.godotengine.org/en/stable/classes/class_camera3d.html)
  is a representative engine boundary that keeps perspective and orthographic
  projection behavior distinct from camera transform and consumer control.

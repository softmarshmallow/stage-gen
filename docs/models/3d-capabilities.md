# 3D AI capability catalog

Checked **2026-09-09**. This is a research inventory of public contracts, released
code and product features relevant to editable character assets. It is not a
quality leaderboard or a declaration of Stage Gen runtime bindings. No inference,
upload or paid operation was run for this survey. Recheck the exact route and
account access before a trial; [provider operations](providers.md) owns execution
policy.

The main finding: **existing 3D + instructions → revised 3D is available**, but
texture generation, geometry resynthesis, local editing and remeshing are
different operations. An editable GLB is a container, not a promise that its
UVs, separate meshes, skeleton or animation survive another service.

Coverage prioritizes Tripo, Meshy, Hyper3D/Rodin, Tencent/Hunyuan, Microsoft
TRELLIS and Hi3D, plus relevant part-generation, rigging and motion systems.
The operation taxonomy spans the current character workflow; the vendor list
is broad rather than every model in existence. Scene/world generation, CAD,
video-only animation and avatar-template products need separate surveys when
those become requirements. Human, SD and anthro proportions do not change this
taxonomy; their quality and rig requirements must be tested separately.

## Read the evidence correctly

| Evidence | Meaning |
|---|---|
| API documented | A public operation schema was inspected. Credentials, account rollout and this asset's success are untested. |
| App documented | A vendor describes a usable product feature. No equivalent headless route is established by that alone. |
| Code + weights | An official implementation and model downloads are published. Installation and inference here remain untested. |
| Research | A paper/project demonstrates a capability; deployable inference is not established. |
| Unconfirmed | This bounded search did not establish support. This is not proof of absence. |

The **operation**, model version, provider and interface are all part of the
identity. A provider's newest geometry model may not be its texture model.
Availability on fal must be checked per route; a vendor logo is insufficient.

## Operation taxonomy

| Operation | Input → output | What it solves; what remains separate |
|---|---|---|
| Reference preparation | Brief/reference images → canonical views, crops, masks | Common identity, palette, lighting and part boundaries; does not create shared 3D context between independent jobs. |
| Geometry generation | Text, one image or multiple views → new mesh, optionally textures | New shape; generated topology and identity need review. |
| Joint part generation | Whole reference → several jointly conditioned meshes | Potential global coherence with editable parts; anatomical divisions and deforming seams are not guaranteed. |
| Segmentation | Existing mesh + optional labels/masks → part assignments/meshes | Separates an existing shape; does not necessarily reconstruct hidden surfaces. |
| Part completion | Segmented mesh → completed part surfaces | Reconstructs occluded/missing geometry; changes the asset and does not automatically weld adjacent parts. |
| Whole-mesh texturing | Existing mesh + text/images → texture maps/materials, often a new model file | Palette, surface detail and baked appearance; rig/UV preservation is a separate question. |
| Local texture editing | Mesh + selected region/view + instruction → changed surface paint | Small marks or face details; unseen sides and projection boundaries still matter. |
| Geometry editing/variation | Existing shape + prompt/region/control → changed shape | Proportions or local additions/removals; may resynthesize topology and lose correspondence. |
| Retopology/remesh | Mesh + density/topology controls → rebuilt/reduced mesh | Complexity and connectivity; quads alone do not prove good joint deformation. |
| UV unwrap/repack/bake | Mesh/UVs/source appearance → new UV layout/maps | Texture storage and transfer; can invalidate existing map correspondence. |
| Rigging/skinning | Mesh, optionally skeleton → joints and vertex weights | Makes deformation possible; does not establish every required finger, paw, tail or expression control. |
| Motion generation/retargeting | Text, motion library, capture or source skeleton → animation | Moves a rig; target contacts, proportions, props and joint mapping still need review. |
| Facial animation | Audio/performance/expression state → facial controls or sprite states | Requires compatible facial targets or authored expression assets; body auto-rigging is insufficient. |
| Material/render finishing | Material parameters/maps + lighting/color policy → rendered appearance | Consistent light response; does not remove baked paint marks or repair geometry. |
| Style adaptation | Dataset/reference style → adapted generator or conditioning | Collection consistency; training and evaluation cost exceeds reusing a prompt. |

## New geometry and coordinated parts

| Model or family | Documented input/output | Access and important limits |
|---|---|---|
| Tripo P2, `P2-20260801` | Text, image or front/left/back/right views → new mesh; native quad option | Direct v3 API; multiview marked Preview. Front/back meets the minimum two views. Integrated `generate_parts` is absent from the inspected P contract; separate segmentation exists. [P2 image](https://developers.tripo3d.ai/en/docs/generation-image-to-model/p), [multiview](https://developers.tripo3d.ai/en/docs/generation-multiview-to-model/p), [changelog](https://developers.tripo3d.ai/en/docs/changelog). |
| Tripo P1 / H3.1 | Text/image/multiview directly; verified fal routes are narrower | fal has versioned [P1](https://fal.ai/models/tripo3d/p1/image-to-3d/api) and [H3.1](https://fal.ai/models/tripo3d/h3.1/image-to-3d/api) routes. P2 and direct mesh-processing parity on fal were not confirmed. Old v2.5 routes are not P2 aliases. |
| Meshy 7 | Text preview/refine, image or 1–4 images → textured model | Direct API and fal [v7 image](https://fal.ai/models/meshy/v7/image-to-3d/api), [text](https://fal.ai/models/meshy/v7/text-to-3d/api), [multiview](https://fal.ai/models/meshy/v7/multi-image-to-3d/api). Geometry views and texture references are different inputs. [Direct multiview](https://docs.meshy.ai/en/api/multi-image-to-3d). |
| Meshy T2 Smart Topology | Text/image → low-poly triangular geometry with vendor-described native separate parts | `model_type=smart-topology`, `ai_model=meshy-t2`; 100–15,000 target faces. A distinct model from Meshy 7, and not an external-mesh segmentation service. [Image contract](https://docs.meshy.ai/en/api/image-to-3d), [text contract](https://docs.meshy.ai/en/api/text-to-3d). |
| Rodin Gen-2.5 | Text/images → new geometry and materials | Direct [Gen-2.5 contract](https://docs.hyper3d.ai/en/api-specification/rodin-gen2-5). Do not infer an editing API from a generation tier or from app features. |
| Hunyuan3D 3.1 Pro | Text or front image plus optional named views → geometry/textured mesh | fal [3.1 Pro contracts](https://fal.ai/docs/model-api-reference/3d-api/hunyuan-3d-v3.1-pro); separate Part/Smart Topology services. Generation does not accept an existing mesh to repair. |
| Hunyuan3D 2 / 2.1 | Image → shape, separately mesh + image(s) → paint | Official [2](https://github.com/Tencent-Hunyuan/Hunyuan3D-2) and [2.1](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1) code/weights. These are not local releases of hosted 3.1. |
| TRELLIS.2 | Image → PBR mesh | [Microsoft code/weights](https://github.com/microsoft/TRELLIS.2), [fal](https://fal.ai/models/fal-ai/trellis-2/api). Remesh/export options can change geometry. A multiview input schema appears on fal's page, but a separate callable multiview route was not resolved in this survey. |
| Hi3D / Hitem3D 3.0 | Image or up to four views → model | Direct and versioned fal [image](https://fal.ai/models/hitem3d/hi3d/v3.0/image-to-3d/api), [multiview](https://fal.ai/models/hitem3d/hi3d/v3.0/multi-view-to-3d/api). Includes de-shading control. Unversioned routes expose older versions; staged texturing has a different version limit. |
| PartCrafter | One RGB image + part count → jointly generated part meshes | Official [code and weights](https://github.com/wgsxm/PartCrafter) released. Research-derived local option for coordinated parts; does not establish textured, anatomically divided, rig-ready SD characters. |

Multiview means several cameras viewing the **same object**. Multipart means
several object components. A canonical front/back/face atlas is useful authoring
context, but named-view APIs need appropriately separated panels. A face close-up
is not a full-body side view. An API's image count alone does not prove support
for arbitrary style references or mixed crop scales.

## Existing mesh → revised appearance

These are the most direct candidates for harmonizing independently generated
parts without requesting new geometry. None is a proven drop-in editor for an
already rigged multipart character in this repository.

| Operation | Conditioning and access | Preservation / control boundary |
|---|---|---|
| Tripo Texture | External GLB/GLTF/FBX/OBJ/STL, up to 150 MB; text, image or four ordered views. Direct v3 `/models/texture`, texture models `v3.0-20250812` / `v2.5-20250123`. [Contract](https://developers.tripo3d.ai/en/docs/models-texture). | Not the P2 geometry model. Supports selected provider-segmented part names; no public local brush mask or exact UV/rig preservation guarantee found. fal equivalent unconfirmed. |
| Meshy Retexture | External mesh + text/image, or 1–4 texture views with explicit Meshy 7; direct `/openapi/v1/retexture`. [Contract](https://docs.meshy.ai/en/api/retexture). | `enable_original_uv` retains existing UV layout by contract; bones, weights, vertex order, parts and clips are not promised. Meshy 7/multiview rollout may be account-gated. Alternatives cannot all be combined in one request. |
| Rodin Generate Texture | External mesh + exactly one reference image + optional prompt; direct `/api/v2/rodin_texture_only`. [Contract](https://docs.hyper3d.ai/en/api-specification/generate-texture). | `texture_delight` removes reference lighting/highlights; `escore` controls simpler/flatter versus richer texture. UV, grouping and rig retention unconfirmed; matching fal operation unconfirmed. |
| Tencent Hunyuan3D 3.0/3.1 Texture | OBJ/GLB + prompt or image; 3.1 adds multiview. Mainland `ai3d` API `SubmitTextureTo3DJob`. [Contract](https://cloud.tencent.com/document/product/1804/126292). | `EnableKeepUV` defaults false; optional PBR, 720–4096 texture size. Rig/group preservation unconfirmed. This is distinct from the older international `SubmitHunyuanTo3DTextureEditJob`. |
| TRELLIS.2 Retexture | Existing mesh + reference image → textured GLB; [fal route](https://fal.ai/models/fal-ai/trellis-2/retexture/api), [local pipeline](https://github.com/microsoft/TRELLIS.2/blob/main/trellis2/pipelines/trellis2_texturing.py). | No prompt, brush mask or keep-UV flag in inspected fal schema. Local implementation normalizes geometry, drops original UV visuals and re-unwraps; carries no original skin/scene contract. fal deployment behavior must be tested separately. |
| Hunyuan3D 2.1 Paint | Supplied mesh + reference images → PBR textures; [released implementation](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/blob/main/hy3dpaint/textureGenPipeline.py). | Default remeshing and UV wrap; turning remesh off is insufficient to establish preserved UVs or skins. No user free-text prompt at this paint entry point. |
| Hi3D Texture | Geometry GLB + reference image; [fal texture](https://fal.ai/models/hitem3d/hi3d/texture/api), [direct task contract](https://docs.hi3d.ai/en/api/api-reference/list/create-task). | fal explicitly supports v1.5 texture models, not latest 3.0 generation. No prompt or full-character preservation guarantee found. Direct examples/version restrictions need reconciliation before use. |

fal's verified [Meshy v5 retexture](https://fal.ai/models/fal-ai/meshy/v5/retexture/api)
offers original-UV reuse but displays an **October 1, 2026 deprecation** notice.
Dedicated v6/v7 retexture parity was not confirmed from a usable schema; do not
invent a replacement route from its name. The direct and fal APIs also differ
in exposed options. Pin the provider contract rather than translating by analogy.

## Local edits, geometry processing and decomposition

| Operation/model | Inputs → output; access | Boundary relevant to character assembly |
|---|---|---|
| Tripo Magic Brush | Uploaded/generated mesh + brushed view region + instruction/paint → local texture change; [Studio feature](https://www.tripo3d.ai/blog/repaint-part-of-3d-texture). | App documented; equivalent public masked-edit API not found. The [character case study](https://www.tripo3d.ai/blog/game-industry-character-workflow) distinguishes front-view edits from hidden rear surfaces. |
| Meshy Texture Edit / Smart Healing | Painted selection + prompt or healing → texture edit; [webapp guide](https://docs.meshy.ai/en/webapp/guides/texture-edit). | App documented; no equivalent public endpoint found. Not geometry repair. |
| Rodin Gen-2 Edit | Existing model + selected region + prompt → local geometry edit; [vendor explanation](https://hyper3d.ai/blog/rodin-gen-2). | App/product documented. External uploads are described in the [vendor's editing guide](https://hyper3d.ai/blog/how-to-edit-3d-model); compatibility with an external skinned multipart character remains unverified. Public [API index](https://docs.hyper3d.ai/en/api-specification/rodin-gen2-5) does not establish a prompted geometry-edit endpoint. Exact unchanged-region, UV and rig preservation need a trial. |
| TRELLIS 1 variation | Existing triangle mesh + text → a new variant; [released example](https://github.com/microsoft/TRELLIS/blob/main/example_variant.py). | Code/weights. Conditional resynthesis, not a masked exact-topology edit. Distinct from TRELLIS.2 image-conditioned retexture. |
| Hunyuan3D-Buffalo 1.0 | Research framework: shape/text understanding, instruction-guided mesh editing, text-grounded part generation. [Paper](https://arxiv.org/abs/2608.02711), [repository](https://github.com/Tencent-Hunyuan/Hunyuan3D-Buffalo1.0). | August 5, 2026 paper/project release; inspected repository did not establish inference code/weights or public service access. Watchlist, not a callable Hunyuan 3.1 feature. |
| Tripo Segment + Complete | External mesh + optional reference segmentation mask, granularity/connectivity controls → labeled parts; segmentation task → completed parts. [Segment](https://developers.tripo3d.ai/en/docs/mesh-segment), [complete](https://developers.tripo3d.ai/en/docs/mesh-complete). | v2 outputs semantic labels; no free-text label input was established. Completion offers generated hidden surfaces or quick boundary caps. Neither is a command to weld a neck while preserving its rig. |
| Rodin Bang | Rodin asset or uploaded model → separated components; optional splitting instruction and strength. [Direct API](https://docs.hyper3d.ai/en/api-specification/bang). | External GLB input is documented. An image is required with a custom model when using an instruction or generating materials. Decomposition does not guarantee continuous deforming joints, retained UVs or a retained rig. |
| Hunyuan3D Part | Holistic mesh → segmentation and completed parts; [official code](https://github.com/Tencent-Hunyuan/Hunyuan3D-Part), [fal Part](https://fal.ai/models/fal-ai/hunyuan-3d/v3.1/part/api). | P3-SAM and light X-Part released; full X-Part in Studio. fal Part accepts FBX, up to 100 MB / 30k faces. Reconstruction can change surfaces and UV/rig correspondence. |
| Tencent staged part generation | Existing model → inspectable segmentation → completed parts; `SubmitHunyuan3DPartJob` in [direct ai3d SDK](https://github.com/TencentCloud/tencentcloud-sdk-nodejs/blob/master/src/services/ai3d/v20250513/ai3d_models.ts). | `EnableStagedGeneration` and `PartSegmentationInfo` expose an intervention between segmentation and completion. This additional control is not established by the fal wrapper; rig/UV preservation remains unverified. |
| HoloPart | Already segmented mesh → completed semantic part meshes; [code/weights](https://github.com/VAST-AI-Research/HoloPart). | Released local completion system; its example requires an upstream segmentation. Does not itself prove seamless character anatomy or texture preservation. |
| Meshy Auto Split | Untextured Meshy-6+ draft → cut/capped printable parts; [webapp guide](https://docs.meshy.ai/en/webapp/guides/3d-model/auto-split). | External uploads unsupported; printing workflow, not an external character segmentation route. Distinct from T2 native parts. |
| Smart retopology / remesh | Existing mesh + target density/topology → rebuilt mesh. [Tripo](https://developers.tripo3d.ai/en/docs/mesh-decimate), [Meshy](https://docs.meshy.ai/en/api/remesh), [Hunyuan fal](https://fal.ai/models/fal-ai/hunyuan-3d/v3.1/smart-topology/api). | New connectivity/vertex correspondence requires skin and deformation validation. It is not general prompt-based sculpting. |
| UV unwrap / conversion | Existing mesh → new UV layout or converted/baked output. [Meshy UV](https://docs.meshy.ai/en/api/uv-unwrap), [Tripo conversion](https://developers.tripo3d.ai/en/docs/models-convert). | Meshy UV: GLB ≤40k faces, new UVs/placeholder material, account rollout. Tripo can repack UVs and explicitly include animation during conversion; that does not guarantee preservation through prior processors. |

## Rigging, motion, expressions and style learning

| Model/service | Modality and availability | What it does not establish |
|---|---|---|
| Tripo Rig / Retarget | Mesh → skeleton/skin; provider rig task + preset → motion. Direct [rig](https://developers.tripo3d.ai/en/docs/animations-rig), [retarget](https://developers.tripo3d.ai/en/docs/animations-retarget). | v1 humanoid and v2.5 creature support differ. No complete finger/paw/tail/face guarantee; rig-check is suitability, not deformation acceptance. Presets depend on rig version/type. |
| Meshy Rig / Animation | Humanoid textured GLB → rig; rig task + preset or generated motion → animation. [Rig](https://docs.meshy.ai/en/api/rigging), [animation](https://docs.meshy.ai/en/api/animation), [fal rig](https://fal.ai/models/fal-ai/meshy/rigging/api). | Arbitrary existing external rig import for animation is not documented. Facial and tail controls are not promised. |
| Meshy Text-to-Motion | Prompt → 2–10-second motion; Prime FBX / Swift BVH. [Direct API](https://docs.meshy.ai/en/api/text-to-motion). | Standalone motion still needs retargeting; does not rig the target mesh. Dedicated fal parity unconfirmed. |
| Tencent automatic rigging | Existing model → rig; documented humanoid and nonhumanoid inputs in [official ai3d SDK](https://github.com/TencentCloud/tencentcloud-sdk-nodejs/blob/master/src/services/ai3d/v20250513/ai3d_models.ts). | Nonhumanoid motion templates are not supplied. Required paw/ear/tail controls and weights remain untested. |
| UniRig / SkinTokens (TokenRig) | Mesh → skeleton and skin weights; [UniRig](https://github.com/VAST-AI-Research/UniRig), [SkinTokens code/weights](https://github.com/VAST-AI-Research/SkinTokens). | Released local options. SkinTokens also accepts an existing skeleton for skin prediction and a texture/scale transfer option; this is not evidence of complete animation/morph preservation or this character's quality. |
| HY-Motion 1.0 | Text → 3D human motion; [code/weights](https://github.com/Tencent-Hunyuan/HY-Motion-1.0). | Generates motion, not a custom character mesh or its rig; retargeting to SD/anthro proportions remains a separate task. |
| NVIDIA Audio2Face-3D | Audio → facial animation controls; [models/SDK](https://developer.nvidia.com/ace-for-games), [output contract](https://docs.nvidia.com/ace/audio2face-3d-microservice/2.0/text/architecture/audio2face-ms.html). | Requires compatible facial targets/retargeting. It does not supply the desired original SD cat face, expression sprites or a complete facial asset automatically. |
| TRELLIS.2 LoRA | 3D examples → stage-specific adapters for structure/geometry/texture; [fal trainer](https://fal.ai/models/fal-ai/trellis-2-lora-trainer), [inference](https://fal.ai/models/fal-ai/trellis-2-lora/api). | Dataset and training/evaluation project; not persistent shared context automatically gained by repeating a style prompt. |

Local availability is not installation on this workspace: several published
implementations require NVIDIA/CUDA. TRELLIS.2 documents at least 24 GB GPU
memory; SkinTokens documents at least 14 GB. Deployment and model/dependency
licenses are part of admission for a selected route, not established by this
catalog's links.

## Challenge → operation selection

These are engineering recommendations, not measured rankings of model quality.

| Observed failure | First operation to consider | Escalation if the controlled comparison fails |
|---|---|---|
| Head and body react differently to light | One explicit material/color-management policy applied to the saved asset | Texture harmonization if differences remain under the same shading. |
| Painted fur/highlights/palette differ across parts | Texture the assembled static character with shared full-character views; compare a UV-reuse route first | Local repaint, controlled reference de-lighting or new texture generation. |
| References cause baked lighting or mismatched detail density | Prepare consistent views with restrained lighting and detail; retain identity marks | Use documented de-light/texture controls; do not assume settings transfer between versions. |
| Neck protrudes or opens during motion | Inspect rest geometry, overlap ownership, weights and pose deformation | Agent/DCC geometry correction, changed part boundary, or a continuous base; prompt geometry editing is experimental. |
| Independent parts disagree in shape or scale | Common reference/scale/pose contract and explicit assembly landmarks | Whole-character generation followed by segmentation, or native joint part generation. |
| Fingers, paws or tail missing | Inspect required joint coverage and actual deformation | Specialized rig model or agent-authored joints/weights; joint names alone are insufficient. |
| Face needs discrete SD expressions | Authored texture/sprite states or compatible blendshapes | Face-specific generation/editing; audio-driven motion only when appropriate targets exist. |

Two complementary assembly strategies deserve separate tests: **generate parts,
then texture them together**, and **generate a coherent whole, then split it**.
The latter may improve global appearance but make clean anatomy extraction harder.
Neither is a universal replacement for high-value part generation.

Blender/agent finishing is a valid authored stage. The automation question is
whether its intent, parameters, measurements and review loop can be reproduced,
rather than whether a dedicated generator performed every edit. Standard unlit
materials explicitly support stylized appearance in
[glTF](https://github.com/KhronosGroup/glTF/blob/main/extensions/2.0/Khronos/KHR_materials_unlit/README.md).
Unlit shading suppresses lighting response; it cannot erase lighting already
painted into a base-color texture.

## Admission and refresh record

For each future trial, record the following alongside the artifact rather than
turning a catalog claim directly into a production binding:

| Field | Required observation |
|---|---|
| Identity/access | `checked_at`, `provider`, `model_version`, `operation`, `route`, `access_kind`, official source links; reconcile conflicting versions and account gates. |
| Inputs/outputs | Accepted formats, view ordering/framing, optional mask/part selection, topology/texture controls and actual output files. |
| Preservation | Compare positions/indices, UV arrays, node transforms, part/material assignments, skeleton, weights, bind matrices, morph targets and clips separately. Record promised versus observed behavior. |
| Visual result | Matching cameras, poses, lighting/exposure and target display size; identity, seams, texture continuity and motion reviewed independently of structural checks. |
| Reproducibility | Frozen source, exact request/configuration, derivative lineage, agent decisions, bounded review iterations and short verdict. |
| Cost/availability | Current quoted unit plus observed ledger; refresh deprecated routes, feature rollout and licenses before the selected run. No prices were measured here. |
| Status | `documented`, `trial_pass`, `revise`, `reject` or `unverified`; name the asset/domain tested. A pass for a human does not automatically pass an anthro cat. |

Texture-only trials should begin on a static derivative of the assembled asset.
If UV/material correspondence is verified, compatible maps can be applied to
the retained rigged asset. Otherwise rebaking or rerigging is a new explicit
stage; silently substituting the provider's export would lose the preservation
boundary. Any geometric change reopens fit, skin and motion review.

Refresh the affected rows when choosing the next operation or encountering a
new release. Check the developer contract, vendor app documentation, fal schema
and official code release separately. An app demo or paper must not silently
become a callable route. Future contained LLM review/tool orchestration should
use the project's selected OpenRouter route; this survey changes no bindings.

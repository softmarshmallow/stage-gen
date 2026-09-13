# Helix SD 3D independent visual review

- Reviewer identity: Codex independent semantic review agent.
- Reviewer role: `independent_character_semantic_reviewer`, separate from the reference, mesh, assembly, rig and preview producers.
- `independent: true`
- `reviewed_at: 2026-09-14`
- `model_verdict: pass`
- `preview_verdict: pass`
- Scope: the exact curated 3D SD model and static preview below; canonical identity, rest appearance and supplied sampled cat-rig diagnostics at a 120px character-height bar. This is not general or polished-motion certification.

## Accepted artifacts and canonical input

| Repository path | SHA-256 | Bytes |
| --- | --- | ---: |
| `library/characters/helix/sd_3d.glb` | `f35acbec84c6fe2ee6d843a2765852125871003bca99be97b8cb948d5888a340` | 10305600 |
| `library/characters/helix/sd_3d.webp` | `abb389aaca787babdb960f07b3f0d2f01dfa44683aec0e5bd936b930a2266913` | 22156 |
| `library/characters/helix/sd_flat_anthro.webp` | `16b24795aa2eba9c1159fbd482c139b339627ad43fd9baa77926adc46c0f902c` | 116488 |

The static preview is 750 × 750. Verdicts apply only to these bytes. The library GLB is byte-identical to the admitted pipeline `rig_01` candidate; no model repair after pipeline admission is represented by this file.

## Direct inspection and findings

The reviewer inspected Helix's canonical anthropomorphic SD illustration and supporting seated design, the exact final WebP, its source three-quarter PNG and the full-size front rest render. Diagnostic inspection covered seven rows in five views each: rest, shoulder raise, elbow bend, knee bend, paw curl, cheer and tail wag. The source atlas uses 240px character height; all seven rows were also inspected in 120px reductions. The two-view face strip was inspected separately. Diagnostic stills sample the joint/paw motions at 0.75 seconds and cheer/tail wag at 1.5 seconds; this is not continuous playback review.

Helix preserves the oversized round feline head, tall triangular pink ears with white tufts, large amber eyes, white blaze and muzzle, small pink nose, open smile and tongue, warm silver-gray tabby markings, rounded white chest/belly, broad white paws and curved tuft-ended tail. The neutral stance replaces the original wave and tilted head without introducing clothing, human hands or a narrow human waist. Face paint remains clear and correctly positioned. Full head, ears, paws and tail fit comfortably in the exact WebP.

The sampled diagnostics show connected rounded forepaws and feet, visible limb bending, and a head/neck overlap that stays covered. The tail remains attached through the tail-wag and cheer samples. No gross collapse, flying strip, detached paw or exposed part gap was observed at the stated bar. The attachment review establishes visible continuity; it does not assert welded topology. Minor nonblocking interpretation differences include more sculpted rear-head fur, a slightly collar-like tail-root transition, and modestly longer visible limbs than the tucked original pose.

The final WebP retains the source PNG's identity, framing and dimensions. An independent in-memory encoding with WebP quality 90 and method 6 reproduced the exact final WebP bytes. Small background/color quantization does not impair character readability.

## Motion contents and limitations

Direct inspection of the GLB JSON confirms six embedded clips: `shoulder_raise`, `elbow_bend`, `knee_bend`, `paw_curl`, `cheer` and `tail_wag`. Rest is an inspected pose, not a seventh animation clip. The library GLB contains no Samba clip.

A separate local Samba retarget of these same model bytes was previously inspected through distributed stills and an encoded-video sample. It shows minor dark creasing and angular folding under the belly and around the inner thigh during bent-leg poses, notably frames 24, 280, 320 and 380. The artifact is visible at 640px but did not break readability in the reviewed 120px samples. Its precise geometric cause was not established. That limitation remains and is not overridden by this curated model/static-preview acceptance.

This record does not certify every intermediate frame, arbitrary retargeted motions, collision-free surfaces, precise ground contact, seamless looping, facial performance or independent ear/fur simulation. Licensing and publication authorization are recorded separately and are not determined by this visual review.

## Content-addressed review evidence

These portable evidence identifiers bind the inspection to the exact model. All diagnostic source-image hashes, row/face hashes and rest-render artifact hashes were independently checked against the pipeline evidence. The second automatic rig-review node reused the first verdict for unchanged model bytes; it is not presented as an additional fresh visual review.

| Evidence name | SHA-256 | Bytes |
| --- | --- | ---: |
| `pipeline_rig_review_01` | `6b7755dba8dfcbb03fce7f7aceea9730b29430852658170fda9dd0a133f5cda3` | 53198 |
| `pipeline_rig_review_02_reused` | `558dc04c081b85aeb7193028f301c04dff769c0bbc3348621e21975b2f4acd36` | 29531 |
| `pipeline_rig_admission` | `ed211a6afda4c7a57a4d1061a6deb7756c5a8bf3559e85afc94f004570b405eb` | 311 |
| `final_rig_rest_render_manifest` | `cc4dc6b97f9774dd4f3f70ddb904a9f21adf59d5f7e0c9649d89d35e6022f402` | 696 |
| `preview_source_three_quarter_png` | `2a6c611db140916c755574f1dee170b0db5254774a07f16828dec7d9fafb72ca` | 563557 |
| `final_rig_front_png` | `9394d387b690deb07c8425c30e2613250dba32c70ecf269e1a3c59ab848210d1` | 579471 |
| `rest_five_view_row` | `64986737386dbcbbaae1663a886abf1332e56f616a8e639af04b7b136eaa73b3` | 294782 |
| `shoulder_raise_five_view_row` | `a46376f3a89d5ea6dca677f76bb87b097bff8fda2f38c317fe80d04e890db6c9` | 294755 |
| `elbow_bend_five_view_row` | `669ed4fe74a0fcffc6775ae4e5cd5131eef9307eb5e3d247727a9e5d024dae49` | 296498 |
| `knee_bend_five_view_row` | `b34f5757d04c889a94d24a8904cd3a05a58dddd3e1ffce8b55e68ee237cf05ae` | 290097 |
| `paw_curl_five_view_row` | `2686b77f4297069c1c4dc0d354bd3f1ca41df991da4ddff1fb48f153e029a4b6` | 296806 |
| `cheer_five_view_row` | `cfb6d6bb21078b66cb84d3ecb0d4da136f581d8ef7db7c425a0b96d9152e1341` | 293018 |
| `tail_wag_five_view_row` | `2e398a2aef51667e34fd1bb4b6cc6e66688b8003182300d6cc69e22b3745e15b` | 295856 |
| `face_front_and_three_quarter_strip` | `1ec48eb1ace6ee0376c8b65bcd99d3ac03873ea58903b0cff00b36d65b076c78` | 453654 |
| `separate_sampled_samba_review` | `5afcafa7810a4508a72d50c7c71c4d3790a645fe9046e17f4b77f4b8d5f9ab7c` | 2635 |

# Riko SD 3D independent visual review

- Reviewer role: `independent_character_semantic_reviewer`, separate from the model, repair and render producers.
- `independent: true`
- `reviewed_at: 2026-09-13T15:09:16Z`
- `model_verdict: pass`
- `preview_verdict: pass`
- Scope: exact final library model and preview; canonical identity, rest appearance and sampled embedded fixed-humanoid motions. The motion quality bar is 120 pixels of character height; detailed renders also inform the preview verdict.

## Accepted artifacts and canonical input

| Repository path | SHA-256 | Bytes |
| --- | --- | --- |
| `library/characters/riko/sd_3d.glb` | `c3db2031bda77b7128d19d8e5b25c1c001a615390f0d50f1ff1577bd2048aca3` | 4542432 |
| `library/characters/riko/sd_3d.webp` | `67c1ce85a0473f38150429843d0748b89d0e1c3e510019caa74d328df2e3c3b9` | 43728 |
| `library/characters/riko/sd_flat.webp` | `f01c965ff785f0a90a8e19a0f2c1c78820eb54ac50cb4b9f78ba1d264369b3dd` | 208504 |

The preview is 1024 × 1024. These verdicts apply only to these exact bytes. A changed model or preview needs a new binding and review.

## Review and findings

The reviewer directly inspected the canonical flat reference, exact final WebP, its canonical PNG, front/back/left/right studio renders, and all 30 diagnostic views: rest plus shoulder raise, elbow bend, knee bend, wrist bend and cheer, each from front, back, both sides and three-quarter. Three selection-mask views were also inspected. Diagnostic stills sample arm/leg/wrist motions at 0.75 seconds and cheer at 1.5 seconds; they are not a continuous playback review.

Riko remains recognizable: blonde hair with pink ends, the high side ponytail and raspberry bow, paired pink hair clips, rose-colored eyes, open playful smile, raspberry off-shoulder cropped sweater, blue shorts, white/navy high-top sneakers with pink laces, small jewelry and a compact curvy SD silhouette. Face paint is readable and correctly placed in the final preview and diagnostic front/three-quarter views. Tiny jewelry and trim use simplified 3D shapes; this is nonblocking identity variation at the stated bar. Fixed mitten hands replace the illustration's peace sign as intended by this lane.

The repaired long ponytail preserves its hanging silhouette through the arm diagnostics and cheer. It no longer lifts from shorts height and bunches around the raised sleeve as in the rejected upstream rig. Head, hands, feet and hair remain attached in the sampled views. Arms and knees bend visibly without gross joint collapse, flying vertices or detached surfaces. The shorts are stable during arm-only diagnostics. The sweater sleeves fold and lift with the arms; minor folds and close hair/sleeve overlaps are visible in side views but do not split the character silhouette or reproduce the earlier hair failure. No blocking defect is visible at the review bar in the supplied poses.

The exact WebP has complete head, hair and foot framing, clear facial expression, coherent color and material appearance, and no visible encoding defect that changes identity. The canonical PNG and final WebP were both viewed; the declared transform is a same-size WebP encoding.

## Upstream rejection and local repair

The original automatic rig candidate, SHA-256 `9a1edcfd31ee3f71eea3f0557306e43e74c09de36bc71697bd8a8a041f7bf93e`, failed independent pipeline review for arm-driven ponytail deformation. That original rejection is preserved; this report does not claim the automatic pipeline succeeded. The accepted library model is a separately reviewed local derivative.

The local repair assigns the selected high head geometry and pink hanging hair to the Head joint. The reviewer independently compared the original and final GLB bytes: the JSON chunk and file length match, and every one of the 65,292 changed bytes lies inside the declared `JOINTS_0` or `WEIGHTS_0` accessor rows. All bytes outside those rows are identical, preserving geometry, normals, UVs, textures, materials, skeleton and clip data. The final library GLB is byte-identical to the reviewed derivative. The producer's bound numeric report records maximum rest-position drift of about 2.60e-7 scene units; the bound weight report records finite nonnegative normalized weights and nonzero coverage for all 22 required joints. These numeric findings support, but do not replace, the direct visual review.

## Limits

Acceptance covers the fixed-hair, fixed-hand character and the sampled embedded motions. It does not establish every intermediate frame, arbitrary retargeted animation, collision-free cloth/hair simulation, facial or finger animation, a seamless loop, Samba readiness, or end-to-end automatic pipeline reliability. Static hair may overlap nearby clothing at angles not fully established by these samples.

## Content-addressed review evidence

The names below identify the exact inspected images and supporting records. They are portable evidence identifiers, not machine-specific paths. Source manifests bind the renders to the accepted model digest above. All listed hashes and sizes were computed independently during review; studio artifact hashes also match their producer manifest.

| Evidence name | SHA-256 | Bytes |
| --- | --- | --- |
| `upstream_rejected_rig_review` | `3b12051caace06a0f65912881e7e5729b69aa7c3b52f7126a1fa79089b45904f` | 47637 |
| `local_weight_repair` | `65cf142d2813233359fe0ddece62e5c727764ea4e8d8298b418aa05be6d1ef59` | 1937 |
| `weight_integrity` | `81a1911644eb1bb00f490fa932c71d1ce0820d86711c75d1d3e957594608670a` | 1212 |
| `diagnostic_manifest` | `454172f8464d2305167c08d3cbc248804617ba3bdd9025bb0c7c53f7123c21d7` | 145417 |
| `studio_manifest` | `95fa4b6128d57e03582db28563a06080ead869a0dfc443b8e58366cf3d81e05d` | 5995 |
| `publication_transform` | `e4797125b353ae17e529150f297a64d79b24964c96446965f2cd20a29d8d6be1` | 398 |
| `studio_canonical` | `e72e751dca1f1ee6a518fcfd26996a2238abd51d55302cfd28dc660a95ab209d` | 1078452 |
| `studio_front` | `f6cce794a13e22fc22118f078aa4655ba555d5413a0277673cb2f2b9d38d0600` | 1104010 |
| `studio_back` | `a8d9e11697abd6f8ffc3b71f6144acaace1fcaeef0c06354ca41a3eb8b2f0281` | 1061513 |
| `studio_left` | `bad9352034314663b31fa8462a2cf7a831ff63768a3ac5773e5aa83adb657c6a` | 1013914 |
| `studio_right` | `8adeb27c03055451e3c3efa3359a64d3943ccc28deb5affe23850e06d1bede33` | 1030618 |
| `rest_positive_z` | `f170ee185867acac58ed04b57ced5e98d7f49497970cfa3a633e847fc61ff77b` | 297995 |
| `rest_negative_z` | `133c1967a93384d3990d0dc87ff35460608823201a9f9c5a09d310136495103c` | 285204 |
| `rest_negative_x` | `8e4fca0ae6a129c0889ef4c67ca069c17df8e270f3fed5bfe45cdb93619b00f6` | 266333 |
| `rest_positive_x` | `26b8ce67c5bd396dd2ecbe040fd2f9aa4d97d529091e48eaff05714f8396105c` | 272607 |
| `rest_three_quarter` | `d8ead7c581c200a78560e69e0f28d2a164b105bca1fa4b4bc1c4ca05b4fc187b` | 299480 |
| `shoulder_raise_positive_z` | `b2b1f30a79c4ce3e44a09d6400eb91101e8d5dae957cf5dc6a66aaddcadbc9d0` | 296446 |
| `shoulder_raise_negative_z` | `491bfdcf1ab07d8f6a74cce87c508f659bc9537baee0e19f191f14ef8d90ff7b` | 284943 |
| `shoulder_raise_negative_x` | `00981704531cea71e618421fe96566c016c4cf9c7e49290a22b43763c5395921` | 266288 |
| `shoulder_raise_positive_x` | `659a310cad39dab04c845bd5ad63051fe439c39573bad807526016be05f03003` | 272077 |
| `shoulder_raise_three_quarter` | `d88e17ba2817deaef471c33f9ded1b77b7ff2f38b0091f0d50ed76623da9cd67` | 300280 |
| `elbow_bend_positive_z` | `7f0445c04a3ce00cbc1374207e16a0ee82902c5b4c10aa814ac62cf31dc0f24f` | 298275 |
| `elbow_bend_negative_z` | `cdc25dec30178214ecf9daa2bff5cddf4d694cf16bffafd14d5e9af421d30459` | 284855 |
| `elbow_bend_negative_x` | `9ece8d889ad087d5ab8c1c54964b358d6b676d1e0dd154633ef238c9bd6662df` | 267239 |
| `elbow_bend_positive_x` | `e599bb6ee271eb08b59eaa08a0ed70415dea131597612f8b9d9568d38a1c86f4` | 272699 |
| `elbow_bend_three_quarter` | `8fcce9c2adc1577ae4ace332c049dc26fa6e6e435392e88df1d347ba5b40bfae` | 300956 |
| `knee_bend_positive_z` | `967c1d27d9d6addba890a4ba21d13f11f94845ba0121ea1680a25067e8cf6ef5` | 300779 |
| `knee_bend_negative_z` | `03e5dbaa58cb5ce8aed7524df39cd09966e8a9998a249bd54ba58cc0d4232b5e` | 284811 |
| `knee_bend_negative_x` | `0b5deadaf86572230ebb7360a8ad4f96380867601046d6b4068edcabca875681` | 269528 |
| `knee_bend_positive_x` | `c8b33ea3bfc8a843fde26358cd61f684b62cf9cc0134777f1e585fd6f05c9d9e` | 277145 |
| `knee_bend_three_quarter` | `76f333c4e98aeb29ad39f1973f2e9323316dcb6d4869991278720066e9c2c9fa` | 304910 |
| `wrist_bend_positive_z` | `701a40a9c37c3b8191d7aaa30bd505de8024022c2831b1ddccafba17669f0f39` | 298340 |
| `wrist_bend_negative_z` | `7549f978e4733c03da59816742b42c1b15829746c9c8238c86ed7b816acc68d5` | 285366 |
| `wrist_bend_negative_x` | `49f8e6bdbfc55ed233a956e0e0472140c33eabe18b69687d81a0554be449ea25` | 266472 |
| `wrist_bend_positive_x` | `d97b6398bc6b0639018c0da94cda24a1f1eb0116db617ec35001c4395054131b` | 272594 |
| `wrist_bend_three_quarter` | `4f94b0688fc7f9b58be349ded98ee78bc3a1b71a03821d9d15788e4fdc0c7b12` | 299368 |
| `cheer_positive_z` | `3dbcb0e701d45a858d7729e91cc0c7ac7bdaa6308020d701d95743fee9aeba71` | 296571 |
| `cheer_negative_z` | `5d7a35301a00c59fcabb802af00ff6d9e6d2b93c2a683a2284359d50afc91faa` | 284668 |
| `cheer_negative_x` | `f64ca390ef2f8a1c140b7935affab4732f359358505381f95562e430c77e904c` | 265514 |
| `cheer_positive_x` | `e3d2fbe9fd1275da74eb108e7bae50c811d82a4fabf602d601662cea7abb5c1e` | 271889 |
| `cheer_three_quarter` | `b1f7d51e4021fa9673dcb803e497812779d1e09c2cf4c0840e8a6952526bb5dd` | 299827 |
| `head_mask_positive_z` | `e97342560ebf3fff9ee1b0b23d38ca51ca270d8fc7b5000809f42074d0a8a2da` | 266560 |
| `head_mask_negative_z` | `e2c46b41fdedb631cdb77eb5b5640476f618464fe7984361ffd64f0ced5e3b05` | 259277 |
| `head_mask_positive_x` | `9812955d0f039c81675a7b390b591d1a2306fc18a7aba37b5889faf08febb144` | 254184 |

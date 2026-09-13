# Nami SD 3D independent visual review

- Reviewer role: `independent_character_semantic_reviewer`, separate from the model, repair and render producers.
- `independent: true`
- `reviewed_at: 2026-09-13T15:14:27Z`
- `model_verdict: pass`
- `preview_verdict: pass`
- Scope: exact final library model and preview; canonical identity, rest appearance and sampled embedded fixed-humanoid motions. The motion quality bar is 120 pixels of character height; detailed renders also inform the preview verdict.

## Accepted artifacts and canonical input

| Repository path | SHA-256 | Bytes |
| --- | --- | --- |
| `library/characters/nami/sd_3d.glb` | `4fed29a340920d8f01d0976dc8521a3a816d0576722dc3dcc23f50b1d5e81b13` | 4601428 |
| `library/characters/nami/sd_3d.webp` | `fe030a366858906da23209f0b9cc3986878a8db54309cebd733ede4ad21b1271` | 41322 |
| `library/characters/nami/sd_flat.webp` | `5aa418f700f9c99bde0e336915ba99a5e8f4b7e6446d6d34265b70164ac0fd67` | 970236 |

The preview is 1024 × 1024. These verdicts apply only to these exact bytes. Earlier derivative and preview hashes are not accepted by this record.

## Review and findings

The reviewer directly inspected the canonical flat reference, exact final WebP, its canonical PNG, and all four orthographic studio views. Final motion inspection covered six five-view rows (30 view samples): rest, shoulder raise, elbow bend, knee bend, wrist bend and cheer, each from front, back, both sides and three-quarter. The four front/back/three-quarter images exposing the earlier strap defect were additionally inspected at full size, as were two actual face closeups. Motion stills sample the joint diagnostics at 0.75 seconds and cheer at 1.5 seconds; they are not a continuous playback review.

Nami retains the defining charcoal rabbit hood with long pink-lined ears, pale blonde-to-pink hair, magenta eyes, flower/ribbon accents, welcoming open smile, broad pink cuffs, neck bow, pleated charcoal skirt with pink hem, banded dark stockings, heavy boots with pink laces, and small crossbody bag. Her compact SD silhouette and clear face remain coherent from front and three-quarter views. Face paint is correctly placed and readable without smearing or duplication. Fine accessories and the bag are simplified 3D interpretations; this does not impair identity at the stated bar. Fixed mitten hands replace the illustration's open wave as intended by this lane.

The final hair and hood ears retain their head-relative shape through the arm diagnostics and cheer. Hanging pink locks no longer swing horizontally with the arms. The skirt stays around the hips without the earlier one-sided pink point under arm-only motion. The final strap revision also removes the thin black strip that previously projected sideways from the bag-side waist: the inspected shoulder/cheer views now show the strap and bag staying against the torso. Upper strap attachment remains coherent. Hands and boots stay connected, elbow and knee bends remain readable, and no gross joint collapse or flying geometry is visible in the supplied poses. Minor sleeve folding and close static hair/clothing overlaps are nonblocking at the review bar.

The exact final WebP preserves the complete hood, hair, skirt and boots with comfortable frame margins, consistent charcoal/pink color blocks and a readable expression. The canonical PNG and final WebP were both inspected; the declared transform is a same-size WebP encoding and shows no visible identity-changing encoding defect.

## Upstream rejection and local repair

The original automatic rig candidate, SHA-256 `8efbef43c6caa1379c2f0f60c21a6c1255ed1e557d0c8860d09e03eaf65177cf`, failed independent pipeline review for arm-driven hanging hair and an asymmetric skirt spike. That original rejection remains unchanged. This report accepts a separately reviewed local derivative and does not claim the automatic pipeline succeeded.

An earlier local derivative, SHA-256 `8210dd152635d187518b5abd48a4f82041485c1146c27c9a491074287545707f`, corrected the major hair/skirt defects but was rejected by this reviewer for the remaining arm-driven bag strap. The final derivative includes a targeted revision of that strap's 312 vertices. The bound audit reports no remaining arm influence on those vertices and zero strap displacement through 17 samples of each arm-only diagnostic; movement during cheer follows torso motion. These numeric results support the visible correction rather than replacing visual assessment.

The reviewer independently compared the original and final GLB bytes: file length and JSON chunk match, and every one of the 143,589 changed bytes lies inside the declared `JOINTS_0` or `WEIGHTS_0` accessor rows. All bytes outside those rows are identical, preserving geometry, normals, UVs, textures, materials, skeleton and original clip data. The final library GLB is byte-identical to the reviewed local derivative. The bound repair report records maximum rest-skin displacement of about 2.28e-7 scene units.

## Limits

Acceptance covers the fixed-hair, fixed-ear, fixed-hand character and supplied sampled motions. It does not establish every intermediate frame, arbitrary retargeted animation, collision-free hair/cloth simulation, facial or finger animation, a seamless loop, Samba readiness, or end-to-end automatic pipeline reliability. Static long hair can overlap nearby arms or clothing at untested poses.

## Content-addressed review evidence

These are portable evidence identifiers, not machine-specific paths. The diagnostic manifest binds all 30 underlying pose images and two face images to the accepted model digest; the row atlas supplies the five-view visual comparisons. Listed hashes and sizes were computed independently, and every diagnostic/studio artifact hash was checked against its producer manifest.

| Evidence name | SHA-256 | Bytes |
| --- | --- | --- |
| `upstream_rejected_rig_review` | `5275eebe82abef45f2802b597d62de52b04c87fbcc9004b5745ca830a4985b40` | 48182 |
| `local_weight_repair` | `3dbdb25fe21a9c855c8573598161ad2b5113541b19f96f8885b93be080b1d541` | 8326 |
| `strap_revision_audit` | `d92484ed31d724de1d8aa2f457ff86218948c73f6efd2f2b8f5930d420f730b5` | 1726 |
| `diagnostic_manifest` | `71ee91d92e9090f461fc56d1d734056a3cdefdf0542c1acc5c79b40982b4cf38` | 7108 |
| `diagnostic_atlas_manifest` | `a806db6be6c9b62ab3415bea4ce95aedd83d8be37fe6fbe6fd41bb37466dd6f8` | 1225 |
| `studio_manifest` | `0272eba412b25dd57a74cb2045f44ebc77800e192bad10dac9516963481d6805` | 5996 |
| `publication_transform` | `f660fb68acf43d9c5f34f49b090e26c123fd0a792bb9815ce81ed9873dc55c31` | 398 |
| `studio_canonical` | `45d5c951bd9c9bea987bd47c53e9e9b035e4d2978bfac01fb997ff8e8021e544` | 1057519 |
| `studio_front` | `c09590f62ce752875557ce6744aa452c27aa3451d706fb7eb4d290e6ada9539f` | 1117846 |
| `studio_back` | `1b680bca4afa59ca702de23a861af899f9718a38f59849b7333651006b3b8519` | 1009070 |
| `studio_left` | `d39d371906845872217a6e51331ae23907b5cfd10c004492da1897f9fc64a597` | 998943 |
| `studio_right` | `ab1b724eb084f01883a1450027df20eae7cbad0485d622a87e0e5d4929907864` | 996919 |
| `rest_five_view_row` | `51fcb8fe5677c11ebac8b41aa686beba43d32c2d2589c727ff4608e5d7a4c3c3` | 344546 |
| `shoulder_raise_five_view_row` | `45837410c6cc8a84e5a4629b2c338d17e82317f63a013fd1d66246c79b9d27a4` | 340532 |
| `elbow_bend_five_view_row` | `9faeae39c56ec65837097182b9ac2ab9372d93e8b50640b3e6e7a62ddfeedd9d` | 344545 |
| `knee_bend_five_view_row` | `07246d4fc9b0a33bc44ac48311f0673966e61f4afa5a19416dafb47c8e812746` | 345919 |
| `wrist_bend_five_view_row` | `4034e29cea13f0f5d43e741e2c8dc8711ea3d01b988c44075599e1229884c6f1` | 344991 |
| `cheer_five_view_row` | `cfe6ef471fa7676fbadcf14e9391da2a3987ddb1622e511a60218b6ca5d6efc5` | 338811 |
| `shoulder_raise_positive_z` | `fbcfa03ed529cacce54faaeef5d2559b2aa40bdac5c2c43d717e0c43260583ef` | 449088 |
| `shoulder_raise_three_quarter` | `9ae4b178442c486918b2d451cd5902f808b71f1bc3c17abb2f7762f313be4104` | 428424 |
| `cheer_negative_z` | `24d0a0600c035ceb56db8b9313c9f1488c29743250acf1ccce27cac3d8c523af` | 396426 |
| `cheer_three_quarter` | `92adc92e85705c3351daec721645354f3956cc91ce6aa17747f65c74651f2633` | 428877 |
| `face_positive_z` | `f6a9a7c780d0a5af717425a1d746728bf01f7ec611beded37b09842bd1951f0e` | 730937 |
| `face_three_quarter` | `dcf83bb4ba8ccc6f95567d258b6d916c744750e3dc2cbfe5ab198c3d763ffd60` | 703014 |
| `rejected_previous_derivative_shoulder_front` | `c8afcdabd8d585b40ffc0a934f5db2bcd9716d3dc4d71e9c56dc7ef41400f0c4` | 449771 |

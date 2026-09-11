# Game Presentation SDK — complete request triage

> **Design evidence, 2026-09-11; no runtime promotion performed.**
> Companion to the [SDK design](game-presentation-sdk-design.md).

All **106 archived prompts** were reviewed in conversation order against the
request ledger, current inventory and relevant implementation contracts. Each
row below is a triage outcome, not a replacement for the user's exact words in
the linked archive. Earlier budgets, approvals, deferrals and experimental
directions remain historical; they are not new instructions or spending grants.

The design's F01–F36 census groups behavior independently of prompt count.
One request may touch multiple mechanisms, and many requests introduce no new
mechanism. **M** = SDK mechanism candidate; **P** = preset/bounded pattern;
**H** = host/template/example; **A** = assets/preparation; **D** = decision,
review or process; **Q** = explicitly deferred/proposed work. A combined tag
means responsibilities must remain separate, not that the entire row becomes
one module.

## P01–P40: presentation foundations and the tactical example

| Prompt | Disposition and current interpretation |
| --- | --- |
| [P01](../../presentation-playground/USER_PROMPTS.md#p01) | **D** Status/context. No capability or requirement to preserve the legacy standalone point-and-click game. |
| [P02](../../presentation-playground/USER_PROMPTS.md#p02) | **M/P/D** Fine-grained presentation taxonomy; matte departure becomes F05 in P22. The roughly twenty techniques were not supplied as a complete list; do not invent unnamed requirements. |
| [P03](../../presentation-playground/USER_PROMPTS.md#p03) | **D** Gameplay/runtime first with manually prepared assets. Keep provider and generation code outside the SDK. |
| [P04](../../presentation-playground/USER_PROMPTS.md#p04) | **M/H/A** F27 Point Contact; reach pose, sprite blink/expression, feedback and cast art are example content. Original discard-the-spike intent is superseded by direct succession in P102–P106. |
| [P05](../../presentation-playground/USER_PROMPTS.md#p05) | **A** Initial clean-anime direction; P08 replaces it. No mandatory SDK visual style. |
| [P06](../../presentation-playground/USER_PROMPTS.md#p06) | **D** Original ignored-spike location, superseded by P40's tracked standalone location. |
| [P07](../../presentation-playground/USER_PROMPTS.md#p07) | **H/A** Second actor and multi-actor dialogue example. Cast appearance, age and count do not become SDK requirements. |
| [P08](../../presentation-playground/USER_PROMPTS.md#p08) | **A** Replace character art from supplied style references and adjust registration/targets. Preserve historical art records; no runtime generation feature. |
| [P09](../../presentation-playground/USER_PROMPTS.md#p09) | **M/P/H/A** F07 Manpu cues and animation; rasters, selected reactions and gallery remain art/host responsibilities. |
| [P10](../../presentation-playground/USER_PROMPTS.md#p10) | **A** Raster/image-model direction for Manpu artwork. Does not prohibit procedural shaders or the later code-authored UI. |
| [P11](../../presentation-playground/USER_PROMPTS.md#p11) | **D** Reproducible launch command and handoff convention. Carry into template documentation. |
| [P12](../../presentation-playground/USER_PROMPTS.md#p12) | **H/P/A** Background selection and location announcement, F28. Random selection was provisional; P24/P67/P77 establish authored places and story-first art. |
| [P13](../../presentation-playground/USER_PROMPTS.md#p13) | **D** Continue P12; no additional capability. |
| [P14](../../presentation-playground/USER_PROMPTS.md#p14) | **D** Exact request history and short outcomes for later taxonomy review. Explicitly distinguishes features from modules. |
| [P15](../../presentation-playground/USER_PROMPTS.md#p15) | **H/A** Third actor for transition demonstrations. Does not set a universal cast size. |
| [P16](../../presentation-playground/USER_PROMPTS.md#p16) | **M/P/H** F16 Holographic Projection. Matching voice is separate F26 composed by the host; its earlier audio deferral is resolved by P73/P99. |
| [P17](../../presentation-playground/USER_PROMPTS.md#p17) | **H** Fixed logical layout, proportional world-attached Manpu. P37 refines native window rendering. |
| [P18](../../presentation-playground/USER_PROMPTS.md#p18) | **H** Playable main story and separate studies. P67 extracts Presentation Lab; P71 changes Afterlight's controls. No shared mandatory game UI. |
| [P19](../../presentation-playground/USER_PROMPTS.md#p19) | **H/Q** Larger/lower standing composition implemented. Standing framing parameters remain explicitly deferred, reaffirmed by P99. |
| [P20](../../presentation-playground/USER_PROMPTS.md#p20) | **M/P** F04 Actor Focus over F01 animation; bounce, pulse, listener dim/fade and none are presets. |
| [P21](../../presentation-playground/USER_PROMPTS.md#p21) | **M/P** Reuse F01 animation for F07 Manpu introductions with independent clocks. No common actor/mark clock is required. |
| [P22](../../presentation-playground/USER_PROMPTS.md#p22) | **M/P** F05 Character Exit with Silhouette Fade/Opacity Fade. Brightness then opacity achieves the matte behavior while preserving alpha. |
| [P23](../../presentation-playground/USER_PROMPTS.md#p23) | **P/M/H** F06 sequential handoff and F02 curve controls. Existing pattern is two slots/three actors; the live curve graph belongs to Lab tooling. |
| [P24](../../presentation-playground/USER_PROMPTS.md#p24) | **P/M/H/A** F10 Establishing Shot, F20 flare, tactical story and art, fingertip pairing. Camera mechanism does not own titles, location meaning or cast visibility policy. |
| [P25](../../presentation-playground/USER_PROMPTS.md#p25) | **H/P** Author existing exit/handoff in the main story, including progress gates and continuation. No new mechanism. |
| [P26](../../presentation-playground/USER_PROMPTS.md#p26) | **M/H** F09 Dialogue Camera with coverage constraints. Target selection and multi-line hold remain directed, not automatic speaker rules. |
| [P27](../../presentation-playground/USER_PROMPTS.md#p27) | **H** Tactical UI in code. P45 confirms whole-host ownership; future image-based UI automation remains optional tooling. |
| [P28](../../presentation-playground/USER_PROMPTS.md#p28) | **D** Promotion/taxonomy review. Preserve useful classifications; later P102–P106 supersede old destination and integration prerequisites. |
| [P29](../../presentation-playground/USER_PROMPTS.md#p29) | **D** Readiness and incumbent coupling concerns. Latest direction chooses a supported code-first successor, without requiring old Scenario or room parity. |
| [P30](../../presentation-playground/USER_PROMPTS.md#p30) | **H/A/D** F29 replaceable video-opening feasibility. Named generation models belong to historical production context. |
| [P31](../../presentation-playground/USER_PROMPTS.md#p31) | **H** Minimal placeholder title route. P36 supersedes completion/continuation behavior with looping and explicit click. |
| [P32](../../presentation-playground/USER_PROMPTS.md#p32) | **A** Opening-video production and variants under a historical budget. No SDK generation dependency. |
| [P33](../../presentation-playground/USER_PROMPTS.md#p33) | **D** Report arriving video paths for parallel review. No runtime feature. |
| [P34](../../presentation-playground/USER_PROMPTS.md#p34) | **D** Status/ETA request. No capability. |
| [P35](../../presentation-playground/USER_PROMPTS.md#p35) | **A/H** Select and bind opening A; P36 subsequently revises playback policy. |
| [P36](../../presentation-playground/USER_PROMPTS.md#p36) | **P/H** F29 loop with fade-through-black and explicit-click continuation. Playback treatment and story navigation remain distinct. |
| [P37](../../presentation-playground/USER_PROMPTS.md#p37) | **H** F32 native-resolution Canvas Items rendering with fixed logical layout. Supersedes the earlier low-resolution viewport scaling. |
| [P38](../../presentation-playground/USER_PROMPTS.md#p38) | **D** Earlier sibling/replacement ordering discussion, revised by P39 and now P102–P106. Mentioned future ideas do not create an unseen backlog. |
| [P39](../../presentation-playground/USER_PROMPTS.md#p39) | **D** Historical choice to continue exploration before migration. Does not freeze the present SDK design. |
| [P40](../../presentation-playground/USER_PROMPTS.md#p40) | **D** Move intact into tracked standalone project. Git location did not itself make it canonical or publish media. |

## P41–P75: independent roots, Afterlight and composable effects

| Prompt | Disposition and current interpretation |
| --- | --- |
| [P41](../../presentation-playground/USER_PROMPTS.md#p41) | **D/H/M** Shared components with separate code-authored roots. Five hints later land at P47, P63, P95/P96 and P99. Dating framing is corrected by P68. |
| [P42](../../presentation-playground/USER_PROMPTS.md#p42) | **D** Maintainability and quick composition. One discoverable master root, not a literal one-file limit. Mandatory shared-view extraction proposals were superseded by P43/P45. |
| [P43](../../presentation-playground/USER_PROMPTS.md#p43) | **D** Explicit dependencies, state and lifecycle; flexibility over compactness. Adequate integration is legitimate host code. |
| [P44](../../presentation-playground/USER_PROMPTS.md#p44) | **D/H** Answer-first UI customization review. P45 supersedes a shared-view/skin direction. No outstanding mandatory UI framework. |
| [P45](../../presentation-playground/USER_PROMPTS.md#p45) | **H** Binding ownership rule: complete UI hierarchy, layout, style, controls and wiring belong to each host. Optional independent utilities are allowed. |
| [P46](../../presentation-playground/USER_PROMPTS.md#p46) | **D/H** Group five ideas and propose the first Afterlight pass; implementation starts at P47. Asset duplicates were temporary. Original TTS/particle deferrals later resolve. |
| [P47](../../presentation-playground/USER_PROMPTS.md#p47) | **M/H/A** F11 Walking Approach. Initial story/UI/placeholders are host material, replaced by later art and P67's story. P99 resolves the historical general-particle deferral. |
| [P48](../../presentation-playground/USER_PROMPTS.md#p48) | **D** Share runnable command while work continues. Collaboration/setup convention. |
| [P49](../../presentation-playground/USER_PROMPTS.md#p49) | **M/P/D** F14 eye-transition timing/mask plus terminology. Opening/closing/blink are modes, distinct from an actor's sprite blinking. |
| [P50](../../presentation-playground/USER_PROMPTS.md#p50) | **P** F14 Edge Feathering softens mask coverage. Defocus and organic mask art remain optional ideas, not implemented or required. |
| [P51](../../presentation-playground/USER_PROMPTS.md#p51) | **A/H** Cast references, proportions, art generation and review setup. Final assets superseded by P61; guest selection superseded by P67. |
| [P52](../../presentation-playground/USER_PROMPTS.md#p52) | **A/H** Indoor locations are game art direction, not an SDK module. |
| [P53](../../presentation-playground/USER_PROMPTS.md#p53) | **A** Historical reference-distinctness redesign, rejected by P54 and not activated. |
| [P54](../../presentation-playground/USER_PROMPTS.md#p54) | **D/A** Pause/reject that art candidate. Later iterations/P61 resolve it; no current work stop. |
| [P55](../../presentation-playground/USER_PROMPTS.md#p55) | **A** Canonical-style-reference prompting experiment. Offline preparation method, not runtime style logic. |
| [P56](../../presentation-playground/USER_PROMPTS.md#p56) | **D/A** User review before replacing Afterlight art. Applies to asset activation, not an approval gate for ordinary SDK code work. |
| [P57](../../presentation-playground/USER_PROMPTS.md#p57) | **A** Detailed description/style-reference iteration. No runtime feature or automatic originality guarantee. |
| [P58](../../presentation-playground/USER_PROMPTS.md#p58) | **A** Candidate vibrancy tuning; followed by regeneration and selection. |
| [P59](../../presentation-playground/USER_PROMPTS.md#p59) | **A** Cast preparation with selected model/effort. Runtime consumes supplied textures independently of that choice. |
| [P60](../../presentation-playground/USER_PROMPTS.md#p60) | **D** Historical additional budget. Not continuing authorization for new spend. |
| [P61](../../presentation-playground/USER_PROMPTS.md#p61) | **D/A/H** Approved cast installation and matching host landmarks. Preserve selected assets separately from SDK code. |
| [P62](../../presentation-playground/USER_PROMPTS.md#p62) | **D** Historical five-item audit. Subsequent P63, P95/P96 and P99 resolve concrete missing features. |
| [P63](../../presentation-playground/USER_PROMPTS.md#p63) | **M/P/H/A** F24 reveal/Intertitle, F12 Drift and F17 Halo. Monologue layout, portrait crop and combined mood are authored. Replaces the literal silhouette interpretation; dedicated art installed at P66. |
| [P64](../../presentation-playground/USER_PROMPTS.md#p64) | **M/H/A** F23 Text Set. Localized strings, fonts, controls and switching continuity remain host-owned; no full localization framework. |
| [P65](../../presentation-playground/USER_PROMPTS.md#p65) | **D** Historical spend clarification. Did not replace the later visual-selection approval. |
| [P66](../../presentation-playground/USER_PROMPTS.md#p66) | **D/A/H** Approve dedicated Nami portrait. Asset binding, not a required Drift/Halo asset. |
| [P67](../../presentation-playground/USER_PROMPTS.md#p67) | **H/D** Linear ensemble story and separate Presentation Lab. Supersedes guest-selection flow; studies and story keep independent state/UI. |
| [P68](../../presentation-playground/USER_PROMPTS.md#p68) | **H/D** Bishōjo adventure rather than dating simulation. No affinity/romance framework follows from the example's audience. |
| [P69](../../presentation-playground/USER_PROMPTS.md#p69) | **P/H** Walk-Away under F05 Exit; Restless Bounce under F04 Focus/F01 Motion. No new walking-physics module. |
| [P70](../../presentation-playground/USER_PROMPTS.md#p70) | **M/P/A** F07 independent ephemeral Manpu instances and Sigh Puff art/preset. 3D billboard sampling preview is not a complete 3D effects backend. |
| [P71](../../presentation-playground/USER_PROMPTS.md#p71) | **H** Gradient chrome, ready dot, screen advance and reconverging choice. Entire UI and choice routing remain game-owned. |
| [P72](../../presentation-playground/USER_PROMPTS.md#p72) | **H/P** Schedule sigh after reveal so it is noticeable. Host scheduling, not a new shared scheduler. |
| [P73](../../presentation-playground/USER_PROMPTS.md#p73) | **M/H** F25 typing/supplied voice/silence with pause and interruption. Host chooses stream and reveal policy; P95/P96 adds recordings. |
| [P74](../../presentation-playground/USER_PROMPTS.md#p74) | **M/P/H** F18 barrier/heat, F19 bounded corruption and F13 Impact Shake. The encounter is host direction; shader flecks did not replace the later sustained particle request. |
| [P75](../../presentation-playground/USER_PROMPTS.md#p75) | **H/A** Move the encounter later and add Keeper art. No villain/isekai SDK abstraction. |

## P76–P100: stronger composition, particles, voice and geometry

| Prompt | Disposition and current interpretation |
| --- | --- |
| [P76](../../presentation-playground/USER_PROMPTS.md#p76) | **A** Pretty villain/evil-smile direction. Game artwork, not a core actor semantic. |
| [P77](../../presentation-playground/USER_PROMPTS.md#p77) | **H/A** Story drives art; dedicated villain location. Retain authored scene/background binding, not image-driven story inference. |
| [P78](../../presentation-playground/USER_PROMPTS.md#p78) | **A** Darker infernal background revision. No new effect mechanism. |
| [P79](../../presentation-playground/USER_PROMPTS.md#p79) | **D** Full documentation/backlog audit. Maintain traceability and distinguish historical from current status. |
| [P80](../../presentation-playground/USER_PROMPTS.md#p80) | **D/M/P** Particle Effects grouping; P99 subsequently implements sustained emission. Smoke/embers/sparks are interchangeable art/presets, distinct from shader flecks. |
| [P81](../../presentation-playground/USER_PROMPTS.md#p81) | **H/A** Dedicated Eira solo transmission and cleanup; P82 refines its presentation. No reusable remote-character scene requirement. |
| [P82](../../presentation-playground/USER_PROMPTS.md#p82) | **H/A/P** Floating framed portrait, laboratory and contained hologram. A world display is concrete scene composition, not shared game UI or a new effects engine. |
| [P83](../../presentation-playground/USER_PROMPTS.md#p83) | **P** Stronger F16 hologram defaults, retaining adjustable strength and zero bypass. Intensity variants are not modules. |
| [P84](../../presentation-playground/USER_PROMPTS.md#p84) | **P** Waking Eye-Opening adds a peek/close/hold/open mode within F14. No additional transition controller. |
| [P85](../../presentation-playground/USER_PROMPTS.md#p85) | **H/P** Stronger encounter tuning across existing fields and shake. No separate “7/10” capability. |
| [P86](../../presentation-playground/USER_PROMPTS.md#p86) | **M/H** Explicit pattern/world transform for corruption's procedural flecks; source geometry follows camera. General particle shapes/emission later addressed by P99. |
| [P87](../../presentation-playground/USER_PROMPTS.md#p87) | **H/P** Reuse waking transition for realm arrival/return. New scene placement of F14, not a new system. |
| [P88](../../presentation-playground/USER_PROMPTS.md#p88) | **M/P/H** F21 Radial Sprite Burst: content-neutral finite outward motion, interchangeable art, host origin/layer. Distinct from sustained emission. |
| [P89](../../presentation-playground/USER_PROMPTS.md#p89) | **M/H** F15 Background Blackout below fixed actors. Stunned interpretation and solo use are authored. |
| [P90](../../presentation-playground/USER_PROMPTS.md#p90) | **P/H** Quick Approach uses F02 movement sampling. Host captures target/gap, moves one actor and holds. No pathfinding or general blocking graph. |
| [P91](../../presentation-playground/USER_PROMPTS.md#p91) | **M/H/P** F03 Layer Pan; Cast Pan selects actor-group membership over fixed scenery. Does not move the camera or change local actor spacing. |
| [P92](../../presentation-playground/USER_PROMPTS.md#p92) | **M/P** F07 loops via held scalar steps, supplied sprite frames or pure external sampling. Existing lifecycle stays single-owner; no serialized graph requirement. |
| [P93](../../presentation-playground/USER_PROMPTS.md#p93) | **P** Sweat Drop Fall reuses F07 one-shot animation and supplied sweat art. No new controller. |
| [P94](../../presentation-playground/USER_PROMPTS.md#p94) | **M/H/A** Reuse F27 Point Contact for Nami's new pose. Art, readiness, feedback and gate remain host-owned; approved generation was a completed separate pass. |
| [P95](../../presentation-playground/USER_PROMPTS.md#p95) | **M/H/A** F25 playback plus F33 explicit voice policy/bindings and F36 preparation. Preserve localized text, speaker/line overrides, intentional silence and alternate replies. Existing recordings do not imply listening approval. |
| [P96](../../presentation-playground/USER_PROMPTS.md#p96) | **H/A/D** One-time manual preparation, source revisions and ready/none/pending/missing/failed/stale status. Runtime/status/replay never generate. Do not promote the concrete Afterlight resolver as a provider-aware SDK core. |
| [P97](../../presentation-playground/USER_PROMPTS.md#p97) | **H** F30 autoplay toggle/defaults/gates and readiness timing. No implicit contact or automatic restart; audio completion alone does not advance. |
| [P98](../../presentation-playground/USER_PROMPTS.md#p98) | **D** Remaining-request audit before P99. No new mechanism. |
| [P99](../../presentation-playground/USER_PROMPTS.md#p99) | **M/P/H/Q** F22 sustained Sprite Particle Emitter and F26 Transmission Voice processing. Host atmosphere/call policy remains separate; standing framing stays deferred. |
| [P100](../../presentation-playground/USER_PROMPTS.md#p100) | **Q/D** Anatomy/visual-geometry research only. Sparse COCO-based proposal, VLM-only future evaluation, no annotation/implementation/rig. Keep distinct from runtime manual attachment inputs and calibration authority. |

## P101–P106: the current SDK mandate

| Prompt | Disposition and current interpretation |
| --- | --- |
| [P101](../../presentation-playground/USER_PROMPTS.md#p101) | **D/Q** Assess asset independence. Geometry is a major placement gap; metadata must satisfy the selected feature, not merely parse. Later SDK scope permits explicit manual bindings initially. |
| [P102](../../presentation-playground/USER_PROMPTS.md#p102) | **D** Direct successor, fidelity baseline, Ren'Py comparison and text/code tradeoff. Ren'Py feasibility was documentation research, not a port or migration selection. |
| [P103](../../presentation-playground/USER_PROMPTS.md#p103) | **D** SDK is primary supported code; Scenario authoring/execution is secondary, experimental and allowed to lag/break/be bypassed. Replaces the earlier roughly equal-authoring-path framing. |
| [P104](../../presentation-playground/USER_PROMPTS.md#p104) | **D/H** Exclude legacy standalone point-and-click compatibility from promotion; retain small code-authored interactions. General point-and-click Scenario logic is outside scope. No deletion performed in this design pass. |
| [P105](../../presentation-playground/USER_PROMPTS.md#p105) | **D** Pragmatic game system + template + example: package existing behavior, externalize content bindings, account for UIDs and reproducible setup. No broad architecture rewrite or mandatory Scenario coverage. |
| [P106](../../presentation-playground/USER_PROMPTS.md#p106) | **D** This design-only review: 36 feature groups, explicit SDK/host/asset ownership, proposed portable addon topology, lifecycle/coordinate limits, and complete request triage. Implementation/promotion remains a subsequent pass. |

## Cross-cutting decisions and supersession

- **UI:** P45 is authoritative over earlier shared-view ideas. P27/P71 are
  different host styles, not requirements for an SDK skin system.
- **Game identity:** P68 establishes Afterlight as a bishōjo ensemble adventure.
  Tactical Command Link remains a separate example. Legacy point-and-click
  retirement does not imply deleting either example's fingertip interaction.
- **Promotion order:** P102–P106 supersede disposal, indefinite incubation and
  mandatory old-host/second-genre proofs. The practical proof is independent
  installation and an editable starter using the same SDK, plus preserved
  Afterlight behavior. No actual package has been assembled by this review.
- **Scenario:** P103 makes it a secondary experiment. Small animation catalogs
  can remain data without forcing every behavior into the old closed language.
- **Five original hints:** all concrete mechanisms are implemented by P99;
  original deferral wording is historical. Standing framing is still deferred.
- **Anatomy:** P100's proposal-only limit survives P106. SDK design may describe
  where a future adapter feeds geometry, but does not ratify or annotate it.
- **Evidence:** media approvals/budgets and past gameplay checks remain bound to
  their original passes. This review adds documentation/source-review evidence,
  not new visual acceptance, listening approval or export/runtime proof.

The [SDK census](game-presentation-sdk-design.md#3-feature-census-and-proposed-ownership)
is the feature-to-owner summary. The [current inventory](../../presentation-playground/CURRENT_STATUS.md)
continues to own what is implemented in the experimental project. The
[request ledger](../../presentation-playground/REQUESTS.md) preserves outcomes
at the time of each pass; it must not be read as a list of independent modules.

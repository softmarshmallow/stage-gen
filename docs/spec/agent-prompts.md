# AI flows + prompts (review sheet)

Every image-gen call the pipeline makes, written as a function-spec with
its inputs, output artifact id, and the **verbatim** prompt sent to the
model. Reviewing this file should be enough to spot prompt drift / bad
contracts / redundant guidance.

All calls go to `openai/gpt-image-2` via Vercel AI Gateway, with
`moderation: "low"`, wrapped in the project's retry helper (see
`docs/tech/gpt-image-2.md`). `${tag}` is the world's slug; `${i}` is a
0-based variant index.

---

## Pipeline orchestration

The pipeline runs five waves (one image-gen wave + one **text-gen agent**
wave + two image-gen waves + one CPU wave). Calls inside a wave fire in
parallel.

| Wave | Step | Parallelism | Backend |
|---|---|---|---|
| 1 | `generate_concept` | 1 | image |
| 1.5 | `generate_world_spec` (vision LLM, structured output) | 1 | text agent |
| 2 | L× `generate_layer` (parallax depth layers, agent-designed count + per-layer config), `generate_character_concept`, N× `generate_mob_concept`, `generate_tileset`, M× `generate_obstacles`, `generate_items`, `generate_inventory`, `generate_portal` | `5 + L + N + M` | image |
| 3 | `generate_character_states_combined`, `generate_character_attack`, N× `generate_mob_idle`, N× `generate_mob_hurt` | `2 + 2N` | image |
| 4 | `splitCombined` (CPU only — slices the master sheet) | 1 | none |

Defaults: `N = 8` mob variants, `M = 3` obstacle sheet variants. `L` is
whatever the world-design agent designs (1-5; typically 3-5).

---

## generate_concept(tag, theme, style?)

The single style root. Every other generator takes its output as a
reference image.

| | |
|---|---|
| **Output id** | `concept_${tag}.png` |
| **Inputs** | text prompt only — no image |
| **Canvas** | 1536 × 1024 (3:2 landscape) |
| **Wave** | 1 |

```text
${styleLine}2D side-scrolling platformer scene concept art, wide cinematic landscape view.
Theme: ${theme}.
Compose clear DEPTH: distant background (sky, distant mountains, soft atmosphere), middle (mid-distance trees / rolling hills), foreground (close trees / grass / near rocks).
Hand-painted painterly look.
```

`styleLine` = `"Visual style: <style>.\n"` when `style?` is provided, else empty.

---

## generate_world_spec(tag, prompt, mob_count, obstacle_count)

The **text-gen agent** that names every concrete asset the rest of the
pipeline draws. Calls a vision LLM with the concept image + the user's
world prompt; returns structured JSON via Zod schema. Downstream image
generators (mob concept, obstacles, items, parallax layers) read this
file at gen time and feed the agent's names + briefs into their prompts
so what gets drawn actually matches the world's theme — not a static menu.

| | |
|---|---|
| **Output id** | `world_spec_${tag}.json` |
| **Inputs** | `concept_${tag}.png` (vision), user world prompt (text) |
| **Backend** | text-gen LLM via structured-output (`generateObject`-style) call — `openai/gpt-5.5` |
| **Wave** | 1.5 (between concept and image fan-out) |

### Output shape (Zod schema)

```ts
{
  world: { name, one_liner, narrative },
  mobs: [
    { tier_label, body_plan, name, brief },   // length = mob_count
    ...
  ],
  obstacles: [
    {
      sheet_theme,
      props: [{ name, brief }, × 8],          // length = obstacle_count
    }, ...
  ],
  items: [
    { kind, name, brief },                    // length = 8
    ...
  ],
  layers: [
    { id, title, z_index, parallax, opaque, paint_region, description },
    ...                                       // length 1..5; exactly one opaque
  ],
}
```

**No pre-defined enums anywhere.** `tier_label`, `body_plan`, and item
`kind` are all agent-designed strings — the agent invents the world's
ladder and pickup categories from scratch using the concept image as
its only constraint.

**Runtime contract**: `mobs[]` is an ascending power ladder (slot 0
weakest, slot N-1 strongest). The runtime scales HP linearly with
slot index (`mobHpForTier(i) = i + 1`), so monotonic power across
slots is required. The agent is told this in the prompt.

### System prompt

```text
You are a WORLD-DESIGN AGENT for a procedural 2D side-scrolling platformer.

The user gives you a world prompt and the world's main concept art image (palette, atmosphere, mood — your source of truth). You produce a tight world bible naming AND DESIGNING every asset the downstream image-generation pipeline will draw.

Image-generation calls downstream will receive BOTH your output AND the same concept image. So you don't need to re-describe the world's look in long paragraphs — focus on DESIGN CHOICES and concise naming + briefs that anchor each asset to the world's theme.

NAMING RULES (critical — image models receive these names later, and confusing names produce wrong sprites):
- 1-3 words for names. Pronounceable. World-specific.
- Avoid generic names ("Slime", "Goblin", "Crate") — design every entry to fit this world's flavour ("Mosswick", "Cinder Hare", "Ash Reliquary").
- "brief" is ONE short sentence/clause for the image model to riff on — silhouette + a distinguishing visual trait.

Return ONLY the structured object.
```

### User prompt

```text
WORLD PROMPT (from the user): "${userPromptText}"

The image attached is the world's main concept art.

PRODUCE THE WORLD BIBLE. You design every entry yourself — there is no pre-defined ladder or item palette to fill in. Use the concept art as your sole source of truth for what fits this world.

1) world: name (1-3 words), one_liner, narrative (2-4 sentences — setting, atmosphere, tone, what's at stake).

2) mobs: design a CREATURE LADDER of exactly ${mobCount} rungs for this world. Slot 0 = the WEAKEST / smallest / lowest-tier creature in this world. Slot ${mobCount - 1} = the STRONGEST / largest / boss-class apex. Power, size, ornateness, and threat must monotonically rise across slots — the runtime scales HP linearly with slot index, so the ladder ordering is load-bearing. For EACH slot, design:
   - tier_label: short label for this rung — your design (e.g. "hatchling", "forager", "stalker", "bloomling", "alpha"). Don't reuse the same label across slots.
   - body_plan: 2-5 word body-plan archetype that defines this creature's silhouette (e.g. "four-legged quadruped", "six-legged insectoid", "two-legged bird", "horned biped", "tendrilled cephalopod"). Body plans MUST clearly differ between ADJACENT slots so the ladder reads visually distinct — DO NOT repeat a body plan on consecutive rungs.
   - name: 1-3 word creature name
   - brief: ONE sentence — silhouette + a distinguishing trait. Don't restate the tier_label or body_plan.

3) obstacles: exactly ${obstacleCount} obstacle sheets. For each sheet pick a thematic bias (sheet_theme, 2-4 words) appropriate to this world — sheet themes must NOT duplicate. Then list exactly 8 props with name + brief, all clearly fitting that sheet's theme.

4) items: exactly 8 collectible pickups for this world. You design EACH pickup yourself — no fixed kind enum. Vary the kinds across the 8 entries (e.g. one currency, one consumable, one key/access, one rare relic, one weapon trinket — but choose what makes sense for THIS world). For EACH item:
   - kind: 1-2 word category label — your design (e.g. "sun-coin", "spore-vial", "amber-bead", "rune-shard"). Used in HUD / pickup logs. Don't reuse the same kind across items.
   - name: 1-3 word item name
   - brief: one short clause — appearance + flavour

5) layers: design 1-5 PARALLAX DEPTH LAYERS for this world. Each layer is a 3:1 horizontal panel (2400×800) painted in this world's style. The runtime stacks them back-to-front by z_index and scrolls each at its own parallax speed.

REQUIRED: include EXACTLY ONE OPAQUE BACKDROP layer (e.g. sky / nebula / vast distant void). It must have z_index=0, parallax=0, opaque=true. This layer is what shows behind everything else.

All other layers (1 to 4 of them) are TRANSPARENT — they paint a region and leave the rest as magenta chroma key so deeper layers show through.

For each layer:
   - id: lowercase_snake slug for the filename ("sky_void", "far_peaks", "mid_canopy", "fg_vines")
   - title: human-readable
   - z_index: integer; lowest is drawn first (deepest). Use 0 for the opaque backdrop, then ascending values for each transparent layer painted on top.
   - parallax: scroll-speed multiplier. 0 for the opaque backdrop. Then ~0.15 for far / ~0.4 for mid / ~0.75 for near / ~1.1 for foreground accents that scroll faster than gameplay. Pick what fits each layer's depth.
   - opaque: true ONLY for the deepest backdrop. All other layers MUST be false.
   - paint_region: describe in CANVAS-FRACTION terms which Y / X range you'll paint, and what stays magenta. The Y axis runs 0/5 (top) to 5/5 (bottom). Examples: "paint Y range 3/5..5/5 (lower 40%) — leave the upper 60% magenta because the deeper sky covers it", "paint full canvas" for the opaque sky, "sparse vertical accents at any Y, X anywhere" for foreground vines. Be precise about what stays magenta.
   - description: ONE sentence — what to paint in the painted region (e.g. "silhouettes of jagged ash mountains receding into haze"). World-specific.

THE RUNTIME HANDLES LOOPING + DEPTH-OF-FIELD: don't paint loop-fade gradients yourself, and don't worry about blur. The runtime crossfades the L/R edges of each transparent layer so seams are invisible, and applies a depth-of-field blur derived from the layer's parallax (foreground layers with parallax > 1 get progressively blurred to suggest out-of-focus near-camera depth). Paint each layer SHARP and edge-to-edge as if it were a single isolated panel.
```

The agent designs the entire ladder + item palette + parallax stack from scratch — there is no per-slot guidance template anywhere in the pipeline.

---

## generate_layer(tag, concept_tag, layer_idx)

A single per-layer generator, called once per entry in `world_spec.layers[]`
(1-5 calls). Each entry is fully agent-designed (id, z_index, parallax,
opaque, paint_region, description). The deepest layer is the agent's
opaque backdrop — there is no separate skybox call.

There is no lobe-mask layout prior. The runtime applies a horizontal
alpha-fade gradient at each transparent layer's L/R edges and renders two
overlapping copies, so seams crossfade automatically — no painter-side
cooperation needed.

| | |
|---|---|
| **Output id** | `layer_${tag}_${layer.id}.png` |
| **Inputs** | `concept_${concept_tag}.png`, `world_spec_${tag}.json` (`layers[layer_idx]`) |
| **Canvas** | 2400 × 800 (3:1) |
| **Wave** | 2 (×L, where L = `world_spec.layers.length`) |

```text
Parallax depth layer for a 2D side-scrolling platformer.
The provided image is the world's concept art — match its painterly rendering, palette, lighting, and overall mood EXACTLY.

LAYER METADATA (designed by the world-design agent for this world):
  • Title: "${layer.title}"
  • Z-index: ${layer.z_index} (${layer.opaque ? "deepest backdrop" : "transparent overlay; deeper layers show through where you leave magenta"})
  • Parallax: ${layer.parallax} (${depthPhrase})

WHAT TO PAINT (one sentence): ${layer.description}

WHERE TO PAINT (canvas-fraction language; Y axis runs 0/5 top to 5/5 bottom, X axis 0/5 left to 5/5 right):
${layer.paint_region}

Honour the paint region literally. Painted content fills the described region edge-to-edge with full painterly detail; outside the described region the rules below apply.

${opaqueClause}

LOOPING — handled by the runtime. The image will be rendered twice with overlap and crossfaded at the L/R edges, so seams disappear automatically. You do NOT need to paint any loop-fade gradient, alpha taper, or "fade-to-edge" effect. Paint the content edge-to-edge as if the canvas were a single isolated panel; the runtime takes care of seamless tiling.

Output canvas: 2400×800 (3:1).
Same painterly style as the concept. Do NOT render any text in the output. No labels, no borders.
```

`depthPhrase` is computed from `layer.parallax` to nudge the model on detail level:

| parallax range | phrase |
|---|---|
| `opaque` | `static distant backdrop (no scrolling)` |
| `< 0.25` | `FAR distance — atmospheric, hazier, low contrast` |
| `< 0.6` | `MID distance — softer detail, partial atmospheric haze` |
| `< 1.0` | `NEAR distance — sharper detail, fuller saturation` |
| `>= 1.0` | `FOREGROUND — sharp, high-contrast, very close to camera` |

`opaqueClause`:

```text
[when layer.opaque == true]
OPAQUE BACKDROP — fill the ENTIRE canvas. Do NOT use any magenta chroma key. Every pixel is part of the layer. There is no transparent region.

[when layer.opaque == false]
TRANSPARENT LAYER — paint only inside the region described above; everywhere else stays SOLID MAGENTA (#FF00FF). Magenta is the chroma key — those pixels become transparent at runtime so deeper layers show through.
```

---

## generate_tileset(tag, concept_tag?, style?)

| | |
|---|---|
| **Output id** | `tileset_${tag}.png` |
| **Inputs** | `fixtures/image_gen_templates/wireframe.png` (3-colour role layout), `concept_${concept_tag}.png` (style ref) |
| **Canvas** | 2400 × 800 (3:1) — sliced as 12 cols × 4 rows = 48 cells |
| **Wave** | 2 |

```text
${styleLine}${conceptLine}Render the layout in the FIRST image as ground terrain for this world.
The layout is a 12×4 grid of independent ground blocks; each cell is one self-contained block that meets its neighbours at the cell border, sharing material with adjacent cells.

The GREEN regions mark the WALKABLE SURFACE LAYER of this world (only the top row has any). Treat green as a placeholder colour, NOT as a material instruction — the actual material must come from the world style reference. For example: lush forest → grass blades; snowy mountain → snow / snowdrifts / pine-needle litter; desert → dry grass tufts / sand drifts; swamp → mossy clumps / reeds; cyberpunk alley → broken pavement edge / weeds in cracks. Pick the material that fits the reference.

The green silhouette has TWO parts you must read literally as SHAPES (independent of what material you paint them with):
  • A thin horizontal BAND of solid green near the middle of the cell — paint this as the continuous flat top of the walkable surface (the strip the player walks on).
  • Tall, irregular GREEN PROTRUSIONS rising upward from that band into the magenta sky — paint these as vertical surface details: blades, drifts, crystals, tufts, weeds, sprigs, icicles — whatever fits the world. Vary heights; some short, some tall, some clumped.
Honour both parts. Do NOT smooth the protrusions into a flat ledge or trim them into a hedge; do NOT thicken the band into a fat slab. The band stays thin and the protrusions stand out against the sky.

The GRAY regions are the UNDERGROUND material directly below the walkable surface — uniform across all three lower rows. Pick the material from the world reference (dirt, packed snow, sand, stone, peat, concrete substrate, etc.). Do NOT add a second surface layer, ledges, terraces, or highlights between rows; the horizontal seams are tile borders, not elevation changes.

Magenta regions stay exactly magenta, untouched (including the magenta gaps between tall protrusions at the top of the surface layer).
Fill each cell edge-to-edge.
```

`conceptLine` is added when `concept_tag` is supplied: `"The SECOND image is the style reference — match its rendering technique, brushwork, palette, lighting, atmosphere and overall mood exactly. The FIRST image is only a layout guide; do not copy its flat colours.\n"`

---

## generate_character_concept(tag, concept_tag, description?)

Three-pose turnaround used as the design reference for every character
motion sheet downstream.

| | |
|---|---|
| **Output id** | `character_concept_${tag}.png` |
| **Inputs** | `concept_${concept_tag}.png` |
| **Canvas** | 2400 × 800 (3:1) |
| **Wave** | 2 |

```text
Character turnaround sheet for a 2D platformer.
The provided image is the world's concept art — match its painterly rendering, palette, lighting, and overall mood EXACTLY.
Render the SAME character three times in a single horizontal row, evenly spaced:
  1) FRONT view (facing camera)
  2) SIDE view (facing right, profile)
  3) BACK view (facing away from camera)

Character: ${description}.
Each pose is full body in a relaxed neutral standing pose — head to feet visible, arms at sides.
Equal spacing between poses, identical scale, same vertical baseline (feet on the same horizontal line).
The entire background is solid magenta (#FF00FF) — chroma key, will be removed later.
No ground shadow, no border, no labels, no captions.
```

---

## generate_character_states_combined(tag)

The single-largest call (≈8.26 Mpx — sized just under the model's 8.3 Mpx
cap; this is the longest wall-clock call in the pipeline). Renders all 5 character
motion states on one master sheet under a head-rail / feet-rail anchor
contract; sliced into per-state strips in wave 4.

| | |
|---|---|
| **Output id** | `character_${tag}_combined.png` |
| **Inputs** | `fixtures/image_gen_templates/character_template_combined.png` (5×4 layout prior), `character_concept_${tag}.png` |
| **Canvas** | 2400 × 3440 (≈ 30:43, just under 8.3 Mpx cap) |
| **Wave** | 3 |

Grid: rows = `idle, walk, run, jump, crawl` (top → bottom), 4 frames each.

```text
Sprite animation MASTER SHEET for a single 2D platformer character.
TWO reference images are provided:
  IMAGE 1 — LAYOUT TEMPLATE: a 4×5 grid of equal cells on magenta with bright YELLOW grid lines. Each cell contains a gray HUMANOID silhouette (head circle + torso + legs) marking the EXACT position, scale, and feet baseline the character must occupy:
    • The CYAN horizontal rail across the top of each silhouette = the TOP OF THE CHARACTER'S HEAD/HAIR.
    • The GREEN horizontal rail running across the FULL ROW WIDTH = the SOLES OF THE FEET. Every frame in a row shares this single green ground line.
    • The grey humanoid figure between cyan and green rails marks the body's height, width, and centre.
  Match those rails and silhouette dimensions PRECISELY in every cell; do NOT draw the character taller, shorter, wider, or narrower than the silhouette.
  IMAGE 2 — DESIGN REFERENCE: the character's turnaround. Match its design, proportions, colours, outfit, and rendering style EXACTLY across every frame.

Render a master sheet as a strict 4×5 grid (4 columns × 5 rows), aligned 1:1 with the template's cells. Each ROW is a different motion state. Each COLUMN within a row is the next frame in that motion's cycle, read left-to-right.

Rows (top to bottom):
  Row 1 (top): IDLE — subtle breathing, weight shift, arms relaxed at sides. Loops cleanly.
  Row 2: WALK — alternating left/right legs forward, gentle opposite arm swing, slight head bob. Loops cleanly.
  Row 3: RUN — full sprint, knees driven high, bent arms swinging hard front-to-back, body leaning slightly forward, cloak/hair trailing. Faster, more exaggerated than the walk row. Loops cleanly.
  Row 4: JUMP — frame 1 anticipation crouch, frame 2 push-off rising, frame 3 apex with legs tucked, frame 4 descending/landing absorption.
  Row 5 (bottom): CRAWL / SQUAT-WALK — character is crouched LOW, knees deeply bent, body lowered to ~half its standing height, head ducked. Alternating crouched steps with hands near knees or held low. Sustained low squat the entire row. Loops cleanly.

In every cell, replace the gray silhouette with the character in the correct pose for that row's motion and that column's phase. CRITICAL anchoring rules — the rails are HARD limits:
  - The CYAN top rail = the TOP of the character's head/hair. Do NOT paint hair, ears, or head pixels above the cyan line.
  - The GREEN feet rail = the SOLES of the character's feet/boots. Do NOT paint any character pixels below the green line.
  - The horizontal centre of the silhouette = the character's body centre.
  - The character must fit ENTIRELY between the cyan top rail and the green feet rail; pixels outside the silhouette stay magenta.
  - The narrow magenta band below the green feet rail in every cell MUST remain solid magenta — no boots, no feet, no shadow, no toes poking through.
SCALE LOCK: because every row shares the same green feet rail height and the same cyan head-top rail height, the character's overall body scale must be IDENTICAL across ALL 20 frames in the sheet. The crawl row character is the SAME body as the idle row, just deeply crouched — same head size, same proportions, same scale; only the pose changes. Do NOT enlarge the run-row character or shrink the crawl-row character.

Side view, facing right, throughout the whole sheet.
Background is solid magenta (#FF00FF) everywhere outside the character — chroma key, will be removed.
Do NOT render the silhouettes, the cyan/green rails, or the yellow grid in the output. No labels, no row dividers, no borders, no frame numbers, no ground shadow.
```

---

## generate_character_attack(tag)

| | |
|---|---|
| **Output id** | `character_${tag}_attack.png` |
| **Inputs** | `fixtures/image_gen_templates/character_template.png` (4×1 layout prior), `character_concept_${tag}.png` |
| **Canvas** | 2400 × 800 (3:1) |
| **Wave** | 3 |

Grid: 4 cols × 1 row, frame phases: `wind-up, swing, impact, recovery`.

```text
Sprite ATTACK animation strip for a 2D platformer character.
TWO reference images:
  IMAGE 1 — LAYOUT TEMPLATE: a 4x1 grid on magenta with bright YELLOW grid lines. Each cell has a CYAN horizontal rail (head-top marker) and a single GREEN horizontal rail across the FULL ROW (feet baseline / ground line). The grey humanoid silhouette marks the body's height, width, and centre.
  IMAGE 2 — DESIGN REFERENCE: the character's turnaround. Match its design, proportions, colours, outfit, and rendering style EXACTLY across every frame.

Render a 4-frame ATTACK animation as a strict 4x1 grid of equal cells, aligned 1:1 with the template's cells. Read order: left-to-right.

The character performs ONE attack motion, choose whatever weapon / style fits the design reference (a sword swing, a punch combo, a magic cast, a claw swipe, a staff strike, a kick — anything consistent with the character):
  Frame 1 — ANTICIPATION / WIND-UP: weight shifted back, weapon or limb drawn back / charging up, body coiled.
  Frame 2 — FORWARD SWING / RELEASE: body driving forward, weapon or limb mid-arc / mid-throw, peak motion line, debris or motion suggestion welcome.
  Frame 3 — IMPACT / FULL EXTENSION: arm and weapon at full extension forward, weight committed forward, peak reach. This is the hit frame.
  Frame 4 — RECOVERY: weapon / limb pulling back, body settling back to neutral, ready to chain into idle.
The four frames should read as ONE fluid motion when played at ~12 fps.

Side view facing right.

CRITICAL anchoring rules — the rails are HARD limits FOR THE BODY:
  - The CYAN top rail = the TOP of the character's head/hair. Do NOT paint the head above it.
  - The GREEN feet rail = the SOLES of the character's feet/boots. Do NOT paint any character pixels below the green line.
  - The character's BODY (torso, head, legs) must fit between the rails at the SAME scale as the silhouette — same proportions as the idle/walk/run reference frames.
  - WEAPON / EFFECT EXCEPTION: an outstretched sword, fist, claw, or magic effect MAY extend OUTSIDE the silhouette horizontally during the swing/impact frames — that is expected. But the BODY itself stays within the rails.
  - Pixels that are not the character or their weapon/effect stay solid magenta.

Background is solid magenta (#FF00FF) — chroma key, will be removed.
Do NOT render the silhouettes, the cyan/green rails, or the yellow grid in the output. No labels, no borders, no shadows.
```

---

## generate_mob_concept(tag, concept_tag, description?, variant_idx)

Per-variant creature turnaround. The world-design agent designs the
**entire mob ladder** for the world — including tier_label, body_plan,
name, and brief for every slot. This generator reads slot `i` from
`world_spec_${tag}.json` and feeds the agent's design choices into the
prompt. The generator knows nothing about specific tier names or body
plans of its own.

If the spec is missing, falls back to a generic `description` prompt
with no ladder context (generator remains runnable in isolation).

| | |
|---|---|
| **Output id** | `mob_concept_${tag}_${i}.png` |
| **Inputs** | `concept_${concept_tag}.png`, `world_spec_${tag}.json` (`mobs[i]`: tier_label, body_plan, name, brief) |
| **Canvas** | 2400 × 800 (3:1) |
| **Wave** | 2 (×N) |

```text
Creature / mob turnaround for a 2D platformer.
The provided image is the world's concept art — match its painterly rendering, palette, lighting, and overall mood EXACTLY.
Render the SAME creature three times in a single horizontal row, evenly spaced:
  1) FRONT view (facing camera)
  2) SIDE view (facing right, profile)
  3) BACK view (facing away from camera)

${designBlock}

${ladderBlock}

Keep the creature CONSISTENT across the three views (same anatomy, same colours, same proportions).
Each pose is the creature in a relaxed neutral idle/standing pose, full body visible. The base of the creature (feet / underside / contact point) must rest on a SHARED horizontal baseline across all three poses.
Equal spacing, identical scale.

Background is solid magenta (#FF00FF) — chroma key, will be removed.
No labels, no borders, no shadows under the creature.
```

`designBlock` injects the world-design agent's choices for this slot (when the spec is present):

```text
WORLD-DESIGN AGENT'S CHOICE for this creature:
  • Name: "${mobEntry.name}"
  • Tier label (rung name on this world's ladder): "${mobEntry.tier_label}"
  • Body-plan archetype: ${mobEntry.body_plan}
  • Brief: ${mobEntry.brief}

Honour all of the above. The body-plan archetype is the silhouette contract — it MUST visually distinguish this creature from creatures on adjacent rungs of the ladder.
```

When the spec is missing, `designBlock` collapses to `Creature for this world: ${fallbackDescription}.`

`ladderBlock` provides relative-power anchoring (when the spec is present):

```text
LADDER POSITION: this is rung ${slotNumber} of ${ladderTotal} on this world's mob ladder. Rung 1 is the weakest, lowest-tier creature in the world; rung ${ladderTotal} is the strongest, boss-class apex. Power, size, ornateness, and threat presence rise monotonically across the ladder. EVERY frame of this turnaround must read UNAMBIGUOUSLY at rung ${slotNumber} — its size, ornateness, level of detail, threat presence, and overall menace must clearly fit between rung ${max(1, slotNumber - 1)} and rung ${min(ladderTotal, slotNumber + 1)} on that ladder. Do NOT make the creature look weaker than rung ${slotNumber}, and do NOT make it look stronger than rung ${slotNumber}.
```

When the spec is missing, `ladderBlock` collapses to `(No ladder context available — design a single self-contained creature for this world.)`

---

## generate_mob_idle(tag, variant_idx)

| | |
|---|---|
| **Output id** | `mob_${tag}_${i}_idle.png` |
| **Inputs** | `fixtures/image_gen_templates/character_template.png` (sizing rail, reused), `mob_concept_${tag}_${i}.png` |
| **Canvas** | 2400 × 800 (3:1) |
| **Wave** | 3 (×N) |

```text
Sprite IDLE animation strip for a CREATURE / MOB in a 2D platformer.
TWO reference images:
  IMAGE 1 — LAYOUT TEMPLATE: a 4×1 grid on magenta with bright YELLOW grid lines. Each cell has a CYAN horizontal rail (head-top marker) and a single GREEN horizontal rail across the FULL ROW (the feet baseline / ground line). The grey humanoid silhouette is just a SIZING RAIL — the creature does NOT need to be humanoid; only the top of the creature must touch the CYAN rail and the base of the creature must rest on the GREEN rail.
  IMAGE 2 — DESIGN REFERENCE: the creature's turnaround. Match its design, anatomy, colours, and rendering style EXACTLY across every frame.

Render a 4-frame IDLE animation as a strict 4×1 grid of equal cells, aligned 1:1 with the template's cells.
Read order: left-to-right — each cell is the next moment in the idle cycle.
Animation: a subtle idle — small breathing rise/fall, gentle sway, antenna twitch, wing flutter, tail flick (whatever fits the creature's anatomy). The cycle LOOPS cleanly: the last frame leads naturally into the first. Side view facing right.

CRITICAL anchoring rules — the rails are HARD limits:
  - The CYAN top rail = the topmost point of the creature (head, antenna tip, ear tip — whatever is highest). Do NOT paint above it.
  - The GREEN feet rail = the creature's contact base (feet, slime base, underbelly — whatever rests on the ground). Do NOT paint below it.
  - The body fits ENTIRELY between the cyan and green rails; pixels outside the silhouette stay magenta.
  - Scale is IDENTICAL across all 4 frames — every frame uses the same creature size.

Background is solid magenta (#FF00FF) outside the creature — chroma key.
Do NOT render the silhouettes, the cyan/green rails, or the yellow grid in the output. No labels, no borders, no shadows.
```

---

## generate_mob_hurt(tag, variant_idx)

| | |
|---|---|
| **Output id** | `mob_${tag}_${i}_hurt.png` |
| **Inputs** | `fixtures/image_gen_templates/character_template.png`, `mob_concept_${tag}_${i}.png` |
| **Canvas** | 2400 × 800 (3:1) |
| **Wave** | 3 (×N) |

```text
Sprite HURT / DAMAGE animation strip for a CREATURE / MOB in a 2D platformer.
TWO reference images:
  IMAGE 1 — LAYOUT TEMPLATE: a 4x1 grid on magenta with bright YELLOW grid lines. Each cell has a CYAN top rail (head-top marker) and a single GREEN feet rail across the FULL ROW (ground baseline). The grey humanoid silhouette is just a SIZING RAIL — the creature does NOT need to be humanoid; only the top of the creature touches the cyan rail and the base of the creature rests on the GREEN rail.
  IMAGE 2 — DESIGN REFERENCE: the creature's turnaround. Match anatomy, colours, and rendering style EXACTLY across every frame.

Render a 4-frame HURT animation as a strict 4x1 grid of equal cells. Read order: left-to-right. Side view, the creature is facing RIGHT but is being hit FROM THE RIGHT (so the recoil pushes it LEFT — back of the body / head whips away from the attacker).

  Frame 1 — IMPACT FLINCH: sharp recoil, body whipping away from the hit point, head/eyes squeezed, mouth open in pain, limbs splayed slightly. Strongest pose of the four.
  Frame 2 — STAGGER PEAK: leaning back / off-balance, body tilted away from where the hit landed, weight shifted to the rear contact point, expression dazed.
  Frame 3 — STAGGER SETTLING: still off-balance but starting to recover, body partially returning to upright, dazed expression continuing.
  Frame 4 — RECOVERY: nearly back to neutral upright pose, almost ready to return to idle, residual flinch.

The four frames read as ONE recoil motion at ~10 fps.

CRITICAL anchoring rules — the rails are HARD limits:
  - CYAN top rail = the topmost point of the creature's body silhouette in its NEUTRAL standing pose. The recoil may visually compress/lower the head; that is fine, but do NOT paint anything ABOVE the cyan rail.
  - GREEN feet rail = ground contact base. The creature stays on the ground (one foot may lift, but the body's contact point with the ground stays on the green line). Do NOT paint any pixels BELOW the green line.
  - Scale is IDENTICAL across all 4 frames AND identical to the idle reference scale — same body size, just contorted.
  - The creature stays the same colours and design; do NOT add red flash overlays, blood, or extra effects (the runtime tints / flashes the sprite procedurally).

Background is solid magenta (#FF00FF) — chroma key.
Do NOT render the silhouettes, the cyan/green rails, or the yellow grid in the output. No labels, no borders, no shadows.
```

---

## generate_obstacles(tag, concept_tag, variant_idx)

Per-sheet themed prop sheet (8 props in 4×2). Sheet theme **and** the 8
prop names come from `world_spec_${tag}.json` (`obstacles[i].sheet_theme`
+ `obstacles[i].props[]`). When the spec is missing, falls back to a
hardcoded 5-theme rotation with a generic prop menu.

| | |
|---|---|
| **Output id** | `obstacles_${tag}_${i}.png` |
| **Inputs** | `fixtures/image_gen_templates/obstacle_template.png` (4×2 cells with green grass band), `concept_${concept_tag}.png`, `world_spec_${tag}.json` (obstacles[i]) |
| **Canvas** | 2400 × 800 (3:1) |
| **Wave** | 2 (×M) |

```text
Obstacle / prop sprite sheet #${variantIdx + 1} for a 2D side-scroll platformer.
TWO reference images:
  IMAGE 1 — LAYOUT TEMPLATE: a 4×2 grid of 8 equal cells on magenta. Each cell has a thin GREEN GRASS BAND at the bottom — that band is the ground-contact line where the obstacle rests on the world's ground.
  IMAGE 2 — STYLE REFERENCE: the world's concept art. Match its painterly rendering, palette, lighting, and overall mood EXACTLY.

Theme for THIS sheet: ${sheetTheme}. Other sheets in this world cover other themes, so emphasize this one — the 8 props on this sheet should all clearly fit the theme above.

[WHEN WORLD SPEC PRESENT]
PAINT EXACTLY THESE 8 NAMED PROPS, ONE PER CELL (read order: top-left → top-right → bottom-left → bottom-right):
  • Cell 0: "${name}" — ${brief}
  • Cell 1: "${name}" — ${brief}
  • …
  • Cell 7: "${name}" — ${brief}

Keep the proportions realistic and varied — some props small, some tall, some wide. Each must clearly read as the named entry.

[FALLBACK WHEN SPEC MISSING — generic menu]
Paint 8 DIFFERENT self-contained obstacles / props for this world, one per cell. Vary type AND size dramatically:
  • a small low rock or pebble cluster
  • a medium boulder
  • a tall narrow vertical prop (post, sign, broken pillar, totem — choose what fits the world)
  • a wide low prop (crate, fallen log, stone slab — fits the world)
  • a rounded organic prop (mushroom, bush, large flower bud — fits the world)
  • a tall thin organic prop (dead tree stump, tall reeds, bamboo cluster — fits the world)
  • an ambient light / decorative prop (lantern, brazier, idol, shrine — fits the world)
  • a unique flavour prop (whatever this world calls for — surprise me)

CONTRACT for every cell:
  - The obstacle's BASE rests directly on the grass band, with grass tufts wrapping the foot of the obstacle so it BLENDS into the world's grass — no floating, no shadow gap.
  - Keep the bottom of each painted obstacle FLAT and TEXTURED (not a sharp single-line edge) so it integrates with grass at any width when placed in-world.
  - The grass band stays GREEN at the bottom of the cell — paint over it in the same painterly grass style as the world reference.
  - Above the grass band, EVERY pixel that is NOT part of the obstacle stays solid magenta (#FF00FF). Magenta is the chroma key.
  - Each obstacle is opaque and HARD-edged against the magenta — no soft halos, no glow, no feathered alpha.
  - Obstacles vary in size: some fill 30% of the cell, others fill 90%. Mix small / medium / tall / wide so the demo has visual variety.

Do NOT render the cell grid lines or any text in the output. No labels, no borders, no frame numbers.
```

### Fallback theme rotation (used when world spec is missing)

When the world-design agent's spec is unavailable, each variant biases
toward a different thematic category so multi-sheet variety is
preserved. The categories are open-ended (e.g. mixed variety, natural
debris, vegetation, built structures, containers and trinkets) — pick a
small rotation that fits the world's flavour and cycle through it
modulo the variant count.

---

## generate_items(tag, concept_tag)

8 collectible items in 4×2, each centred in its cell (no ground band).
Reuses `obstacle_template.png` as a generic 4×2 grid prior. Per-cell
**kind + name + brief** comes from `world_spec_${tag}.json` (`items[]`,
8 entries). The agent designs every item including its **kind** label
— there is no fixed kind enum. Falls back to a generic 8-item menu when
the spec is missing.

| | |
|---|---|
| **Output id** | `items_${tag}.png` |
| **Inputs** | `fixtures/image_gen_templates/obstacle_template.png`, `concept_${concept_tag}.png`, `world_spec_${tag}.json` (items[]) |
| **Canvas** | 2400 × 800 (3:1) |
| **Wave** | 2 |

```text
Item / pickup sprite sheet for a 2D side-scroll platformer.
TWO reference images:
  IMAGE 1 — LAYOUT TEMPLATE: a 4x2 grid of 8 equal cells on magenta. Ignore the green band at the bottom of each cell — paint magenta over it. Treat each cell as a centered slot for ONE item.
  IMAGE 2 — STYLE REFERENCE: the world's concept art. Match its painterly rendering, palette, lighting, and overall mood EXACTLY.

[WHEN WORLD SPEC PRESENT]
PAINT EXACTLY THESE 8 NAMED ITEMS, ONE PER CELL (read order: top-left → top-right → bottom-left → bottom-right). Each item is centred inside its cell. The "kind" in parentheses is the world-design agent's category label for the pickup (its own design, not a fixed enum) — paint each item so it visually reads as that kind:
  • Cell 0: "${name}" (${kind}) — ${brief}
  • Cell 1: "${name}" (${kind}) — ${brief}
  • …
  • Cell 7: "${name}" (${kind}) — ${brief}

[FALLBACK WHEN SPEC MISSING — generic menu]
Paint 8 DIFFERENT collectible items / pickups for this world, one per cell, each CENTERED inside its cell. Vary the item types so the loot feels rich. Choose 8 from this menu (or substitute world-appropriate equivalents):
  • a coin / currency token
  • a glowing gem or crystal shard
  • a small potion vial / flask with liquid
  • an old key
  • a rolled scroll or folded paper
  • an edible (mushroom / fruit / berry / loaf)
  • a tiny weapon trinket (dagger, arrow, throwing star)
  • a rare / mysterious orb or relic

CONTRACT for every cell:
  - Each item is CENTERED inside its cell — neither at the top nor sitting on the bottom band.
  - Each item is sized to roughly 40-60% of its cell's height (not filling the cell, leaving comfortable margin).
  - Each item is opaque and HARD-edged against magenta — no soft halos, no glow halos painted as soft alpha (any "glow" appearance must be painted as crisp shapes; the runtime applies any glow/bloom procedurally).
  - EVERY pixel that is NOT part of the item stays solid magenta (#FF00FF). Magenta is the chroma key.
  - Items vary in size relative to each other: a coin is small, a relic is large.
  - The 8 items together form a varied loot palette — no two items should read the same.

Do NOT render the cell grid lines, the green grass band, or any text in the output. No labels, no borders, no frame numbers.
```

---

## generate_inventory(tag, concept_tag)

Themed bag UI panel with 8 recessed empty slots; runtime composites item
icons into the slot centres at known coordinates.

| | |
|---|---|
| **Output id** | `inventory_${tag}.png` |
| **Inputs** | `fixtures/image_gen_templates/inventory_template.png` (yellow outer frame + cyan slot grid), `concept_${concept_tag}.png` |
| **Canvas** | 1536 × 1024 (3:2) |
| **Wave** | 2 |

```text
Inventory / bag UI panel for a 2D side-scroll platformer.
TWO reference images:
  IMAGE 1 — LAYOUT TEMPLATE: a 1536x1024 magenta canvas with a YELLOW rectangular outline marking the panel's outer edge, and a 4x2 grid of CYAN-outlined square slots inside. The cyan rectangles mark the EXACT positions and sizes of the 8 inventory slots — these must be honoured 1:1 in the output.
  IMAGE 2 — STYLE REFERENCE: the world's concept art. Match its painterly rendering style, palette, lighting, and overall mood EXACTLY.

Render an ornate themed inventory / bag panel:
  - The PANEL FRAME fills the area between the yellow outline and the cyan slot grid. Style it as something the inhabitants of this world would carry their belongings in: carved wood, etched stone, embroidered cloth, woven leather, hammered metal, woven reeds, polished bone — whatever fits the concept reference. Add decorative trim, corner motifs, and small thematic flourishes appropriate to the world.
  - The 8 SLOTS are EMPTY recessed cells, one inside each cyan outline. Each slot is a SHALLOW INSET pocket — slightly darker / more shadowed than the surrounding panel, with subtle inner-edge shadow at the top-left and a faint highlight at the bottom-right to read as "recessed". The slot interior is a calm, mostly flat tone (so item icons composited on top at runtime read clearly). NO items, NO icons, NO placeholder content inside any slot.
  - Slot positions, sizes, and the gutters between them must EXACTLY match the cyan-outlined grid in the template — do not shift, resize, rotate, or rearrange them.

OUTSIDE THE PANEL (everything beyond the yellow outline) stays solid magenta (#FF00FF). Magenta is the chroma key — it will be removed at runtime.

Do NOT render the cyan slot outlines, the yellow frame line, or any text in the output. No labels, no slot numbers, no badges, no cursor, no item icons.
```

---

## generate_portal(tag, concept_tag)

Building-sized entry / exit pair on one 2:1 sheet (left half = entry,
right half = exit). Same architectural body, distinguished only by
colour temperature and glow intensity. Sliced down the middle at runtime.

| | |
|---|---|
| **Output id** | `portal_${tag}.png` |
| **Inputs** | `concept_${concept_tag}.png` |
| **Canvas** | 2048 × 1024 (2:1) |
| **Wave** | 2 |

```text
Portal sprite sheet for a 2D side-scroll platformer — two
building-sized landmark structures painted on a single 2:1 canvas.

ONE reference image:
  IMAGE 1 — STYLE REFERENCE: the world's concept art. Match its painterly
  rendering, palette, lighting, and overall mood EXACTLY.

LAYOUT — exactly TWO equal halves on the canvas:
  LEFT HALF (entry portal): the START-of-stage portal. Reads as "you came
    from here" — calm, welcoming, slightly cool / muted in tone.
  RIGHT HALF (exit portal): the END-of-stage portal. Reads as "go through
    here to advance" — more active, slightly warmer / more luminous, with
    a clear sense of pull or invitation.

Both portals are the SAME body of architecture (gateway / shrine / arch /
torii / standing stones / runic doorway — pick one form that fits the
world's concept), differing only in subtle colour temperature and the
energy of any glow / particle / inner-fill detail. They should obviously
read as a matched pair.

CONTRACT for both portals:
  - Each portal stands UPRIGHT and is BUILDING-SIZED — roughly TWICE the
    height of a small humanoid hero would stand at the same scale.
  - The BASE of each portal sits flat on a thin GREEN GRASS BAND at the
    bottom of its half — the same grass-contact convention as obstacle
    tiles. Grass tufts wrap the portal's foot so it integrates with the
    world's ground. No floating, no shadow gap.
  - The portal has an OPEN INNER AREA (an aperture / archway / doorway)
    filled with a soft glow or mystical fill that hints at passage —
    swirling mist, a shimmer, a runic glow, a starfield. Keep this fill
    INSIDE the portal's frame — do not let it bleed past the architecture.
  - Each portal is centred horizontally inside its half and occupies
    roughly 70-85% of the half's height (leaving ~15% of headroom and the
    grass band at the foot).
  - Outside the portal architecture, EVERY pixel is solid magenta
    (#FF00FF). Magenta is the chroma key.
  - Each portal is opaque and HARD-edged against the magenta — no soft
    halos, no glow halos painted as soft alpha. The inner aperture glow
    must stay inside the architecture's frame and end at hard edges.
  - The two portals share the same overall silhouette and structural
    style; only colour temperature, glow intensity, and small symbolic
    accents (e.g. arrival vs departure runes) distinguish them.

Do NOT render any visible vertical divider line between the halves, no
labels, no text, no frame numbers, no grid lines. Just two portals on a
shared magenta field with green grass bands at their feet.
```

---

## (post-processing — no AI call)

`splitCombined(tag, outDir)` runs in-process via an image-processing
library after wave 3. It reads `character_${tag}_combined.png` and writes
5 per-state strips: `character_${tag}-fromcombined_idle.png`,
`…_walk.png`, `…_run.png`, `…_jump.png`, `…_crawl.png`.

`pickBgm({ tag, prompt? })` runs in the web runtime and matches the
world prompt against a curated BGM index — currently a deterministic
random pick by tag hash; no AI call.

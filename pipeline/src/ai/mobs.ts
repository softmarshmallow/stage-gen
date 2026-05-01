// Mob concept (turnaround) generators (Wave 2).
// One per ladder rung. Each prompt carries the agent's tier_label, body_plan,
// name, brief PLUS an explicit "rung i+1 of N" anchoring clause so the
// turnarounds visually escalate up the ladder (TC-036).

import { join } from "node:path";
import type { WorldSpec } from "../schema/world.ts";
import { generateImageAsset } from "./image-helper.ts";

const CANVAS_W = 2400;
const CANVAS_H = 800;

function buildMobPrompt(args: {
  mob: WorldSpec["mobs"][number];
  slotNumber: number; // 1-based
  ladderTotal: number;
  laddertierLabels: string[];
}): string {
  const { mob, slotNumber, ladderTotal, laddertierLabels } = args;
  const lowerNeighbour = Math.max(1, slotNumber - 1);
  const upperNeighbour = Math.min(ladderTotal, slotNumber + 1);

  // Show neighbour tier_labels for context so the model can interpolate.
  const ladderSummary = laddertierLabels
    .map((label, i) => `  rung ${i + 1}: "${label}"`)
    .join("\n");

  return (
    `Creature / mob turnaround for a 2D platformer.\n` +
    `The provided image is the world's concept art — match its painterly rendering, palette, lighting, and overall mood EXACTLY.\n` +
    `Render the SAME creature three times in a single horizontal row, evenly spaced:\n` +
    `  1) FRONT view (facing camera)\n` +
    `  2) SIDE view (facing right, profile)\n` +
    `  3) BACK view (facing away from camera)\n\n` +
    `WORLD-DESIGN AGENT'S CHOICE for this creature:\n` +
    `  • Name: "${mob.name}"\n` +
    `  • Tier label (rung name on this world's ladder): "${mob.tier_label}"\n` +
    `  • Body-plan archetype: ${mob.body_plan}\n` +
    `  • Brief: ${mob.brief}\n\n` +
    `Honour all of the above. The body-plan archetype is the silhouette contract — it MUST visually distinguish this creature from creatures on adjacent rungs of the ladder.\n\n` +
    `LADDER POSITION: this is rung ${slotNumber} of ${ladderTotal} on this world's mob ladder. Rung 1 is the WEAKEST, lowest-tier creature in the world; rung ${ladderTotal} is the STRONGEST, boss-class apex. Power, size, ornateness, and threat presence rise MONOTONICALLY across the ladder. EVERY frame of this turnaround must read UNAMBIGUOUSLY at rung ${slotNumber} — its size, ornateness, level of detail, threat presence, and overall menace must clearly fit between rung ${lowerNeighbour} and rung ${upperNeighbour} on that ladder. Do NOT make the creature look weaker than rung ${slotNumber}, and do NOT make it look stronger than rung ${slotNumber}.\n\n` +
    `Full ladder for context (the agent's labels in ascending power order):\n${ladderSummary}\n\n` +
    `Keep the creature CONSISTENT across the three views (same anatomy, same colours, same proportions).\n` +
    `Each pose is the creature in a relaxed neutral idle/standing pose, full body visible. The base of the creature (feet / underside / contact point) must rest on a SHARED horizontal baseline across all three poses.\n` +
    `Equal spacing, identical scale.\n\n` +
    `Background is solid magenta (#FF00FF) — chroma key, will be removed. EXACT colour, not a near-magenta.\n` +
    `No labels, no borders, no shadows under the creature.\n` +
    `Output canvas: 2400×800 (3:1).`
  );
}

export interface MobConceptArgs {
  prompt: string;
  tag: string;
  runDir: string;
  model: string;
  conceptImagePath: string;
  mobs: WorldSpec["mobs"];
}

export async function generateAllMobConcepts(args: MobConceptArgs) {
  const { prompt, tag, runDir, model, conceptImagePath, mobs } = args;
  const ladderTotal = mobs.length;
  const tierLabels = mobs.map((m) => m.tier_label);

  return Promise.all(
    mobs.map((mob, i) => {
      const outPath = join(runDir, `mob_concept_${tag}_${i}.png`);
      const promptText = buildMobPrompt({
        mob,
        slotNumber: i + 1,
        ladderTotal,
        laddertierLabels: tierLabels,
      });
      return generateImageAsset({
        stage: `mob-concept-${i}`,
        userPrompt: prompt,
        promptText,
        refs: [conceptImagePath],
        outPath,
        width: CANVAS_W,
        height: CANVAS_H,
        model,
        extra: {
          slot: i,
          rung: i + 1,
          ladder_total: ladderTotal,
          tier_label: mob.tier_label,
          body_plan: mob.body_plan,
          name: mob.name,
        },
      });
    }),
  );
}

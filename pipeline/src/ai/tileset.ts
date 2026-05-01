// Ground tileset generator (Wave 2).
// 12×4 grid on 2400×800. Each ROW encodes a different STRUCTURAL ROLE family
// per docs/spec/tileset.md — surface tiles, slope/inner-corner tiles, side &
// bottom-edge tiles, and fill + floating-platform tiles. Wireframe is reused
// as a generic 12×4 layout helper (it does not encode the per-row roles), so
// the prompt below carries the role contract verbatim, row by row, cell by
// cell, and demands visible cell separators so the runtime slicer can rely
// on the painted cell geometry matching the contract.
//
// Concept attached as the style reference.

import { join } from "node:path";
import { generateImageAsset } from "./image-helper.ts";

const CANVAS_W = 2400;
const CANVAS_H = 800;
const COLS = 12;
const ROWS = 4;
const CELL_W = CANVAS_W / COLS; // 200
const CELL_H = CANVAS_H / ROWS; // 200

// Role contract — extended from the compact 4×4 essentials in
// docs/spec/tileset.md to 12 cells per row by adding repeats / variants of
// each role so every cell still encodes a discrete structural function.
// The prompt explicitly enumerates each cell so no row collapses into a
// generic "stone fill" stripe (the failure mode of the previous attempt).
const PROMPT = `Render a 2D side-scrolling platformer GROUND TILESET.

Two reference images are attached:
  IMAGE 1 — generic 12-column × 4-row WIREFRAME on magenta. Use it ONLY as a coarse cell-grid alignment helper: the painted output must be split into exactly ${COLS} equal columns × ${ROWS} equal rows of self-contained tile cells. Do NOT copy any of the wireframe's flat colours into the painted material.
  IMAGE 2 — STYLE REFERENCE: the world's concept art. Match its painterly rendering, palette, lighting, atmosphere and overall mood EXACTLY. Pick the SURFACE material (snow / grass / sand / moss / pavement / etc.) and the UNDERGROUND material (packed snow / dirt / sandstone / peat / stone / etc.) from this reference.

CANVAS GEOMETRY — strict:
  • Output canvas: ${CANVAS_W}×${CANVAS_H} (3:1).
  • Strict ${COLS} × ${ROWS} grid of equal cells. Each cell is exactly ${CELL_W}px wide × ${CELL_H}px tall.
  • Render a thin, dark, 1-2px CELL-SEPARATOR LINE along every internal cell boundary (both horizontal and vertical seams) so each cell reads as a discrete sprite slot. The separator is a hairline gutter — do NOT let painted material flow between cells.
  • Magenta (#FF00FF) is the chroma key. Anywhere a cell's role calls for "sky" / "above-surface" / "outside-the-tile", paint solid magenta — those pixels become transparent at runtime.

ROW ROLE CONTRACT — each row encodes a DIFFERENT STRUCTURAL ROLE FAMILY. The four rows MUST read as four visually distinct families. If rows 2/3/4 all look like the same featureless block of underground material, the sheet is WRONG.

ROW 1 — TOP SURFACE TILES. **This is the ONLY row that contains surface material** (grass / snow / sand cap / etc., picked from the style reference). The walkable surface is a thin band near the TOP of each cell; magenta fills the area ABOVE the surface; underground material fills BELOW the surface down to the cell's bottom edge.
  • Cell (1,1): TOP-LEFT outer corner — surface only on TOP and LEFT edges; magenta fills the upper-right quadrant; underground fills lower-right.
  • Cell (1,2)–(1,4): TOP middle — flat continuous surface along the top edge; magenta above, underground below. Vary each cell with subtle decoration (a tuft, a pebble, a clean variant).
  • Cell (1,5): TOP-RIGHT outer corner — surface only on TOP and RIGHT edges; magenta fills the upper-left quadrant.
  • Cell (1,6)–(1,8): TOP single / 1-tile platform top — surface caps the top edge with magenta wrapping LEFT, RIGHT, and BOTTOM-corners (a short isolated cap).
  • Cell (1,9)–(1,11): more TOP middle variants (clean / decorated / clumped surface details).
  • Cell (1,12): TOP-LEFT outer corner variant (mirror of (1,1)) — closes the row.

ROW 2 — SLOPE TILES + INNER (CONCAVE) CORNER TILES. The defining feature of this row is DIAGONAL geometry. Every cell must show an obviously DIAGONAL boundary between magenta-sky and underground material. **No surface material anywhere in this row** — the diagonal is a clean cut between magenta and underground. NO cell in this row is a featureless flat block.
  • Cell (2,1): SLOPE UP 45° — diagonal rises from BOTTOM-LEFT to TOP-RIGHT; magenta fills the UPPER-LEFT triangle, underground fills the LOWER-RIGHT triangle. The diagonal is a clean dirt-to-magenta cut; NO grass/snow/surface cap on the slope.
  • Cell (2,2): SLOPE DOWN 45° — diagonal rises from TOP-LEFT to BOTTOM-RIGHT; magenta fills the UPPER-RIGHT triangle, underground fills the LOWER-LEFT triangle. Clean dirt-to-magenta cut; NO surface cap.
  • Cell (2,3): GENTLE SLOPE UP (left half, ~22.5°) — shallow diagonal rising from bottom-left into the cell's right edge at mid-height; large magenta wedge in the upper-left; underground fills the rest. NO surface cap.
  • Cell (2,4): GENTLE SLOPE UP (right half) — continues from (2,3); diagonal exits the cell's right edge at the top. NO surface cap.
  • Cell (2,5): GENTLE SLOPE DOWN (left half) — diagonal enters the right edge at top, falls toward bottom-right. NO surface cap.
  • Cell (2,6): GENTLE SLOPE DOWN (right half) — completes the descent. NO surface cap.
  • Cell (2,7): SLOPE-UP CAP — a slope meets a flat top going right; diagonal in the left half, flat horizontal underground-to-magenta edge in the right half. All dirt below the boundary; magenta above. NO surface material.
  • Cell (2,8): SLOPE-DOWN CAP — flat horizontal underground-to-magenta edge on the left half, slope on the right half. NO surface material.
  • Cell (2,9): INNER CORNER TOP-LEFT (concave) — magenta is a clean QUARTER-CIRCLE BITE in the TOP-LEFT corner only; underground fills the rest of the cell.
  • Cell (2,10): INNER CORNER TOP-RIGHT (concave) — magenta quarter-circle bite in the TOP-RIGHT corner only.
  • Cell (2,11): INNER CORNER BOTTOM-LEFT (concave) — magenta quarter-circle bite in the BOTTOM-LEFT corner only.
  • Cell (2,12): INNER CORNER BOTTOM-RIGHT (concave) — magenta quarter-circle bite in the BOTTOM-RIGHT corner only.

ROW 3 — SIDE TILES + BOTTOM-EDGE / OUTER (CONVEX) CORNER TILES. Defining feature: VERTICAL or HORIZONTAL CLIFF EDGES with magenta on ONE side only. Every cell shows a clear straight edge between magenta and underground material — NO cell is a featureless block. **No surface material anywhere in this row** — every edge is a direct dirt-to-magenta cut.
  • Cell (3,1): SIDE-LEFT — magenta fills the LEFT third of the cell; underground fills the right two-thirds; the boundary is a clean VERTICAL CLIFF EDGE running top-to-bottom — no grass cap, no surface band.
  • Cell (3,2): SIDE-RIGHT — magenta fills the RIGHT third; underground fills the left two-thirds; clean vertical dirt-to-magenta cut.
  • Cell (3,3): SIDE-LEFT variant — same as (3,1) with subtle dirt texture variation; still no surface material.
  • Cell (3,4): SIDE-RIGHT variant — same as (3,2) with subtle dirt texture variation; still no surface material.
  • Cell (3,5): BOTTOM-LEFT outer corner — magenta fills BOTTOM and LEFT (an L-shape of magenta wrapping the bottom-left); underground fills the upper-right.
  • Cell (3,6): BOTTOM-MIDDLE — magenta fills the BOTTOM third only; cliff bottom-edge (a horizontal underside) runs left-to-right; underground fills the upper two-thirds.
  • Cell (3,7): BOTTOM-MIDDLE variant.
  • Cell (3,8): BOTTOM-RIGHT outer corner — magenta fills BOTTOM and RIGHT.
  • Cell (3,9): OUTER CORNER TOP-LEFT (convex / overhang) — underground exists ONLY in the top-left QUADRANT; the rest of the cell is magenta.
  • Cell (3,10): OUTER CORNER TOP-RIGHT — underground only in top-right quadrant.
  • Cell (3,11): OUTER CORNER BOTTOM-LEFT — underground only in bottom-left quadrant.
  • Cell (3,12): OUTER CORNER BOTTOM-RIGHT — underground only in bottom-right quadrant.

ROW 4 — INTERIOR FILL + FLOATING PLATFORM TILES. Two visually distinct sub-families inside this row. **No surface material anywhere in this row** — every floating platform is a pure dirt island with a flat-or-rounded TOP edge cutting straight against magenta sky; NO grass/snow cap on any platform.
  • Cell (4,1)–(4,4): INTERIOR FILL — solid underground material edge-to-edge, NO magenta anywhere in the cell. Each cell is a subtly different texture variant (different rock cluster / pebble pattern / packed-dirt grain). These are the ONLY cells in the entire sheet that legitimately read as "solid underground block".
  • Cell (4,5): FLOATING PLATFORM LEFT — a self-contained mini-platform of pure underground material; flat dirt TOP edge cutting straight against magenta sky above; underground rounds off into a curved/tapered BOTTOM-LEFT; magenta surrounds the platform on TOP, LEFT and BOTTOM. NO surface cap.
  • Cell (4,6): FLOATING PLATFORM MIDDLE — flat dirt TOP edge, underground sits flat at the BOTTOM, magenta surrounds on TOP and BOTTOM (passes through horizontally to neighbours). NO surface cap.
  • Cell (4,7): FLOATING PLATFORM MIDDLE variant. NO surface cap.
  • Cell (4,8): FLOATING PLATFORM RIGHT — mirror of (4,5); flat dirt TOP, curved/tapered BOTTOM-RIGHT, magenta on TOP, RIGHT and BOTTOM. NO surface cap.
  • Cell (4,9): SINGLE 1-TILE FLOATING PLATFORM — fully self-contained dirt island: magenta on all four sides, flat dirt TOP, rounded underground bottom; reads as one isolated step. NO surface cap.
  • Cell (4,10): 2-TILE FLOATING PLATFORM LEFT — flat dirt TOP, rounded bottom-left, magenta on TOP, LEFT, BOTTOM. NO surface cap.
  • Cell (4,11): 2-TILE FLOATING PLATFORM RIGHT — mirror of (4,10). NO surface cap.
  • Cell (4,12): CLOUD-STYLE FLOATING TILE — softer, more diffuse silhouette but still a clearly bounded dirt platform with magenta surrounding. NO surface cap.

ABSOLUTE REQUIREMENTS (read carefully — the previous attempts failed on these):
  0. **ROW 1 IS THE ONLY ROW WITH SURFACE MATERIAL.** Row 1 cells have a thin grass/snow/sand band capping the dirt. Rows 2, 3 and 4 contain ONLY dirt (underground material) and magenta — NO grass, NO snow cap, NO green band, NO surface stripe anywhere. Slopes, sides, corners and floating platforms in rows 2/3/4 are pure dirt cut against magenta sky.
  1. ROWS MUST READ AS FOUR DIFFERENT FAMILIES. If a verifier looks at the sheet and sees "row 1 has surface tiles" but "rows 2/3/4 all look like one big stone block", the sheet is wrong. Row 2 is dominated by DIAGONALS. Row 3 is dominated by STRAIGHT VERTICAL/HORIZONTAL EDGES with magenta on one side. Row 4 mixes solid fill blocks (left half) with FLOATING PLATFORMS surrounded by magenta (right half).
  2. SLOPES IN ROW 2 MUST ACTUALLY SLOPE. Each slope cell shows a clear diagonal boundary between magenta and underground — not a flat horizontal surface band, not a rectangular block.
  3. CORNERS MUST SHOW CORNERS. Inner-corner cells (concave) show a quarter-circle BITE of magenta in the named corner. Outer-corner cells (convex) show underground material ONLY in the named quadrant, magenta everywhere else in the cell.
  4. SIDES MUST SHOW SIDE EDGES. Side-left / side-right cells have magenta on ONE vertical side only and an obvious vertical cliff face running top-to-bottom in the underground material.
  5. FLOATING PLATFORMS MUST FLOAT. The platform tiles in row 4 are surrounded by magenta on multiple sides — they do not blend into a wall of underground material.
  6. CELL SEPARATOR LINES are visible across the entire sheet (thin dark hairlines at every internal seam). They make each cell a discrete sprite slot.
  7. MATERIAL CONSISTENCY: the SURFACE material (whatever you pick from the style reference) is the SAME across every cell that has surface; the UNDERGROUND material is the SAME across every cell that has underground. Only the SHAPES of the magenta/underground/surface regions change between cells, not the materials.
  8. NO TEXT, no labels, no row numbers, no coordinate captions painted into the output.

Output a single 2400×800 PNG following this contract.`;

export interface TilesetArgs {
  prompt: string;
  tag: string;
  runDir: string;
  model: string;
  conceptImagePath: string;
  wireframePath: string;
}

export async function generateTileset(args: TilesetArgs) {
  const { prompt, tag, runDir, model, conceptImagePath, wireframePath } = args;
  const outPath = join(runDir, `tileset_${tag}.png`);
  return generateImageAsset({
    stage: "tileset",
    userPrompt: prompt,
    promptText: PROMPT,
    refs: [wireframePath, conceptImagePath],
    outPath,
    width: CANVAS_W,
    height: CANVAS_H,
    model,
    extra: {
      grid: { cols: COLS, rows: ROWS, cellW: CELL_W, cellH: CELL_H },
      role_contract: "docs/spec/tileset.md (extended 4-row role families)",
    },
  });
}

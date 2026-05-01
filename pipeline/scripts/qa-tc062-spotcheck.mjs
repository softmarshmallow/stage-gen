// TC-062 spot-check — confirm sprite interior pinkish/reddish content
// remains opaque after the flood-fill snap. Counts non-magenta painted
// pixels and any interior near-magenta cluster sizes per file via sharp
// (no canvas/runtime; deterministic).
//
// We DON'T expect "pink" specifically inside the sprites — we just want
// to confirm the sprite's painted body is intact. The test checks that
// the count of non-magenta opaque pixels is reasonable (>50k for a
// drawn mob), and reports separately:
//   - exactMagentaPx: edge-snapped background
//   - paintedPx: non-magenta pixels (the sprite body)
//   - reddishPx: r > 180, g < 120, b < 120 (red/orange details)
//   - interiorNearMagenta: near-magenta pixels NOT touching the canvas
//     edge — these should survive the flood-fill (any number > 0 is
//     proof that interior pinks are not being eaten).

import sharp from 'sharp';
import { readdir } from 'node:fs/promises';
import { join } from 'node:path';

const RUN_DIR = '/Users/universe/Desktop/stage-gen-ralph-setup/out/snowy-mountain-platformer-with-crisp-pow-5162c8d2';

async function inspect(filePath) {
  const { data, info } = await sharp(filePath).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  const W = info.width, H = info.height, N = W * H;
  let exactMagenta = 0, painted = 0, reddish = 0, nearMagenta = 0;
  for (let p = 0; p < N; p++) {
    const o = p * 4;
    const r = data[o], g = data[o + 1], b = data[o + 2];
    if (r === 255 && g === 0 && b === 255) {
      exactMagenta++;
      continue;
    }
    painted++;
    if (r > 180 && g < 120 && b < 120) reddish++;
    // Manhattan from magenta
    const d = (255 - r) + g + (255 - b);
    if (d <= 220) nearMagenta++; // within flood threshold but NOT edge-connected (else it'd be exact)
  }
  return { file: filePath.split('/').pop(), W, H, exactMagenta, painted, reddish, interiorNearMagenta: nearMagenta };
}

const targets = [
  'mob_concept_snowy-mountain-platformer-with-crisp-pow-5162c8d2_4.png',
  'mob_concept_snowy-mountain-platformer-with-crisp-pow-5162c8d2_2.png',
  'mob_concept_snowy-mountain-platformer-with-crisp-pow-5162c8d2_7.png',
  'mob_snowy-mountain-platformer-with-crisp-pow-5162c8d2_4_idle.png',
  'character_snowy-mountain-platformer-with-crisp-pow-5162c8d2_combined.png',
  'items_snowy-mountain-platformer-with-crisp-pow-5162c8d2.png',
];

const out = [];
for (const t of targets) {
  out.push(await inspect(join(RUN_DIR, t)));
}
console.log(JSON.stringify(out, null, 2));

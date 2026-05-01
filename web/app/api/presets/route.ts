// GET /api/presets — curated preset prompts read from fixtures/prompts.txt.
//
// Lines starting with `#` or blank are skipped. Bullet markers (`- `) are
// stripped so the returned strings are clean prompts the picker can show
// directly.

import { promises as fs } from "node:fs";
import path from "node:path";

export const runtime = "nodejs";

const REPO_ROOT = path.resolve(process.cwd(), "..");
const PROMPTS_PATH = path.join(REPO_ROOT, "fixtures", "prompts.txt");

function parsePrompts(raw: string): string[] {
  const out: string[] = [];
  for (const rawLine of raw.split("\n")) {
    const line = rawLine.trim();
    if (!line) continue;
    if (line.startsWith("#")) continue;
    // Only lines that look like list bullets are real prompts. Any other
    // prose in fixtures/prompts.txt is documentation, not a preset.
    const m = line.match(/^[-*]\s+(.+)$/);
    if (!m) continue;
    const stripped = m[1].trim();
    if (stripped) out.push(stripped);
  }
  return out;
}

export async function GET() {
  try {
    const raw = await fs.readFile(PROMPTS_PATH, "utf8");
    const prompts = parsePrompts(raw);
    return Response.json({ prompts });
  } catch (err) {
    return Response.json(
      { prompts: [], error: err instanceof Error ? err.message : String(err) },
      { status: 500 },
    );
  }
}

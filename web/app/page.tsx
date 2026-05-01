// Picker view (root URL).
//
// Phase 8 / TC-100..103, 113. Server component fetches the curated preset
// list, hands it to a client island for the input + Generate flow.

import { promises as fs } from "node:fs";
import path from "node:path";
import Picker from "./Picker";

export const dynamic = "force-dynamic";

const REPO_ROOT = path.resolve(process.cwd(), "..");
const PROMPTS_PATH = path.join(REPO_ROOT, "fixtures", "prompts.txt");

function parsePrompts(raw: string): string[] {
  const out: string[] = [];
  for (const rawLine of raw.split("\n")) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const m = line.match(/^[-*]\s+(.+)$/);
    if (!m) continue;
    const stripped = m[1].trim();
    if (stripped) out.push(stripped);
  }
  return out;
}

export default async function Home() {
  let presets: string[] = [];
  try {
    const raw = await fs.readFile(PROMPTS_PATH, "utf8");
    presets = parsePrompts(raw);
  } catch {
    // empty preset list still renders the input
  }
  return (
    <main className="sg-page">
      <h1 className="sg-h1">stage-gen</h1>
      <Picker presets={presets} />
    </main>
  );
}

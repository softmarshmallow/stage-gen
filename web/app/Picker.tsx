"use client";

// Picker client island. Owns the prompt input, preset list, and Generate
// button. On Generate it POSTs /api/run and navigates to /generate/<tag>.

import { useRouter } from "next/navigation";
import { useState } from "react";

// Top-6 curated preset chips. Each chip's `label` is the short tag shown
// in the UI; clicking injects `prompt` into the textarea. Picked for visual
// variety across the 30-line fixture (one per major biome/aesthetic).
const CHIPS: { label: string; prompt: string }[] = [
  {
    label: "gothic ruins",
    prompt:
      "I want a moody side-scroll platformer, like Hollow Knight, with rainy gothic ruins, cracked stone arches, and bioluminescent moss glowing pale blue.",
  },
  {
    label: "cozy autumn",
    prompt:
      "I want a cozy autumn village adventure, like Stardew Valley meets a 2D platformer, with thatched-roof cottages, pumpkin patches, falling orange leaves, and warm lantern light.",
  },
  {
    label: "neon cyberpunk",
    prompt:
      "I want a neon cyberpunk side-scroller, like Katana ZERO, with rainy back-alleys, holographic signs in Japanese, puddle reflections, and pink-cyan rim lighting.",
  },
  {
    label: "snowy peaks",
    prompt:
      "I want a snowy mountain platformer, like Celeste, with crisp powder, pine forests on distant peaks, frozen lakes, and faint aurora in the sky.",
  },
  {
    label: "desert tombs",
    prompt:
      "I want a desert dungeon-crawler side-view, like Crypt of the NecroDancer, with sandstone tombs, half-buried obelisks, scorpions in the foreground, and a heat-hazed horizon.",
  },
  {
    label: "deep sea",
    prompt:
      "I want a deep-sea exploration platformer, like Aquaria, with kelp forests, glowing jellyfish drifting in the back, sunken stone columns, and god rays from above.",
  },
];

export default function Picker(_props: { presets: string[] }) {
  const router = useRouter();
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trimmed = prompt.trim();
  const canSubmit = !busy && trimmed.length > 0;

  async function onGenerate() {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/run", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ prompt: trimmed }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error ?? `HTTP ${res.status}`);
      }
      const data = (await res.json()) as { tag: string };
      router.push(`/generate/${data.tag}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <div style={{ color: "var(--dim)", marginBottom: 4 }}>prompt:</div>
        <textarea
          className="sg-textarea"
          aria-label="world prompt"
          placeholder="describe a world…"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          autoFocus
        />
      </div>

      <div style={{ marginBottom: 16 }}>
        <div style={{ color: "var(--dim)", marginBottom: 6 }}>presets:</div>
        <div className="sg-chips">
          {CHIPS.map((c) => (
            <button
              key={c.label}
              type="button"
              className="sg-chip"
              onClick={() => setPrompt(c.prompt)}
              title={c.prompt}
            >
              #{c.label}
            </button>
          ))}
        </div>
      </div>

      {error ? (
        <div className="sg-error-banner" role="alert">
          {error}
        </div>
      ) : null}

      <div style={{ textAlign: "right", marginTop: 16 }}>
        <button
          type="button"
          className="sg-btn"
          disabled={!canSubmit}
          onClick={onGenerate}
        >
          [ {busy ? "starting…" : "generate"} ]
        </button>
      </div>
    </div>
  );
}

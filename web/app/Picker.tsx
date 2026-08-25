"use client";

// Picker client island. Owns the prompt input, preset list, and Generate
// button. On Generate it POSTs /api/run and navigates to /generate/<tag>.

import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  DEFAULT_TRANSPARENCY_MODE,
  modeForAiBackgroundRemoval,
} from "@/lib/shell/transparency";

// Neutral, repository-authored prompts for the scrolling-preview recipe.
// They intentionally avoid named properties, creators, studios, and styles.
const CHIPS: { label: string; prompt: string }[] = [
  {
    label: "rain ruins",
    prompt:
      "Create an original side-view scrolling-game asset set for rain-dark stone ruins, with broken arches, pale bioluminescent moss, layered mist, and a restrained blue-gray palette.",
  },
  {
    label: "harvest village",
    prompt:
      "Create an original side-view scrolling-game asset set for an autumn farming village, with timber cottages, squash gardens, drifting copper leaves, and warm lantern light.",
  },
  {
    label: "neon transit",
    prompt:
      "Create an original side-view scrolling-game asset set for a rain-soaked future transit district, with geometric light panels, puddle reflections, service tunnels, and cyan-magenta rim light without logos or text.",
  },
  {
    label: "alpine dusk",
    prompt:
      "Create an original side-view scrolling-game asset set for an alpine route at dusk, with crisp snow, distant conifer ridges, frozen ponds, and a faint green aurora.",
  },
  {
    label: "desert vault",
    prompt:
      "Create an original side-view scrolling-game asset set for a buried desert observatory, with weathered sandstone chambers, abstract stone markers, small desert creatures, and a heat-softened horizon.",
  },
  {
    label: "abyssal reef",
    prompt:
      "Create an original side-view scrolling-game asset set for a deep-ocean reef, with kelp silhouettes, luminous drifting creatures, eroded mineral columns, and narrow shafts of light from above.",
  },
];

export default function Picker(_props: { presets: string[] }) {
  const router = useRouter();
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aiBackgroundRemoval, setAiBackgroundRemoval] = useState(
    DEFAULT_TRANSPARENCY_MODE === "ai",
  );

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
        body: JSON.stringify({
          prompt: trimmed,
          transparency_mode: modeForAiBackgroundRemoval(aiBackgroundRemoval),
        }),
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
        <div style={{ color: "var(--dim)", marginBottom: 4 }}>
          scrolling-preview recipe prompt:
        </div>
        <textarea
          className="sg-textarea"
          aria-label="scrolling preview asset prompt"
          placeholder="describe an original side-view asset set…"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          autoFocus
        />
      </div>

      <label
        style={{
          display: "flex",
          alignItems: "flex-start",
          gap: 8,
          marginBottom: 16,
          color: "var(--fg)",
          cursor: busy ? "default" : "pointer",
        }}
      >
        <input
          type="checkbox"
          checked={aiBackgroundRemoval}
          disabled={busy}
          onChange={(event) => setAiBackgroundRemoval(event.target.checked)}
          aria-label="AI background removal"
        />
        <span>
          <span>AI background removal: {aiBackgroundRemoval ? "on" : "off"}</span>
          <span style={{ display: "block", color: "var(--dim)", marginTop: 2 }}>
            {aiBackgroundRemoval
              ? "default; requires server-side FAL_KEY and fails closed if removal is unavailable"
              : "explicit degraded chroma fallback; no background-removal call"}
          </span>
        </span>
      </label>

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

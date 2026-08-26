"use client";

// Picker client island. Owns the prompt input, preset list, and Generate
// button. On Generate it POSTs /api/run and navigates to /generate/<tag>.

import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  DEFAULT_TRANSPARENCY_MODE,
  type TransparencyMode,
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
  const [transparencyMode, setTransparencyMode] = useState<TransparencyMode>(
    DEFAULT_TRANSPARENCY_MODE,
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
          transparency_mode: transparencyMode,
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

      <label style={{ display: "block", marginBottom: 16, color: "var(--fg)" }}>
        <span style={{ display: "block", marginBottom: 4 }}>transparency strategy:</span>
        <select
          value={transparencyMode}
          disabled={busy}
          onChange={(event) => setTransparencyMode(event.target.value as TransparencyMode)}
          aria-label="Transparency strategy"
        >
          <option value="native">Native alpha — best quality</option>
          <option value="ai">AI background removal — compatibility fallback</option>
          <option value="chroma">Chroma key — degraded local fallback</option>
        </select>
        <span style={{ display: "block", color: "var(--dim)", marginTop: 4 }}>
          {transparencyMode === "native"
            ? "default; the image model creates alpha directly, preserving edge detail"
            : transparencyMode === "ai"
              ? "generates opaque art, then uses server-side FAL background removal"
              : "generates a keyed background and removes it locally"}
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

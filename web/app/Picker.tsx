"use client";

// Picker client island. Owns the prompt input, preset list, and Generate
// button. On Generate it POSTs /api/run and navigates to /generate/<tag>.

import { useRouter } from "next/navigation";
import { useState } from "react";

export default function Picker({ presets }: { presets: string[] }) {
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
        <div style={{ color: "var(--dim)", marginBottom: 4 }}>presets:</div>
        <div>
          {presets.length === 0 ? (
            <div style={{ color: "var(--dim)" }}>no presets available</div>
          ) : (
            presets.map((p) => (
              <button
                key={p}
                type="button"
                className="sg-btn-preset"
                onClick={() => setPrompt(p)}
              >
                [ {p} ]
              </button>
            ))
          )}
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

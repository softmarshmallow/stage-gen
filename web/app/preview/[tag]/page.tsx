import Link from "next/link";
import { notFound } from "next/navigation";
import {
  isPreparedRuntimeRun,
  isSafeRunTag,
  readRunInput,
} from "@/lib/shell/runs";
import {
  previewPolicyForRunMode,
  transparencyModeLabel,
} from "@/lib/shell/transparency";
import {
  GameplayAutomationRequestError,
  resolveGameplayAutomationMode,
} from "@/lib/runtime/automation";
import PreviewCanvas from "./PreviewCanvas";

// Optional per-run consumer for the scrolling-world recipe. This page is a
// preview adapter, not the core pipeline or a committed production runtime.
export default async function PreviewPage({
  params,
  searchParams,
}: {
  params: Promise<{ tag: string }>;
  searchParams: Promise<{ automation?: string | string[] }>;
}) {
  const { tag } = await params;
  if (!isSafeRunTag(tag)) notFound();
  const query = await searchParams;
  let automationMode;
  try {
    automationMode = resolveGameplayAutomationMode(
      query.automation,
      process.env.STAGE_GEN_GAMEPLAY_AUTOMATION,
    );
  } catch (error) {
    if (error instanceof GameplayAutomationRequestError) notFound();
    throw error;
  }
  const input = await readRunInput(tag);
  const prepared = await isPreparedRuntimeRun(tag);
  const transparencyMode = input?.transparencyMode ?? (prepared ? "native" : null);
  const policy = previewPolicyForRunMode(transparencyMode);
  if (automationMode) {
    // A capture records one published run. The override is dropped here as well as inside
    // `bootPreparedGame`, so neither the shell nor the scene can be the one place it leaks.
    return (
      <main
        data-testid="gameplay-canvas-only-shell"
        style={{ width: 1280, height: 720, margin: 0, padding: 0, overflow: "hidden" }}
      >
        <PreviewCanvas
          tag={tag}
          transparencyPolicy={policy}
          automationMode={automationMode}
        />
      </main>
    );
  }
  return (
    <main style={{ padding: 0, margin: 0, background: "#0a0a0a" }}>
      <div
        style={{
          padding: "8px 16px",
          color: "#666",
          fontSize: 12,
          display: "flex",
          gap: 16,
          alignItems: "center",
        }}
      >
        <Link
          href={`/generate/${tag}`}
          style={{ color: "#e6e6e6", textDecoration: "none" }}
        >
          [ ◂ back ]
        </Link>
        <span>
          stage-gen / optional scrolling preview /{" "}
          <span style={{ color: "#e6e6e6" }}>{tag}</span>
        </span>
        <span data-testid="preview-transparency-mode">
          transparency:{" "}
          <span style={{ color: "#e6e6e6" }}>
            {transparencyModeLabel(transparencyMode)}
          </span>
        </span>
      </div>
      <PreviewCanvas
        tag={tag}
        transparencyPolicy={policy}
        automationMode={automationMode}
      />
    </main>
  );
}

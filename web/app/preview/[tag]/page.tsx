import Link from "next/link";
import { notFound } from "next/navigation";
import { isPreparedRuntimeRun, isSafeRunTag } from "@/lib/shell/runs";
import { previewPolicyForRunMode } from "@/lib/shell/transparency";
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
  const prepared = await isPreparedRuntimeRun(tag);
  if (!prepared) notFound();
  const policy = previewPolicyForRunMode(prepared);
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
    <main className="bg-bg">
      <div className="flex items-center gap-4 px-4 py-2 text-xs text-dim">
        <Link href="/" className="text-fg no-underline">
          [ ◂ back ]
        </Link>
        <span>
          stage-gen / optional scrolling preview /{" "}
          <span className="text-fg">{tag}</span>
        </span>
        <span data-testid="preview-transparency-mode">
          transparency: <span className="text-fg">canonical alpha</span>
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

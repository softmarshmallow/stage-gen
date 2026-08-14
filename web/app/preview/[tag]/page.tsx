import Link from "next/link";
import { notFound } from "next/navigation";
import { isSafeRunTag, readRunInput } from "@/lib/shell/runs";
import {
  previewPolicyForRunMode,
  transparencyModeLabel,
} from "@/lib/shell/transparency";
import PreviewCanvas from "./PreviewCanvas";

// Optional per-run consumer for the scrolling-world recipe. This page is a
// preview adapter, not the core pipeline or a committed production runtime.
export default async function PreviewPage({
  params,
}: {
  params: Promise<{ tag: string }>;
}) {
  const { tag } = await params;
  if (!isSafeRunTag(tag)) notFound();
  const input = await readRunInput(tag);
  const policy = previewPolicyForRunMode(input?.transparencyMode ?? null);
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
            {transparencyModeLabel(input?.transparencyMode ?? null)}
          </span>
        </span>
      </div>
      <PreviewCanvas tag={tag} transparencyPolicy={policy} />
    </main>
  );
}

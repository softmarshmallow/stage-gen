import { describe, expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import { parseRunnerRuntimeManifest } from "@/lib/sideview-runner/contract";
import { runnerManifestFixture } from "@/lib/sideview-runner/fixture";
import RunnerPlayer from "./RunnerPlayer";

describe("RunnerPlayer control copy", () => {
  test("advertises slide only when the manifest and avatar support it", () => {
    const sliding = parseRunnerRuntimeManifest(runnerManifestFixture());
    const slidingMarkup = renderToStaticMarkup(
      <RunnerPlayer tag="sliding" manifest={sliding} />,
    );
    expect(slidingMarkup).toContain("Arrow Down to slide");
    expect(slidingMarkup).toContain("Hold lower screen / ↓ · Slide");

    const document = runnerManifestFixture();
    const gameplay = document.gameplay as Record<string, unknown>;
    gameplay.duck_profile = null;
    gameplay.ducked_height_fraction = null;
    gameplay.min_overhead_clearance_rows = null;
    const avatar = document.avatar as { motions: Record<string, unknown>[] };
    avatar.motions = avatar.motions.filter((motion) => motion.state !== "slide");
    const jumping = parseRunnerRuntimeManifest(document);
    const jumpingMarkup = renderToStaticMarkup(
      <RunnerPlayer tag="jumping" manifest={jumping} />,
    );

    expect(jumpingMarkup).toContain("Tap the screen or press Space to jump");
    expect(jumpingMarkup).not.toContain("Arrow Down");
    expect(jumpingMarkup).not.toContain("Slide");
  });
});

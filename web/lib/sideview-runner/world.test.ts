import { describe, expect, test } from "bun:test";
import { parseRunnerRuntimeManifest } from "./contract";
import { runnerManifestFixture } from "./fixture";
import {
  cameraScrollX,
  createRunnerWorld,
  groundLineY,
  resetRunnerWorld,
  rowToScreenY,
  RUNNER_VIEW_HEIGHT,
  runnerWorldConfig,
} from "./world";

const manifest = parseRunnerRuntimeManifest(runnerManifestFixture());

describe("createRunnerWorld", () => {
  test("primes a streamed window the avatar can stand on immediately", () => {
    const world = createRunnerWorld(manifest, 99);
    expect(world.segments.chunks.length).toBeGreaterThan(0);
    expect(world.segments.nextColumn).toBeGreaterThan(
      world.avatar.distanceColumns + world.config.streamAheadColumns,
    );
    expect(world.avatar.grounded).toBe(true);
    expect(world.avatar.y).toBe(manifest.segments.walkSurfaceRow);
    expect(world.run.phase).toBe("running");
  });

  test("the same seed streams the same track", () => {
    const first = createRunnerWorld(manifest, 7);
    const second = createRunnerWorld(manifest, 7);
    expect(first.segments.chunks.map((chunk) => chunk.segmentId)).toEqual(
      second.segments.chunks.map((chunk) => chunk.segmentId),
    );
  });

  test("resetRunnerWorld rebuilds the dynamic halves in place", () => {
    const world = createRunnerWorld(manifest, 5);
    world.score.total = 120;
    world.run.phase = "dead";
    world.avatar.distanceColumns = 400;
    world.obstacles.collected.add("40:2:sunleaf_token");
    resetRunnerWorld(world, 6);
    // Widened read: TS control-flow narrowing cannot see the in-place reset.
    expect(world.run.phase as string).toBe("running");
    // The scorer owns its own slice and its own reset; `resetRunnerWorld`
    // deliberately leaves it alone so that one slice has one author.
    expect(world.score.total).toBe(120);
    expect(world.run.seed).toBe(6);
    expect(world.avatar.distanceColumns).toBe(2);
    expect(world.obstacles.collected.size).toBe(0);
    expect(world.segments.chunks[0].startColumn).toBe(0);
  });
});

describe("world geometry", () => {
  const config = runnerWorldConfig(manifest);

  test("floor_to_screen_bottom pins the deepest row to the canvas bottom", () => {
    expect(rowToScreenY(config.rows, config)).toBe(RUNNER_VIEW_HEIGHT);
    expect(groundLineY(config)).toBe(
      RUNNER_VIEW_HEIGHT - (config.rows - config.walkSurfaceRow) * config.tilePx,
    );
  });

  test("camera scroll pins the avatar to its screen anchor", () => {
    const scroll = cameraScrollX(10, config);
    expect(10 * config.tilePx - scroll).toBe(config.avatarScreenX);
  });

  test("config carries the prop magnitudes for collision", () => {
    expect(config.propHeightUnits.get("toppled_cart")).toBe(1);
  });
});

describe("the intro moment", () => {
  test("is read off the fx block's stage_start binding and born once per boot", async () => {
    const { fxBlockFixture } = await import("@/lib/manifest/fx");
    const document = runnerManifestFixture();
    document.fx = fxBlockFixture();
    const withFx = parseRunnerRuntimeManifest(document);
    expect(runnerWorldConfig(withFx).introMoment?.portraitId).toBe("stage_start");
    const world = createRunnerWorld(withFx, 7);
    expect(world.run.phase).toBe("intro");
    expect(world.fx?.startedAt).toBeNull();
    resetRunnerWorld(world, 8, { intro: false });
    expect(world.run.phase).toBe("running");
    expect(world.fx).toBeNull();
    const silent = createRunnerWorld(withFx, 7, { intro: false });
    expect(silent.run.phase).toBe("running");
  });

  test("the avatar and obstacles hold during the intro", async () => {
    const { fxBlockFixture } = await import("@/lib/manifest/fx");
    const { stepAvatar } = await import("./avatar");
    const document = runnerManifestFixture();
    document.fx = fxBlockFixture();
    const world = createRunnerWorld(parseRunnerRuntimeManifest(document), 7);
    const before = world.avatar.distanceColumns;
    stepAvatar(world, 1 / 60);
    expect(world.avatar.distanceColumns).toBe(before);
  });
});

import { describe, expect, test } from "bun:test";
import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import {
  DEFAULT_RECORDING_OPTIONS,
  GAMEPLAY_RECORDER_BUILD_ARGV,
  GAMEPLAY_RECORDING_SCHEMA_VERSION,
  assertPortableFixtureEntries,
  assertPortableRecordingMetadata,
  createCanonicalRecorderWorkspace,
  groupGameplayEventFrames,
  installRecorderCaptureAfterFinalCheck,
  parseGameplayRecorderArgs,
  recorderMediaCommands,
  readBoundedRecorderInput,
  resolveGameplayReportPaths,
  sanitizeRecorderDiagnostic,
  snapshotRecorderFixture,
  validateRecorderTimeline,
  validateRecordingMp4Probe,
} from "../../scripts/gameplay/recorder";
import {
  GAMEPLAY_BUILD_SOURCE_DIRECTORIES,
  GAMEPLAY_BUILD_SOURCE_FILES,
  assertCanonicalSnapshotsEqual,
  snapshotGameplayBuildInputs,
  snapshotRecorderImplementationTree,
  snapshotServedNextBuild,
  validateRecorderDependencies,
} from "../../scripts/gameplay/build-binding";
import {
  bindCaptureDirectoryIdentity,
  installCaptureFiles,
} from "./harness";

const CUSTOM_SOURCE_ARGS = [
  "--fixture",
  "out/shareable-demo",
  "--tag",
  "shareable-demo",
  "--timeline",
  "fixtures/gameplay/custom-timeline.json",
] as const;

function validTimeline() {
  return {
    schemaVersion: 1,
    simulationFps: 30,
    frames: [
      {
        index: 0,
        actions: [{ type: "down", key: "ArrowRight" }],
      },
      { index: 1, actions: [] },
      {
        index: 2,
        actions: [{ type: "up", key: "ArrowRight" }],
      },
    ],
  };
}

function validProbe() {
  return {
    format: {
      format_name: "mov,mp4,m4a,3gp,3g2,mj2",
      duration: "5.000000",
      size: "2000000",
    },
    streams: [
      {
        index: 0,
        codec_type: "video",
        codec_name: "h264",
        pix_fmt: "yuv420p",
        width: 640,
        height: 360,
        avg_frame_rate: "24/1",
        r_frame_rate: "24/1",
        duration: "5.000000",
        nb_frames: "120",
        nb_read_frames: "120",
      },
    ],
  };
}

const EXPECTED_PROBE = {
  width: 640,
  height: 360,
  fps: 24,
  durationSeconds: 5,
  frameCount: 120,
  maxBytes: 3_000_000,
} as const;

async function makeSyntheticBuildInputRoot(label: string): Promise<string> {
  const root = await fs.mkdtemp(path.join(tmpdir(), `stage-gen-${label}-`));
  for (const directory of GAMEPLAY_BUILD_SOURCE_DIRECTORIES) {
    const target = path.join(root, ...directory.split("/"));
    await fs.mkdir(target, { recursive: true });
    await fs.writeFile(path.join(target, "bound.txt"), `${directory}\n`);
  }
  for (const file of GAMEPLAY_BUILD_SOURCE_FILES) {
    await fs.writeFile(path.join(root, file), `${file}\n`);
  }
  const runtime = path.join(root, "lib", "runtime");
  await fs.mkdir(runtime);
  await fs.writeFile(path.join(runtime, "vertical.ts"), "frozen vertical\n");
  return root;
}

describe("reusable gameplay recorder options", () => {
  test("has a safe deterministic 30-second model-demo default", () => {
    expect(DEFAULT_RECORDING_OPTIONS).toEqual({
      mode: "record",
      output: "output/playwright/gameplay-report.mp4",
      durationSeconds: 30,
      fps: 30,
      width: 1280,
      height: 720,
      posterFrame: 35,
      verifyTwice: true,
      timeoutMs: 600_000,
      source: { kind: "model-demo" },
    });
    expect(parseGameplayRecorderArgs([])).toEqual(DEFAULT_RECORDING_OPTIONS);
  });

  test("recursively binds every production and gameplay source root", async () => {
    const webRoot = path.resolve(import.meta.dir, "../..");
    const snapshot = await snapshotGameplayBuildInputs(webRoot);
    for (const directory of GAMEPLAY_BUILD_SOURCE_DIRECTORIES) {
      expect(
        snapshot.files.some((file) => file.name.startsWith(`${directory}/`)),
      ).toBe(true);
    }
    for (const file of GAMEPLAY_BUILD_SOURCE_FILES) {
      expect(snapshot.files.some((entry) => entry.name === file)).toBe(true);
    }
    for (const formerlyOmitted of [
      "app/preview/[tag]/PreviewCanvas.tsx",
      "app/api/assets/[tag]/[...path]/route.ts",
      "lib/runtime/automation.ts",
      "lib/runtime/assets.ts",
      "lib/runtime/heightmap.ts",
      "lib/runtime/image-ops.ts",
      "tests/gameplay/contracts.ts",
      "next.config.mjs",
    ]) {
      expect(snapshot.files.some((file) => file.name === formerlyOmitted)).toBe(
        true,
      );
    }
  });

  test("accepts bounded custom dimensions, timing, output, and source trio", () => {
    expect(
      parseGameplayRecorderArgs([
        "--output",
        "output/playwright/custom-report-2.mp4",
        "--duration",
        "5",
        "--fps",
        "24",
        "--width",
        "640",
        "--height",
        "360",
        "--poster-frame",
        "17",
        "--timeout-ms",
        "120000",
        "--no-verify-twice",
        "--dry-run",
        ...CUSTOM_SOURCE_ARGS,
      ]),
    ).toEqual({
      mode: "dry-run",
      output: "output/playwright/custom-report-2.mp4",
      durationSeconds: 5,
      fps: 24,
      width: 640,
      height: 360,
      posterFrame: 17,
      verifyTwice: false,
      timeoutMs: 120_000,
      source: {
        kind: "fixture",
        fixture: "out/shareable-demo",
        tag: "shareable-demo",
        timeline: "fixtures/gameplay/custom-timeline.json",
      },
    });
  });

  test("confines reports to portable MP4 paths below output/playwright", () => {
    const paths = resolveGameplayReportPaths(
      "output/playwright/team/demo/custom-report-2.mp4",
    );
    expect(paths.relativeVideo).toBe(
      "output/playwright/team/demo/custom-report-2.mp4",
    );
    expect(paths.relativePoster).toMatch(
      /^output\/playwright\/team\/demo\/custom-report-2(?:\.poster)?\.png$/,
    );
    expect(paths.relativeMetadata).toMatch(
      /^output\/playwright\/team\/demo\/custom-report-2(?:\.recording|\.report|\.mp4\.meta)?\.json$/,
    );
    for (const absolute of [paths.video, paths.poster, paths.metadata]) {
      expect(path.isAbsolute(absolute)).toBe(true);
    }

    for (const unsafe of [
      "/tmp/report.mp4",
      "C:\\tmp\\report.mp4",
      "docs/media/report.mp4",
      "output/playwright/../report.mp4",
      "output/playwright/./report.mp4",
      "output\\playwright\\report.mp4",
      "output/playwright/report.mov",
      "output/playwright/report.MP4",
      "output/playwright/.mp4",
    ]) {
      expect(() => resolveGameplayReportPaths(unsafe)).toThrow();
      expect(() =>
        parseGameplayRecorderArgs(["--output", unsafe]),
      ).toThrow();
    }
  });

  test("allows safe nested lowercase components and rejects nonportable ones", () => {
    expect(
      resolveGameplayReportPaths(
        "output/playwright/team-7/session-02/report-01.mp4",
      ).relativeVideo,
    ).toBe("output/playwright/team-7/session-02/report-01.mp4");

    for (const unsafe of [
      "output/playwright/Team/report.mp4",
      "output/playwright/team/Report.mp4",
      "output/playwright/.hidden/report.mp4",
      "output/playwright/team name/report.mp4",
      "output/playwright/café/report.mp4",
      "output/playwright/team\u0001/report.mp4",
    ]) {
      expect(() => resolveGameplayReportPaths(unsafe)).toThrow();
      expect(() =>
        parseGameplayRecorderArgs(["--output", unsafe]),
      ).toThrow();
    }
  });

  test("requires either the model preset or all three custom-source flags", () => {
    expect(parseGameplayRecorderArgs(["--preset", "model-demo"]).source).toEqual(
      { kind: "model-demo" },
    );
    expect(() =>
      parseGameplayRecorderArgs(["--preset", "unknown"]),
    ).toThrow();
    expect(() =>
      parseGameplayRecorderArgs(["--preset", "model-demo", ...CUSTOM_SOURCE_ARGS]),
    ).toThrow();

    for (const incomplete of [
      ["--fixture", "out/shareable-demo"],
      ["--tag", "shareable-demo"],
      ["--timeline", "fixtures/gameplay/custom-timeline.json"],
      [
        "--fixture",
        "out/shareable-demo",
        "--tag",
        "shareable-demo",
      ],
    ]) {
      expect(() => parseGameplayRecorderArgs(incomplete)).toThrow();
    }
  });

  test("rejects ambiguous, malformed, odd, or out-of-range numeric options", () => {
    const invalid: ReadonlyArray<readonly string[]> = [
      ["--duration", "0"],
      ["--duration", "30junk"],
      ["--duration", "1.01", "--fps", "30"],
      ["--fps", "0"],
      ["--fps", "30.5"],
      ["--fps", "61"],
      ["--width", "321"],
      ["--width", "318"],
      ["--width", "0"],
      ["--height", "181"],
      ["--height", "178"],
      ["--height", "0"],
      ["--poster-frame", "-1"],
      ["--duration", "1", "--fps", "24", "--poster-frame", "31"],
      ["--timeout-ms", "0"],
      ["--timeout-ms", "1e5"],
      ["--duration"],
      ["--unknown"],
      ["--dry-run", "--dry-run"],
    ];
    for (const args of invalid) {
      expect(() => parseGameplayRecorderArgs([...args])).toThrow();
    }
  });
});

describe("reusable gameplay recorder contracts", () => {
  test("accepts a complete, ordered, balanced real-key timeline", () => {
    expect(() => validateRecorderTimeline(validTimeline(), 3)).not.toThrow();
  });

  test("accepts balanced horizontal and vertical traversal keys", () => {
    const vertical = {
      schemaVersion: 1,
      simulationFps: 30,
      frames: [
        { index: 0, actions: [{ type: "down", key: "ArrowUp" }] },
        {
          index: 1,
          actions: [
            { type: "up", key: "ArrowUp" },
            { type: "down", key: "ArrowDown" },
            { type: "down", key: "ArrowLeft" },
          ],
        },
        {
          index: 2,
          actions: [
            { type: "up", key: "ArrowDown" },
            { type: "up", key: "ArrowLeft" },
          ],
        },
      ],
    };
    expect(
      validateRecorderTimeline(vertical, 3).flatMap((frame) =>
        frame.actions.map((action) => `${action.type}:${action.key}`),
      ),
    ).toEqual([
      "down:ArrowUp",
      "up:ArrowUp",
      "down:ArrowDown",
      "down:ArrowLeft",
      "up:ArrowDown",
      "up:ArrowLeft",
    ]);

    const unbalanced = structuredClone(vertical);
    unbalanced.frames[2]!.actions = [
      { type: "up", key: "ArrowLeft" },
    ];
    expect(() => validateRecorderTimeline(unbalanced, 3)).toThrow(
      "leaves keys pressed: ArrowDown",
    );
    const invalid = structuredClone(vertical);
    invalid.frames[0]!.actions[0]!.key = "Escape";
    expect(() => validateRecorderTimeline(invalid, 3)).toThrow("invalid action");
  });

  test("rejects malformed timelines and invalid or unbalanced actions", () => {
    const cases: unknown[] = [
      null,
      { ...validTimeline(), schemaVersion: 2 },
      { ...validTimeline(), simulationFps: 60 },
      { ...validTimeline(), frames: validTimeline().frames.slice(0, 2) },
      {
        ...validTimeline(),
        frames: validTimeline().frames.map((frame, index) => ({
          ...frame,
          index: index === 1 ? 0 : frame.index,
        })),
      },
      {
        ...validTimeline(),
        frames: [
          { index: 0, actions: [{ type: "press", key: "ArrowRight" }] },
          { index: 1, actions: [] },
          { index: 2, actions: [] },
        ],
      },
      {
        ...validTimeline(),
        frames: [
          { index: 0, actions: [{ type: "down", key: "Escape" }] },
          { index: 1, actions: [] },
          { index: 2, actions: [{ type: "up", key: "Escape" }] },
        ],
      },
      {
        ...validTimeline(),
        frames: [
          { index: 0, actions: [{ type: "up", key: "ArrowRight" }] },
          { index: 1, actions: [] },
          { index: 2, actions: [] },
        ],
      },
      {
        ...validTimeline(),
        frames: [
          { index: 0, actions: [{ type: "down", key: "ArrowRight" }] },
          { index: 1, actions: [] },
          { index: 2, actions: [] },
        ],
      },
    ];
    for (const value of cases) {
      expect(() => validateRecorderTimeline(value, 3)).toThrow();
    }
  });

  test("requires one exact H.264 video stream and exact recording metrics", () => {
    expect(
      validateRecordingMp4Probe(validProbe(), EXPECTED_PROBE),
    ).toMatchObject({
      container: "mp4",
      video_codec: "h264",
      pixel_format: "yuv420p",
      width: 640,
      height: 360,
      frame_rate: 24,
      real_frame_rate: 24,
      frame_count: 120,
      duration_seconds: 5,
      size_bytes: 2_000_000,
    });

    const mutations: unknown[] = [
      { ...validProbe(), streams: [] },
      { ...validProbe(), streams: [...validProbe().streams, validProbe().streams[0]] },
      {
        ...validProbe(),
        streams: [
          ...validProbe().streams,
          { codec_type: "audio", codec_name: "aac" },
        ],
      },
      {
        ...validProbe(),
        streams: [
          ...validProbe().streams,
          { codec_type: "subtitle", codec_name: "mov_text" },
        ],
      },
      {
        ...validProbe(),
        streams: [{ ...validProbe().streams[0], codec_name: "hevc" }],
      },
      {
        ...validProbe(),
        streams: [{ ...validProbe().streams[0], pix_fmt: "yuv444p" }],
      },
      {
        ...validProbe(),
        streams: [{ ...validProbe().streams[0], width: 638 }],
      },
      {
        ...validProbe(),
        streams: [{ ...validProbe().streams[0], avg_frame_rate: "25/1" }],
      },
      {
        ...validProbe(),
        streams: [{ ...validProbe().streams[0], r_frame_rate: "25/1" }],
      },
      {
        ...validProbe(),
        streams: [
          {
            ...validProbe().streams[0],
            nb_frames: "119",
            nb_read_frames: "119",
          },
        ],
      },
      {
        ...validProbe(),
        format: { ...validProbe().format, duration: "4.999999" },
      },
      {
        ...validProbe(),
        format: { ...validProbe().format, size: "3000001" },
      },
      {
        ...validProbe(),
        format: { ...validProbe().format, size: "2000000junk" },
      },
      {
        ...validProbe(),
        format: { ...validProbe().format, size: "2000000.0" },
      },
      {
        ...validProbe(),
        format: { ...validProbe().format, size: "2e6" },
      },
      {
        ...validProbe(),
        streams: [{ ...validProbe().streams[0], nb_frames: "120.0" }],
      },
      {
        ...validProbe(),
        streams: [{ ...validProbe().streams[0], nb_read_frames: "+120" }],
      },
      {
        ...validProbe(),
        streams: [{ ...validProbe().streams[0], nb_read_frames: "0120" }],
      },
      {
        ...validProbe(),
        streams: [{ ...validProbe().streams[0], nb_read_frames: true }],
      },
    ];
    for (const value of mutations) {
      expect(() =>
        validateRecordingMp4Probe(value, EXPECTED_PROBE),
      ).toThrow();
    }
  });

  test("independently verifies counted frames and stream duration", () => {
    expect(() =>
      validateRecordingMp4Probe(
        {
          ...validProbe(),
          streams: [
            { ...validProbe().streams[0], nb_read_frames: "119" },
          ],
        },
        EXPECTED_PROBE,
      ),
    ).toThrow();
    expect(() =>
      validateRecordingMp4Probe(
        {
          ...validProbe(),
          streams: [
            { ...validProbe().streams[0], duration: "4.999999" },
          ],
        },
        EXPECTED_PROBE,
      ),
    ).toThrow();
  });

  test("does not begin a capture transaction for an already-aborted signal", async () => {
    const root = await fs.mkdtemp(
      path.join(tmpdir(), "stage-gen-aborted-recorder-test-"),
    );
    try {
      const targets = ["video.mp4", "poster.png", "recording.json"].map(
        (name) => path.join(root, name),
      );
      const previous = targets.map((_, index) =>
        Buffer.from(`previous-${index}`),
      );
      await Promise.all(
        targets.map((target, index) => fs.writeFile(target, previous[index]!)),
      );
      const controller = new AbortController();
      controller.abort(new Error("test cancellation"));

      await expect(
        installCaptureFiles(
          targets.map((target, index) => ({
            target,
            bytes: Buffer.from(`replacement-${index}`),
          })),
          { signal: controller.signal },
        ),
      ).rejects.toThrow("cancelled");

      expect(await Promise.all(targets.map((target) => fs.readFile(target)))).toEqual(
        previous,
      );
      expect(
        (await fs.readdir(root)).filter((name) =>
          name.startsWith(".stage-gen-capture-install-"),
        ),
      ).toEqual([]);
    } finally {
      await fs.rm(root, { recursive: true, force: true });
    }
  });

  test("rejects a repository input reached through an inside-root symlink parent", async () => {
    const root = await fs.mkdtemp(
      path.join(tmpdir(), "stage-gen-recorder-input-test-"),
    );
    try {
      const realParent = path.join(root, "real-parent");
      await fs.mkdir(realParent);
      await fs.writeFile(path.join(realParent, "timeline.json"), "{}\n");
      await fs.symlink(realParent, path.join(root, "alias-parent"), "dir");

      await expect(
        readBoundedRecorderInput(root, "alias-parent/timeline.json", 1_024),
      ).rejects.toThrow("symlinked path components");
      expect(
        await readBoundedRecorderInput(root, "real-parent/timeline.json", 1_024),
      ).toEqual(Buffer.from("{}\n"));
    } finally {
      await fs.rm(root, { recursive: true, force: true });
    }
  });

  test("snapshots the model preset including exact nested ladder provenance", async () => {
    const repositoryRoot = path.resolve(import.meta.dir, "../../..");
    const first = await snapshotRecorderFixture(
      repositoryRoot,
      "fixtures/gameplay-demo",
    );
    const second = await snapshotRecorderFixture(
      repositoryRoot,
      "fixtures/gameplay-demo",
    );
    expect(second).toEqual(first);
    expect(first.files.map((file) => file.name)).toEqual(
      first.files.map((file) => file.name).toSorted(),
    );
    expect(
      first.files.find(
        (file) => file.name === "sources/ladder/generation.json",
      ),
    ).toEqual({
      name: "sources/ladder/generation.json",
      sha256: "4fc2155a0eda619230b30e7c355d0c6e4b853c54945a0585b13969dfdf717eb3",
      bytes: 6456,
    });
    expect(first.files.find((file) => file.name === "ladder.png")).toEqual({
      name: "ladder.png",
      sha256: "a89b1d865b651806b1457ab1fc37da4d0a54ff28daf5566ec4011483c732faa6",
      bytes: 172703,
    });
  });

  test("recursively snapshots safe fixtures and rejects unsafe tree entries", async () => {
    const root = await fs.mkdtemp(
      path.join(tmpdir(), "stage-gen-recorder-fixture-tree-test-"),
    );
    try {
      const fixture = path.join(root, "fixture");
      const nested = path.join(fixture, "sources", "ladder");
      await fs.mkdir(nested, { recursive: true });
      await fs.writeFile(path.join(fixture, "runtime.json"), "runtime\n");
      await fs.writeFile(path.join(nested, "generation.json"), "provenance\n");

      const snapshot = await snapshotRecorderFixture(root, "fixture");
      expect(snapshot.files.map((file) => file.name)).toEqual([
        "runtime.json",
        "sources/ladder/generation.json",
      ]);
      await expect(
        snapshotRecorderFixture(root, "../fixture"),
      ).rejects.toThrow("canonical repository-relative path");
      expect(() =>
        assertPortableFixtureEntries(["Asset.png", "asset.png"]),
      ).toThrow("collide by case or normalization");
      expect(() =>
        assertPortableFixtureEntries(["café.png", "cafe\u0301.png"]),
      ).toThrow("unsafe filename");

      const link = path.join(fixture, "linked.json");
      await fs.symlink(path.join(fixture, "runtime.json"), link);
      await expect(snapshotRecorderFixture(root, "fixture")).rejects.toThrow(
        "must not contain symlinks",
      );
      await fs.unlink(link);

      const empty = path.join(fixture, "empty.json");
      await fs.writeFile(empty, "");
      await expect(snapshotRecorderFixture(root, "fixture")).rejects.toThrow(
        "nonempty regular files",
      );
      await fs.unlink(empty);

      const emptyDirectory = path.join(fixture, "empty-dir");
      await fs.mkdir(emptyDirectory);
      await expect(snapshotRecorderFixture(root, "fixture")).rejects.toThrow(
        "empty directories",
      );
    } finally {
      await fs.rm(root, { recursive: true, force: true });
    }
  });

  test("source snapshots defeat stale-build reuse and reject unsafe inputs", async () => {
    const root = await makeSyntheticBuildInputRoot("recorder-stale-build-test");
    try {
      const staleNext = path.join(root, ".next");
      await fs.mkdir(staleNext);
      await fs.writeFile(path.join(staleNext, "BUILD_ID"), "stale-build\n");
      const before = await snapshotGameplayBuildInputs(root);
      await fs.writeFile(
        path.join(root, "public", "bound.txt"),
        "changed pixel source\n",
      );
      const after = await snapshotGameplayBuildInputs(root);
      expect(() =>
        assertCanonicalSnapshotsEqual(before, after, "recording source"),
      ).toThrow("recording source changed");
      expect(await fs.readFile(path.join(staleNext, "BUILD_ID"), "utf8")).toBe(
        "stale-build\n",
      );

      const link = path.join(root, "app", "linked.ts");
      await fs.symlink(path.join(root, "app", "bound.txt"), link);
      await expect(snapshotGameplayBuildInputs(root)).rejects.toThrow(
        "must not contain symlinks",
      );
      await fs.unlink(link);
      const empty = path.join(root, "app", "empty");
      await fs.mkdir(empty);
      await expect(snapshotGameplayBuildInputs(root)).rejects.toThrow(
        "empty directories",
      );
    } finally {
      await fs.rm(root, { recursive: true, force: true });
    }
  });

  test("binds future root inputs while excluding outputs and every .env variant", async () => {
    const root = await makeSyntheticBuildInputRoot(
      "recorder-build-context-policy-test",
    );
    try {
      await fs.writeFile(path.join(root, ".env.local"), "FAL_KEY=first-secret\n");
      const baseline = await snapshotGameplayBuildInputs(root);
      expect(baseline.files.some((file) => file.name.startsWith(".env"))).toBe(
        false,
      );
      expect(JSON.stringify(baseline)).not.toContain("first-secret");

      await fs.writeFile(path.join(root, ".env.local"), "FAL_KEY=second-secret\n");
      expect(await snapshotGameplayBuildInputs(root)).toEqual(baseline);

      await fs.writeFile(
        path.join(root, "middleware.ts"),
        "export const middleware = () => undefined;\n",
      );
      const withFutureInput = await snapshotGameplayBuildInputs(root);
      expect(withFutureInput.files.some((file) => file.name === "middleware.ts")).toBe(
        true,
      );
      expect(() =>
        assertCanonicalSnapshotsEqual(
          baseline,
          withFutureInput,
          "future Next root input",
        ),
      ).toThrow("future Next root input changed");
    } finally {
      await fs.rm(root, { recursive: true, force: true });
    }
  });

  test("materializes the discovered build context as one exact immutable source copy", async () => {
    const root = await makeSyntheticBuildInputRoot("recorder-copy-test");
    const workspace = await fs.mkdtemp(
      path.join(tmpdir(), "stage-gen-recorder-copy-target-test-"),
    );
    try {
      const destination = path.join(workspace, "source");
      const source = await snapshotGameplayBuildInputs(root, destination);
      expect(await snapshotGameplayBuildInputs(destination)).toEqual(source);
      expect(await fs.readFile(path.join(destination, "scripts", "bound.txt"), "utf8")).toBe(
        "scripts\n",
      );
      expect(await fs.readFile(path.join(destination, "tests", "bound.txt"), "utf8")).toBe(
        "tests\n",
      );
    } finally {
      await Promise.all([
        fs.rm(root, { recursive: true, force: true }),
        fs.rm(workspace, { recursive: true, force: true }),
      ]);
    }
  });

  test("canonicalizes a recorder workspace created through a system path alias", async () => {
    const root = await fs.mkdtemp(
      path.join(tmpdir(), "stage-gen-recorder-workspace-alias-test-"),
    );
    const realParent = path.join(root, "real-temporary-root");
    const aliasParent = path.join(root, "temporary-root-alias");
    await fs.mkdir(realParent);
    await fs.symlink(realParent, aliasParent, "dir");
    let workspace: string | undefined;
    try {
      workspace = await createCanonicalRecorderWorkspace(aliasParent);
      expect(workspace.startsWith(`${await fs.realpath(realParent)}${path.sep}`)).toBe(
        true,
      );
      expect(await fs.realpath(workspace)).toBe(workspace);
      expect((await fs.lstat(workspace)).isDirectory()).toBe(true);
    } finally {
      if (workspace) await fs.rm(workspace, { recursive: true, force: true });
      await fs.rm(root, { recursive: true, force: true });
    }
  });

  test(
    "binds installed direct dependency versions to bun.lock",
    async () => {
      const webRoot = path.resolve(import.meta.dir, "../..");
      const identity = await validateRecorderDependencies(webRoot);
      expect(identity.nextCliPath).toBe("node_modules/next/dist/bin/next");
      expect(identity.packages.next).toMatch(/^15\./);
      expect(identity.packages.playwright).toMatch(/^1\./);
      expect(identity.implementations.next.fileCount).toBeGreaterThan(1_000);
      expect(identity.implementations.playwright.fileCount).toBeGreaterThan(10);
      expect(
        identity.implementations["playwright-core"].fileCount,
      ).toBeGreaterThan(10);
      expect(identity.implementations.phaser.totalBytes).toBeGreaterThan(
        10_000_000,
      );
      expect(identity.implementations.pngjs.fileCount).toBeGreaterThan(1);
      expect(identity.runtimeExecutable.locator).toBe("process.execPath");
      expect(identity.runtimeExecutable.sha256).toMatch(/^[0-9a-f]{64}$/);
      expect(identity.digest).toMatch(/^[0-9a-f]{64}$/);
    },
    // This deliberately hashes the installed Next/Playwright/Phaser trees;
    // cold filesystem caches can exceed Bun's generic five-second default.
    15_000,
  );

  test("dependency implementation identity detects changed executable code", async () => {
    const root = await fs.mkdtemp(
      path.join(tmpdir(), "stage-gen-recorder-dependency-tree-test-"),
    );
    try {
      await fs.mkdir(path.join(root, "dist"));
      await Promise.all([
        fs.writeFile(
          path.join(root, "package.json"),
          '{"name":"synthetic-runtime","version":"1.0.0"}\n',
        ),
        fs.writeFile(path.join(root, "dist", "runtime.js"), "export const value = 1;\n"),
      ]);
      const before = await snapshotRecorderImplementationTree(root);
      await fs.writeFile(
        path.join(root, "dist", "runtime.js"),
        "export const value = 2;\n",
      );
      const after = await snapshotRecorderImplementationTree(root);
      expect(after.digest).not.toBe(before.digest);
      expect(after.fileCount).toBe(before.fileCount);
    } finally {
      await fs.rm(root, { recursive: true, force: true });
    }
  });

  test("records exact build/media argv and ordered repeated event frames", () => {
    expect(GAMEPLAY_RECORDING_SCHEMA_VERSION).toBe(2);
    expect(GAMEPLAY_RECORDER_BUILD_ARGV).toEqual([
      "node_modules/next/dist/bin/next",
      "build",
      ".",
    ]);
    const commands = recorderMediaCommands({
      durationSeconds: 30,
      fps: 30,
      width: 1_280,
      height: 720,
      posterFrame: 35,
    });
    expect(commands.video.slice(0, 5)).toEqual([
      "-nostdin",
      "-hide_banner",
      "-loglevel",
      "error",
      "-y",
    ]);
    expect(commands.video.at(-1)).toBe("recording.mp4");
    expect(commands.poster.at(-1)).toBe("recording.poster.png");
    expect(commands.probe).toEqual([
      "-v",
      "error",
      "-count_frames",
      "-show_entries",
      "format=format_name,duration,size:stream=codec_type,codec_name,pix_fmt,width,height,avg_frame_rate,r_frame_rate,duration,nb_frames,nb_read_frames",
      "-of",
      "json",
      "recording.mp4",
    ]);
    expect(
      groupGameplayEventFrames([
        { kind: "platform-land", frame: 145 },
        { kind: "ladder-enter", frame: 154 },
        { kind: "platform-land", frame: 190 },
        { kind: "platform-land", frame: 211 },
      ]),
    ).toEqual({
      "platform-land": [145, 190, 211],
      "ladder-enter": [154],
    });
  });

  test("served-build identity rejects stale build injection", async () => {
    const root = await fs.mkdtemp(
      path.join(tmpdir(), "stage-gen-recorder-served-build-test-"),
    );
    try {
      const next = path.join(root, ".next");
      await fs.mkdir(path.join(next, "server"), { recursive: true });
      await fs.mkdir(path.join(next, "static"), { recursive: true });
      await Promise.all([
        fs.writeFile(path.join(next, "BUILD_ID"), "build-123\n"),
        fs.writeFile(path.join(next, "build-manifest.json"), "{}\n"),
        fs.writeFile(path.join(next, "routes-manifest.json"), "{}\n"),
        fs.writeFile(path.join(next, "required-server-files.json"), "{}\n"),
        fs.writeFile(path.join(next, "server", "entry.js"), "server\n"),
        fs.writeFile(path.join(next, "static", "chunk.js"), "static\n"),
      ]);
      const before = await snapshotServedNextBuild(root);
      await fs.writeFile(
        path.join(next, "server", "stale-injection.js"),
        "injected\n",
      );
      const after = await snapshotServedNextBuild(root);
      expect(() =>
        assertCanonicalSnapshotsEqual(before, after, "served build"),
      ).toThrow("served build changed");
    } finally {
      await fs.rm(root, { recursive: true, force: true });
    }
  });

  test("rejects a capture-parent rename and symlink swap before staging", async () => {
    const root = await fs.mkdtemp(
      path.join(tmpdir(), "stage-gen-recorder-parent-swap-test-"),
    );
    const reports = path.join(root, "reports");
    const moved = path.join(root, "reports-moved");
    const outside = path.join(root, "outside");
    await Promise.all([fs.mkdir(reports), fs.mkdir(outside)]);
    const targets = ["video.mp4", "poster.png", "recording.json"].map(
      (name) => path.join(reports, name),
    );
    const previous = targets.map((_, index) => Buffer.from(`previous-${index}`));
    await Promise.all(
      targets.map((target, index) => fs.writeFile(target, previous[index]!)),
    );
    const identity = await bindCaptureDirectoryIdentity(reports);
    let swapped = false;
    try {
      await expect(
        installCaptureFiles(
          targets.map((target, index) => ({
            target,
            bytes: Buffer.from(`replacement-${index}`),
          })),
          {
            directoryIdentity: identity,
            beforeDirectoryCheck: async (stage) => {
              if (stage !== "before-transaction" || swapped) return;
              swapped = true;
              await fs.rename(reports, moved);
              await fs.symlink(outside, reports, "dir");
            },
          },
        ),
      ).rejects.toThrow("directory identity changed");
      expect(await fs.readdir(outside)).toEqual([]);
      expect(
        await Promise.all(
          targets.map((target) => fs.readFile(path.join(moved, path.basename(target)))),
        ),
      ).toEqual(previous);
      expect(
        (await fs.readdir(moved)).filter((name) =>
          name.startsWith(".stage-gen-capture-install-"),
        ),
      ).toEqual([]);
    } finally {
      await fs.rm(root, { recursive: true, force: true });
    }
  });

  test("a mutation after the post-check cannot reach the atomic install", async () => {
    const root = await fs.mkdtemp(
      path.join(tmpdir(), "stage-gen-recorder-final-check-test-"),
    );
    try {
      const source = path.join(root, "source.ts");
      await fs.writeFile(source, "frozen source\n");
      const expectedSource = await fs.readFile(source);
      const targets = ["video.mp4", "poster.png", "recording.json"].map(
        (name) => path.join(root, name),
      );
      const previous = targets.map((_, index) => Buffer.from(`previous-${index}`));
      await Promise.all(
        targets.map((target, index) => fs.writeFile(target, previous[index]!)),
      );

      // This models a change while version probes and metadata work run after
      // the earlier post-capture check.
      await fs.writeFile(source, "mutated source\n");
      await expect(
        installRecorderCaptureAfterFinalCheck(
          targets.map((target, index) => ({
            target,
            bytes: Buffer.from(`replacement-${index}`),
          })),
          async () => {
            if (!(await fs.readFile(source)).equals(expectedSource)) {
              throw new Error("recording source changed before install");
            }
          },
          new AbortController().signal,
        ),
      ).rejects.toThrow("recording source changed before install");

      expect(await Promise.all(targets.map((target) => fs.readFile(target)))).toEqual(
        previous,
      );
      expect(
        (await fs.readdir(root)).filter((name) =>
          name.startsWith(".stage-gen-capture-install-"),
        ),
      ).toEqual([]);
    } finally {
      await fs.rm(root, { recursive: true, force: true });
    }
  });

  test("a bound vertical source mutation aborts before recorder install", async () => {
    const root = await makeSyntheticBuildInputRoot("recorder-bound-source-test");
    try {
      const before = await snapshotGameplayBuildInputs(root);
      const targets = ["video.mp4", "poster.png", "recording.json"].map(
        (name) => path.join(root, name),
      );
      const previous = targets.map((_, index) =>
        Buffer.from(`previous-${index}`),
      );
      await Promise.all(
        targets.map((target, index) => fs.writeFile(target, previous[index]!)),
      );
      await fs.writeFile(
        path.join(root, "lib", "runtime", "vertical.ts"),
        "mutated vertical source\n",
      );

      await expect(
        installRecorderCaptureAfterFinalCheck(
          targets.map((target, index) => ({
            target,
            bytes: Buffer.from(`replacement-${index}`),
          })),
          async () => {
            assertCanonicalSnapshotsEqual(
              before,
              await snapshotGameplayBuildInputs(root),
              "recording source",
            );
          },
          new AbortController().signal,
        ),
      ).rejects.toThrow("recording source changed");

      expect(
        await Promise.all(targets.map((target) => fs.readFile(target))),
      ).toEqual(previous);
      expect(
        (await fs.readdir(root)).filter((name) =>
          name.startsWith(".stage-gen-capture-install-"),
        ),
      ).toEqual([]);
    } finally {
      await fs.rm(root, { recursive: true, force: true });
    }
  });

  test("a mutation at the last installed sibling rolls back every original", async () => {
    const root = await fs.mkdtemp(
      path.join(tmpdir(), "stage-gen-recorder-installed-check-test-"),
    );
    try {
      const source = path.join(root, "source.ts");
      await fs.writeFile(source, "frozen source\n");
      const expectedSource = await fs.readFile(source);
      const targets = ["video.mp4", "poster.png", "recording.json"].map(
        (name) => path.join(root, name),
      );
      const previous = targets.map((_, index) =>
        Buffer.from(`previous-${index}`),
      );
      await Promise.all(
        targets.map((target, index) => fs.writeFile(target, previous[index]!)),
      );
      let validationCalls = 0;
      let mutated = false;

      await expect(
        installRecorderCaptureAfterFinalCheck(
          targets.map((target, index) => ({
            target,
            bytes: Buffer.from(`replacement-${index}`),
          })),
          async () => {
            validationCalls += 1;
            if (!(await fs.readFile(source)).equals(expectedSource)) {
              throw new Error("recording source changed after install");
            }
          },
          new AbortController().signal,
          undefined,
          {
            beforeDirectoryCheck: async (stage) => {
              if (stage !== "after-rename:recording.json" || mutated) return;
              mutated = true;
              await fs.writeFile(source, "mutated at final sibling\n");
            },
          },
        ),
      ).rejects.toThrow("recording source changed after install");

      expect(validationCalls).toBe(2);
      expect(await Promise.all(targets.map((target) => fs.readFile(target)))).toEqual(
        previous,
      );
      expect(
        (await fs.readdir(root)).filter((name) =>
          name.startsWith(".stage-gen-capture-install-"),
        ),
      ).toEqual([]);
    } finally {
      await fs.rm(root, { recursive: true, force: true });
    }
  });

  test("a dependency-code mutation at final install validation rolls back", async () => {
    const root = await fs.mkdtemp(
      path.join(tmpdir(), "stage-gen-recorder-dependency-install-test-"),
    );
    const dependency = path.join(root, "runtime-package");
    const reports = path.join(root, "reports");
    try {
      await Promise.all([fs.mkdir(dependency), fs.mkdir(reports)]);
      await Promise.all([
        fs.writeFile(
          path.join(dependency, "package.json"),
          '{"name":"runtime-package","version":"1.0.0"}\n',
        ),
        fs.writeFile(path.join(dependency, "runtime.js"), "export const value = 1;\n"),
      ]);
      const expectedDependency = await snapshotRecorderImplementationTree(
        dependency,
      );
      const targets = ["video.mp4", "poster.png", "recording.json"].map(
        (name) => path.join(reports, name),
      );
      const previous = targets.map((_, index) =>
        Buffer.from(`previous-${index}`),
      );
      await Promise.all(
        targets.map((target, index) => fs.writeFile(target, previous[index]!)),
      );
      let mutated = false;

      await expect(
        installRecorderCaptureAfterFinalCheck(
          targets.map((target, index) => ({
            target,
            bytes: Buffer.from(`replacement-${index}`),
          })),
          async () => {
            const current = await snapshotRecorderImplementationTree(dependency);
            if (current.digest !== expectedDependency.digest) {
              throw new Error("recorder dependency identity changed");
            }
          },
          new AbortController().signal,
          undefined,
          {
            beforeDirectoryCheck: async (stage) => {
              if (stage !== "after-rename:recording.json" || mutated) return;
              mutated = true;
              await fs.writeFile(
                path.join(dependency, "runtime.js"),
                "export const value = 2;\n",
              );
            },
          },
        ),
      ).rejects.toThrow("recorder dependency identity changed");

      expect(await Promise.all(targets.map((target) => fs.readFile(target)))).toEqual(
        previous,
      );
      expect(
        (await fs.readdir(reports)).filter((name) =>
          name.startsWith(".stage-gen-capture-install-"),
        ),
      ).toEqual([]);
    } finally {
      await fs.rm(root, { recursive: true, force: true });
    }
  });

  test("redacts and bounds diagnostics before they can enter report metadata", () => {
    const privatePath = ["", "Users", "example", "secret-project"].join("/");
    const diagnostic = sanitizeRecorderDiagnostic(
      `FAL_KEY=do-not-leak OPENROUTER_API_KEY=also-secret ${privatePath} ` +
        `Bearer token-value ${"x".repeat(10_000)} tail-marker`,
    );
    expect(diagnostic).not.toContain("do-not-leak");
    expect(diagnostic).not.toContain("also-secret");
    expect(diagnostic).not.toContain("token-value");
    expect(diagnostic).not.toContain(privatePath);
    expect(diagnostic).toContain("tail-marker");
    expect(diagnostic.length).toBeLessThanOrEqual(4_096);
  });

  test("allows portable report metadata and rejects paths or credentials", () => {
    expect(() =>
      assertPortableRecordingMetadata({
        schemaVersion: 1,
        artifact: "output/playwright/custom-report-2.mp4",
        digest: "a".repeat(64),
        command: [
          "bun",
          "scripts/gameplay/record.ts",
          "--output",
          "output/playwright/custom-report-2.mp4",
        ],
        capture: { browser: "chromium", fps: 24 },
      }),
    ).not.toThrow();

    const syntheticUserDirectory = ["Us", "ers"].join("");
    const syntheticPosixAbsolute = path.posix.join(
      path.posix.sep,
      syntheticUserDirectory,
      "synthetic-recorder-user",
      "private",
      "source.json",
    );
    const syntheticWindowsAbsolute = path.win32.join(
      "C:\\",
      syntheticUserDirectory,
      "synthetic-recorder-user",
      "private",
      "source.json",
    );
    for (const unsafe of [
      { source: syntheticPosixAbsolute },
      { source: syntheticWindowsAbsolute },
      { source: `file://${syntheticPosixAbsolute}` },
      { diagnostic: "FAL_KEY=do-not-publish" },
      { diagnostic: "Authorization: Bearer do-not-publish" },
    ]) {
      expect(() => assertPortableRecordingMetadata(unsafe)).toThrow();
    }
  });
});

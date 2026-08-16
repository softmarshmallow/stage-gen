import { afterEach, describe, expect, test } from "bun:test";
import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { PNG } from "pngjs";
import {
  GAMEPLAY_AUTOMATION_ENCOUNTER,
  GAMEPLAY_AUTOMATION_MODE,
  gameplayAutomationPresentation,
  type GameplayEncounterProbe,
  type GameplayAutomationSnapshot,
} from "../../lib/runtime/automation";
import { GAMEPLAY_MODEL_REQUIRED_ASSET_KEYS } from "./model-assets";
import {
  installCaptureFiles,
  resolveGameplayCapturePath,
  projectGameplayBoundsToViewport,
  runTool,
  runWithGameplayCleanups,
  validateFastStartMp4,
  validateGameplayMp4Probe,
  validateGameplayRun,
  validatePosterPng,
  type GameplayRunEvidence,
} from "./harness";
import { GAMEPLAY_POSTER_FRAME, GAMEPLAY_SELECTED_FRAMES } from "./timeline";

const temporaryRoots: string[] = [];

afterEach(async () => {
  await Promise.all(
    temporaryRoots
      .splice(0)
      .map((root) => fs.rm(root, { recursive: true, force: true })),
  );
});

async function makeTemporaryRoot(): Promise<string> {
  const root = await fs.mkdtemp(path.join(tmpdir(), "stage-gen-tool-test-"));
  temporaryRoots.push(root);
  return root;
}

function png(width: number, height: number, colorType = 2): Buffer {
  const data = Buffer.alloc(width * height * 4, 0);
  for (let offset = 0; offset < data.byteLength; offset += 4) {
    data[offset] = 20;
    data[offset + 1] = (offset / 4) % 251;
    data[offset + 2] = 190;
    data[offset + 3] = 255;
  }
  return PNG.sync.write(
    { width, height, data },
    { colorType, inputColorType: 6, inputHasAlpha: true },
  );
}

function isoBox(
  type: string,
  payload = Buffer.alloc(0),
  size: "normal" | "extended" | "open" = "normal",
): Buffer {
  if (size === "extended") {
    const header = Buffer.alloc(16);
    header.writeUInt32BE(1, 0);
    header.write(type, 4, 4, "ascii");
    header.writeBigUInt64BE(BigInt(header.byteLength + payload.byteLength), 8);
    return Buffer.concat([header, payload]);
  }
  const header = Buffer.alloc(8);
  header.writeUInt32BE(
    size === "open" ? 0 : header.byteLength + payload.byteLength,
    0,
  );
  header.write(type, 4, 4, "ascii");
  return Buffer.concat([header, payload]);
}

function encounterProbe(frame: number): GameplayEncounterProbe {
  const drop =
    frame >= 49 && frame < 67
      ? { left: 690, right: 730, top: 430, bottom: 490 }
      : null;
  const pickup =
    frame >= 67 ? { left: 690, right: 730, top: 430, bottom: 490 } : null;
  return {
    safeMarginPixels: GAMEPLAY_AUTOMATION_ENCOUNTER.safeMarginPixels,
    focusX: 610,
    focusY: 410,
    player: { left: 420, right: 520, top: 300, bottom: 520 },
    mob: { left: 680, right: 780, top: 310, bottom: 520 },
    attack: { left: 500, right: 710, top: 300, bottom: 520 },
    drop,
    pickup,
  };
}

function validRun(): GameplayRunEvidence {
  const eventFrames: Readonly<Record<string, number>> = {
    "mob-hit": 34,
    "mob-death": 43,
    "mob-drop": 49,
    "item-pickup": 67,
    "inventory-toggle": 480,
    "stage-advance": 892,
  };
  const events: GameplayAutomationSnapshot["events"] = Object.entries(
    eventFrames,
  ).map(([kind, frame]) => ({
    kind,
    frame,
    simulationMs: frame * (1000 / 30),
    data: kind === "inventory-toggle" ? { visible: false } : null,
  }));
  const snapshot: GameplayAutomationSnapshot = {
    version: GAMEPLAY_AUTOMATION_MODE,
    state: "ready",
    ready: true,
    errors: [],
    assetKeys: GAMEPLAY_MODEL_REQUIRED_ASSET_KEYS,
    frame: 900,
    simulationMs: 30_000,
    player: {
      state: "idle",
      facing: "right",
      x: 12_700,
      y: 512,
      column: 198,
      vx: 0,
      vy: 0,
      airborne: false,
      attackActive: false,
    },
    camera: { scrollX: 11_520, scrollY: 0, zoom: 1 },
    mobs: [],
    inventory: {
      visible: false,
      slots: [
        {
          kindIndex: 0,
          slotIndex: 0,
          count: 1,
          x: 0,
          y: 0,
          expectedPanelX: 336,
          expectedPanelY: 368,
        },
      ],
    },
    worldItems: [],
    encounter: encounterProbe(900),
    portals: [
      { kind: "entry", x: 224, y: 512, w: 100, h: 200 },
      { kind: "exit", x: 12_576, y: 512, w: 100, h: 200 },
    ],
    presentation: gameplayAutomationPresentation(900),
    events,
    heightmapDigest: "a".repeat(64),
  };
  const transcript = Array.from({ length: 900 }, (_, index) => {
    const frame = index + 1;
    const presentation = gameplayAutomationPresentation(frame);
    return JSON.stringify({
      frame,
      player: {
        ...snapshot.player,
        state: frame === GAMEPLAY_POSTER_FRAME ? "attack" : "run",
        vx: frame >= 846 && frame <= 899 ? 540 : 0,
      },
      camera: presentation.encounterFocus
        ? { scrollX: 0, scrollY: 0, zoom: presentation.cameraZoom }
        : { ...snapshot.camera, zoom: presentation.cameraZoom },
      mobs: [],
      worldItems:
        frame >= eventFrames["mob-drop"] && frame < eventFrames["item-pickup"]
          ? [{ kindIndex: 0, x: 100, y: 100, settled: true }]
          : [],
      encounter: encounterProbe(frame),
      presentation,
    });
  }).join("\n");
  return {
    transcript: `${transcript}\n`,
    transcriptDigest: "b".repeat(64),
    selectedFrameHashes: Object.fromEntries(
      GAMEPLAY_SELECTED_FRAMES.map((frame) => [String(frame), "c".repeat(64)]),
    ),
    states: ["idle", "walk", "run", "jump", "crouch", "attack"],
    finalSnapshot: snapshot,
  };
}

describe("gameplay harness verdict", () => {
  test("accepts the complete deterministic gameplay contract", () => {
    expect(() => validateGameplayRun(validRun())).not.toThrow();
  });

  test("projects encounter bounds through Phaser zoom-independent scroll", () => {
    expect(
      projectGameplayBoundsToViewport(
        { left: 540, right: 740, top: 260, bottom: 460 },
        { scrollX: 0, scrollY: 0, zoom: 1.2 },
      ),
    ).toEqual({ left: 520, right: 760, top: 240, bottom: 480 });
  });

  test("rejects a cropped encounter subject and poster action", () => {
    const run = validRun();
    const lines = run.transcript.trimEnd().split("\n");
    lines[34] = JSON.stringify({
      ...(JSON.parse(lines[34]!) as Record<string, unknown>),
      encounter: {
        ...encounterProbe(35),
        mob: { left: 1_500, right: 1_600, top: 310, bottom: 520 },
      },
    });
    expect(() =>
      validateGameplayRun({ ...run, transcript: `${lines.join("\n")}\n` }),
    ).toThrow("mob leaves the safe viewport at frame 35");
  });

  test("rejects duplicate gameplay milestones", () => {
    const run = validRun();
    const duplicate = run.finalSnapshot.events[0];
    const broken = {
      ...run,
      finalSnapshot: {
        ...run.finalSnapshot,
        events: [...run.finalSnapshot.events, duplicate],
      },
    };
    expect(() => validateGameplayRun(broken)).toThrow("exactly one mob-hit");
  });

  test("rejects missing state, asset, frame-hash, and duration evidence", () => {
    const run = validRun();
    expect(() => validateGameplayRun({ ...run, states: ["idle"] })).toThrow(
      "walk",
    );
    expect(() =>
      validateGameplayRun({
        ...run,
        finalSnapshot: { ...run.finalSnapshot, assetKeys: [] },
      }),
    ).toThrow("asset keys");
    expect(() =>
      validateGameplayRun({ ...run, selectedFrameHashes: {} }),
    ).toThrow("incomplete");
    expect(() =>
      validateGameplayRun({
        ...run,
        finalSnapshot: { ...run.finalSnapshot, simulationMs: 29_999 },
      }),
    ).toThrow("duration");
  });

  test("validates the capture path and exact MP4 technical contract", () => {
    expect(
      resolveGameplayCapturePath("docs/media/gameplay-showcase.mp4"),
    ).toEndWith("/docs/media/gameplay-showcase.mp4");
    for (const unsafe of [
      "showcase.mp4",
      "docs/media/showcase.mp4",
      "docs/media/gameplay-showcase.mov",
      "docs/media/../gameplay-showcase.mp4",
    ]) {
      expect(() => resolveGameplayCapturePath(unsafe)).toThrow(
        "exactly docs/media",
      );
    }
    const probe = {
      format: {
        format_name: "mov,mp4,m4a,3gp,3g2,mj2",
        duration: "30.000000",
        size: "9999999",
      },
      streams: [
        {
          codec_type: "video",
          codec_name: "h264",
          pix_fmt: "yuv420p",
          width: 1280,
          height: 720,
          avg_frame_rate: "30/1",
        },
      ],
    };
    expect(validateGameplayMp4Probe(probe)).toEqual({
      container: "mp4",
      video_codec: "h264",
      pixel_format: "yuv420p",
      width: 1280,
      height: 720,
      frame_rate: 30,
      duration_seconds: 30,
      fast_start: true,
      audio_codec: null,
    });
    expect(() =>
      validateGameplayMp4Probe({
        ...probe,
        format: { ...probe.format, size: "10000001" },
      }),
    ).toThrow("10 MB");
    expect(() =>
      validateGameplayMp4Probe({
        ...probe,
        streams: [...probe.streams, { codec_type: "audio", codec_name: "aac" }],
      }),
    ).toThrow("audio");

    for (const frameRate of [
      "30/1/trailing",
      "3e1/1",
      "030/1",
      "+30/1",
      "30/01",
      "30",
    ]) {
      expect(() =>
        validateGameplayMp4Probe({
          ...probe,
          streams: [{ ...probe.streams[0], avg_frame_rate: frameRate }],
        }),
      ).toThrow("invalid frame rate");
    }
    for (const duration of [
      "30.000000junk",
      "3e1",
      "030.0",
      "+30",
      " 30",
      "30.",
    ]) {
      expect(() =>
        validateGameplayMp4Probe({
          ...probe,
          format: { ...probe.format, duration },
        }),
      ).toThrow("invalid duration");
    }
    for (const size of [
      "9999999junk",
      "1e6",
      "0999999",
      "+9999999",
      " 9999999",
    ]) {
      expect(() =>
        validateGameplayMp4Probe({
          ...probe,
          format: { ...probe.format, size },
        }),
      ).toThrow("invalid size");
    }
  });

  test("attempts every cleanup and preserves primary failure ordering", async () => {
    const calls: string[] = [];
    const primary = new Error("operation failed");
    const browserFailure = new Error("browser close failed");
    let thrown: unknown;
    try {
      await runWithGameplayCleanups(async () => {
        throw primary;
      }, [
        {
          name: "browser",
          run: async () => {
            calls.push("browser");
            throw browserFailure;
          },
        },
        {
          name: "server",
          run: () => {
            calls.push("server");
          },
        },
        {
          name: "workspace",
          run: () => {
            calls.push("workspace");
          },
        },
      ]);
    } catch (error) {
      thrown = error;
    }
    expect(calls).toEqual(["browser", "server", "workspace"]);
    expect(thrown).toBeInstanceOf(AggregateError);
    const aggregate = thrown as AggregateError;
    expect(aggregate.errors).toEqual([primary, browserFailure]);
    expect(aggregate.cause).toBe(primary);
  });

  test("aggregates cleanup-only failures after preserving a successful result", async () => {
    const successful = await runWithGameplayCleanups(
      async () => "ok",
      [{ name: "browser", run: () => undefined }],
    );
    expect(successful).toBe("ok");

    const cleanupFailure = new Error("server stop failed");
    let thrown: unknown;
    try {
      await runWithGameplayCleanups(
        async () => "unused",
        [
          { name: "browser", run: () => undefined },
          { name: "server", run: async () => Promise.reject(cleanupFailure) },
          { name: "workspace", run: () => undefined },
        ],
      );
    } catch (error) {
      thrown = error;
    }
    expect(thrown).toBeInstanceOf(AggregateError);
    expect((thrown as AggregateError).errors).toEqual([cleanupFailure]);
  });

  test("rolls back every capture target after an injected replacement failure", async () => {
    const root = await makeTemporaryRoot();
    const targets = [
      "video.mp4",
      "poster.png",
      "video.json",
      "poster.json",
    ].map((name) => path.join(root, name));
    const previousBytes = targets.map((_, index) =>
      Buffer.from(`previous-${index}`),
    );
    await Promise.all(
      targets.map((target, index) =>
        fs.writeFile(target, previousBytes[index]!),
      ),
    );
    let payloadRenames = 0;
    await expect(
      installCaptureFiles(
        targets.map((target, index) => ({
          target,
          bytes: Buffer.from(`replacement-${index}`),
        })),
        {
          rename: async (source, target) => {
            if (path.basename(path.dirname(source)) === "payload") {
              payloadRenames += 1;
              if (payloadRenames === 2)
                throw new Error("injected replacement failure");
            }
            await fs.rename(source, target);
          },
        },
      ),
    ).rejects.toThrow("injected replacement failure");

    const restored = await Promise.all(
      targets.map((target) => fs.readFile(target)),
    );
    expect(restored).toEqual(previousBytes);
    expect(
      (await fs.readdir(root)).filter((name) =>
        name.startsWith(".stage-gen-capture-install-"),
      ),
    ).toEqual([]);
  });

  test("fully decodes exact RGB posters and rejects malformed or spoofed PNGs", () => {
    const valid = png(1280, 720);
    expect(() => validatePosterPng(valid)).not.toThrow();
    expect(() =>
      validatePosterPng(valid.subarray(0, valid.byteLength - 5)),
    ).toThrow("complete decodable PNG");

    const headerOnly = Buffer.alloc(33);
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]).copy(headerOnly);
    headerOnly.writeUInt32BE(1280, 16);
    headerOnly.writeUInt32BE(720, 20);
    expect(() => validatePosterPng(headerOnly)).toThrow(
      "complete decodable PNG",
    );

    const corrupted = Buffer.from(valid);
    corrupted[Math.floor(corrupted.byteLength / 2)] ^= 0xff;
    expect(() => validatePosterPng(corrupted)).toThrow(
      "complete decodable PNG",
    );
    expect(() => validatePosterPng(png(1280, 720, 6))).toThrow("8-bit RGB");
    expect(() => validatePosterPng(png(1279, 720))).toThrow("1280x720 PNG");
    const oversized = Buffer.alloc(5_000_001);
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]).copy(oversized);
    oversized.writeUInt32BE(1280, 16);
    oversized.writeUInt32BE(720, 20);
    expect(() => validatePosterPng(oversized)).toThrow("5 MB");
  });

  test("walks bounded ISO-BMFF boxes and rejects truncation or payload-name spoofing", () => {
    const valid = Buffer.concat([
      isoBox("ftyp", Buffer.from("isom\0\0\0\0", "latin1")),
      isoBox("moov", Buffer.alloc(0), "extended"),
      isoBox("free", Buffer.from("padding")),
      isoBox("mdat", Buffer.from([1, 2, 3])),
    ]);
    expect(() => validateFastStartMp4(valid)).not.toThrow();
    expect(() =>
      validateFastStartMp4(valid.subarray(0, valid.byteLength - 1)),
    ).toThrow("truncated");
    expect(() =>
      validateFastStartMp4(
        Buffer.concat([
          isoBox("ftyp", Buffer.from("isom\0\0\0\0", "latin1")),
          isoBox("free", Buffer.from("incidental moov then mdat text")),
        ]),
      ),
    ).toThrow("complete moov");
    expect(() =>
      validateFastStartMp4(
        Buffer.concat([
          isoBox("ftyp", Buffer.from("isom\0\0\0\0", "latin1")),
          isoBox("mdat", Buffer.alloc(0)),
          isoBox("moov", Buffer.alloc(0)),
        ]),
      ),
    ).toThrow("before mdat");

    const overflowing = Buffer.alloc(16);
    overflowing.writeUInt32BE(1, 0);
    overflowing.write("moov", 4, 4, "ascii");
    overflowing.writeBigUInt64BE(BigInt(Number.MAX_SAFE_INTEGER) + 1n, 8);
    expect(() => validateFastStartMp4(overflowing)).toThrow("overflowing");
  });

  test("times out a TERM-resistant tool, drains it, and fully reaps its process", async () => {
    const root = await makeTemporaryRoot();
    const marker = path.join(root, "hanging-tool.marker");
    const fakeTool = [
      'const fs = require("node:fs");',
      "const marker = process.argv[1];",
      "fs.writeFileSync(marker, String(process.pid));",
      'process.on("SIGTERM", () => fs.appendFileSync(marker, "\\nSIGTERM"));',
      "setInterval(() => {}, 1000);",
    ].join("\n");

    await expect(
      runTool(process.execPath, ["-e", fakeTool, marker], {
        timeoutMs: 250,
        terminateGraceMs: 100,
      }),
    ).rejects.toThrow("timed out after 250ms");
    const [pidText, signalMarker] = (await fs.readFile(marker, "utf8"))
      .trim()
      .split("\n");
    expect(signalMarker).toBe("SIGTERM");
    const pid = Number(pidText);
    expect(Number.isSafeInteger(pid) && pid > 0).toBe(true);
    expect(() => process.kill(pid, 0)).toThrow();
  });

  test("bounds and redacts failed-tool diagnostics", async () => {
    const syntheticPrivatePath = ["", "Users", "example", "private"].join("/");
    const fakeTool = [
      `console.error("FAL_KEY=do-not-leak ${syntheticPrivatePath} " + "x".repeat(10000));`,
      "process.exit(9);",
    ].join("\n");
    let message = "";
    try {
      await runTool(process.execPath, ["-e", fakeTool], { timeoutMs: 2_000 });
    } catch (error) {
      message = (error as Error).message;
    }
    expect(message).toContain("exited 9");
    expect(message).not.toContain("do-not-leak");
    expect(message).not.toContain(syntheticPrivatePath);
    expect(message.length).toBeLessThan(4_300);
  });
});

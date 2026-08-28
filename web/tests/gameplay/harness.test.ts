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
  APPROVED_VERTICAL,
  GAMEPLAY_VERTICAL_CAMERA_CHECKPOINTS,
  PLAYER_HURT_EVENT_FRAME,
  PLAYER_HURT_FRAME_COUNT,
  PLAYER_HURT_LAST_REACTION_FRAME,
  PLAYER_HURT_RECOVERY_FRAME,
  PLAYER_HURT_TIMELINE,
  acquireAbortableGameplayResource,
  installCaptureFiles,
  modelAssetBundleReference,
  resolveGameplayCapturePath,
  projectGameplayBoundsToViewport,
  runOwnedGameplayStartup,
  runTool,
  runWithGameplayCleanups,
  validateFastStartMp4,
  validateGameplayMp4Probe,
  validateGameplayRun,
  validatePlayerHurtRun,
  validatePosterPng,
  type GameplayRunEvidence,
} from "./harness";
import { GAMEPLAY_POSTER_FRAME, GAMEPLAY_SELECTED_FRAMES } from "./timeline";
import { STAGE_PLANS } from "../../lib/runtime/stages";
import {
  NEAR_FOREGROUND_DEPTH_COEFFICIENT,
  layoutSceneLayer,
  resolveSceneLayerStack,
  sceneLayerProbe,
  type SceneLayerProbe,
} from "../../lib/runtime/layers";

const temporaryRoots: string[] = [];

const FOREGROUND_CONTEXT = Object.freeze({
  viewportWidth: 1280,
  viewportHeight: 720,
  worldWidth: 12_800,
  groundBaselineY: 720,
  // Matches the runtime rule: the foreground meets the ground baseline, not a
  // separate row 16px above it.
  foregroundContactScreenY: 720,
  foregroundSafeBandTopY: 540,
  foregroundMaxScale: 0.75,
});
const FOREGROUND_ASSET = Object.freeze({
  width: 1024,
  height: 711,
  foreground: Object.freeze({
    sourceWidth: 1280,
    sourceHeight: 720,
    contentBounds: Object.freeze({ left: 0, top: 0, right: 1024, bottom: 711 }),
    meaningfulContentBounds: Object.freeze({
      left: 0,
      top: 425,
      right: 1024,
      bottom: 654,
    }),
    contactStrip: Object.freeze({ top: 609, bottom: 654 }),
    contactSourceY: 653,
    repeatPeriod: 1024,
    overlap: 256,
  }),
});
const FOREGROUND_CONTRACT = resolveSceneLayerStack(
  [
    { id: "sky", z_index: 0, parallax: 0, opaque: true },
    {
      id: "foreground",
      z_index: 20,
      parallax: NEAR_FOREGROUND_DEPTH_COEFFICIENT,
      opaque: false,
    },
  ],
  FOREGROUND_CONTEXT,
).find((layer) => layer.kind === "near-foreground")!;

function validForegroundLayer(
  camera: GameplayAutomationSnapshot["camera"],
  visible: boolean,
): SceneLayerProbe {
  const layout = layoutSceneLayer(
    FOREGROUND_CONTRACT,
    camera,
    FOREGROUND_CONTEXT,
    FOREGROUND_ASSET,
    1,
  );
  return sceneLayerProbe(FOREGROUND_CONTRACT, layout, camera, {
    x: layout.x,
    y: layout.y,
    scaleX: layout.scale,
    scaleY: layout.scale,
    displayWidth: layout.renderWidth * layout.scale,
    displayHeight: layout.renderHeight * layout.scale,
    originX: 0,
    originY: 0,
    scrollFactorX: 0,
    scrollFactorY: 0,
    tilePositionX: layout.tilePositionX,
    tilePositionY: 0,
    tileScaleX: layout.textureScale,
    tileScaleY: layout.textureScale,
    visible,
    depth: FOREGROUND_CONTRACT.renderDepth,
    spriteCount: 1,
    textureWidth: layout.textureWidth,
    textureHeight: layout.textureHeight,
    clipBounds: { left: 0, top: 0, right: 1280, bottom: 720 },
  });
}

type MutableBounds = {
  left: number;
  top: number;
  right: number;
  bottom: number;
};

type MutableVerticalBounds = { top: number; bottom: number };

type MutableTranscriptForegroundLayer = {
  renderDepth: number;
  depthCoefficient: number;
  cameraScrollX: number;
  cameraScrollY: number;
  screenBounds: MutableBounds;
  tilePositionX: number;
  render: {
    spriteCount: number;
    depth: number;
    y: number;
    scaleX: number;
    scaleY: number;
    tilePositionX: number;
    tileScaleX: number;
    tileScaleY: number;
    scrollFactorX: number;
    scrollFactorY: number;
    displayBounds: MutableBounds;
  };
  foreground: {
    spriteCount: number;
    contentScreenBounds: MutableBounds;
    meaningfulContentScreenBounds: MutableBounds;
    contactStripScreen: MutableVerticalBounds;
    contactScreenY: number;
    depthCoefficient: number;
    projectedCameraTravelScreenPx: number;
    phaseSourcePx: number;
    observedPhaseScreenPx: number;
    phaseDevicePixels: number;
    sourceScaleScreenX: number;
    sourceScaleScreenY: number;
    devicePixelRatio: number;
    repeatPeriodSourcePx: number;
    seamPeriodScreenPx: number;
    seamScreenX: number;
  };
};

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

function combatTextProbe(
  frame: number,
  eventFrame: number,
  direction: "outgoing" | "incoming",
): NonNullable<GameplayAutomationSnapshot["combatText"]> {
  const active = frame >= eventFrame && frame < eventFrame + 20;
  const startedAtMs = eventFrame * (1000 / 30);
  return Object.freeze({
    enabled: true,
    reducedMotion: true,
    disposed: false,
    activeCount: active ? 1 : 0,
    pooledCount: active ? 0 : frame >= eventFrame + 20 ? 1 : 0,
    entries: active
      ? Object.freeze([
          Object.freeze({
            eventId: 1,
            direction,
            amount: 1,
            text: "1",
            startedAtMs,
            anchorX: 730,
            anchorY: 290,
            x: 730,
            y: 290,
            alpha: 1,
            scale: 1,
          }),
        ])
      : Object.freeze([]),
  });
}

function validRun(): GameplayRunEvidence {
  const eventFrames: Readonly<Record<string, number>> = {
    "mob-hit": 34,
    "mob-death": 43,
    "mob-drop": 49,
    "item-pickup": 67,
    "inventory-toggle": 480,
    "stage-advance": 859,
  };
  const events: Array<GameplayAutomationSnapshot["events"][number]> = Object.entries(
    eventFrames,
  ).map(
    ([kind, frame]): GameplayAutomationSnapshot["events"][number] => ({
      kind,
      frame,
      simulationMs: frame * (1000 / 30),
      data:
        kind === "inventory-toggle"
          ? { visible: false }
          : kind === "mob-hit"
            ? { damage: 1, hpLeft: 0, died: true, ladderIndex: 0 }
            : null,
    }),
  );
  events.push(
    {
      kind: "platform-land",
      frame: 145,
      simulationMs: 145 * (1000 / 30),
      data: { platformId: "tier-1-launch" },
    },
    {
      kind: "terrain-step-off",
      frame: 700,
      simulationMs: 700 * (1000 / 30),
      data: { footY: 592, surfaceY: 656, column: 140 },
    },
    {
      kind: "terrain-step-block",
      frame: 596,
      simulationMs: 596 * (1000 / 30),
      data: { column: 118, footY: 592, x: 7551 },
    },
    {
      kind: "air-jump",
      frame: 610,
      simulationMs: 610 * (1000 / 30),
      data: { airJumpsUsed: 1, footY: 556, vy: -440 },
    },
    {
      kind: "air-jump",
      frame: 720,
      simulationMs: 720 * (1000 / 30),
      data: { airJumpsUsed: 1, footY: 556, vy: -440 },
    },
    {
      kind: "platform-drop",
      frame: 154,
      simulationMs: 154 * (1000 / 30),
      data: {
        platformId: "tier-1-launch",
        footY: 528,
        platformLeft: 1280,
        platformRight: 1664,
        platformBottomY: 560,
      },
    },
    {
      kind: "platform-underside-clear",
      frame: 162,
      simulationMs: 162 * (1000 / 30),
      data: {
        platformId: "tier-1-launch",
        footY: 603,
        playerLeft: 1679.4666666666667,
        playerTop: 462.2,
        playerRight: 1749.8666666666668,
        playerBottom: 603,
        platformLeft: 1280,
        platformRight: 1664,
        platformDeckY: 528,
        platformBottomY: 560,
        separationAxis: "horizontal",
      },
    },
    {
      kind: "platform-lower-land",
      frame: 165,
      simulationMs: 165 * (1000 / 30),
      data: { platformId: "tier-1-launch", support: "terrain", footY: 656 },
    },
    {
      kind: "platform-lower-settle",
      frame: 171,
      simulationMs: 171 * (1000 / 30),
      data: {
        platformId: "tier-1-launch",
        support: "terrain",
        footY: 656,
        stableFrames: 7,
      },
    },
    {
      kind: "platform-recovery-launch",
      frame: 175,
      simulationMs: 175 * (1000 / 30),
      data: {
        platformId: "tier-1-launch",
        support: "terrain",
        footY: 656,
        settledFootY: 656,
        stableFrames: 7,
      },
    },
    {
      kind: "platform-recovery-land",
      frame: 196,
      simulationMs: 196 * (1000 / 30),
      data: { platformId: "tier-1-launch", support: "platform", footY: 528 },
    },
    {
      kind: "platform-land",
      frame: 196,
      simulationMs: 196 * (1000 / 30),
      data: { platformId: "tier-1-launch" },
    },
    {
      kind: "platform-land",
      frame: 211,
      simulationMs: 211 * (1000 / 30),
      data: { platformId: "tier-2-transfer" },
    },
    {
      kind: "platform-land",
      frame: 231,
      simulationMs: 231 * (1000 / 30),
      data: { platformId: "tier-3-bridge" },
    },
    {
      kind: "platform-land",
      frame: 256,
      simulationMs: 256 * (1000 / 30),
      data: { platformId: "tier-4-summit" },
    },
    {
      kind: "ladder-enter",
      frame: 275,
      simulationMs: 275 * (1000 / 30),
      data: { ladderId: "ladder-summit", from: "platform", direction: "down" },
    },
    {
      kind: "ladder-exit",
      frame: 320,
      simulationMs: 320 * (1000 / 30),
      data: { ladderId: "ladder-summit", to: "terrain" },
    },
  );
  events.sort((left, right) => left.frame - right.frame);
  // Mirrors what the runtime builds for the fixture's terrain seed, so this
  // fixture stays a fixture rather than a second hand-copied world spec.
  const approved = APPROVED_VERTICAL[0]!;
  const platforms: GameplayAutomationSnapshot["platforms"] =
    approved.platforms.map((platform) => ({ ...platform, visible: false }));
  const platformRoutes: GameplayAutomationSnapshot["platformRoutes"] = [
    ...approved.routes,
  ];
  const climbables: GameplayAutomationSnapshot["climbables"] = approved.climbables.map(
    (ladder) => ({ ...ladder, visible: false }),
  );
  const finalPresentation = gameplayAutomationPresentation(900);
  const finalCamera = { scrollX: 11_520, scrollY: 0, zoom: 1 } as const;
  const snapshot: GameplayAutomationSnapshot = {
    version: GAMEPLAY_AUTOMATION_MODE,
    state: "ready",
    ready: true,
    errors: [],
    diagnostics: [],
    assetKeys: GAMEPLAY_MODEL_REQUIRED_ASSET_KEYS,
    stageIndex: 0,
    stageId: STAGE_PLANS[0]!.id,
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
      airJumpsUsed: 0,
      attackActive: false,
    hp: 6,
    maxHp: 6,
    invulnerable: false,
    defeated: false,
      support: "terrain",
      supportId: null,
      ladderId: null,
      platformId: null,
      dropThroughPlatformId: null,
      dropTraversalPhase: "recovered",
      dropTraversalPlatformId: "tier-1-launch",
      dropTraversalPlatformBottomY: 560,
      dropTraversalLowerSupport: "terrain",
      dropTraversalLowerSupportId: null,
      dropTraversalLowerSupportY: 656,
      dropTraversalStableFrames: 7,
      renderBounds: {
        left: 12_664.8,
        top: 371.2,
        right: 12_735.2,
        bottom: 512,
      },
      climbAnimationKey: null,
      climbTextureKey: null,
      climbFrame: null,
      climbAnimationPaused: null,
      rearFacing: false,
    },
    camera: finalCamera,
    layers: [
      validForegroundLayer(finalCamera, finalPresentation.foregroundVisible),
    ],
    platforms,
    platformRoutes,
    climbables,
    mobs: [],
    inventory: {
      visible: false,
      bounds: { left: 821, right: 1256, top: 24, bottom: 314 },
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
    presentation: finalPresentation,
    combatText: combatTextProbe(900, eventFrames["mob-hit"]!, "outgoing"),
    events,
    heightmapDigest: "a".repeat(64),
  };
  // One synthetic frame per index, shaped to the same choreography the live
  // capture produces. It exists to exercise the validators, so it only has to
  // be self-consistent with what they read: support and height through the
  // platform route, the paused ladder descent, and the arcs the air jumps
  // extend.
  const CLIMB_FROM = 275;
  const CLIMB_TO = 320;
  const PAUSE_FROM = 297;
  const PAUSE_TO = 300;
  /** Grounded jump arc height after `steps` fixed steps, in pixels risen. */
  const arcRise = (steps: number) => (495 * steps - 25 * steps * steps) / 30;
  const transcript = Array.from({ length: 900 }, (_, index) => {
    const frame = index + 1;
    const presentation = gameplayAutomationPresentation(frame);
    const climbing = frame >= CLIMB_FROM && frame < CLIMB_TO;
    const pausedClimb = frame >= PAUSE_FROM && frame < PAUSE_TO;
    const descentSteps =
      frame < CLIMB_FROM
        ? 0
        : frame < PAUSE_FROM
          ? frame - (CLIMB_FROM - 1)
          : frame < PAUSE_TO
            ? PAUSE_FROM - CLIMB_FROM
            : PAUSE_FROM - CLIMB_FROM + (frame - (PAUSE_TO - 1));
    const platformId =
      (frame >= 145 && frame <= 153) || frame === 196
        ? "tier-1-launch"
        : frame >= 211 && frame <= 216
          ? "tier-2-transfer"
          : frame >= 231 && frame <= 241
            ? "tier-3-bridge"
            : frame >= 256 && frame < CLIMB_FROM
              ? "tier-4-summit"
              : null;
    // Two air jumps over two-tile walls, and one terrain ledge that drops the
    // player under gravity, each with the arc the validators walk.
    const firstAirArc = frame >= 601 && frame <= 640;
    const secondAirArc = frame >= 711 && frame <= 750;
    const airJumpsUsed =
      (frame >= 610 && frame <= 640) || (frame >= 720 && frame <= 750) ? 1 : 0;
    const stepOffFall = frame >= 700 && frame <= 704;
    // A face met at 596 and left behind by the climb that follows it.
    const wallHold = frame >= 592 && frame <= 596;
    const airborne =
      (frame >= 126 && frame < 145) ||
      (frame >= 154 && frame < 165) ||
      (frame >= 175 && frame < 196) ||
      (frame >= 197 && frame < 211) ||
      (frame >= 217 && frame < 231) ||
      (frame >= 242 && frame < 256) ||
      firstAirArc ||
      secondAirArc ||
      stepOffFall;
    const support = climbing
      ? "climbable"
      : platformId
        ? "platform"
        : airborne
          ? "air"
          : "terrain";
    const deckY =
      platformId === "tier-1-launch"
        ? 528
        : platformId === "tier-2-transfer"
          ? 464
          : platformId === "tier-3-bridge"
            ? 400
            : platformId === "tier-4-summit"
              ? 336
              : null;
    const airArcY = (start: number, base: number) => base - arcRise(frame - start);
    const y = climbing
      ? Math.min(592, 336 + descentSteps * 6)
      : deckY !== null
        ? deckY
        : frame >= 154 && frame < 165
          ? 528 + (5 / 6) * (frame - 153) * (frame - 152)
          : frame >= 165 && frame < 175
            ? 656
            : frame >= 175 && frame < 196
              ? 656 - arcRise(frame - 174) - (frame >= 185 ? 40 : 0)
              : frame >= 197 && frame < 211
                ? airArcY(196, 528)
                : firstAirArc
                  ? 656 - arcRise(frame - 600) - (frame >= 610 ? 40 : 0)
                  : secondAirArc
                    ? 656 - arcRise(frame - 710) - (frame >= 720 ? 40 : 0)
                    : stepOffFall
                      ? 592 + (5 / 6) * (frame - 699) * (frame - 698)
                      : frame === 125
                        ? 528
                        : frame >= CLIMB_TO
                          ? 592
                          : snapshot.player!.y;
    const camera = presentation.encounterFocus
      ? { scrollX: 0, scrollY: 0, zoom: presentation.cameraZoom }
      : {
          ...snapshot.camera,
          scrollX:
            (snapshot.camera.scrollX * Math.max(0, frame - 80)) /
            (900 - 80),
          scrollY:
            frame === 231
              ? GAMEPLAY_VERTICAL_CAMERA_CHECKPOINTS.tierThree
              : frame >= 256 && frame < 315
                ? GAMEPLAY_VERTICAL_CAMERA_CHECKPOINTS.summit
                : GAMEPLAY_VERTICAL_CAMERA_CHECKPOINTS.recovery,
          zoom: presentation.cameraZoom,
        };
    const ladderId = climbing ? "ladder-summit" : null;
    const climbFrame = climbing ? Math.floor(Math.abs(592 - y) / 12) % 4 : null;
    const x =
      frame === 125
        ? 1192.6666666666667
        : frame === 130
        ? 1282.6666666666667
        : frame >= 145 && frame <= 153
          ? 1552.6666666666667
          : frame >= 154 && frame <= 162
            ? 1552.6666666666667 + 18 * (frame - 153)
            : frame >= 163 && frame <= 172
              ? 1714.6666666666667
              : frame >= 173 && frame <= 175
                ? 1714.6666666666667 - 18 * (frame - 172)
                : frame >= 176 && frame <= 196
                  ? 1660.6666666666667
                  : frame >= 197 && frame <= 211
                    ? 1660.6666666666667 + 18 * (frame - 196)
                    : frame >= 212 && frame <= 216
                      ? 1930.6666666666667 + 18 * (frame - 211)
                      : frame >= 217 && frame <= 231
                        ? 2020.6666666666667 + 18 * (frame - 216)
                        : frame >= 232 && frame <= 241
                          ? 2290.666666666667 + 18 * (frame - 231)
                          : frame >= 242 && frame <= 256
                            ? 2470.666666666667 + 18 * (frame - 241)
                            : frame >= 257 && frame < CLIMB_FROM
                              ? 2740.666666666667 + 18 * (frame - 256)
                              : climbing || frame === CLIMB_TO
                                ? 2976
                                : frame > CLIMB_TO
                                  ? // The closing run advances, held for the
                                    // frames spent against a column face.
                                    Math.min(
                                      snapshot.player!.x,
                                      2976 +
                                        18 *
                                          (Math.min(frame, wallHold ? 592 : frame) -
                                            CLIMB_TO),
                                    )
                                  : snapshot.player!.x;
    const renderBounds = {
      left: x - 35.2,
      top: y - 140.8,
      right: x + 35.2,
      bottom: y,
    };
    return JSON.stringify({
      frame,
      stageIndex: 0,
      stageId: STAGE_PLANS[0]!.id,
      player: {
        ...snapshot.player,
        state:
          climbing
            ? "climb"
            : airborne
              ? "jump"
            : frame === GAMEPLAY_POSTER_FRAME
              ? "attack"
              : "run",
        x,
        column: Math.floor(x / 64),
        y,
        vx: wallHold
          ? 0
          : (frame >= 154 && frame <= 162) ||
              (frame >= 197 && frame < CLIMB_FROM) ||
              (frame >= 846 && frame <= 899)
            ? 540
            : frame >= 173 && frame <= 180
              ? -540
              : 0,
        vy: climbing
          ? pausedClimb
            ? 0
            : 180
          : firstAirArc
            ? frame < 610
              ? -520 + 50 * (frame - 600)
              : -440 + 50 * (frame - 610)
            : secondAirArc
              ? frame < 720
                ? -520 + 50 * (frame - 710)
                : -440 + 50 * (frame - 720)
              : frame >= 154 && frame < 165
                ? 50 * (frame - 153)
                : frame >= 175 && frame < 196
                  ? frame < 185
                    ? -520 + 50 * (frame - 174)
                    : -440 + 50 * (frame - 185)
                  : airborne
                    ? 100
                    : 0,
        airborne,
        airJumpsUsed,
        support,
        supportId: ladderId ?? platformId,
        ladderId,
        platformId,
        dropThroughPlatformId:
          frame >= 154 && frame < 160 ? "tier-1-launch" : null,
        dropTraversalPhase:
          frame < 154
            ? null
            : frame < 162
              ? "drop-commanded"
              : frame < 165
                ? "underside-cleared"
                : frame < 171
                  ? "lower-support-landed"
                  : frame < 175
                    ? "lower-support-settled"
                    : frame < 196
                      ? "recovery-airborne"
                      : "recovered",
        dropTraversalPlatformId: frame >= 154 ? "tier-1-launch" : null,
        dropTraversalPlatformBottomY: frame >= 154 ? 560 : null,
        dropTraversalLowerSupport: frame >= 165 ? "terrain" : null,
        dropTraversalLowerSupportId: null,
        dropTraversalLowerSupportY: frame >= 165 ? 656 : null,
        dropTraversalStableFrames:
          frame < 165 ? 0 : Math.min(7, frame - 164),
        renderBounds,
        climbAnimationKey: climbing ? "player_climb" : null,
        climbTextureKey: climbing ? "character_climb" : null,
        climbFrame,
        climbAnimationPaused: climbing ? pausedClimb : null,
        rearFacing: climbing,
      },
      camera,
      layers: [validForegroundLayer(camera, presentation.foregroundVisible)],
      platforms,
      platformRoutes,
      climbables,
      mobs: [],
      worldItems:
        frame >= eventFrames["mob-drop"] && frame < eventFrames["item-pickup"]
          ? [
              {
                kindIndex: 0,
                x: 100,
                y: 100,
                settled: true,
                renderBounds: { left: 84, right: 116, top: 68, bottom: 100 },
              },
            ]
          : [],
      encounter: encounterProbe(frame),
      presentation,
      combatText: combatTextProbe(
        frame,
        eventFrames["mob-hit"]!,
        "outgoing",
      ),
      events: events.filter((event) => event.frame <= frame),
    });
  }).join("\n");
  return {
    transcript: `${transcript}\n`,
    transcriptDigest: "b".repeat(64),
    selectedFrameHashes: Object.fromEntries(
      GAMEPLAY_SELECTED_FRAMES.map((frame) => [String(frame), "c".repeat(64)]),
    ),
    states: ["idle", "walk", "run", "jump", "crouch", "attack", "climb"],
    finalSnapshot: snapshot,
  };
}

function validPlayerHurtRun(): GameplayRunEvidence {
  const events: GameplayAutomationSnapshot["events"] = Object.freeze([
    Object.freeze({
      kind: "player-hurt",
      frame: PLAYER_HURT_EVENT_FRAME,
      simulationMs: PLAYER_HURT_EVENT_FRAME * (1000 / 30),
      data: Object.freeze({ ladderIndex: 0, damage: 1, hpLeft: 5 }),
    }),
  ]);
  const snapshots = Array.from({ length: PLAYER_HURT_FRAME_COUNT }, (_, index) => {
    const frame = index + 1;
    const hurt =
      frame >= PLAYER_HURT_EVENT_FRAME &&
      frame <= PLAYER_HURT_LAST_REACTION_FRAME;
    const heldMovement = frame >= 14 && frame < 35;
    const movingAfterRecovery =
      frame >= PLAYER_HURT_RECOVERY_FRAME && heldMovement;
    const x =
      frame <= 13
        ? 96 + Math.max(0, frame - PLAYER_HURT_EVENT_FRAME) * 8
        : Math.max(32, 104 - (Math.min(frame, 34) - 13) * 6);
    const player: NonNullable<GameplayAutomationSnapshot["player"]> = {
      state: hurt ? "hurt" : movingAfterRecovery ? "walk" : "idle",
      facing: "left",
      x,
      y: 592,
      column: Math.floor(x / 64),
      vx: heldMovement ? -180 : hurt ? 260 : 0,
      vy: 0,
      airborne: false,
      airJumpsUsed: 0,
      attackActive: false,
      hp: frame >= PLAYER_HURT_EVENT_FRAME ? 5 : 6,
      maxHp: 6,
      invulnerable: frame >= PLAYER_HURT_EVENT_FRAME,
      defeated: false,
      support: "terrain",
      supportId: null,
      ladderId: null,
      platformId: null,
      dropThroughPlatformId: null,
      dropTraversalPhase: null,
      dropTraversalPlatformId: null,
      dropTraversalPlatformBottomY: null,
      dropTraversalLowerSupport: null,
      dropTraversalLowerSupportId: null,
      dropTraversalLowerSupportY: null,
      dropTraversalStableFrames: 0,
      renderBounds: { left: x - 24, right: x + 24, top: 472, bottom: 592 },
      climbAnimationKey: null,
      climbTextureKey: null,
      climbFrame: null,
      climbAnimationPaused: null,
      rearFacing: false,
    };
    return Object.freeze({ frame, player, events });
  });
  return {
    transcript: `${snapshots.map((snapshot) => JSON.stringify(snapshot)).join("\n")}\n`,
    transcriptDigest: "d".repeat(64),
    selectedFrameHashes: {},
    states: ["hurt", "idle", "walk"],
    finalSnapshot: {
      frame: PLAYER_HURT_FRAME_COUNT,
      events,
    } as GameplayAutomationSnapshot,
  };
}

describe("gameplay harness verdict", () => {
  test("ratifies one deterministic player hurt reaction without a control lock", () => {
    const actions = PLAYER_HURT_TIMELINE.flatMap((frame) => frame.actions);
    expect(actions).toEqual([
      { type: "down", key: "ArrowLeft" },
      { type: "up", key: "ArrowLeft" },
    ]);
    expect(() => validatePlayerHurtRun(validPlayerHurtRun())).not.toThrow();

    const invalid = validPlayerHurtRun();
    const lines = invalid.transcript.trimEnd().split("\n");
    const stunned = JSON.parse(lines[19]!) as { player: { vx: number } };
    stunned.player.vx = 260;
    lines[19] = JSON.stringify(stunned);
    expect(() =>
      validatePlayerHurtRun({ ...invalid, transcript: `${lines.join("\n")}\n` }),
    ).toThrow("held movement was blocked during player hurt");
  });

  test("binds the current capture entrypoint to the approved 20-asset set", async () => {
    const assetSet = await modelAssetBundleReference();
    expect(assetSet.count).toBe(20);
    expect(assetSet.assets).toHaveLength(20);
    expect(new Set(assetSet.assets.map((asset) => asset.id)).size).toBe(20);
    expect(assetSet.aggregate.sha256).toBe(
      "24f02376a8a561333b1f89403649c954a53ffb7c7cc035c3d4495f1127cfe9b8",
    );
  });

  test("accepts the complete deterministic gameplay contract", () => {
    expect(() => validateGameplayRun(validRun())).not.toThrow();
  });

  test("rejects live foreground mutations despite unchanged deterministic hashes", () => {
    const source = validRun();
    const mutateAtFrame = (
      mutate: (layer: MutableTranscriptForegroundLayer) => void,
    ): GameplayRunEvidence => {
      const lines = source.transcript.trimEnd().split("\n");
      const snapshot = JSON.parse(lines[100]!) as {
        layers: MutableTranscriptForegroundLayer[];
      };
      mutate(snapshot.layers[0]!);
      lines[100] = JSON.stringify(snapshot);
      return { ...source, transcript: `${lines.join("\n")}\n` };
    };
    const extraPartner = mutateAtFrame((layer) => {
      layer.render.spriteCount = 2;
      layer.foreground.spriteCount = 2;
    });
    const shiftedY = mutateAtFrame((layer) => {
      for (const bounds of [
        layer.screenBounds,
        layer.render.displayBounds,
        layer.foreground.contentScreenBounds,
        layer.foreground.meaningfulContentScreenBounds,
        layer.foreground.contactStripScreen,
      ]) {
        bounds.top += 24;
        bounds.bottom += 24;
      }
      layer.render.y += 24;
      layer.foreground.contactScreenY += 24;
    });
    const shiftedPhase = mutateAtFrame((layer) => {
      const delta =
        1 /
        (layer.foreground.sourceScaleScreenX *
          layer.foreground.devicePixelRatio);
      layer.tilePositionX += delta;
      layer.render.tilePositionX += delta;
      layer.foreground.phaseSourcePx += delta;
      layer.foreground.observedPhaseScreenPx +=
        delta * layer.foreground.sourceScaleScreenX;
      layer.foreground.phaseDevicePixels +=
        delta *
        layer.foreground.sourceScaleScreenX *
        layer.foreground.devicePixelRatio;
      layer.foreground.seamScreenX -=
        delta * layer.foreground.sourceScaleScreenX;
    });
    for (const run of [extraPartner, shiftedY, shiftedPhase]) {
      expect(run.selectedFrameHashes).toBe(source.selectedFrameHashes);
      expect(() => validateGameplayRun(run)).toThrow(
        "foreground layer probe violates contract",
      );
    }
  });

  test("rejects a fully correlated replay of the removed source-pixel phase formula", () => {
    const source = validRun();
    const lines = source.transcript.trimEnd().split("\n");
    for (let index = 0; index < lines.length; index += 1) {
      const snapshot = JSON.parse(lines[index]!) as {
        camera: GameplayAutomationSnapshot["camera"];
        layers: MutableTranscriptForegroundLayer[];
      };
      const layer = snapshot.layers[0]!;
      const foreground = layer.foreground;
      const raw =
        ((snapshot.camera.scrollX * layer.depthCoefficient) %
          foreground.repeatPeriodSourcePx +
          foreground.repeatPeriodSourcePx) %
        foreground.repeatPeriodSourcePx;
      let phase =
        Math.round(
          raw *
            foreground.sourceScaleScreenX *
            foreground.devicePixelRatio,
        ) /
        (foreground.sourceScaleScreenX * foreground.devicePixelRatio);
      if (phase >= foreground.repeatPeriodSourcePx) phase = 0;
      layer.tilePositionX = phase;
      layer.render.tilePositionX = phase;
      foreground.phaseSourcePx = phase;
      foreground.observedPhaseScreenPx =
        phase * foreground.sourceScaleScreenX;
      foreground.phaseDevicePixels =
        foreground.observedPhaseScreenPx * foreground.devicePixelRatio;
      foreground.seamScreenX =
        layer.render.displayBounds.left +
        (phase === 0 ? 0 : foreground.repeatPeriodSourcePx - phase) *
          foreground.sourceScaleScreenX;
      foreground.projectedCameraTravelScreenPx =
        snapshot.camera.scrollX *
        layer.depthCoefficient *
        foreground.sourceScaleScreenX;
      lines[index] = JSON.stringify(snapshot);
    }
    expect(() =>
      validateGameplayRun({
        ...source,
        transcript: `${lines.join("\n")}\n`,
      }),
    ).toThrow("foreground layer probe violates contract");
  });

  test("separately rejects motion-depth, painter-depth, scroll-factor, and stale re-entry mutations", () => {
    const source = validRun();
    const mutateFrame = (
      frame: number,
      mutate: (layer: MutableTranscriptForegroundLayer) => void,
    ): GameplayRunEvidence => {
      const lines = source.transcript.trimEnd().split("\n");
      const snapshot = JSON.parse(lines[frame - 1]!) as {
        layers: MutableTranscriptForegroundLayer[];
      };
      mutate(snapshot.layers[0]!);
      lines[frame - 1] = JSON.stringify(snapshot);
      return { ...source, transcript: `${lines.join("\n")}\n` };
    };
    const wrongCoefficient = mutateFrame(101, (layer) => {
      layer.depthCoefficient = 1.9;
      layer.foreground.depthCoefficient = 1.9;
    });
    const wrongPainter = mutateFrame(101, (layer) => {
      layer.renderDepth = 1199;
      layer.render.depth = 1199;
    });
    const phaserScrollFactor = mutateFrame(101, (layer) => {
      layer.render.scrollFactorX = 1;
    });
    const staleReentry = (() => {
      const lines = source.transcript.trimEnd().split("\n");
      const hidden = JSON.parse(lines[79]!) as {
        layers: MutableTranscriptForegroundLayer[];
      };
      const visible = JSON.parse(lines[80]!) as {
        layers: MutableTranscriptForegroundLayer[];
      };
      const before = hidden.layers[0]!;
      const after = visible.layers[0]!;
      after.tilePositionX = before.tilePositionX;
      after.render.tilePositionX = before.render.tilePositionX;
      after.foreground.phaseSourcePx = before.foreground.phaseSourcePx;
      after.foreground.observedPhaseScreenPx =
        before.foreground.observedPhaseScreenPx;
      after.foreground.phaseDevicePixels =
        before.foreground.phaseDevicePixels;
      after.foreground.seamScreenX = before.foreground.seamScreenX;
      lines[80] = JSON.stringify(visible);
      return { ...source, transcript: `${lines.join("\n")}\n` };
    })();
    for (const run of [
      wrongCoefficient,
      wrongPainter,
      phaserScrollFactor,
      staleReentry,
    ]) {
      expect(() => validateGameplayRun(run)).toThrow(
        "foreground layer probe violates contract",
      );
    }
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

  test("rejects missing, duplicate, and wrong-id ladder transitions", () => {
    const source = validRun();
    const vertical = source.finalSnapshot.events.filter((event) =>
      event.kind.startsWith("ladder-"),
    );
    const missing: GameplayAutomationSnapshot = {
      ...source.finalSnapshot,
      events: source.finalSnapshot.events.filter(
        (event) =>
          !(
            event.kind === "ladder-exit" &&
            event.data?.ladderId === "ladder-summit"
          ),
      ),
    };
    expect(() =>
      validateGameplayRun({ ...source, finalSnapshot: missing }),
    ).toThrow("event count");

    const duplicate: GameplayAutomationSnapshot = {
      ...source.finalSnapshot,
      events: [...source.finalSnapshot.events, structuredClone(vertical[0]!)].sort(
        (left, right) => left.frame - right.frame,
      ),
    };
    expect(() =>
      validateGameplayRun({ ...source, finalSnapshot: duplicate }),
    ).toThrow("event count");

    const wrongId: GameplayAutomationSnapshot = {
      ...source.finalSnapshot,
      events: source.finalSnapshot.events.map((event) =>
        event.kind === "ladder-enter" &&
        event.data?.ladderId === "ladder-summit"
          ? { ...event, data: { ...event.data, ladderId: "ladder-wrong" } }
          : event,
      ),
    };
    expect(() =>
      validateGameplayRun({ ...source, finalSnapshot: wrongId }),
    ).toThrow("order or ids");
  });

  test("rejects fake vertical probes and support/camera evidence", () => {
    const source = validRun();
    const fakeProbe: GameplayAutomationSnapshot = {
      ...source.finalSnapshot,
      platforms: source.finalSnapshot.platforms.map((platform, index) =>
        index === 0 ? { ...platform, deckY: 337 } : platform,
      ),
    };
    expect(() =>
      validateGameplayRun({ ...source, finalSnapshot: fakeProbe }),
    ).toThrow("platform probe");

    const lines = source.transcript.trimEnd().split("\n");
    const upper = JSON.parse(lines[255]!) as {
      player: {
        support: string;
        airborne: boolean;
        supportId: string | null;
        platformId: string | null;
      };
      camera: { scrollY: number };
      layers: MutableTranscriptForegroundLayer[];
    };
    upper.player.support = "air";
    upper.player.airborne = true;
    upper.player.supportId = null;
    upper.player.platformId = null;
    upper.camera.scrollY = 0;
    upper.layers[0]!.cameraScrollY = 0;
    lines[255] = JSON.stringify(upper);
    expect(() =>
      validateGameplayRun({
        ...source,
        transcript: `${lines.join("\n")}\n`,
      }),
    ).toThrow("exact summit state");

    const visualDrift: GameplayAutomationSnapshot = {
      ...source.finalSnapshot,
      climbables: source.finalSnapshot.climbables.map((ladder, index) =>
        index === 0
          ? { ...ladder, top: 312, visualTopOvershoot: 24 }
          : ladder,
      ),
    };
    expect(() =>
      validateGameplayRun({ ...source, finalSnapshot: visualDrift }),
    ).toThrow("climbable probe violates");

    const climbLines = source.transcript.trimEnd().split("\n");
    const climb = JSON.parse(climbLines[280]!) as {
      player: { rearFacing: boolean };
    };
    climb.player.rearFacing = false;
    climbLines[280] = JSON.stringify(climb);
    expect(() =>
      validateGameplayRun({
        ...source,
        transcript: `${climbLines.join("\n")}\n`,
      }),
    ).toThrow("climb presentation");

    const dropLines = source.transcript.trimEnd().split("\n");
    const recovered = JSON.parse(dropLines[164]!) as {
      player: { dropThroughPlatformId: string | null };
    };
    recovered.player.dropThroughPlatformId = "tier-1-launch";
    dropLines[164] = JSON.stringify(recovered);
    expect(() =>
      validateGameplayRun({
        ...source,
        transcript: `${dropLines.join("\n")}\n`,
      }),
    ).toThrow("sticky");

    const routeLines = source.transcript.trimEnd().split("\n");
    const routeDrift = JSON.parse(routeLines[400]!) as {
      platformRoutes: Array<{ horizontalRange: number | null }>;
    };
    routeDrift.platformRoutes[1]!.horizontalRange = 269;
    routeLines[400] = JSON.stringify(routeDrift);
    expect(() =>
      validateGameplayRun({
        ...source,
        transcript: `${routeLines.join("\n")}\n`,
      }),
    ).toThrow("routes drifted");
  });

  test("rejects compressed, clipped, or probe-free drop recovery", () => {
    const source = validRun();
    const retime = {
      ...source,
      finalSnapshot: {
        ...source.finalSnapshot,
        events: source.finalSnapshot.events.map((event) =>
          event.kind === "platform-lower-settle"
            ? {
                ...event,
                frame: 169,
                simulationMs: 169 * (1000 / 30),
              }
            : event,
        ),
      },
    };
    expect(() => validateGameplayRun(retime)).toThrow("choreography");

    const clipped = {
      ...source,
      finalSnapshot: {
        ...source.finalSnapshot,
        events: source.finalSnapshot.events.map((event) =>
          event.kind === "platform-underside-clear"
            ? {
                ...event,
                data: {
                  ...event.data,
                  playerLeft: 1650,
                  playerRight: 1720,
                },
              }
            : event,
        ),
      },
    };
    expect(() => validateGameplayRun(clipped)).toThrow("geometry or support");

    const lines = source.transcript.trimEnd().split("\n");
    const missingPhase = JSON.parse(lines[161]!) as {
      player: { dropTraversalPhase: string | null };
    };
    missingPhase.player.dropTraversalPhase = "drop-commanded";
    lines[161] = JSON.stringify(missingPhase);
    expect(() =>
      validateGameplayRun({
        ...source,
        transcript: `${lines.join("\n")}\n`,
      }),
    ).toThrow("ambiguous at frame 162");

    const lowerLines = source.transcript.trimEnd().split("\n");
    const movingLower = JSON.parse(lowerLines[165]!) as {
      player: { vy: number };
    };
    movingLower.player.vy = -60;
    lowerLines[165] = JSON.stringify(movingLower);
    expect(() =>
      validateGameplayRun({
        ...source,
        transcript: `${lowerLines.join("\n")}\n`,
      }),
    ).toThrow("lower drop support did not visibly settle at frame 166");
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

  test("reaps a startup-owned child before propagating startup cancellation", async () => {
    const cancellation = new Error("startup cancelled");
    let childPending = true;

    await expect(
      runOwnedGameplayStartup(
        async () => {
          throw cancellation;
        },
        async () => {
          childPending = false;
        },
        "gameplay server startup",
      ),
    ).rejects.toBe(cancellation);
    expect(childPending).toBe(false);
  });

  test("closes a late Chromium handle before propagating launch cancellation", async () => {
    const controller = new AbortController();
    let resolveBrowser!: (browser: { close: () => Promise<void> }) => void;
    let browserPending = true;
    const acquisition = new Promise<{ close: () => Promise<void> }>(
      (resolve) => {
        resolveBrowser = resolve;
      },
    );
    const result = acquireAbortableGameplayResource(
      acquisition,
      controller.signal,
      "Chromium launch",
      async (browser) => await browser.close(),
    );

    controller.abort(new Error("test cancellation"));
    resolveBrowser({
      close: async () => {
        browserPending = false;
      },
    });

    await expect(result).rejects.toThrow("Chromium launch was cancelled");
    expect(browserPending).toBe(false);
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
    const restoredBasenames: string[] = [];
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
            } else if (path.basename(path.dirname(source)) === "backup") {
              restoredBasenames.push(path.basename(target));
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
    expect(restoredBasenames).toEqual(["video.mp4"]);
    expect(
      (await fs.readdir(root)).filter((name) =>
        name.startsWith(".stage-gen-capture-install-"),
      ),
    ).toEqual([]);
  });

  test("does not disturb originals when cancellation wins during staging", async () => {
    const root = await makeTemporaryRoot();
    const targets = ["video.mp4", "poster.png", "recording.json"].map((name) =>
      path.join(root, name),
    );
    const previous = targets.map((_, index) =>
      Buffer.from(`previous-${index}`),
    );
    await Promise.all(
      targets.map((target, index) => fs.writeFile(target, previous[index]!)),
    );
    const controller = new AbortController();
    let renameCalls = 0;
    let backupCalls = 0;

    await expect(
      installCaptureFiles(
        targets.map((target, index) => ({
          target,
          bytes: Buffer.from(`replacement-${index}`),
        })),
        {
          signal: controller.signal,
          backup: async (source, target) => {
            backupCalls += 1;
            await fs.copyFile(source, target);
            if (backupCalls === 1)
              controller.abort(new Error("staging cancelled"));
          },
          rename: async (source, target) => {
            renameCalls += 1;
            await fs.rename(source, target);
          },
        },
      ),
    ).rejects.toThrow("cancelled");

    expect(renameCalls).toBe(0);
    expect(
      await Promise.all(targets.map((target) => fs.readFile(target))),
    ).toEqual(previous);
    expect(
      (await fs.readdir(root)).filter((name) =>
        name.startsWith(".stage-gen-capture-install-"),
      ),
    ).toEqual([]);
  });

  test("does not manufacture rollback when backup staging fails", async () => {
    const root = await makeTemporaryRoot();
    const targets = ["video.mp4", "poster.png", "recording.json"].map((name) =>
      path.join(root, name),
    );
    const previous = targets.map((_, index) =>
      Buffer.from(`previous-${index}`),
    );
    await Promise.all(
      targets.map((target, index) => fs.writeFile(target, previous[index]!)),
    );
    let backupCalls = 0;
    let renameCalls = 0;

    await expect(
      installCaptureFiles(
        targets.map((target, index) => ({
          target,
          bytes: Buffer.from(`replacement-${index}`),
        })),
        {
          backup: async (source, target) => {
            backupCalls += 1;
            if (backupCalls === 2) throw new Error("injected backup failure");
            await fs.copyFile(source, target);
          },
          rename: async (source, target) => {
            renameCalls += 1;
            await fs.rename(source, target);
          },
        },
      ),
    ).rejects.toThrow("injected backup failure");

    expect(renameCalls).toBe(0);
    expect(
      await Promise.all(targets.map((target) => fs.readFile(target))),
    ).toEqual(previous);
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

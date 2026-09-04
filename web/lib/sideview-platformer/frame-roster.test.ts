import { describe, expect, test } from "bun:test";
import { SealRefusal, SystemCycleError, sealSystems } from "@/lib/kernel/systems";
import { PREPARED_RUNTIME_BLOCKS } from "@/lib/manifest/prepared-manifest";
import { KILL_SHAKE_PROFILE } from "@/lib/families/screen-fx/shake";
import { NO_SHAKE, ShakeCarrier } from "@/lib/families/camera";
import { IMPACT_SHAKE_MS, IMPACT_SHAKE_PX } from "./impact-presentation";
import { parsePlatformerClockBlock } from "./clock";
import { parsePlatformerCameraBlock } from "./camera";
import {
  NEUTRAL_PLAYER_INTENT,
  PLATFORMER_INTENT_SHAPE,
  parsePlatformerIntentBlock,
} from "./player-intent";
import {
  assemblePlatformerSystems,
  createPlatformerFrameWorld,
  type PlatformerFrameSteps,
  type PlatformerFrameSystem,
} from "./frame-roster";

/**
 * The platformer's frame order, derived and pinned.
 *
 * The runner has had one of these since it was written; the platformer never
 * has, because until the strangler there was no roster to seal — the order was
 * seventy method calls in a row and the only way to see it was to read them.
 * This is the platformer's first, and it is the artefact every later extraction
 * is measured against: a declaration edit that moves a system moves this list,
 * and a list that moves without a sentence saying why is the diff to refuse.
 */
const DOCUMENTED_ORDER = [
  // Everything above the conversation hold runs on every frame, held or not.
  // The overlay's toggle, the two developer keys and the announcement are all
  // outside the simulation and stay outside it while a panel is open.
  "debug/overlay-toggle",
  "control/auto-play",
  "kit/switch",
  "debug/overlay",
  "banner/map-name",
  // One keyboard reading per frame, taken before anything branches on it.
  "intent/keyboard",
  // The hold itself. Every system below it declares `reads: ["hold"]` and
  // returns at its first line while a conversation is open, which is exactly
  // what the hand-written `return` in the middle of `update` did.
  "dialogue/input",
  "progression/stat-log",
  // The `clock` family, sealed where the genre's own hitstop step used to be:
  // it now answers for both of this frame's holders, the conversation as well
  // as the blow, rather than for the blow alone.
  "clock/step",
  // The simulation, in the order the audit found it: the player against
  // creatures that have not moved yet, then the authored set-pieces against the
  // player that has moved, then the census director that places new bodies
  // around both, then the creatures, then the shots against where the creatures
  // actually ended up, then the loot the shots produced.
  "player/update",
  // The `director` family: a gate armed at a map anchor, which reads this
  // frame's player position and writes the body it stands behind before
  // anything steps one.
  "director/set-piece",
  // ...and the `waves` profile of the same family, which arms at a census
  // zone's own left edge instead of at a portal anchor.
  "director/waves",
  "mobs/population",
  "mobs/step",
  "projectiles/step",
  "items/collect",
  // Presentation over the settled frame: the impact release before the shake
  // that sums it, the shake before the parallax that inherits it.
  "impact/release",
  "camera/shake",
  "npc/prompt",
  "shadows/contact",
  "parallax/scroll",
  // Last among the systems that step the world: it tears it down and builds
  // another one.
  "map/entry",
  // The round, and every one of the four is quiet for a package that authors
  // neither `[score]` nor `[timers]`. They are a *reading* of the frame rather
  // than a part of it — how much time is left, whether that was the last frame,
  // what the frame was worth, and what a readout shows — which is why they seal
  // after everything that could have changed any of those answers.
  "timers/countdown",
  "session/run",
  "score/run",
  "hud/round",
];

/** A steps object that answers every call, so the roster can be sealed without a scene. */
function inertSteps(record: string[] = []): PlatformerFrameSteps {
  const note =
    <T>(name: string, answer: T) =>
    (): T => {
      record.push(name);
      return answer;
    };
  return {
    toggleDebugOverlay: note("debug/overlay-toggle", undefined),
    updateAutoPlayToggle: note("control/auto-play", undefined),
    updateKitSwitch: note("kit/switch", undefined),
    updateDebugOverlay: note("debug/overlay", undefined),
    updateMapBanner: note("banner/map-name", undefined),
    readIntent: note("intent/keyboard", NEUTRAL_PLAYER_INTENT),
    dialogueOpen: () => true,
    updateDialogueInput: note("dialogue/input", undefined),
    updateStatLog: note("progression/stat-log", undefined),
    hitstopActive: note("clock/step", false),
    updatePlayer: note("player/update", undefined),
    stepSetPieces: note("director/set-piece", undefined),
    updateMobPopulation: note("mobs/population", undefined),
    stepMobs: note("mobs/step", undefined),
    updateProjectiles: note("projectiles/step", undefined),
    collectDrops: note("items/collect", undefined),
    updateImpact: note("impact/release", undefined),
    impactShake: note("camera/shake", NO_SHAKE),
    carryCameraShake: () => undefined,
    updateInteractionPrompt: note("npc/prompt", undefined),
    updateContactShadows: note("shadows/contact", undefined),
    scrollParallaxLayers: note("parallax/scroll", undefined),
    applyPendingMapEntry: note("map/entry", undefined),
    stepWaves: note("director/waves", undefined),
    scoredThisFrame: note("score/run", {}),
    scoreChanged: () => undefined,
    roundEnded: () => undefined,
  };
}

const roster = (steps: PlatformerFrameSteps = inertSteps()) => assemblePlatformerSystems(steps);

/** The real roster with one system's declaration replaced, the way the runner fixtures its own. */
function rosterWith(
  id: string,
  replace: (system: PlatformerFrameSystem) => PlatformerFrameSystem,
): PlatformerFrameSystem[] {
  return roster().map((system) => (system.id === id ? replace(system) : system));
}

/** Add reads to one system, which is how every recorded refusal is reproduced. */
function alsoReads(id: string, ...keys: string[]): PlatformerFrameSystem[] {
  return rosterWith(id, (system) => ({
    ...system,
    reads: [...system.reads, ...(keys as PlatformerFrameSystem["reads"])],
  }));
}

describe("assemblePlatformerSystems", () => {
  test("seals into the documented frame order", () => {
    expect(sealSystems(roster()).order).toEqual(DOCUMENTED_ORDER);
  });

  test("the documented order is the order the hand-written frame ran in", () => {
    // Registration order is the frame as it was typed out before this step. The
    // sealer derives its order from declarations and only falls back on
    // registration to break a tie, so this equality is the zero-diff claim: the
    // roster reproduces the frame rather than reorganising it.
    expect(roster().map((system) => system.id)).toEqual(DOCUMENTED_ORDER);
  });

  test("every system declares a contract version", () => {
    for (const system of roster()) expect(system.contractVersion).toMatch(/-v\d+$/);
  });

  test("no system emits or consumes, so the seal takes no queue", () => {
    // The platformer names occurrences in its own transcript rather than in an
    // event queue. Sealing with an events accessor no system uses is refused,
    // and that refusal is what would catch a half-migration here.
    for (const system of roster()) {
      expect(system.emits ?? []).toEqual([]);
      expect(system.consumes ?? []).toEqual([]);
    }
    expect(() =>
      sealSystems(roster(), { events: () => ({ beginFrame() {}, discardFrames() {} }) }),
    ).toThrow(SealRefusal);
  });
});

/**
 * The order facts that are load bearing, asserted where registration cannot help.
 *
 * The roster is not fully determined by its declarations, and pretending it is
 * would be the same lie the runner's fake `reads` told. Several steps are
 * genuinely independent — the overlay's visibility against its text, the
 * announcement against the developer keys — and their relative order is broken
 * by registration and means nothing. These pairs are the ones that do mean
 * something, and each one survives a reversed registration because a
 * declaration, not the list, buys it.
 */
const LOAD_BEARING = [
  // The frame reads the keyboard once, and the conversation reads that answer.
  ["intent/keyboard", "dialogue/input"],
  // The hold is written before anything that returns under it.
  ["dialogue/input", "player/update"],
  ["dialogue/input", "npc/prompt"],
  // The simulation delta is decided before the integrators are handed it.
  ["clock/step", "player/update"],
  ["clock/step", "mobs/step"],
  // The director places bodies against a player that has already moved.
  ["player/update", "mobs/population"],
  // ...and the creatures it reserved are stepped after it reserved them.
  ["mobs/population", "mobs/step"],
  // A shot collides against where the creatures actually are.
  ["mobs/step", "projectiles/step"],
  // A kill lands in this frame's loot pass, not the next one's.
  ["player/update", "items/collect"],
  ["projectiles/step", "items/collect"],
  // The audit's own three: release before the shake that sums it, shake before
  // the parallax that inherits it, and the kit resolved before it is reported.
  ["impact/release", "camera/shake"],
  ["camera/shake", "parallax/scroll"],
  ["kit/switch", "debug/overlay"],
  ["control/auto-play", "debug/overlay"],
  // The world is replaced when every system stepping it has finished.
  ["parallax/scroll", "map/entry"],
  ["shadows/contact", "map/entry"],
  ["npc/prompt", "map/entry"],
] as const;

describe("the edges the frame order actually rests on", () => {
  test("hold under a reversed registration, so the declarations and not the list buy them", () => {
    const reversed = sealSystems([...roster()].reverse()).order;
    for (const [before, after] of LOAD_BEARING) {
      expect(reversed.indexOf(before)).toBeLessThan(reversed.indexOf(after));
    }
  });

  test("and hold in the documented order too", () => {
    for (const [before, after] of LOAD_BEARING) {
      expect(DOCUMENTED_ORDER.indexOf(before)).toBeLessThan(DOCUMENTED_ORDER.indexOf(after));
    }
  });
});

/**
 * The six refusals the sealer made on the first attempt.
 *
 * Each one is a hidden edge the hand-written frame carried and no reader could
 * see: a read of a value the frame produces *later*, which is a feedback read
 * and cannot be declared, or a write whose readers are all a frame away. They
 * are fixtured rather than described, so a later step that "tidies up" a
 * declaration by adding the read back is refused by a test that names the
 * cycle rather than by a golden that moves for reasons nobody can place.
 */
describe("the refusals that produced the edge list", () => {
  test("1: the hitstop deadline is last frame's", () => {
    // `clock/step` asks the impact system whether a blow is still holding the
    // simulation, and the systems that arm one are sealed after it.
    expect(() => sealSystems(alsoReads("clock/step", "impact"))).toThrow(SystemCycleError);
  });

  test("2: the creatures the player fights are where they stood last frame", () => {
    // The audit's "the mob's committed strike read a frame later by the player
    // update", and the largest of the six.
    expect(() => sealSystems(alsoReads("player/update", "mobs"))).toThrow(SystemCycleError);
  });

  test("3: the bag a throw spends from is last frame's", () => {
    expect(() => sealSystems(alsoReads("player/update", "items"))).toThrow(SystemCycleError);
  });

  test("4: the creatures are stepped by an explicit edge, not by a read", () => {
    // Both `mobs/population` and `mobs/step` write the creatures and neither
    // reads what the other wrote, so the dataflow does not order them. Declaring
    // the read instead collides with the shot pool, which legitimately reads
    // this frame's positions and writes its damage back into them.
    expect(() => sealSystems(alsoReads("mobs/step", "mobs"))).toThrow(SystemCycleError);
    expect(roster().find((system) => system.id === "mobs/step")?.after).toEqual([
      "mobs/population",
    ]);
  });

  test("5: the camera the population director asks is last frame's", () => {
    // Not on the audit's list. The director asks the camera what is on screen
    // before this frame's shake has been applied and before the engine's follow
    // has run.
    expect(() => sealSystems(alsoReads("mobs/population", "camera"))).toThrow(SystemCycleError);
  });

  test("6: the stage a map entry builds is read a frame later", () => {
    // The mirror image of a feedback read: a deferred write. Declaring it makes
    // the player both the system that asks for an entry and a reader of the
    // stage the entry rebuilds.
    const declared = rosterWith("map/entry", (system) => ({
      ...system,
      writes: [...system.writes, "stage" as const],
    }));
    expect(() => sealSystems(declared)).toThrow(SystemCycleError);
  });
});

describe("the conversation hold", () => {
  test("every system below it returns at its first line while a panel is open", () => {
    const ran: string[] = [];
    const sealed = sealSystems(roster(inertSteps(ran)));
    sealed.tick(createPlatformerFrameWorld(), { dt: 1000 / 30, now: 0, frame: 1 });
    // `dialogueOpen` answers true, so the frame is exactly the systems above the
    // hold plus the hold itself — which is what the hand-written `return` left
    // running, line for line.
    expect(ran).toEqual(DOCUMENTED_ORDER.slice(0, DOCUMENTED_ORDER.indexOf("dialogue/input") + 1));
  });

  test("and the whole frame runs when no panel is open", () => {
    const ran: string[] = [];
    const sealed = sealSystems(roster({ ...inertSteps(ran), dialogueOpen: () => false }));
    sealed.tick(createPlatformerFrameWorld(), { dt: 1000 / 30, now: 0, frame: 1 });
    // Everything but the conversation's own input, which only runs while one is
    // open — and the four round systems, which for a package that authors
    // neither optional block reach no step at all. That is what "quiet" means
    // here and it is asserted rather than described: an empty award table, an
    // empty countdown, a lifecycle with nothing that can end it, and a readout
    // with nothing to draw.
    expect(ran).toEqual(
      DOCUMENTED_ORDER.filter((id) => id !== "dialogue/input" && !QUIET_WITHOUT_A_ROUND.includes(id)),
    );
  });

  test("a quiet round writes nothing into its own slices", () => {
    const world = createPlatformerFrameWorld();
    const sealed = sealSystems(roster({ ...inertSteps(), dialogueOpen: () => false }));
    for (let frame = 1; frame <= 120; frame += 1) {
      sealed.tick(world, { dt: 1000 / 30, now: (frame * 1000) / 30, frame });
    }
    expect(world.score).toEqual({ total: 0, chain: 0, multiplier: 1 });
    expect(world.timers.entries).toEqual([]);
    // The lifecycle does the one thing it always does: it starts. Nothing can
    // end it, because nothing is counting down.
    expect(world.session.phase).toBe("running");
    expect(world.session.endedBy).toBeNull();
  });
});

/** The four systems a package with no `[score]` and no `[timers]` never reaches a step through. */
const QUIET_WITHOUT_A_ROUND: readonly string[] = [
  "timers/countdown",
  "session/run",
  "score/run",
  "hud/round",
];

/**
 * The invariant that lets the one keyboard reading be modelled as a read.
 *
 * `JustDown` spends the latch, so the frame's intent reading is destructive for
 * the edges it takes; it is declared as a read of `keys` rather than a write
 * because every key whose latch it spends is one the scene itself never touches.
 * That disjointness is the fix step 0 measured at 529 frames of the golden —
 * before it, the scene re-read space after the intent had spent it and the
 * conversation never closed — and it is checked here against the two files
 * rather than trusted, because a new key on either side would break it in
 * silence and the golden would report it as five hundred moved frames.
 */
describe("the frame's one keyboard reading", () => {
  /** `name: <keyboard>.addKey(Phaser.Input.Keyboard.KeyCodes.CODE)` → name → CODE. */
  function bindings(source: string, region: RegExp): Map<string, string> {
    const body = region.exec(source)?.[0] ?? "";
    const found = new Map<string, string>();
    for (const match of body.matchAll(
      /(\w+):\s*(?:keyboard|kb)\.addKey\(\s*Phaser\.Input\.Keyboard\.KeyCodes\.(\w+)/g,
    )) {
      found.set(match[1]!, match[2]!);
    }
    return found;
  }

  test("spends no latch on a key the scene itself reads", async () => {
    const sceneSource = await Bun.file("lib/sideview-platformer/prepared-scene.ts").text();
    const playerSource = await Bun.file("lib/sideview-platformer/player.ts").text();
    const sceneKeys = bindings(sceneSource, /private installInput\(\)[\s\S]*?\n  \}/);
    const playerKeys = bindings(playerSource, /private bindInput\(\)[\s\S]*?\n  \}/);
    // The maps parsed at all, so a rename cannot make this test vacuously green.
    expect(sceneKeys.size).toBeGreaterThan(4);
    expect(playerKeys.size).toBeGreaterThan(4);

    // Every key the intent reading takes as an edge, and so spends.
    const intentEdges = new Set(
      [...playerKeys]
        .filter(([name]) => new RegExp(`JustDown\\(\\s*k\\??\\.${name}\\b`).test(playerSource))
        .map(([, code]) => code),
    );
    expect([...intentEdges].sort()).toEqual(["I", "J", "Q", "SPACE", "X", "Z"]);

    // Every key the scene reaches for at all — level or edge, directly or
    // through a local. Deliberately the wider set: the invariant is not "the
    // two edge reads do not collide", which would let a level read of a spent
    // latch back in, but "the scene does not touch what the intent spends".
    const sceneTouched = new Set(
      [...sceneKeys]
        .filter(([name]) => new RegExp(`\\bkeys\\??\\.${name}\\b`).test(sceneSource))
        .map(([, code]) => code),
    );
    expect([...sceneTouched].sort()).toEqual(["ENTER", "E", "K", "P", "UP", "W", "BACKTICK"].sort());

    expect([...intentEdges].filter((code) => sceneTouched.has(code)).sort()).toEqual([]);
  });

  test("and the scene binds one key it no longer reads", () => {
    // Space. Step 0 routed the conversation and the death screen onto the
    // intent's own answer, which left `keys.jump` bound and unread — the exact
    // binding whose latch the intent spends. It is left here rather than
    // removed because removing it belongs to the step that extracts `intent`,
    // and it is asserted here so that "unread" stays a fact rather than a
    // memory: anything that starts reading it re-opens the step-0 defect.
    return Bun.file("lib/sideview-platformer/prepared-scene.ts")
      .text()
      .then((source) => {
        expect(source).toContain("jump: keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.SPACE)");
        expect(/\bkeys\??\.jump\b/.test(source)).toBe(false);
      });
  });
});

// --- The `clock` family, sealed into this genre ---------------------------------------------

describe("the clock family in the platformer", () => {
  test("E7 subtraction: with the clock taken out, the rest seals to the identical order", () => {
    const quiet = roster().filter((system) => system.id !== "clock/step");
    expect(sealSystems(quiet).order).toEqual(DOCUMENTED_ORDER.filter((id) => id !== "clock/step"));
  });

  test("both holders stop the simulation, and the conversation is named first", () => {
    const world = createPlatformerFrameWorld();
    let dialogue = false;
    let hitstop = false;
    const steps = { ...inertSteps(), dialogueOpen: () => dialogue, hitstopActive: () => hitstop };
    const sealed = sealSystems(assemblePlatformerSystems(steps));
    const tick = (frame: number) => sealed.tick(world, { dt: 1000 / 30, now: frame * (1000 / 30), frame });

    tick(1);
    expect(world.clock.held).toBe(false);
    expect(world.clock.simulationDt).toBeCloseTo(1000 / 30, 9);

    hitstop = true;
    tick(2);
    expect(world.clock.heldBy).toBe("hitstop");
    expect(world.clock.simulationDt).toBe(0);

    dialogue = true;
    tick(3);
    expect(world.clock.heldBy).toBe("dialogue");

    dialogue = false;
    hitstop = false;
    tick(4);
    expect(world.clock.held).toBe(false);
    // Two of four frames were held: the integral is two deltas, not four.
    expect(world.clock.simulationNow).toBeCloseTo((2 * 1000) / 30, 9);
  });

  test("the family gates its own block, and the refusal names it", () => {
    expect(parsePlatformerClockBlock(PREPARED_RUNTIME_BLOCKS).published).toBe(true);
    expect(() =>
      parsePlatformerClockBlock({ ...PREPARED_RUNTIME_BLOCKS, gameplay: "platformer-gameplay-block-v2" }),
    ).toThrow(
      'manifest block "gameplay" is published as platformer-gameplay-block-v2; ' +
        "this build reads platformer-gameplay-block-v1",
    );
  });
});

// --- The `intent` family, sealed into this genre -----------------------------------------------

describe("the intent family in the platformer", () => {
  test("E7 subtraction: with the intent read taken out, the rest seals to the identical order", () => {
    const quiet = roster().filter((system) => system.id !== "intent/keyboard");
    expect(sealSystems(quiet).order).toEqual(
      DOCUMENTED_ORDER.filter((id) => id !== "intent/keyboard"),
    );
  });

  test("the edge-vs-level split is data this genre declares, not a comment", () => {
    expect([...PLATFORMER_INTENT_SHAPE.edges].sort()).toEqual([
      "attack",
      "jump",
      "toggleInventory",
      "useHealing",
    ]);
    expect([...PLATFORMER_INTENT_SHAPE.levels].sort()).toEqual([
      "down",
      "face",
      "left",
      "right",
      "run",
      "up",
    ]);
  });

  test("the family gates its own block, and the refusal names it", () => {
    expect(parsePlatformerIntentBlock(PREPARED_RUNTIME_BLOCKS).published).toBe(true);
    expect(() =>
      parsePlatformerIntentBlock({
        ...PREPARED_RUNTIME_BLOCKS,
        gameplay: "platformer-gameplay-block-v2",
      }),
    ).toThrow('manifest block "gameplay" is published as platformer-gameplay-block-v2');
  });
});

// --- The `screen-fx` family, sealed into this genre --------------------------------------------

describe("the screen-fx family in the platformer", () => {
  test("the kill shake is the family's profile, not a second copy", () => {
    expect(IMPACT_SHAKE_MS).toBe(KILL_SHAKE_PROFILE.durationMs);
    expect(IMPACT_SHAKE_PX).toBe(KILL_SHAKE_PROFILE.amplitudePx);
  });
});

// --- The `camera` family, sealed into this genre -----------------------------------------------

describe("the camera family in the platformer", () => {
  test("E7 subtraction: with the camera taken out, the rest seals to the identical order", () => {
    // A genre that never shakes — the cinematic platformer the plan names —
    // drops the entry and the parallax's read of what it wrote with it.
    const quiet = roster()
      .filter((system) => system.id !== "camera/shake")
      .map((system) => ({
        ...system,
        reads: system.reads.filter((key) => key !== "camera"),
      }));
    expect(sealSystems(quiet).order).toEqual(DOCUMENTED_ORDER.filter((id) => id !== "camera/shake"));
  });

  test("the offset is an input: what the follow wrote survives the tremor", () => {
    // The whole reason the shake stopped being a write into `camera.scrollX`.
    // Two frames of tremor with the follower moving underneath, and the view
    // ends where the follower put it rather than where the shake left it.
    const carrier = new ShakeCarrier();
    let view = { scrollX: 1_000, scrollY: 0 };
    view = carrier.shift(view, { x: 4, y: -2 });
    expect(view).toEqual({ scrollX: 1_004, scrollY: -2 });
    view = { scrollX: view.scrollX + 8, scrollY: view.scrollY };
    view = carrier.shift(view, NO_SHAKE);
    expect(view).toEqual({ scrollX: 1_008, scrollY: 0 });
  });

  test("the family gates its own block, by name", () => {
    expect(parsePlatformerCameraBlock(PREPARED_RUNTIME_BLOCKS).published).toBe(true);
    expect(() =>
      parsePlatformerCameraBlock({ ...PREPARED_RUNTIME_BLOCKS, maps: "platformer-maps-block-v2" }),
    ).toThrow('manifest block "maps" is published as platformer-maps-block-v2');
  });
});

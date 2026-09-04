// The platformer's frame, as declarations.
//
// `PreparedStageScene.update` used to be seventy method calls in a hand-written
// order, on `performance.now()`, with the edges that order encodes living in
// comments beside the calls. This module is the strangler: every step of that
// frame becomes a `GameSystem` with declared reads and writes, the roster is
// sealed by the kernel, and the order the frame runs in is derived rather than
// typed out. Nothing about the steps themselves moves — the scene still holds
// the state and still owns the methods — which is the point. A rebuild on
// families has no "before" to be compared against; this wrapper is what turns
// the hand order into data so that every later extraction has one.
//
// What the wrapper does and does not buy, stated plainly so nobody reads more
// into it than is there:
//
//   - It buys the order. `sealSystems` derives it from writes-before-reads and
//     the explicit `after` edges, and `frame-roster.test.ts` pins the result.
//     A declaration edit that reorders the frame is a diff in that test.
//   - It buys the edge list. Every ordering constraint that used to be a
//     comment is now either a declared read or an `after`, and every read of a
//     value produced *later* in the frame — a feedback read — is named at the
//     read site below rather than declared, because declaring it would assert
//     an order the frame cannot satisfy. The sealer refuses those; this file
//     records each refusal it made on the first attempt.
//   - It does not buy the write trap. The steps mutate the scene's own fields,
//     not the world object, so `devTrap` has nothing to check for any slice the
//     scene still holds. Three slices are real world state — `intent`, `hold`
//     and `clock` — and those the trap does check. The rest are names.
//
// The clock is the tick's. `now` is `step.now`, the engine's frame time, which
// under the replay harness is the same virtual clock the simulation is stepped
// on. There is no `performance.now()` in the frame.

import type { FixedStep, GameSystem, SealedSystems } from "@/lib/kernel/systems";
import { sealSystems } from "@/lib/kernel/systems";
import { createClock, createClockSystem, type ClockState } from "@/lib/families/clock/clock";
import { platformerClockHolders } from "./clock";
import { createPlatformerCameraSystem } from "./camera";
import type { ShakeOffset } from "@/lib/families/camera";
import { NEUTRAL_PLAYER_INTENT, type PlayerIntent } from "./player-intent";

/**
 * The slices the frame is ordered over.
 *
 * Three of them are state this world actually holds: the frame's one keyboard
 * reading, the conversation hold, and the elapsed simulation time the
 * integrators are handed. The rest are declared and not held — the scene still
 * owns the `Player`, the `Mob` list, the `ItemSystem` and the rest — so they
 * are typed `?: never`: a name a system may declare against and nothing may
 * write through. Each becomes real storage on the step that extracts its class.
 */
export interface PlatformerFrameWorld {
  /**
   * This frame's keyboard reading, taken once and handed to both sides.
   *
   * Once, because `JustDown` spends the latch: a second reader downstream of
   * the first sees a key nobody pressed, which is the defect step 0 measured at
   * 529 frames of the golden.
   */
  intent: PlayerIntent;
  /** True while a conversation holds the simulation; every system below the hold reads it. */
  hold: boolean;
  /**
   * The simulation clock: elapsed milliseconds this frame, and their integral.
   *
   * Owned by the `clock` family rather than by a hitstop step of the genre's
   * own, which is what makes "how much time passed" one decision with one
   * author for both of this frame's holders.
   */
  clock: ClockState;

  /** The constructed world — map, terrain, decks, layers, camera bounds, the actors' existence. */
  readonly stage?: never;
  /** The scene's own command keys, distinct from the ones the controller binds. */
  readonly keys?: never;
  /** The player controller and its sprite. */
  readonly player?: never;
  /** The creatures, their instance ids, and the population director. */
  readonly mobs?: never;
  /** The shot pool. */
  readonly projectiles?: never;
  /** Dropped items on the ground, and the bag they are collected into. */
  readonly items?: never;
  /** Hitstop, sparks, swings and the shake sources they arm. */
  readonly impact?: never;
  /** The camera's scroll and zoom. */
  readonly camera?: never;
  /** The arriving-map announcement. */
  readonly banner?: never;
  /** The stat log's notices and the progression they report. */
  readonly statLog?: never;
  /** The conversation in flight and the panel that draws it. */
  readonly dialogue?: never;
  /** The NPCs and their talk prompts. */
  readonly npcs?: never;
  /** The contact shadow rings. */
  readonly shadows?: never;
  /** The parallax tile sprites' scroll offsets. */
  readonly layers?: never;
  /** A map entry asked for during the frame, taken once the frame is over. */
  readonly mapEntry?: never;
  /** Who is driving: the human, or the bot. */
  readonly control?: never;
  /** The developer kit in force, and the weapon profile resolved from it. */
  readonly kit?: never;
  /** The debug overlay's visibility and text. */
  readonly debug?: never;
  /** What the runtime named this frame. */
  readonly transcript?: never;
}

export type PlatformerFrameSystem = GameSystem<PlatformerFrameWorld>;

/** A fresh frame world. The three real slices start neutral; the rest are names. */
export function createPlatformerFrameWorld(): PlatformerFrameWorld {
  return { intent: NEUTRAL_PLAYER_INTENT, hold: false, clock: createClock() };
}

/**
 * The steps of the frame, as the scene implements them.
 *
 * One method per system, named for what it does rather than for the private
 * method it forwards to, so this interface reads as the frame and the scene
 * stays free to rename its own internals. The scene passes an object of bound
 * arrows; nothing here reaches into it.
 */
export interface PlatformerFrameSteps {
  toggleDebugOverlay(): void;
  updateAutoPlayToggle(nowMs: number): void;
  updateKitSwitch(nowMs: number): void;
  updateDebugOverlay(): void;
  updateMapBanner(nowMs: number): void;
  /** Read the controller's bound keys into this frame's intent. Destructive; see the system. */
  readIntent(): PlayerIntent;
  /** Whether a conversation is open, asked before the input that may close it. */
  dialogueOpen(): boolean;
  updateDialogueInput(intent: PlayerIntent): void;
  updateStatLog(nowMs: number): void;
  /** Whether a blow is still holding the simulation. */
  hitstopActive(nowMs: number): boolean;
  updatePlayer(simulationDeltaMs: number, nowMs: number, intent: PlayerIntent): void;
  /** Advance every authored set-piece: armed, engaged, ended. */
  stepSetPieces(nowMs: number): void;
  updateMobPopulation(nowMs: number): void;
  stepMobs(simulationDeltaMs: number, nowMs: number): void;
  updateProjectiles(simulationDeltaMs: number, nowMs: number): void;
  collectDrops(simulationDeltaMs: number, nowMs: number): void;
  updateImpact(nowMs: number): void;
  /** What is shaking the view this frame; the genre decides which events do. */
  impactShake(nowMs: number): ShakeOffset;
  /** Move the view from the offset it carries to this one. */
  carryCameraShake(next: ShakeOffset): void;
  updateInteractionPrompt(): void;
  updateContactShadows(): void;
  scrollParallaxLayers(): void;
  applyPendingMapEntry(): void;
}

/** Every system below the conversation hold returns at its first line while one is open. */
function held(world: PlatformerFrameWorld): boolean {
  return world.hold;
}

/**
 * The full roster, in registration order.
 *
 * Registration order is the frame as it was written by hand; the sealed order
 * is derived from the declarations and asserted in `frame-roster.test.ts`. The
 * two agree, which is the whole claim of this step: the hand order was already
 * the order the declarations imply, and now it is written down as data.
 */
export function assemblePlatformerSystems(
  steps: PlatformerFrameSteps,
): readonly PlatformerFrameSystem[] {
  return [
    {
      id: "debug/overlay-toggle",
      contractVersion: "debug-overlay-system-v1",
      reads: ["keys"],
      writes: ["debug"],
      update: () => steps.toggleDebugOverlay(),
    },
    {
      id: "control/auto-play",
      contractVersion: "control-system-v1",
      reads: ["keys"],
      writes: ["control", "statLog"],
      update: (_world, step) => steps.updateAutoPlayToggle(step.now),
    },
    {
      id: "kit/switch",
      contractVersion: "kit-system-v1",
      reads: ["keys", "kit"],
      // A kit switch re-enters the map, which rebuilds the stage in the middle
      // of the frame — before anything that steps it, which is why the write is
      // declarable at all. The end-of-frame rebuild is not; see "map/entry".
      writes: ["kit", "statLog", "stage"],
      update: (_world, step) => steps.updateKitSwitch(step.now),
    },
    {
      id: "debug/overlay",
      contractVersion: "debug-overlay-system-v1",
      // Feedback reads of `player`, `control` and `items`, undeclared: the
      // health, the level, the bot's last decision and the bag are all of the
      // previous frame, because the systems that write them are sealed after
      // this one. The overlay is presentation lagging a frame, which is the
      // ordinary shape; what is not ordinary is that half of `control` — the
      // auto-play flag itself — *is* this frame's, so the read is of mixed age
      // and the `after` edge buys the position that half needs.
      reads: ["kit"],
      writes: ["debug"],
      after: ["control/auto-play"],
      update: () => steps.updateDebugOverlay(),
    },
    {
      id: "banner/map-name",
      contractVersion: "banner-system-v1",
      reads: [],
      writes: [],
      owns: ["banner"],
      update: (_world, step) => steps.updateMapBanner(step.now),
    },
    {
      id: "intent/keyboard",
      contractVersion: "intent-system-v1",
      // `stage` because the reading goes through the controller the stage
      // built, and a kit switch replaces that controller earlier in this same
      // frame. `keys` is a read and not a write, with one qualification worth
      // stating: `JustDown` spends the latch, so this reading is destructive
      // for the edges it takes. It is modelled as a read because the edges it
      // spends — space, J/X/Z, Q, I — are disjoint from every key the scene
      // itself reads with `JustDown`, which `frame-roster.test.ts` asserts
      // rather than assumes. That disjointness is what step 0 established, at
      // 529 frames of the golden.
      reads: ["keys", "stage"],
      writes: [],
      owns: ["intent"],
      update: (world) => {
        world.intent = steps.readIntent();
      },
    },
    {
      id: "dialogue/input",
      contractVersion: "dialogue-system-v1",
      reads: ["keys", "intent"],
      writes: ["dialogue"],
      owns: ["hold"],
      update: (world) => {
        // Asked before the input runs, because the input may close the
        // conversation and the frame it closes on is still held — which is what
        // the hand-written `return` did.
        world.hold = steps.dialogueOpen();
        if (world.hold) steps.updateDialogueInput(world.intent);
      },
    },
    {
      id: "progression/stat-log",
      contractVersion: "stat-log-system-v1",
      reads: ["hold"],
      writes: ["statLog"],
      update: (world, step) => {
        if (held(world)) return;
        steps.updateStatLog(step.now);
      },
    },
    // The `clock` family, instantiated into this genre's two holders. It used
    // to be a genre step called "clock/hitstop" that knew about exactly one of
    // them and left the other — the conversation — to be re-checked at the top
    // of every system below it. The holders themselves are in `clock.ts`, with
    // the block the family gates for itself.
    createClockSystem<PlatformerFrameWorld>({
      slice: "clock",
      // `hold` is this frame's, written by `dialogue/input` above; the sealer
      // is what puts this system after it.
      reads: ["hold"],
      holders: platformerClockHolders(steps),
    }),
    {
      id: "player/update",
      contractVersion: "player-system-v1",
      // Feedback read of `mobs`, undeclared: every creature this step touches is
      // where it stood at the end of the previous frame, and the strike it
      // consumes was committed by `mob.update` a frame ago. Declaring the read
      // closes the cycle player/update -> mobs/population -> mobs/step ->
      // player/update, which is refusal 2 — and it is the audit's own
      // "the mob's committed strike read a frame later by the player update".
      //
      // Feedback read of `items`, undeclared: the bag a throw spends a round
      // from and a drink spends a flask from is the one `items/collect` filled
      // at the end of the previous frame. Declaring it closes
      // player/update -> items/collect -> player/update (refusal 3).
      reads: ["hold", "clock", "intent", "keys", "kit", "control", "stage"],
      writes: [
        "player",
        "mobs",
        "items",
        "impact",
        "control",
        "dialogue",
        "mapEntry",
        "statLog",
        "transcript",
      ],
      update: (world, step) => {
        if (held(world)) return;
        steps.updatePlayer(world.clock.simulationDt, step.now, world.intent);
      },
    },
    {
      // The `director` family, instantiated into this genre's authored gates.
      // A set-piece is armed at a map anchor and fires when the player reaches
      // it, so it reads *this* frame's player position — which is what puts it
      // after the controller — and writes the body it stands behind into
      // `mobs`, which is what puts it before everything that steps one.
      id: "director/set-piece",
      contractVersion: "director-system-v1",
      // Feedback read of `mobs`, undeclared: a gate ends when the creature
      // standing in it is no longer alive, and the creature it is looking at is
      // the one `mobs/step` left at the end of the previous frame. Declaring
      // the read closes director/set-piece -> mobs/population -> mobs/step ->
      // director/set-piece, which is the same shape as refusal 2. A gate that
      // ends one frame late is a set-piece; a cycle is not a frame.
      reads: ["hold", "player", "stage"],
      writes: ["mobs", "transcript"],
      update: (world, step) => {
        if (held(world)) return;
        steps.stepSetPieces(step.now);
      },
    },
    {
      id: "mobs/population",
      contractVersion: "population-system-v1",
      // `player` is this frame's: the director places bodies against where the
      // player has already moved to. The two other things it reads are not.
      //
      // Feedback read of `mobs`, undeclared: it reports each live instance's
      // position to the director before `mobs/step` has moved any of them, so
      // the positions it reasons about are last frame's. That is the audit's
      // "the population director reads player and mob positions of mixed age",
      // and it is the reason `mobs/step` carries an explicit `after` instead.
      //
      // Feedback read of `camera`, undeclared: the director asks the camera
      // what is on screen before this frame's shake has been applied and before
      // the engine's follow has run, so the view it sees is the previous
      // frame's. Declaring it closes mobs/population -> mobs/step ->
      // projectiles/step -> impact/release -> camera/shake -> mobs/population,
      // which is refusal 5 — an edge the audit did not predict.
      reads: ["hold", "stage", "player"],
      writes: ["mobs", "transcript"],
      // The gate places its own body before the census counts the map. Both
      // write `mobs` and neither reads what the other wrote, so nothing in the
      // dataflow orders them; the edge is explicit for the same reason
      // `mobs/step` after `mobs/population` is, and it buys the set-piece's
      // creature the same treatment a spawned one gets — stepped on the frame
      // it arrives rather than a frame later.
      after: ["director/set-piece"],
      update: (world, step) => {
        if (held(world)) return;
        steps.updateMobPopulation(step.now);
      },
    },
    {
      id: "mobs/step",
      contractVersion: "mob-system-v1",
      reads: ["hold", "clock", "stage"],
      writes: ["mobs"],
      // The director hands this step the creatures it reserved, and it reserved
      // them having read the player where the player is *now* and the creatures
      // where they stood *last* frame — the mixed age the audit names. Both
      // systems write `mobs` and neither reads what the other wrote, so nothing
      // in the dataflow orders them; declaring a read of `mobs` here instead
      // closes mobs/step -> projectiles/step -> mobs/step (refusal 4), because
      // the shot pool legitimately reads this frame's positions and writes the
      // damage it deals back into them. So the edge is explicit.
      after: ["mobs/population"],
      update: (world, step) => {
        if (held(world)) return;
        steps.stepMobs(world.clock.simulationDt, step.now);
      },
    },
    {
      id: "projectiles/step",
      contractVersion: "projectile-system-v1",
      reads: ["hold", "clock", "mobs"],
      writes: ["projectiles", "mobs", "items", "impact", "statLog", "transcript"],
      update: (world, step) => {
        if (held(world)) return;
        steps.updateProjectiles(world.clock.simulationDt, step.now);
      },
    },
    {
      id: "items/collect",
      contractVersion: "item-system-v1",
      reads: ["hold", "clock", "player", "items"],
      writes: ["items", "transcript"],
      update: (world, step) => {
        if (held(world)) return;
        steps.collectDrops(world.clock.simulationDt, step.now);
      },
    },
    {
      id: "impact/release",
      contractVersion: "impact-system-v1",
      reads: ["hold", "impact"],
      writes: ["impact"],
      update: (world, step) => {
        if (held(world)) return;
        steps.updateImpact(step.now);
      },
    },
    // The `camera` family, instantiated into this genre's follow mode. The
    // frame does not compute a scroll here — the engine's follow does — so the
    // whole of the step is carrying the tremor a blow raised, which is what
    // "shake is an input" means once the offset is a value rather than a write
    // into `camera.scrollX`.
    createPlatformerCameraSystem(steps),
    {
      id: "npc/prompt",
      contractVersion: "npc-system-v1",
      reads: ["hold", "keys", "player", "stage"],
      writes: ["npcs", "dialogue"],
      update: (world) => {
        if (held(world)) return;
        steps.updateInteractionPrompt();
      },
    },
    {
      id: "shadows/contact",
      contractVersion: "contact-shadow-system-v1",
      reads: ["hold", "stage", "player", "mobs", "items"],
      writes: [],
      owns: ["shadows"],
      update: (world) => {
        if (held(world)) return;
        steps.updateContactShadows();
      },
    },
    {
      id: "parallax/scroll",
      contractVersion: "parallax-system-v1",
      reads: ["hold", "stage", "camera"],
      writes: [],
      owns: ["layers"],
      update: (world) => {
        if (held(world)) return;
        steps.scrollParallaxLayers();
      },
    },
    {
      id: "map/entry",
      contractVersion: "map-entry-system-v1",
      reads: ["hold", "mapEntry"],
      // Deferred write of `stage`, undeclared — the mirror image of a feedback
      // read, written down at the write site for the same reason. Entering a
      // map tears the world down and builds another; every system that steps
      // that world is sealed before this one, so the stage this writes is read
      // on the *following* frame and never on this one. Declaring the write
      // closes player/update -> map/entry -> player/update (refusal 6), the
      // player being both the system that asks for an entry and a reader of the
      // stage. What keeps the rebuild at the end of the frame is not the
      // dataflow but the `after` edge below, which names every system that is
      // still stepping the world this one replaces.
      writes: ["mapEntry"],
      after: ["npc/prompt", "shadows/contact", "parallax/scroll"],
      update: (world) => {
        if (held(world)) return;
        steps.applyPendingMapEntry();
      },
    },
  ];
}

/** Seal the platformer's frame. No system emits or consumes, so there is no queue to clear. */
export function sealPlatformerFrame(
  steps: PlatformerFrameSteps,
): SealedSystems<PlatformerFrameWorld> {
  return sealSystems(assemblePlatformerSystems(steps));
}

export type { FixedStep };

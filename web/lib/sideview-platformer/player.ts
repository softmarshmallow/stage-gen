// Player controller (Phase 7).
//
// Owns:
//   - WASD + arrow input → horizontal velocity                     (TC-080)
//   - State machine: idle / walk / run / jump / crouch / attack / hurt / climb
//   - Feet locked to heightmap surface during X movement           (TC-082)
//   - Attack hit-window query for the mob system                   (TC-084/085)
//
// The Phaser scene constructs one Player, calls update(dtSec) every frame,
// and reads .sprite / .state / .attacking for collision + camera follow.

import Phaser from "phaser";
import { SCENE_CONTENT_DEPTH } from "./depths";
import {
  headMatchedScale,
  masterSheetScale,
  playerSheetScaleForState,
  rebasedSheetScales,
  type ScaleReference,
} from "@/lib/sideview/sprite-scale";
import {
  type PlayerDamageResolution,
  type PlayerHealResolution,
  type PlayerHealthState,
  PLAYER_KNOCKBACK_VX,
  PLAYER_KNOCKBACK_VY,
  applyPlayerDamage,
  applyPlayerHealing,
  grownPlayerHealth,
  initialPlayerHealth,
  isPlayerInvulnerable,
  playerInvulnerabilityBlinkAlpha,
} from "./combat";
import { nextAttackHitTick, stepAttackWindow } from "./attack-window";
import { type PlayerIntent, playerIntent } from "./player-intent";
import {
  PLAYER_ATTACK_STATES,
  PLAYER_ATTACK_STATE_BY_MOTION,
  type PlayerState,
} from "./player-state";
import {
  weaponClassProfile,
  type WeaponClassProfile,
} from "./weapon-class";
import {
  DEATH_STRIP_FRAME_RATE,
  playerDamagePresentationState,
} from "./death-presentation";
import { terrainSurfaceY } from "./terrain";
import {
  anchorRepackedMotionFeet,
  anchorRepackedMotionHead,
  applyMotionPlayback,
  installMotionPlayback,
  type RuntimeMotionPlayback,
} from "@/lib/sideview/motion-playback";
import {
  PLATFORMER_COYOTE_MS,
  PLATFORMER_GRAVITY,
  PLATFORMER_RUN_SPEED,
  PLATFORMER_WALK_SPEED,
  PLATFORM_DROP_THROUGH_MS,
  PLATFORM_DROP_SETTLE_FRAMES,
  UPPER_PLATFORM_THICKNESS,
  advanceLadderMotion,
  ladderEntryAt,
  ladderJumpOffVelocity,
  platformDropThroughActive,
  resolveCrouchHorizontalVelocity,
  resolveJumpRequest,
  resolveTerrainStep,
  resolveTerrainWalk,
  resolveVerticalLanding,
  type ClimbableRole,
  type ClimbableZone,
  type PlayerSupport,
  type UpperPlatform,
} from "./vertical";

// The state vocabulary itself lives in `player-state.ts`, which imports nothing, so a module that
// needs to reason about a player state does not have to load Phaser to do it. Re-exported here
// because this is the file every consumer already reaches for.
export {
  PLAYER_ATTACK_STATES,
  PLAYER_ATTACK_STATE_BY_MOTION,
  type PlayerState,
} from "./player-state";

export type PlatformDropTraversalPhase =
  | "drop-commanded"
  | "underside-cleared"
  | "lower-support-landed"
  | "lower-support-settled"
  | "recovery-airborne"
  | "recovered";

export type PlayerTransitionKind =
  | "ladder-enter"
  | "ladder-exit"
  | "platform-land"
  | "platform-drop"
  | "platform-underside-clear"
  | "platform-lower-land"
  | "platform-lower-settle"
  | "platform-recovery-launch"
  | "platform-recovery-land"
  | "air-jump"
  | "terrain-step-off"
  | "terrain-step-block";

export type PlayerStateSnapshot = {
  state: PlayerState;
  facing: "left" | "right";
  x: number;
  y: number;
  column: number;
  vx: number;
  vy: number;
  airborne: boolean;
  /** Mid-air jumps spent since the last support. Reset by landing or a ladder. */
  airJumpsUsed: number;
  attackActive: boolean;
  hp: number;
  maxHp: number;
  invulnerable: boolean;
  defeated: boolean;
  support: PlayerSupport;
  supportId: string | null;
  ladderId: string | null;
  platformId: string | null;
  dropThroughPlatformId: string | null;
  dropTraversalPhase: PlatformDropTraversalPhase | null;
  dropTraversalPlatformId: string | null;
  dropTraversalPlatformBottomY: number | null;
  dropTraversalLowerSupport: "terrain" | "platform" | null;
  dropTraversalLowerSupportId: string | null;
  dropTraversalLowerSupportY: number | null;
  dropTraversalStableFrames: number;
  renderBounds: Readonly<{
    left: number;
    top: number;
    right: number;
    bottom: number;
  }>;
  climbAnimationKey: string | null;
  climbTextureKey: string | null;
  climbFrame: number | null;
  climbAnimationPaused: boolean | null;
  rearFacing: boolean;
};

export interface PlayerOpts {
  scene: Phaser.Scene;
  startX: number;
  startY: number;
  tilePx: number;
  worldWidthPx: number;
  baselineY: number; // GROUND_BASELINE_Y
  heightFn: (col: number) => number; // returns column height in tiles
  targetSpriteHeight: number; // px
  platforms?: readonly UpperPlatform[];
  climbables?: readonly ClimbableZone[];
  maximumAirJumps: number;
  combatEnabled: boolean;
  /**
   * How the package's weapon class attacks.
   *
   * Passed in rather than imported, because the controller must not decide which class a package
   * fights with - the scene reads that from the manifest, and a controller that reached for the
   * table itself would be a second place the answer is chosen. Omitted for the standalone and
   * legacy tag runtimes, which have no manifest and swing at the melee defaults.
   */
  weaponClass?: WeaponClassProfile;
  /** Authored starting/max health for this run. */
  startingHealth?: number;
  onTransition?: (
    kind: PlayerTransitionKind,
    data: Record<string, string | number | boolean>,
  ) => void;
  /** Resolved presentation per state; omitted entries use standalone-runtime defaults. */
  motionPlayback?: Partial<Record<PlayerState, RuntimeMotionPlayback>>;
  /**
   * Climb artwork per climbable role. Climbing is one state to the controller - the physics of a
   * rope and a ladder are identical - but not one pose, so the role a zone declares selects the
   * strip rather than the state machine carrying two climbing states.
   */
  climbArtwork?: Partial<Record<ClimbableRole, ClimbArtwork>>;
  /**
   * Published anatomical scale reference per texture key.
   */
  scaleReferences: ReadonlyMap<string, ScaleReference>;
  /** States whose authored pose height is meaningful and must retain atlas scale. */
  preserveSourceScaleStates?: readonly PlayerState[];
  /**
   * Published per-state draw-scale multipliers, keyed by texture key and relative to the
   * baseline. When present it is the sole authority for sheet scale: every state composes its
   * multiplier with the baseline's anchor, and a state without one is refused rather than
   * silently inheriting the baseline's scale.
   */
  stateRebase?: ReadonlyMap<string, number>;
}

/** Every player state, in one place so animations and scale resolution cannot diverge. */
const PLAYER_STATES: readonly PlayerState[] = [
  "idle",
  "walk",
  "run",
  "jump",
  "crouch",
  "attack",
  "ranged_attack",
  "hurt",
  "death",
  "climb",
];

/** Current player roles measured by the producer; hurt remains an optional current role. */
const MEASURED_PLAYER_STATES: readonly PlayerState[] = [
  "idle",
  "walk",
  "run",
  "jump",
  "crouch",
  "attack",
];

/** One climbable role's strip, animation, and playback. */
export type ClimbArtwork = Readonly<{
  textureKey: string;
  animKey: string;
  playback: RuntimeMotionPlayback;
  /** Which edge this motion's frames register against, as published by the manifest. */
  anchor: MotionAnchor;
}>;

/** Which edge a motion's frames register against. Mirrors the authored contract. */
export type MotionAnchor = "bottom" | "top";

const CLIMBABLE_ROLES: readonly ClimbableRole[] = ["ladder", "rope"];

/**
 * Resolve one role's climb strip.
 *
 * A prepared package publishes `character_climb_ladder` and `character_climb_rope`. The
 * standalone and legacy tag runtimes publish a single `character_climb`, so a role whose own
 * strip was never registered falls back to that shared one rather than failing to animate.
 */
function defaultClimbArtwork(
  scene: Phaser.Scene,
  role: ClimbableRole,
): ClimbArtwork {
  const roleTextureKey = `character_climb_${role}`;
  const roleSpecific = scene.textures.exists(roleTextureKey);
  return Object.freeze({
    textureKey: roleSpecific ? roleTextureKey : "character_climb",
    animKey: roleSpecific ? `player_climb_${role}` : "player_climb",
    playback: Object.freeze({
      mode: "gameplay_driven",
      canonical_frame_indices: Object.freeze(roleSpecific ? [0, 1] : [0, 1, 2, 3]),
    }) as RuntimeMotionPlayback,
    // The shared legacy strip was drawn and packed for feet; only role strips are grip-registered.
    anchor: roleSpecific ? "top" : "bottom",
  });
}

const DEFAULT_FRAME_RATES: Record<PlayerState, number> = {
  idle: 4,
  walk: 8,
  run: 14,
  jump: 8,
  crouch: 6,
  attack: 12,
  // The cast strip is authored at 10 fps where the swing is authored at 12; a throw commits for
  // longer than a swing, and that is the cost the extra reach is bought with.
  ranged_attack: 10,
  hurt: 7,
  death: DEATH_STRIP_FRAME_RATE,
  climb: 9,
};

function defaultMotionPlayback(state: PlayerState): RuntimeMotionPlayback {
  if (state === "climb") {
    return Object.freeze({
      mode: "gameplay_driven",
      canonical_frame_indices: Object.freeze([0, 1, 2, 3]),
    });
  }
  return Object.freeze({
    mode:
      PLAYER_ATTACK_STATES.has(state) ||
      state === "jump" ||
      state === "hurt" ||
      state === "death"
        ? "once"
        : "loop",
    canonical_frame_indices: Object.freeze([0, 1, 2, 3]),
    frames_per_second: DEFAULT_FRAME_RATES[state],
  });
}

const HURT_DURATION_MS = 600;

export class Player {
  readonly sprite: Phaser.GameObjects.Sprite;
  state: PlayerState = "idle";
  facing: "left" | "right" = "right";
  vx = 0;
  vy = 0;
  airborne = false;
  support: PlayerSupport = "terrain";
  supportId: string | null = null;
  ladderId: string | null = null;
  /** Mid-air jumps spent since the last grounded or ladder support. */
  airJumpsUsed = 0;
  /** Deadline until which a lost support still buys a full grounded jump. */
  private coyoteExpiresAtMs: number | null = null;
  /** Column face currently stopping horizontal motion, for edge-triggered logs. */
  private blockedColumn: number | null = null;
  private opts: PlayerOpts;
  private readonly motionPlayback: Readonly<Record<PlayerState, RuntimeMotionPlayback>>;
  private readonly climbArtwork: Readonly<Record<ClimbableRole, ClimbArtwork>>;
  private readonly tallestFrameHeights = new Map<string, number>();
  private cursors?: Phaser.Types.Input.Keyboard.CursorKeys;
  private wasdKeys?: {
    up: Phaser.Input.Keyboard.Key;
    down: Phaser.Input.Keyboard.Key;
    left: Phaser.Input.Keyboard.Key;
    right: Phaser.Input.Keyboard.Key;
    jump: Phaser.Input.Keyboard.Key;
    attack1: Phaser.Input.Keyboard.Key;
    attack2: Phaser.Input.Keyboard.Key;
    attack3: Phaser.Input.Keyboard.Key;
    shift: Phaser.Input.Keyboard.Key;
    inventory: Phaser.Input.Keyboard.Key;
    useHealing: Phaser.Input.Keyboard.Key;
  };
  private attackUntil = 0;
  private attackStarted = 0;
  /** Blows already landed by the running action; reset when a fresh action commits. */
  private attackHitTicksFired = 0;
  /** Deadline for the authored hurt presentation; it does not lock player control. */
  private hurtUntil = 0;
  private activeClimbable?: ClimbableZone;
  private climbFrame: number | null = null;
  /** Sprite scale for textures sliced from the character's master sheet. */
  private masterSheetScale = 1;
  /** Sprite scale by texture key, for sheets that do not share the master's geometry. */
  private readonly sheetScale = new Map<string, number>();
  private dropThroughPlatformId: string | null = null;
  private dropThroughUntil = 0;
  private dropTraversal?: {
    platformId: string;
    platformLeft: number;
    platformRight: number;
    platformDeckY: number;
    platformBottomY: number;
    phase: PlatformDropTraversalPhase;
    lowerSupport: "terrain" | "platform" | null;
    lowerSupportId: string | null;
    lowerSupportY: number | null;
    stableFrames: number;
  };
  /** Hit points, invulnerability window and defeat, owned here because they are gameplay. */
  private health: PlayerHealthState = initialPlayerHealth();

  /** Set while the attack swing is in its hit window. */
  attackActive = false;

  constructor(opts: PlayerOpts) {
    if (!Number.isSafeInteger(opts.maximumAirJumps) || opts.maximumAirJumps < 0) {
      throw new Error("maximumAirJumps must be a nonnegative integer");
    }
    this.opts = opts;
    this.health = initialPlayerHealth(opts.startingHealth);
    this.motionPlayback = Object.freeze(
      Object.fromEntries(
        PLAYER_STATES.map((state) => [
          state,
          opts.motionPlayback?.[state] ?? defaultMotionPlayback(state),
        ]),
      ) as Record<PlayerState, RuntimeMotionPlayback>,
    );

    const scene = opts.scene;
    this.climbArtwork = Object.freeze(
      Object.fromEntries(
        CLIMBABLE_ROLES.map((role) => [
          role,
          opts.climbArtwork?.[role] ?? defaultClimbArtwork(scene, role),
        ]),
      ) as Record<ClimbableRole, ClimbArtwork>,
    );

    // Build animations for each state once. `climb` is skipped here and installed per climbable
    // role below, because one controller state maps to one strip per role.
    for (const st of PLAYER_STATES) {
      if (st === "climb") continue;
      const animKey = `player_${st}`;
      const texKey = stateTextureKey(st);
      if (!scene.anims.exists(animKey) && scene.textures.exists(texKey)) {
        installMotionPlayback(scene, animKey, texKey, this.motionPlayback[st]);
      }
    }
    for (const role of CLIMBABLE_ROLES) {
      const artwork = this.climbArtwork[role];
      if (
        !scene.anims.exists(artwork.animKey) &&
        scene.textures.exists(artwork.textureKey)
      ) {
        installMotionPlayback(
          scene,
          artwork.animKey,
          artwork.textureKey,
          artwork.playback,
        );
      }
    }

    const initialKey = stateTextureKey("idle");
    this.sprite = scene.add.sprite(opts.startX, opts.startY, initialKey, 0);
    this.sprite.setOrigin(0.5, 1.0);
    this.resolveSheetScales();
    this.applySheetScale(initialKey);
    this.sprite.setDepth(SCENE_CONTENT_DEPTH.player);
    applyMotionPlayback(
      this.sprite,
      "player_idle",
      initialKey,
      this.motionPlayback.idle,
    );
    anchorRepackedMotionFeet(this.sprite);

    this.bindInput();
  }

  /**
   * Work out the sprite scale each state's source sheet needs.
   *
   * Each required sheet carries its own producer-published anatomical measurement. Matching each
   * extent to idle is what preserves apparent character size across unrelated source canvases and
   * poses. Optional reaction and terminal strips retain the anchored master-sheet scale because
   * their producer roles do not yet publish measurements.
   */
  private resolveSheetScales(): void {
    const scene = this.opts.scene;
    const idleKey = stateTextureKey("idle");
    this.masterSheetScale = masterSheetScale(
      this.opts.targetSpriteHeight,
      sheetFrameHeight(scene, idleKey, 0),
    );

    const rebase = this.opts.stateRebase;
    if (rebase !== undefined) {
      // The producer judged every atlas against the baseline on one plate, so the runtime
      // multiplies rather than re-measuring. This is the whole contract: a ratio the pixels
      // cannot yield, composed with the magnitude the baseline anchors.
      for (const [key, scale] of rebasedSheetScales(this.masterSheetScale, rebase)) {
        this.sheetScale.set(key, scale);
      }
      return;
    }

    // Idle sets the size the character reads at; every other measured sheet is matched to it.
    const references = this.opts.scaleReferences;
    const idleReference = references.get(idleKey);
    if (!idleReference) {
      throw new Error("current player requires character_idle scale reference");
    }
    const reference = {
      extentPixels: idleReference.extentPixels,
      scale: this.masterSheetScale,
    };
    for (const state of MEASURED_PLAYER_STATES) {
      const key = stateTextureKey(state);
      const sheetReference = references.get(key);
      if (!sheetReference) {
        throw new Error(`current player requires ${key} scale reference`);
      }
      this.sheetScale.set(
        key,
        playerSheetScaleForState({
          state,
          masterSheetScale: this.masterSheetScale,
          measuredSheetScale: headMatchedScale(reference, sheetReference),
          preserveSourceScaleStates:
            this.opts.preserveSourceScaleStates ?? Object.freeze([]),
        }),
      );
    }
    // Climb is measured per climbable role rather than per state: one controller state resolves to
    // one strip per role, and a package legitimately ships only the roles its maps place, so a
    // role without a published measurement is skipped instead of rejected.
    for (const role of CLIMBABLE_ROLES) {
      const key = this.climbArtwork[role].textureKey;
      const sheetReference = references.get(key);
      if (!sheetReference || this.sheetScale.has(key)) continue;
      this.sheetScale.set(
        key,
        playerSheetScaleForState({
          state: "climb",
          masterSheetScale: this.masterSheetScale,
          measuredSheetScale: headMatchedScale(reference, sheetReference),
          preserveSourceScaleStates:
            this.opts.preserveSourceScaleStates ?? Object.freeze([]),
        }),
      );
    }
  }

  /** Resolved per-texture draw scales, read-only, so QA probes can see what will be applied. */
  resolvedSheetScales(): ReadonlyMap<string, number> {
    return new Map(this.sheetScale);
  }

  /** Apply the scale belonging to `textureKey`'s source sheet. */
  private applySheetScale(textureKey: string): void {
    const measured = this.sheetScale.get(textureKey);
    if (measured !== undefined) {
      this.sprite.setScale(measured);
      return;
    }
    if (this.opts.stateRebase !== undefined) {
      // A published rebase covers every state the actor ships. Falling back here would restore
      // the defect the contract removes: hurt and death inheriting the baseline's scale and
      // collapsing on screen.
      throw new Error(`current player texture ${textureKey} has no published rebase multiplier`);
    }
    // Reaction and terminal strips are optional producer roles without published measurements.
    // Their explicit current behavior is to retain the anchored master-sheet scale.
    if (
      textureKey === "character_hurt" ||
      textureKey === "character_death"
    ) {
      this.sprite.setScale(this.masterSheetScale);
      return;
    }
    throw new Error(`current player texture ${textureKey} has no resolved scale`);
  }

  private bindInput() {
    const kb = this.opts.scene.input.keyboard;
    if (!kb) return;
    this.cursors = kb.createCursorKeys();
    this.wasdKeys = {
      up: kb.addKey(Phaser.Input.Keyboard.KeyCodes.W),
      down: kb.addKey(Phaser.Input.Keyboard.KeyCodes.S),
      left: kb.addKey(Phaser.Input.Keyboard.KeyCodes.A),
      right: kb.addKey(Phaser.Input.Keyboard.KeyCodes.D),
      jump: kb.addKey(Phaser.Input.Keyboard.KeyCodes.SPACE),
      attack1: kb.addKey(Phaser.Input.Keyboard.KeyCodes.J),
      attack2: kb.addKey(Phaser.Input.Keyboard.KeyCodes.X),
      attack3: kb.addKey(Phaser.Input.Keyboard.KeyCodes.Z),
      shift: kb.addKey(Phaser.Input.Keyboard.KeyCodes.SHIFT),
      inventory: kb.addKey(Phaser.Input.Keyboard.KeyCodes.I),
      useHealing: kb.addKey(Phaser.Input.Keyboard.KeyCodes.Q),
    };
  }

  /**
   * Read the bound keyboard into this frame's intent.
   *
   * The only impure part of input handling, and deliberately the thinnest: it converts Phaser key
   * state into plain booleans and stops there. Edge-triggered actions go through `JustDown`, which
   * consumes the latch, so this must be called exactly once per frame — including on frames the
   * caller intends to throw the result away, since a request that is never read stays armed and
   * fires later out of context.
   */
  readKeyboardIntent(): PlayerIntent {
    const k = this.wasdKeys;
    const c = this.cursors;
    return playerIntent({
      left: !!(k?.left.isDown || c?.left?.isDown),
      right: !!(k?.right.isDown || c?.right?.isDown),
      up: !!(k?.up.isDown || c?.up?.isDown),
      down: !!(k?.down.isDown || c?.down?.isDown),
      run: !!k?.shift.isDown,
      jump: !!(k?.jump && Phaser.Input.Keyboard.JustDown(k.jump)),
      attack: !!(
        k &&
        (Phaser.Input.Keyboard.JustDown(k.attack1) ||
          Phaser.Input.Keyboard.JustDown(k.attack2) ||
          Phaser.Input.Keyboard.JustDown(k.attack3))
      ),
      useHealing: !!(
        k?.useHealing && Phaser.Input.Keyboard.JustDown(k.useHealing)
      ),
      toggleInventory: !!(
        k?.inventory && Phaser.Input.Keyboard.JustDown(k.inventory)
      ),
    });
  }

  /** Release this controller's scene bindings. */
  destroy(): void {
    this.sprite.destroy();
  }

  /**
   * Called every frame from the scene with this frame's intent.
   *
   * The intent's source is not this controller's business: a keyboard, an automated policy and a
   * replay all reach the physics through the same nine booleans. Combat is the one action gated
   * here rather than at the source, because whether a package has combat at all is a property of
   * the package the controller was built for, not of whoever is asking to swing.
   */
  update(dtMs: number, nowMs: number, intent: PlayerIntent) {
    const dt = dtMs / 1000;
    const left = intent.left;
    const right = intent.right;
    const down = intent.down;
    const up = intent.up;
    const shift = intent.run;
    const wantsJump = intent.jump;
    const wantsAttack = intent.attack && this.opts.combatEnabled;

    // Damage is resolved by the scene after this controller has already stepped for the frame,
    // so `takeDamage` enters its presentation synchronously and this branch owns every later
    // reaction frame. Hurt is feedback, not a stun: ordinary movement and traversal remain live
    // while invulnerability blinks the sprite. Only terminal defeat locks input.
    const hurtPresentationAvailable = this.hasHurtPresentation();
    const deathPresentationAvailable = this.hasDeathPresentation();
    const hurtReaction = hurtPresentationAvailable && this.state === "hurt";
    const hurtMotionActive = hurtReaction && nowMs < this.hurtUntil;
    const controlsLocked = this.health.defeated;
    if (controlsLocked) this.vx = 0;
    this.sprite.setAlpha(playerInvulnerabilityBlinkAlpha(this.health, nowMs));

    // Active ladder traversal has priority over every movement/combat action.
    if (!controlsLocked && this.support === "climbable" && this.activeClimbable) {
      this.continueLadder({ dt, up, down, left, right, wantsJump });
      this.sprite.setFlipX(
        this.support === "climbable" ? false : this.facing === "left",
      );
      return;
    }

    // Entering a ladder has priority over platform drop-through.
    const entry = controlsLocked
      ? null
      : ladderEntryAt({
          climbables: this.opts.climbables ?? [],
          support: this.support,
          supportId: this.supportId,
          x: this.sprite.x,
          footY: this.sprite.y,
          up,
          down,
        });
    if (entry) {
      const entrySupport = this.support;
      this.activeClimbable = entry.ladder;
      this.ladderId = entry.ladder.id;
      this.setSupport("climbable", entry.ladder.id);
      this.vx = 0;
      this.vy = 0;
      this.sprite.x = entry.ladder.centerX;
      this.clearAttack();
      this.opts.onTransition?.("ladder-enter", {
        ladderId: entry.ladder.id,
        from: entrySupport,
        direction: entry.direction,
      });
      this.continueLadder({ dt, up, down, left, right, wantsJump: false });
      this.sprite.setFlipX(
        this.support === "climbable" ? false : this.facing === "left",
      );
      return;
    }

    this.advanceDropTraversalSettle();

    // Determine target horizontal velocity.
    let targetVx = this.vx;
    if (!controlsLocked) {
      targetVx = 0;
      if (left && !right) {
        targetVx = -(shift ? PLATFORMER_RUN_SPEED : PLATFORMER_WALK_SPEED);
        this.facing = "left";
      } else if (right && !left) {
        targetVx = shift ? PLATFORMER_RUN_SPEED : PLATFORMER_WALK_SPEED;
        this.facing = "right";
      }
      // An aim override outranks the step. Without it a policy that backs away from what it is
      // fighting turns its back on it, and the scene reads facing at the frame the blow leaves —
      // so the whole retreat would be spent attacking in the wrong direction.
      if (intent.face) this.facing = intent.face;
    }

    // Crouch selects the grounded low posture and caps horizontal speed.
    const crouching = !controlsLocked && down && this.support !== "air";
    if (crouching) {
      targetVx = resolveCrouchHorizontalVelocity(targetVx);
    }

    if (!controlsLocked) this.vx = targetVx;

    // Down+Space drops through the current one-way platform. A valid ladder
    // entry was already consumed above, so it cannot be shadowed by this.
    const dropping =
      !controlsLocked &&
      wantsJump &&
      down &&
      this.support === "platform" &&
      this.supportId !== null;
    if (dropping) {
      const platformId = this.supportId!;
      const platform = (this.opts.platforms ?? []).find(
        (candidate) => candidate.id === platformId,
      );
      if (!platform) {
        throw new Error("drop-through support must name an active platform");
      }
      this.dropThroughPlatformId = platformId;
      this.dropThroughUntil = nowMs + PLATFORM_DROP_THROUGH_MS;
      this.dropTraversal = {
        platformId,
        platformLeft: platform.left,
        platformRight: platform.right,
        platformDeckY: platform.deckY,
        platformBottomY: platform.deckY + UPPER_PLATFORM_THICKNESS,
        phase: "drop-commanded",
        lowerSupport: null,
        lowerSupportId: null,
        lowerSupportY: null,
        stableFrames: 0,
      };
      this.setSupport("air", null);
      this.vy = 0;
      this.opts.onTransition?.("platform-drop", {
        platformId,
        footY: this.sprite.y,
        platformLeft: this.dropTraversal.platformLeft,
        platformRight: this.dropTraversal.platformRight,
        platformBottomY: this.dropTraversal.platformBottomY,
      });
    } else if (!controlsLocked && wantsJump) {
      const jump = resolveJumpRequest({
        support: this.support,
        airJumpsUsed: this.airJumpsUsed,
        nowMs,
        coyoteExpiresAtMs: this.coyoteExpiresAtMs,
        crouching,
        maximumAirJumps: this.opts.maximumAirJumps,
      });
      if (jump.kind !== "none") {
        this.beginDropRecoveryIfReady();
        this.vy = jump.vy;
        this.airJumpsUsed = jump.airJumpsUsed;
        this.coyoteExpiresAtMs = null;
        if (jump.kind === "air") {
          this.opts.onTransition?.("air-jump", {
            airJumpsUsed: jump.airJumpsUsed,
            footY: this.sprite.y,
            vy: jump.vy,
          });
        }
        if (this.support !== "air") this.setSupport("air", null);
      }
    }

    // Horizontal motion, stopped by any column face standing above the feet.
    // A one-tile rise is a wall now, not a step, so the way up is a jump.
    const previousX = this.sprite.x;
    const walk = resolveTerrainWalk({
      previousX,
      nextX: Phaser.Math.Clamp(
        previousX + this.vx * dt,
        this.opts.tilePx / 2,
        this.opts.worldWidthPx - this.opts.tilePx / 2,
      ),
      footY: this.sprite.y,
      tilePixels: this.opts.tilePx,
      surfaceAt: (column) =>
        terrainSurfaceY(
          this.opts.heightFn(column),
          this.opts.tilePx,
          this.opts.baselineY,
        ),
    });
    this.sprite.x = walk.x;
    if (walk.blocked) {
      this.vx = 0;
      // Edge-triggered: held against a face this would otherwise log every
      // frame, and the interesting fact is arriving at the wall, not leaning
      // on it.
      if (this.blockedColumn !== walk.blockedColumn) {
        this.blockedColumn = walk.blockedColumn;
        this.opts.onTransition?.("terrain-step-block", {
          column: walk.blockedColumn!,
          footY: this.sprite.y,
          x: walk.x,
        });
      }
    } else {
      this.blockedColumn = null;
    }

    // Attack overrides locomotion anim state (still moves but plays the attack pose).
    const weapon = this.weaponProfile();
    const window = stepAttackWindow({
      profile: weapon,
      state: {
        attackUntil: this.attackUntil,
        attackStarted: this.attackStarted,
        attackActive: this.attackActive,
      },
      nowMs,
      requested: wantsAttack,
      blocked: controlsLocked || this.support === "climbable",
    });
    this.attackUntil = window.attackUntil;
    this.attackStarted = window.attackStarted;
    this.attackActive = window.attackActive;
    if (window.committed) this.attackHitTicksFired = 0;
    const attacking = window.attacking;

    // Vertical motion + one-way platform/terrain resolution.
    const col = Math.floor(this.sprite.x / this.opts.tilePx);
    const colH = this.opts.heightFn(col);
    const surfaceY = terrainSurfaceY(
      colH,
      this.opts.tilePx,
      this.opts.baselineY,
    );

    if (this.support === "platform") {
      const platform = (this.opts.platforms ?? []).find(
        (candidate) => candidate.id === this.supportId,
      );
      if (!platform || this.sprite.x < platform.left || this.sprite.x > platform.right) {
        this.openCoyoteWindow(nowMs);
        this.setSupport("air", null);
        this.vy = 0;
      } else {
        this.sprite.y = platform.deckY;
      }
    } else if (this.support === "terrain") {
      // Uphill columns are still absorbed, which keeps this heightfield's
      // column-locked climb. A descending column is a real ledge: the foot
      // holds its height and the airborne branch below drops it under gravity
      // instead of teleporting it onto the new surface.
      const step = resolveTerrainStep({
        footY: this.sprite.y,
        surfaceY,
      });
      this.sprite.y = step.footY;
      if (step.support === "air") {
        this.openCoyoteWindow(nowMs);
        this.setSupport("air", null);
        this.vy = 0;
        this.opts.onTransition?.("terrain-step-off", {
          footY: step.footY,
          surfaceY,
          column: col,
        });
      }
    }

    if (this.support === "air") {
      this.vy += PLATFORMER_GRAVITY * dt;
      const nextFootY = this.sprite.y + this.vy * dt;
      const ignoredPlatformId = this.activeDropThroughPlatform(nowMs);
      const landing = resolveVerticalLanding({
        x: this.sprite.x,
        previousFootY: this.sprite.y,
        nextFootY,
        vy: this.vy,
        terrainY: surfaceY,
        platforms: this.opts.platforms ?? [],
        ignoredPlatformId,
      });
      this.sprite.y = landing.footY;
      this.vy = landing.vy;
      this.setSupport(landing.support, landing.supportId);
      this.advanceDropTraversalAfterAirborne(landing);
      if (landing.support === "platform" && landing.supportId) {
        this.opts.onTransition?.("platform-land", {
          platformId: landing.supportId,
        });
      }
      if (
        landing.support !== "air" &&
        landing.supportId !== this.dropThroughPlatformId
      ) {
        this.clearDropThrough();
      }
    }

    // Compute new state.
    let next: PlayerState;
    const damagePresentation = playerDamagePresentationState({
      defeated: this.health.defeated,
      deathAvailable: deathPresentationAvailable,
      hurtAvailable: hurtPresentationAvailable,
      hurtMotionActive,
      airborne: this.support === "air",
    });
    if (damagePresentation !== null) next = damagePresentation;
    // Which attack pose is the weapon class's answer, not the controller's: the two states differ
    // only in which drawn strip they play and how long they commit for.
    else if (attacking) next = PLAYER_ATTACK_STATE_BY_MOTION[weapon.motionState];
    else if (this.support === "air") next = "jump";
    else if (crouching) next = "crouch";
    else if (this.vx !== 0 && shift) next = "run";
    else if (this.vx !== 0) next = "walk";
    else next = "idle";

    if (next !== this.state) {
      this.setState(next);
    }

    // Flip sprite by facing.
    this.sprite.setFlipX(this.facing === "left");
  }

  private continueLadder(input: Readonly<{
    dt: number;
    up: boolean;
    down: boolean;
    left: boolean;
    right: boolean;
    wantsJump: boolean;
  }>): void {
    const ladder = this.activeClimbable;
    if (!ladder) throw new Error("ladder support requires an active ladder");
    this.sprite.x = ladder.centerX;
    this.vx = 0;
    if (input.wantsJump) {
      const jump = ladderJumpOffVelocity({
        left: input.left,
        right: input.right,
        facing: this.facing,
      });
      this.vx = jump.vx;
      this.vy = jump.vy;
      this.sprite.x += this.vx * input.dt;
      this.sprite.y += this.vy * input.dt;
      const ladderId = ladder.id;
      this.activeClimbable = undefined;
      this.ladderId = null;
      this.setSupport("air", null);
      this.opts.onTransition?.("ladder-exit", {
        ladderId,
        to: "air",
      });
      this.setState("jump");
      return;
    }
    const motion = advanceLadderMotion({
      ladder,
      footY: this.sprite.y,
      deltaSeconds: input.dt,
      up: input.up,
      down: input.down,
    });
    this.sprite.y = motion.footY;
    this.vy = motion.vy;
    if (motion.exit === "platform") {
      const ladderId = ladder.id;
      this.activeClimbable = undefined;
      this.ladderId = null;
      this.setSupport("platform", ladder.platformId);
      this.opts.onTransition?.("ladder-exit", {
        ladderId,
        to: "platform",
      });
      this.setState("idle");
      return;
    }
    if (motion.exit === "terrain") {
      const ladderId = ladder.id;
      this.activeClimbable = undefined;
      this.ladderId = null;
      this.setSupport("terrain", null);
      this.opts.onTransition?.("ladder-exit", {
        ladderId,
        to: "terrain",
      });
      this.setState("idle");
      return;
    }
    if (this.state !== "climb") this.setState("climb");
    this.setClimbFrame(this.vy !== 0);
  }

  private setSupport(support: PlayerSupport, supportId: string | null): void {
    this.support = support;
    this.supportId = supportId;
    this.airborne = support === "air";
    if (support !== "air") {
      this.airJumpsUsed = 0;
      this.coyoteExpiresAtMs = null;
    }
  }

  /**
   * Open the grace window for a support lost by falling.
   *
   * Only fall sites call this. A jump clears the deadline instead, so the
   * window can never turn one press into two grounded launches.
   */
  private openCoyoteWindow(nowMs: number): void {
    if (this.support === "air") return;
    this.coyoteExpiresAtMs = nowMs + PLATFORMER_COYOTE_MS;
  }

  private activeDropThroughPlatform(nowMs: number): string | null {
    if (!this.dropThroughPlatformId) return null;
    const platform = (this.opts.platforms ?? []).find(
      (candidate) => candidate.id === this.dropThroughPlatformId,
    );
    if (
      !platform ||
      !platformDropThroughActive({
        nowMs,
        expiresAtMs: this.dropThroughUntil,
        footY: this.sprite.y,
        deckY: platform.deckY,
      })
    ) {
      this.clearDropThrough();
      return null;
    }
    return this.dropThroughPlatformId;
  }

  private clearDropThrough(): void {
    this.dropThroughPlatformId = null;
    this.dropThroughUntil = 0;
  }

  private advanceDropTraversalSettle(): void {
    const traversal = this.dropTraversal;
    if (!traversal || traversal.phase !== "lower-support-landed") return;
    if (
      this.support !== traversal.lowerSupport ||
      this.supportId !== traversal.lowerSupportId ||
      this.sprite.y !== traversal.lowerSupportY
    ) {
      return;
    }
    traversal.stableFrames += 1;
    if (traversal.stableFrames !== PLATFORM_DROP_SETTLE_FRAMES) return;
    traversal.phase = "lower-support-settled";
    this.opts.onTransition?.("platform-lower-settle", {
      platformId: traversal.platformId,
      support: traversal.lowerSupport!,
      footY: traversal.lowerSupportY!,
      stableFrames: traversal.stableFrames,
    });
  }

  private beginDropRecoveryIfReady(): void {
    const traversal = this.dropTraversal;
    if (!traversal || traversal.phase !== "lower-support-settled") return;
    if (this.support === "air" || this.support === "climbable") return;
    traversal.phase = "recovery-airborne";
    this.opts.onTransition?.("platform-recovery-launch", {
      platformId: traversal.platformId,
      support: this.support,
      footY: this.sprite.y,
      settledFootY: traversal.lowerSupportY!,
      stableFrames: traversal.stableFrames,
    });
  }

  private advanceDropTraversalAfterAirborne(
    landing: Readonly<{
      footY: number;
      support: "air" | "terrain" | "platform";
      supportId: string | null;
    }>,
  ): void {
    const traversal = this.dropTraversal;
    if (!traversal) return;
    const renderBounds = this.playerRenderBounds();
    const fullyClear =
      renderBounds.right < traversal.platformLeft ||
      renderBounds.left > traversal.platformRight ||
      renderBounds.bottom < traversal.platformDeckY ||
      renderBounds.top > traversal.platformBottomY;
    if (
      traversal.phase === "drop-commanded" &&
      fullyClear
    ) {
      traversal.phase = "underside-cleared";
      this.opts.onTransition?.("platform-underside-clear", {
        platformId: traversal.platformId,
        footY: landing.footY,
        playerLeft: renderBounds.left,
        playerTop: renderBounds.top,
        playerRight: renderBounds.right,
        playerBottom: renderBounds.bottom,
        platformLeft: traversal.platformLeft,
        platformRight: traversal.platformRight,
        platformDeckY: traversal.platformDeckY,
        platformBottomY: traversal.platformBottomY,
        separationAxis:
          renderBounds.left > traversal.platformRight ||
          renderBounds.right < traversal.platformLeft
            ? "horizontal"
            : "vertical",
      });
    }
    if (
      (traversal.phase === "drop-commanded" ||
        traversal.phase === "underside-cleared") &&
      landing.support !== "air" &&
      !(
        landing.support === "platform" &&
        landing.supportId === traversal.platformId
      )
    ) {
      traversal.phase = "lower-support-landed";
      traversal.lowerSupport = landing.support;
      traversal.lowerSupportId = landing.supportId;
      traversal.lowerSupportY = landing.footY;
      traversal.stableFrames = 1;
      this.opts.onTransition?.("platform-lower-land", {
        platformId: traversal.platformId,
        support: landing.support,
        footY: landing.footY,
      });
      return;
    }
    if (
      traversal.phase === "recovery-airborne" &&
      landing.support === "platform" &&
      landing.supportId === traversal.platformId
    ) {
      traversal.phase = "recovered";
      this.opts.onTransition?.("platform-recovery-land", {
        platformId: traversal.platformId,
        support: "platform",
        footY: landing.footY,
      });
    }
  }

  private clearAttack(): void {
    this.attackUntil = 0;
    this.attackStarted = 0;
    this.attackHitTicksFired = 0;
    this.attackActive = false;
  }

  private playerRenderBounds(): Readonly<{
    left: number;
    top: number;
    right: number;
    bottom: number;
  }> {
    const bounds = this.sprite.getBounds();
    return {
      left: bounds.left,
      top: bounds.top,
      right: bounds.right,
      bottom: bounds.bottom,
    };
  }

  /** The strip for the climbable currently held, or the ladder strip when none is. */
  private currentClimbArtwork(): ClimbArtwork {
    return this.climbArtwork[this.activeClimbable?.role ?? "ladder"];
  }

  private setClimbFrame(moving: boolean): void {
    const artwork = this.currentClimbArtwork();
    const textureKey = artwork.textureKey;
    if (!this.opts.scene.textures.exists(textureKey)) {
      throw new Error(`current climb texture ${textureKey} is missing`);
    }
    if (!this.opts.scene.anims.exists(artwork.animKey)) {
      throw new Error(`current climb animation ${artwork.animKey} is missing`);
    }
    const climbable = this.activeClimbable;
    const climbFrameCount = artwork.playback.canonical_frame_indices.length;
    const nextFrame =
      moving && climbable
        ? Math.floor(Math.abs(climbable.lowerSurfaceY - this.sprite.y) / 12) %
          climbFrameCount
        : (this.climbFrame ?? 0);
    if (
      this.sprite.anims.currentAnim?.key !== artwork.animKey ||
      !this.sprite.anims.isPlaying
    ) {
      this.sprite.play(artwork.animKey, true);
    }
    const animationFrame = this.sprite.anims.currentAnim?.frames[nextFrame];
    if (!animationFrame) {
      throw new Error(`current climb animation frame ${nextFrame} is missing`);
    }
    this.sprite.anims.setCurrentFrame(animationFrame);
    if (moving) this.sprite.anims.resume();
    else this.sprite.anims.pause();
    this.sprite.setFlipX(false);
    this.applySheetScale(textureKey);
    this.anchorMotionFrame(textureKey, artwork.anchor);
    this.climbFrame = nextFrame;
  }

  /**
   * Register the current frame against the edge its motion declares.
   *
   * Frames arrive as tight alpha crops, so the producer's packing offsets are already gone by the
   * time a sprite draws one: whatever edge the strip was packed against, every frame is flush. The
   * registration therefore has to be re-applied here from the authored anchor, against the tallest
   * frame of the same texture, or a hanging pose silently reverts to standing on its own feet.
   */
  private anchorMotionFrame(textureKey: string, anchor: MotionAnchor): void {
    if (anchor !== "top") {
      anchorRepackedMotionFeet(this.sprite);
      return;
    }
    anchorRepackedMotionHead(this.sprite, this.tallestFrameHeight(textureKey));
  }

  /** Tallest frame of a loaded strip, which is the pose whose feet define the logical actor Y. */
  private tallestFrameHeight(textureKey: string): number {
    const cached = this.tallestFrameHeights.get(textureKey);
    if (cached !== undefined) return cached;
    const texture = this.opts.scene.textures.get(textureKey);
    const heights = texture
      .getFrameNames(false)
      .map((name) => texture.get(name).height)
      .filter((height) => height > 0);
    const tallest = heights.length > 0 ? Math.max(...heights) : this.sprite.frame.height;
    this.tallestFrameHeights.set(textureKey, tallest);
    return tallest;
  }

  /** Force the animation matching `next`. */
  private setState(next: PlayerState) {
    this.state = next;
    if (next === "climb") {
      this.setClimbFrame(false);
      return;
    }
    this.climbFrame = null;
    const animKey = `player_${next}`;
    const texKey = stateTextureKey(next);
    applyMotionPlayback(this.sprite, animKey, texKey, this.motionPlayback[next]);
    this.applySheetScale(texKey);
    anchorRepackedMotionFeet(this.sprite);
  }

  /** A public hurt state exists only when the matching four-frame sheet was actually loaded. */
  private hasHurtPresentation(): boolean {
    return (
      this.opts.scene.textures.exists("character_hurt") &&
      this.opts.scene.anims.exists("player_hurt")
    );
  }

  /** A terminal state exists only when the matching four-frame sheet was actually loaded. */
  private hasDeathPresentation(): boolean {
    return (
      this.opts.scene.textures.exists("character_death") &&
      this.opts.scene.anims.exists("player_death")
    );
  }

  /** Current health, for the HUD and the probe. */
  get healthState(): PlayerHealthState {
    return this.health;
  }

  /**
   * Take a blow from a mob and return the authoritative before/after resolution.
   *
   * Knockback is applied only on a connect, and away from the striker, so a blow reads as a blow
   * rather than as the player snagging on geometry. The invulnerability window that follows is
   * what makes standing beside a mob survivable - without it, contact is continuous and the bar
   * empties in a single cooldown cycle.
   */
  takeDamage(
    amount: number,
    nowMs: number,
    fromDirSign: 1 | -1,
    critical = false,
  ): PlayerDamageResolution {
    const result = applyPlayerDamage(this.health, amount, nowMs, critical);
    this.health = result.health;
    if (!result.connected) return result;
    this.sprite.setAlpha(playerInvulnerabilityBlinkAlpha(this.health, nowMs));
    this.vx = fromDirSign * PLAYER_KNOCKBACK_VX;
    this.vy = PLAYER_KNOCKBACK_VY;
    // Look back toward the striker while the body travels away from it. The source strip faces
    // right, so a shove to the right means the attacker was on the left and the sheet is flipped.
    this.facing = fromDirSign === 1 ? "left" : "right";
    // Through the support machine, not by setting `airborne` behind its back. A blow launches
    // the player - that is what `PLAYER_KNOCKBACK_VY` is - so the support they had is gone, and
    // writing the flag alone left the two disagreeing: the state machine kept resolving them
    // against the terrain it still believed they stood on, which pinned them to the surface and
    // swallowed the launch whole, while every reader of `airborne` was told they were in the
    // air. A mob striking a standing player is the ordinary way into that state, so it is the
    // frame-12 invariant failure in the deterministic transcript.
    this.setSupport("air", null);
    this.activeClimbable = undefined;
    this.ladderId = null;
    this.clearAttack();
    if (result.health.defeated && this.hasDeathPresentation()) {
      this.hurtUntil = 0;
      this.setState("death");
      this.sprite.setFlipX(this.facing === "left");
    } else if (this.hasHurtPresentation()) {
      this.hurtUntil = nowMs + HURT_DURATION_MS;
      // The scene resolves strikes after `update`, so waiting for the next state-selection pass
      // leaves the hit frame in the old pose. Enter now; the update loop holds the final frame
      // when this is also the best available terminal fallback.
      this.setState("hurt");
      this.sprite.setFlipX(this.facing === "left");
    }
    return result;
  }

  /**
   * Restore hit points and report whether the restore actually happened.
   *
   * The caller decides what was spent to get here and only learns from `connected` whether it was
   * worth spending, so a drink at full health costs the player nothing. No presentation of its
   * own: the floating health bar is already the reading for a pool that changed.
   */
  heal(amount: number): PlayerHealResolution {
    const result = applyPlayerHealing(this.health, amount);
    this.health = result.health;
    return result;
  }

  /**
   * Widen the health pool and fill it, which is what arriving at a new level does.
   *
   * Separate from `heal` because it is not a restore: the ceiling itself moves, and a caller that
   * only healed would leave the new capacity permanently unreachable.
   */
  growMaximumHealth(maxHp: number): PlayerHealthState {
    this.health = grownPlayerHealth(this.health, maxHp);
    return this.health;
  }

  /**
   * How this run attacks.
   *
   * Resolved through the table on every read rather than cached, so a run that publishes no class
   * and one that publishes the melee class are the same object rather than two code paths.
   */
  private weaponProfile(): WeaponClassProfile {
    return this.opts.weaponClass ?? weaponClassProfile(null);
  }

  /** The profile this controller is attacking with, for callers that must agree with it. */
  get weapon(): WeaponClassProfile {
    return this.weaponProfile();
  }

  /**
   * The index of the blow the running action lands this frame, or null.
   *
   * Zero on the first blow of any action, which is what a single-blow class only ever returns;
   * a multi-hit class returns its later ticks as they come due. Each index is handed out once.
   */
  consumeAttackHit(nowMs: number): number | null {
    const tick = nextAttackHitTick({
      profile: this.weaponProfile(),
      state: {
        attackUntil: this.attackUntil,
        attackStarted: this.attackStarted,
        attackActive: this.attackActive,
      },
      nowMs,
      ticksFired: this.attackHitTicksFired,
    });
    if (tick === null) return null;
    this.attackHitTicksFired = tick + 1;
    return tick;
  }

  snapshot(nowMs?: number): PlayerStateSnapshot {
    const renderBounds = this.playerRenderBounds();
    return {
      state: this.state,
      facing: this.facing,
      x: this.sprite.x,
      y: this.sprite.y,
      column: Math.floor(this.sprite.x / this.opts.tilePx),
      vx: this.vx,
      vy: this.vy,
      airborne: this.airborne,
      airJumpsUsed: this.airJumpsUsed,
      attackActive: this.attackActive,
      hp: this.health.hp,
      maxHp: this.health.maxHp,
      invulnerable: isPlayerInvulnerable(this.health, nowMs ?? 0),
      defeated: this.health.defeated,
      support: this.support,
      supportId: this.supportId,
      ladderId: this.ladderId,
      platformId: this.support === "platform" ? this.supportId : null,
      dropThroughPlatformId: this.dropThroughPlatformId,
      dropTraversalPhase: this.dropTraversal?.phase ?? null,
      dropTraversalPlatformId: this.dropTraversal?.platformId ?? null,
      dropTraversalPlatformBottomY:
        this.dropTraversal?.platformBottomY ?? null,
      dropTraversalLowerSupport: this.dropTraversal?.lowerSupport ?? null,
      dropTraversalLowerSupportId:
        this.dropTraversal?.lowerSupportId ?? null,
      dropTraversalLowerSupportY: this.dropTraversal?.lowerSupportY ?? null,
      dropTraversalStableFrames: this.dropTraversal?.stableFrames ?? 0,
      renderBounds,
      climbAnimationKey:
        this.support === "climbable" && this.climbFrame !== null
          ? this.currentClimbArtwork().animKey
          : null,
      climbTextureKey:
        this.support === "climbable" && this.climbFrame !== null
          ? this.currentClimbArtwork().textureKey
          : null,
      climbFrame: this.support === "climbable" ? this.climbFrame : null,
      climbAnimationPaused:
        this.support === "climbable" && this.climbFrame !== null
          ? this.sprite.anims.isPaused
          : null,
      rearFacing: this.support === "climbable" && !this.sprite.flipX,
    };
  }

  /** Test/QA helper to drive position directly. */
  setX(x: number) {
    this.sprite.x = x;
  }

  /** Restore the exact frame-zero state before deterministic automation starts. */
  resetAutomationState(): void {
    this.state = "idle";
    this.facing = "right";
    this.vx = 0;
    this.vy = 0;
    this.airJumpsUsed = 0;
    this.coyoteExpiresAtMs = null;
    this.blockedColumn = null;
    this.setSupport("terrain", null);
    this.activeClimbable = undefined;
    this.ladderId = null;
    this.climbFrame = null;
    this.clearDropThrough();
    this.dropTraversal = undefined;
    this.clearAttack();
    this.hurtUntil = 0;
    this.health = initialPlayerHealth(this.opts.startingHealth);
    this.sprite.setPosition(this.opts.startX, this.opts.startY);
    this.sprite.setFlipX(false);
    this.sprite.setAlpha(1);
    this.sprite.setVisible(true);
    this.sprite.anims.stop();
    const initialKey = stateTextureKey("idle");
    applyMotionPlayback(
      this.sprite,
      "player_idle",
      initialKey,
      this.motionPlayback.idle,
    );
    this.applySheetScale(initialKey);
    anchorRepackedMotionFeet(this.sprite);
  }
}

/** Height in source pixels of one required loaded strip frame. */
function sheetFrameHeight(
  scene: Phaser.Scene,
  key: string,
  index: number,
): number {
  if (!scene.textures.exists(key)) {
    throw new Error(`current player texture ${key} is missing`);
  }
  const height = scene.textures.get(key).get(index)?.height;
  if (typeof height !== "number" || !Number.isFinite(height) || height <= 0) {
    throw new Error(`current player texture ${key} frame ${index} has invalid height`);
  }
  return height;
}

function stateTextureKey(state: PlayerState): string {
  // Pre-loaded by the scene as character_<state> for master slices and sibling strips.
  if (state === "attack") return "character_attack";
  // The throw plays the strip the contract calls `skill_cast`, which every combat-enabled package
  // already ships. The runtime state is named for what it does; the key is named for what was drawn.
  if (state === "ranged_attack") return "character_skill_cast";
  // Historical mature-runtime key; prepared contracts call this state `crouch`.
  if (state === "crouch") return "character_crawl";
  if (state === "climb") return "character_climb";
  return `character_${state}`;
}

import { terrainSurfaceY } from "./terrain";
import { resolveTerrainWalk, type TerrainWalkResolution } from "./vertical";

export type MobNavigationSurface = "terrain_lane";
export type MobPatrolBoundary = "home_radius";
export type MobPursuitBoundary = "home_territory_within_terrain_lane";

/**
 * Immutable in-code policy for current mob navigation.
 *
 * These values are runtime game design, not authored generation input. The names keep three
 * independent concepts separate: where a mob can stand, where it idles, and how far an engaged
 * pursuit may travel.
 */
export class MobNavigationPolicy {
  readonly navigationSurface: MobNavigationSurface = "terrain_lane";
  readonly patrolBoundary: MobPatrolBoundary = "home_radius";
  readonly pursuitBoundary: MobPursuitBoundary =
    "home_territory_within_terrain_lane";
  readonly patrolHomeRadiusPx: number;
  readonly pursuitHomeRadiusPx: number;
  readonly returnHomeArrivalRadiusPx: number;
  readonly returnHomeSpeedPx: number;

  constructor(tilePixels: number) {
    if (!Number.isFinite(tilePixels) || tilePixels <= 0) {
      throw new Error("mob navigation policy requires a positive finite tile size");
    }
    this.patrolHomeRadiusPx = Math.round(tilePixels * 1.5);
    this.pursuitHomeRadiusPx = tilePixels * 6;
    this.returnHomeArrivalRadiusPx = Math.round(tilePixels * 0.125);
    this.returnHomeSpeedPx = Math.round(tilePixels * 0.85);
    Object.freeze(this);
  }
}

export type MobTerrainLaneNodeOptions = Readonly<{
  spawnColumn: number;
  spawnX: number;
  tilePixels: number;
  worldWidthPx: number;
  baselineY: number;
  renderedHalfWidth: number;
  heightAtColumn: (column: number) => number;
  policy: MobNavigationPolicy;
}>;

/**
 * Navigation node for one mob's connected terrain shelf.
 *
 * Spawn zones do not appear here. They own population placement, not actor navigation. The lane
 * is derived solely from terrain topology: equal-height adjacent columns are connected; a rise,
 * descent, pit, or world edge terminates it. Ladders are intentionally absent because they are a
 * player traversal mechanism, not terrain collision.
 */
export class MobTerrainLaneNode {
  private _homeX = 0;
  private _patrolMinX = 0;
  private _patrolMaxX = 0;
  private _laneMinX = 0;
  private _laneMaxX = 0;
  private _pursuitMinX = 0;
  private _pursuitMaxX = 0;
  private readonly opts: MobTerrainLaneNodeOptions;

  constructor(opts: MobTerrainLaneNodeOptions) {
    if (!Number.isSafeInteger(opts.spawnColumn) || opts.spawnColumn < 0) {
      throw new Error("mob terrain lane requires a non-negative spawn column");
    }
    for (const value of [
      opts.spawnX,
      opts.tilePixels,
      opts.worldWidthPx,
      opts.baselineY,
      opts.renderedHalfWidth,
    ]) {
      if (!Number.isFinite(value)) {
        throw new Error("mob terrain lane geometry must be finite");
      }
    }
    if (opts.tilePixels <= 0 || opts.worldWidthPx <= 0 || opts.renderedHalfWidth < 0) {
      throw new Error("mob terrain lane geometry has invalid dimensions");
    }
    this.opts = opts;
    const worldColumns = Math.ceil(opts.worldWidthPx / opts.tilePixels);
    if (opts.spawnColumn >= worldColumns) {
      throw new Error("mob terrain lane spawn column lies outside the world");
    }
    this.setHome(opts.spawnColumn, opts.spawnX);
  }

  get homeX(): number {
    return this._homeX;
  }

  get patrolMinX(): number {
    return this._patrolMinX;
  }

  get patrolMaxX(): number {
    return this._patrolMaxX;
  }

  get laneMinX(): number {
    return this._laneMinX;
  }

  get laneMaxX(): number {
    return this._laneMaxX;
  }

  get pursuitMinX(): number {
    return this._pursuitMinX;
  }

  get pursuitMaxX(): number {
    return this._pursuitMaxX;
  }

  /**
   * Adopt a forced landing shelf as the actor's new local territory.
   *
   * Player knockback may deliberately carry a mob over a drop. Once it lands on a disconnected
   * shelf, the original home is unreachable because mobs cannot jump or climb. Re-homing only in
   * that case preserves normal patrol/pursuit bounds while preventing an impossible return goal.
   */
  rehomeAfterForcedDisplacement(landingX: number): boolean {
    if (!Number.isFinite(landingX)) {
      throw new Error("mob forced landing coordinate must be finite");
    }
    if (this.containsWorldX(landingX)) return false;
    const worldX = Math.min(
      this.opts.worldWidthPx - this.opts.renderedHalfWidth,
      Math.max(this.opts.renderedHalfWidth, landingX),
    );
    this.setHome(Math.floor(worldX / this.opts.tilePixels), worldX);
    return true;
  }

  /** Restore the authored spawn territory for deterministic replay/reset. */
  restoreHome(spawnColumn: number, spawnX: number): void {
    this.setHome(spawnColumn, spawnX);
  }

  private setHome(spawnColumn: number, spawnX: number): void {
    const worldColumns = Math.ceil(this.opts.worldWidthPx / this.opts.tilePixels);
    if (!Number.isSafeInteger(spawnColumn) || spawnColumn < 0 || spawnColumn >= worldColumns) {
      throw new Error("mob terrain lane home column lies outside the world");
    }
    if (!Number.isFinite(spawnX)) {
      throw new Error("mob terrain lane home coordinate must be finite");
    }
    const spawnHeight = this.opts.heightAtColumn(spawnColumn);
    if (!Number.isFinite(spawnHeight)) {
      throw new Error("mob terrain lane spawn height must be finite");
    }
    let leftColumn = spawnColumn;
    while (leftColumn > 0 && this.opts.heightAtColumn(leftColumn - 1) === spawnHeight) {
      leftColumn -= 1;
    }
    let rightColumn = spawnColumn;
    while (
      rightColumn + 1 < worldColumns &&
      this.opts.heightAtColumn(rightColumn + 1) === spawnHeight
    ) {
      rightColumn += 1;
    }
    const worldMin = this.opts.renderedHalfWidth;
    const worldMax = this.opts.worldWidthPx - this.opts.renderedHalfWidth;
    this._homeX = spawnX;
    this._laneMinX = Math.max(worldMin, leftColumn * this.opts.tilePixels);
    this._laneMaxX = Math.min(
      worldMax,
      (rightColumn + 1) * this.opts.tilePixels - 1,
    );
    this._patrolMinX = Math.max(
      this._laneMinX,
      spawnX - this.opts.policy.patrolHomeRadiusPx,
    );
    this._patrolMaxX = Math.min(
      this._laneMaxX,
      spawnX + this.opts.policy.patrolHomeRadiusPx,
    );
    this._pursuitMinX = Math.max(
      this._laneMinX,
      spawnX - this.opts.policy.pursuitHomeRadiusPx,
    );
    this._pursuitMaxX = Math.min(
      this._laneMaxX,
      spawnX + this.opts.policy.pursuitHomeRadiusPx,
    );
  }

  containsWorldX(x: number): boolean {
    return Number.isFinite(x) && x >= this._laneMinX && x <= this._laneMaxX;
  }

  containsPatrolX(x: number): boolean {
    return Number.isFinite(x) && x >= this._patrolMinX && x <= this._patrolMaxX;
  }

  containsPursuitX(x: number): boolean {
    return Number.isFinite(x) && x >= this._pursuitMinX && x <= this._pursuitMaxX;
  }

  walk(
    previousX: number,
    nextX: number,
    boundary: "patrol" | "pursuit" | "world",
    allowDescents = false,
  ): TerrainWalkResolution {
    const worldMin = this.opts.renderedHalfWidth;
    const worldMax = this.opts.worldWidthPx - this.opts.renderedHalfWidth;
    const minimum =
      boundary === "patrol"
        ? this.patrolMinX
        : boundary === "pursuit"
          ? this.pursuitMinX
          : worldMin;
    const maximum =
      boundary === "patrol"
        ? this.patrolMaxX
        : boundary === "pursuit"
          ? this.pursuitMaxX
          : worldMax;
    const boundaryStep = resolveMobBoundaryStep(previousX, nextX, minimum, maximum);
    const walk = resolveTerrainWalk({
      previousX,
      nextX: boundaryStep.x,
      footY: this.surfaceYAt(previousX),
      tilePixels: this.opts.tilePixels,
      surfaceAt: (column) => this.surfaceYAtColumn(column),
      allowDescents,
    });
    if (walk.blocked || !boundaryStep.blocked) return walk;
    return Object.freeze({ x: walk.x, blocked: true, blockedColumn: null });
  }

  surfaceYAt(x: number): number {
    return this.surfaceYAtColumn(Math.floor(x / this.opts.tilePixels));
  }

  private surfaceYAtColumn(column: number): number {
    return terrainSurfaceY(
      this.opts.heightAtColumn(column),
      this.opts.tilePixels,
      this.opts.baselineY,
    );
  }
}

/**
 * Enforce a home boundary without snapping an externally displaced actor back into it.
 *
 * An actor already outside may advance inward at its requested step size, but cannot move farther
 * outward. An actor inside is stopped at the boundary if its requested step would cross it.
 */
function resolveMobBoundaryStep(
  previousX: number,
  nextX: number,
  minimum: number,
  maximum: number,
): Readonly<{ x: number; blocked: boolean }> {
  if (previousX < minimum) {
    if (nextX < previousX) return Object.freeze({ x: previousX, blocked: true });
    if (nextX > maximum) return Object.freeze({ x: maximum, blocked: true });
    return Object.freeze({ x: nextX, blocked: false });
  }
  if (previousX > maximum) {
    if (nextX > previousX) return Object.freeze({ x: previousX, blocked: true });
    if (nextX < minimum) return Object.freeze({ x: minimum, blocked: true });
    return Object.freeze({ x: nextX, blocked: false });
  }
  const bounded = Math.min(maximum, Math.max(minimum, nextX));
  return Object.freeze({ x: bounded, blocked: bounded !== nextX });
}

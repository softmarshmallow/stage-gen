// What a projectile's named facets cost in pixels, milliseconds, and hit points.
//
// The generator publishes three names per drawn object — a silhouette, a flight, and an impact —
// and the artwork drawn for it. It publishes no numbers, the same split the aggression, critical
// and weapon-class tables already use.
//
// The division of labour with `weapon-class.ts` is the point of having both. The **weapon** is the
// character's business: which pose plays, how long the action commits, how much a blow is worth,
// how far the policy stands off. The **projectile** is the object's: how fast it travels, whether
// it falls, how far it reaches, how big its box is, and what its arrival resolves against. That is
// why a game can give one weapon a slow drifting orb and another a flat dart without inventing a
// second weapon class, and why a director retuning flight costs no regeneration — the generator
// excludes both facets from the artwork's cache key precisely because it cannot draw them.

/** What is drawn, and therefore what the runtime may do with the sprite. */
export type ProjectileSilhouette = "radial_v1" | "axial_v1" | "irregular_v1";

/** How the object travels. */
export type ProjectileFlight = "flat_bolt_v1" | "lobbed_arc_v1" | "drifting_orb_v1";

/** What arrival resolves against, and how it reads. */
export type ProjectileImpact = "single_target_v1" | "burst_v1" | "piercing_v1";

export const PROJECTILE_SILHOUETTES = Object.freeze([
  "radial_v1",
  "axial_v1",
  "irregular_v1",
] as const);
export const PROJECTILE_FLIGHTS = Object.freeze([
  "flat_bolt_v1",
  "lobbed_arc_v1",
  "drifting_orb_v1",
] as const);
export const PROJECTILE_IMPACTS = Object.freeze([
  "single_target_v1",
  "burst_v1",
  "piercing_v1",
] as const);

/**
 * How the sprite is oriented while it travels.
 *
 * Derived from the silhouette, because the silhouette is a statement about the pixels: only an
 * object drawn with a leading end can be pointed anywhere, and only one drawn without a direction
 * can be spun without looking wrong.
 */
export type ProjectileOrientation = Readonly<{
  /** Turn the sprite to follow its velocity. Meaningless without a drawn leading end. */
  aimAlongFlight: boolean;
  /** Mirror the sprite when travelling left, so a drawn-right subject still leads with its nose. */
  mirrorWhenReversed: boolean;
  /** Degrees per second of free spin. Only ever non-zero for a subject with no leading end. */
  spinDegreesPerSecond: number;
}>;

const ORIENTATIONS: Readonly<Record<ProjectileSilhouette, ProjectileOrientation>> = Object.freeze({
  // No leading end, so there is nothing to aim and nothing a mirror would change. Spun instead,
  // which is the only way a directionless object reads as travelling rather than floating.
  radial_v1: Object.freeze({
    aimAlongFlight: false,
    mirrorWhenReversed: false,
    spinDegreesPerSecond: 220,
  }),
  // Drawn pointing right, so it is mirrored to travel left and turned to follow an arc. Never
  // spun: a dart tumbling end over end is a different object.
  axial_v1: Object.freeze({
    aimAlongFlight: true,
    mirrorWhenReversed: true,
    spinDegreesPerSecond: 0,
  }),
  // No axis worth aiming and no symmetry worth preserving. Tumbles slowly, and mirrors only so two
  // shots in opposite directions do not look like the same frame twice.
  irregular_v1: Object.freeze({
    aimAlongFlight: false,
    mirrorWhenReversed: true,
    spinDegreesPerSecond: 90,
  }),
});

export function projectileOrientation(silhouette: string): ProjectileOrientation {
  return ORIENTATIONS[silhouette as ProjectileSilhouette] ?? ORIENTATIONS.irregular_v1;
}

/** Everything about how one object moves. */
export type ProjectileFlightProfile = Readonly<{
  speedTilesPerSecond: number;
  gravityPxPerSecond2: number;
  maxRangeTiles: number;
  releaseForwardTiles: number;
  releaseHeightFraction: number;
  halfWidthTiles: number;
  halfHeightTiles: number;
}>;

/**
 * What each flight costs.
 *
 * `flat_bolt_v1` is a transcription, not a design: it reproduces the numbers the ranged weapon
 * class shipped with, so a package that moves from the old inline delivery to a named flight plays
 * identically. The other two are the two things a flat bolt cannot do — reach over a ledge, and
 * hang in the air long enough to be dodged.
 */
const FLIGHTS: Readonly<Record<ProjectileFlight, ProjectileFlightProfile>> = Object.freeze({
  flat_bolt_v1: Object.freeze({
    // 11 tiles/s is 704 px/s, crossing the full range in a little over half a second: long enough
    // to read as a thrown object, short enough that a walking target rarely steps out after it.
    speedTilesPerSecond: 11,
    gravityPxPerSecond2: 0,
    // Six tiles is 384px against a 1280px viewport, so nothing it kills dies off camera.
    maxRangeTiles: 6,
    releaseForwardTiles: 0.5,
    releaseHeightFraction: 0.5,
    // Narrow and tall: a thrown object should miss what it flies past and connect with what it
    // flies into.
    halfWidthTiles: 0.35,
    halfHeightTiles: 0.7,
  }),
  lobbed_arc_v1: Object.freeze({
    // Slower and shorter than a bolt, and it falls. The arc is what buys the one thing a flat
    // throw cannot do — clear a lip and land on the deck below — and the price is that a moving
    // target has time to leave.
    speedTilesPerSecond: 8,
    gravityPxPerSecond2: 900,
    maxRangeTiles: 7,
    releaseForwardTiles: 0.4,
    // Released higher, because a lob that starts at chest height spends its first tile going up.
    releaseHeightFraction: 0.75,
    halfWidthTiles: 0.4,
    halfHeightTiles: 0.4,
  }),
  drifting_orb_v1: Object.freeze({
    // Slow enough to be seen coming and to be walked around, which is the whole character of it.
    // Wide box, because an orb that visibly passes through a creature and misses reads as broken.
    speedTilesPerSecond: 5,
    gravityPxPerSecond2: 0,
    maxRangeTiles: 5,
    releaseForwardTiles: 0.6,
    releaseHeightFraction: 0.6,
    halfWidthTiles: 0.5,
    halfHeightTiles: 0.5,
  }),
});

export function projectileFlightProfile(flight: string): ProjectileFlightProfile {
  return FLIGHTS[flight as ProjectileFlight] ?? FLIGHTS.flat_bolt_v1;
}

/**
 * What one arrival resolves against, and how it looks.
 *
 * Named kinds, never counts or radii — those are here, in the consumer, exactly as the aggression
 * archetype's aggro radius is. The authored choice is what *kind* of thing the object is, which is
 * a property of the object in the same way a creature's temperament is a property of the creature.
 */
export type ProjectileImpactProfile = Readonly<{
  /** How many targets one shot may resolve against. */
  maxTargets: number;
  /** Whether the shot survives a connection and keeps flying. */
  continuesAfterHit: boolean;
  /**
   * How the arrival reads, drawn by the runtime from the projectile's own sprite.
   *
   * No new artwork: the sprite it already has is scaled and faded on the deterministic clock the
   * combat text already uses. An impact that needed its own drawn frame would be a second
   * generated asset per projectile, which is a cost this facet is deliberately not worth.
   */
  flashMs: number;
  flashScale: number;
}>;

const IMPACTS: Readonly<Record<ProjectileImpact, ProjectileImpactProfile>> = Object.freeze({
  single_target_v1: Object.freeze({
    maxTargets: 1,
    continuesAfterHit: false,
    flashMs: 140,
    flashScale: 1.6,
  }),
  // Resolves against everything its box touches on the frame it lands, then stops. Not a spread:
  // one object arriving, several things in the way of it.
  burst_v1: Object.freeze({
    maxTargets: 4,
    continuesAfterHit: false,
    flashMs: 220,
    flashScale: 2.6,
  }),
  // Keeps going. The cap is what stops one shot clearing a whole zone.
  piercing_v1: Object.freeze({
    maxTargets: 3,
    continuesAfterHit: true,
    flashMs: 110,
    flashScale: 1.3,
  }),
});

export function projectileImpactProfile(impact: string): ProjectileImpactProfile {
  return IMPACTS[impact as ProjectileImpact] ?? IMPACTS.single_target_v1;
}

/** One published projectile, resolved into everything the runtime needs to fly and draw it. */
export type ProjectileProfile = Readonly<{
  projectileId: string;
  orientation: ProjectileOrientation;
  flight: ProjectileFlightProfile;
  impact: ProjectileImpactProfile;
}>;

export function projectileProfile(published: {
  projectile_id: string;
  silhouette: string;
  flight: string;
  impact: string;
}): ProjectileProfile {
  return Object.freeze({
    projectileId: published.projectile_id,
    orientation: projectileOrientation(published.silhouette),
    flight: projectileFlightProfile(published.flight),
    impact: projectileImpactProfile(published.impact),
  });
}

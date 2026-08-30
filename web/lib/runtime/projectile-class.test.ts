import { describe, expect, test } from "bun:test";
import {
  PROJECTILE_FLIGHTS,
  PROJECTILE_IMPACTS,
  PROJECTILE_SILHOUETTES,
  projectileFlightProfile,
  projectileImpactProfile,
  projectileOrientation,
  projectileProfile,
} from "./projectile-class";

describe("the flight table", () => {
  test("the flat bolt reproduces the numbers the weapon class used to carry", () => {
    // The transcription that makes moving flight off the weapon a refactor rather than a retune:
    // a package that fired a flat bolt before plays identically after.
    expect(projectileFlightProfile("flat_bolt_v1")).toEqual({
      speedTilesPerSecond: 11,
      gravityPxPerSecond2: 0,
      maxRangeTiles: 6,
      releaseForwardTiles: 0.5,
      releaseHeightFraction: 0.5,
      halfWidthTiles: 0.35,
      halfHeightTiles: 0.7,
    });
  });

  test("only the lobbed arc falls, which is the one thing a flat throw cannot do", () => {
    for (const flight of PROJECTILE_FLIGHTS) {
      const falls = projectileFlightProfile(flight).gravityPxPerSecond2 > 0;
      expect(falls).toBe(flight === "lobbed_arc_v1");
    }
  });

  test("a slower flight is a dodgeable one, and buys a wider box for it", () => {
    const bolt = projectileFlightProfile("flat_bolt_v1");
    const orb = projectileFlightProfile("drifting_orb_v1");
    expect(orb.speedTilesPerSecond).toBeLessThan(bolt.speedTilesPerSecond);
    // An orb that visibly passes through a creature and misses reads as broken.
    expect(orb.halfWidthTiles).toBeGreaterThan(bolt.halfWidthTiles);
  });

  test("no two flights are the same record under different names", () => {
    const seen = new Set(PROJECTILE_FLIGHTS.map((f) => JSON.stringify(projectileFlightProfile(f))));
    expect(seen.size).toBe(PROJECTILE_FLIGHTS.length);
  });
});

describe("the orientation rule", () => {
  test("only a subject drawn with a leading end is aimed or mirrored", () => {
    const axial = projectileOrientation("axial_v1");
    expect(axial.aimAlongFlight).toBe(true);
    expect(axial.mirrorWhenReversed).toBe(true);
    expect(axial.spinDegreesPerSecond).toBe(0);
  });

  test("a directionless subject is spun and never aimed, because there is nothing to point", () => {
    const radial = projectileOrientation("radial_v1");
    expect(radial.aimAlongFlight).toBe(false);
    expect(radial.mirrorWhenReversed).toBe(false);
    expect(radial.spinDegreesPerSecond).toBeGreaterThan(0);
  });

  test("nothing is both aimed and spun, which would fight itself every frame", () => {
    for (const silhouette of PROJECTILE_SILHOUETTES) {
      const orientation = projectileOrientation(silhouette);
      expect(orientation.aimAlongFlight && orientation.spinDegreesPerSecond !== 0).toBe(false);
    }
  });
});

describe("the impact rule", () => {
  test("it names a kind and the consumer owns every number", () => {
    expect(projectileImpactProfile("single_target_v1").maxTargets).toBe(1);
    expect(projectileImpactProfile("burst_v1").maxTargets).toBeGreaterThan(1);
    expect(projectileImpactProfile("piercing_v1").continuesAfterHit).toBe(true);
  });

  test("only a piercing shot survives a connection", () => {
    for (const impact of PROJECTILE_IMPACTS) {
      const survives = projectileImpactProfile(impact).continuesAfterHit;
      expect(survives).toBe(impact === "piercing_v1");
    }
  });

  test("every impact draws itself from the sprite it already has", () => {
    // The facet is deliberately presentational: an impact needing its own drawn frame would be a
    // second generated asset per projectile.
    for (const impact of PROJECTILE_IMPACTS) {
      const profile = projectileImpactProfile(impact);
      expect(profile.flashMs).toBeGreaterThan(0);
      expect(profile.flashScale).toBeGreaterThan(1);
    }
  });
});

describe("resolving one published entry", () => {
  test("the three facets are read independently, from the names the manifest carries", () => {
    const profile = projectileProfile({
      projectile_id: "paperwing_dart",
      silhouette: "axial_v1",
      flight: "lobbed_arc_v1",
      impact: "piercing_v1",
    });
    expect(profile.projectileId).toBe("paperwing_dart");
    expect(profile.orientation).toEqual(projectileOrientation("axial_v1"));
    expect(profile.flight).toEqual(projectileFlightProfile("lobbed_arc_v1"));
    expect(profile.impact).toEqual(projectileImpactProfile("piercing_v1"));
  });

  test("a facet from a later contract falls back rather than crashing the scene", () => {
    // The manifest is parsed as free text on purpose: a package from a later contract must load
    // and play, not blank the screen because one vocabulary grew.
    const profile = projectileProfile({
      projectile_id: "unknown",
      silhouette: "spiral_v1",
      flight: "homing_v1",
      impact: "chain_v1",
    });
    expect(profile.flight).toEqual(projectileFlightProfile("flat_bolt_v1"));
    expect(profile.impact).toEqual(projectileImpactProfile("single_target_v1"));
    expect(profile.orientation).toEqual(projectileOrientation("irregular_v1"));
  });
});

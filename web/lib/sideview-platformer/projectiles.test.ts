import { describe, expect, test } from "bun:test";
import type Phaser from "phaser";
import { SCENE_CONTENT_DEPTH } from "./depths";
import { PROJECTILE_POOL_CAP, ProjectileSystem } from "./projectiles";
import type { WorldLimits } from "./projectile-flight";
import { projectileProfile, type ProjectileProfile } from "./projectile-class";

// The pool holds Phaser images and nothing else, so it is tested against a stub scene exactly as
// the combat-text pool is. Everything that decides an outcome already lives in
// `projectile-flight.ts` and is tested there; what is asserted here is the lifecycle — that a shot
// gets a sprite, that the sprite is destroyed on every exit path, and that the order hits come back
// in is the order the shots were fired.

const TILE = 64;
const TEXTURE = "prepared_item_stone";
const DART = projectileProfile({
  projectile_id: "paperwing_dart",
  silhouette: "axial_v1",
  flight: "flat_bolt_v1",
  impact: "single_target_v1",
});

class FakeImage {
  x = 0;
  y = 0;
  originX = 0;
  originY = 0;
  displayWidth = 0;
  displayHeight = 0;
  depth = 0;
  flipX = false;
  angle = 0;
  destroyed = false;

  setOrigin(x: number, y: number): this {
    this.originX = x;
    this.originY = y;
    return this;
  }
  setDisplaySize(width: number, height: number): this {
    this.displayWidth = width;
    this.displayHeight = height;
    return this;
  }
  setDepth(depth: number): this {
    this.depth = depth;
    return this;
  }
  setFlipX(flip: boolean): this {
    this.flipX = flip;
    return this;
  }
  setAngle(angle: number): this {
    this.angle = angle;
    return this;
  }
  setPosition(x: number, y: number): this {
    this.x = x;
    this.y = y;
    return this;
  }
  destroy(): void {
    this.destroyed = true;
  }
}

function fakeScene(textures: readonly string[] = [TEXTURE]): Readonly<{
  scene: Phaser.Scene;
  images: FakeImage[];
}> {
  const images: FakeImage[] = [];
  const known = new Set(textures);
  const scene = {
    add: {
      image(x: number, y: number): FakeImage {
        const image = new FakeImage();
        image.x = x;
        image.y = y;
        images.push(image);
        return image;
      },
    },
    textures: {
      exists: (key: string) => known.has(key),
      // A plain image texture's base frame. 2:1 so the aspect is visible in the assertion.
      get: () => ({ get: () => ({ width: 200, height: 100 }) }),
    },
  } as unknown as Phaser.Scene;
  return Object.freeze({ scene, images });
}

const OPEN_WORLD: WorldLimits = { minX: -10_000, maxX: 10_000, surfaceYAt: null };

function systemFor(
  fake: ReturnType<typeof fakeScene>,
  world: WorldLimits = OPEN_WORLD,
  projectile: ProjectileProfile = DART,
  textureKey = TEXTURE,
): ProjectileSystem {
  return new ProjectileSystem({
    scene: fake.scene,
    tilePx: TILE,
    textureKey,
    drawnLengthPx: 96,
    projectile,
    world,
  });
}

const shot = { originX: 500, footY: 656, bodyHeightPx: 154, dirSign: 1 as const };

describe("putting a shot in the air", () => {
  test("a fired shot gets a sprite drawn at the calibrated height, above the player", () => {
    const fake = fakeScene();
    const system = systemFor(fake);

    expect(system.fire(shot)).not.toBeNull();

    expect(system.liveCount).toBe(1);
    const sprite = fake.images[0];
    // The declared magnitude is a LENGTH, so it sizes the long axis and the height follows from
    // the trimmed frame's own 2:1 aspect.
    expect(sprite.displayWidth).toBe(96);
    expect(sprite.displayHeight).toBe(48);
    expect(sprite.depth).toBe(SCENE_CONTENT_DEPTH.effect);
    expect(sprite.originX).toBe(0.5);
    expect(sprite.originY).toBe(0.5);
  });

  test("a shot thrown left is flipped, so a thrown object reads as thrown rather than dropped", () => {
    const fake = fakeScene();
    systemFor(fake).fire({ ...shot, dirSign: -1 });
    expect(fake.images[0].flipX).toBe(true);
  });

  test("a missing texture refuses rather than drawing an invisible shot", () => {
    // Returning null and not throwing is what lets the caller decline to spend a round.
    const fake = fakeScene([]);
    expect(systemFor(fake).fire(shot)).toBeNull();
  });

  test("the pool has a ceiling, and refuses past it instead of growing", () => {
    const fake = fakeScene();
    const system = systemFor(fake);
    for (let i = 0; i < PROJECTILE_POOL_CAP; i += 1) expect(system.fire(shot)).not.toBeNull();
    expect(system.liveCount).toBe(PROJECTILE_POOL_CAP);
    expect(system.fire(shot)).toBeNull();
    expect(system.liveCount).toBe(PROJECTILE_POOL_CAP);
  });

  test("every shot carries an identity of its own, stable for its whole life", () => {
    const system = systemFor(fakeScene());
    const first = system.fire(shot);
    const second = system.fire(shot);
    expect(first?.id).not.toBe(second?.id);
  });
});

describe("leaving the world", () => {
  test("a shot that runs out of range is destroyed, not merely hidden", () => {
    const fake = fakeScene();
    const system = systemFor(fake);
    system.fire(shot);
    for (let step = 0; step < 60 && system.liveCount > 0; step += 1) {
      system.update(16, []);
    }
    expect(system.liveCount).toBe(0);
    expect(fake.images[0].destroyed).toBe(true);
  });

  test("a shot that connects is destroyed in the same pass that reports the hit", () => {
    const fake = fakeScene();
    const system = systemFor(fake);
    const fired = system.fire(shot);
    const target = {
      bounds: {
        left: fired!.x - 40,
        right: fired!.x + 40,
        top: fired!.y - 60,
        bottom: fired!.y + 60,
      },
    };

    const hits = system.update(16, [target]);

    expect(hits).toHaveLength(1);
    expect(hits[0].targetIndex).toBe(0);
    // Seeded from where the throw started, not where it landed.
    expect(hits[0].spawnX).toBe(fired!.spawnX);
    expect(system.liveCount).toBe(0);
    expect(fake.images[0].destroyed).toBe(true);
  });

  test("a shot into a rising hillside stops at the hill", () => {
    const fake = fakeScene();
    const system = systemFor(fake, { ...OPEN_WORLD, surfaceYAt: () => -10_000 });
    system.fire(shot);
    system.update(16, []);
    expect(system.liveCount).toBe(0);
  });

  test("clearAll destroys every sprite, so a map change leaves nothing behind", () => {
    const fake = fakeScene();
    const system = systemFor(fake);
    system.fire(shot);
    system.fire(shot);

    system.clearAll();

    expect(system.liveCount).toBe(0);
    expect(fake.images.every((image) => image.destroyed)).toBe(true);
  });
});

describe("the order impacts are reported in", () => {
  test("hits come back in the order the shots were fired, not in reverse", () => {
    // The pool steps backwards so a shot can be removed in the pass that resolved it. Without the
    // reversal that would hand the caller two simultaneous impacts in the opposite order, and the
    // critical seed advances per blow — so a replay would roll different criticals.
    const fake = fakeScene();
    const system = systemFor(fake);
    const first = system.fire(shot)!;
    const second = system.fire({ ...shot, originX: 400 })!;
    const boxFor = (x: number, y: number) => ({
      bounds: { left: x - 40, right: x + 40, top: y - 60, bottom: y + 60 },
    });

    const hits = system.update(16, [boxFor(first.x, first.y), boxFor(second.x, second.y)]);

    expect(hits).toHaveLength(2);
    expect(hits[0].spawnX).toBe(first.spawnX);
    expect(hits[1].spawnX).toBe(second.spawnX);
  });
});

describe("what the object's own facets change", () => {
  const ORB = projectileProfile({
    projectile_id: "sonar_pulse",
    silhouette: "radial_v1",
    flight: "drifting_orb_v1",
    impact: "burst_v1",
  });
  const PIERCER = projectileProfile({
    projectile_id: "tether_bolt",
    silhouette: "axial_v1",
    flight: "flat_bolt_v1",
    impact: "piercing_v1",
  });

  function boxAt(x: number, y: number) {
    return { bounds: { left: x - 40, right: x + 40, top: y - 60, bottom: y + 60 } };
  }

  test("a directionless subject is spun and never mirrored", () => {
    const fake = fakeScene();
    const system = systemFor(fake, OPEN_WORLD, ORB);
    system.fire({ ...shot, dirSign: -1 });
    // Nothing for a mirror to preserve on a subject with no leading end.
    expect(fake.images[0].flipX).toBe(false);
    const before = fake.images[0].angle;
    system.update(500, []);
    expect(fake.images[0].angle).not.toBe(before);
  });

  test("a subject with a leading end is mirrored and never spun", () => {
    const fake = fakeScene();
    const system = systemFor(fake, OPEN_WORLD, DART);
    system.fire({ ...shot, dirSign: -1 });
    expect(fake.images[0].flipX).toBe(true);
    system.update(500, []);
    // A flat flight has no vertical velocity, so a subject that aims along it stays level.
    expect(fake.images[0].angle).toBe(0);
  });

  test("an arcing subject noses over as it falls", () => {
    const arcing = projectileProfile({
      projectile_id: "pressure_charge",
      silhouette: "axial_v1",
      flight: "lobbed_arc_v1",
      impact: "burst_v1",
    });
    const fake = fakeScene();
    const system = systemFor(fake, OPEN_WORLD, arcing);
    system.fire(shot);
    expect(fake.images[0].angle).toBe(0);
    system.update(200, []);
    expect(fake.images[0].angle).toBeGreaterThan(0);
  });

  test("a bursting shot resolves against everything its box touches, then stops", () => {
    const fake = fakeScene();
    const system = systemFor(fake, OPEN_WORLD, ORB);
    const fired = system.fire(shot)!;

    const hits = system.update(16, [
      boxAt(fired.x, fired.y),
      boxAt(fired.x + 2, fired.y),
      boxAt(fired.x + 4, fired.y),
    ]);

    expect(hits.map((hit) => hit.targetIndex).sort()).toEqual([0, 1, 2]);
    expect(system.liveCount).toBe(0);
  });

  test("a piercing shot keeps flying and never strikes the same target twice", () => {
    const fake = fakeScene();
    const system = systemFor(fake, OPEN_WORLD, PIERCER);
    const fired = system.fire(shot)!;
    const wide = { bounds: { left: fired.x - 400, right: fired.x + 400, top: fired.y - 60, bottom: fired.y + 60 } };

    const first = system.update(16, [wide]);
    expect(first).toHaveLength(1);
    // Still in the air, and the target it already passed through is remembered.
    expect(system.liveCount).toBe(1);
    expect(system.update(16, [wide])).toHaveLength(0);
    expect(system.liveCount).toBe(1);
  });

  test("a piercing shot stops once it has spent its allowance", () => {
    const fake = fakeScene();
    const system = systemFor(fake, OPEN_WORLD, PIERCER);
    const fired = system.fire(shot)!;
    const row = [0, 2, 4, 6].map((offset) => boxAt(fired.x + offset, fired.y));

    const hits = system.update(16, row);

    // Three of the four: the cap is what stops one shot clearing a whole zone.
    expect(hits).toHaveLength(3);
    expect(system.liveCount).toBe(0);
  });
});

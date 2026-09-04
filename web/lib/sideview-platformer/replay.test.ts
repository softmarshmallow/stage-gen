import { describe, expect, mock, test } from "bun:test";

// The platformer's replay golden: one package, one scripted intent, one hash per fixed step.
//
// The runner's golden (`sideview-runner/replay.test.ts`) drives a sealed roster over a plain world
// object. The platformer has neither: its world is a Phaser scene, its actors are game objects, and
// until this file nothing had ever constructed one outside a browser. So the instrument is two
// stand-ins and a script — `headless-phaser.fixture.ts` for the engine, `headless-browser.fixture.ts`
// for the page, and a `PlayerIntent` source through the seam `player-intent.ts` was written for —
// driving the real `PreparedStageScene.update` at the platformer's own fixed step of 1/30s.
//
// Read the two fixtures' opening comments before trusting a number here. The short version: authored
// geometry is real, art is absent, and the engine's tweens and timers run on the same clock as the
// simulation rather than on a browser's, which makes this harness kinder to engine-driven code than
// a browser is rather than harsher.

const { headlessPhaserModule } = await import("./headless-phaser.fixture");
mock.module("phaser", headlessPhaserModule);

const { installHeadlessBrowser } = await import("./headless-browser.fixture");
const { replayRuntimeManifest } = await import("./replay-package.fixture");
const { playerIntent } = await import("./player-intent");
const { PreparedStageScene } = await import("./prepared-scene");
const { KEY_CODES } = await import("./headless-phaser.fixture");
type StubKey = import("./headless-phaser.fixture").StubKey;
type StubScene = import("./headless-phaser.fixture").StubScene;

const FRAMES = 600;
/** The platformer's own step, from `vertical.ts`: thirty simulation frames a second. */
const FRAME_MS = 1000 / 30;

/**
 * The scripted run, frame by frame.
 *
 * Written as windows rather than as a recorded input trace so it stays readable and so a reader can
 * tell what the run is supposed to be doing: leave the village gate, talk to the baker, walk east
 * through the portal onto the hunting route, throw the three darts the package starts with, pick up
 * what falls, climb the ladder onto the deck, drop back off it, and take enough contact damage on
 * the way to reach the defeat panel.
 */
function scriptedIntent(frame: number) {
  const between = (from: number, to: number) => frame >= from && frame < to;
  return playerIntent({
    right: between(1, 60) || between(80, 150) || between(155, 250) || between(495, 575),
    left: between(255, 375),
    // Held at the ladder the westward run ends against, then released to climb back down it.
    up: between(380, 432),
    down: between(437, 492),
    run: between(80, 150) || between(155, 250) || between(255, 375) || between(495, 575),
    // Edge-triggered, so one frame each: throws going east, and more coming back west.
    attack: [200, 215, 230, 245, 268, 285, 300, 515, 530, 545].includes(frame),
    jump: [493].includes(frame),
    useHealing: frame === 470,
    toggleInventory: frame === 350 || frame === 480,
  });
}

/** Which scene-level keys — the ones `PlayerIntent` does not carry — are held on a frame. */
function scriptedKeys(frame: number): readonly ("interact" | "enter" | "up" | "space")[] {
  // Open the conversation, then advance her first line.
  if ([60, 68].includes(frame)) return ["interact"];
  // And end it with a jump, which is the key the dialogue hold used to swallow: the frame's intent
  // read spends space's latch, and the panel then reads a key nobody pressed.
  if (frame === 72) return ["space"];
  // Ask the east gate to open, after the walk has run out of world.
  if (frame === 150 || frame === 151) return ["up"];
  // Accept the death screen, if the run reached one.
  if ([580, 588, 596].includes(frame)) return ["enter"];
  return [];
}

/**
 * The second scripted run: the one that dies.
 *
 * The first run never reaches a defeat — its event kinds stop at
 * `player-damaged` — so nothing about defeat, the prompt it raises, or the
 * recovery it offers could be measured at all. Step 3 said so in as many words
 * when it declined to pull the platformer's `session` out of `updatePlayer`
 * ("the platformer's golden cannot observe any of them"), and step 6 is the
 * step chartered to split that system. So the golden needs a run that gets
 * there first, and this is it.
 *
 * The opening is the first run's: east out of the village and through the gate,
 * without the conversation, which is why it arrives ten frames earlier. What it
 * then does is the one thing the first run never does — it fights nothing. No
 * throw, no healing draught, and it walks the route out and back so the
 * creatures it is not killing keep reaching it. Three contacts is what six
 * points of health and a nine-hundred-millisecond immunity window are worth.
 *
 * It also walks far enough east to reach the `east_gate` anchor, which is what
 * makes it the run that exercises the `director` family's set-piece as well as
 * the defeat: the gate fires at 259, the defeat lands at 376, the panel
 * finishes fading in at 403, and the run answers it at 500 and wakes up in the
 * village.
 */
function defeatIntent(frame: number) {
  const between = (from: number, to: number) => frame >= from && frame < to;
  // East out of the village, then up and down the hunting route without ever
  // striking back or drinking anything. Three contacts is all six points are
  // worth.
  return playerIntent({
    right: between(1, 150) || between(155, 300) || between(455, 600),
    left: between(305, 450),
    run: between(1, 150) || between(155, 300) || between(305, 450) || between(455, 600),
  });
}

/** Which scene-level keys the defeat run holds. */
function defeatKeys(frame: number): readonly ("interact" | "enter" | "up" | "space")[] {
  // Ask the east gate to open, on alternate frames so each press is a fresh
  // edge: this run has no conversation to pace it, so it arrives at the arch
  // earlier than the first one and the exact frame is not worth pinning.
  if (frame >= 140 && frame <= 200 && frame % 2 === 0) return ["up"];
  // Accept the death screen, once, well after it is up: the run has to record
  // the recovery as well as the defeat.
  if (DEFEAT_CONFIRM_FRAMES.includes(frame)) return ["enter"];
  return [];
}

/**
 * When the defeat run answers its own death screen.
 *
 * Measured from the run rather than guessed: with the gate honoured the defeat
 * lands at 376 and the panel finishes fading in at 403, so a press at 500 is
 * unambiguously an answer to a prompt that is up. Exactly one press, so the
 * recovery is one edge and the village the player wakes in is not then talked
 * to.
 */
const DEFEAT_CONFIRM_FRAMES: readonly number[] = [500];

type Harness = Readonly<{
  scene: InstanceType<typeof PreparedStageScene>;
  step: (frame: number) => void;
  restore: () => void;
}>;

async function settle(): Promise<void> {
  for (let turn = 0; turn < 2000; turn += 1) await Promise.resolve();
}

type Script = Readonly<{
  intent: (frame: number) => ReturnType<typeof playerIntent>;
  keys: (frame: number) => readonly ("interact" | "enter" | "up" | "space")[];
}>;

const WALK_AND_TALK: Script = { intent: scriptedIntent, keys: scriptedKeys };
const STAND_AND_DIE: Script = { intent: defeatIntent, keys: defeatKeys };

async function bootReplay(script: Script = WALK_AND_TALK): Promise<Harness> {
  let clockMs = 0;
  const browser = installHeadlessBrowser({
    manifest: replayRuntimeManifest(),
    now: () => clockMs,
    verbose: process.env.REPLAY_TRACE === "1",
  });
  const scene = new PreparedStageScene("replay", "canonical-alpha", "capture");
  const engine = scene as unknown as StubScene;
  scene.create();
  await settle();
  let frame = 0;
  scene.driveWithIntent(() => script.intent(frame));
  const keyboard = engine.input.keyboard;
  const keys: Record<string, StubKey> = {
    interact: keyboard.addKey(KEY_CODES.E),
    enter: keyboard.addKey(KEY_CODES.ENTER),
    up: keyboard.addKey(KEY_CODES.UP),
    space: keyboard.addKey(KEY_CODES.SPACE),
  };
  return {
    scene,
    step: (next: number) => {
      frame = next;
      const held = new Set<string>(script.keys(next));
      for (const [name, key] of Object.entries(keys)) {
        if (held.has(name)) key.press();
        else key.release();
      }
      clockMs = next * FRAME_MS;
      engine.stepEngine(clockMs, FRAME_MS, () => scene.update(clockMs, FRAME_MS));
    },
    restore: browser.restore,
  };
}

function plain(value: unknown): unknown {
  if (value instanceof Set) return [...value].map(plain).sort();
  if (value instanceof Map) return [...value.entries()].map(([key, entry]) => [plain(key), plain(entry)]);
  if (Array.isArray(value)) return value.map(plain);
  if (typeof value === "function") return undefined;
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const key of Object.keys(value).sort()) {
      const inner = plain((value as Record<string, unknown>)[key]);
      if (inner !== undefined) out[key] = inner;
    }
    return out;
  }
  // Nine places is past anything the simulation resolves at and short of float noise.
  if (typeof value === "number" && !Number.isInteger(value)) return value.toFixed(9);
  return value;
}

function digest(world: unknown, events: readonly unknown[]): string {
  const hasher = new Bun.CryptoHasher("sha256");
  hasher.update(JSON.stringify({ world: plain(world), events: plain(events) }));
  return hasher.digest("hex");
}

/**
 * Digest chain checkpoints; the final value covers every one of the six hundred frames.
 *
 * Re-pin only against a frame-by-frame diff of the previous chain, with a sentence naming which
 * frames moved and why. That is the whole discipline this file exists to enforce.
 */
const GOLDEN: Record<number, string> = {
  // Still in the village, mid-conversation with the baker. Upstream of every re-pin so far.
  // Re-pinned once, for the soundtrack player being wired at all: from frame 1 the record carries
  // a `soundtrack` field it did not have, silent until the first keypress at 60 starts the
  // village's track.
  60: "b60392b5d048486787cbf1799dcb2780cc7ed97defebd757ba10415d8d276a0e",
  // On the hunting route, one creature down and the loot collected.
  //
  // Re-pinned once, for `Mob` off the engine's tweens and timers. Twenty-two of six hundred frames
  // moved — 291 to 312 — and every changed field is under `mobs`. The killed creature's fade now
  // begins on the killing frame instead of five hundred milliseconds later, and the body retires at
  // 299 rather than 313. Its knockback x is identical frame for frame in both runs, which is the
  // measurement that `sampleFixedMobHit` really does reproduce the Cubic ease the tween ran; 313
  // onward hash identically one by one.
  // Re-pinned again for the map-name banner off its tween. Forty-five contiguous frames moved,
  // 150 to 194, and every changed field is under `banner`: the announcement raised by the portal
  // transition at 150 now exists in the record at all — a tween is engine state the probe could
  // not read — and lives for exactly the fade-hold-fade it declares, 1500ms at a 1/30s step.
  // Re-pinned again for `enterMap` deferred to the end of the frame that asks for it. Frames 150
  // to 600 moved, and the whole tail follows from one thing: the world is now rebuilt after the
  // frame's systems have run, so the population's first two spawns land on 151 instead of 150 and
  // those two creatures are a frame behind their old selves forever after. The run itself is the
  // same run — the kill at 290, both pickups at 293 and all three contact hits are on identical
  // frames — but the player's hp between 306 and 469 differs, because a critical is seeded from
  // where the creature that struck it was standing.
  // Re-pinned again for the soundtrack. All six hundred frames moved and every changed field is
  // under `soundtrack`: the run is silent until the keypress at 60 starts `village_theme`, and the
  // portal at 150 narrows the pool to the route's two tracks, which the seeded bag opens with
  // `road_theme_b` and plans `road_theme` behind.
  // Re-pinned again for the latched keys drained on one side of the dialogue hold. 529 frames
  // moved, 72 to 600, and the measurement is the strongest one this file has produced: with the
  // same script, the runtime before the fix never leaves the conversation at all — the player
  // stands at x=546 in the village for all 528 remaining frames and the run records two dialogue
  // events and nothing else — because space, the key the script ends the conversation with, was
  // spent by the intent read that runs first. After it, the conversation closes at 72 and the run
  // proceeds through the portal, four spawns, ten throws, a kill, two pickups and three hits.
  // Re-pinned again for the `director` family. Four hundred and fifty-one
  // frames moved, 150 to 600, and they all follow from one thing: the boss the
  // runtime used to stand at ninety-one percent of the road from the moment the
  // map loaded is a *set-piece* now, armed at the authored `east_gate` anchor,
  // and this run never walks that far — its furthest point east is x=1948
  // against a gate at x=2304. So it never meets the boss at all, which is what
  // "the platformer authored a set-piece and the runtime dropped it to a spawn"
  // costs when the set-piece is honoured. The cascade has a single origin,
  // measured with `REPLAY_DUMP` rather than argued: at 264 the dart `shot_4`
  // used to strike the boss at x=2332 and vanish. It now flies on, so that
  // blow's hitstop, its spark, its damage number and its place in the critical
  // sequence are all gone — which is why the creatures step one frame further
  // at 265, both pickups land at 290 instead of 293, and the contact hit slides
  // from 306 to 305. The kill at 290 and the map entry at 150 are on the same
  // frames as before.
  300: "d4259a823bcc5b6bb663015c16298fa3800934f917fcca135717b881eeb4e8d7",
  // The whole run.
  600: "8cd90200565e1151b508ceb089bcaa477ca2f47a13bd9c8e31ed34f8aae5d0d3",
};

describe("the platformer replays to its golden", () => {
  test("six hundred fixed steps under a scripted intent hash to the pinned chain", async () => {
    const harness = await bootReplay();
    try {
      let chain = "";
      const seen: Record<number, string> = {};
      const frames: string[] = [];
      const kinds = new Set<string>();
      const notes: Record<string, number> = {};
      const dumps: string[] = [];
      for (let frame = 1; frame <= FRAMES; frame += 1) {
        harness.step(frame);
        const snapshot = harness.scene.replaySnapshot();
        const hasher = new Bun.CryptoHasher("sha256");
        const frameDigest = digest(snapshot, harness.scene.transcript);
        hasher.update(chain + frameDigest);
        chain = hasher.digest("hex");
        frames.push(`${frame} ${frameDigest}`);
        if (process.env.REPLAY_DUMP) {
          dumps.push(`${frame} ${JSON.stringify(plain({ w: snapshot, e: harness.scene.transcript }))}`);
        }
        if (frame in GOLDEN) seen[frame] = chain;
        for (const event of harness.scene.transcript) {
          kinds.add(event.kind);
          notes[event.kind] ??= frame;
        }
        const player = snapshot.player as { state?: string } | null;
        if (player?.state === "climb") notes.climbed ??= frame;
      }
      // The instruments a bug commit re-pins against. `REPLAY_FRAMES` writes one unchained digest
      // per frame, so "which frames moved" is a diff rather than a claim; `REPLAY_DUMP` writes the
      // whole hashed snapshot per frame, so "and why" is a field-level diff rather than a guess.
      if (process.env.REPLAY_DUMP) await Bun.write(process.env.REPLAY_DUMP, `${dumps.join("\n")}\n`);
      if (process.env.REPLAY_FRAMES) {
        await Bun.write(process.env.REPLAY_FRAMES, `${frames.join("\n")}\n`);
      }
      expect(seen).toEqual(GOLDEN);
      // What the six hundred frames are actually a recording of. A script that silently stopped
      // covering the map transition or the population would still hash to something stable, and a
      // stable hash of nothing is the one way a golden fails without failing.
      expect([...kinds].sort()).toEqual([
        "dialogue-closed",
        "dialogue-opened",
        "item-collected",
        "map-entered",
        "mob-defeated",
        "mob-spawned",
        "player-damaged",
        "projectile-thrown",
      ]);
      expect(notes["map-entered"]).toBe(150);
      expect(notes.climbed).toBe(380);
    } finally {
      harness.restore();
    }
  });
});

/**
 * E1's second scenario: the run that reaches a defeat.
 *
 * Same instruments, same digest, its own chain. It exists because a split that
 * moves where defeat is decided has to have a before, and the first run cannot
 * provide one: it never dies, so every arrangement of the defeat that step 6
 * could reach would hash identically under it and prove nothing.
 */
const DEFEAT_GOLDEN: Record<number, string> = {
  // On the route, past the gate, and still standing.
  //
  // Re-pinned once, for the `director` family, and this run is the half of that
  // measurement that shows the set-piece *working*: it walks far enough east to
  // reach the authored `east_gate` anchor, so at 259 the gate fires —
  // `encounter-started` is in the record, the page-eater is placed at the gate
  // rather than having stood there since the map loaded, and the soundtrack
  // narrows to the authored `road_theme` for as long as the fight is on. Four
  // hundred and sixty-one frames moved, 140 to 600, all from that: the fight is
  // a different fight, so the defeat slides from 320 to 376 and the death
  // screen from 347 to 403. The run still ends the same way — answered at 500,
  // awake in the village — and from the respawn onward the two runs agree again
  // on everything but the combat text still in the air.
  300: "4feb7d66ee5c67c8a9f9c95c38d8ff6ab92bc6af9d38df2f1877be9f57832fc1",
  // Defeated at 376; the death screen arrives at 403.
  350: "7217d56783404397c1d59fd2748b5c078dfc908e43f9980230cf747713fabe66",
  // The whole run: the gate, the defeat, the prompt, the answer, and the village.
  600: "c78bf521709e0356f0c0ebc83e4ace27be15867e90e22760b562780aa9fe2952",
};

describe("the platformer replays its defeat run to a golden of its own", () => {
  test("six hundred fixed steps of standing still hash to the pinned chain", async () => {
    const harness = await bootReplay(STAND_AND_DIE);
    try {
      let chain = "";
      const seen: Record<number, string> = {};
      const frames: string[] = [];
      const dumps: string[] = [];
      const kinds = new Set<string>();
      const notes: Record<string, number> = {};
      for (let frame = 1; frame <= FRAMES; frame += 1) {
        harness.step(frame);
        const snapshot = harness.scene.replaySnapshot();
        const frameDigest = digest(snapshot, harness.scene.transcript);
        const hasher = new Bun.CryptoHasher("sha256");
        hasher.update(chain + frameDigest);
        chain = hasher.digest("hex");
        frames.push(`${frame} ${frameDigest}`);
        if (process.env.REPLAY_DUMP) {
          dumps.push(`${frame} ${JSON.stringify(plain({ w: snapshot, e: harness.scene.transcript }))}`);
        }
        if (frame in DEFEAT_GOLDEN) seen[frame] = chain;
        for (const event of harness.scene.transcript) {
          kinds.add(event.kind);
          notes[event.kind] ??= frame;
        }
        const panel = snapshot.defeatPanel as { visible?: boolean } | null;
        if (panel?.visible) notes.panelUp ??= frame;
      }
      if (process.env.REPLAY_DUMP) await Bun.write(process.env.REPLAY_DUMP, `${dumps.join("\n")}\n`);
      if (process.env.REPLAY_FRAMES) {
        await Bun.write(process.env.REPLAY_FRAMES, `${frames.join("\n")}\n`);
      }
      expect(seen).toEqual(DEFEAT_GOLDEN);
      // What this recording is of, and the whole reason it exists: the two
      // event kinds the first run cannot produce, `player-defeated` and
      // `player-respawned`. `mob-defeated` is absent on purpose — this run
      // kills nothing, which is how it manages to die.
      expect([...kinds].sort()).toEqual([
        "encounter-started",
        "map-entered",
        "mob-spawned",
        "player-damaged",
        "player-defeated",
        "player-respawned",
      ]);
      // The gate fires when the player reaches the authored anchor, and not
      // when the map loads — which is the whole of what the director changed.
      expect(notes["encounter-started"]).toBe(259);
      expect(notes["player-defeated"]).toBe(376);
      expect(notes.panelUp).toBe(403);
      expect(notes["player-respawned"]).toBe(500);
    } finally {
      harness.restore();
    }
  });
});

import { describe, expect, test } from "bun:test";

// E1 for the room: one manifest, one scripted click track, one hash per step.
//
// The instrument the plan's table asks for, in the shape the runner's and the
// platformer's goldens already have — seed plus scripted intent, a digest of the
// world per fixed step and of that step's events — with the one difference the
// genre forces: a room has no clock. Every transition is a click, so the "step"
// is the click, and the script is a list of them rather than a frame window.
//
// This is the first instrument the room has ever had. `state.test.ts` asserts
// individual transitions; nothing hashed a run, so a refactor of the reducer, of
// `interaction`'s selection, of `effects`' vocabulary or of the `inventory` bag
// had no way to say "identical" other than by the tests somebody remembered to
// write. The digest chain says it for every step at once.
//
// `REPLAY_FRAMES` writes one unchained digest per step, so "which step moved" is
// a diff rather than a claim; `REPLAY_DUMP` writes the state and the events.

import { parseRoomManifest, type Verb } from "./contract";
import { roomManifestFixture } from "./fixture";
import {
  initialState,
  interactTurn,
  selectItem,
  type RoomPlayState,
  type RoomTurn,
} from "./state";
import { bagItemIds } from "@/lib/families/inventory";

type Click =
  | { readonly kind: "interact"; readonly verb: Verb; readonly hotspot: string; readonly item?: string }
  | { readonly kind: "select"; readonly item: string | null };

/**
 * The scripted run: the fixture room, solved, with misses on the way.
 *
 * Written as verbs on hotspots rather than as pixels, because that is what the
 * reducer takes and what the solvability proof searched. The misses are in the
 * script on purpose — `interaction/refused` is an occurrence a consumer draws,
 * and a golden that only walked the happy path would never hash one.
 */
const SCRIPT: readonly Click[] = [
  // Look before touching, twice: an interaction with no effects never fires, so
  // the second look is the same state and the same occurrence as the first.
  { kind: "interact", verb: "inspect", hotspot: "bench" },
  { kind: "interact", verb: "inspect", hotspot: "bench" },
  // The chest, before the key: a hidden hotspot and an unmet item, both refused.
  { kind: "interact", verb: "use", hotspot: "chest" },
  { kind: "interact", verb: "use", hotspot: "prize" },
  // The key, and the same grant a second time — the room's bag is a set, so a
  // repeat grant is the no-op it has always been.
  { kind: "interact", verb: "use", hotspot: "bench" },
  { kind: "interact", verb: "use", hotspot: "bench" },
  { kind: "select", item: "key" },
  // A held item with nowhere to go: the miss line that names the item.
  { kind: "interact", verb: "use", hotspot: "bench", item: "key" },
  { kind: "select", item: "key" },
  // The chest, with the key: two effects in authored order, and a reveal.
  { kind: "interact", verb: "use", hotspot: "chest", item: "key" },
  { kind: "interact", verb: "use", hotspot: "chest", item: "key" },
  // The prize the reveal made visible: the click that solves the room.
  { kind: "interact", verb: "use", hotspot: "prize" },
  { kind: "interact", verb: "use", hotspot: "prize" },
  { kind: "interact", verb: "inspect", hotspot: "bench" },
];

function plain(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(plain);
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const key of Object.keys(value).sort()) {
      out[key] = plain((value as Record<string, unknown>)[key]);
    }
    return out;
  }
  return value;
}

function digest(state: RoomPlayState, events: readonly unknown[]): string {
  const hasher = new Bun.CryptoHasher("sha256");
  hasher.update(
    JSON.stringify({
      state: { ...(plain(state) as Record<string, unknown>), inventory: bagItemIds(state.inventory) },
      events: plain(events),
    }),
  );
  return hasher.digest("hex");
}

describe("the room replays to its golden", () => {
  test("fourteen scripted clicks hash to the pinned chain", async () => {
    const manifest = parseRoomManifest(roomManifestFixture());
    let state = initialState(manifest);
    let chain = digest(state, []);
    const steps: string[] = [];
    const dumps: string[] = [];

    for (const [index, click] of SCRIPT.entries()) {
      let turn: RoomTurn;
      if (click.kind === "select") {
        turn = { state: selectItem(state, click.item), events: [] };
      } else {
        turn = interactTurn(manifest, state, click.verb, click.hotspot, click.item ?? null);
      }
      state = turn.state;
      const step = digest(state, turn.events);
      steps.push(`${index} ${step}`);
      if (process.env.REPLAY_DUMP) {
        dumps.push(
          JSON.stringify({
            step: index,
            state: {
              ...(plain(state) as Record<string, unknown>),
              inventory: bagItemIds(state.inventory),
            },
            events: turn.events,
          }),
        );
      }
      const hasher = new Bun.CryptoHasher("sha256");
      hasher.update(`${chain}${step}`);
      chain = hasher.digest("hex");
    }

    if (process.env.REPLAY_FRAMES) {
      await Bun.write(process.env.REPLAY_FRAMES, `${steps.join("\n")}\n`);
    }
    if (process.env.REPLAY_DUMP) await Bun.write(process.env.REPLAY_DUMP, `${dumps.join("\n")}\n`);

    // Pinned at the step it was baked. A refactor that must preserve behaviour
    // shows this exact chain; one that intends a change shows a diff at the
    // documented step and nowhere else, and re-pins with a sentence saying why.
    expect(chain).toBe("3edcda1024b0ae41656fbb8b3a31addf8b448be892c09fa320726c57f92ea06a");
    expect(state.solved).toBe(true);
  });

  test("the room reports what it did, and refuses by name", () => {
    const manifest = parseRoomManifest(roomManifestFixture());
    const opening = initialState(manifest);
    // A miss narrates and says so; it is not silence, and it is not a state diff
    // a consumer has to notice.
    const missed = interactTurn(manifest, opening, "use", "chest", "key");
    expect(missed.events).toEqual([
      { type: "interaction/refused", verb: "use", hotspot: "chest", item: "key" },
    ]);
    // A hit names the authored index that won — the room's affordance selection
    // has no distance, so authored order is the whole of the priority.
    const hit = interactTurn(manifest, opening, "inspect", "bench");
    expect(hit.events[0]).toMatchObject({ type: "interaction/outcome", verb: "inspect" });
  });
});

import { describe, expect, test } from "bun:test";
import {
  advanceCase,
  caseBeat,
  caseBeatIsTerminal,
  caseBeatNumber,
  initialCaseProgress,
  mergeFacts,
  parseCase,
  singleBeatCase,
} from "./case";
import { demoCaseDocument, demoCaseLeaf, demoCaseWire } from "./case.fixture";

function wire(): Record<string, unknown> {
  return demoCaseWire();
}

describe("parseCase", () => {
  test("admits the demonstration case and reads its beats in authored order", () => {
    const document = parseCase(wire());
    expect(document.caseId).toBe("demo_case");
    expect(document.entry).toBe("demo_supper");
    expect(document.beats.map((beat) => beat.beatId)).toEqual([
      "demo_supper",
      "demo_room",
      "demo_close",
    ]);
    expect(document.facts).toContain("saw_the_card");
    expect(caseBeatNumber(document, "demo_room")).toBe(2);
  });

  test("an unknown key is drift and is refused", () => {
    expect(() => parseCase({ ...wire(), notes: "hello" })).toThrow("keys must match");
  });

  test("a wire under another identity is refused rather than read leniently", () => {
    expect(() => parseCase({ ...wire(), kind: "case-v2" })).toThrow("kind");
    expect(() => parseCase({ ...wire(), schema_version: 2 })).toThrow("schema_version");
  });

  test("an entry that names no beat is refused", () => {
    expect(() => parseCase({ ...wire(), entry: "nowhere" })).toThrow("does not name a beat");
  });

  test("an edge into thin air is refused", () => {
    const document = wire();
    const beats = document.beats as Record<string, unknown>[];
    beats[0]!.edges = [{ outcome: "to_the_room", to: "a_beat_that_is_not_here" }];
    expect(() => parseCase(document)).toThrow("edge to unknown beat");
  });

  test("a case with no terminal beat is refused", () => {
    const document = wire();
    const beats = document.beats as Record<string, unknown>[];
    delete beats[2]!.terminal;
    beats[2]!.edges = [{ outcome: "closed_quietly", to: "demo_supper" }];
    expect(() => parseCase(document)).toThrow("terminal beat");
  });

  test("a beat whose `terminal` disagrees with its edges is refused, not guessed at", () => {
    const document = wire();
    const beats = document.beats as Record<string, unknown>[];
    beats[0]!.terminal = true;
    expect(() => parseCase(document)).toThrow("disagrees with the edges");
  });

  test("the authored fact fields survive the crossing to the consumer", () => {
    const document = parseCase(wire());
    const left = document.factDeclarations.find((fact) => fact.factId === "left_the_room");
    expect(left?.establishment).toBe("required");
    expect(left?.summary).not.toBeNull();
    const beat = caseBeat(document, "demo_close")!;
    expect(beat.reads).toContain("saw_the_card");
    expect(caseBeat(document, "demo_room")!.writes).toContain("left_the_room");
  });

  test("an establishment outside the vocabulary is refused", () => {
    const document = wire();
    const facts = document.facts as Record<string, unknown>[];
    facts[0]!.establishment = "defaults_true";
    expect(() => parseCase(document)).toThrow("required or defaults_false");
  });

  test("a room whose edge is not the win is refused: a room has one outcome", () => {
    const document = wire();
    const beats = document.beats as Record<string, unknown>[];
    beats[1]!.edges = [{ outcome: "escaped", to: "demo_close" }];
    expect(() => parseCase(document)).toThrow("only outcome is win");
  });

  test("two beats with one id are refused", () => {
    const document = wire();
    const beats = document.beats as Record<string, unknown>[];
    beats[2]!.beat_id = "demo_supper";
    expect(() => parseCase(document)).toThrow("unique");
  });
});

describe("walking a case", () => {
  const document = demoCaseDocument();

  test("it starts at the entry, carrying nothing", () => {
    const progress = initialCaseProgress(document);
    expect(progress.beatId).toBe("demo_supper");
    expect(progress.facts).toEqual([]);
  });

  test("an outcome takes its edge and carries the declared facts across", () => {
    const start = initialCaseProgress(document);
    const next = advanceCase(document, start, "to_the_room", ["heard_the_toast"]);
    expect(next?.beatId).toBe("demo_room");
    expect(next?.facts).toEqual(["heard_the_toast"]);
  });

  test("only declared facts cross; a leaf's private flags stay in the leaf", () => {
    const start = initialCaseProgress(document);
    const next = advanceCase(document, start, "to_the_room", [
      "heard_the_toast",
      "some_local_bookkeeping_flag",
    ]);
    expect(next?.facts).toEqual(["heard_the_toast"]);
  });

  test("facts accumulate rather than replace as the beats go by", () => {
    const atRoom = advanceCase(document, initialCaseProgress(document), "to_the_room", [
      "heard_the_toast",
    ])!;
    const atClose = advanceCase(document, atRoom, "win", ["saw_the_card", "left_the_room"])!;
    expect(atClose.beatId).toBe("demo_close");
    expect(atClose.facts).toEqual(["heard_the_toast", "left_the_room", "saw_the_card"]);
  });

  test("a terminal beat ends the case rather than walking off the end", () => {
    const terminal = caseBeat(document, "demo_close")!;
    expect(caseBeatIsTerminal(terminal)).toBe(true);
    const progress = { beatId: "demo_close", facts: [] as readonly string[] };
    expect(advanceCase(document, progress, "closed_quietly", [])).toBeNull();
  });

  test("an outcome the case declares no edge for ends the case rather than stranding", () => {
    const progress = initialCaseProgress(document);
    expect(advanceCase(document, progress, "an_outcome_nobody_wired", [])).toBeNull();
  });

  test("mergeFacts is idempotent and sorted, so a save round-trips unchanged", () => {
    const once = mergeFacts(document, [], ["saw_the_card", "heard_the_toast"]);
    expect(once).toEqual(["heard_the_toast", "saw_the_card"]);
    expect(mergeFacts(document, once, [])).toEqual(once);
  });
});

describe("singleBeatCase", () => {
  test("wraps one leaf as a case with one terminal beat", () => {
    const document = singleBeatCase("The Ferry Bell", "scenario", "larkfield-ui-v1");
    expect(document.beats).toHaveLength(1);
    expect(document.beats[0]!.runTag).toBe("larkfield-ui-v1");
    expect(caseBeatIsTerminal(document.beats[0]!)).toBe(true);
    expect(document.facts).toEqual([]);
    expect(initialCaseProgress(document).beatId).toBe(document.beats[0]!.beatId);
  });
});

describe("the demonstration case's leaves", () => {
  test("every beat has a leaf, and each is admitted by its own contract", () => {
    for (const beat of demoCaseDocument().beats) {
      const leaf = demoCaseLeaf(beat.beatId);
      expect(leaf).not.toBeNull();
      if (beat.kind === "scenario") expect(leaf!.scene).not.toBeNull();
      else expect(leaf!.room).not.toBeNull();
    }
    expect(demoCaseLeaf("a_beat_that_is_not_here")).toBeNull();
  });

  test("the opening beat stages all five slots, which is what it is for", () => {
    const scene = demoCaseLeaf("demo_supper")!.scene!;
    const slots = new Set(
      scene.scenario.blocks
        .flatMap((block) => block.statements)
        .filter((statement) => statement.kind === "show")
        .map((statement) => (statement as { slot: string }).slot),
    );
    expect(slots).toEqual(
      new Set(["far_left", "left", "center", "right", "far_right"]),
    );
  });

  test("the facts the room exports are the ones the closing beat reads", () => {
    const room = demoCaseLeaf("demo_room")!.room!;
    const exported = new Set(
      room.interactions.flatMap((interaction) =>
        interaction.effects.flatMap((effect) =>
          effect.set_flag === undefined ? [] : [effect.set_flag],
        ),
      ),
    );
    const close = demoCaseLeaf("demo_close")!.scene!;
    const read = new Set(close.scenario.flags);
    expect(exported.has("saw_the_card")).toBe(true);
    expect(read.has("saw_the_card")).toBe(true);
    expect(read.has("asked_about_the_bell")).toBe(true);
    // The win flag is the room's own exit and is not something the next beat reads.
    expect(room.win.requires).toEqual(["left_the_room"]);
  });
});

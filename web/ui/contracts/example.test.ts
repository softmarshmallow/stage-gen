import { describe, expect, test } from "bun:test";
import catalogFixture from "./catalog.fixture.json";
import {
  EXAMPLE_REFUSAL,
  GAME_EXAMPLE_ENTRY_REFUSAL,
  latestFigures,
  parseFiguresLedger,
  parseGameExampleEntry,
  parseWorkflowExample,
} from "./example";
import exampleFixture from "./example.fixture.json";

function example(): Record<string, unknown> {
  return structuredClone(exampleFixture) as Record<string, unknown>;
}

function nodes(document: Record<string, unknown>): Record<string, Record<string, unknown>> {
  return document.nodes as Record<string, Record<string, unknown>>;
}

describe("parseWorkflowExample", () => {
  test("reads the hand-authored example into runtime shapes", () => {
    const parsed = parseWorkflowExample(example());
    expect(parsed.exampleId).toBe("slate-swatches");
    expect(parsed.madeBy).toEqual({ kind: "workflow", id: "swatch-sheet" });
    expect(parsed.sourceRuns[0].anchor).toBe("plan.json");
    expect(parsed.graphKind).toBe("gnode-graph-v2");
    expect(Object.keys(parsed.nodes)).toEqual(["brief", "draw", "check", "contact-sheet"]);
    expect(parsed.nodes.draw.dependsOn).toEqual(["brief"]);
    expect(parsed.nodes.draw.maxAttempts).toBe(6);
    expect(parsed.nodes["contact-sheet"].origin).toBe("derived");
    expect(parsed.nodes.check.verdict).toEqual({
      passed: true,
      reason: "six swatches, none touching, all inside the grid",
    });
    expect(parsed.metrics.swatches).toBe(6);
    expect(parsed.tree[""]).toEqual({ kind: "dir", bytes: 1051266, files: 4, entries: 4 });
    expect(parsed.tree["sheet.png"].files).toBeNull();
    // Inputs and outputs stay as written: the page that shows them owns their meaning.
    expect(parsed.outputs.sheet.picture).toEqual(exampleFixture.outputs.sheet.picture);
  });

  test("a converted record without source files still reads", () => {
    const document = example();
    document.source_files = null;
    document.graph_kind = null;
    document.graph_sha256 = null;
    const parsed = parseWorkflowExample(document);
    expect(parsed.sourceFiles).toBeNull();
    expect(parsed.graphKind).toBeNull();
  });

  test.each([
    ["kind", "workflow-example-v2"],
    ["schema_version", 2],
  ])("refuses an unknown envelope (%s)", (field, value) => {
    expect(() => parseWorkflowExample({ ...example(), [field]: value })).toThrow(EXAMPLE_REFUSAL);
  });

  test("refuses a node keyed under another id or depending on a node it does not hold", () => {
    const renamed = example();
    nodes(renamed).draw.id = "paint";
    expect(() => parseWorkflowExample(renamed)).toThrow("nodes.draw.id must equal its key");

    const dangling = example();
    nodes(dangling).check.depends_on = ["paint"];
    expect(() => parseWorkflowExample(dangling)).toThrow("depends on an undeclared node paint");
  });

  test("refuses a malformed origin, digest or empty source list", () => {
    const origin = example();
    nodes(origin).draw.origin = "imported";
    expect(() => parseWorkflowExample(origin)).toThrow("nodes.draw.origin must be one of run, derived");

    const anchor = example();
    (anchor.source_runs as Record<string, unknown>[])[0].anchor_sha256 = "abc";
    expect(() => parseWorkflowExample(anchor)).toThrow("source_runs[0].anchor_sha256 must be a SHA-256 digest");

    expect(() => parseWorkflowExample({ ...example(), source_runs: [] })).toThrow(
      "source_runs must name at least one run",
    );
  });
});

describe("parseFiguresLedger", () => {
  const ledger = () =>
    structuredClone(catalogFixture.workflows[0].examples[0].figures) as Record<string, unknown>;

  test("reads every derived file with the run files it came from", () => {
    const parsed = parseFiguresLedger(ledger());
    expect(parsed.run).toBe("out/swatch-sheet-slate-01");
    expect(parsed.files[0].size).toEqual([640, 640]);
    expect(parsed.files[0].sources[0].path).toBe("out/swatch-sheet-slate-01/sheet.png");
  });

  test("the last entry for a file written twice wins", () => {
    const document = ledger();
    const files = document.files as Record<string, unknown>[];
    files.push({ ...files[0], bytes: 1, sha256: "f".repeat(64) });
    expect(latestFigures(parseFiguresLedger(document)).get(files[0].file as string)?.bytes).toBe(1);
  });

  test("refuses a size that is not a width and a height", () => {
    const document = ledger();
    (document.files as Record<string, unknown>[])[0].size = [640];
    expect(() => parseFiguresLedger(document)).toThrow("files[0].size must be [width, height]");
  });
});

describe("parseGameExampleEntry", () => {
  const entry = () =>
    structuredClone(catalogFixture.game_examples[0].entry) as Record<string, unknown>;

  test("reads what a game says about an example it made", () => {
    const parsed = parseGameExampleEntry(entry());
    expect(parsed.gameTitle).toBe("Example Game");
    expect(parsed.order).toBe(1);
    expect(parsed.steps[0].members).toEqual(["harbor-atlas"]);
    expect(parsed.currency).toBe("current");
  });

  test("refuses an unknown envelope, a workflow maker, and an unknown currency", () => {
    expect(() => parseGameExampleEntry({ ...entry(), schema_version: 2 })).toThrow(
      GAME_EXAMPLE_ENTRY_REFUSAL,
    );
    expect(() =>
      parseGameExampleEntry({ ...entry(), made_by: { kind: "workflow", id: "swatch-sheet" } }),
    ).toThrow("made_by.kind must be game");
    expect(() => parseGameExampleEntry({ ...entry(), currency: "stale" })).toThrow(
      "currency must be one of current, earlier_version",
    );
  });
});

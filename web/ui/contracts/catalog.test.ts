import { describe, expect, test } from "bun:test";
import { CATALOG_REFUSAL, findWorkflow, parseCatalog } from "./catalog";
import catalogFixture from "./catalog.fixture.json";
import exampleFixture from "./example.fixture.json";

type Wire = Record<string, unknown>;

function catalog(): Wire {
  return structuredClone(catalogFixture) as Wire;
}

function firstWorkflow(document: Wire): Wire {
  return (document.workflows as Wire[])[0];
}

describe("parseCatalog", () => {
  test("reads the hand-authored catalog into runtime shapes", () => {
    const parsed = parseCatalog(catalog());
    const workflow = findWorkflow(parsed, "swatch-sheet");
    expect(workflow?.manifest.title).toBe("Swatch sheet");
    expect(workflow?.manifest.tryIt?.commands).toHaveLength(2);
    expect(workflow?.identity.graphKinds).toEqual(["pipeline-execution-graph-v1"]);
    expect(workflow?.identity.declared.pipelines).toBeDefined();
    expect(workflow?.steps.map((step) => step.label)).toEqual(["Draw", "Check"]);
    expect(workflow?.steps[0].members[1]).toEqual({
      typeId: "swatch.draw",
      title: "Draw the swatch sheet",
      archetype: "image",
      operation: "image_generation",
    });
    expect(workflow?.samplePlan?.operationCounts).toEqual({ image_generation: 1, local: 2 });
    expect(workflow?.samplePlan?.nodes.map((node) => node.id)).toEqual(["brief", "draw", "check"]);
    const [example] = workflow?.examples ?? [];
    expect(example.cover).toBe(true);
    expect(example.currency).toBe("current");
    expect(example.example?.exampleId).toBe(exampleFixture.example_id);
    expect(example.figures?.files).toHaveLength(2);
    expect(findWorkflow(parsed, "unknown")).toBeNull();
  });

  test("reads an example entry's own footer, labels and steps", () => {
    const parsed = parseCatalog(catalog());
    const [plain] = findWorkflow(parsed, "swatch-sheet")?.examples ?? [];
    expect([plain.footer, plain.labels, plain.steps]).toEqual([null, {}, []]);
    const document = catalog();
    const entry = (firstWorkflow(document).examples as Wire[])[0];
    entry.footer = "Made from one run.";
    entry.labels = { draw: "Draw the sheet" };
    entry.steps = [{ label: "Draw", note: "One sheet.", members: ["brief", "draw"] }];
    const [own] = findWorkflow(parseCatalog(document), "swatch-sheet")?.examples ?? [];
    expect(own.footer).toBe("Made from one run.");
    expect(own.labels).toEqual({ draw: "Draw the sheet" });
    expect(own.steps).toEqual([{ label: "Draw", note: "One sheet.", members: ["brief", "draw"] }]);
    entry.steps = [{ label: "Draw", note: "", members: [] }];
    expect(() => parseCatalog(document)).toThrow(/members must not be empty/);
  });

  test("lists game examples and orders the landing cards", () => {
    const parsed = parseCatalog(catalog());
    expect(parsed.gameExamples[0].entry?.gameTitle).toBe("Example Game");
    expect(parsed.gameExamples[0].example.madeBy).toEqual({ kind: "game", id: "example-game" });
    expect(parsed.cards.map((card) => [card.order, card.madeInside, card.workflow])).toEqual([
      [1, "Example Game", null],
      [2, null, "swatch-sheet"],
    ]);
    expect(parsed.modelNames["gpt-image-2"]).toBe("GPT Image 2");
  });

  test("a clean-clone catalog lists examples it could not find", () => {
    const document = catalog();
    const [example] = firstWorkflow(document).examples as Wire[];
    Object.assign(example, { present: false, currency: null, example: null, figures: null });
    const parsed = parseCatalog(document);
    expect(parsed.workflows[0].examples[0].example).toBeNull();
    expect(parsed.workflows[0].examples[0].present).toBe(false);
  });

  test.each([
    ["kind", "stage-gen-catalog-v2"],
    ["schema_version", 2],
  ])("refuses an unknown envelope (%s)", (field, value) => {
    expect(() => parseCatalog({ ...catalog(), [field]: value })).toThrow(CATALOG_REFUSAL);
  });

  test("refuses a manifest that names another workflow", () => {
    const document = catalog();
    (firstWorkflow(document).manifest as Wire).id = "other";
    expect(() => parseCatalog(document)).toThrow("manifest.id must equal the workflow id");
  });

  test("refuses a sample plan edge to an undeclared node", () => {
    const document = catalog();
    const plan = firstWorkflow(document).sample_plan as Wire;
    (plan.nodes as Wire[])[2].depends_on = ["paint"];
    expect(() => parseCatalog(document)).toThrow("depends on an undeclared node paint");
  });

  test("refuses an absent example that still carries a document", () => {
    const document = catalog();
    ((firstWorkflow(document).examples as Wire[])[0] as Wire).present = false;
    expect(() => parseCatalog(document)).toThrow("is not present but carries a document");
  });

  test("refuses cards out of order or naming an example the catalog lacks", () => {
    const reordered = catalog();
    (reordered.cards as Wire[]).reverse();
    expect(() => parseCatalog(reordered)).toThrow("cards must be in strictly increasing order");

    const unknown = catalog();
    (unknown.cards as Wire[])[1].example = "granite-swatches";
    expect(() => parseCatalog(unknown)).toThrow("unknown example swatch-sheet/granite-swatches");

    const unknownGame = catalog();
    (unknownGame.cards as Wire[])[0].made_by = { kind: "game", id: "other-game" };
    expect(() => parseCatalog(unknownGame)).toThrow("unknown game example other-game/harbor-tiles");
  });
});

// The joins and the tally: what the page says about a gallery, checked without
// rendering it.

import { describe, expect, test } from "bun:test";
import type {
  AdmittedUniverse,
  EntityRecord,
  GalleryManifest,
  ImageReview,
  ReviewCheck,
} from "./contract";
import {
  buildEntityCards,
  presentClasses,
  tallyReviewChecks,
} from "./gallery-view";

function review(
  overrides: Partial<Record<ReviewCheck, string>> = {},
): ImageReview {
  return {
    verdict: "admit",
    whatTheImageTeaches: "",
    blockingFindings: [],
    advisoryFindings: [],
    checks: {
      entity_identity: "pass",
      action_legibility: "pass",
      register_fidelity: "pass",
      medium_fidelity: "pass",
      explanatory_form_absent: "pass",
      readable_text_absent: "pass",
      technical_quality: "pass",
      ...overrides,
    },
  };
}

function entity(entityId: string, displayName: string, primaryClass: string) {
  return {
    entityId,
    displayName,
    entityKind: "",
    primaryClass,
    facets: [],
    summary: "",
    howItWorksOrLives: "",
    presentTension: "",
    facts: [],
  };
}

function universe(): AdmittedUniverse {
  return {
    universeId: "u",
    title: "U",
    mediumId: "anime_2d",
    premise: { claim: "", lineage: "" },
    presentState: { claim: "", lineage: "" },
    entities: [
      entity("e_idea", "An Idea", "idea"),
      entity("e_actor", "Zoe", "actor"),
      entity("e_place", "Asterlock", "place"),
    ],
    relationships: [
      {
        relationshipId: "r1",
        kind: "located_in",
        family: "spatial",
        sourceEntityId: "e_actor",
        targetEntityId: "e_place",
        summary: "Zoe lives in Asterlock.",
        perspective: "",
        temporalScope: "",
      },
    ],
    identityMarkers: [
      {
        markerId: "m1",
        ownerEntityId: "e_place",
        form: "notches",
        meaning: "accountability",
        materials: "",
        appliedUse: "",
        limits: "",
      },
    ],
    viewpoints: [],
    institutionalTensions: [],
    physicalEcologicalRules: [],
    unresolvedQuestions: [],
    plans: [],
  };
}

function manifest(
  entries: readonly { id: string; name: string; cls: string; status: string }[],
): GalleryManifest {
  return {
    universeId: "u",
    title: "U",
    mediumId: "anime_2d",
    graphSha256: "a",
    invocationId: "i",
    closedInGraph: true,
    inputs: {
      universePath: "inputs/universe.json",
      universeSha256: "b",
      posterProxyPath: "p.jpg",
    },
    counts: {},
    entityCount: entries.length,
    entities: entries.map((entry) => ({
      entityId: entry.id,
      displayName: entry.name,
      primaryClass: entry.cls,
      status: entry.status as GalleryManifest["entities"][number]["status"],
      reason: "",
      image: null,
      record: null,
      review: null,
    })),
    durationMs: null,
    knownCostUsd: null,
    publicationAuthorized: false,
    publicationGate: "",
  };
}

function record(
  status: string,
  checks: Partial<Record<ReviewCheck, string>> = {},
): EntityRecord {
  return {
    entityId: "",
    status: status as EntityRecord["status"],
    direction: null,
    review: review(checks),
    image: null,
  };
}

const ENTRIES = [
  { id: "e_idea", name: "An Idea", cls: "idea", status: "admitted" },
  { id: "e_actor", name: "Zoe", cls: "actor", status: "rejected" },
  { id: "e_place", name: "Asterlock", cls: "place", status: "admitted" },
];

describe("buildEntityCards", () => {
  test("orders by class then name, not by the manifest's own order", () => {
    const cards = buildEntityCards(manifest(ENTRIES), universe(), {});
    expect(cards.map((card) => card.entityId)).toEqual([
      "e_actor",
      "e_place",
      "e_idea",
    ]);
  });

  test("gives both ends of a relationship their own direction", () => {
    const cards = buildEntityCards(manifest(ENTRIES), universe(), {});
    const zoe = cards.find((card) => card.entityId === "e_actor");
    const asterlock = cards.find((card) => card.entityId === "e_place");
    expect(zoe?.relationships).toEqual([
      {
        kind: "located_in",
        otherEntityId: "e_place",
        otherDisplayName: "Asterlock",
        summary: "Zoe lives in Asterlock.",
        outgoing: true,
      },
    ]);
    expect(asterlock?.relationships[0].outgoing).toBe(false);
    expect(asterlock?.relationships[0].otherDisplayName).toBe("Zoe");
  });

  test("attaches each marker to the entity that owns it", () => {
    const cards = buildEntityCards(manifest(ENTRIES), universe(), {});
    expect(
      cards.find((card) => card.entityId === "e_place")?.markers,
    ).toHaveLength(1);
    expect(
      cards.find((card) => card.entityId === "e_actor")?.markers,
    ).toHaveLength(0);
  });

  test("skips an entity the manifest names but the proposal never described", () => {
    const extra = [
      ...ENTRIES,
      { id: "e_ghost", name: "Ghost", cls: "thing", status: "unknown" },
    ];
    const cards = buildEntityCards(manifest(extra), universe(), {});
    expect(cards.map((card) => card.entityId)).not.toContain("e_ghost");
  });

  test("a branch with no record still becomes a card, carrying its status", () => {
    const cards = buildEntityCards(manifest(ENTRIES), universe(), {});
    const zoe = cards.find((card) => card.entityId === "e_actor");
    expect(zoe?.status).toBe("rejected");
    expect(zoe?.review).toBeNull();
  });
});

describe("tallyReviewChecks", () => {
  test("counts only entities that were actually reviewed", () => {
    const cards = buildEntityCards(manifest(ENTRIES), universe(), {
      e_actor: record("rejected", { register_fidelity: "fail" }),
      e_place: record("admitted"),
    });
    const tallies = tallyReviewChecks(cards);
    const register = tallies.find(
      (tally) => tally.check === "register_fidelity",
    );
    expect(register).toEqual({
      check: "register_fidelity",
      passed: 1,
      failed: 1,
      other: 0,
    });
    const medium = tallies.find((tally) => tally.check === "medium_fidelity");
    expect(medium?.passed).toBe(2);
  });

  test("puts the check that failed most first, so the lean is the first thing read", () => {
    const cards = buildEntityCards(manifest(ENTRIES), universe(), {
      e_actor: record("rejected", {
        register_fidelity: "fail",
        technical_quality: "fail",
      }),
      e_place: record("rejected", { register_fidelity: "fail" }),
      e_idea: record("admitted"),
    });
    expect(tallyReviewChecks(cards)[0].check).toBe("register_fidelity");
    expect(tallyReviewChecks(cards)[0].failed).toBe(2);
  });

  test("reports every check even when nothing was reviewed", () => {
    const tallies = tallyReviewChecks(
      buildEntityCards(manifest(ENTRIES), universe(), {}),
    );
    expect(tallies).toHaveLength(7);
    expect(
      tallies.every((tally) => tally.passed + tally.failed + tally.other === 0),
    ).toBe(true);
  });
});

describe("presentClasses", () => {
  test("lists only the classes present, in presentation order", () => {
    const cards = buildEntityCards(manifest(ENTRIES), universe(), {});
    expect(presentClasses(cards)).toEqual(["actor", "place", "idea"]);
  });
});

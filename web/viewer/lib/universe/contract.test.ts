// The universe contracts refuse what they do not understand, and translate
// what they do. Fixtures are hand-authored to the shape the producer writes.

import { describe, expect, test } from "bun:test";
import {
  parseAdmittedUniverse,
  parseEntityRecord,
  parseGalleryManifest,
  UNIVERSE_REFUSAL,
} from "./contract";

function manifestDocument(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    schema_version: 1,
    kind: "universe-gallery-manifest-v1",
    universe_id: "the_green_passage",
    title: "The Green Passage",
    medium_id: "anime_2d",
    graph_sha256: "a".repeat(64),
    invocation_id: "inv-1",
    closed_in_graph: true,
    inputs: {
      universe_path: "inputs/universe.json",
      universe_sha256: "b".repeat(64),
      poster_proxy_path: "inputs/poster-proxy.jpg",
    },
    counts: { admitted: 1, rejected: 1 },
    entity_count: 2,
    entities: [
      {
        entity_id: "entity_01",
        display_name: "Iri Vale",
        primary_class: "actor",
        status: "admitted",
        reason: "",
        image: "package/entities/entity_01.png",
        record: "package/entities/entity_01.json",
        review: "production/review/reviews/entity_01.json",
      },
      {
        entity_id: "entity_02",
        display_name: "Asterlock",
        primary_class: "place",
        status: "generation_failed",
        reason: "the route refused the requested size",
        image: null,
        record: null,
        review: null,
      },
    ],
    duration_ms: 1337945,
    known_cost_usd: 11.97,
    publication_authorized: false,
    publication_gate:
      "all entities admitted and a separate human rights review",
    ...overrides,
  };
}

function universeDocument(): Record<string, unknown> {
  return {
    schema_version: 1,
    kind: "universe-admitted-v1",
    universe_id: "the_green_passage",
    title: "The Green Passage",
    medium_id: "anime_2d",
    proposal: {
      premise: {
        claim: "Each forest is one organism.",
        lineage: "explicit_source",
      },
      present_state: {
        claim: "The city is rebuilding.",
        lineage: "explicit_source",
      },
      entities: [
        {
          entity_id: "entity_01",
          display_name: "Iri Vale",
          entity_kind: "human knotwright apprentice",
          primary_class: "actor",
          facets: [],
          salience: "primary",
          summary: "A young knotwright.",
          how_it_works_or_lives: "She certifies anchors.",
          present_tension: "Her certificate is wrong.",
          facts: [
            {
              claim: "She is seventeen.",
              lineage: "explicit_source",
              basis: "stated",
            },
          ],
        },
      ],
      relationships: [
        {
          relationship_id: "rel_001",
          relationship_kind: "located_in",
          relationship_family: "spatial",
          source_entity_id: "entity_01",
          target_entity_id: "entity_02",
          summary: "Iri lives in Asterlock.",
          perspective: "public record",
          temporal_scope: "before and after",
        },
      ],
      identity_markers: [
        {
          marker_id: "marker_01",
          owner_entity_id: "entity_01",
          form: "graduated notches",
          meaning: "accountability to stored water",
          materials: "reservoir stone",
          applied_use: "Officials place a hand beside the level.",
          limits: "It cannot prove policy.",
        },
      ],
      viewpoints: [
        {
          viewpoint_id: "viewpoint_iri",
          display_name: "Iri Vale: Certified Apprentice",
          summary: "A young knotwright enters the crisis.",
          entry_question: "What does a professional owe the public?",
          initially_known: "Guild measurements.",
          anchor_entity_ids: ["entity_01"],
        },
      ],
      institutional_tensions: [
        {
          tension_id: "tension_01",
          summary: "Anchor or let it walk.",
          material_stakes: "Eighty thousand residents.",
          competing_legitimate_needs: "Water against an intact ecology.",
          participant_entity_ids: ["entity_01"],
        },
      ],
      physical_ecological_rules: [
        {
          claim: "A forest migrates when its soil is exhausted.",
          lineage: "explicit_source",
        },
      ],
      unresolved_questions: ["What woke Thalen forty years early?"],
    },
    plan: {
      universe_id: "the_green_passage",
      plans: [
        {
          entity_id: "entity_01",
          primary_purpose: "identify",
          audience_question: "What does Iri risk?",
          scene_premise: "She removes the anchor she certified.",
          in_frame_contrast: "The removed anchor beside the damaged members.",
          concept_mode: "in_world_action",
          lesson_key: "public_certificate_invalidation",
          signature_motif: {
            action_verb: "removing",
            dominant_prop: "certified_ironroot_anchor",
            vantage: "eye_level",
          },
          scene_register: {
            scale: "human",
            time_of_day: "day",
            weather: "dry overcast",
            setting: "works threshold",
            population: "solitary",
            energy: "working",
            weather_justification: "The sealed plan says dry.",
          },
        },
      ],
    },
  };
}

function recordDocument(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    schema_version: 1,
    kind: "universe-entity-record-v1",
    universe_id: "the_green_passage",
    status: "rejected",
    direction_summary: {
      primary_subject: "Seventeen-year-old Iri Vale in compact work layers.",
      action_beat: {
        agent: "Iri Vale.",
        goal: "Withdraw the anchor she certified.",
        obstacle: "The component retains weight and line tension.",
        intervention: "She plants both feet and works the peg free.",
        visible_state_change:
          "The anchor settles detached; its socket stands empty.",
      },
      visual_identity: {
        silhouette: "Compact, braced.",
        proportions: "Adolescent, working.",
        construction_logic: "Layered work cloth over reinforcement.",
        materials: "Work cloth, hemp rope, leather.",
        color_placement: "Subdued blue upper, charcoal trousers.",
        scale_anchor: "The anchor is half her height.",
        wear_and_history: "Chalk marks at the belt.",
        characteristic_motion_or_use: "She observes before committing weight.",
        forbidden_substitutions: ["no ceremonial robes"],
      },
    },
    image: {
      width: 2560,
      height: 1712,
      path: "entities/entity_01.png",
      sha256: "c".repeat(64),
    },
    review: {
      review_id: "review_01",
      entity_id: "entity_01",
      verdict: "reject",
      what_the_image_teaches: "That anchors are certified by hand.",
      blocking_findings: [
        "The sky is blue against a sealed overcast register.",
      ],
      advisory_findings: ["The anchor's detachment is not yet explicit."],
      entity_identity: "pass",
      action_legibility: "pass",
      register_fidelity: "fail",
      medium_fidelity: "pass",
      explanatory_form_absent: "pass",
      readable_text_absent: "pass",
      technical_quality: "pass",
      artifact_sha256: "c".repeat(64),
    },
    ...overrides,
  };
}

describe("parseGalleryManifest", () => {
  test("translates the wire document into runtime shape", () => {
    const manifest = parseGalleryManifest(manifestDocument());
    expect(manifest.title).toBe("The Green Passage");
    expect(manifest.inputs.universePath).toBe("inputs/universe.json");
    expect(manifest.knownCostUsd).toBe(11.97);
    expect(manifest.entities[1].image).toBeNull();
    expect(manifest.entities[1].status).toBe("generation_failed");
  });

  test("refuses a document published under another kind", () => {
    expect(() =>
      parseGalleryManifest(
        manifestDocument({ kind: "universe_v1_gallery_manifest" }),
      ),
    ).toThrow(UNIVERSE_REFUSAL);
  });

  test("refuses a manifest whose entity count disagrees with its list", () => {
    expect(() =>
      parseGalleryManifest(manifestDocument({ entity_count: 3 })),
    ).toThrow(/entity_count/);
  });

  test("refuses an artifact ref that climbs out of the run", () => {
    const document = manifestDocument();
    const entities = document.entities as Record<string, unknown>[];
    entities[0].image = "../../etc/passwd";
    expect(() => parseGalleryManifest(document)).toThrow(/run-relative/);
  });

  test("an unpublished gallery stays unpublished unless it says otherwise", () => {
    expect(parseGalleryManifest(manifestDocument()).publicationAuthorized).toBe(
      false,
    );
    expect(
      parseGalleryManifest(manifestDocument({ publication_authorized: "yes" }))
        .publicationAuthorized,
    ).toBe(false);
  });
});

describe("parseAdmittedUniverse", () => {
  test("carries the prose and the sealed plan across the boundary", () => {
    const universe = parseAdmittedUniverse(universeDocument());
    expect(universe.premise.claim).toBe("Each forest is one organism.");
    expect(universe.entities[0].howItWorksOrLives).toBe(
      "She certifies anchors.",
    );
    expect(universe.relationships[0].kind).toBe("located_in");
    expect(universe.viewpoints[0].anchorEntityIds).toEqual(["entity_01"]);
    expect(universe.unresolvedQuestions).toHaveLength(1);
    expect(universe.plans[0].sceneRegister.timeOfDay).toBe("day");
  });

  test("reads the signature motif as the three strokes it is", () => {
    const motif =
      parseAdmittedUniverse(universeDocument()).plans[0].signatureMotif;
    expect(motif).toEqual({
      actionVerb: "removing",
      dominantProp: "certified_ironroot_anchor",
      vantage: "eye_level",
    });
  });
});

describe("parseEntityRecord", () => {
  test("carries every named check and the findings that explain them", () => {
    const record = parseEntityRecord(recordDocument());
    expect(record.status).toBe("rejected");
    expect(record.review.verdict).toBe("reject");
    expect(record.review.checks.register_fidelity).toBe("fail");
    expect(record.review.checks.medium_fidelity).toBe("pass");
    expect(record.review.blockingFindings).toHaveLength(1);
    expect(record.image).toEqual({ width: 2560, height: 1712 });
  });

  test("reads the compiled direction the finding must be judged against", () => {
    const direction = parseEntityRecord(recordDocument()).direction;
    expect(direction?.actionBeat.visibleStateChange).toContain(
      "socket stands empty",
    );
    expect(direction?.visualIdentity.forbiddenSubstitutions).toEqual([
      "no ceremonial robes",
    ]);
  });

  test("a record without a direction summary is read, not refused", () => {
    expect(
      parseEntityRecord(recordDocument({ direction_summary: null })).direction,
    ).toBeNull();
  });

  test("refuses the spike's dead record kind", () => {
    expect(() =>
      parseEntityRecord(recordDocument({ kind: "universe_v1_entity_record" })),
    ).toThrow(UNIVERSE_REFUSAL);
  });
});

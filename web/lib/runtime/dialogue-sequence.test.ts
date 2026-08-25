import { describe, expect, test } from "bun:test";
import {
  DIALOGUE_EXPRESSION_STATES,
  parseDialogueCharactersManifest,
  verifyDialogueAssetIntegrity,
} from "./dialogue-sequence";

const SOURCE_BUNDLE_SHA256 = "1".repeat(64);
const IDENTITY_SHA256 = "2".repeat(64);
const REVIEW_SHA256 = "3".repeat(64);

const ASSET_DIGESTS = {
  neutral: "4".repeat(64),
  delighted: "5".repeat(64),
  flustered: "6".repeat(64),
  concerned: "7".repeat(64),
} as const;

const PROVENANCE_DIGESTS = {
  neutral: "8".repeat(64),
  delighted: "9".repeat(64),
  flustered: "a".repeat(64),
  concerned: "b".repeat(64),
} as const;

function validManifest() {
  return {
    schema_version: 7,
    recipe: "scrolling-preview",
    tag: "whimsical-storybook-fantasy-6fa8e3e1-ai",
    dialogue_characters: [
      {
        schema_version: 1,
        kind: "dialogue-character-runtime-v1",
        npc_slot: 2,
        npc_name: "Elowen",
        character_id: "elowen",
        source_bundle_sha256: SOURCE_BUNDLE_SHA256,
        identity_sha256: IDENTITY_SHA256,
        available_states: [
          "neutral",
          "delighted",
          "flustered",
          "concerned",
        ],
        assets: DIALOGUE_EXPRESSION_STATES.map((state, index) => ({
          state,
          path: `dialogue-character-${ASSET_DIGESTS[state]}.png`,
          sha256: ASSET_DIGESTS[state],
          bytes: 410_000 + index,
          media_type: "image/png",
          width: 1024,
          height: 1536,
          alpha: true,
          provenance_path: `dialogue-character-${ASSET_DIGESTS[state]}.png.meta.json`,
          provenance_sha256: PROVENANCE_DIGESTS[state],
        })),
        dialogue: [
          {
            id: "elowen-greeting",
            speaker: "Elowen",
            text: "You found the lantern path after all.",
            expression_state: "delighted",
          },
          {
            id: "player-reply",
            speaker: "You",
            text: "The blue lights led me here.",
            expression_state: "neutral",
          },
          {
            id: "elowen-warning",
            speaker: "Elowen",
            text: "Then stay close. The woods are listening tonight.",
            expression_state: "concerned",
          },
          {
            id: "elowen-parting",
            speaker: "Elowen",
            text: "Meet me by the old arch when you are ready.",
            expression_state: "flustered",
          },
        ],
        review: {
          status: "pass",
          usage: "local-demo",
          source_review_sha256: REVIEW_SHA256,
        },
        rights: {
          aggregate: "restricted",
          publication_authorized: false,
        },
      },
    ],
  };
}

type ValidManifest = ReturnType<typeof validManifest>;

describe("dialogue character runtime projection", () => {
  test("parses nested runtime v1 independently inside the current parent v7", () => {
    const result = parseDialogueCharactersManifest(validManifest());

    expect(result.status).toBe("valid");
    expect(result.diagnostic).toBeNull();
    expect(result.characters).toHaveLength(1);
    expect(result.characters[0]).toMatchObject({
      schemaVersion: 1,
      kind: "dialogue-character-runtime-v1",
      npcSlot: 2,
      npcName: "Elowen",
      characterId: "elowen",
      sourceBundleSha256: SOURCE_BUNDLE_SHA256,
      identitySha256: IDENTITY_SHA256,
      availableStates: DIALOGUE_EXPRESSION_STATES,
      review: {
        status: "pass",
        usage: "local-demo",
        sourceReviewSha256: REVIEW_SHA256,
      },
      rights: {
        aggregate: "restricted",
        publicationAuthorized: false,
      },
    });
    expect(result.characters[0]?.assets.map((asset) => asset.state)).toEqual([
      ...DIALOGUE_EXPRESSION_STATES,
    ]);
    expect(result.characters[0]?.dialogue[1]).toEqual({
      id: "player-reply",
      speaker: "You",
      text: "The blue lights led me here.",
      expressionState: "neutral",
    });
    expect(Object.isFrozen(result)).toBeTrue();
    expect(Object.isFrozen(result.characters)).toBeTrue();
    expect(Object.isFrozen(result.characters[0])).toBeTrue();
    expect(Object.isFrozen(result.characters[0]?.assets)).toBeTrue();
    expect(Object.isFrozen(result.characters[0]?.dialogue[0])).toBeTrue();
  });

  test("allows true absence only in parent v7", () => {
    const result = parseDialogueCharactersManifest({
      schema_version: 7,
      recipe: "scrolling-preview",
    });

    expect(result).toEqual({
      status: "absent",
      characters: [],
      diagnostic: null,
    });
    for (const schemaVersion of [1, 4, 5, 6, 8]) {
      expect(() =>
        parseDialogueCharactersManifest({ schema_version: schemaVersion }),
      ).toThrow("manifest schema_version must be 7");
    }
    expect(() => parseDialogueCharactersManifest(null)).toThrow(
      "manifest must be a JSON object",
    );
  });

  test("requires the independent current nested runtime-v1 identity", () => {
    const wrongVersion = validManifest();
    wrongVersion.dialogue_characters[0].schema_version = 2;
    expect(() => parseDialogueCharactersManifest(wrongVersion)).toThrow(
      "schema_version must be 1",
    );
    const wrongKind = validManifest();
    wrongKind.dialogue_characters[0].kind = "dialogue-character-runtime-v2";
    expect(() => parseDialogueCharactersManifest(wrongKind)).toThrow(
      ".kind is unsupported",
    );
  });

  test("rejects a U+FEFF-confusable dialogue key", () => {
    const manifest = validManifest();
    const { dialogue, ...characterWithoutDialogue } =
      manifest.dialogue_characters[0];
    const confusableCharacter = {
      ...characterWithoutDialogue,
      ["dialogue\uFEFF"]: dialogue,
    };

    expect(() =>
      parseDialogueCharactersManifest({
        ...manifest,
        dialogue_characters: [confusableCharacter],
      }),
    ).toThrow("exactly the declared runtime keys");
  });

  test.each([
    {
      label: "character camelCase alias",
      mutate(manifest: ValidManifest) {
        Object.assign(manifest.dialogue_characters[0], {
          characterId: "elowen",
        });
      },
    },
    {
      label: "asset extension",
      mutate(manifest: ValidManifest) {
        Object.assign(manifest.dialogue_characters[0].assets[0], {
          approved: true,
        });
      },
    },
    {
      label: "beat extension",
      mutate(manifest: ValidManifest) {
        Object.assign(manifest.dialogue_characters[0].dialogue[0], {
          voice: "warm",
        });
      },
    },
    {
      label: "review extension",
      mutate(manifest: ValidManifest) {
        Object.assign(manifest.dialogue_characters[0].review, {
          reviewer: "operator",
        });
      },
    },
  ])("rejects an unknown $label key", ({ mutate }) => {
    const manifest = validManifest();
    mutate(manifest);

    expect(() => parseDialogueCharactersManifest(manifest)).toThrow(
      "exactly the declared runtime keys",
    );
  });

  test.each([
    "portraits/dialogue_elowen_neutral.png",
    "../dialogue_elowen_neutral.png",
    "dialogue_elowen_.._neutral.png",
    "/dialogue_elowen_neutral.png",
    "dialogue_elowen_neutral.PNG",
  ])("rejects unsafe or non-canonical PNG path %s", (path) => {
    const manifest = validManifest();
    manifest.dialogue_characters[0].assets[0].path = path;

    expect(() => parseDialogueCharactersManifest(manifest)).toThrow("content-addressed");
  });

  test.each([
    "meta/dialogue_elowen_neutral.png.meta.json",
    "../dialogue_elowen_neutral.png.meta.json",
    "dialogue_elowen_neutral.png..meta.json",
  ])("rejects unsafe provenance path %s", (provenancePath) => {
    const manifest = validManifest();
    manifest.dialogue_characters[0].assets[0].provenance_path = provenancePath;

    expect(() => parseDialogueCharactersManifest(manifest)).toThrow("content-addressed");
  });

  test("binds each asset and provenance filename to the declared asset digest", () => {
    const wrongAsset = validManifest();
    wrongAsset.dialogue_characters[0].assets[0].path =
      `dialogue-character-${ASSET_DIGESTS.delighted}.png`;
    expect(() => parseDialogueCharactersManifest(wrongAsset)).toThrow(
      "content-addressed by the asset sha256",
    );

    const wrongProvenance = validManifest();
    wrongProvenance.dialogue_characters[0].assets[0].provenance_path =
      `dialogue-character-${ASSET_DIGESTS.delighted}.png.meta.json`;
    expect(() => parseDialogueCharactersManifest(wrongProvenance)).toThrow(
      "content-addressed by the asset sha256",
    );
  });

  test.each([
    {
      label: "non-canonical available state order",
      mutate(manifest: ValidManifest) {
        manifest.dialogue_characters[0].available_states = [
          "delighted",
          "neutral",
          "flustered",
          "concerned",
        ];
      },
    },
    {
      label: "missing asset state",
      mutate(manifest: ValidManifest) {
        manifest.dialogue_characters[0].assets.pop();
      },
    },
    {
      label: "duplicate asset state",
      mutate(manifest: ValidManifest) {
        manifest.dialogue_characters[0].assets[3].state = "neutral";
      },
    },
    {
      label: "non-canonical asset state order",
      mutate(manifest: ValidManifest) {
        const first = manifest.dialogue_characters[0].assets[0];
        manifest.dialogue_characters[0].assets[0] =
          manifest.dialogue_characters[0].assets[1];
        manifest.dialogue_characters[0].assets[1] = first;
      },
    },
    {
      label: "wrong asset dimensions",
      mutate(manifest: ValidManifest) {
        manifest.dialogue_characters[0].assets[0].width = 512;
      },
    },
    {
      label: "non-alpha asset",
      mutate(manifest: ValidManifest) {
        manifest.dialogue_characters[0].assets[0].alpha = false;
      },
    },
    {
      label: "unreviewed projection",
      mutate(manifest: ValidManifest) {
        manifest.dialogue_characters[0].review.status = "pending";
      },
    },
    {
      label: "non-local review usage",
      mutate(manifest: ValidManifest) {
        manifest.dialogue_characters[0].review.usage = "public";
      },
    },
    {
      label: "unrestricted rights",
      mutate(manifest: ValidManifest) {
        manifest.dialogue_characters[0].rights.aggregate = "approved";
      },
    },
    {
      label: "publication authorization",
      mutate(manifest: ValidManifest) {
        manifest.dialogue_characters[0].rights.publication_authorized = true;
      },
    },
  ])("fails closed for $label", ({ mutate }) => {
    const manifest = validManifest();
    mutate(manifest);

    expect(() => parseDialogueCharactersManifest(manifest)).toThrow();
  });

  test.each([
    {
      label: "npc slot above the four-resident roster",
      mutate(manifest: ValidManifest) {
        manifest.dialogue_characters[0].npc_slot = 4;
      },
    },
    {
      label: "npc name over 96 characters",
      mutate(manifest: ValidManifest) {
        manifest.dialogue_characters[0].npc_name = "n".repeat(97);
      },
    },
    {
      label: "dialogue id over 48 characters",
      mutate(manifest: ValidManifest) {
        manifest.dialogue_characters[0].dialogue[0].id = "a".repeat(49);
      },
    },
    {
      label: "speaker over 64 characters",
      mutate(manifest: ValidManifest) {
        manifest.dialogue_characters[0].dialogue[0].speaker = "s".repeat(65);
      },
    },
    {
      label: "dialogue text over 320 characters",
      mutate(manifest: ValidManifest) {
        manifest.dialogue_characters[0].dialogue[0].text = "t".repeat(321);
      },
    },
  ])("enforces the producer bound for $label", ({ mutate }) => {
    const manifest = validManifest();
    mutate(manifest);
    expect(() => parseDialogueCharactersManifest(manifest)).toThrow();
  });

  test("rejects the whole declared block when a later character is malformed", () => {
    const manifest = validManifest();
    const second = structuredClone(manifest.dialogue_characters[0]);
    second.npc_slot = 3;
    second.npc_name = "Mira";
    second.character_id = "mira";
    second.assets[2].path = "../mira_flustered.png";
    manifest.dialogue_characters.push(second);

    expect(() => parseDialogueCharactersManifest(manifest)).toThrow("content-addressed");
  });
});

describe("verifyDialogueAssetIntegrity", () => {
  const expected = {
    bytes: 410_000,
    sha256: PROVENANCE_DIGESTS.flustered,
  };

  test("accepts an exact byte-count and lowercase sha256 match", () => {
    expect(verifyDialogueAssetIntegrity({ ...expected }, expected)).toBeTrue();
  });

  test.each([
    {
      label: "byte-count mismatch",
      actual: { ...expected, bytes: expected.bytes + 1 },
    },
    {
      label: "digest mismatch",
      actual: { ...expected, sha256: PROVENANCE_DIGESTS.concerned },
    },
    {
      label: "uppercase digest spelling",
      actual: { ...expected, sha256: expected.sha256.toUpperCase() },
    },
    {
      label: "unsafe byte count",
      actual: { ...expected, bytes: Number.MAX_SAFE_INTEGER + 1 },
    },
  ])("rejects a $label", ({ actual }) => {
    expect(verifyDialogueAssetIntegrity(actual, expected)).toBeFalse();
  });
});

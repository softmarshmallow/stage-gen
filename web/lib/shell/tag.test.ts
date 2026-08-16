import { describe, expect, test } from "bun:test";
import tagFixture from "../../../tests/contract/fixtures/tag-vectors.json";
import { shortHash, slugify, tagFor } from "./tag";
import type { TransparencyMode } from "./transparency";

interface TagVector {
  name: string;
  prompt: string;
  transparencyMode: TransparencyMode;
  slug: string;
  baseTag: string;
  tag: string;
}

const vectors = tagFixture.vectors as TagVector[];

describe("shared Python/web tag vectors", () => {
  for (const vector of vectors) {
    test(vector.name, () => {
      expect(slugify(vector.prompt)).toBe(vector.slug);
      expect(`${vector.slug}-${shortHash(vector.prompt)}`).toBe(vector.baseTag);
      expect(tagFor(vector.prompt, vector.transparencyMode)).toBe(vector.tag);
    });
  }
});

import { afterEach, describe, expect, test } from "bun:test";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  OPENROUTER_IMAGE_MODEL,
  createOpenRouterImageGenerator,
} from "../src/index.ts";

const temporaryDirectories: string[] = [];
const pngBytes = Uint8Array.from([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00,
]);

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true })));
});

describe("createOpenRouterImageGenerator", () => {
  test("returns validated bytes and writes a secret-free provenance sidecar", async () => {
    const directory = await mkdtemp(join(tmpdir(), "stage-gen-image-"));
    temporaryDirectories.push(directory);
    const apiKey = "sk-or-v1-image-secret";
    let requestBody: Record<string, unknown> | undefined;
    const fetchMock: typeof fetch = Object.assign(
      async (_input: RequestInfo | URL, init?: RequestInit) => {
        expect(new Headers(init?.headers).get("authorization")).toBe(`Bearer ${apiKey}`);
        requestBody = JSON.parse(String(init?.body));
        return new Response(
          JSON.stringify({
            created: 123,
            data: [{ b64_json: Buffer.from(pngBytes).toString("base64"), media_type: "image/png" }],
            usage: { cost: 0.1 },
          }),
          { status: 200, headers: { "x-request-id": "request-1" } },
        );
      },
      { preconnect: fetch.preconnect },
    ) as typeof fetch;

    const generator = createOpenRouterImageGenerator({
      apiKey,
      fetch: fetchMock,
      now: () => new Date("2026-08-14T01:02:03.000Z"),
      retry: { sleep: async () => {}, initialDelayMs: 0 },
    });
    const result = await generator.generate({
      prompt: "A neutral asset description",
      artifactPath: join(directory, "asset.png"),
      aspectRatio: "3:2",
      quality: "high",
      inputReferences: [
        {
          url: "data:image/png;base64,AAAA",
          provenanceRef: "inputs/reference.png",
        },
      ],
    });

    expect(result.model).toBe(OPENROUTER_IMAGE_MODEL);
    expect(result.bytes).toEqual(pngBytes);
    expect(result.mediaType).toBe("image/png");
    expect(result.attempts).toBe(1);
    expect(requestBody).toMatchObject({
      model: OPENROUTER_IMAGE_MODEL,
      n: 1,
      aspect_ratio: "3:2",
      quality: "high",
    });
    const sidecar = await readFile(result.provenancePath, "utf8");
    expect(sidecar).not.toContain(apiKey);
    expect(sidecar).not.toContain("AAAA");
    expect(JSON.parse(sidecar)).toMatchObject({
      provider: "openrouter",
      model: OPENROUTER_IMAGE_MODEL,
      seed: null,
      prompt: "A neutral asset description",
      references: ["inputs/reference.png"],
      refs: ["inputs/reference.png"],
      attempts: 1,
    });
  });

  test("retries empty and invalid image payloads", async () => {
    const directory = await mkdtemp(join(tmpdir(), "stage-gen-image-retry-"));
    temporaryDirectories.push(directory);
    let calls = 0;
    const fetchMock = (async () => {
      calls += 1;
      if (calls === 1) return new Response("", { status: 200 });
      if (calls === 2) {
        return Response.json({ data: [{ b64_json: "not-base64", media_type: "image/png" }] });
      }
      return Response.json({
        data: [{ b64_json: Buffer.from(pngBytes).toString("base64"), media_type: "image/png" }],
      });
    }) as unknown as typeof fetch;
    const generator = createOpenRouterImageGenerator({
      apiKey: "test-key",
      fetch: fetchMock,
      retry: { sleep: async () => {}, initialDelayMs: 0 },
    });

    const result = await generator.generate({
      prompt: "retry payload",
      artifactPath: join(directory, "asset.png"),
    });
    expect(calls).toBe(3);
    expect(result.attempts).toBe(3);
  });

  test("runs caller validation inside the provider retry loop", async () => {
    const directory = await mkdtemp(join(tmpdir(), "stage-gen-image-validation-"));
    temporaryDirectories.push(directory);
    let calls = 0;
    const fetchMock = (async () => {
      calls += 1;
      return Response.json({
        data: [{ b64_json: Buffer.from(pngBytes).toString("base64"), media_type: "image/png" }],
      });
    }) as unknown as typeof fetch;
    const generator = createOpenRouterImageGenerator({
      apiKey: "test-key",
      fetch: fetchMock,
      retry: { sleep: async () => {}, initialDelayMs: 0 },
    });

    const result = await generator.generate({
      prompt: "validate dimensions elsewhere",
      artifactPath: join(directory, "asset.png"),
      aspectRatio: "30:43",
      validate() {
        if (calls < 3) throw new Error("dimension mismatch");
      },
    });
    expect(result.attempts).toBe(3);
    expect(calls).toBe(3);
  });
});

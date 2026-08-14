import { afterEach, expect, test } from "bun:test";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  FAL_BACKGROUND_REMOVAL_MODEL,
  createFalBackgroundRemover,
} from "../src/index.ts";

const temporaryDirectories: string[] = [];
const pngBytes = Uint8Array.from([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00,
]);

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true })));
});

test("retries HTTP failures, validates data URI output, and persists provenance", async () => {
  const directory = await mkdtemp(join(tmpdir(), "stage-gen-background-"));
  temporaryDirectories.push(directory);
  const apiKey = "fal-private-key";
  let calls = 0;
  const fetchMock = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    calls += 1;
    expect(new Headers(init?.headers).get("authorization")).toBe(`Key ${apiKey}`);
    if (calls === 1) return new Response("upstream error", { status: 503 });
    return Response.json(
      {
        image: {
          url: `data:image/png;base64,${Buffer.from(pngBytes).toString("base64")}`,
          content_type: "image/png",
          width: 1024,
          height: 1024,
        },
      },
      { headers: { "x-request-id": "fal-request-1" } },
    );
  }) as typeof fetch;
  const remover = createFalBackgroundRemover({
    apiKey,
    fetch: fetchMock,
    retry: { sleep: async () => {}, initialDelayMs: 0 },
  });

  const result = await remover.remove({
    imageUrl: "https://example.com/source.png?signature=secret",
    artifactPath: join(directory, "cutout.png"),
    validate(artifact) {
      expect(artifact.mediaType).toBe("image/png");
    },
  });
  expect(calls).toBe(2);
  expect(result.attempts).toBe(2);
  expect(result.model).toBe(FAL_BACKGROUND_REMOVAL_MODEL);
  expect(result.bytes).toEqual(pngBytes);
  const sidecar = await readFile(result.provenancePath, "utf8");
  expect(sidecar).not.toContain(apiKey);
  expect(sidecar).not.toContain("signature=secret");
  expect(JSON.parse(sidecar)).toMatchObject({ seed: null, references: ["https://example.com/source.png"] });
});

test("downloads hosted output without forwarding the fal credential", async () => {
  const directory = await mkdtemp(join(tmpdir(), "stage-gen-background-download-"));
  temporaryDirectories.push(directory);
  const calls: Array<{ url: string; authorization: string | null }> = [];
  const fetchMock = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, authorization: new Headers(init?.headers).get("authorization") });
    if (url.startsWith("https://fal.run/")) {
      return Response.json({
        image: { url: "https://cdn.example.com/cutout.png", content_type: "image/png" },
      });
    }
    return new Response(pngBytes, { status: 200, headers: { "content-type": "image/png" } });
  }) as typeof fetch;
  const remover = createFalBackgroundRemover({ apiKey: "fal-key", fetch: fetchMock });
  const result = await remover.remove({
    imageUrl: "https://example.com/source.png",
    artifactPath: join(directory, "cutout.png"),
    syncMode: false,
  });

  expect(result.bytes).toEqual(pngBytes);
  expect(calls).toHaveLength(2);
  expect(calls[0].authorization).toBe("Key fal-key");
  expect(calls[1].authorization).toBeNull();
});

test("downloads and exposes a returned mask inside the retry-owned validator", async () => {
  const directory = await mkdtemp(join(tmpdir(), "stage-gen-background-mask-"));
  temporaryDirectories.push(directory);
  const maskBytes = Uint8Array.from([...pngBytes, 0x01]);
  const fetchMock = ((async () =>
    Response.json({
      image: {
        url: `data:image/png;base64,${Buffer.from(pngBytes).toString("base64")}`,
        content_type: "image/png",
      },
      mask_image: {
        url: `data:image/png;base64,${Buffer.from(maskBytes).toString("base64")}`,
        content_type: "image/png",
        width: 1024,
        height: 1024,
      },
    })) as unknown) as typeof fetch;
  let validatedMask: Uint8Array | undefined;
  const remover = createFalBackgroundRemover({ apiKey: "fal-key", fetch: fetchMock });
  const result = await remover.remove({
    imageUrl: "https://example.com/source.png",
    artifactPath: join(directory, "cutout.png"),
    outputMask: true,
    validate(_artifact, context) {
      validatedMask = context.mask?.bytes;
      return { mask_checked: context.mask !== undefined };
    },
  });

  expect(validatedMask).toEqual(maskBytes);
  expect(result.mask?.bytes).toEqual(maskBytes);
  expect(result.mask?.mediaType).toBe("image/png");
  const sidecar = JSON.parse(await readFile(result.provenancePath, "utf8"));
  expect(sidecar.validation).toMatchObject({
    mask_requested: true,
    mask_received: true,
    mask_checked: true,
  });
});

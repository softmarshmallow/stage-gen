import { afterEach, expect, test } from "bun:test";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { createOpenRouterStructuredGenerator } from "../src/index.ts";

const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true })));
});

test("retries invalid JSON and caller schema failures before returning validated data", async () => {
  const directory = await mkdtemp(join(tmpdir(), "stage-gen-structured-"));
  temporaryDirectories.push(directory);
  let calls = 0;
  const fetchMock = (async () => {
    calls += 1;
    if (calls === 1) {
      return Response.json({ choices: [{ message: { content: "" } }] });
    }
    if (calls === 2) {
      return Response.json({ choices: [{ message: { content: JSON.stringify({ count: "bad" }) } }] });
    }
    return Response.json({
      choices: [{ message: { content: JSON.stringify({ count: 3 }) } }],
      usage: { total_tokens: 12 },
    });
  }) as unknown as typeof fetch;
  const generator = createOpenRouterStructuredGenerator({
    apiKey: "test-key",
    model: "author/text-model",
    fetch: fetchMock,
    retry: { sleep: async () => {}, initialDelayMs: 0 },
  });

  const result = await generator.generate({
    prompt: "Return a count",
    artifactPath: join(directory, "value.json"),
    seed: 731,
    schema: {
      name: "count",
      jsonSchema: {
        type: "object",
        properties: { count: { type: "number" } },
        required: ["count"],
        additionalProperties: false,
      },
    },
    parse(value) {
      if (!value || typeof value !== "object" || typeof (value as { count?: unknown }).count !== "number") {
        throw new Error("invalid count");
      }
      return value as { count: number };
    },
  });

  expect(calls).toBe(3);
  expect(result.attempts).toBe(3);
  expect(result.value).toEqual({ count: 3 });
  expect(JSON.parse(await readFile(result.provenancePath, "utf8"))).toMatchObject({
    seed: 731,
    references: [],
    params: { seed: 731 },
  });
});

test("sends strict json_schema output and vision references", async () => {
  const directory = await mkdtemp(join(tmpdir(), "stage-gen-structured-request-"));
  temporaryDirectories.push(directory);
  let body: Record<string, any> | undefined;
  const fetchMock = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    body = JSON.parse(String(init?.body));
    return Response.json({ choices: [{ message: { content: "{\"ok\":true}" } }] });
  }) as unknown as typeof fetch;
  const generator = createOpenRouterStructuredGenerator({
    apiKey: "test-key",
    model: "author/text-model",
    fetch: fetchMock,
  });
  await generator.generate({
    prompt: "Inspect reference",
    artifactPath: join(directory, "value.json"),
    references: [{ url: "data:image/png;base64,AAAA", provenanceRef: "reference.png" }],
    schema: { name: "ok", jsonSchema: { type: "object" } },
    parse: (value) => value,
  });

  expect(body?.response_format).toMatchObject({
    type: "json_schema",
    json_schema: { name: "ok", strict: true },
  });
  expect(body?.provider).toEqual({ require_parameters: true });
  expect(body?.messages[0].content[1].type).toBe("image_url");
});

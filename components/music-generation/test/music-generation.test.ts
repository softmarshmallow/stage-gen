import { afterEach, expect, test } from "bun:test";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  OPENROUTER_MUSIC_MODEL,
  createOpenRouterMusicGenerator,
} from "../src/index.ts";

const temporaryDirectories: string[] = [];
const mp3Bytes = Uint8Array.from([0x49, 0x44, 0x33, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00]);

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true })));
});

test("assembles documented SSE audio chunks and writes provenance", async () => {
  const directory = await mkdtemp(join(tmpdir(), "stage-gen-music-"));
  temporaryDirectories.push(directory);
  const encoded = Buffer.from(mp3Bytes).toString("base64");
  const apiKey = "sk-or-v1-music-secret";
  let requestBody: Record<string, any> | undefined;
  const fetchMock = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    requestBody = JSON.parse(String(init?.body));
    const stream = [
      `data: ${JSON.stringify({ choices: [{ delta: { audio: { data: encoded.slice(0, 8), format: "mp3" } } }] })}`,
      `data: ${JSON.stringify({ choices: [{ delta: { audio: { data: encoded.slice(8), transcript: "instrumental" } } }] })}`,
      "data: [DONE]",
      "",
    ].join("\n\n");
    return new Response(stream, {
      status: 200,
      headers: { "content-type": "text/event-stream", "x-request-id": "music-request-1" },
    });
  }) as unknown as typeof fetch;
  const generator = createOpenRouterMusicGenerator({ apiKey, fetch: fetchMock });
  const result = await generator.generate({
    prompt: "Original instrumental with a timestamped structure.",
    artifactPath: join(directory, "music.mp3"),
    seed: 90210,
    metadata: { stage: "placeholder-music" },
    rights: {
      status: "unreviewed",
      license_id: null,
      notice: "No redistribution approval has been recorded.",
      attribution: [],
      basis: [],
      reviewed_at: null,
    },
  });

  expect(result.model).toBe(OPENROUTER_MUSIC_MODEL);
  expect(result.bytes).toEqual(mp3Bytes);
  expect(result.mediaType).toBe("audio/mpeg");
  expect(result.text).toBe("instrumental");
  expect(requestBody).toMatchObject({
    model: OPENROUTER_MUSIC_MODEL,
    modalities: ["text", "audio"],
    audio: { format: "mp3" },
    stream: true,
  });
  const sidecar = await readFile(result.provenancePath, "utf8");
  expect(sidecar).not.toContain(apiKey);
  const parsedSidecar = JSON.parse(sidecar);
  expect(parsedSidecar.params.metadata.stage).toBe("placeholder-music");
  expect(parsedSidecar).toMatchObject({ seed: 90210, references: [], params: { seed: 90210 } });
  expect(parsedSidecar.rights).toEqual({
    status: "unreviewed",
    license_id: null,
    notice: "No redistribution approval has been recorded.",
    attribution: [],
    basis: [],
    reviewed_at: null,
  });
});

test("retries empty and schema-invalid buffered audio responses", async () => {
  const directory = await mkdtemp(join(tmpdir(), "stage-gen-music-retry-"));
  temporaryDirectories.push(directory);
  let calls = 0;
  const fetchMock = (async () => {
    calls += 1;
    if (calls === 1) return new Response("", { status: 200 });
    if (calls === 2) {
      return Response.json({ choices: [{ message: { audio: { data: "AAAA", format: "mp3" } } }] });
    }
    return Response.json({
      steps: [
        {
          type: "model_output",
          content: [
            { type: "text", text: "structure" },
            { type: "audio", data: Buffer.from(mp3Bytes).toString("base64"), media_type: "audio/mpeg" },
          ],
        },
      ],
    });
  }) as unknown as typeof fetch;
  const generator = createOpenRouterMusicGenerator({
    apiKey: "test-key",
    fetch: fetchMock,
    retry: { sleep: async () => {}, initialDelayMs: 0 },
  });
  const result = await generator.generate({
    prompt: "retry music",
    artifactPath: join(directory, "music.mp3"),
    validate() {
      if (calls < 3) throw new Error("invalid duration");
    },
  });
  expect(calls).toBe(3);
  expect(result.attempts).toBe(3);
  expect(result.text).toBe("structure");
  expect(JSON.parse(await readFile(result.provenancePath, "utf8")).rights).toBeUndefined();
});

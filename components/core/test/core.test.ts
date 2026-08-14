import { afterEach, describe, expect, test } from "bun:test";
import {
  access,
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rename,
  rm,
  writeFile,
} from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  MAX_AI_ATTEMPTS,
  RetryExhaustedError,
  isPortableArtifactReference,
  parseArtifactRights,
  recordArtifactRights,
  hashInputReference,
  redactSecrets,
  sha256Hex,
  withRetry,
  writeArtifactWithProvenance,
  writeProvenance,
  type AtomicFileSystem,
  type ArtifactRights,
  type ArtifactRightsFileSystem,
} from "../src/index.ts";

const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true })));
});

describe("withRetry", () => {
  test("retries network failures and reports the successful attempt", async () => {
    let calls = 0;
    const result = await withRetry(
      async ({ attempt }) => {
        calls += 1;
        if (attempt < 3) throw new TypeError("network unavailable");
        return attempt;
      },
      { sleep: async () => {}, initialDelayMs: 0 },
    );

    expect(result).toBe(3);
    expect(calls).toBe(3);
  });

  test("uses one initial attempt plus five retries and redacts errors", async () => {
    const secret = "sk-or-v1-super-secret";
    let calls = 0;

    try {
      await withRetry(
        async () => {
          calls += 1;
          throw new Error(
            `Authorization: Bearer ${secret} data:image/png;base64,${"A".repeat(80)}`,
          );
        },
        { sleep: async () => {}, initialDelayMs: 0, secrets: [secret] },
      );
      throw new Error("expected retry exhaustion");
    } catch (error) {
      expect(error).toBeInstanceOf(RetryExhaustedError);
      expect(String(error)).not.toContain(secret);
      expect(String((error as Error).cause)).not.toContain(secret);
    }
    expect(calls).toBe(MAX_AI_ATTEMPTS);
    expect(calls).toBe(6);
  });

  test("caller cancellation aborts the active attempt without retrying", async () => {
    const controller = new AbortController();
    const secret = "cancel-private-value";
    let calls = 0;
    const pending = withRetry(
      async ({ signal }) => {
        calls += 1;
        await new Promise<never>((_resolve, reject) => {
          signal.addEventListener("abort", () => reject(new Error(secret)), { once: true });
        });
      },
      {
        signal: controller.signal,
        secrets: [secret],
        sleep: async () => {},
        initialDelayMs: 0,
      },
    );
    controller.abort(new Error(secret));

    try {
      await pending;
      throw new Error("expected cancellation");
    } catch (error) {
      expect((error as Error).name).toBe("AbortError");
      expect(String(error)).not.toContain(secret);
    }
    expect(calls).toBe(1);
  });

  test("per-attempt timeout aborts and retries all six attempts", async () => {
    let calls = 0;
    try {
      await withRetry(
        async ({ signal }) => {
          calls += 1;
          await new Promise<never>((_resolve, reject) => {
            signal.addEventListener(
              "abort",
              () => reject(new Error("provider request aborted")),
              { once: true },
            );
          });
        },
        { timeoutMs: 1, sleep: async () => {}, initialDelayMs: 0 },
      );
      throw new Error("expected timeout exhaustion");
    } catch (error) {
      expect(error).toBeInstanceOf(RetryExhaustedError);
      expect(String(error)).toContain("timed out");
    }
    expect(calls).toBe(6);
  });
});

test("redactSecrets removes explicit and header credentials", () => {
  const secret = "fal-key-private-value";
  const redacted = redactSecrets(
    `authorization=Key ${secret} api_key='${secret}'`,
    [secret],
  );
  expect(redacted).not.toContain(secret);
  expect(redacted).toContain("[REDACTED]");
});

test("redactSecrets removes data URLs and base64 fields", () => {
  const payload = "A".repeat(80);
  const redacted = redactSecrets(
    `data:image/png;base64,${payload} b64_json='${payload}'`,
  );
  expect(redacted).not.toContain(payload);
  expect(redacted).toContain("[REDACTED]");
});

test("writeProvenance persists the required reproducibility fields safely", async () => {
  const directory = await mkdtemp(join(tmpdir(), "stage-gen-core-"));
  temporaryDirectories.push(directory);
  const artifactPath = join(directory, "artifact.bin");
  const secret = "sk-or-v1-sidecar-secret";
  const metaPath = await writeProvenance(
    artifactPath,
    {
      provider: "provider",
      model: "author/model",
      prompt: "plain prompt",
      refs: ["https://example.com/input.png?signature=private", "data:image/png;base64,AAAA"],
      params: { apiKey: secret, quality: "high" },
      timestamp: "2026-08-14T00:00:00.000Z",
      attempts: 2,
    },
    { secrets: [secret] },
  );

  const text = await readFile(metaPath, "utf8");
  const parsed = JSON.parse(text);
  expect(parsed).toMatchObject({
    provider: "provider",
    model: "author/model",
    prompt: "plain prompt",
    ts: "2026-08-14T00:00:00.000Z",
    attempts: 2,
  });
  expect(text).not.toContain(secret);
  expect(text).not.toContain("signature=private");
  expect(text).not.toContain("AAAA");
});

test("paired persistence records hashes, versions, validation, and retry counts", async () => {
  const directory = await mkdtemp(join(tmpdir(), "stage-gen-core-pair-"));
  temporaryDirectories.push(directory);
  const artifactPath = join(directory, "artifact.bin");
  const bytes = Uint8Array.from([1, 2, 3, 4]);
  const input = "data:application/octet-stream;base64,AQID";
  const metaPath = await writeArtifactWithProvenance(
    artifactPath,
    { bytes, mediaType: "application/octet-stream" },
    {
      provider: "provider",
      model: "author/model",
      prompt: "hashed prompt",
      refs: ["input.bin"],
      inputs: [hashInputReference(input, "input.bin")],
      params: { quality: "high" },
      validation: { signature: "matched", dimensions: "32x32" },
      component: { name: "@stage-gen/example", version: "1.2.3" },
      tool: { name: "stage-gen", version: "4.5.6" },
      timestamp: "2026-08-14T00:00:00.000Z",
      attempts: 4,
    },
  );

  expect(new Uint8Array(await readFile(artifactPath))).toEqual(bytes);
  const parsed = JSON.parse(await readFile(metaPath, "utf8"));
  expect(parsed).toMatchObject({
    schema_version: 1,
    prompt_sha256: sha256Hex("hashed prompt"),
    artifact: {
      sha256: sha256Hex(bytes),
      bytes: 4,
      media_type: "application/octet-stream",
    },
    component: { name: "@stage-gen/example", version: "1.2.3" },
    tool: { name: "stage-gen", version: "4.5.6" },
    validation: { signature: "matched", dimensions: "32x32" },
    attempts: 4,
    retries: 3,
  });
  expect(parsed.inputs[0]).toMatchObject({
    ref: "input.bin",
    sha256: sha256Hex(Uint8Array.from([1, 2, 3])),
    source: "content",
  });
});

describe("artifact rights", () => {
  const unreviewed: ArtifactRights = {
    status: "unreviewed",
    license_id: null,
    notice: "No redistribution approval has been recorded.",
    attribution: [],
    basis: [],
    reviewed_at: null,
  };
  const restricted: ArtifactRights = {
    status: "restricted",
    license_id: null,
    notice: "Internal evaluation only.",
    attribution: ["Example provider"],
    basis: ["Provider terms require a restricted disposition."],
    reviewed_at: "2026-08-14T10:00:00.000Z",
  };
  const approved: ArtifactRights = {
    status: "redistribution-approved",
    license_id: "CC0-1.0",
    notice: "RIGHTS.md",
    attribution: [],
    basis: ["Authorized project-owned rights only."],
    reviewed_at: "2026-08-14T10:00:00.000Z",
  };

  test("validates all statuses without inferring approval", async () => {
    expect(parseArtifactRights(unreviewed)).toEqual(unreviewed);
    expect(parseArtifactRights(restricted)).toEqual(restricted);
    expect(parseArtifactRights(approved)).toEqual(approved);

    const directory = await mkdtemp(join(tmpdir(), "stage-gen-rights-absent-"));
    temporaryDirectories.push(directory);
    const artifactPath = join(directory, "artifact.bin");
    const metaPath = await writeArtifactWithProvenance(
      artifactPath,
      { bytes: Uint8Array.from([1]), mediaType: "application/octet-stream" },
      { provider: "provider", model: "model", prompt: "prompt", attempts: 1 },
    );
    const persisted = JSON.parse(await readFile(metaPath, "utf8"));
    expect(persisted.rights).toBeUndefined();
  });

  test("rejects invalid status-dependent fields", () => {
    const invalid = [
      { ...unreviewed, license_id: "CC0-1.0" },
      { ...unreviewed, reviewed_at: "2026-08-14T10:00:00.000Z" },
      { ...restricted, basis: [] },
      { ...restricted, reviewed_at: null },
      { ...approved, license_id: null },
      { ...approved, reviewed_at: "not-a-timestamp" },
      { ...approved, unexpected: true },
    ];
    for (const value of invalid) {
      expect(() => parseArtifactRights(value)).toThrow();
    }
  });

  test("records rights only when artifact digest matches", async () => {
    const directory = await mkdtemp(join(tmpdir(), "stage-gen-rights-record-"));
    temporaryDirectories.push(directory);
    const artifactPath = join(directory, "artifact.bin");
    const metaPath = await writeArtifactWithProvenance(
      artifactPath,
      { bytes: Uint8Array.from([1, 2, 3]), mediaType: "application/octet-stream" },
      {
        provider: "provider",
        model: "model",
        prompt: "prompt",
        refs: ["brief.txt"],
        attempts: 1,
        rights: unreviewed,
      },
    );

    expect(await recordArtifactRights(artifactPath, approved)).toBe(metaPath);
    expect(JSON.parse(await readFile(metaPath, "utf8")).rights).toEqual(approved);

    await writeFile(artifactPath, Uint8Array.from([9, 9, 9]));
    const before = await readFile(metaPath, "utf8");
    await expect(recordArtifactRights(artifactPath, restricted)).rejects.toThrow(
      "do not match provenance digest",
    );
    expect(await readFile(metaPath, "utf8")).toBe(before);
  });

  test("keeps the original sidecar and removes staging files when atomic replace fails", async () => {
    const directory = await mkdtemp(join(tmpdir(), "stage-gen-rights-atomic-"));
    temporaryDirectories.push(directory);
    const artifactPath = join(directory, "artifact.bin");
    const metaPath = await writeArtifactWithProvenance(
      artifactPath,
      { bytes: Uint8Array.from([4, 5, 6]), mediaType: "application/octet-stream" },
      {
        provider: "provider",
        model: "model",
        prompt: "prompt",
        attempts: 1,
        rights: unreviewed,
      },
    );
    const before = await readFile(metaPath, "utf8");
    const fileSystem: ArtifactRightsFileSystem = {
      async mkdir(path) {
        await mkdir(path, { recursive: true });
      },
      async readFile(path) {
        return new Uint8Array(await readFile(path));
      },
      async writeFile(path, data) {
        await writeFile(path, data, { flag: "wx" });
      },
      async rename() {
        throw new Error("atomic replace failed");
      },
      async rm(path) {
        await rm(path, { force: true });
      },
    };

    await expect(
      recordArtifactRights(artifactPath, restricted, { fileSystem }),
    ).rejects.toThrow("atomic replace failed");
    expect(await readFile(metaPath, "utf8")).toBe(before);
    expect((await readdir(directory)).filter((entry) => entry.endsWith(".tmp"))).toEqual([]);
  });

  test("rejects unsafe references when approval is recorded", async () => {
    expect(isPortableArtifactReference(`sha256:${"a".repeat(64)}`)).toBe(true);
    expect(isPortableArtifactReference("assets/music/source.mp3")).toBe(true);
    for (const reference of [
      "/tmp/private/source.mp3",
      "file:///private/source.mp3",
      "data:audio/mpeg;base64,AAAA",
      "https://user:password@example.com/source.mp3",
      "https://example.com/source.mp3?signature=private",
      "https://127.0.0.1/source.mp3",
      "../private/source.mp3",
    ]) {
      expect(isPortableArtifactReference(reference)).toBe(false);
    }

    const directory = await mkdtemp(join(tmpdir(), "stage-gen-rights-unsafe-"));
    temporaryDirectories.push(directory);
    const artifactPath = join(directory, "artifact.bin");
    await writeArtifactWithProvenance(
      artifactPath,
      { bytes: Uint8Array.from([7]), mediaType: "application/octet-stream" },
      {
        provider: "provider",
        model: "model",
        prompt: "prompt",
        refs: ["/Users/private/source.bin"],
        attempts: 1,
        rights: unreviewed,
      },
    );
    await expect(recordArtifactRights(artifactPath, approved)).rejects.toThrow(
      "unsafe reference in references",
    );
  });
});

test("paired persistence removes both outputs and staged files when commit fails", async () => {
  const directory = await mkdtemp(join(tmpdir(), "stage-gen-core-rollback-"));
  temporaryDirectories.push(directory);
  const artifactPath = join(directory, "artifact.bin");
  const metaPath = `${artifactPath}.meta.json`;
  const secretPayload = "A".repeat(80);
  const fileSystem: AtomicFileSystem = {
    async mkdir(path) {
      await mkdir(path, { recursive: true });
    },
    async writeFile(path, data) {
      await writeFile(path, data, { flag: "wx" });
    },
    async rename(from, to) {
      if (to === metaPath) {
        throw new Error(`commit failed data:image/png;base64,${secretPayload}`);
      }
      await rename(from, to);
    },
    async rm(path) {
      await rm(path, { force: true, recursive: true });
    },
    async access(path) {
      await access(path);
    },
  };

  try {
    await writeArtifactWithProvenance(
      artifactPath,
      { bytes: Uint8Array.from([1]), mediaType: "application/octet-stream" },
      {
        provider: "provider",
        model: "model",
        prompt: "prompt",
        attempts: 1,
      },
      { fileSystem },
    );
    throw new Error("expected paired commit failure");
  } catch (error) {
    expect(String(error)).not.toContain(secretPayload);
  }
  expect(await exists(artifactPath)).toBe(false);
  expect(await exists(metaPath)).toBe(false);
  expect(await readdir(directory)).toEqual([]);
});

async function exists(path: string): Promise<boolean> {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

import { createHash } from "node:crypto";
import { promises as fs } from "node:fs";
import path from "node:path";

export const GAMEPLAY_BUILD_SOURCE_DIRECTORIES = Object.freeze([
  "app",
  "lib",
  "types",
  "public",
  "scripts",
  "tests",
]);

export const GAMEPLAY_BUILD_SOURCE_FILES = Object.freeze([
  "package.json",
  "bun.lock",
  "next.config.mjs",
  "next-env.d.ts",
  "tsconfig.json",
]);

const SOURCE_LIMITS = Object.freeze({
  maxFiles: 8_192,
  maxDirectories: 8_192,
  maxFileBytes: 16 * 1024 * 1024,
  maxTotalBytes: 128 * 1024 * 1024,
});
const BUILD_LIMITS = Object.freeze({
  maxFiles: 4_096,
  maxDirectories: 2_048,
  maxFileBytes: 64 * 1024 * 1024,
  maxTotalBytes: 256 * 1024 * 1024,
});
const PACKAGE_LIMIT_BYTES = 1_000_000;
const DEPENDENCY_TREE_LIMITS = Object.freeze({
  maxFiles: 16_384,
  maxDirectories: 8_192,
  maxFileBytes: 256 * 1024 * 1024,
  maxTotalBytes: 512 * 1024 * 1024,
});
const DEPENDENCY_CLOSURE_LIMITS = Object.freeze({
  maxPackages: 512,
  maxFiles: 100_000,
  maxDirectories: 50_000,
  maxTotalBytes: 2 * 1024 * 1024 * 1024,
});
const NEXT_BUILD_ID = /^[A-Za-z0-9_-]{1,128}$/;
const BUILD_CONTEXT_EXCLUDED_ROOT_NAMES = new Set([
  ".next",
  ".turbo",
  ".vercel",
  ".git",
  ".ds_store",
  "build",
  "coverage",
  "dist",
  "node_modules",
  "out",
  "output",
  "playwright-report",
  "report",
  "reports",
  "test-results",
  "tsconfig.tsbuildinfo",
]);
const BUILD_CONTEXT_SECRET_ROOT_NAMES = new Set([
  ".npmrc",
  ".pypirc",
  ".yarnrc",
  ".yarnrc.yml",
  ".aws",
  ".ssh",
]);

export type CanonicalTreeFile = Readonly<{
  name: string;
  sha256: string;
  bytes: number;
}>;

export type CanonicalTreeSnapshot = Readonly<{
  digest: string;
  fileCount: number;
  directoryCount: number;
  totalBytes: number;
  files: readonly CanonicalTreeFile[];
}>;

export type CanonicalTreeIdentity = Readonly<{
  digest: string;
  fileCount: number;
  directoryCount: number;
  totalBytes: number;
}>;

export type ServedNextBuildSnapshot = CanonicalTreeSnapshot &
  Readonly<{ buildId: string }>;

export type RecorderDependencyIdentity = Readonly<{
  digest: string;
  lockSha256: string;
  packageJsonSha256: string;
  nextCliPath: "node_modules/next/dist/bin/next";
  nextCliSha256: string;
  runtimeExecutable: Readonly<{
    locator: "process.execPath";
    sha256: string;
    bytes: number;
  }>;
  packages: Readonly<Record<string, string>>;
  implementations: Readonly<Record<string, CanonicalTreeIdentity>>;
}>;

type InternalFile = CanonicalTreeFile & Readonly<{ contents: Buffer }>;
type SnapshotLimits = Readonly<{
  maxFiles: number;
  maxDirectories: number;
  maxFileBytes: number;
  maxTotalBytes: number;
}>;

function sha256(value: string | Uint8Array): string {
  return createHash("sha256").update(value).digest("hex");
}

function assertSafeEntryName(name: string): void {
  if (
    !name ||
    name !== name.normalize("NFC") ||
    name !== name.trim() ||
    name === "." ||
    name === ".." ||
    Buffer.byteLength(name, "utf8") > 255 ||
    /[\\/\0-\x20\x7f:*?"<>|]/.test(name) ||
    /[^\x21-\x7e]/.test(name)
  ) {
    throw new Error("build input contains an unsafe or noncanonical name");
  }
}

function assertSafeDependencyEntryName(name: string): void {
  if (
    !name ||
    name !== name.normalize("NFC") ||
    name !== name.trim() ||
    name === "." ||
    name === ".." ||
    Buffer.byteLength(name, "utf8") > 255 ||
    /[\\/\0-\x1f\x7f]/.test(name)
  ) {
    throw new Error(
      "dependency implementation contains an unsafe or noncanonical name",
    );
  }
}

async function realDirectory(target: string, label: string): Promise<string> {
  const resolved = path.resolve(target);
  const stat = await fs.lstat(resolved).catch(() => {
    throw new Error(`${label} must be a real directory`);
  });
  if (!stat.isDirectory() || stat.isSymbolicLink()) {
    throw new Error(`${label} must be a real directory`);
  }
  return await fs.realpath(resolved);
}

function snapshotDigest(files: readonly CanonicalTreeFile[]): string {
  return sha256(
    files
      .map((file) => `${file.name}:${file.sha256}:${file.bytes}\n`)
      .join(""),
  );
}

async function collectCanonicalPaths(
  root: string,
  directories: readonly string[],
  rootFiles: readonly string[],
  limits: SnapshotLimits,
  copyTo?: string,
  expectedRootNames?: readonly string[],
  expectedRootIdentity?: Readonly<{ dev: number; ino: number }>,
): Promise<CanonicalTreeSnapshot> {
  const trustedRoot = await realDirectory(root, "snapshot root");
  const trustedRootStat = await fs.lstat(trustedRoot);
  if (
    expectedRootIdentity &&
    (trustedRootStat.dev !== expectedRootIdentity.dev ||
      trustedRootStat.ino !== expectedRootIdentity.ino)
  ) {
    throw new Error("build context root identity changed before snapshot");
  }
  const identities = new Set<string>();
  const directoryNames: string[] = [];
  const files: InternalFile[] = [];
  let totalBytes = 0;

  const register = (relative: string): void => {
    const parts = relative.split("/");
    for (const part of parts) assertSafeEntryName(part);
    const identity = relative.normalize("NFC").toLocaleLowerCase("en-US");
    if (identities.has(identity)) {
      throw new Error("build inputs collide by case or Unicode normalization");
    }
    identities.add(identity);
  };

  const readFile = async (target: string, relative: string): Promise<void> => {
    register(relative);
    const before = await fs.lstat(target);
    if (
      !before.isFile() ||
      before.isSymbolicLink() ||
      before.size <= 0 ||
      before.size > limits.maxFileBytes
    ) {
      throw new Error("build inputs must be bounded nonempty regular files");
    }
    if ((await fs.realpath(target)) !== target) {
      throw new Error("build inputs must not use symlinked path components");
    }
    const contents = await fs.readFile(target);
    const after = await fs.lstat(target);
    if (
      !after.isFile() ||
      after.isSymbolicLink() ||
      after.dev !== before.dev ||
      after.ino !== before.ino ||
      after.size !== before.size ||
      after.mtimeMs !== before.mtimeMs ||
      contents.byteLength !== before.size ||
      (await fs.realpath(target)) !== target
    ) {
      throw new Error("build input changed while it was read");
    }
    totalBytes += contents.byteLength;
    if (totalBytes > limits.maxTotalBytes) {
      throw new Error("build inputs exceed the total byte limit");
    }
    files.push(
      Object.freeze({
        name: relative,
        sha256: sha256(contents),
        bytes: contents.byteLength,
        contents,
      }),
    );
    if (files.length > limits.maxFiles) {
      throw new Error("build inputs exceed the file-count limit");
    }
  };

  const visit = async (directory: string, prefix: string): Promise<void> => {
    register(prefix);
    directoryNames.push(prefix);
    if (directoryNames.length > limits.maxDirectories) {
      throw new Error("build inputs exceed the directory-count limit");
    }
    const before = await fs.lstat(directory);
    if (!before.isDirectory() || before.isSymbolicLink()) {
      throw new Error("build inputs must not contain symlinked directories");
    }
    if ((await fs.realpath(directory)) !== directory) {
      throw new Error("build inputs must not use symlinked path components");
    }
    const names = (await fs.readdir(directory)).sort();
    if (names.length === 0) {
      throw new Error("build inputs must not contain empty directories");
    }
    for (const name of names) {
      assertSafeEntryName(name);
      const relative = `${prefix}/${name}`;
      const target = path.join(directory, name);
      if (!target.startsWith(`${trustedRoot}${path.sep}`)) {
        throw new Error("build input escapes its root");
      }
      const stat = await fs.lstat(target);
      if (stat.isSymbolicLink()) {
        throw new Error("build inputs must not contain symlinks");
      }
      if (stat.isDirectory()) {
        await visit(target, relative);
      } else if (stat.isFile()) {
        await readFile(target, relative);
      } else {
        throw new Error("build inputs must not contain special files");
      }
    }
    const [after, afterNames] = await Promise.all([
      fs.lstat(directory),
      fs.readdir(directory),
    ]);
    if (
      !after.isDirectory() ||
      after.isSymbolicLink() ||
      after.dev !== before.dev ||
      after.ino !== before.ino ||
      after.mtimeMs !== before.mtimeMs ||
      JSON.stringify(afterNames.sort()) !== JSON.stringify(names) ||
      (await fs.realpath(directory)) !== directory
    ) {
      throw new Error("build input directory changed while it was read");
    }
  };

  for (const relative of directories) {
    if (path.posix.normalize(relative) !== relative || relative.startsWith("/")) {
      throw new Error("build input directory contract is invalid");
    }
    const target = path.join(trustedRoot, ...relative.split("/"));
    await visit(target, relative);
  }
  for (const relative of rootFiles) {
    if (
      relative.includes("/") ||
      path.posix.normalize(relative) !== relative
    ) {
      throw new Error("build input file contract is invalid");
    }
    await readFile(path.join(trustedRoot, relative), relative);
  }

  if (expectedRootNames) {
    const [currentRootStat, currentRootNames] = await Promise.all([
      fs.lstat(trustedRoot),
      fs.readdir(trustedRoot),
    ]);
    if (
      (expectedRootIdentity &&
        (currentRootStat.dev !== expectedRootIdentity.dev ||
          currentRootStat.ino !== expectedRootIdentity.ino)) ||
      JSON.stringify(currentRootNames.sort()) !==
        JSON.stringify(expectedRootNames)
    ) {
      throw new Error("build context root changed while it was read");
    }
  }

  files.sort((left, right) => left.name.localeCompare(right.name, "en-US"));
  directoryNames.sort(
    (left, right) =>
      left.split("/").length - right.split("/").length ||
      left.localeCompare(right, "en-US"),
  );
  if (copyTo) {
    const requestedDestination = path.resolve(copyTo);
    const destinationName = path.basename(requestedDestination);
    assertSafeEntryName(destinationName);
    const destinationParent = await realDirectory(
      path.dirname(requestedDestination),
      "build snapshot destination parent",
    );
    const destination = path.join(destinationParent, destinationName);
    await fs.mkdir(destination, { mode: 0o700 });
    const destinationStat = await fs.lstat(destination);
    const destinationReal = await fs.realpath(destination);
    if (
      !destinationStat.isDirectory() ||
      destinationStat.isSymbolicLink() ||
      destinationReal !== destination
    ) {
      throw new Error("build snapshot destination must be a real directory");
    }
    const ensureDestinationDirectory = async (
      relative: string,
    ): Promise<void> => {
      let current = destination;
      for (const segment of relative.split("/")) {
        current = path.join(current, segment);
        try {
          await fs.mkdir(current, { mode: 0o700 });
        } catch (error) {
          if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
        }
        const stat = await fs.lstat(current);
        if (
          !stat.isDirectory() ||
          stat.isSymbolicLink() ||
          (await fs.realpath(current)) !== current
        ) {
          throw new Error(
            "build snapshot destination contains an unsafe directory",
          );
        }
      }
    };
    for (const relative of directoryNames) {
      await ensureDestinationDirectory(relative);
    }
    for (const file of files) {
      const target = path.join(destination, ...file.name.split("/"));
      await fs.writeFile(target, file.contents, { flag: "wx", mode: 0o600 });
    }
  }

  const publicFiles = Object.freeze(
    files.map(({ name, sha256, bytes }) =>
      Object.freeze({ name, sha256, bytes }),
    ),
  );
  return Object.freeze({
    digest: snapshotDigest(publicFiles),
    fileCount: publicFiles.length,
    directoryCount: directoryNames.length,
    totalBytes,
    files: publicFiles,
  });
}

function isExcludedBuildContextRoot(name: string): boolean {
  const folded = name.toLocaleLowerCase("en-US");
  return (
    folded.startsWith(".env") ||
    /^(?:credentials?|secrets?)(?:[._-].*)?$/.test(folded) ||
    BUILD_CONTEXT_EXCLUDED_ROOT_NAMES.has(folded) ||
    BUILD_CONTEXT_SECRET_ROOT_NAMES.has(folded)
  );
}

async function discoverGameplayBuildContext(webRoot: string): Promise<{
  root: string;
  rootIdentity: Readonly<{ dev: number; ino: number }>;
  directories: readonly string[];
  files: readonly string[];
  rootNames: readonly string[];
}> {
  const trustedRoot = await realDirectory(webRoot, "snapshot root");
  const rootBefore = await fs.lstat(trustedRoot);
  const rootNames = (await fs.readdir(trustedRoot)).sort();
  const identities = new Set<string>();
  const directories: string[] = [];
  const files: string[] = [];
  for (const name of rootNames) {
    assertSafeEntryName(name);
    const identity = name.normalize("NFC").toLocaleLowerCase("en-US");
    if (identities.has(identity)) {
      throw new Error("build context roots collide by case or Unicode normalization");
    }
    identities.add(identity);
    if (isExcludedBuildContextRoot(name)) continue;
    const target = path.join(trustedRoot, name);
    const stat = await fs.lstat(target);
    if (stat.isSymbolicLink()) {
      throw new Error("build context roots must not contain symlinks");
    }
    if (stat.isDirectory()) directories.push(name);
    else if (stat.isFile()) files.push(name);
    else throw new Error("build context roots must not contain special files");
  }
  for (const required of GAMEPLAY_BUILD_SOURCE_DIRECTORIES) {
    if (!directories.includes(required)) {
      throw new Error(`build context is missing required directory ${required}`);
    }
  }
  for (const required of GAMEPLAY_BUILD_SOURCE_FILES) {
    if (!files.includes(required)) {
      throw new Error(`build context is missing required file ${required}`);
    }
  }
  const [rootAfter, namesAfter] = await Promise.all([
    fs.lstat(trustedRoot),
    fs.readdir(trustedRoot),
  ]);
  if (
    rootAfter.dev !== rootBefore.dev ||
    rootAfter.ino !== rootBefore.ino ||
    JSON.stringify(namesAfter.sort()) !== JSON.stringify(rootNames)
  ) {
    throw new Error("build context root changed during discovery");
  }
  return Object.freeze({
    root: trustedRoot,
    rootIdentity: Object.freeze({ dev: rootBefore.dev, ino: rootBefore.ino }),
    directories: Object.freeze(directories),
    files: Object.freeze(files),
    rootNames: Object.freeze(rootNames),
  });
}

export async function snapshotGameplayBuildInputs(
  webRoot: string,
  copyTo?: string,
): Promise<CanonicalTreeSnapshot> {
  const context = await discoverGameplayBuildContext(webRoot);
  return await collectCanonicalPaths(
    context.root,
    context.directories,
    context.files,
    SOURCE_LIMITS,
    copyTo,
    context.rootNames,
    context.rootIdentity,
  );
}

export function assertCanonicalSnapshotsEqual(
  expected: CanonicalTreeSnapshot,
  actual: CanonicalTreeSnapshot,
  label: string,
): void {
  if (JSON.stringify(expected) !== JSON.stringify(actual)) {
    throw new Error(`${label} changed; refusing to use or install the capture`);
  }
}

function stripTrailingJsonCommas(text: string): string {
  let result = "";
  let quoted = false;
  let escaped = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index]!;
    if (quoted) {
      result += char;
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === '"') quoted = false;
      continue;
    }
    if (char === '"') {
      quoted = true;
      result += char;
      continue;
    }
    if (char === ",") {
      let lookahead = index + 1;
      while (/\s/.test(text[lookahead] ?? "")) lookahead += 1;
      if (text[lookahead] === "}" || text[lookahead] === "]") continue;
    }
    result += char;
  }
  return result;
}

function isWithin(root: string, target: string): boolean {
  return target === root || target.startsWith(`${root}${path.sep}`);
}

async function boundedDependencyFile(
  target: string,
  lexicalRoot: string,
  allowedRealRoots: readonly string[],
  label: string,
): Promise<Buffer> {
  const resolved = path.resolve(target);
  if (!isWithin(lexicalRoot, resolved) || resolved === lexicalRoot) {
    throw new Error(`${label} escapes node_modules`);
  }
  const before = await fs.lstat(resolved).catch(() => {
    throw new Error(`${label} is missing`);
  });
  const realBefore = await fs.realpath(resolved).catch(() => {
    throw new Error(`${label} cannot be resolved`);
  });
  if (
    !before.isFile() ||
    before.isSymbolicLink() ||
    before.size <= 0 ||
    before.size > PACKAGE_LIMIT_BYTES ||
    !allowedRealRoots.some((root) => isWithin(root, realBefore))
  ) {
    throw new Error(`${label} is unsafe`);
  }
  const contents = await fs.readFile(resolved);
  const after = await fs.lstat(resolved);
  const realAfter = await fs.realpath(resolved);
  if (
    !after.isFile() ||
    after.isSymbolicLink() ||
    after.dev !== before.dev ||
    after.ino !== before.ino ||
    after.size !== before.size ||
    after.mtimeMs !== before.mtimeMs ||
    realAfter !== realBefore ||
    contents.byteLength !== before.size
  ) {
    throw new Error(`${label} changed while it was read`);
  }
  return contents;
}

async function boundedRuntimeExecutable(): Promise<{
  sha256: string;
  bytes: number;
}> {
  const target = path.resolve(process.execPath);
  const before = await fs.lstat(target);
  if (
    !before.isFile() ||
    before.isSymbolicLink() ||
    before.size <= 0 ||
    before.size > DEPENDENCY_TREE_LIMITS.maxFileBytes ||
    (await fs.realpath(target)) !== target
  ) {
    throw new Error("recorder runtime executable is unsafe");
  }
  const contents = await fs.readFile(target);
  const after = await fs.lstat(target);
  if (
    !after.isFile() ||
    after.isSymbolicLink() ||
    after.dev !== before.dev ||
    after.ino !== before.ino ||
    after.size !== before.size ||
    after.mtimeMs !== before.mtimeMs ||
    contents.byteLength !== before.size ||
    (await fs.realpath(target)) !== target
  ) {
    throw new Error("recorder runtime executable changed while it was read");
  }
  return Object.freeze({ sha256: sha256(contents), bytes: contents.byteLength });
}

type DependencyTreeSnapshot = CanonicalTreeIdentity &
  Readonly<{ packageJsonSha256: string }>;

async function snapshotDependencyTreeRoot(
  packageRoot: string,
): Promise<DependencyTreeSnapshot> {
  const trustedRoot = await realDirectory(
    packageRoot,
    "dependency implementation root",
  );
  const identities = new Set<string>();
  const files: CanonicalTreeFile[] = [];
  let directoryCount = 1;
  let totalBytes = 0;

  const register = (relative: string): void => {
    for (const part of relative.split("/"))
      assertSafeDependencyEntryName(part);
    const identity = relative.normalize("NFC").toLocaleLowerCase("en-US");
    if (identities.has(identity)) {
      throw new Error(
        "dependency implementation collides by case or Unicode normalization",
      );
    }
    identities.add(identity);
  };

  const readFile = async (target: string, relative: string): Promise<void> => {
    register(relative);
    const before = await fs.lstat(target);
    if (
      !before.isFile() ||
      before.isSymbolicLink() ||
      before.size > DEPENDENCY_TREE_LIMITS.maxFileBytes ||
      (await fs.realpath(target)) !== target
    ) {
      throw new Error(
        "dependency implementation must contain bounded regular files",
      );
    }
    const contents = await fs.readFile(target);
    const after = await fs.lstat(target);
    if (
      !after.isFile() ||
      after.isSymbolicLink() ||
      after.dev !== before.dev ||
      after.ino !== before.ino ||
      after.size !== before.size ||
      after.mtimeMs !== before.mtimeMs ||
      contents.byteLength !== before.size ||
      (await fs.realpath(target)) !== target
    ) {
      throw new Error("dependency implementation changed while it was read");
    }
    totalBytes += contents.byteLength;
    if (totalBytes > DEPENDENCY_TREE_LIMITS.maxTotalBytes) {
      throw new Error("dependency implementation exceeds the byte limit");
    }
    files.push(
      Object.freeze({
        name: relative,
        sha256: sha256(contents),
        bytes: contents.byteLength,
      }),
    );
    if (files.length > DEPENDENCY_TREE_LIMITS.maxFiles) {
      throw new Error("dependency implementation exceeds the file-count limit");
    }
  };

  const visit = async (directory: string, prefix: string): Promise<void> => {
    const before = await fs.lstat(directory);
    if (
      !before.isDirectory() ||
      before.isSymbolicLink() ||
      (await fs.realpath(directory)) !== directory
    ) {
      throw new Error("dependency implementation must not contain symlinks");
    }
    const names = (await fs.readdir(directory)).sort();
    if (names.length === 0) {
      throw new Error("dependency implementation must not contain empty directories");
    }
    for (const name of names) {
      assertSafeDependencyEntryName(name);
      const relative = prefix ? `${prefix}/${name}` : name;
      const target = path.join(directory, name);
      if (!isWithin(trustedRoot, target) || target === trustedRoot) {
        throw new Error("dependency implementation escapes its package root");
      }
      const stat = await fs.lstat(target);
      if (stat.isSymbolicLink()) {
        throw new Error("dependency implementation must not contain symlinks");
      }
      if (stat.isDirectory()) {
        register(relative);
        directoryCount += 1;
        if (directoryCount > DEPENDENCY_TREE_LIMITS.maxDirectories) {
          throw new Error(
            "dependency implementation exceeds the directory-count limit",
          );
        }
        await visit(target, relative);
      } else if (stat.isFile()) {
        await readFile(target, relative);
      } else {
        throw new Error("dependency implementation contains a special file");
      }
    }
    const [after, afterNames] = await Promise.all([
      fs.lstat(directory),
      fs.readdir(directory),
    ]);
    if (
      !after.isDirectory() ||
      after.isSymbolicLink() ||
      after.dev !== before.dev ||
      after.ino !== before.ino ||
      after.mtimeMs !== before.mtimeMs ||
      JSON.stringify(afterNames.sort()) !== JSON.stringify(names) ||
      (await fs.realpath(directory)) !== directory
    ) {
      throw new Error(
        "dependency implementation directory changed while it was read",
      );
    }
  };

  await visit(trustedRoot, "");
  files.sort((left, right) => left.name.localeCompare(right.name, "en-US"));
  const packageJson = files.find((file) => file.name === "package.json");
  if (!packageJson) {
    throw new Error("dependency implementation is missing package.json");
  }
  return Object.freeze({
    digest: snapshotDigest(files),
    fileCount: files.length,
    directoryCount,
    totalBytes,
    packageJsonSha256: packageJson.sha256,
  });
}

export async function snapshotRecorderImplementationTree(
  packageRoot: string,
): Promise<CanonicalTreeIdentity> {
  const { packageJsonSha256: _packageJsonSha256, ...identity } =
    await snapshotDependencyTreeRoot(packageRoot);
  return Object.freeze(identity);
}

function validPackageName(name: string): boolean {
  return /^(?:@[A-Za-z0-9._-]+\/)?[A-Za-z0-9._-]+$/.test(name);
}

async function resolveInstalledPackageDirectory(
  nodeModules: string,
  allowedRealRoots: readonly string[],
  name: string,
): Promise<string> {
  if (!validPackageName(name)) {
    throw new Error("installed dependency name is unsafe");
  }
  const lexical = path.join(nodeModules, ...name.split("/"));
  if (!isWithin(nodeModules, lexical) || lexical === nodeModules) {
    throw new Error(`installed ${name} package escapes node_modules`);
  }
  const stat = await fs.lstat(lexical).catch(() => {
    throw new Error(`installed ${name} package is missing`);
  });
  const real = await fs.realpath(lexical).catch(() => {
    throw new Error(`installed ${name} package cannot be resolved`);
  });
  const realStat = await fs.stat(real);
  if (
    !realStat.isDirectory() ||
    (!stat.isDirectory() && !stat.isSymbolicLink()) ||
    !allowedRealRoots.some((root) => isWithin(root, real) && real !== root) ||
    (!stat.isSymbolicLink() && real !== lexical)
  ) {
    throw new Error(`installed ${name} package root is unsafe`);
  }
  return real;
}

function dependencyNames(
  packageRecord: Record<string, unknown>,
  field: "dependencies" | "optionalDependencies",
): readonly string[] {
  const value = packageRecord[field];
  if (value === undefined) return [];
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`installed package ${field} metadata is malformed`);
  }
  const names = Object.keys(value as Record<string, unknown>).sort();
  if (names.some((name) => !validPackageName(name))) {
    throw new Error(`installed package ${field} contains an unsafe name`);
  }
  return names;
}

export async function validateRecorderDependencies(
  webRoot: string,
): Promise<RecorderDependencyIdentity> {
  const trustedRoot = await realDirectory(webRoot, "web dependency root");
  const nodeModules = path.join(trustedRoot, "node_modules");
  const trustedNodeModules = await realDirectory(nodeModules, "node_modules");
  if (trustedNodeModules !== nodeModules) {
    throw new Error("node_modules must not use symlinked path components");
  }
  const bunStore = path.join(path.dirname(trustedRoot), "node_modules", ".bun");
  const allowedRealRoots = [trustedNodeModules];
  const bunStoreStat = await fs.lstat(bunStore).catch(() => undefined);
  if (bunStoreStat?.isDirectory() && !bunStoreStat.isSymbolicLink()) {
    allowedRealRoots.push(await fs.realpath(bunStore));
  }
  const packageBytes = await fs.readFile(path.join(trustedRoot, "package.json"));
  const lockBytes = await fs.readFile(path.join(trustedRoot, "bun.lock"));
  let packageValue: unknown;
  let lockValue: unknown;
  try {
    packageValue = JSON.parse(packageBytes.toString("utf8"));
    lockValue = JSON.parse(stripTrailingJsonCommas(lockBytes.toString("utf8")));
  } catch {
    throw new Error("package.json and bun.lock must be valid locked metadata");
  }
  const packageRecord = packageValue as Record<string, unknown>;
  const lockRecord = lockValue as Record<string, unknown>;
  const declared = {
    ...((packageRecord.dependencies ?? {}) as Record<string, string>),
    ...((packageRecord.devDependencies ?? {}) as Record<string, string>),
  };
  const workspace = ((lockRecord.workspaces as Record<string, unknown>)[
    ""
  ] ?? {}) as Record<string, unknown>;
  const lockedDeclared = {
    ...((workspace.dependencies ?? {}) as Record<string, string>),
    ...((workspace.devDependencies ?? {}) as Record<string, string>),
  };
  if (JSON.stringify(declared) !== JSON.stringify(lockedDeclared)) {
    throw new Error("bun.lock workspace dependencies do not match package.json");
  }
  const lockPackages = lockRecord.packages as Record<string, unknown>;
  if (!lockPackages || typeof lockPackages !== "object") {
    throw new Error("bun.lock packages are missing");
  }
  const versions: Record<string, string> = {};
  const identityLines: string[] = [];
  for (const name of Object.keys(declared).sort()) {
    const relativePackage = `${name}/package.json`;
    const bytes = await boundedDependencyFile(
      path.join(trustedNodeModules, ...relativePackage.split("/")),
      trustedNodeModules,
      allowedRealRoots,
      `installed ${name} package metadata`,
    );
    let installed: unknown;
    try {
      installed = JSON.parse(bytes.toString("utf8"));
    } catch {
      throw new Error(`installed ${name} package metadata is malformed`);
    }
    const installedRecord = installed as Record<string, unknown>;
    if (
      installedRecord.name !== name ||
      typeof installedRecord.version !== "string" ||
      !/^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$/.test(
        installedRecord.version,
      )
    ) {
      throw new Error(`installed ${name} version is invalid`);
    }
    const lockEntry = lockPackages[name];
    if (
      !Array.isArray(lockEntry) ||
      lockEntry[0] !== `${name}@${installedRecord.version}`
    ) {
      throw new Error(`installed ${name} version does not match bun.lock`);
    }
    versions[name] = installedRecord.version;
    identityLines.push(`${name}:${installedRecord.version}:${sha256(bytes)}\n`);
  }

  const implementations: Record<string, CanonicalTreeIdentity> = {};
  const implementationLines: string[] = [];
  const queued = [...Object.keys(declared).sort()];
  const visited = new Set<string>();
  let implementationFileCount = 0;
  let implementationDirectoryCount = 0;
  let implementationTotalBytes = 0;
  while (queued.length > 0) {
    const name = queued.shift()!;
    if (visited.has(name)) continue;
    if (visited.size >= DEPENDENCY_CLOSURE_LIMITS.maxPackages) {
      throw new Error("recorder dependency closure exceeds the package limit");
    }
    visited.add(name);
    const packageRoot = await resolveInstalledPackageDirectory(
      trustedNodeModules,
      allowedRealRoots,
      name,
    );
    const manifestBytes = await boundedDependencyFile(
      path.join(trustedNodeModules, ...name.split("/"), "package.json"),
      trustedNodeModules,
      allowedRealRoots,
      `installed ${name} implementation metadata`,
    );
    let manifest: Record<string, unknown>;
    try {
      manifest = JSON.parse(manifestBytes.toString("utf8")) as Record<
        string,
        unknown
      >;
    } catch {
      throw new Error(`installed ${name} implementation metadata is malformed`);
    }
    if (manifest.name !== name || typeof manifest.version !== "string") {
      throw new Error(`installed ${name} implementation identity is invalid`);
    }
    const tree = await snapshotDependencyTreeRoot(packageRoot);
    if (tree.packageJsonSha256 !== sha256(manifestBytes)) {
      throw new Error(`installed ${name} metadata changed during tree snapshot`);
    }
    implementationFileCount += tree.fileCount;
    implementationDirectoryCount += tree.directoryCount;
    implementationTotalBytes += tree.totalBytes;
    if (
      implementationFileCount > DEPENDENCY_CLOSURE_LIMITS.maxFiles ||
      implementationDirectoryCount >
        DEPENDENCY_CLOSURE_LIMITS.maxDirectories ||
      implementationTotalBytes > DEPENDENCY_CLOSURE_LIMITS.maxTotalBytes
    ) {
      throw new Error("recorder dependency closure exceeds its global limits");
    }
    const {
      packageJsonSha256: _packageJsonSha256,
      ...publicTree
    } = tree;
    implementations[name] = Object.freeze(publicTree);
    implementationLines.push(
      `${name}:${manifest.version}:${publicTree.digest}:${publicTree.fileCount}:${publicTree.directoryCount}:${publicTree.totalBytes}\n`,
    );
    for (const dependency of dependencyNames(manifest, "dependencies")) {
      if (!visited.has(dependency)) queued.push(dependency);
    }
    for (const dependency of dependencyNames(
      manifest,
      "optionalDependencies",
    )) {
      const candidate = path.join(
        trustedNodeModules,
        ...dependency.split("/"),
      );
      if (await fs.lstat(candidate).catch(() => undefined)) {
        if (!visited.has(dependency)) queued.push(dependency);
      }
    }
    queued.sort();
  }
  const nextCliPath = "node_modules/next/dist/bin/next" as const;
  const nextCliBytes = await boundedDependencyFile(
    path.join(trustedRoot, ...nextCliPath.split("/")),
    trustedNodeModules,
    allowedRealRoots,
    "installed Next CLI",
  );
  const nextCliSha256 = sha256(nextCliBytes);
  const runtimeExecutable = await boundedRuntimeExecutable();
  const lockSha256 = sha256(lockBytes);
  const packageJsonSha256 = sha256(packageBytes);
  return Object.freeze({
    digest: sha256(
      `${packageJsonSha256}\n${lockSha256}\n${nextCliSha256}\n${runtimeExecutable.sha256}:${runtimeExecutable.bytes}\n${identityLines.join("")}${implementationLines.sort().join("")}`,
    ),
    lockSha256,
    packageJsonSha256,
    nextCliPath,
    nextCliSha256,
    runtimeExecutable: Object.freeze({
      locator: "process.execPath",
      ...runtimeExecutable,
    }),
    packages: Object.freeze({ ...versions }),
    implementations: Object.freeze({ ...implementations }),
  });
}

export async function linkRecorderDependencies(
  webRoot: string,
  applicationRoot: string,
): Promise<void> {
  const trustedWeb = await realDirectory(webRoot, "web dependency root");
  const trustedApplication = await realDirectory(
    applicationRoot,
    "recorder application root",
  );
  const dependencies = await realDirectory(
    path.join(trustedWeb, "node_modules"),
    "node_modules",
  );
  await fs.symlink(
    dependencies,
    path.join(trustedApplication, "node_modules"),
    "dir",
  );
}

export async function pruneNonRuntimeNextArtifacts(
  applicationRoot: string,
): Promise<void> {
  const trustedApplication = await realDirectory(
    applicationRoot,
    "recorder application root",
  );
  const nextRoot = path.join(trustedApplication, ".next");
  await realDirectory(nextRoot, "owned Next build");
  for (const relative of ["cache", "diagnostics", "types", "trace"] as const) {
    await fs.rm(path.join(nextRoot, relative), {
      recursive: true,
      force: true,
    });
  }
}

export async function snapshotServedNextBuild(
  applicationRoot: string,
): Promise<ServedNextBuildSnapshot> {
  const trustedApplication = await realDirectory(
    applicationRoot,
    "recorder application root",
  );
  const snapshot = await collectCanonicalPaths(
    trustedApplication,
    [".next"],
    [],
    BUILD_LIMITS,
  );
  const buildIdBytes = await fs.readFile(
    path.join(trustedApplication, ".next", "BUILD_ID"),
  );
  const buildIdFile = snapshot.files.find(
    (file) => file.name === ".next/BUILD_ID",
  );
  if (
    !buildIdFile ||
    buildIdFile.sha256 !== sha256(buildIdBytes) ||
    buildIdFile.bytes !== buildIdBytes.byteLength
  ) {
    throw new Error("served Next BUILD_ID changed during snapshot");
  }
  const buildId = buildIdBytes.toString("utf8").trim();
  if (!NEXT_BUILD_ID.test(buildId)) {
    throw new Error("served Next BUILD_ID is invalid");
  }
  for (const required of [
    ".next/BUILD_ID",
    ".next/build-manifest.json",
    ".next/routes-manifest.json",
    ".next/required-server-files.json",
  ]) {
    if (!snapshot.files.some((file) => file.name === required)) {
      throw new Error(`served Next build is missing ${path.basename(required)}`);
    }
  }
  if (
    !snapshot.files.some((file) => file.name.startsWith(".next/server/")) ||
    !snapshot.files.some((file) => file.name.startsWith(".next/static/"))
  ) {
    throw new Error("served Next build must bind server and static trees");
  }
  return Object.freeze({ ...snapshot, buildId });
}

export function assertDependencyIdentityEqual(
  expected: RecorderDependencyIdentity,
  actual: RecorderDependencyIdentity,
): void {
  if (JSON.stringify(expected) !== JSON.stringify(actual)) {
    throw new Error("recorder dependency identity changed");
  }
}

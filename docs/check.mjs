#!/usr/bin/env bun

import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, extname, join, resolve } from "node:path";
import { checkGeneratedMediaPublication } from "./media-rights.mjs";

const repo = resolve(import.meta.dirname, "..");
const doctrine = [
  join(repo, "README.md"),
  join(repo, "CONTRIBUTING.md"),
  join(repo, "ARCHITECTURE.md"),
  join(repo, "MISSION.md"),
  join(repo, "LOOP_PROMPT.md"),
];
const governance = [join(repo, "AGENTS.md"), join(repo, "TODO.md")];
const envExamplePath = join(repo, ".env.example");
const stageGenConfigPath = join(repo, "stage-gen", "src", "config.ts");
const generatedMediaInventoryPath = join(repo, "docs", "generated-media-inventory.json");
const promptFixtures = [
  join(repo, "fixtures", "prompts.txt"),
  join(repo, "fixtures", "styles.txt"),
];
const markdownRoots = [...doctrine, join(repo, "docs")];
const markdown = [];

function walk(path) {
  if (!existsSync(path)) return;
  const stat = statSync(path);
  if (stat.isDirectory()) {
    for (const name of readdirSync(path)) walk(join(path, name));
  } else if (extname(path) === ".md") {
    markdown.push(path);
  }
}

for (const path of markdownRoots) walk(path);

const failures = [];
const generatedMedia = checkGeneratedMediaPublication(repo, generatedMediaInventoryPath);
for (const failure of generatedMedia.failures) {
  failures.push(`generated-media: ${failure}`);
}
const linkPattern = /\[[^\]]*\]\(([^)]+)\)/g;

const envExample = readFileSync(envExamplePath, "utf8");
const envAssignments = new Map(
  [...envExample.matchAll(/^([A-Z][A-Z0-9_]*)=(.*)$/gm)].map((match) => [
    match[1],
    match[2],
  ]),
);
const consumedEnvNames = new Set(
  [...readFileSync(stageGenConfigPath, "utf8").matchAll(/\benv\.([A-Z][A-Z0-9_]*)\b/g)].map(
    (match) => match[1],
  ),
);
for (const name of consumedEnvNames) {
  if (!envAssignments.has(name)) {
    failures.push(`.env.example: missing stage-gen config name ${name}`);
  }
}
if (envAssignments.get("TRANSPARENCY_MODE") !== "ai") {
  failures.push(".env.example: TRANSPARENCY_MODE must document the ai default");
}
for (const secretName of ["OPENROUTER_API_KEY", "FAL_KEY"]) {
  if ((envAssignments.get(secretName) ?? "") !== "") {
    failures.push(`.env.example: ${secretName} must remain blank`);
  }
}

for (const file of markdown) {
  const source = readFileSync(file, "utf8");
  for (const match of source.matchAll(linkPattern)) {
    let target = match[1].trim();
    if (!target || /^(https?:|mailto:|#)/.test(target)) continue;
    if (target.startsWith("<") && target.endsWith(">")) target = target.slice(1, -1);
    target = decodeURIComponent(target.split("#", 1)[0].split("?", 1)[0]);
    const resolved = resolve(dirname(file), target);
    if (!existsSync(resolved)) failures.push(`${file.slice(repo.length + 1)}: missing link ${match[1]}`);
  }
}

const publicText = [
  ...doctrine,
  ...governance,
  ...promptFixtures,
  join(repo, "docs"),
  join(repo, "web"),
];
const textFiles = [];

function walkText(path) {
  if (!existsSync(path)) return;
  const stat = statSync(path);
  if (stat.isDirectory()) {
    for (const name of readdirSync(path)) {
      if (name === ".next" || name === "node_modules" || name === "public") continue;
      walkText(join(path, name));
    }
  } else if ([".md", ".txt", ".ts", ".tsx", ".mjs"].includes(extname(path))) {
    textFiles.push(path);
  }
}

for (const path of publicText) walkText(path);

const stale = [
  ["legacy gateway key", new RegExp(["AI", "GATEWAY", "API", "KEY"].join("_"))],
  ["legacy gateway URL", new RegExp(["ai-gateway", "vercel", "sh"].join("\\."))],
  ["legacy gateway name", new RegExp(["Vercel", "AI", "Gateway"].join(" "), "i")],
  ["legacy gateway shorthand", new RegExp(["vercel", "ai", "gateway"].join("[-\\s]+"), "i")],
  ["legacy pipeline workspace", new RegExp(["pipeline", ""].join("/"))],
  ["legacy recording directory", new RegExp(["fixtures", "bgm"].join("/"), "i")],
  ["legacy curated recording claim", new RegExp(["BGM", "is", "curated"].join("\\s+"), "i")],
  ["legacy no-audio rule", new RegExp(["do", "not", "add", "audio", "generation"].join("\\s+"), "i")],
  ["pinned browser engine rule", new RegExp(["do", "not", "replace", "Phaser"].join("\\s+"), "i")],
  ["private absolute path", /\/Users\/[A-Za-z0-9._-]+\//],
  [
    "unconditional exact-key background rule",
    /\b(?:all|every)\s+(?:sprite|transparent|transparency-producing)[^\n]*(?:magenta|#FF00FF)/i,
  ],
  [
    "automatic chroma fallback",
    /(?:automatically|silently)\s+(?:fall(?:s|ing)?\s+back|switch(?:es|ing)?)\s+to\s+chroma/i,
  ],
];

for (const file of textFiles) {
  const source = readFileSync(file, "utf8");
  for (const [label, pattern] of stale) {
    if (pattern.test(source)) failures.push(`${file.slice(repo.length + 1)}: ${label}`);
  }
  const accountFundingCode = new RegExp(`\\b${["TOP", "UP"].join("_")}\\b`);
  if (file !== join(repo, "TODO.md") && accountFundingCode.test(source)) {
    failures.push(`${file.slice(repo.length + 1)}: account-specific funding note outside TODO.md`);
  }
}

const picker = join(repo, "web/app/Picker.tsx");
const promptPolicyFiles = [...promptFixtures, picker];
const imitationPatterns = [
  /\bin the style of\b/i,
  /\bstyle of\b/i,
  /\binspired by\b/i,
  /\blike\s+["'A-Z]/,
  /\bmeets\s+["'A-Z]/,
];

for (const file of promptPolicyFiles) {
  if (!existsSync(file)) continue;
  const source = readFileSync(file, "utf8");
  for (const pattern of imitationPatterns) {
    if (pattern.test(source)) {
      failures.push(`${file.slice(repo.length + 1)}: imitation-style prompt language`);
      break;
    }
  }
}

for (const file of promptFixtures) {
  if (!existsSync(file)) continue;
  const lines = readFileSync(file, "utf8")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.startsWith("- "));
  if (file.endsWith("prompts.txt") && lines.some((line) => !line.startsWith("- Create an original "))) {
    failures.push("fixtures/prompts.txt: every preset must explicitly request an original result");
  }
  if (file.endsWith("styles.txt") && lines.some((line) => /["'()]|\b(?:game|film|studio|artist)\b/i.test(line))) {
    failures.push("fixtures/styles.txt: style hints must remain neutral property descriptions");
  }
}

const readme = readFileSync(join(repo, "README.md"), "utf8");
if (!/\bgeneral\b/i.test(readme) || !/optional web-based scrolling-game\s+preview/i.test(readme)) {
  failures.push("README.md: missing general-core / optional-preview framing");
}

const generatedMediaPolicy = readFileSync(
  join(repo, "docs", "generated-media-publication.md"),
  "utf8",
);
const publicationPolicyRequirements = [
  [/runtime-unreviewed[\s\S]*repository-approved/i, "runtime/repository status boundary"],
  [/provenance[\s\S]{0,160}not a redistribution grant/i, "provenance rights boundary"],
  [/SynthID[\s\S]{0,220}not been independently verified/i, "SynthID verification status"],
  [/BSD-3-Clause[\s\S]{0,180}CC0/i, "no blanket source/output license claim"],
];
for (const [pattern, label] of publicationPolicyRequirements) {
  if (!pattern.test(generatedMediaPolicy)) {
    failures.push(`docs/generated-media-publication.md: missing ${label}`);
  }
}

const requiredTransparencyContract = [
  ["README.md", /default[^\n]*--transparency ai/i, "AI CLI default"],
  ["README.md", /--transparency chroma/i, "explicit chroma CLI fallback"],
  ["README.md", /FAL_KEY[\s\S]{0,160}not\s+required/i, "conditional FAL_KEY requirement"],
  ["docs/spec/agent-prompts.md", /neutral gr(?:a|e)y|naturally isolated/i, "AI isolation prompt"],
  ["docs/spec/agent-prompts.md", /exact `#FF00FF`/i, "exact degraded fallback key"],
  ["docs/spec/agent-prompts.md", /opaque[^\n]*(?:neither|omit|bypass)/i, "opaque exclusion"],
  ["docs/web-preview.md", /input\.transparencyMode/, "manifest strategy field"],
  ["docs/web-preview.md", /legacy manifests?[\s\S]{0,120}(?:predate|omit|missing|do not declare)/i, "legacy-only compatibility"],
  ["web/app/Picker.tsx", /aria-label="AI background removal"/, "background removal control"],
  ["web/lib/shell/transparency.ts", /DEFAULT_TRANSPARENCY_MODE[^\n]*= "ai"/, "web default"],
  ["web/lib/shell/transparency.ts", /mode === null \? "legacy-chroma" : "canonical-alpha"/, "legacy preview boundary"],
];

for (const [relative, pattern, label] of requiredTransparencyContract) {
  const source = readFileSync(join(repo, relative), "utf8");
  if (!pattern.test(source)) failures.push(`${relative}: missing ${label}`);
}

if (failures.length > 0) {
  for (const failure of failures) process.stderr.write(`docs-check: ${failure}\n`);
  process.exit(1);
}

process.stdout.write(
  `docs-check: ok (${markdown.length} markdown files, ${textFiles.length} public text files, ${generatedMedia.mediaCount} generated-media files)\n`,
);

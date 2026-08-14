import { createHash } from "node:crypto";
import {
  existsSync,
  lstatSync,
  readFileSync,
  readdirSync,
} from "node:fs";
import { extname, isAbsolute, join, relative, resolve, sep } from "node:path";

const MEDIA_EXTENSIONS = new Set([
  ".aac",
  ".flac",
  ".gif",
  ".jpeg",
  ".jpg",
  ".m4a",
  ".mp3",
  ".mp4",
  ".ogg",
  ".png",
  ".wav",
  ".webm",
  ".webp",
]);
const AUDIO_EXTENSIONS = new Set([".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav"]);
const SHA256 = /^[a-f0-9]{64}$/;
const ISO_TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/;
const UNSTABLE_REF = /^(?:file:|data:|[A-Za-z]:[\\/])|(?:^|[\\/])(?:tmp|private\/tmp|var\/folders|Users)(?:[\\/]|$)|(?:^|[\\/])\.\.(?:[\\/]|$)/i;
const PLACEHOLDER = /^(?:tbd|todo|pending|unknown|none|n\/a)$/i;

function isRecord(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function stableText(value) {
  return typeof value === "string" && value.trim().length > 2 && !PLACEHOLDER.test(value.trim());
}

function validTimestamp(value) {
  return typeof value === "string" && ISO_TIMESTAMP.test(value) && !Number.isNaN(Date.parse(value));
}

function safeRepoPath(repo, path) {
  if (typeof path !== "string" || !path || isAbsolute(path) || path.includes("\\")) return false;
  const absolute = resolve(repo, path);
  return absolute.startsWith(`${resolve(repo)}${sep}`) && relative(repo, absolute) === path;
}

function validateSourceInputs(sidecar, errors) {
  if (!Array.isArray(sidecar.inputs) || sidecar.inputs.length === 0) {
    errors.push("sidecar.inputs must contain content-addressed source records");
    return;
  }
  sidecar.inputs.forEach((input, index) => {
    if (!isRecord(input)) {
      errors.push(`sidecar.inputs[${index}] must be an object`);
      return;
    }
    if (!stableText(input.ref) || UNSTABLE_REF.test(input.ref)) {
      errors.push(`sidecar.inputs[${index}].ref must be a stable non-file identifier`);
    }
    if (!SHA256.test(input.sha256 ?? "")) {
      errors.push(`sidecar.inputs[${index}].sha256 must be a content digest`);
    } else if (input.ref !== `sha256:${input.sha256}`) {
      errors.push(`sidecar.inputs[${index}].ref must match its sha256 content identifier`);
    }
    if (!Number.isSafeInteger(input.bytes) || input.bytes <= 0) {
      errors.push(`sidecar.inputs[${index}].bytes must be a positive integer`);
    }
  });
}

function validateRights(entry, sidecar, isAudio, errors) {
  if (entry.reviewStatus !== "repository-approved") {
    errors.push("inventory reviewStatus must be repository-approved");
  }
  const rights = sidecar.rights;
  if (!isRecord(rights)) {
    errors.push("sidecar.rights is required for repository publication");
    return;
  }
  if (rights.status !== "redistribution-approved") {
    errors.push("sidecar.rights.status must be redistribution-approved");
  }
  if (!stableText(rights.notice) || UNSTABLE_REF.test(rights.notice)) {
    errors.push("sidecar.rights.notice must be a stable reviewed value");
  }
  if (!stableText(rights.license_id) || UNSTABLE_REF.test(rights.license_id)) {
    errors.push("sidecar.rights.license_id must be a stable reviewed value");
  }
  if (
    !Array.isArray(rights.basis) ||
    rights.basis.length === 0 ||
    rights.basis.some((basis) => !stableText(basis) || UNSTABLE_REF.test(basis))
  ) {
    errors.push("sidecar.rights.basis must contain stable reviewed values");
  } else if (
    rights.basis.every((basis) => /^\s*(?:provider|model)?\s*provenance(?:\s+only)?[.!]?\s*$/i.test(basis))
  ) {
    errors.push("sidecar.rights.basis cannot rely only on provider provenance");
  }
  if (!validTimestamp(rights.reviewed_at)) {
    errors.push("sidecar.rights.reviewed_at must be an ISO UTC timestamp");
  }
  if (rights.license_id === "BSD-3-Clause") {
    errors.push("the repository source license cannot be inherited by generated media");
  }
  if (
    rights.license_id === "CC0-1.0" &&
    !rights.basis?.some((basis) => /artifact-specific rights-holder dedication/i.test(basis))
  ) {
    errors.push("CC0 requires an artifact-specific rights-holder dedication basis");
  }
  if (!isRecord(entry.synthId)) {
    errors.push("inventory synthId review record is required");
  } else {
    if (entry.synthId.expected !== true) {
      errors.push("inventory synthId.expected must record the expected watermark");
    }
    if (typeof entry.synthId.independentlyVerified !== "boolean") {
      errors.push("inventory synthId.independentlyVerified must be explicit");
    }
  }
  if (isAudio) {
    const review = entry.listeningReview;
    if (!isRecord(review) || review.status !== "approved") {
      errors.push("inventory listeningReview.status must be approved");
    } else {
      if (!stableText(review.reviewedBy)) {
        errors.push("inventory listeningReview.reviewedBy is required");
      }
      if (!stableText(review.authorityBasis)) {
        errors.push("inventory listeningReview.authorityBasis is required");
      }
      if (
        review.result !==
        "no recognizable protected composition, lyrics, performer, voice, brand, or mark"
      ) {
        errors.push("inventory listeningReview.result must record the protected-material finding");
      }
      if (review.approvalScope !== "project-controlled rights, if any") {
        errors.push("inventory listeningReview.approvalScope must remain artifact-scoped");
      }
      if (!validTimestamp(review.reviewedAt)) {
        errors.push("inventory listeningReview.reviewedAt must be an ISO UTC timestamp");
      }
      if (!stableText(review.attestationId) || UNSTABLE_REF.test(review.attestationId)) {
        errors.push("inventory listeningReview.attestationId must be stable");
      } else if (!rights.basis?.includes(review.attestationId)) {
        errors.push("sidecar.rights.basis must include the listening attestation identifier");
      }
      if (!validTimestamp(review.attestedAt) || review.attestedAt !== review.reviewedAt) {
        errors.push("inventory listeningReview.attestedAt must match reviewedAt");
      }
    }
  }
}

export function validatePublishedMediaRecord({ entry, observed, sidecar }) {
  const errors = [];
  if (!isRecord(entry) || !stableText(entry.path)) {
    return ["inventory entry path is required"];
  }
  if (!isRecord(sidecar)) {
    return ["sidecar must be a JSON object"];
  }
  if (!SHA256.test(observed?.sha256 ?? "") || !Number.isSafeInteger(observed?.bytes)) {
    errors.push("observed media digest and byte size are required");
  }
  if (sidecar.artifact?.sha256 !== observed?.sha256) {
    errors.push("sidecar artifact digest does not match media bytes");
  }
  if (sidecar.artifact?.bytes !== observed?.bytes) {
    errors.push("sidecar artifact byte size does not match media bytes");
  }
  validateSourceInputs(sidecar, errors);
  validateRights(entry, sidecar, AUDIO_EXTENSIONS.has(extname(entry.path).toLowerCase()), errors);
  return errors;
}

function discoverMedia(repo, roots, failures) {
  const media = [];
  const visit = (absolute) => {
    for (const name of readdirSync(absolute)) {
      const path = join(absolute, name);
      const stat = lstatSync(path);
      if (stat.isSymbolicLink()) {
        failures.push(`${relative(repo, path)}: generated-media roots cannot contain symlinks`);
      } else if (stat.isDirectory()) {
        visit(path);
      } else if (MEDIA_EXTENSIONS.has(extname(name).toLowerCase())) {
        media.push(relative(repo, path));
      }
    }
  };
  for (const root of roots) {
    if (!safeRepoPath(repo, root)) {
      failures.push(`generated-media inventory root is unsafe: ${String(root)}`);
      continue;
    }
    const absolute = resolve(repo, root);
    if (!existsSync(absolute)) {
      failures.push(`generated-media inventory root is missing: ${root}`);
      continue;
    }
    visit(absolute);
  }
  return media.sort();
}

export function checkGeneratedMediaPublication(repo, inventoryPath) {
  const failures = [];
  let inventory;
  try {
    inventory = JSON.parse(readFileSync(inventoryPath, "utf8"));
  } catch {
    return { failures: ["generated-media inventory is missing or invalid JSON"], mediaCount: 0 };
  }
  if (!isRecord(inventory) || inventory.schemaVersion !== 1) {
    return { failures: ["generated-media inventory schemaVersion must be 1"], mediaCount: 0 };
  }
  if (!Array.isArray(inventory.roots) || !Array.isArray(inventory.media)) {
    return { failures: ["generated-media inventory roots and media must be arrays"], mediaCount: 0 };
  }

  const discovered = discoverMedia(repo, inventory.roots, failures);
  const entries = new Map();
  for (const entry of inventory.media) {
    if (!isRecord(entry) || !safeRepoPath(repo, entry.path)) {
      failures.push("generated-media inventory contains an unsafe media path");
      continue;
    }
    if (entries.has(entry.path)) failures.push(`${entry.path}: duplicate inventory entry`);
    entries.set(entry.path, entry);
  }
  for (const path of discovered) {
    if (!entries.has(path)) failures.push(`${path}: binary media is not enumerated in the inventory`);
  }
  for (const [path, entry] of entries) {
    if (!discovered.includes(path)) {
      failures.push(`${path}: inventory entry does not resolve to discovered binary media`);
      continue;
    }
    const absolute = resolve(repo, path);
    const sidecarPath = `${absolute}.meta.json`;
    if (!existsSync(sidecarPath)) {
      failures.push(`${path}: adjacent provenance sidecar is missing`);
      continue;
    }
    let sidecar;
    try {
      sidecar = JSON.parse(readFileSync(sidecarPath, "utf8"));
    } catch {
      failures.push(`${path}: adjacent provenance sidecar is invalid JSON`);
      continue;
    }
    const bytes = readFileSync(absolute);
    const observed = {
      bytes: bytes.byteLength,
      sha256: createHash("sha256").update(bytes).digest("hex"),
    };
    for (const failure of validatePublishedMediaRecord({ entry, observed, sidecar })) {
      failures.push(`${path}: ${failure}`);
    }
  }
  return { failures, mediaCount: discovered.length };
}

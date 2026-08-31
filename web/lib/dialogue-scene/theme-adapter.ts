import { createHash, randomUUID } from "node:crypto";
import {
  copyFile,
  lstat,
  mkdir,
  open,
  readFile,
  readdir,
  realpath,
  rename,
  rm,
  stat,
  unlink,
} from "node:fs/promises";
import path from "node:path";
import { inflateSync } from "node:zlib";
import {
  DIALOGUE_SCENE_DEMO_AUTHORSHIP,
  DIALOGUE_SCENE_DEMO_MODE,
  DIALOGUE_SCENE_DEMO_SCHEMA_VERSION,
  DIALOGUE_SCENE_EXPRESSION_STATES,
  parseDialogueSceneThemeFixture,
  serializeDialogueSceneThemeFixture,
  validateDialogueSceneRuntimeFixture,
  type DialogueSceneDemoFixture,
  type DialogueSceneExpressionState,
} from "./schema";

export const DIALOGUE_THEME_ADAPTER_VERSION = 3 as const;

const SHA256 = /^[a-f0-9]{64}$/;
const STABLE_ID = /^[a-z][a-z0-9-]*$/;
const SNAKE_ID = /^[a-z0-9]+(?:_[a-z0-9]+)*$/;
const PORTABLE_SEGMENT = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
const MAX_JSON_BYTES = 8 * 1024 * 1024;
const MAX_PNG_BYTES = 64 * 1024 * 1024;
const PNG_SIGNATURE = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
const JSON_SCHEMA_KEYWORDS = new Set([
  "$anchor",
  "$comment",
  "$defs",
  "$dynamicAnchor",
  "$dynamicRef",
  "$id",
  "$ref",
  "$schema",
  "$vocabulary",
  "additionalProperties",
  "contentEncoding",
  "contentMediaType",
  "contentSchema",
  "dependentRequired",
  "dependentSchemas",
  "exclusiveMaximum",
  "exclusiveMinimum",
  "maxContains",
  "maxItems",
  "maxLength",
  "maxProperties",
  "minContains",
  "minItems",
  "minLength",
  "minProperties",
  "multipleOf",
  "patternProperties",
  "prefixItems",
  "propertyNames",
  "unevaluatedItems",
  "unevaluatedProperties",
  "uniqueItems",
]);

type AssetRole = "concept" | "background" | "expression";
type ReviewStatus = "pending" | "pass" | "fail";
type RightsStatus = "unreviewed" | "restricted" | "redistribution-approved";
type DialogueBundleContract = DialogueSceneBundleV4;

interface BundleFileBinding {
  readonly path: string;
  readonly sha256: string;
  readonly provenance_path: string;
  readonly provenance_sha256: string;
}

interface BundleAsset {
  readonly id: string;
  readonly role: AssetRole;
  readonly state: DialogueSceneExpressionState | null;
  readonly path: string;
  readonly sha256: string;
  readonly bytes: number;
  readonly media: {
    readonly mime_type: "image/png";
    readonly width: number;
    readonly height: number;
    readonly alpha: boolean;
  };
  readonly provenance_path: string;
  readonly provenance_sha256: string;
  readonly selected_attempt: number;
}

interface StyleProvenanceBinding {
  readonly style_anchor_path: "style-anchor.json";
  readonly style_anchor_artifact_sha256: string;
  readonly style_anchor_provenance_path: "style-anchor.json.meta.json";
  readonly style_anchor_provenance_sha256: string;
  readonly style_anchor_sha256: string;
  readonly style_compiler_sha256: string;
  readonly style_compiler_version: number;
  readonly style_resource_sha256: string;
  readonly style_skill_sha256: string;
  readonly style_vocabulary_sha256: string;
}

interface StyleAnchorFacts {
  readonly style_mode:
    | "cel_shaded_anime_2d"
    | "photorealistic_natural"
    | "gouache_illustration_2d";
  readonly compiler_sha256: string;
  readonly compiler_version: number;
  readonly resource_sha256: string;
  readonly skill_sha256: string;
  readonly vocabulary_sha256: string;
  readonly canonical_sha256: string;
}

interface SceneData {
  readonly scene_id: string;
  readonly title: string;
  readonly scene_label: string;
  readonly concept_asset_id: string;
  readonly background: {
    readonly asset_id: string;
    readonly alt: string;
  };
  readonly appearance: {
    readonly id: string;
    readonly label: string;
    readonly age: number;
    readonly role: string;
    readonly tagline: string;
    readonly description: string;
    readonly visual_identity: string;
    readonly art_direction: string;
  };
  readonly placement: {
    readonly slot: "right";
    readonly framing_zoom: number;
    readonly source_framing_zoom: number;
  };
  readonly available_states: readonly DialogueSceneExpressionState[];
  readonly expression_variants: readonly {
    readonly id: string;
    readonly asset_id: string;
    readonly appearance_id: string;
    readonly state: DialogueSceneExpressionState;
    readonly label: string;
    readonly description: string;
    readonly alt: string;
    readonly slot: "right";
  }[];
  readonly dialogue: readonly {
    readonly id: string;
    readonly speaker: string;
    readonly text: string;
    readonly expression_state: DialogueSceneExpressionState;
  }[];
}

export interface DialogueSceneBundleV4 {
  readonly schema_version: 4;
  readonly kind: "dialogue-scene-bundle-v4";
  readonly recipe: "dialogue-scene";
  readonly recipe_version: "dialogue-scene-v5";
  readonly tag: string;
  readonly game_id: string;
  readonly run_identity_sha256: string;
  readonly request: BundleFileBinding;
  readonly plan: BundleFileBinding;
  readonly character_profile: BundleFileBinding;
  readonly character_profile_binding: {
    readonly schema_version: 1;
    readonly kind: "character-profile-binding-v1";
    readonly ref: string;
    readonly source_sha256: string;
  };
  readonly character_profile_sha256: string;
  /** The authored plate every image was drawn against, as the run republished it. */
  readonly identity_reference: BundleFileBinding;
  readonly identity_reference_source: string;
  readonly assets: readonly BundleAsset[];
  readonly scene_data: SceneData;
  readonly attempt_ledger: {
    readonly path: "attempts.json";
    readonly sha256: string;
  };
  readonly review: {
    readonly status: ReviewStatus;
    readonly path: string | null;
    readonly sha256: string | null;
    readonly provenance_path: string | null;
    readonly provenance_sha256: string | null;
  };
  readonly rights: {
    readonly aggregate: RightsStatus;
    readonly publication_authorized: boolean;
  };
}

interface ActiveBundleBinding {
  readonly bundle_id: string;
  readonly wire_schema_version: 4;
  readonly kind: "dialogue-scene-bundle-v4";
  readonly recipe_version: "dialogue-scene-v5";
  readonly source_bundle_sha256: string;
  readonly install_receipt_sha256: string;
}

export interface DialogueThemeActivePointer {
  readonly schema_version: 3;
  readonly kind: "dialogue-theme-active-v3";
  readonly adapter_version: 3;
  readonly active: ActiveBundleBinding;
  readonly previous: ActiveBundleBinding | null;
}

interface InstallCopy {
  readonly kind:
    | "request"
    | "request-provenance"
    | "plan"
    | "plan-provenance"
    | "bundle-provenance"
    | "style-anchor"
    | "style-anchor-provenance"
    | "character-profile"
    | "character-profile-provenance"
    | "attempt-ledger"
    | "review"
    | "review-provenance"
    | "review-source"
    | "asset"
    | "asset-provenance";
  readonly source_path: string;
  readonly installed_path: string;
  readonly sha256: string;
  readonly bytes: number;
}

interface InstallReceipt {
  readonly schema_version: 3;
  readonly kind: "dialogue-theme-install-v3";
  readonly adapter_version: 3;
  readonly bundle_id: string;
  readonly bundle_wire_schema_version: 3;
  readonly bundle_kind: "dialogue-scene-bundle-v4";
  readonly recipe_version: "dialogue-scene-v5";
  readonly source_bundle_sha256: string;
  readonly fixture_sha256: string;
  readonly character_profile_source_sha256: string;
  readonly character_profile_sha256: string;
  readonly profile_id: string;
  readonly profile_revision: number;
  readonly review_status: ReviewStatus;
  readonly rights_status: RightsStatus;
  readonly publication_authorized: boolean;
  readonly copies: readonly InstallCopy[];
}

export interface InstallDialogueThemeResult {
  readonly schema_version: 3;
  readonly kind: "dialogue-theme-install-result-v3";
  readonly adapter_version: 3;
  readonly bundle_id: string;
  readonly installed: boolean;
  readonly activation_eligible: boolean;
}

export interface DialogueThemeStatus {
  readonly schema_version: 3;
  readonly kind: "dialogue-theme-status-v3";
  readonly adapter_version: 3;
  readonly mode: "committed-fallback" | "installed-theme";
  readonly bundle_id: string | null;
  readonly previous_bundle_id: string | null;
  readonly installed_bundles: number;
  readonly activation_eligible: boolean | null;
}

export interface DialogueThemeAdapterOptions {
  readonly stateRoot: string;
  readonly publicRoot: string;
}

interface SourceCopy extends InstallCopy {
  readonly absoluteSourcePath: string;
}

interface ValidatedSourceBundle {
  readonly bundle: DialogueBundleContract;
  readonly sourceBundleBytes: Buffer;
  readonly source_bundle_sha256: string;
  readonly sourceCopies: readonly SourceCopy[];
  readonly roleAssets: {
    readonly concept: BundleAsset;
    readonly background: BundleAsset;
    readonly expressions: ReadonlyMap<
      DialogueSceneExpressionState,
      BundleAsset
    >;
  };
  readonly profile: { readonly profile_id: string; readonly revision: number };
}

interface ValidatedInstall {
  readonly receipt: InstallReceipt;
  readonly fixture: DialogueSceneDemoFixture;
  readonly directory: string;
  readonly bundle: DialogueBundleContract;
}

export function parseDialogueSceneBundleV4(
  value: unknown,
): DialogueSceneBundleV4 {
  const root = strictRecord(
    value,
    [
      "schema_version",
      "kind",
      "recipe",
      "recipe_version",
      "tag",
      "game_id",
      "run_identity_sha256",
      "request",
      "plan",
      "character_profile",
      "character_profile_binding",
      "character_profile_sha256",
      "identity_reference",
      "identity_reference_source",
      "assets",
      "scene_data",
      "attempt_ledger",
      "review",
      "rights",
    ],
    [],
    "dialogue-scene bundle v4",
  );
  exact(root.schema_version, 4, "bundle.schema_version");
  exact(root.kind, "dialogue-scene-bundle-v4", "bundle.kind");
  exact(root.recipe, "dialogue-scene", "bundle.recipe");
  exact(root.recipe_version, "dialogue-scene-v5", "bundle.recipe_version");
  const binding = strictRecord(
    root.character_profile_binding,
    ["schema_version", "kind", "ref", "source_sha256"],
    [],
    "bundle.character_profile_binding",
  );
  exact(binding.schema_version, 1, "character profile binding schema_version");
  exact(binding.kind, "character-profile-binding-v1", "character profile binding kind");
  const attempt = strictRecord(
    root.attempt_ledger,
    ["path", "sha256"],
    [],
    "bundle.attempt_ledger",
  );
  exact(attempt.path, "attempts.json", "bundle.attempt_ledger.path");
  const assets = parseAssets(root.assets);
  const scene_data = parseSceneData(root.scene_data);
  validateSceneAssetBindings(assets, scene_data);
  const review = parseReview(root.review);
  const rights = parseRights(root.rights);
  if (rights.publication_authorized && rights.aggregate !== "redistribution-approved") {
    throw new Error(
      "bundle.rights publication_authorized requires redistribution-approved rights",
    );
  }
  return Object.freeze({
    schema_version: 4,
    kind: "dialogue-scene-bundle-v4",
    recipe: "dialogue-scene",
    recipe_version: "dialogue-scene-v5",
    tag: strictText(root.tag, "bundle.tag", 160),
    game_id: snakeId(root.game_id, "bundle.game_id", 64),
    run_identity_sha256: digest(root.run_identity_sha256, "bundle.run_identity_sha256"),
    request: parseBundleFile(root.request, "bundle.request"),
    plan: parseBundleFile(root.plan, "bundle.plan"),
    character_profile: parseBundleFile(root.character_profile, "bundle.character_profile"),
    character_profile_binding: Object.freeze({
      schema_version: 1,
      kind: "character-profile-binding-v1",
      ref: portableProfileRef(binding.ref, "bundle.character_profile_binding.ref"),
      source_sha256: digest(
        binding.source_sha256,
        "bundle.character_profile_binding.source_sha256",
      ),
    }),
    character_profile_sha256: digest(
      root.character_profile_sha256,
      "bundle.character_profile_sha256",
    ),
    identity_reference: parseBundleFile(root.identity_reference, "bundle.identity_reference"),
    identity_reference_source: portableReuseRef(
      root.identity_reference_source,
      "bundle.identity_reference_source",
    ),
    assets: Object.freeze(assets),
    scene_data,
    attempt_ledger: Object.freeze({
      path: "attempts.json",
      sha256: digest(attempt.sha256, "bundle.attempt_ledger.sha256"),
    }),
    review,
    rights,
  });
}

function parseDialogueSceneBundle(value: unknown): DialogueBundleContract {
  return parseDialogueSceneBundleV4(value);
}

function validateSceneAssetBindings(
  assets: readonly BundleAsset[],
  sceneData: SceneData,
): void {
  const concept = assets.find((asset) => asset.id === sceneData.concept_asset_id);
  if (concept?.role !== "concept") {
    throw new Error("bundle.scene_data.concept_asset_id must reference the concept");
  }
  const background = assets.find((asset) => asset.id === sceneData.background.asset_id);
  if (background?.role !== "background") {
    throw new Error("bundle.scene_data.background.asset_id must reference the background");
  }
  for (const variant of sceneData.expression_variants) {
    const asset = assets.find((candidate) => candidate.id === variant.asset_id);
    if (asset?.role !== "expression" || asset.state !== variant.state) {
      throw new Error(
        `bundle.scene_data expression ${variant.state} must reference its expression asset`,
      );
    }
  }
}

export async function installDialogueTheme(
  bundlePath: string,
  options: DialogueThemeAdapterOptions,
): Promise<InstallDialogueThemeResult> {
  validateAdapterRootSeparation(options);
  return withAdapterLock(options.stateRoot, async () => {
    await prepareAdapterRoots(options);
    const validated = await validateSourceBundle(bundlePath);
    const bundleId = computeBundleId(
      validated.source_bundle_sha256,
      validated.sourceCopies,
    );
    const finalStateDirectory = path.join(options.stateRoot, bundleId);
    const finalPublicDirectory = path.join(options.publicRoot, bundleId);
    const existing = await pathKind(finalStateDirectory);
    if (existing !== "missing") {
      if (existing !== "directory") {
        throw new Error(
          `installed bundle path is not a directory: ${bundleId}`,
        );
      }
      const installed = await validateInstalledBundle(bundleId, options);
      if (
        installed.receipt.source_bundle_sha256 !==
        validated.source_bundle_sha256
      ) {
        throw new Error(`installed bundle identifier conflict: ${bundleId}`);
      }
      return Object.freeze({
        schema_version: 3,
        kind: "dialogue-theme-install-result-v3",
        adapter_version: 3,
        bundle_id: bundleId,
        installed: false,
        activation_eligible: isLocalActivationEligible(installed.receipt),
      });
    }

    const fixture = projectFixture(
      validated.bundle,
      validated.roleAssets,
      bundleId,
      validated.profile,
    );
    const fixtureBytes = canonicalJsonBytes(
      serializeDialogueSceneThemeFixture(fixture),
    );
    const stateStagingDirectory = path.join(
      options.stateRoot,
      `.staging-${process.pid}-${randomUUID()}`,
    );
    const publicStagingDirectory = path.join(
      options.publicRoot,
      `.staging-${process.pid}-${randomUUID()}`,
    );
    let publishedPublicProjection = false;
    try {
      await mkdir(stateStagingDirectory, { recursive: false });
      for (const copy of validated.sourceCopies) {
        const destination = path.join(
          stateStagingDirectory,
          ...copy.installed_path.split("/"),
        );
        await mkdir(path.dirname(destination), { recursive: true });
        await copyFile(copy.absoluteSourcePath, destination);
        await assertRegularNonSymlink(
          destination,
          `installed ${copy.installed_path}`,
        );
        const copiedBytes = await readFile(destination);
        if (
          copiedBytes.byteLength !== copy.bytes ||
          sha256(copiedBytes) !== copy.sha256
        ) {
          throw new Error(`copied bytes changed for ${copy.source_path}`);
        }
      }

      await writeNewFile(
        path.join(stateStagingDirectory, "source-bundle.json"),
        validated.sourceBundleBytes,
      );
      await writeNewFile(
        path.join(stateStagingDirectory, "fixture.json"),
        fixtureBytes,
      );
      const receiptCopies = Object.freeze(
        [...validated.sourceCopies]
          .map(({ absoluteSourcePath: _absoluteSourcePath, ...copy }) =>
            Object.freeze(copy),
          )
          .sort((left, right) =>
            left.installed_path.localeCompare(right.installed_path),
          ),
      );
      const receipt: InstallReceipt = Object.freeze({
        schema_version: 3,
        kind: "dialogue-theme-install-v3",
        adapter_version: 3,
        bundle_id: bundleId,
        bundle_wire_schema_version: 3,
        bundle_kind: "dialogue-scene-bundle-v4",
        recipe_version: "dialogue-scene-v5",
        character_profile_source_sha256:
          validated.bundle.character_profile_binding.source_sha256,
        character_profile_sha256: validated.bundle.character_profile_sha256,
        profile_id: validated.profile.profile_id,
        profile_revision: validated.profile.revision,
        source_bundle_sha256: validated.source_bundle_sha256,
        fixture_sha256: sha256(fixtureBytes),
        review_status: validated.bundle.review.status,
        rights_status: validated.bundle.rights.aggregate,
        publication_authorized: validated.bundle.rights.publication_authorized,
        copies: receiptCopies,
      });
      await writeNewFile(
        path.join(stateStagingDirectory, "install-receipt.json"),
        canonicalJsonBytes(receipt),
      );
      await validateInstalledDirectory(stateStagingDirectory, bundleId);

      await stagePublicProjection(publicStagingDirectory, validated);
      const existingPublic = await pathKind(finalPublicDirectory);
      if (existingPublic === "missing") {
        await rename(publicStagingDirectory, finalPublicDirectory);
        publishedPublicProjection = true;
      } else {
        if (existingPublic !== "directory") {
          throw new Error(`public bundle path is not a directory: ${bundleId}`);
        }
        await validatePublicProjection(finalPublicDirectory, validated.bundle);
        await rm(publicStagingDirectory, { recursive: true, force: true });
      }
      await rename(stateStagingDirectory, finalStateDirectory);
    } catch (error) {
      await rm(stateStagingDirectory, { recursive: true, force: true });
      await rm(publicStagingDirectory, { recursive: true, force: true });
      if (publishedPublicProjection) {
        await rm(finalPublicDirectory, { recursive: true, force: true });
      }
      throw error;
    }

    const installed = await validateInstalledBundle(bundleId, options);
    return Object.freeze({
      schema_version: 3,
      kind: "dialogue-theme-install-result-v3",
      adapter_version: 3,
      bundle_id: bundleId,
      installed: true,
      activation_eligible: isLocalActivationEligible(installed.receipt),
    });
  });
}

export async function activateDialogueTheme(
  bundleId: string,
  options: DialogueThemeAdapterOptions,
): Promise<DialogueThemeActivePointer> {
  validateAdapterRootSeparation(options);
  return withAdapterLock(options.stateRoot, async () => {
    digest(bundleId, "bundle id");
    const installed = await validateInstalledBundle(bundleId, options);
    if (!isLocalActivationEligible(installed.receipt)) {
      throw new Error(
        "dialogue theme local activation requires review pass, restricted local-only rights, and publication_authorized=false",
      );
    }
    const current = await readActivePointer(options.stateRoot, true, options);
    const target = await installedActiveBinding(installed);
    const pointer: DialogueThemeActivePointer = Object.freeze({
      schema_version: 3,
      kind: "dialogue-theme-active-v3",
      adapter_version: 3,
      active: target,
      previous:
        current?.active.bundle_id === bundleId
          ? current.previous
          : (current?.active ?? null),
    });
    await writeActivePointer(options.stateRoot, pointer);
    return pointer;
  });
}

export async function rollbackDialogueTheme(
  options: DialogueThemeAdapterOptions,
): Promise<DialogueThemeActivePointer> {
  validateAdapterRootSeparation(options);
  return withAdapterLock(options.stateRoot, async () => {
    const current = await readActivePointer(options.stateRoot, false, options);
    if (current === null || current.previous === null) {
      throw new Error(
        "dialogue theme has no previous installed bundle to restore",
      );
    }
    const previous = await validateInstalledBundle(
      current.previous.bundle_id,
      options,
    );
    if (!isLocalActivationEligible(previous.receipt)) {
      throw new Error(
        "previous dialogue theme is no longer local-activation eligible",
      );
    }
    const pointer: DialogueThemeActivePointer = Object.freeze({
      schema_version: 3,
      kind: "dialogue-theme-active-v3",
      adapter_version: 3,
      active: await installedActiveBinding(previous),
      previous: current.active,
    });
    await writeActivePointer(options.stateRoot, pointer);
    return pointer;
  });
}

export async function dialogueThemeStatus(
  options: DialogueThemeAdapterOptions,
): Promise<DialogueThemeStatus> {
  validateAdapterRootSeparation(options);
  const installedBundles = await countInstalledBundles(options.stateRoot);
  const active = await readActivePointer(options.stateRoot, true, options);
  if (active === null) {
    return Object.freeze({
      schema_version: 3,
      kind: "dialogue-theme-status-v3",
      adapter_version: 3,
      mode: "committed-fallback",
      bundle_id: null,
      previous_bundle_id: null,
      installed_bundles: installedBundles,
      activation_eligible: null,
    });
  }
  const activeBundleId = active.active.bundle_id;
  const previousBundleId = active.previous?.bundle_id ?? null;
  const installed = await validateInstalledBundle(activeBundleId, options);
  return Object.freeze({
    schema_version: 3,
    kind: "dialogue-theme-status-v3",
    adapter_version: 3,
    mode: "installed-theme",
    bundle_id: activeBundleId,
    previous_bundle_id: previousBundleId,
    installed_bundles: installedBundles,
    activation_eligible: isLocalActivationEligible(installed.receipt),
  });
}

export async function loadActiveDialogueThemeFixture(
  options: DialogueThemeAdapterOptions,
): Promise<DialogueSceneDemoFixture | null> {
  validateAdapterRootSeparation(options);
  const active = await readActivePointer(options.stateRoot, true, options);
  if (active === null) return null;
  const binding = active.active;
  const installed = await validateInstalledBundle(binding.bundle_id, options);
  if (installed.receipt.source_bundle_sha256 !== binding.source_bundle_sha256) {
    throw new Error(
      "active dialogue theme source bundle digest does not match receipt",
    );
  }
  if (!isLocalActivationEligible(installed.receipt)) {
    throw new Error(
      "active dialogue theme is no longer local-activation eligible",
    );
  }
  return installed.fixture;
}

async function validateSourceBundle(
  bundlePath: string,
): Promise<ValidatedSourceBundle> {
  await assertRegularNonSymlink(bundlePath, "bundle");
  const sourceBundleBytes = await readBoundedFile(
    bundlePath,
    MAX_JSON_BYTES,
    "bundle",
  );
  const bundle = parseDialogueSceneBundle(parseJson(sourceBundleBytes, "bundle"));
  const sourceRoot = path.dirname(path.resolve(bundlePath));
  await assertDirectoryNonSymlink(sourceRoot, "bundle source root");
  const sourceCopies: SourceCopy[] = [];
  const seenSourcePaths = new Set<string>();

  const addJsonBinding = async (
    kind: "request" | "plan" | "character-profile",
    binding: BundleFileBinding,
  ): Promise<void> => {
    await addSourceCopy(
      sourceCopies,
      seenSourcePaths,
      sourceRoot,
      kind,
      binding.path,
      binding.sha256,
      `records/${binding.sha256}.json`,
      MAX_JSON_BYTES,
      true,
    );
    await addSourceCopy(
      sourceCopies,
      seenSourcePaths,
      sourceRoot,
      `${kind}-provenance`,
      binding.provenance_path,
      binding.provenance_sha256,
      `provenance/${binding.provenance_sha256}.json`,
      MAX_JSON_BYTES,
      true,
    );
    const provenanceCopy = sourceCopies.at(-1);
    if (provenanceCopy?.kind !== `${kind}-provenance`) {
      throw new Error(`${kind} provenance copy is missing`);
    }
    validateProvenanceBinding(
      parseJson(
        await readFile(provenanceCopy.absoluteSourcePath),
        `${kind} provenance`,
      ),
      binding.sha256,
      `${kind} provenance`,
    );
  };

  await addJsonBinding("request", bundle.request);
  await addJsonBinding("plan", bundle.plan);
  const requestCopy = sourceCopies.find((copy) => copy.kind === "request");
  const planCopy = sourceCopies.find((copy) => copy.kind === "plan");
  const planProvenanceCopy = sourceCopies.find(
    (copy) => copy.kind === "plan-provenance",
  );
  if (
    requestCopy === undefined ||
    planCopy === undefined ||
    planProvenanceCopy === undefined
  ) {
    throw new Error("request, plan, or plan provenance copy is missing");
  }
  validateRequestEnvelope(
    parseJson(await readFile(requestCopy.absoluteSourcePath), "bundle request"),
    bundle,
  );
  validatePlanEnvelope(
    parseJson(await readFile(planCopy.absoluteSourcePath), "bundle plan"),
    bundle,
  );
  const planProvenance = parseJson(
    await readFile(planProvenanceCopy.absoluteSourcePath),
    "plan provenance",
  );
  await addSourceCopy(
    sourceCopies,
    seenSourcePaths,
    sourceRoot,
    "attempt-ledger",
    bundle.attempt_ledger.path,
    bundle.attempt_ledger.sha256,
    `records/${bundle.attempt_ledger.sha256}.json`,
    MAX_JSON_BYTES,
    true,
  );

  const attemptsBytes = sourceCopies.find(
    (copy) => copy.kind === "attempt-ledger",
  );
  if (attemptsBytes === undefined)
    throw new Error("attempt ledger copy is missing");
  const ledger = parseAttemptLedger(
    parseJson(
      await readFile(attemptsBytes.absoluteSourcePath),
      "bundle attempt ledger",
    ),
  );

  const roleAssets = requireRoleAssets(bundle.assets);
  for (const asset of bundle.assets) {
    const source = await readPortableSource(
      sourceRoot,
      asset.path,
      MAX_PNG_BYTES,
      `asset ${asset.id}`,
    );
    if (source.bytes.byteLength !== asset.bytes) {
      throw new Error(`asset ${asset.id} byte count does not match bundle`);
    }
    if (sha256(source.bytes) !== asset.sha256) {
      throw new Error(`asset ${asset.id} digest does not match bundle`);
    }
    validateAssetPng(asset, source.bytes);
    await addComputedSourceCopy(
      sourceCopies,
      seenSourcePaths,
      "asset",
      asset.path,
      source,
      `assets/${asset.sha256}.png`,
      asset.sha256,
    );

    await addSourceCopy(
      sourceCopies,
      seenSourcePaths,
      sourceRoot,
      "asset-provenance",
      asset.provenance_path,
      asset.provenance_sha256,
      `provenance/${asset.provenance_sha256}.json`,
      MAX_JSON_BYTES,
      true,
    );
    const provenanceCopy = sourceCopies.at(-1);
    if (provenanceCopy?.kind !== "asset-provenance") {
      throw new Error(`asset ${asset.id} provenance copy is missing`);
    }
    validateProvenanceBinding(
      parseJson(
        await readFile(provenanceCopy.absoluteSourcePath),
        `asset ${asset.id} provenance`,
      ),
      asset.sha256,
      `asset ${asset.id} provenance`,
    );
    if (
      asset.selected_attempt > 0 &&
      !ledgerHasSelectedAttempt(ledger, asset)
    ) {
      throw new Error(
        `asset ${asset.id} selected_attempt is not bound by attempts.json`,
      );
    }
  }

  await addJsonBinding("character-profile", bundle.character_profile);
  const profileCopy = sourceCopies.find((copy) => copy.kind === "character-profile");
  if (profileCopy === undefined) throw new Error("character profile copy is missing");
  const profileBytes = await readFile(profileCopy.absoluteSourcePath);
  if (bundle.character_profile.sha256 !== bundle.character_profile_sha256) {
    throw new Error("bundle character profile artifact and canonical digests must match");
  }
  const profile = parseCanonicalCharacterProfile(profileBytes, bundle);
  const profileProvenance = sourceCopies.find(
    (copy) => copy.kind === "character-profile-provenance",
  );
  if (profileProvenance === undefined) {
    throw new Error("character profile provenance copy is missing");
  }
  validateProvenanceBinding(
    parseJson(
      await readFile(profileProvenance.absoluteSourcePath),
      "character profile provenance",
    ),
    bundle.character_profile_sha256,
    "character profile provenance",
  );

  let pendingBundleSha256 = sha256(sourceBundleBytes);
  if (bundle.review.status === "pending") {
    if (
      bundle.review.path !== null ||
      bundle.review.sha256 !== null ||
      bundle.review.provenance_path !== null ||
      bundle.review.provenance_sha256 !== null
    ) {
      throw new Error("pending review must not reference a review record");
    }
  } else {
    if (
      bundle.review.path === null ||
      bundle.review.sha256 === null ||
      bundle.review.provenance_path === null ||
      bundle.review.provenance_sha256 === null
    ) {
      throw new Error(
        `${bundle.review.status} review must reference a digest-bound record`,
      );
    }
    await addSourceCopy(
      sourceCopies,
      seenSourcePaths,
      sourceRoot,
      "review",
      bundle.review.path,
      bundle.review.sha256,
      `records/${bundle.review.sha256}.json`,
      MAX_JSON_BYTES,
      true,
    );
    const reviewCopy = sourceCopies.find((copy) => copy.kind === "review");
    if (reviewCopy === undefined) throw new Error("review copy is missing");
    await addSourceCopy(
      sourceCopies,
      seenSourcePaths,
      sourceRoot,
      "review-provenance",
      bundle.review.provenance_path,
      bundle.review.provenance_sha256,
      `provenance/${bundle.review.provenance_sha256}.json`,
      MAX_JSON_BYTES,
      true,
    );
    const reviewProvenanceCopy = sourceCopies.find(
      (copy) => copy.kind === "review-provenance",
    );
    if (reviewProvenanceCopy === undefined) {
      throw new Error("review provenance copy is missing");
    }
    const reviewProvenanceValue = parseJson(
      await readFile(reviewProvenanceCopy.absoluteSourcePath),
      "review provenance",
    );
    validateProvenanceBinding(
      reviewProvenanceValue,
      bundle.review.sha256,
      "review provenance",
    );
    const reviewedSourceSha256 = validateReviewProof(
      parseJson(await readFile(reviewCopy.absoluteSourcePath), "review record"),
      bundle.review.status,
      bundle,
    );
    pendingBundleSha256 = reviewedSourceSha256;
    validateV4ReviewProvenance(reviewProvenanceValue, bundle, reviewedSourceSha256);
    await addSourceCopy(
      sourceCopies,
      seenSourcePaths,
      sourceRoot,
      "review-source",
      "bundle.json",
      reviewedSourceSha256,
      `records/${reviewedSourceSha256}.json`,
      MAX_JSON_BYTES,
      true,
    );
    const reviewSourceCopy = sourceCopies.find(
      (copy) => copy.kind === "review-source",
    );
    if (reviewSourceCopy === undefined)
      throw new Error("review source copy is missing");
    validateReviewedTransition(
      parseDialogueSceneBundle(
        parseJson(
          await readFile(reviewSourceCopy.absoluteSourcePath),
          "review source bundle",
        ),
      ),
      bundle,
    );
  }

  await validateV3StyleContract({
    bundle,
    sourceRoot,
    sourceCopies,
    seenSourcePaths,
    planProvenance,
    pendingBundleSha256,
  });

  return Object.freeze({
    bundle,
    sourceBundleBytes,
    source_bundle_sha256: sha256(sourceBundleBytes),
    sourceCopies: Object.freeze(sourceCopies),
    roleAssets,
    profile,
  });
}

function projectFixture(
  bundle: DialogueBundleContract,
  roleAssets: ValidatedSourceBundle["roleAssets"],
  bundleId: string,
  profile: ValidatedSourceBundle["profile"],
): DialogueSceneDemoFixture {
  const assetUrl = (asset: BundleAsset): string =>
    `/dialogue-scene/themes/${bundleId}/assets/${asset.sha256}.png`;
  const variants = new Map(
    bundle.scene_data.expression_variants.map((entry) => [entry.state, entry]),
  );
  return validateDialogueSceneRuntimeFixture({
    schemaVersion: DIALOGUE_SCENE_DEMO_SCHEMA_VERSION,
    fixtureId: bundle.scene_data.scene_id,
    mode: DIALOGUE_SCENE_DEMO_MODE,
    authorship: DIALOGUE_SCENE_DEMO_AUTHORSHIP,
    title: bundle.scene_data.title,
    sceneLabel: bundle.scene_data.scene_label,
    presentation: {
      framingZoom: bundle.scene_data.placement.framing_zoom,
      sourceFramingZoom: bundle.scene_data.placement.source_framing_zoom,
    },
    background: {
      id: bundle.scene_data.background.asset_id,
      src: assetUrl(roleAssets.background),
      alt: bundle.scene_data.background.alt,
    },
    appearance: {
      id: bundle.scene_data.appearance.id,
      label: bundle.scene_data.appearance.label,
      age: bundle.scene_data.appearance.age,
      role: bundle.scene_data.appearance.role,
      tagline: bundle.scene_data.appearance.tagline,
      description: bundle.scene_data.appearance.description,
      visualIdentity: bundle.scene_data.appearance.visual_identity,
      artDirection: bundle.scene_data.appearance.art_direction,
      conceptSrc: assetUrl(roleAssets.concept),
    },
    expressionVariants: DIALOGUE_SCENE_EXPRESSION_STATES.map((state) => {
      const asset = roleAssets.expressions.get(state);
      const copy = variants.get(state);
      if (asset === undefined || copy === undefined) {
        throw new Error(`cannot project missing expression state: ${state}`);
      }
      return {
        id: copy.id,
        src: assetUrl(asset),
        alt: copy.alt,
        appearanceId: bundle.scene_data.appearance.id,
        state,
        label: copy.label,
        description: copy.description,
        slot: "right",
      };
    }),
    dialogue: bundle.scene_data.dialogue.map((beat) => ({
      id: beat.id,
      speaker: beat.speaker,
      text: beat.text,
      expressionState: beat.expression_state,
    })),
    profileIdentity: {
      profileId: profile.profile_id,
      revision: profile.revision,
    },
  });
}

async function validateInstalledBundle(
  bundleId: string,
  options: DialogueThemeAdapterOptions,
): Promise<ValidatedInstall> {
  digest(bundleId, "bundle id");
  await assertDirectoryNonSymlink(options.stateRoot, "dialogue theme state root");
  await assertDirectoryNonSymlink(options.publicRoot, "dialogue theme public root");
  validateResolvedRootSeparation(
    await realpath(options.stateRoot),
    await realpath(options.publicRoot),
  );
  const installed = await validateInstalledDirectory(
    path.join(options.stateRoot, bundleId),
    bundleId,
  );
  await validatePublicProjection(
    path.join(options.publicRoot, bundleId),
    installed.bundle,
  );
  return installed;
}

async function validateInstalledDirectory(
  directory: string,
  expectedBundleId: string,
): Promise<ValidatedInstall> {
  await assertDirectoryNonSymlink(directory, "installed bundle directory");
  const receiptPath = path.join(directory, "install-receipt.json");
  const receiptBytes = await readBoundedFile(
    receiptPath,
    MAX_JSON_BYTES,
    "install receipt",
  );
  const receipt = parseInstallReceipt(
    parseJson(receiptBytes, "install receipt"),
  );
  if (receipt.bundle_id !== expectedBundleId) {
    throw new Error("installed receipt bundle_id does not match its directory");
  }
  const recomputedBundleId = computeBundleId(
    receipt.source_bundle_sha256,
    receipt.copies,
  );
  if (recomputedBundleId !== expectedBundleId) {
    throw new Error("installed receipt does not reproduce its bundle_id");
  }

  const sourceBundleBytes = await readBoundedFile(
    path.join(directory, "source-bundle.json"),
    MAX_JSON_BYTES,
    "installed source bundle",
  );
  if (sha256(sourceBundleBytes) !== receipt.source_bundle_sha256) {
    throw new Error("installed source bundle digest does not match receipt");
  }
  const sourceBundle = parseDialogueSceneBundle(
    parseJson(sourceBundleBytes, "installed source bundle"),
  );
  validateInstalledCopyContract(sourceBundle, receipt.copies);
  if (
    receipt.character_profile_source_sha256 !==
      sourceBundle.character_profile_binding.source_sha256 ||
    receipt.character_profile_sha256 !== sourceBundle.character_profile_sha256 ||
    receipt.profile_id !== sourceBundle.scene_data.appearance.id
  ) {
    throw new Error("install receipt character profile binding does not match source bundle");
  }
  if (
    receipt.review_status !== sourceBundle.review.status ||
    receipt.rights_status !== sourceBundle.rights.aggregate ||
    receipt.publication_authorized !==
      sourceBundle.rights.publication_authorized
  ) {
    throw new Error(
      "install receipt review or rights state does not match source bundle",
    );
  }

  for (const copy of receipt.copies) {
    const installed = await readInstalledFile(
      directory,
      copy.installed_path,
      copy.bytes,
    );
    if (sha256(installed) !== copy.sha256) {
      throw new Error(`installed copy digest changed: ${copy.installed_path}`);
    }
  }
  const profileCopy = receipt.copies.find((copy) => copy.kind === "character-profile");
  if (profileCopy === undefined) throw new Error("installed character profile copy is missing");
  const profileBytes = await readInstalledFile(
    directory,
    profileCopy.installed_path,
    profileCopy.bytes,
  );
  const profile = parseCanonicalCharacterProfile(profileBytes, sourceBundle);
  if (
    profile.profile_id !== receipt.profile_id ||
    profile.revision !== receipt.profile_revision
  ) {
    throw new Error("installed character profile identity does not match receipt");
  }

  const fixtureBytes = await readBoundedFile(
    path.join(directory, "fixture.json"),
    MAX_JSON_BYTES,
    "installed fixture",
  );
  if (sha256(fixtureBytes) !== receipt.fixture_sha256) {
    throw new Error("installed fixture digest does not match receipt");
  }
  const expectedFixtureBytes = canonicalJsonBytes(
    serializeDialogueSceneThemeFixture(
      projectFixture(
        sourceBundle,
        requireRoleAssets(sourceBundle.assets),
        expectedBundleId,
        {
          profile_id: receipt.profile_id,
          revision: receipt.profile_revision,
        },
      ),
    ),
  );
  if (!fixtureBytes.equals(expectedFixtureBytes)) {
    throw new Error(
      "installed fixture is not the deterministic source bundle projection",
    );
  }
  const fixture = parseDialogueSceneThemeFixture(
    parseJson(fixtureBytes, "installed fixture"),
  );
  return Object.freeze({ receipt, fixture, directory, bundle: sourceBundle });
}

function validateAdapterRootSeparation(
  options: DialogueThemeAdapterOptions,
): void {
  validateResolvedRootSeparation(
    path.resolve(options.stateRoot),
    path.resolve(options.publicRoot),
  );
}

function validateResolvedRootSeparation(
  stateRoot: string,
  publicRoot: string,
): void {
  const contains = (parent: string, child: string): boolean => {
    const relative = path.relative(parent, child);
    return (
      relative === "" ||
      (!relative.startsWith("..") && !path.isAbsolute(relative))
    );
  };
  if (contains(stateRoot, publicRoot) || contains(publicRoot, stateRoot)) {
    throw new Error(
      "dialogue theme state_root and public_root must be separate non-overlapping directories",
    );
  }
}

async function prepareAdapterRoots(
  options: DialogueThemeAdapterOptions,
): Promise<void> {
  validateAdapterRootSeparation(options);
  await mkdir(options.publicRoot, { recursive: true });
  await assertDirectoryNonSymlink(options.stateRoot, "dialogue theme state root");
  await assertDirectoryNonSymlink(options.publicRoot, "dialogue theme public root");
  validateResolvedRootSeparation(
    await realpath(options.stateRoot),
    await realpath(options.publicRoot),
  );
}

async function stagePublicProjection(
  directory: string,
  validated: ValidatedSourceBundle,
): Promise<void> {
  await mkdir(directory, { recursive: false });
  await mkdir(path.join(directory, "assets"), { recursive: false });
  for (const asset of validated.bundle.assets) {
    const source = validated.sourceCopies.find(
      (copy) =>
        copy.kind === "asset" &&
        copy.source_path === asset.path &&
        copy.sha256 === asset.sha256,
    );
    if (source === undefined) {
      throw new Error(`public projection source is missing for asset ${asset.id}`);
    }
    const destination = path.join(directory, "assets", `${asset.sha256}.png`);
    await copyFile(source.absoluteSourcePath, destination);
    await assertRegularNonSymlink(destination, `public asset ${asset.id}`);
    const bytes = await readBoundedFile(
      destination,
      MAX_PNG_BYTES,
      `public asset ${asset.id}`,
    );
    if (bytes.byteLength !== asset.bytes || sha256(bytes) !== asset.sha256) {
      throw new Error(`public projection changed asset ${asset.id}`);
    }
    validateAssetPng(asset, bytes);
  }
  await validatePublicProjection(directory, validated.bundle);
}

async function validatePublicProjection(
  directory: string,
  bundle: DialogueBundleContract,
): Promise<void> {
  await assertDirectoryNonSymlink(directory, "public bundle directory");
  const rootEntries = await readdir(directory, { withFileTypes: true });
  if (
    rootEntries.length !== 1 ||
    rootEntries[0].name !== "assets" ||
    !rootEntries[0].isDirectory() ||
    rootEntries[0].isSymbolicLink()
  ) {
    throw new Error("public bundle directory must contain only the assets directory");
  }
  const assetsDirectory = path.join(directory, "assets");
  await assertDirectoryNonSymlink(assetsDirectory, "public assets directory");
  const expectedNames = bundle.assets.map((asset) => `${asset.sha256}.png`);
  if (new Set(expectedNames).size !== bundle.assets.length) {
    throw new Error("public bundle assets must have distinct content digests");
  }
  const assetEntries = await readdir(assetsDirectory, { withFileTypes: true });
  const actualNames = assetEntries.map((entry) => entry.name).sort();
  if (
    assetEntries.some(
      (entry) => !entry.isFile() || entry.isSymbolicLink(),
    ) ||
    JSON.stringify(actualNames) !== JSON.stringify([...expectedNames].sort())
  ) {
    throw new Error("public assets directory must contain only selected PNG assets");
  }
  for (const asset of bundle.assets) {
    const source = await readPortableSource(
      directory,
      `assets/${asset.sha256}.png`,
      MAX_PNG_BYTES,
      `public asset ${asset.id}`,
    );
    if (source.bytes.byteLength !== asset.bytes || sha256(source.bytes) !== asset.sha256) {
      throw new Error(`public asset ${asset.id} does not match its bundle binding`);
    }
    validateAssetPng(asset, source.bytes);
  }
}

function validateInstalledCopyContract(
  bundle: DialogueBundleContract,
  copies: readonly InstallCopy[],
): void {
  const requiredKinds: readonly InstallCopy["kind"][] = [
    "bundle-provenance",
    "style-anchor",
    "style-anchor-provenance",
    "character-profile",
    "character-profile-provenance",
  ];
  for (const kind of requiredKinds) {
    const count = copies.filter((copy) => copy.kind === kind).length;
    if (count !== 1) {
      throw new Error(`installed current bundle must contain exactly one ${kind} copy`);
    }
  }
}

async function installedActiveBinding(
  installed: ValidatedInstall,
): Promise<ActiveBundleBinding> {
  const receiptBytes = await readBoundedFile(
    path.join(installed.directory, "install-receipt.json"),
    MAX_JSON_BYTES,
    "installed receipt",
  );
  const sourceBytes = await readBoundedFile(
    path.join(installed.directory, "source-bundle.json"),
    MAX_JSON_BYTES,
    "installed source bundle",
  );
  const bundle = parseDialogueSceneBundle(parseJson(sourceBytes, "installed source bundle"));
  return Object.freeze({
    bundle_id: installed.receipt.bundle_id,
    wire_schema_version: bundle.schema_version,
    kind: bundle.kind,
    recipe_version: bundle.recipe_version,
    source_bundle_sha256: installed.receipt.source_bundle_sha256,
    install_receipt_sha256: sha256(receiptBytes),
  });
}

function parseActivePointer(value: unknown): DialogueThemeActivePointer {
  const root = strictRecord(
    value,
    ["schema_version", "kind", "adapter_version", "active", "previous"],
    [],
    "active pointer",
  );
  exact(root.schema_version, 3, "active pointer schema_version");
  exact(root.kind, "dialogue-theme-active-v3", "active pointer kind");
  exact(root.adapter_version, 3, "active pointer adapter_version");
  return Object.freeze({
    schema_version: 3,
    kind: "dialogue-theme-active-v3",
    adapter_version: 3,
    active: parseActiveBundleBinding(root.active, "active pointer active"),
    previous:
      root.previous === null
        ? null
        : parseActiveBundleBinding(root.previous, "active pointer previous"),
  });
}

function parseActiveBundleBinding(
  value: unknown,
  label: string,
): ActiveBundleBinding {
  const root = strictRecord(
    value,
    [
      "bundle_id",
      "wire_schema_version",
      "kind",
      "recipe_version",
      "source_bundle_sha256",
      "install_receipt_sha256",
    ],
    [],
    label,
  );
  exact(root.wire_schema_version, 4, `${label} wire_schema_version`);
  exact(root.kind, "dialogue-scene-bundle-v4", `${label} kind`);
  exact(root.recipe_version, "dialogue-scene-v5", `${label} recipe_version`);
  return Object.freeze({
    bundle_id: digest(root.bundle_id, `${label} bundle_id`),
    wire_schema_version: 4,
    kind: "dialogue-scene-bundle-v4",
    recipe_version: "dialogue-scene-v5",
    source_bundle_sha256: digest(
      root.source_bundle_sha256,
      `${label} source_bundle_sha256`,
    ),
    install_receipt_sha256: digest(
      root.install_receipt_sha256,
      `${label} install_receipt_sha256`,
    ),
  });
}

async function writeAtomicJson(filePath: string, bytes: Buffer): Promise<void> {
  const temporaryPath = `${filePath}.${process.pid}.${randomUUID()}.tmp`;
  try {
    await writeNewFile(temporaryPath, bytes);
    await rename(temporaryPath, filePath);
  } catch (error) {
    await unlink(temporaryPath).catch(() => undefined);
    throw error;
  }
}

async function writeActivePointer(
  stateRoot: string,
  pointer: DialogueThemeActivePointer,
): Promise<void> {
  await mkdir(stateRoot, { recursive: true });
  await assertDirectoryNonSymlink(stateRoot, "dialogue theme state root");
  await writeAtomicJson(
    path.join(stateRoot, "active.json"),
    canonicalJsonBytes(pointer),
  );
}

async function readActivePointer(
  stateRoot: string,
  allowMissing: boolean,
  options: DialogueThemeAdapterOptions,
): Promise<DialogueThemeActivePointer | null> {
  const stateRootKind = await pathKind(stateRoot);
  if (stateRootKind === "missing" && allowMissing) return null;
  if (stateRootKind !== "directory") {
    throw new Error("dialogue theme state root must be a non-symlink directory");
  }
  await assertDirectoryNonSymlink(stateRoot, "dialogue theme state root");
  const activePath = path.join(stateRoot, "active.json");
  let bytes: Buffer;
  try {
    await assertRegularNonSymlink(activePath, "active pointer");
    bytes = await readBoundedFile(activePath, MAX_JSON_BYTES, "active pointer");
  } catch (error) {
    if (allowMissing && isMissingError(error)) return null;
    throw error;
  }
  const pointer = parseActivePointer(parseJson(bytes, "active pointer"));
  for (const binding of [pointer.active, pointer.previous].filter(
    (entry): entry is ActiveBundleBinding => entry !== null,
  )) {
    const installed = await validateInstalledBundle(binding.bundle_id, options);
    const actual = await installedActiveBinding(installed);
    if (!canonicalJsonBytes(actual).equals(canonicalJsonBytes(binding))) {
      throw new Error("active bundle binding does not match immutable install");
    }
  }
  return pointer;
}
async function withAdapterLock<T>(
  stateRoot: string,
  task: () => Promise<T>,
): Promise<T> {
  await mkdir(stateRoot, { recursive: true });
  await assertDirectoryNonSymlink(stateRoot, "dialogue theme state root");
  const lockPath = path.join(stateRoot, ".adapter.lock");
  let handle;
  try {
    handle = await open(lockPath, "wx", 0o600);
  } catch (error) {
    if (isAlreadyExistsError(error)) {
      throw new Error(
        "another dialogue theme adapter operation is in progress",
      );
    }
    throw error;
  }
  try {
    await handle.writeFile(`${process.pid}\n`);
    await handle.sync();
    return await task();
  } finally {
    await handle.close();
    await unlink(lockPath).catch(() => undefined);
  }
}

function parseBundleFile(value: unknown, label: string): BundleFileBinding {
  const record = strictRecord(
    value,
    ["path", "sha256", "provenance_path", "provenance_sha256"],
    [],
    label,
  );
  return Object.freeze({
    path: portablePath(record.path, `${label}.path`),
    sha256: digest(record.sha256, `${label}.sha256`),
    provenance_path: portablePath(
      record.provenance_path,
      `${label}.provenance_path`,
    ),
    provenance_sha256: digest(
      record.provenance_sha256,
      `${label}.provenance_sha256`,
    ),
  });
}

function parseAssets(value: unknown): BundleAsset[] {
  if (!Array.isArray(value) || value.length !== 6) {
    throw new Error(
      "bundle.assets must contain concept, background, and four expressions",
    );
  }
  const ids = new Set<string>();
  const paths = new Set<string>();
  const assets = value.map((entry, index) => {
    const record = strictRecord(
      entry,
      [
        "id",
        "role",
        "path",
        "sha256",
        "bytes",
        "media",
        "provenance_path",
        "provenance_sha256",
        "selected_attempt",
      ],
      ["state"],
      `bundle.assets[${index}]`,
    );
    const id = stableId(record.id, `bundle.assets[${index}].id`);
    if (ids.has(id)) throw new Error(`bundle asset id is duplicated: ${id}`);
    ids.add(id);
    const role = enumValue(
      record.role,
      ["concept", "background", "expression"] as const,
      `bundle.assets[${index}].role`,
    );
    const state =
      record.state === undefined || record.state === null
        ? null
        : expressionState(record.state, `bundle.assets[${index}].state`);
    if ((role === "expression") !== (state !== null)) {
      throw new Error(
        `bundle asset ${id} state is valid only for expression role`,
      );
    }
    const portable = portablePath(record.path, `bundle.assets[${index}].path`);
    if (paths.has(portable))
      throw new Error(`bundle asset path is duplicated: ${portable}`);
    paths.add(portable);
    const assetDigest = digest(record.sha256, `bundle.assets[${index}].sha256`);
    const media = strictRecord(
      record.media,
      ["mime_type", "width", "height", "alpha"],
      [],
      `bundle.assets[${index}].media`,
    );
    exact(
      media.mime_type,
      "image/png",
      `bundle.assets[${index}].media.mime_type`,
    );
    return Object.freeze({
      id,
      role,
      state,
      path: portable,
      sha256: assetDigest,
      bytes: strictInteger(
        record.bytes,
        `bundle.assets[${index}].bytes`,
        1,
        MAX_PNG_BYTES,
      ),
      media: Object.freeze({
        mime_type: "image/png" as const,
        width: strictInteger(
          media.width,
          `bundle.assets[${index}].media.width`,
          1,
          8192,
        ),
        height: strictInteger(
          media.height,
          `bundle.assets[${index}].media.height`,
          1,
          8192,
        ),
        alpha: strictBoolean(
          media.alpha,
          `bundle.assets[${index}].media.alpha`,
        ),
      }),
      provenance_path: portablePath(
        record.provenance_path,
        `bundle.assets[${index}].provenance_path`,
      ),
      provenance_sha256: digest(
        record.provenance_sha256,
        `bundle.assets[${index}].provenance_sha256`,
      ),
      selected_attempt: strictInteger(
        record.selected_attempt,
        `bundle.assets[${index}].selected_attempt`,
        0,
        6,
      ),
    });
  });
  requireRoleAssets(assets);
  return assets;
}

function parseSceneData(value: unknown): SceneData {
  const root = strictRecord(
    value,
    [
      "scene_id",
      "title",
      "scene_label",
      "concept_asset_id",
      "background",
      "appearance",
      "placement",
      "available_states",
      "expression_variants",
      "dialogue",
    ],
    [],
    "bundle.scene_data",
  );
  const appearance = strictRecord(
    root.appearance,
    [
      "id",
      "label",
      "age",
      "role",
      "tagline",
      "description",
      "visual_identity",
      "art_direction",
    ],
    [],
    "bundle.scene_data.appearance",
  );
  const placement = strictRecord(
    root.placement,
    ["slot", "framing_zoom", "source_framing_zoom"],
    [],
    "bundle.scene_data.placement",
  );
  exact(placement.slot, "right", "bundle.scene_data.placement.slot");
  const background = strictRecord(
    root.background,
    ["asset_id", "alt"],
    [],
    "bundle.scene_data.background",
  );
  const available_states = parseExactStates(
    root.available_states,
    "bundle.scene_data.available_states",
  );
  if (
    !Array.isArray(root.expression_variants) ||
    root.expression_variants.length !== 4
  ) {
    throw new Error(
      "bundle.scene_data.expression_variants must contain four states",
    );
  }
  const expression_variants = root.expression_variants.map((entry, index) => {
    const record = strictRecord(
      entry,
      [
        "id",
        "asset_id",
        "appearance_id",
        "state",
        "label",
        "description",
        "alt",
        "slot",
      ],
      [],
      `bundle.scene_data.expression_variants[${index}]`,
    );
    const state = expressionState(
      record.state,
      `bundle.scene_data.expression_variants[${index}].state`,
    );
    if (state !== DIALOGUE_SCENE_EXPRESSION_STATES[index]) {
      throw new Error(
        "bundle.scene_data.expression_variants must use locked state order",
      );
    }
    exact(
      record.slot,
      "right",
      `bundle.scene_data.expression_variants[${index}].slot`,
    );
    return Object.freeze({
      id: stableId(record.id, `expression_variants[${index}].id`),
      asset_id: stableId(
        record.asset_id,
        `expression_variants[${index}].asset_id`,
      ),
      appearance_id: stableId(
        record.appearance_id,
        `expression_variants[${index}].appearance_id`,
      ),
      state,
      label: strictText(
        record.label,
        `expression_variants[${index}].label`,
        64,
      ),
      description: strictText(
        record.description,
        `expression_variants[${index}].description`,
        220,
      ),
      alt: strictText(record.alt, `expression_variants[${index}].alt`, 160),
      slot: "right" as const,
    });
  });
  if (
    !Array.isArray(root.dialogue) ||
    root.dialogue.length < 1 ||
    root.dialogue.length > 12
  ) {
    throw new Error("bundle.scene_data.dialogue must contain 1 to 12 beats");
  }
  const beatIds = new Set<string>();
  const dialogue = root.dialogue.map((entry, index) => {
    const record = strictRecord(
      entry,
      ["id", "speaker", "text", "expression_state"],
      [],
      `bundle.scene_data.dialogue[${index}]`,
    );
    const id = stableId(record.id, `bundle.scene_data.dialogue[${index}].id`);
    if (beatIds.has(id))
      throw new Error(`bundle dialogue id is duplicated: ${id}`);
    beatIds.add(id);
    return Object.freeze({
      id,
      speaker: strictText(record.speaker, `dialogue[${index}].speaker`, 80),
      text: strictText(record.text, `dialogue[${index}].text`, 1000),
      expression_state: expressionState(
        record.expression_state,
        `dialogue[${index}].expression_state`,
      ),
    });
  });
  const appearanceId = stableId(
    appearance.id,
    "bundle.scene_data.appearance.id",
  );
  for (const variant of expression_variants) {
    if (variant.appearance_id !== appearanceId) {
      throw new Error(
        "bundle scene expression variant must reference appearance.id",
      );
    }
  }
  return Object.freeze({
    scene_id: stableId(root.scene_id, "bundle.scene_data.scene_id"),
    title: strictText(root.title, "bundle.scene_data.title", 96),
    scene_label: strictText(
      root.scene_label,
      "bundle.scene_data.scene_label",
      160,
    ),
    concept_asset_id: stableId(
      root.concept_asset_id,
      "bundle.scene_data.concept_asset_id",
    ),
    background: Object.freeze({
      asset_id: stableId(
        background.asset_id,
        "bundle.scene_data.background.asset_id",
      ),
      alt: strictText(background.alt, "bundle.scene_data.background.alt", 160),
    }),
    appearance: Object.freeze({
      id: appearanceId,
      label: strictText(appearance.label, "appearance.label", 96),
      age: strictInteger(appearance.age, "appearance.age", 21, 120),
      role: strictText(appearance.role, "appearance.role", 160),
      tagline: strictText(appearance.tagline, "appearance.tagline", 160),
      description: strictText(
        appearance.description,
        "appearance.description",
        3000,
      ),
      visual_identity: strictText(
        appearance.visual_identity,
        "appearance.visual_identity",
        3000,
      ),
      art_direction: strictText(
        appearance.art_direction,
        "appearance.art_direction",
        220,
      ),
    }),
    placement: Object.freeze({
      slot: "right" as const,
      framing_zoom: strictFiniteNumber(
        placement.framing_zoom,
        "placement.framing_zoom",
        0,
        100,
      ),
      source_framing_zoom: strictFiniteNumber(
        placement.source_framing_zoom,
        "placement.source_framing_zoom",
        0,
        100,
      ),
    }),
    available_states: Object.freeze(available_states),
    expression_variants: Object.freeze(expression_variants),
    dialogue: Object.freeze(dialogue),
  });
}

function parseReview(value: unknown): DialogueSceneBundleV4["review"] {
  const record = strictRecord(
    value,
    ["status"],
    ["path", "sha256", "provenance_path", "provenance_sha256"],
    "bundle.review",
  );
  const status = enumValue(
    record.status,
    ["pending", "pass", "fail"] as const,
    "bundle.review.status",
  );
  return Object.freeze({
    status,
    path:
      record.path === undefined || record.path === null
        ? null
        : portablePath(record.path, "bundle.review.path"),
    sha256:
      record.sha256 === undefined || record.sha256 === null
        ? null
        : digest(record.sha256, "bundle.review.sha256"),
    provenance_path:
      record.provenance_path === undefined || record.provenance_path === null
        ? null
        : portablePath(record.provenance_path, "bundle.review.provenance_path"),
    provenance_sha256:
      record.provenance_sha256 === undefined ||
      record.provenance_sha256 === null
        ? null
        : digest(record.provenance_sha256, "bundle.review.provenance_sha256"),
  });
}

function parseRights(value: unknown): DialogueSceneBundleV4["rights"] {
  const record = strictRecord(
    value,
    ["aggregate", "publication_authorized"],
    [],
    "bundle.rights",
  );
  return Object.freeze({
    aggregate: enumValue(
      record.aggregate,
      ["unreviewed", "restricted", "redistribution-approved"] as const,
      "bundle.rights.aggregate",
    ),
    publication_authorized: strictBoolean(
      record.publication_authorized,
      "bundle.rights.publication_authorized",
    ),
  });
}

function requireRoleAssets(
  assets: readonly BundleAsset[],
): ValidatedSourceBundle["roleAssets"] {
  const concepts = assets.filter((asset) => asset.role === "concept");
  const backgrounds = assets.filter((asset) => asset.role === "background");
  const expressions = assets.filter((asset) => asset.role === "expression");
  if (concepts.length !== 1)
    throw new Error("bundle must contain exactly one concept");
  if (backgrounds.length !== 1)
    throw new Error("web adapter requires exactly one background");
  if (expressions.length !== 4)
    throw new Error("bundle must contain four expressions");
  const expressionMap = new Map<DialogueSceneExpressionState, BundleAsset>();
  for (const expression of expressions) {
    if (expression.state === null || expressionMap.has(expression.state)) {
      throw new Error("bundle expression states must be unique and complete");
    }
    expressionMap.set(expression.state, expression);
  }
  for (const state of DIALOGUE_SCENE_EXPRESSION_STATES) {
    if (!expressionMap.has(state))
      throw new Error(`bundle expression state is missing: ${state}`);
  }
  return Object.freeze({
    concept: concepts[0],
    background: backgrounds[0],
    expressions: expressionMap,
  });
}

function validateAssetPng(asset: BundleAsset, bytes: Buffer): void {
  const png = inspectPng(bytes);
  if (
    png.width !== asset.media.width ||
    png.height !== asset.media.height ||
    png.alpha !== asset.media.alpha
  ) {
    throw new Error(`asset ${asset.id} PNG facts do not match bundle media`);
  }
  if (asset.role === "background") {
    if (png.width !== 1672 || png.height !== 941 || png.colorType !== 2) {
      throw new Error(
        `asset ${asset.id} background must be 1672x941 8-bit RGB PNG`,
      );
    }
  } else if (asset.role === "concept") {
    if (png.width !== 1024 || png.height !== 1536 || png.colorType !== 2) {
      throw new Error(
        `asset ${asset.id} concept must be 1024x1536 8-bit RGB PNG`,
      );
    }
  } else if (png.width !== 1024 || png.height !== 1536 || png.colorType !== 6) {
    throw new Error(
      `asset ${asset.id} expression must be 1024x1536 8-bit RGBA PNG`,
    );
  }
}

export function inspectPng(bytes: Buffer): {
  readonly width: number;
  readonly height: number;
  readonly alpha: boolean;
  readonly colorType: number;
} {
  if (bytes.byteLength < 45 || !bytes.subarray(0, 8).equals(PNG_SIGNATURE)) {
    throw new Error("asset is not a structurally valid PNG");
  }
  let offset = 8;
  let width = 0;
  let height = 0;
  let bitDepth = 0;
  let colorType = -1;
  let sawHeader = false;
  let sawData = false;
  let sawEnd = false;
  let sawTransparency = false;
  let sawPalette = false;
  let dataSequenceEnded = false;
  const compressedData: Buffer[] = [];
  while (offset < bytes.byteLength) {
    if (offset + 12 > bytes.byteLength)
      throw new Error("PNG chunk header is truncated");
    const length = bytes.readUInt32BE(offset);
    const typeStart = offset + 4;
    const dataStart = offset + 8;
    const dataEnd = dataStart + length;
    const crcOffset = dataEnd;
    if (dataEnd + 4 > bytes.byteLength)
      throw new Error("PNG chunk data is truncated");
    const type = bytes.toString("ascii", typeStart, dataStart);
    if (!/^[A-Za-z]{4}$/.test(type)) {
      throw new Error("PNG chunk type must contain four ASCII letters");
    }
    const expectedCrc = bytes.readUInt32BE(crcOffset);
    const actualCrc = crc32(bytes.subarray(typeStart, dataEnd));
    if (expectedCrc !== actualCrc)
      throw new Error(`PNG ${type} chunk CRC is invalid`);
    if (!sawHeader && type !== "IHDR")
      throw new Error("PNG IHDR must be the first chunk");
    if (type === "IHDR") {
      if (sawHeader || length !== 13)
        throw new Error("PNG must contain one valid IHDR");
      sawHeader = true;
      width = bytes.readUInt32BE(dataStart);
      height = bytes.readUInt32BE(dataStart + 4);
      bitDepth = bytes[dataStart + 8];
      colorType = bytes[dataStart + 9];
      if (width === 0 || height === 0)
        throw new Error("PNG dimensions must be positive");
      if (bitDepth !== 8 || ![2, 6].includes(colorType)) {
        throw new Error("PNG must use 8-bit RGB or RGBA encoding");
      }
      if (
        bytes[dataStart + 10] !== 0 ||
        bytes[dataStart + 11] !== 0 ||
        bytes[dataStart + 12] !== 0
      ) {
        throw new Error(
          "PNG uses unsupported compression, filter, or interlace mode",
        );
      }
    } else if (type === "IDAT") {
      if (dataSequenceEnded) {
        throw new Error("PNG IDAT chunks must be consecutive");
      }
      sawData = true;
      compressedData.push(bytes.subarray(dataStart, dataEnd));
    } else if (type === "tRNS") {
      if (sawData || sawTransparency || colorType !== 2 || length !== 6) {
        throw new Error("PNG tRNS must be one six-byte RGB transparency chunk before IDAT");
      }
      sawTransparency = true;
    } else if (type === "PLTE") {
      if (
        sawData ||
        sawPalette ||
        length < 3 ||
        length > 768 ||
        length % 3 !== 0
      ) {
        throw new Error("PNG PLTE must be one valid palette chunk before IDAT");
      }
      sawPalette = true;
    } else if (type === "IEND") {
      if (length !== 0) throw new Error("PNG IEND must be empty");
      sawEnd = true;
      if (crcOffset + 4 !== bytes.byteLength)
        throw new Error("PNG has data after IEND");
    } else if (/^[A-Z]/.test(type)) {
      throw new Error(`PNG contains unsupported critical chunk: ${type}`);
    }
    if (sawData && type !== "IDAT") dataSequenceEnded = true;
    offset = crcOffset + 4;
    if (sawEnd) break;
  }
  if (!sawHeader || !sawData || !sawEnd) {
    throw new Error("PNG is missing IHDR, IDAT, or IEND");
  }
  const channels = colorType === 6 ? 4 : 3;
  const rowBytes = width * channels + 1;
  const expectedInflatedBytes = rowBytes * height;
  let inflated: Buffer;
  try {
    inflated = inflateSync(Buffer.concat(compressedData), {
      maxOutputLength: expectedInflatedBytes + 1,
    });
  } catch {
    throw new Error("PNG IDAT payload is not decodable");
  }
  if (inflated.byteLength !== expectedInflatedBytes) {
    throw new Error("PNG decoded scanline size does not match IHDR dimensions");
  }
  for (let row = 0; row < height; row += 1) {
    if (inflated[row * rowBytes] > 4) {
      throw new Error("PNG decoded scanline uses an invalid filter type");
    }
  }
  return Object.freeze({
    width,
    height,
    alpha: colorType === 6 || sawTransparency,
    colorType,
  });
}

function crc32(bytes: Buffer): number {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function parseAttemptLedger(
  value: unknown,
): readonly Record<string, unknown>[] {
  const root = strictRecord(
    value,
    ["schema_version", "kind", "attempts"],
    [],
    "attempt ledger",
  );
  exact(root.schema_version, 2, "attempt ledger schema_version");
  exact(root.kind, "dialogue-attempt-ledger-v2", "attempt ledger kind");
  if (!Array.isArray(root.attempts))
    throw new Error("attempt ledger attempts must be an array");
  return root.attempts.map((attempt, index) =>
    strictRecord(
      attempt,
      [
        "stage",
        "role",
        "attempt",
        "outcome",
        "prompt_sha256",
        "reference_sha256",
      ],
      ["provider", "model", "artifact", "artifact_sha256", "reason"],
      `attempt ledger attempts[${index}]`,
    ),
  );
}

function validateRequestEnvelope(
  value: unknown,
  bundle: DialogueBundleContract,
): void {
  const root = strictRecord(
    value,
    [
      "schema_version",
      "kind",
      "game_id",
      "display_name",
      "revision",
      "scene_brief",
      "identity_reference_id",
      "character_profile",
      "references",
      "background",
      "dialogue",
      "presentation",
      "transparency_mode",
    ],
    [],
    "bundle request",
  );
  exact(root.schema_version, 1, "bundle request schema_version");
  exact(root.kind, "dialogue-scene-v1", "bundle request kind");
  if (root.game_id !== bundle.game_id) {
    throw new Error("request game_id does not match bundle");
  }
  strictText(root.display_name, "bundle request display_name", 96);
  strictInteger(root.revision, "bundle request revision", 1, Number.MAX_SAFE_INTEGER);
  strictText(root.scene_brief, "bundle request scene_brief", 96);
  validateAuthoredReferences(root, bundle);
  const characterProfile = strictRecord(
    root.character_profile,
    ["schema_version", "kind", "ref", "source_sha256"],
    [],
    "bundle request character_profile",
  );
  exact(characterProfile.schema_version, 1, "request character_profile schema_version");
  exact(characterProfile.kind, "character-profile-binding-v1", "request character_profile kind");
  const requestRef = portableProfileRef(characterProfile.ref, "request character_profile ref");
  const requestSource = digest(
    characterProfile.source_sha256,
    "request character_profile source_sha256",
  );
  if (
    requestRef !== bundle.character_profile_binding.ref ||
    requestSource !== bundle.character_profile_binding.source_sha256
  ) {
    throw new Error("request character profile binding does not match bundle");
  }
  const background = strictRecord(
    root.background,
    [],
    ["description"],
    "bundle request background",
  );
  if (background.description !== undefined) {
    strictText(background.description, "bundle request background description", 2000);
  }
  if (
    !Array.isArray(root.dialogue) ||
    root.dialogue.length < 1 ||
    root.dialogue.length > 12
  ) {
    throw new Error("bundle request dialogue must contain 1 to 12 beats");
  }
  const beatIds = new Set<string>();
  root.dialogue.forEach((value, index) => {
    const beat = strictRecord(
      value,
      ["id", "speaker", "text", "expression_state"],
      [],
      `bundle request dialogue[${index}]`,
    );
    const id = kebabId(beat.id, `bundle request dialogue[${index}].id`, 48);
    if (beatIds.has(id)) {
      throw new Error(`bundle request dialogue id is duplicated: ${id}`);
    }
    beatIds.add(id);
    strictText(beat.speaker, `bundle request dialogue[${index}].speaker`, 64);
    strictText(beat.text, `bundle request dialogue[${index}].text`, 320);
    expressionState(
      beat.expression_state,
      `bundle request dialogue[${index}].expression_state`,
    );
  });
  const presentation = strictRecord(
    root.presentation,
    ["slot", "framing_zoom", "source_framing_zoom"],
    [],
    "bundle request presentation",
  );
  exact(presentation.slot, "right", "bundle request presentation slot");
  strictInteger(
    presentation.framing_zoom,
    "bundle request presentation framing_zoom",
    0,
    100,
  );
  strictInteger(
    presentation.source_framing_zoom,
    "bundle request presentation source_framing_zoom",
    0,
    100,
  );
  enumValue(
    root.transparency_mode,
    ["native", "ai", "chroma"] as const,
    "bundle request transparency_mode",
  );
}

/**
 * The authored references the scene was drawn against, held to the bundle.
 *
 * The plate the run republished is the one the package declared, so the two must
 * agree on both its path and its bytes; a run that shipped something else is not
 * this scene, whatever its filename says.
 */
function validateAuthoredReferences(
  root: Record<string, unknown>,
  bundle: DialogueBundleContract,
): void {
  const identityReferenceId = snakeId(
    root.identity_reference_id,
    "bundle request identity_reference_id",
    64,
  );
  if (!Array.isArray(root.references) || root.references.length < 1) {
    throw new Error("bundle request references must declare at least one entry");
  }
  const seen = new Set<string>();
  let identity: Record<string, unknown> | null = null;
  root.references.forEach((value, index) => {
    const reference = strictRecord(
      value,
      ["reference_id", "source", "source_sha256", "rights_status", "rights_basis"],
      [],
      `bundle request references[${index}]`,
    );
    const id = snakeId(
      reference.reference_id,
      `bundle request references[${index}].reference_id`,
      64,
    );
    if (seen.has(id)) {
      throw new Error(`bundle request reference_id is duplicated: ${id}`);
    }
    seen.add(id);
    portableReuseRef(reference.source, `bundle request references[${index}].source`);
    digest(
      reference.source_sha256,
      `bundle request references[${index}].source_sha256`,
    );
    enumValue(
      reference.rights_status,
      ["unreviewed", "restricted", "redistribution-approved"] as const,
      `bundle request references[${index}].rights_status`,
    );
    if (!Array.isArray(reference.rights_basis) || reference.rights_basis.length < 1) {
      throw new Error(
        `bundle request references[${index}].rights_basis must state at least one line`,
      );
    }
    reference.rights_basis.forEach((line, lineIndex) => {
      strictText(line, `bundle request references[${index}].rights_basis[${lineIndex}]`, 320);
    });
    if (id === identityReferenceId) {
      identity = reference;
    }
  });
  if (identity === null) {
    throw new Error("bundle request identity_reference_id names an undeclared reference");
  }
  const declared = identity as Record<string, unknown>;
  if (declared.source !== bundle.identity_reference_source) {
    throw new Error("request identity reference source does not match bundle");
  }
  if (declared.source_sha256 !== bundle.identity_reference.sha256) {
    throw new Error("request identity reference digest does not match the published plate");
  }
}

function validatePlanEnvelope(
  value: unknown,
  bundle: DialogueBundleContract,
): void {
  const root = strictRecord(
    value,
    [
      "schema_version",
      "kind",
      "recipe_version",
      "policy_version",
      "expression_profile",
      "request_sha256",
      "appearance_id",
      "character_profile_ref",
      "character_profile_source_sha256",
      "character_profile_sha256",
      "identity_reference_sha256",
      "shared_locks",
      "geometry",
      "states",
      "prompt_templates",
    ],
    [],
    "bundle plan",
  );
  exact(root.schema_version, 4, "bundle plan schema_version");
  exact(root.kind, "dialogue-scene-plan-v4", "bundle plan kind");
  exact(root.recipe_version, "dialogue-scene-v5", "bundle plan recipe_version");
  exact(
    root.policy_version,
    "coming-of-age-nonexplicit-v3",
    "bundle plan policy_version",
  );
  exact(
    root.expression_profile,
    "expression-core-v3",
    "bundle plan expression_profile",
  );
  if (
    digest(root.identity_reference_sha256, "bundle plan identity_reference_sha256") !==
    bundle.identity_reference.sha256
  ) {
    throw new Error("plan identity_reference_sha256 does not match the published plate");
  }
  if (
    digest(root.request_sha256, "bundle plan request_sha256") !==
    bundle.request.sha256
  ) {
    throw new Error("plan request_sha256 does not match bundle request");
  }
  if (
    kebabId(root.appearance_id, "bundle plan appearance_id", 96) !==
    bundle.scene_data.appearance.id
  ) {
    throw new Error("plan appearance_id does not match bundle scene appearance");
  }
  const ref = portableProfileRef(
    root.character_profile_ref,
    "bundle plan character_profile_ref",
  );
  const source = digest(
    root.character_profile_source_sha256,
    "bundle plan character_profile_source_sha256",
  );
  const canonical = digest(
    root.character_profile_sha256,
    "bundle plan character_profile_sha256",
  );
  if (
    ref !== bundle.character_profile_binding.ref ||
    source !== bundle.character_profile_binding.source_sha256 ||
    canonical !== bundle.character_profile_sha256
  ) {
    throw new Error("plan character profile binding does not match bundle");
  }
  const sharedLocks = strictRecord(
    root.shared_locks,
    ["identity", "wardrobe", "pose", "lighting", "style"],
    [],
    "bundle plan shared_locks",
  );
  strictText(sharedLocks.identity, "bundle plan shared_locks identity", 2000);
  for (const key of ["wardrobe", "pose", "lighting", "style"] as const) {
    strictText(
      sharedLocks[key],
      `bundle plan shared_locks ${key}`,
      1000,
    );
  }
  const geometry = strictRecord(
    root.geometry,
    ["canvas", "crop", "slot", "safe_bounds"],
    [],
    "bundle plan geometry",
  );
  const canvas = strictRecord(
    geometry.canvas,
    ["width", "height"],
    [],
    "bundle plan geometry canvas",
  );
  exact(canvas.width, 1024, "bundle plan geometry canvas width");
  exact(canvas.height, 1536, "bundle plan geometry canvas height");
  exact(
    geometry.crop,
    "top-hair-through-waist",
    "bundle plan geometry crop",
  );
  exact(geometry.slot, "right", "bundle plan geometry slot");
  if (
    !Array.isArray(geometry.safe_bounds) ||
    geometry.safe_bounds.length !== 4 ||
    geometry.safe_bounds.some(
      (entry, index) =>
        typeof entry !== "number" ||
        !Number.isFinite(entry) ||
        entry !== [0, 0, 1, 1][index],
    )
  ) {
    throw new Error("bundle plan geometry safe_bounds must equal [0, 0, 1, 1]");
  }
  if (
    !Array.isArray(root.states) ||
    root.states.length !== DIALOGUE_SCENE_EXPRESSION_STATES.length
  ) {
    throw new Error("bundle plan states must contain the four locked states");
  }
  root.states.forEach((value, index) => {
    const state = strictRecord(
      value,
      ["id", "direction"],
      [],
      `bundle plan states[${index}]`,
    );
    exact(
      state.id,
      DIALOGUE_SCENE_EXPRESSION_STATES[index],
      `bundle plan states[${index}] id`,
    );
    strictText(state.direction, `bundle plan states[${index}] direction`, 1000);
  });
  if (!Array.isArray(root.prompt_templates)) {
    throw new Error("bundle plan prompt_templates must be an array");
  }
  root.prompt_templates.forEach((value, index) => {
    const template = strictRecord(
      value,
      ["id", "sha256"],
      [],
      `bundle plan prompt_templates[${index}]`,
    );
    strictText(
      template.id,
      `bundle plan prompt_templates[${index}] id`,
      MAX_JSON_BYTES,
    );
    digest(
      template.sha256,
      `bundle plan prompt_templates[${index}] sha256`,
    );
  });
}

async function validateV3StyleContract(options: {
  readonly bundle: DialogueBundleContract;
  readonly sourceRoot: string;
  readonly sourceCopies: SourceCopy[];
  readonly seenSourcePaths: Set<string>;
  readonly planProvenance: unknown;
  readonly pendingBundleSha256: string;
}): Promise<void> {
  const planMetadata = provenanceMetadata(options.planProvenance, "plan provenance");
  const planBinding = parseStyleProvenanceBinding(
    planMetadata,
    "plan provenance params.metadata",
  );
  await addSourceCopy(
    options.sourceCopies,
    options.seenSourcePaths,
    options.sourceRoot,
    "style-anchor",
    planBinding.style_anchor_path,
    planBinding.style_anchor_artifact_sha256,
    `records/${planBinding.style_anchor_artifact_sha256}.json`,
    MAX_JSON_BYTES,
    true,
  );
  await addSourceCopy(
    options.sourceCopies,
    options.seenSourcePaths,
    options.sourceRoot,
    "style-anchor-provenance",
    planBinding.style_anchor_provenance_path,
    planBinding.style_anchor_provenance_sha256,
    `provenance/${planBinding.style_anchor_provenance_sha256}.json`,
    MAX_JSON_BYTES,
    true,
  );
  const anchorCopy = options.sourceCopies.find(
    (copy) => copy.kind === "style-anchor",
  );
  const anchorProvenanceCopy = options.sourceCopies.find(
    (copy) => copy.kind === "style-anchor-provenance",
  );
  if (anchorCopy === undefined || anchorProvenanceCopy === undefined) {
    throw new Error("v3 style anchor or provenance copy is missing");
  }
  const anchorValue = parseJson(
    await readFile(anchorCopy.absoluteSourcePath),
    "style anchor",
  );
  const anchorFacts = parseStyleAnchor(anchorValue);
  validateProvenanceBinding(
    parseJson(
      await readFile(anchorProvenanceCopy.absoluteSourcePath),
      "style anchor provenance",
    ),
    planBinding.style_anchor_artifact_sha256,
    "style anchor provenance",
  );
  validateStyleBindingAgainstAnchor(
    planBinding,
    anchorFacts,
    "plan provenance",
  );
  const expectedPlanProfile = {
    character_profile_ref: options.bundle.character_profile_binding.ref,
    character_profile_source_sha256:
      options.bundle.character_profile_binding.source_sha256,
    character_profile_path: options.bundle.character_profile.path,
    character_profile_sha256: options.bundle.character_profile_sha256,
    character_profile_provenance_path:
      options.bundle.character_profile.provenance_path,
    character_profile_provenance_sha256:
      options.bundle.character_profile.provenance_sha256,
  };
  for (const [key, value] of Object.entries(expectedPlanProfile)) {
    if (planMetadata[key] !== value) {
      throw new Error(`plan provenance ${key} does not match character profile binding`);
    }
  }

  const bundleProvenanceSource = await readPortableSource(
    options.sourceRoot,
    "bundle.json.meta.json",
    MAX_JSON_BYTES,
    "bundle provenance",
  );
  const bundleProvenanceValue = parseJson(
    bundleProvenanceSource.bytes,
    "bundle provenance",
  );
  assertLowerSnakeCaseKeys(bundleProvenanceValue, "bundle provenance");
  validateProvenanceBinding(
    bundleProvenanceValue,
    options.pendingBundleSha256,
    "bundle provenance",
  );
  const bundleRoot = strictRecord(
    bundleProvenanceValue,
    ["schema_version", "artifact", "params", "refs"],
    [],
    "bundle provenance",
    true,
  );
  if (
    !Array.isArray(bundleRoot.refs) ||
    !bundleRoot.refs.includes("style-anchor.json") ||
    !bundleRoot.refs.includes("style-anchor.json.meta.json")
  ) {
    throw new Error(
      "bundle provenance refs must bind the style anchor and provenance",
    );
  }
  const bundleBinding = parseStyleProvenanceBinding(
    strictRecord(bundleRoot.params, [], [], "bundle provenance params", true),
    "bundle provenance params",
  );
  if (
    !canonicalJsonBytes(bundleBinding).equals(canonicalJsonBytes(planBinding))
  ) {
    throw new Error(
      "plan and bundle provenance style bindings must match exactly",
    );
  }
  validateStyleBindingAgainstAnchor(
    bundleBinding,
    anchorFacts,
    "bundle provenance",
  );
  const params = strictRecord(bundleRoot.params, [], [], "bundle provenance params", true);
  const expectedBundleProfile = {
    character_profile_ref: options.bundle.character_profile_binding.ref,
    character_profile_source_sha256:
      options.bundle.character_profile_binding.source_sha256,
    character_profile_path: options.bundle.character_profile.path,
    character_profile_sha256: options.bundle.character_profile_sha256,
    character_profile_provenance_path:
      options.bundle.character_profile.provenance_path,
    character_profile_provenance_sha256:
      options.bundle.character_profile.provenance_sha256,
  };
  for (const [key, value] of Object.entries(expectedBundleProfile)) {
    if (params[key] !== value) {
      throw new Error(`bundle provenance ${key} does not match character profile binding`);
    }
  }
  if (
    !Array.isArray(bundleRoot.refs) ||
    !bundleRoot.refs.includes(options.bundle.character_profile.path) ||
    !bundleRoot.refs.includes(options.bundle.character_profile.provenance_path)
  ) {
    throw new Error("bundle provenance refs must bind the character profile and provenance");
  }
  await addComputedSourceCopy(
    options.sourceCopies,
    options.seenSourcePaths,
    "bundle-provenance",
    "bundle.json.meta.json",
    bundleProvenanceSource,
    `provenance/${sha256(bundleProvenanceSource.bytes)}.json`,
  );
}

function provenanceMetadata(
  value: unknown,
  label: string,
): Record<string, unknown> {
  const root = strictRecord(value, ["params"], [], label, true);
  const params = strictRecord(
    root.params,
    ["metadata"],
    [],
    `${label} params`,
    true,
  );
  return strictRecord(
    params.metadata,
    [],
    [],
    `${label} params.metadata`,
    true,
  );
}

function parseStyleProvenanceBinding(
  value: Record<string, unknown>,
  label: string,
): StyleProvenanceBinding {
  const required = strictRecord(
    value,
    [
      "style_anchor_path",
      "style_anchor_artifact_sha256",
      "style_anchor_provenance_path",
      "style_anchor_provenance_sha256",
      "style_anchor_sha256",
      "style_compiler_sha256",
      "style_compiler_version",
      "style_resource_sha256",
      "style_skill_sha256",
      "style_vocabulary_sha256",
    ],
    [],
    label,
    true,
  );
  exact(
    required.style_anchor_path,
    "style-anchor.json",
    `${label}.style_anchor_path`,
  );
  exact(
    required.style_anchor_provenance_path,
    "style-anchor.json.meta.json",
    `${label}.style_anchor_provenance_path`,
  );
  return Object.freeze({
    style_anchor_path: "style-anchor.json",
    style_anchor_artifact_sha256: digest(
      required.style_anchor_artifact_sha256,
      `${label}.style_anchor_artifact_sha256`,
    ),
    style_anchor_provenance_path: "style-anchor.json.meta.json",
    style_anchor_provenance_sha256: digest(
      required.style_anchor_provenance_sha256,
      `${label}.style_anchor_provenance_sha256`,
    ),
    style_anchor_sha256: digest(
      required.style_anchor_sha256,
      `${label}.style_anchor_sha256`,
    ),
    style_compiler_sha256: digest(
      required.style_compiler_sha256,
      `${label}.style_compiler_sha256`,
    ),
    style_compiler_version: strictInteger(
      required.style_compiler_version,
      `${label}.style_compiler_version`,
      1,
      1,
    ),
    style_resource_sha256: digest(
      required.style_resource_sha256,
      `${label}.style_resource_sha256`,
    ),
    style_skill_sha256: digest(
      required.style_skill_sha256,
      `${label}.style_skill_sha256`,
    ),
    style_vocabulary_sha256: digest(
      required.style_vocabulary_sha256,
      `${label}.style_vocabulary_sha256`,
    ),
  });
}

function parseStyleAnchor(value: unknown): StyleAnchorFacts {
  const root = strictRecord(
    value,
    [
      "schema_version",
      "kind",
      "style_mode",
      "medium_keyword",
      "observable_traits",
      "asset_treatments",
      "exclusions",
      "skill_sha256",
      "vocabulary_sha256",
      "resource_sha256",
      "compiler_sha256",
      "compiler_version",
    ],
    [],
    "style anchor",
  );
  exact(root.schema_version, 1, "style anchor schema_version");
  exact(root.kind, "canonical_style_anchor_v1", "style anchor kind");
  strictText(root.medium_keyword, "style anchor medium_keyword", 240);
  strictTextArray(root.observable_traits, "style anchor observable_traits");
  strictTextArray(root.exclusions, "style anchor exclusions");
  const treatments = strictRecord(
    root.asset_treatments,
    [
      "concept_art",
      "character_sprite",
      "environment_background",
      "illustration",
      "asset_sheet",
      "tileable_texture",
      "interface_art",
      "effect_sheet",
    ],
    [],
    "style anchor asset_treatments",
  );
  for (const [kind, treatment] of Object.entries(treatments)) {
    strictText(treatment, `style anchor asset_treatments.${kind}`, 500);
  }
  return Object.freeze({
    style_mode: enumValue(
      root.style_mode,
      [
        "cel_shaded_anime_2d",
        "photorealistic_natural",
        "gouache_illustration_2d",
      ] as const,
      "style anchor style_mode",
    ),
    compiler_sha256: digest(
      root.compiler_sha256,
      "style anchor compiler_sha256",
    ),
    compiler_version: strictInteger(
      root.compiler_version,
      "style anchor compiler_version",
      1,
      1,
    ),
    resource_sha256: digest(
      root.resource_sha256,
      "style anchor resource_sha256",
    ),
    skill_sha256: digest(root.skill_sha256, "style anchor skill_sha256"),
    vocabulary_sha256: digest(
      root.vocabulary_sha256,
      "style anchor vocabulary_sha256",
    ),
    canonical_sha256: sha256(
      Buffer.from(JSON.stringify(sortJson(value)), "utf8"),
    ),
  });
}

function strictTextArray(value: unknown, label: string): readonly string[] {
  if (!Array.isArray(value) || value.length < 1) {
    throw new Error(`${label} must be a non-empty array`);
  }
  return Object.freeze(
    value.map((entry, index) => strictText(entry, `${label}[${index}]`, 500)),
  );
}

function validateStyleBindingAgainstAnchor(
  binding: StyleProvenanceBinding,
  anchor: StyleAnchorFacts,
  label: string,
): void {
  const expected = {
    style_anchor_sha256: anchor.canonical_sha256,
    style_compiler_sha256: anchor.compiler_sha256,
    style_compiler_version: anchor.compiler_version,
    style_resource_sha256: anchor.resource_sha256,
    style_skill_sha256: anchor.skill_sha256,
    style_vocabulary_sha256: anchor.vocabulary_sha256,
  };
  for (const [key, expectedValue] of Object.entries(expected)) {
    if (binding[key as keyof StyleProvenanceBinding] !== expectedValue) {
      throw new Error(`${label} ${key} does not match the style anchor`);
    }
  }
}

function validateProvenanceBinding(
  value: unknown,
  artifactSha256: string,
  label: string,
): void {
  const root = strictRecord(
    value,
    ["schema_version", "artifact"],
    [],
    label,
    true,
  );
  exact(root.schema_version, 2, `${label} schema_version`);
  const artifact = strictRecord(
    root.artifact,
    ["sha256"],
    [],
    `${label} artifact`,
    true,
  );
  if (digest(artifact.sha256, `${label} artifact sha256`) !== artifactSha256) {
    throw new Error(`${label} does not bind the selected artifact digest`);
  }
}

function ledgerHasSelectedAttempt(
  ledger: readonly Record<string, unknown>[],
  asset: BundleAsset,
): boolean {
  return ledger.some(
    (attempt) =>
      attempt.outcome === "selected" &&
      attempt.attempt === asset.selected_attempt &&
      attempt.artifact_sha256 === asset.sha256,
  );
}

function validateReviewProof(
  value: unknown,
  expectedStatus: Exclude<ReviewStatus, "pending">,
  bundle: DialogueBundleContract,
): string {
  const record = strictRecord(
    value,
    [
      "schema_version",
      "kind",
      "status",
      "usage",
      "source_bundle_sha256",
      "acceptance_spec_sha256",
      "character_profile_source_sha256",
      "character_profile_sha256",
      "independent_reviewer",
      "asset_sha256",
      "publication_authorized",
      "reviewed_at",
    ],
    [],
    "review record",
  );
  exact(record.schema_version, 4, "review record schema_version");
  exact(record.kind, "dialogue-scene-review-v4", "review record kind");
  exact(record.status, expectedStatus, "review record status");
  exact(record.usage, "local-demo", "review record usage");
  const sourceBundleSha256 = digest(
    record.source_bundle_sha256,
    "review record source_bundle_sha256",
  );
  digest(record.acceptance_spec_sha256, "review record acceptance_spec_sha256");
  if (record.independent_reviewer !== true) {
    throw new Error("review record must declare an independent reviewer");
  }
  if (!Array.isArray(record.asset_sha256)) {
    throw new Error("review record asset_sha256 must be an array");
  }
  const reviewed = [...record.asset_sha256].map((item, index) =>
    digest(item, `review record asset_sha256[${index}]`),
  );
  const expected = bundle.assets.map((asset) => asset.sha256);
  const sortedReviewed = [...reviewed].sort();
  const sortedExpected = [...expected].sort();
  if (
    reviewed.length !== expected.length ||
    sortedReviewed.some((item, index) => item !== sortedExpected[index])
  ) {
    throw new Error(
      "review record must bind the exact selected asset digest multiset",
    );
  }
  if (record.publication_authorized !== false) {
    throw new Error("local-demo review record must not authorize publication");
  }
  if (
    digest(
      record.character_profile_source_sha256,
      "review record character_profile_source_sha256",
    ) !== bundle.character_profile_binding.source_sha256 ||
    digest(
      record.character_profile_sha256,
      "review record character_profile_sha256",
    ) !== bundle.character_profile_sha256
  ) {
    throw new Error("review record character profile binding does not match bundle");
  }
  if (
    typeof record.reviewed_at !== "string" ||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/.test(
      record.reviewed_at,
    ) ||
    Number.isNaN(Date.parse(record.reviewed_at))
  ) {
    throw new Error(
      "review record reviewed_at must be a UTC ISO-8601 timestamp",
    );
  }
  return sourceBundleSha256;
}

function validateV4ReviewProvenance(
  value: unknown,
  bundle: DialogueSceneBundleV4,
  sourceBundleSha256: string,
): void {
  const root = strictRecord(
    value,
    ["schema_version", "artifact", "params", "refs"],
    [],
    "review provenance",
    true,
  );
  if (
    !Array.isArray(root.refs) ||
    !root.refs.includes("bundle.json") ||
    !root.refs.includes(bundle.character_profile.path)
  ) {
    throw new Error("review provenance refs must bind bundle and character profile");
  }
  const params = strictRecord(root.params, [], [], "review provenance params", true);
  const expected = {
    source_bundle_sha256: sourceBundleSha256,
    character_profile_ref: bundle.character_profile_binding.ref,
    character_profile_source_sha256: bundle.character_profile_binding.source_sha256,
    character_profile_sha256: bundle.character_profile_sha256,
  };
  for (const [key, expectedValue] of Object.entries(expected)) {
    if (params[key] !== expectedValue) {
      throw new Error(`review provenance ${key} does not match reviewed bundle`);
    }
  }
}

function validateReviewedTransition(
  pending: DialogueBundleContract,
  reviewed: DialogueBundleContract,
): void {
  if (pending.schema_version !== reviewed.schema_version || pending.kind !== reviewed.kind) {
    throw new Error("review source and reviewed bundle wire contracts must match");
  }
  if (
    pending.review.status !== "pending" ||
    pending.rights.aggregate !== "unreviewed" ||
    pending.rights.publication_authorized
  ) {
    throw new Error("review source bundle must be pending and unreviewed");
  }
  const normalizedReviewed: DialogueBundleContract = {
    ...reviewed,
    review: {
      status: "pending",
      path: null,
      sha256: null,
      provenance_path: null,
      provenance_sha256: null,
    },
    rights: { aggregate: "unreviewed", publication_authorized: false },
  };
  if (
    !canonicalJsonBytes(pending).equals(canonicalJsonBytes(normalizedReviewed))
  ) {
    throw new Error(
      "reviewed bundle may differ from its pending source only in review and rights",
    );
  }
}

function parseInstallReceipt(value: unknown): InstallReceipt {
  const root = strictRecord(
    value,
    [
      "schema_version",
      "kind",
      "adapter_version",
      "bundle_id",
      "bundle_wire_schema_version",
      "bundle_kind",
      "recipe_version",
      "source_bundle_sha256",
      "fixture_sha256",
      "character_profile_source_sha256",
      "character_profile_sha256",
      "profile_id",
      "profile_revision",
      "review_status",
      "rights_status",
      "publication_authorized",
      "copies",
    ],
    [],
    "install receipt",
  );
  exact(root.schema_version, 3, "install receipt schema_version");
  exact(root.kind, "dialogue-theme-install-v3", "install receipt kind");
  exact(root.adapter_version, 3, "install receipt adapter_version");
  exact(
    root.bundle_wire_schema_version,
    3,
    "install receipt bundle_wire_schema_version",
  );
  exact(
    root.bundle_kind,
    "dialogue-scene-bundle-v4",
    "install receipt bundle_kind",
  );
  exact(
    root.recipe_version,
    "dialogue-scene-v5",
    "install receipt recipe_version",
  );
  return Object.freeze({
    schema_version: 3,
    kind: "dialogue-theme-install-v3",
    adapter_version: 3,
    bundle_id: digest(root.bundle_id, "install receipt bundle_id"),
    bundle_wire_schema_version: 3,
    bundle_kind: "dialogue-scene-bundle-v4",
    recipe_version: "dialogue-scene-v5",
    source_bundle_sha256: digest(
      root.source_bundle_sha256,
      "install receipt source_bundle_sha256",
    ),
    fixture_sha256: digest(
      root.fixture_sha256,
      "install receipt fixture_sha256",
    ),
    character_profile_source_sha256: digest(
      root.character_profile_source_sha256,
      "install receipt character_profile_source_sha256",
    ),
    character_profile_sha256: digest(
      root.character_profile_sha256,
      "install receipt character_profile_sha256",
    ),
    profile_id: stableId(root.profile_id, "install receipt profile_id"),
    profile_revision: strictInteger(
      root.profile_revision,
      "install receipt profile_revision",
      1,
      2_147_483_647,
    ),
    review_status: enumValue(
      root.review_status,
      ["pending", "pass", "fail"] as const,
      "install receipt review_status",
    ),
    rights_status: enumValue(
      root.rights_status,
      ["unreviewed", "restricted", "redistribution-approved"] as const,
      "install receipt rights_status",
    ),
    publication_authorized: strictBoolean(
      root.publication_authorized,
      "install receipt publication_authorized",
    ),
    copies: parseInstallCopies(root.copies),
  });
}
function parseInstallCopies(value: unknown): readonly InstallCopy[] {
  if (!Array.isArray(value) || value.length < 1) {
    throw new Error("install receipt copies must be a non-empty array");
  }
  const copies = value.map((entry, index) => {
    const record = strictRecord(
      entry,
      ["kind", "source_path", "installed_path", "sha256", "bytes"],
      [],
      `install receipt copies[${index}]`,
    );
    return Object.freeze({
      kind: enumValue(
        record.kind,
        [
          "request", "request-provenance", "plan", "plan-provenance",
          "bundle-provenance", "style-anchor", "style-anchor-provenance",
          "character-profile", "character-profile-provenance", "attempt-ledger",
          "review", "review-provenance", "review-source", "asset", "asset-provenance",
        ] as const,
        `install receipt copies[${index}].kind`,
      ),
      source_path: portablePath(record.source_path, `install receipt copies[${index}].source_path`),
      installed_path: portablePath(record.installed_path, `install receipt copies[${index}].installed_path`),
      sha256: digest(record.sha256, `install receipt copies[${index}].sha256`),
      bytes: strictInteger(record.bytes, `install receipt copies[${index}].bytes`, 1, MAX_PNG_BYTES),
    });
  });
  if (new Set(copies.map((copy) => copy.installed_path)).size !== copies.length) {
    throw new Error("install receipt installed paths must be unique");
  }
  return Object.freeze(copies);
}

function computeBundleId(
  source_bundle_sha256: string,
  copies: readonly Pick<
    InstallCopy,
    "kind" | "source_path" | "installed_path" | "sha256" | "bytes"
  >[],
): string {
  return sha256(
    canonicalJsonBytes({
      domain: "stage-gen:dialogue-theme-install:v3",
      adapter_version: 3,
      source_bundle_sha256,
      copies: [...copies]
        .map(
          ({
            kind,
            source_path,
            installed_path,
            sha256: fileSha256,
            bytes,
          }) => ({
            kind,
            source_path,
            installed_path,
            sha256: fileSha256,
            bytes,
          }),
        )
        .sort((left, right) =>
          left.installed_path.localeCompare(right.installed_path),
        ),
    }),
  );
}

function isLocalActivationEligible(receipt: InstallReceipt): boolean {
  return (
    receipt.review_status === "pass" &&
    receipt.rights_status === "restricted" &&
    !receipt.publication_authorized
  );
}

async function addSourceCopy(
  copies: SourceCopy[],
  seenPaths: Set<string>,
  sourceRoot: string,
  kind: InstallCopy["kind"],
  sourcePath: string,
  expectedSha256: string,
  installedPath: string,
  maximumBytes: number,
  requireJson: boolean,
): Promise<void> {
  const source = await readPortableSource(
    sourceRoot,
    sourcePath,
    maximumBytes,
    kind,
  );
  const actualSha256 = sha256(source.bytes);
  if (actualSha256 !== expectedSha256) {
    throw new Error(`${kind} digest does not match bundle: ${sourcePath}`);
  }
  if (requireJson) {
    const value = parseJson(source.bytes, kind);
    assertLowerSnakeCaseKeys(value, kind);
  }
  await addComputedSourceCopy(
    copies,
    seenPaths,
    kind,
    sourcePath,
    source,
    installedPath,
    actualSha256,
  );
}

async function addComputedSourceCopy(
  copies: SourceCopy[],
  seenPaths: Set<string>,
  kind: InstallCopy["kind"],
  sourcePath: string,
  source: { readonly absolutePath: string; readonly bytes: Buffer },
  installedPath: string,
  knownSha256?: string,
): Promise<void> {
  portablePath(sourcePath, `${kind} source path`);
  portablePath(installedPath, `${kind} installed path`);
  if (seenPaths.has(sourcePath))
    throw new Error(`bundle file path is reused: ${sourcePath}`);
  seenPaths.add(sourcePath);
  copies.push(
    Object.freeze({
      kind,
      source_path: sourcePath,
      installed_path: installedPath,
      sha256: knownSha256 ?? sha256(source.bytes),
      bytes: source.bytes.byteLength,
      absoluteSourcePath: source.absolutePath,
    }),
  );
}

function assertLowerSnakeCaseKeys(value: unknown, label: string): void {
  if (Array.isArray(value)) {
    value.forEach((entry, index) =>
      assertLowerSnakeCaseKeys(entry, `${label}[${index}]`),
    );
    return;
  }
  if (value === null || typeof value !== "object") return;
  for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
    const insideJsonSchema = label.includes(".params.schema");
    if (
      !/^[a-z][a-z0-9_]*$/.test(key) &&
      !(insideJsonSchema && JSON_SCHEMA_KEYWORDS.has(key))
    ) {
      throw new Error(`${label} key must be lower_snake_case: ${key}`);
    }
    assertLowerSnakeCaseKeys(child, `${label}.${key}`);
  }
}

async function readPortableSource(
  sourceRoot: string,
  portable: string,
  maximumBytes: number,
  label: string,
): Promise<{ readonly absolutePath: string; readonly bytes: Buffer }> {
  const safe = portablePath(portable, `${label} path`);
  const absolutePath = path.resolve(sourceRoot, ...safe.split("/"));
  const relative = path.relative(sourceRoot, absolutePath);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error(`${label} path escapes its bundle directory`);
  }
  let current = sourceRoot;
  for (const segment of safe.split("/")) {
    current = path.join(current, segment);
    const facts = await lstat(current);
    if (facts.isSymbolicLink())
      throw new Error(`${label} path must not contain symlinks`);
  }
  await assertRegularNonSymlink(absolutePath, label);
  return Object.freeze({
    absolutePath,
    bytes: await readBoundedFile(absolutePath, maximumBytes, label),
  });
}

async function readInstalledFile(
  directory: string,
  portable: string,
  expectedBytes: number,
): Promise<Buffer> {
  const value = await readPortableSource(
    directory,
    portable,
    MAX_PNG_BYTES,
    "installed copy",
  );
  if (value.bytes.byteLength !== expectedBytes) {
    throw new Error(`installed copy byte count changed: ${portable}`);
  }
  return value.bytes;
}

async function readBoundedFile(
  filePath: string,
  maximumBytes: number,
  label: string,
): Promise<Buffer> {
  const facts = await stat(filePath);
  if (!facts.isFile()) throw new Error(`${label} must be a regular file`);
  if (facts.size < 1 || facts.size > maximumBytes) {
    throw new Error(`${label} size is outside the supported range`);
  }
  return readFile(filePath);
}

async function assertRegularNonSymlink(
  filePath: string,
  label: string,
): Promise<void> {
  const facts = await lstat(filePath);
  if (facts.isSymbolicLink() || !facts.isFile()) {
    throw new Error(`${label} must be a regular non-symlink file`);
  }
}

async function assertDirectoryNonSymlink(
  directory: string,
  label: string,
): Promise<void> {
  const facts = await lstat(directory);
  if (facts.isSymbolicLink() || !facts.isDirectory()) {
    throw new Error(`${label} must be a non-symlink directory`);
  }
}

async function pathKind(
  filePath: string,
): Promise<"missing" | "file" | "directory" | "other"> {
  try {
    const facts = await lstat(filePath);
    if (facts.isSymbolicLink()) return "other";
    if (facts.isFile()) return "file";
    if (facts.isDirectory()) return "directory";
    return "other";
  } catch (error) {
    if (isMissingError(error)) return "missing";
    throw error;
  }
}

async function writeNewFile(filePath: string, bytes: Buffer): Promise<void> {
  const handle = await open(filePath, "wx", 0o600);
  try {
    await handle.writeFile(bytes);
    await handle.sync();
  } finally {
    await handle.close();
  }
}

async function countInstalledBundles(stateRoot: string): Promise<number> {
  try {
    const entries = await readdir(stateRoot, { withFileTypes: true });
    return entries.filter(
      (entry) => entry.isDirectory() && SHA256.test(entry.name),
    ).length;
  } catch (error) {
    if (isMissingError(error)) return 0;
    throw error;
  }
}

function portablePath(value: unknown, label: string): string {
  const parsed = strictText(value, label, 240);
  if (
    parsed.includes("\\") ||
    parsed.startsWith("/") ||
    /^[A-Za-z]:/.test(parsed) ||
    path.posix.normalize(parsed) !== parsed
  ) {
    throw new Error(`${label} must be a canonical relative POSIX path`);
  }
  const segments = parsed.split("/");
  if (
    segments.some(
      (segment) =>
        segment === "." || segment === ".." || !PORTABLE_SEGMENT.test(segment),
    )
  ) {
    throw new Error(`${label} contains an unsafe path segment`);
  }
  return parsed;
}

function portableReuseRef(value: unknown, label: string): string {
  const ref = strictText(value, label, MAX_JSON_BYTES);
  const segments = ref.split("/");
  if (
    ref.includes("\0") ||
    ref.includes("\\") ||
    ref.startsWith("/") ||
    ref.startsWith("~") ||
    ref.startsWith("http://") ||
    ref.startsWith("https://") ||
    segments.some((segment) => segment === "" || segment === "." || segment === "..")
  ) {
    throw new Error(`${label} must be a portable relative reuse reference`);
  }
  return ref;
}

/**
 * The profile ref names a member of the package that bound it. The consumer
 * cannot see that package, so it checks portability and shape only - the digest
 * is what actually binds the bytes.
 */
function portableProfileRef(value: unknown, label: string): string {
  const ref = portablePath(value, label);
  if (!ref.endsWith(".toml")) {
    throw new Error(`${label} must name a package-relative TOML member`);
  }
  return ref;
}

function parseCanonicalCharacterProfile(
  bytes: Buffer,
  bundle: DialogueSceneBundleV4,
): { readonly profile_id: string; readonly revision: number } {
  const value = parseJson(bytes, "character profile");
  assertLowerSnakeCaseKeys(value, "character profile");
  const root = strictRecord(
    value,
    [
      "schema_version",
      "kind",
      "profile_id",
      "revision",
      "display_name",
      "description",
      "visual_identity",
      "wardrobe",
      "invariants",
      "rights",
      "references",
    ],
    ["age_years"],
    "character profile",
  );
  exact(root.schema_version, 1, "character profile schema_version");
  exact(root.kind, "character-profile-v1", "character profile kind");
  const profileId = stableId(root.profile_id, "character profile profile_id");
  const revision = strictInteger(root.revision, "character profile revision", 1, 2147483647);
  // The profile's id is no longer encoded in its path, so the scene projection
  // is what has to agree with it; the binding digest still holds the bytes.
  if (bundle.scene_data.appearance.id !== profileId) {
    throw new Error("character profile id does not match scene appearance");
  }
  const canonical = Buffer.from(JSON.stringify(sortJson(value)), "utf8");
  if (!bytes.equals(canonical)) {
    throw new Error("character profile artifact must use canonical UTF-8 JSON bytes");
  }
  if (sha256(canonical) !== bundle.character_profile_sha256) {
    throw new Error("character profile canonical digest does not match bundle");
  }
  return Object.freeze({ profile_id: profileId, revision });
}

function parseExactStates(
  value: unknown,
  label: string,
): DialogueSceneExpressionState[] {
  if (
    !Array.isArray(value) ||
    value.length !== DIALOGUE_SCENE_EXPRESSION_STATES.length
  ) {
    throw new Error(`${label} must contain the four locked states`);
  }
  const parsed = value.map((entry, index) =>
    expressionState(entry, `${label}[${index}]`),
  );
  if (
    parsed.some(
      (entry, index) => entry !== DIALOGUE_SCENE_EXPRESSION_STATES[index],
    )
  ) {
    throw new Error(`${label} must use the locked state order`);
  }
  return parsed;
}

function expressionState(
  value: unknown,
  label: string,
): DialogueSceneExpressionState {
  return enumValue(value, DIALOGUE_SCENE_EXPRESSION_STATES, label);
}

function strictRecord(
  value: unknown,
  requiredKeys: readonly string[],
  optionalKeys: readonly string[],
  label: string,
  allowAnyKeys = false,
): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  const record = value as Record<string, unknown>;
  if (allowAnyKeys) return record;
  const expected = new Set([...requiredKeys, ...optionalKeys]);
  const missing = requiredKeys.filter(
    (key) => !Object.prototype.hasOwnProperty.call(record, key),
  );
  const extra = Object.keys(record).filter((key) => !expected.has(key));
  if (missing.length > 0 || extra.length > 0) {
    throw new Error(
      `${label} keys must match the schema` +
        `${missing.length > 0 ? `; missing ${missing.join(", ")}` : ""}` +
        `${extra.length > 0 ? `; unexpected ${extra.join(", ")}` : ""}`,
    );
  }
  return record;
}

function strictText(
  value: unknown,
  label: string,
  maximumLength: number,
): string {
  if (
    typeof value !== "string" ||
    value.length < 1 ||
    value.length > maximumLength ||
    value !== value.trim() ||
    value.includes("\0")
  ) {
    throw new Error(
      `${label} must be trimmed text from 1 to ${maximumLength} characters`,
    );
  }
  return value;
}

function stableId(value: unknown, label: string): string {
  return kebabId(value, label, 64);
}

function kebabId(value: unknown, label: string, maximumLength: number): string {
  const parsed = strictText(value, label, maximumLength);
  if (!STABLE_ID.test(parsed))
    throw new Error(`${label} must be a stable lowercase kebab id`);
  return parsed;
}

function snakeId(value: unknown, label: string, maximumLength: number): string {
  const parsed = strictText(value, label, maximumLength);
  if (!SNAKE_ID.test(parsed))
    throw new Error(`${label} must be a stable lowercase snake id`);
  return parsed;
}

function digest(value: unknown, label: string): string {
  if (typeof value !== "string" || !SHA256.test(value)) {
    throw new Error(`${label} must be a lowercase SHA-256 digest`);
  }
  return value;
}

function nullableDigest(value: unknown, label: string): string | null {
  return value === null ? null : digest(value, label);
}

function strictInteger(
  value: unknown,
  label: string,
  minimum: number,
  maximum: number,
): number {
  if (
    typeof value !== "number" ||
    !Number.isInteger(value) ||
    value < minimum ||
    value > maximum
  ) {
    throw new Error(
      `${label} must be an integer from ${minimum} to ${maximum}`,
    );
  }
  return value;
}

function strictFiniteNumber(
  value: unknown,
  label: string,
  minimum: number,
  maximum: number,
): number {
  if (
    typeof value !== "number" ||
    !Number.isFinite(value) ||
    value < minimum ||
    value > maximum
  ) {
    throw new Error(
      `${label} must be a finite number from ${minimum} to ${maximum}`,
    );
  }
  return value;
}

function strictBoolean(value: unknown, label: string): boolean {
  if (typeof value !== "boolean") throw new Error(`${label} must be a boolean`);
  return value;
}

function exact(value: unknown, expected: string | number, label: string): void {
  if (value !== expected)
    throw new Error(`${label} must be ${JSON.stringify(expected)}`);
}

function enumValue<const T extends readonly string[]>(
  value: unknown,
  values: T,
  label: string,
): T[number] {
  if (typeof value !== "string" || !values.includes(value)) {
    throw new Error(`${label} must be one of ${values.join(", ")}`);
  }
  return value as T[number];
}

function parseJson(bytes: Buffer, label: string): unknown {
  try {
    return JSON.parse(bytes.toString("utf8")) as unknown;
  } catch {
    throw new Error(`${label} must contain valid UTF-8 JSON`);
  }
}

function canonicalJsonBytes(value: unknown): Buffer {
  return Buffer.from(`${JSON.stringify(sortJson(value))}\n`, "utf8");
}

function sortJson(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortJson);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, entry]) => [key, sortJson(entry)]),
    );
  }
  return value;
}

function sha256(bytes: Buffer): string {
  return createHash("sha256").update(bytes).digest("hex");
}

function isMissingError(error: unknown): boolean {
  return (
    error !== null &&
    typeof error === "object" &&
    "code" in error &&
    (error as { code?: unknown }).code === "ENOENT"
  );
}

function isAlreadyExistsError(error: unknown): boolean {
  return (
    error !== null &&
    typeof error === "object" &&
    "code" in error &&
    (error as { code?: unknown }).code === "EEXIST"
  );
}

import { createHash } from "node:crypto";
import {
  mkdtemp,
  mkdir,
  readFile,
  readdir,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { deflateSync } from "node:zlib";
import { afterEach, describe, expect, test } from "bun:test";
import { loadDialogueSceneFixture } from "./active-fixture";
import { dialogueSceneDemoFixture } from "./demo-fixture";
import {
  activateDialogueTheme,
  dialogueThemeStatus,
  installDialogueTheme,
  inspectPng,
  loadActiveDialogueThemeFixture,
  rollbackDialogueTheme,
} from "./theme-adapter";
import { runDialogueTheme } from "../../scripts/dialogue-theme";

const cleanupDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(
    cleanupDirectories
      .splice(0)
      .map((directory) => rm(directory, { recursive: true, force: true })),
  );
});

describe("dialogue theme web adapter", () => {
  test("runs the isolated operator workflow end to end through the command API", async () => {
    const firstSetup = await createBundle("operator-first", "local");
    const rootArgs = [
      "--state-root",
      firstSetup.options.stateRoot,
      "--public-root",
      firstSetup.options.publicRoot,
    ] as const;
    const firstInstall = (await runDialogueTheme([
      "install",
      "--bundle",
      firstSetup.bundlePath,
      ...rootArgs,
    ])) as { readonly bundle_id: string; readonly installed: boolean };
    expect(firstInstall.installed).toBeTrue();
    expect(JSON.stringify(firstInstall)).toContain('"bundle_id"');
    expect(JSON.stringify(firstInstall)).not.toContain('"bundleId"');
    expect(JSON.stringify(firstInstall)).not.toContain("directory");

    const repeatedInstall = await runDialogueTheme([
      "install",
      "--bundle",
      firstSetup.bundlePath,
      ...rootArgs,
    ]);
    expect(repeatedInstall).toMatchObject({
      bundle_id: firstInstall.bundle_id,
      installed: false,
    });
    expect(await runDialogueTheme(["status", ...rootArgs])).toMatchObject({
      mode: "committed-fallback",
      installed_bundles: 1,
    });

    await runDialogueTheme([
      "activate",
      "--bundle-id",
      firstInstall.bundle_id,
      ...rootArgs,
    ]);
    expect((await loadDialogueSceneFixture(firstSetup.options)).title).toBe(
      "Operator First",
    );

    const secondSetup = await createBundle(
      "operator-second",
      "local",
      firstSetup.root,
      firstSetup.options.stateRoot,
    );
    const secondInstall = (await runDialogueTheme([
      "install",
      "--bundle",
      secondSetup.bundlePath,
      ...rootArgs,
    ])) as { readonly bundle_id: string };
    await runDialogueTheme([
      "activate",
      "--bundle-id",
      secondInstall.bundle_id,
      ...rootArgs,
    ]);
    expect(await runDialogueTheme(["rollback", ...rootArgs])).toMatchObject({
      active: { bundle_id: firstInstall.bundle_id },
      previous: { bundle_id: secondInstall.bundle_id },
    });
    expect(await runDialogueTheme(["status", ...rootArgs])).toMatchObject({
      mode: "installed-theme",
      bundle_id: firstInstall.bundle_id,
      previous_bundle_id: secondInstall.bundle_id,
      installed_bundles: 2,
    });

    const activePath = path.join(firstSetup.options.stateRoot, "active.json");
    const active = JSON.parse(await readFile(activePath, "utf8")) as Record<
      string,
      unknown
    >;
    (active.active as Record<string, unknown>).source_bundle_sha256 = "0".repeat(64);
    await writeFile(activePath, `${JSON.stringify(active)}\n`);
    await expect(loadDialogueSceneFixture(firstSetup.options)).rejects.toThrow(
      "active bundle binding does not match immutable install",
    );
  });

  test("installs deterministically, activates explicitly, and projects the fixture", async () => {
    const setup = await createBundle("first-theme", "local");
    const first = await installDialogueTheme(setup.bundlePath, setup.options);
    const second = await installDialogueTheme(setup.bundlePath, setup.options);

    expect(first.installed).toBeTrue();
    expect(first.activation_eligible).toBeTrue();
    expect(second).toEqual({ ...first, installed: false });
    expect(first.bundle_id).toMatch(/^[a-f0-9]{64}$/);
    expect((await dialogueThemeStatus(setup.options)).mode).toBe(
      "committed-fallback",
    );

    await activateDialogueTheme(first.bundle_id, setup.options);
    const status = await dialogueThemeStatus(setup.options);
    expect(status).toEqual({
      mode: "installed-theme",
      schema_version: 3,
      kind: "dialogue-theme-status-v3",
      adapter_version: 3,
      bundle_id: first.bundle_id,
      previous_bundle_id: null,
      installed_bundles: 1,
      activation_eligible: true,
    });

    const fixture = await loadActiveDialogueThemeFixture(setup.options);
    expect(fixture?.title).toBe("First Theme");
    expect(fixture?.background.src).toBe(
      `/dialogue-scene/themes/${first.bundle_id}/assets/${setup.backgroundSha256}.png`,
    );
    expect(fixture?.expressionVariants.map((variant) => variant.state)).toEqual(
      ["neutral", "delighted", "flustered", "concerned"],
    );
  });

  test("keeps one-step rollback atomic and reversible", async () => {
    const firstSetup = await createBundle("first-theme", "local");
    const first = await installDialogueTheme(
      firstSetup.bundlePath,
      firstSetup.options,
    );
    await activateDialogueTheme(first.bundle_id, firstSetup.options);

    const secondSetup = await createBundle(
      "second-theme",
      "local",
      firstSetup.root,
      firstSetup.options.stateRoot,
    );
    const second = await installDialogueTheme(
      secondSetup.bundlePath,
      secondSetup.options,
    );
    await activateDialogueTheme(second.bundle_id, secondSetup.options);
    expect(
      (await dialogueThemeStatus(secondSetup.options)).previous_bundle_id,
    ).toBe(first.bundle_id);

    const rolledBack = await rollbackDialogueTheme(secondSetup.options);
    expect(rolledBack.active.bundle_id).toBe(first.bundle_id);
    expect(rolledBack.previous?.bundle_id).toBe(second.bundle_id);
    expect(
      (await loadActiveDialogueThemeFixture(secondSetup.options))?.title,
    ).toBe("First Theme");
  });

  test("installs pending output but fails closed on activation", async () => {
    const setup = await createBundle("pending-theme", "pending");
    const installed = await installDialogueTheme(
      setup.bundlePath,
      setup.options,
    );
    expect(installed.activation_eligible).toBeFalse();
    await expect(
      activateDialogueTheme(installed.bundle_id, setup.options),
    ).rejects.toThrow("requires review pass");
    expect((await dialogueThemeStatus(setup.options)).mode).toBe(
      "committed-fallback",
    );
  });

  test("rejects failed review, unreviewed rights, and publication authorization for local activation", async () => {
    for (const [slug, eligibility] of [
      ["failed-review", "failed-review"],
      ["unreviewed-rights", "unreviewed-rights"],
      ["publication-authorized", "publication-authorized"],
    ] as const) {
      const setup = await createBundle(slug, eligibility);
      const installed = await installDialogueTheme(
        setup.bundlePath,
        setup.options,
      );
      expect(installed.activation_eligible).toBeFalse();
      await expect(
        activateDialogueTheme(installed.bundle_id, setup.options),
      ).rejects.toThrow("local activation requires review pass");
      expect((await dialogueThemeStatus(setup.options)).mode).toBe(
        "committed-fallback",
      );
    }
  });

  test("rejects installed receipt state tampering instead of trusting approval fields", async () => {
    const setup = await createBundle("tamper-theme", "local");
    const installed = await installDialogueTheme(
      setup.bundlePath,
      setup.options,
    );
    await activateDialogueTheme(installed.bundle_id, setup.options);
    const receiptPath = path.join(
      setup.options.stateRoot,
      installed.bundle_id,
      "install-receipt.json",
    );
    const receipt = JSON.parse(await readFile(receiptPath, "utf8")) as Record<
      string,
      unknown
    >;
    receipt.publication_authorized = true;
    await writeFile(receiptPath, `${JSON.stringify(receipt)}\n`);

    await expect(loadActiveDialogueThemeFixture(setup.options)).rejects.toThrow(
      "review or rights state does not match source bundle",
    );
  });

  test("falls back only when active.json is absent and rejects a corrupt pointer", async () => {
    const root = await temporaryDirectory();
    const options = {
      stateRoot: path.join(root, "theme-state"),
      publicRoot: path.join(root, "theme-public"),
    };
    expect(await loadDialogueSceneFixture(options)).toBe(
      dialogueSceneDemoFixture,
    );

    await mkdir(options.stateRoot, { recursive: true });
    await writeFile(path.join(options.stateRoot, "active.json"), "{}\n");
    await expect(loadDialogueSceneFixture(options)).rejects.toThrow(
      "active pointer keys must match the schema",
    );
  });

  test("rejects overlapping private state and public projection roots", async () => {
    const root = await temporaryDirectory();
    await expect(
      dialogueThemeStatus({ stateRoot: root, publicRoot: path.join(root, "public") }),
    ).rejects.toThrow("must be separate non-overlapping directories");
  });

  test("rejects traversal, digest drift, invalid PNG mode, and symlinked inputs", async () => {
    const setup = await createBundle("invalid-theme", "local");
    const original = JSON.parse(
      await readFile(setup.bundlePath, "utf8"),
    ) as Record<string, unknown>;

    const traversal = structuredClone(original);
    (traversal.request as Record<string, unknown>).path = "../request.json";
    const traversalPath = path.join(setup.bundleDirectory, "traversal.json");
    await writeFile(traversalPath, JSON.stringify(traversal));
    await expect(
      installDialogueTheme(traversalPath, setup.options),
    ).rejects.toThrow("unsafe path segment");

    const drifted = structuredClone(original);
    (drifted.assets as Record<string, unknown>[])[0].sha256 = "0".repeat(64);
    const driftedPath = path.join(setup.bundleDirectory, "drifted.json");
    await writeFile(driftedPath, JSON.stringify(drifted));
    await expect(
      installDialogueTheme(driftedPath, setup.options),
    ).rejects.toThrow("digest does not match bundle");

    const wrongMode = structuredClone(original);
    (
      (wrongMode.assets as Record<string, unknown>[])[2].media as Record<
        string,
        unknown
      >
    )["alpha"] = false;
    const wrongModePath = path.join(setup.bundleDirectory, "wrong-mode.json");
    await writeFile(wrongModePath, JSON.stringify(wrongMode));
    await expect(
      installDialogueTheme(wrongModePath, setup.options),
    ).rejects.toThrow("PNG facts do not match bundle media");

    const symlinked = structuredClone(original);
    const linkPath = path.join(setup.bundleDirectory, "linked-request.json");
    await symlink(path.join(setup.bundleDirectory, "request.json"), linkPath);
    (symlinked.request as Record<string, unknown>).path = "linked-request.json";
    const symlinkedPath = path.join(setup.bundleDirectory, "symlinked.json");
    await writeFile(symlinkedPath, JSON.stringify(symlinked));
    await expect(
      installDialogueTheme(symlinkedPath, setup.options),
    ).rejects.toThrow("must not contain symlinks");

    const sourceRootLink = path.join(setup.root, "linked-bundle-root");
    await symlink(setup.bundleDirectory, sourceRootLink, "dir");
    await expect(
      installDialogueTheme(
        path.join(sourceRootLink, path.basename(setup.bundlePath)),
        setup.options,
      ),
    ).rejects.toThrow("bundle source root must be a non-symlink directory");
  });

  test("rejects PNG chunks whose image payload cannot be decoded", () => {
    const invalid = makePng(1672, 941, 2, 2, Buffer.from([0, 1, 2, 3]));
    expect(() => inspectPng(invalid)).toThrow("PNG IDAT payload is not decodable");
  });

  test("rejects request and plan provenance mutation without a bundle change", async () => {
    const requestSetup = await createBundle(
      "request-provenance-tamper",
      "local",
    );
    await writeFile(
      path.join(requestSetup.bundleDirectory, "request.json.meta.json"),
      JSON.stringify({ schema_version: 2, tampered: true }),
    );
    await expect(
      installDialogueTheme(requestSetup.bundlePath, requestSetup.options),
    ).rejects.toThrow("request-provenance digest does not match bundle");

    const planSetup = await createBundle("plan-provenance-tamper", "local");
    await writeFile(
      path.join(planSetup.bundleDirectory, "plan.json.meta.json"),
      JSON.stringify({ schema_version: 2, tampered: true }),
    );
    await expect(
      installDialogueTheme(planSetup.bundlePath, planSetup.options),
    ).rejects.toThrow("plan-provenance digest does not match bundle");
  });

  test("rejects review record, review provenance, and pending source tampering", async () => {
    const recordSetup = await createBundle("review-record-tamper", "local");
    await writeFile(
      path.join(recordSetup.bundleDirectory, "review.json"),
      JSON.stringify({ schema_version: 2, tampered: true }),
    );
    await expect(
      installDialogueTheme(recordSetup.bundlePath, recordSetup.options),
    ).rejects.toThrow("review digest does not match bundle");

    const provenanceSetup = await createBundle(
      "review-provenance-tamper",
      "local",
    );
    await writeFile(
      path.join(provenanceSetup.bundleDirectory, "review.json.meta.json"),
      JSON.stringify({ schema_version: 2, tampered: true }),
    );
    await expect(
      installDialogueTheme(provenanceSetup.bundlePath, provenanceSetup.options),
    ).rejects.toThrow("review-provenance digest does not match bundle");

    const sourceSetup = await createBundle("review-source-tamper", "local");
    const pendingSourcePath = path.join(
      sourceSetup.bundleDirectory,
      "bundle.json",
    );
    const pendingSource = JSON.parse(
      await readFile(pendingSourcePath, "utf8"),
    ) as Record<string, unknown>;
    pendingSource.tag = "tampered";
    await writeFile(pendingSourcePath, JSON.stringify(pendingSource));
    await expect(
      installDialogueTheme(sourceSetup.bundlePath, sourceSetup.options),
    ).rejects.toThrow("review-source digest does not match bundle");
  });

  test("rejects prior bundle wire and recipe versions", async () => {
    // Only one contract exists; a prior one is a different document, not an
    // older dialect the adapter should try to read.
    const priorShape = await createBundle("prior-shape", "pending");
    const shed = JSON.parse(
      await readFile(priorShape.bundlePath, "utf8"),
    ) as Record<string, unknown>;
    delete shed.game_id;
    delete shed.identity_reference;
    delete shed.identity_reference_source;
    await writeFile(priorShape.bundlePath, JSON.stringify(shed));
    await expect(
      installDialogueTheme(priorShape.bundlePath, priorShape.options),
    ).rejects.toThrow("dialogue-scene bundle v4 keys must match the schema");

    const current = await createBundle("wrong-current-recipe", "pending");
    const bundle = JSON.parse(
      await readFile(current.bundlePath, "utf8"),
    ) as Record<string, unknown>;
    bundle.recipe_version = "dialogue-scene-v4";
    await writeFile(current.bundlePath, JSON.stringify(bundle));
    await expect(
      installDialogueTheme(current.bundlePath, current.options),
    ).rejects.toThrow('bundle.recipe_version must be "dialogue-scene-v6"');
  });
  test("installs wire-v3 recipe-v4 and publishes one exact current active pointer", async () => {
    const first = await createBundle("profile-first", "local");
    const firstInstall = await installDialogueTheme(first.bundlePath, first.options);
    await activateDialogueTheme(firstInstall.bundle_id, first.options);
    const setup = await createBundle(
      "profile-v4",
      "local",
      first.root,
      first.options.stateRoot,
    );
    const installed = await installDialogueTheme(setup.bundlePath, setup.options);
    expect(installed).toMatchObject({
      schema_version: 3,
      kind: "dialogue-theme-install-result-v3",
      activation_eligible: true,
    });
    const receipt = JSON.parse(
      await readFile(
        path.join(
          setup.options.stateRoot,
          installed.bundle_id,
          "install-receipt.json",
        ),
        "utf8",
      ),
    ) as { copies: { kind: string }[]; profile_id: string; profile_revision: number };
    expect(receipt.profile_id).toBe("mio-amamiya");
    expect(receipt.profile_revision).toBe(4);
    expect(receipt.copies.map((copy) => copy.kind)).toContain("character-profile");
    const publicDirectory = path.join(
      setup.options.publicRoot,
      installed.bundle_id,
    );
    expect(await readdir(publicDirectory)).toEqual(["assets"]);
    expect((await readdir(path.join(publicDirectory, "assets"))).length).toBe(6);
    await expect(
      readFile(path.join(publicDirectory, "source-bundle.json")),
    ).rejects.toMatchObject({ code: "ENOENT" });
    await expect(
      readFile(path.join(publicDirectory, "install-receipt.json")),
    ).rejects.toMatchObject({ code: "ENOENT" });
    const persistedFixture = JSON.parse(
      await readFile(
        path.join(setup.options.stateRoot, installed.bundle_id, "fixture.json"),
        "utf8",
      ),
    );
    expect(persistedFixture).toMatchObject({
      schema_version: 1,
      kind: "dialogue-scene-theme-fixture-v1",
      profile_identity: { profile_id: "mio-amamiya", revision: 4 },
    });
    expect(JSON.stringify(persistedFixture)).not.toContain("profileIdentity");
    expect(JSON.stringify(persistedFixture)).not.toContain("schemaVersion");
    const activated = await activateDialogueTheme(installed.bundle_id, setup.options);
    expect(activated.schema_version).toBe(3);
    expect(await dialogueThemeStatus(setup.options)).toMatchObject({
      schema_version: 3,
      kind: "dialogue-theme-status-v3",
      bundle_id: installed.bundle_id,
      previous_bundle_id: firstInstall.bundle_id,
    });
    expect((await loadActiveDialogueThemeFixture(setup.options))?.profileIdentity).toEqual({
      profileId: "mio-amamiya",
      revision: 4,
    });
    const active = JSON.parse(
      await readFile(path.join(setup.options.stateRoot, "active.json"), "utf8"),
    );
    expect(active).toMatchObject({
      schema_version: 3,
      kind: "dialogue-theme-active-v3",
      adapter_version: 3,
      active: { bundle_id: installed.bundle_id },
      previous: { bundle_id: firstInstall.bundle_id },
    });
    expect(JSON.stringify(active)).not.toContain("migration");
    await rollbackDialogueTheme(setup.options);
    expect((await dialogueThemeStatus(setup.options)).bundle_id).toBe(
      firstInstall.bundle_id,
    );
  });

  test("rejects profile tampering and corrupt current active state", async () => {
    const camel = await createBundle(
      "profile-camel-v4",
      "local",
    );
    const camelBundle = JSON.parse(await readFile(camel.bundlePath, "utf8")) as Record<string, unknown>;
    const camelBinding = camelBundle.character_profile_binding as Record<string, unknown>;
    camelBinding.sourceSha256 = camelBinding.source_sha256;
    delete camelBinding.source_sha256;
    const camelPath = path.join(camel.bundleDirectory, "bundle.camel.json");
    await writeFile(camelPath, JSON.stringify(camelBundle));
    await expect(installDialogueTheme(camelPath, camel.options)).rejects.toThrow(
      "bundle.character_profile_binding keys must match the schema",
    );

    const profileTamper = await createBundle(
      "profile-tamper-v4",
      "local",
    );
    await writeFile(
      path.join(profileTamper.bundleDirectory, "character-profile.json"),
      JSON.stringify({ schema_version: 1, kind: "character-profile-v1" }),
    );
    await expect(
      installDialogueTheme(profileTamper.bundlePath, profileTamper.options),
    ).rejects.toThrow("character-profile digest does not match bundle");

    const setup = await createBundle(
      "partial-state-v4",
      "local",
    );
    const installed = await installDialogueTheme(setup.bundlePath, setup.options);
    await activateDialogueTheme(installed.bundle_id, setup.options);
    const activePath = path.join(setup.options.stateRoot, "active.json");
    const active = JSON.parse(await readFile(activePath, "utf8")) as Record<
      string,
      unknown
    >;
    delete (active.active as Record<string, unknown>).install_receipt_sha256;
    await writeFile(activePath, JSON.stringify(active));
    await expect(dialogueThemeStatus(setup.options)).rejects.toThrow(
      "active pointer active keys must match the schema",
    );
  });

  test("rejects unknown recipe versions and missing or tampered current style bindings", async () => {
    const unknown = await createBundle("unknown-version", "pending");
    const unknownBundle = JSON.parse(
      await readFile(unknown.bundlePath, "utf8"),
    ) as Record<string, unknown>;
    unknownBundle.recipe_version = "dialogue-scene-v5";
    await writeFile(unknown.bundlePath, JSON.stringify(unknownBundle));
    await expect(
      installDialogueTheme(unknown.bundlePath, unknown.options),
    ).rejects.toThrow('bundle.recipe_version must be "dialogue-scene-v6"');

    const missing = await createBundle("missing-style-binding", "pending");
    const missingBundle = JSON.parse(
      await readFile(missing.bundlePath, "utf8"),
    ) as Record<string, unknown>;
    const planProvenancePath = path.join(
      missing.bundleDirectory,
      "plan.json.meta.json",
    );
    const planProvenance = JSON.parse(
      await readFile(planProvenancePath, "utf8"),
    ) as Record<string, unknown>;
    const metadata = ((planProvenance.params as Record<string, unknown>)
      .metadata ?? {}) as Record<string, unknown>;
    delete metadata.style_resource_sha256;
    const changedPlanProvenance = Buffer.from(JSON.stringify(planProvenance));
    await writeFile(planProvenancePath, changedPlanProvenance);
    (missingBundle.plan as Record<string, unknown>).provenance_sha256 = sha256(
      changedPlanProvenance,
    );
    await writeFile(missing.bundlePath, JSON.stringify(missingBundle));
    await expect(
      installDialogueTheme(missing.bundlePath, missing.options),
    ).rejects.toThrow("style_resource_sha256");

    const anchorTamper = await createBundle("style-anchor-tamper", "pending");
    await writeFile(
      path.join(anchorTamper.bundleDirectory, "style-anchor.json"),
      JSON.stringify({ schema_version: 1, tampered: true }),
    );
    await expect(
      installDialogueTheme(anchorTamper.bundlePath, anchorTamper.options),
    ).rejects.toThrow("style-anchor digest does not match bundle");

    const provenanceTamper = await createBundle(
      "bundle-style-binding-tamper",
      "pending",
    );
    const bundleProvenancePath = path.join(
      provenanceTamper.bundleDirectory,
      "bundle.json.meta.json",
    );
    const bundleProvenance = JSON.parse(
      await readFile(bundleProvenancePath, "utf8"),
    ) as Record<string, unknown>;
    (bundleProvenance.params as Record<string, unknown>).style_resource_sha256 =
      "9".repeat(64);
    await writeFile(bundleProvenancePath, JSON.stringify(bundleProvenance));
    await expect(
      installDialogueTheme(
        provenanceTamper.bundlePath,
        provenanceTamper.options,
      ),
    ).rejects.toThrow(
      "plan and bundle provenance style bindings must match exactly",
    );
  });

  test("rejects camelCase in top-level and nested portable bundle fields", async () => {
    const setup = await createBundle("camel-bundle", "local");
    const original = JSON.parse(
      await readFile(setup.bundlePath, "utf8"),
    ) as Record<string, unknown>;

    const topLevel = structuredClone(original);
    topLevel.schemaVersion = topLevel.schema_version;
    delete topLevel.schema_version;
    const topLevelPath = path.join(
      setup.bundleDirectory,
      "camel-top-level.json",
    );
    await writeFile(topLevelPath, JSON.stringify(topLevel));
    await expect(
      installDialogueTheme(topLevelPath, setup.options),
    ).rejects.toThrow("dialogue-scene bundle v4 keys must match the schema");

    const nested = structuredClone(original);
    const scene = nested.scene_data as Record<string, unknown>;
    scene.sceneLabel = scene.scene_label;
    delete scene.scene_label;
    const nestedPath = path.join(setup.bundleDirectory, "camel-nested.json");
    await writeFile(nestedPath, JSON.stringify(nested));
    await expect(
      installDialogueTheme(nestedPath, setup.options),
    ).rejects.toThrow("bundle.scene_data keys must match the schema");

    const prior = structuredClone(original);
    prior.schema_version = 1;
    prior.kind = "dialogue-scene-bundle-v1";
    const priorPath = path.join(setup.bundleDirectory, "prior-v1.json");
    await writeFile(priorPath, JSON.stringify(prior));
    await expect(
      installDialogueTheme(priorPath, setup.options),
    ).rejects.toThrow("bundle.schema_version must be 4");
  });

  test("requires current request and plan envelopes and rejects bound camelCase", async () => {
    const requestSetup = await createBundle("camel-request", "local");
    const requestBundle = JSON.parse(
      await readFile(requestSetup.bundlePath, "utf8"),
    ) as Record<string, unknown>;
    const requestPath = path.join(requestSetup.bundleDirectory, "request.json");
    const request = JSON.parse(await readFile(requestPath, "utf8")) as Record<
      string,
      unknown
    >;
    request.schemaVersion = request.schema_version;
    delete request.schema_version;
    const requestBytes = Buffer.from(JSON.stringify(request));
    await writeFile(requestPath, requestBytes);
    (requestBundle.request as Record<string, unknown>).sha256 =
      sha256(requestBytes);
    await writeFile(requestSetup.bundlePath, JSON.stringify(requestBundle));
    await expect(
      installDialogueTheme(requestSetup.bundlePath, requestSetup.options),
    ).rejects.toThrow("request key must be lower_snake_case: schemaVersion");

    const planSetup = await createBundle("camel-plan", "local");
    const planBundle = JSON.parse(
      await readFile(planSetup.bundlePath, "utf8"),
    ) as Record<string, unknown>;
    const planPath = path.join(planSetup.bundleDirectory, "plan.json");
    const plan = JSON.parse(await readFile(planPath, "utf8")) as Record<
      string,
      unknown
    >;
    plan.recipeVersion = plan.recipe_version;
    delete plan.recipe_version;
    const planBytes = Buffer.from(JSON.stringify(plan));
    await writeFile(planPath, planBytes);
    (planBundle.plan as Record<string, unknown>).sha256 = sha256(planBytes);
    await writeFile(planSetup.bundlePath, JSON.stringify(planBundle));
    await expect(
      installDialogueTheme(planSetup.bundlePath, planSetup.options),
    ).rejects.toThrow("plan key must be lower_snake_case: recipeVersion");
  });

  test("requires every exact current request field and rejects nested extensions", async () => {
    const unknown = await createBundle("request-unknown", "pending");
    await rewriteBoundRecord(unknown, "request", (record) => {
      record.legacy_mode = true;
    });
    await expect(
      installDialogueTheme(unknown.bundlePath, unknown.options),
    ).rejects.toThrow("bundle request keys must match the schema");

    const missing = await createBundle("request-missing", "pending");
    await rewriteBoundRecord(missing, "request", (record) => {
      delete record.scene_brief;
    });
    await expect(
      installDialogueTheme(missing.bundlePath, missing.options),
    ).rejects.toThrow("missing scene_brief");

    const nested = await createBundle("request-nested", "pending");
    await rewriteBoundRecord(nested, "request", (record) => {
      (record.background as Record<string, unknown>).legacy_ref = "old.png";
    });
    await expect(
      installDialogueTheme(nested.bundlePath, nested.options),
    ).rejects.toThrow("bundle request background keys must match the schema");
  });

  test("requires every exact current plan field and rejects nested drift", async () => {
    const unknown = await createBundle("plan-unknown", "pending");
    await rewriteBoundRecord(unknown, "plan", (record) => {
      record.legacy_mode = true;
    });
    await expect(
      installDialogueTheme(unknown.bundlePath, unknown.options),
    ).rejects.toThrow("bundle plan keys must match the schema");

    const missing = await createBundle("plan-missing", "pending");
    await rewriteBoundRecord(missing, "plan", (record) => {
      delete record.geometry;
    });
    await expect(
      installDialogueTheme(missing.bundlePath, missing.options),
    ).rejects.toThrow("missing geometry");

    const nested = await createBundle("plan-nested", "pending");
    await rewriteBoundRecord(nested, "plan", (record) => {
      const geometry = record.geometry as Record<string, unknown>;
      const canvas = geometry.canvas as Record<string, unknown>;
      canvas.width = 2048;
    });
    await expect(
      installDialogueTheme(nested.bundlePath, nested.options),
    ).rejects.toThrow("bundle plan geometry canvas width must be 1024");
  });

  test("rejects camelCase and prior-version adapter state", async () => {
    const setup = await createBundle("camel-state", "local");
    const installed = await installDialogueTheme(
      setup.bundlePath,
      setup.options,
    );
    await activateDialogueTheme(installed.bundle_id, setup.options);

    const activePath = path.join(setup.options.stateRoot, "active.json");
    const active = JSON.parse(await readFile(activePath, "utf8")) as Record<
      string,
      unknown
    >;
    const validCurrentPointer = structuredClone(active);
    const activeBinding = active.active as Record<string, unknown>;
    activeBinding.bundleId = activeBinding.bundle_id;
    delete activeBinding.bundle_id;
    await writeFile(activePath, `${JSON.stringify(active)}\n`);
    await expect(loadDialogueSceneFixture(setup.options)).rejects.toThrow(
      "active pointer active keys must match the schema",
    );

    const priorPointer = {
      schema_version: 2,
      kind: "dialogue-theme-active-v2",
      adapter_version: 2,
      bundle_id: installed.bundle_id,
      previous_bundle_id: null,
      source_bundle_sha256: sha256(await readFile(setup.bundlePath)),
    };
    await writeFile(activePath, `${JSON.stringify(priorPointer)}\n`);
    await expect(loadDialogueSceneFixture(setup.options)).rejects.toThrow(
      "active pointer keys must match the schema",
    );

    await writeFile(activePath, `${JSON.stringify(validCurrentPointer)}\n`);
    const receiptPath = path.join(
      setup.options.stateRoot,
      installed.bundle_id,
      "install-receipt.json",
    );
    const receipt = JSON.parse(await readFile(receiptPath, "utf8")) as Record<
      string,
      unknown
    >;
    const validCurrentReceipt = structuredClone(receipt);
    receipt.bundleId = receipt.bundle_id;
    delete receipt.bundle_id;
    await writeFile(receiptPath, `${JSON.stringify(receipt)}\n`);
    await expect(loadDialogueSceneFixture(setup.options)).rejects.toThrow(
      "install receipt keys must match the schema",
    );

    await writeFile(
      receiptPath,
      `${JSON.stringify({
        ...validCurrentReceipt,
        schema_version: 2,
        kind: "dialogue-theme-install-v2",
        adapter_version: 2,
      })}\n`,
    );
    await expect(loadDialogueSceneFixture(setup.options)).rejects.toThrow(
      "install receipt schema_version must be 3",
    );
  });
});

async function createBundle(
  slug: string,
  eligibility:
    | "local"
    | "pending"
    | "failed-review"
    | "unreviewed-rights"
    | "publication-authorized",
  existingRoot?: string,
  existingStateRoot?: string,
): Promise<{
  readonly root: string;
  readonly bundleDirectory: string;
  readonly bundlePath: string;
  readonly backgroundSha256: string;
  readonly options: { readonly stateRoot: string; readonly publicRoot: string };
}> {
  const root = existingRoot ?? (await temporaryDirectory());
  const bundleDirectory = path.join(root, slug);
  const stateRoot = existingStateRoot ?? path.join(root, "theme-state");
  const publicRoot = path.join(root, "theme-public");
  await mkdir(path.join(bundleDirectory, "assets"), { recursive: true });

  const profileSourceSha256 = "b".repeat(64);
  const profileBinding = {
    schema_version: 1,
    kind: "character-profile-binding-v1",
    ref: "character.toml",
    source_sha256: profileSourceSha256,
  };
  const identityReferenceSource = "references/cover.png";
  const identityReferenceSha256 = "c".repeat(64);
  const request = Buffer.from(
    JSON.stringify({
      schema_version: 1,
      kind: "dialogue-scene-v2",
      game_id: "seminar_hall",
      display_name: "Seminar Hall",
      revision: 1,
      scene_brief: "Researchers meet after an evening seminar.",
      identity_reference_id: "cover",
      character_profile: profileBinding,
      references: [
        {
          reference_id: "cover",
          source: identityReferenceSource,
          source_sha256: identityReferenceSha256,
          rights_status: "unreviewed",
          rights_basis: ["Original brand-neutral test fixture."],
        },
      ],
      background: { description: "Evening study lounge" },
      dialogue: [
        {
          id: "opening",
          speaker: "Mio",
          text: "I hoped you would stay after the seminar.",
          expression_state: "neutral",
        },
      ],
      presentation: {
        slot: "right",
        framing_zoom: 70,
        source_framing_zoom: 70,
      },
      transparency_mode: "ai",
    }),
  );
  const requestProvenance = Buffer.from(
    JSON.stringify({
      schema_version: 2,
      slug,
      artifact: { sha256: sha256(request) },
    }),
  );
  const styleAnchor = {
    schema_version: 1,
    kind: "canonical_style_anchor_v1",
    style_mode: "cel_shaded_anime_2d",
    medium_keyword: "clean 2D Japanese anime illustration",
    observable_traits: [
      "crisp inked linework",
      "flat cel-shaded color regions",
    ],
    asset_treatments: {
      concept_art: "polished 2D character and world concept art",
      character_sprite: "visual novel character sprite",
      environment_background: "visual novel background art",
      illustration: "finished 2D key illustration",
      asset_sheet: "production-ready 2D game asset sheet",
      tileable_texture: "seamless 2D game texture",
      interface_art: "clean 2D game interface art",
      effect_sheet: "readable 2D game effect sheet",
    },
    exclusions: ["photorealistic rendering", "3D rendering"],
    skill_sha256: "1".repeat(64),
    vocabulary_sha256: "2".repeat(64),
    resource_sha256: "3".repeat(64),
    compiler_sha256: "4".repeat(64),
    compiler_version: 1,
  };
  const styleAnchorBytes = Buffer.from(JSON.stringify(styleAnchor));
  const styleAnchorProvenance = Buffer.from(
    JSON.stringify({
      schema_version: 2,
      artifact: { sha256: sha256(styleAnchorBytes) },
    }),
  );
  const styleBinding = {
    style_anchor_path: "style-anchor.json",
    style_anchor_artifact_sha256: sha256(styleAnchorBytes),
    style_anchor_provenance_path: "style-anchor.json.meta.json",
    style_anchor_provenance_sha256: sha256(styleAnchorProvenance),
    style_anchor_sha256: canonicalSha256(styleAnchor),
    style_compiler_sha256: styleAnchor.compiler_sha256,
    style_compiler_version: styleAnchor.compiler_version,
    style_resource_sha256: styleAnchor.resource_sha256,
    style_skill_sha256: styleAnchor.skill_sha256,
    style_vocabulary_sha256: styleAnchor.vocabulary_sha256,
  };
  const characterProfile = {
    schema_version: 1,
    kind: "character-profile-v1",
    profile_id: "mio-amamiya",
    revision: 4,
    display_name: "Mio Amamiya",
    age_years: 23,
    description: "An adult graduate astronomy researcher.",
    visual_identity: "Adult woman with an indigo bob and star hairpin.",
    wardrobe: "Contemporary adult evening wear.",
    invariants: ["Indigo bob", "Star hairpin"],
    rights: {
      status: "restricted",
      notice: "Local demo only.",
      attribution: [],
      basis: ["Original test fixture."],
      reviewed_at: "2026-08-20T12:00:00Z",
    },
    references: [],
  };
  const characterProfileBytes = Buffer.from(
    JSON.stringify(sortJson(characterProfile)),
  );
  const characterProfileProvenance = Buffer.from(
    JSON.stringify({
      schema_version: 2,
      artifact: { sha256: sha256(characterProfileBytes) },
    }),
  );
  const plan = Buffer.from(
    JSON.stringify({
      schema_version: 4,
      kind: "dialogue-scene-plan-v5",
      recipe_version: "dialogue-scene-v6",
      policy_version: "coming-of-age-nonexplicit-v3",
      expression_profile: "expression-core-v3",
      ...{
            request_sha256: sha256(request),
            appearance_id: "mio-amamiya",
            character_profile_ref: profileBinding.ref,
            character_profile_source_sha256: profileBinding.source_sha256,
            character_profile_sha256: sha256(characterProfileBytes),
            identity_reference_sha256: identityReferenceSha256,
            shared_locks: {
              identity: "Adult woman with an indigo bob and star hairpin",
              wardrobe: "Contemporary adult evening wear",
              pose: "Consistent upright visual-novel pose",
              lighting: "Soft evening study-lounge lighting",
              style: "Polished 2D anime visual-novel character art",
            },
            geometry: {
              canvas: { width: 1024, height: 1536 },
              crop: "top-hair-through-waist",
              slot: "right",
              safe_bounds: [0, 0, 1, 1],
            },
            states: [
              { id: "neutral", direction: "composed and attentive" },
              { id: "delighted", direction: "warm and delighted" },
              { id: "flustered", direction: "warmly flustered" },
              { id: "concerned", direction: "focused concern" },
            ],
            prompt_templates: [
              { id: "profile-neutral-v1", sha256: "5".repeat(64) },
              { id: "profile-expression-edit-v1", sha256: "5".repeat(64) },
            ],
          },
    }),
  );
  const planProvenance = Buffer.from(
    JSON.stringify({
      schema_version: 2,
      slug,
      artifact: { sha256: sha256(plan) },
      params: {
        metadata: {
          stage: "scene-plan",
          request_sha256: sha256(request),
          ...styleBinding,
          character_profile_ref: profileBinding.ref,
          character_profile_source_sha256: profileBinding.source_sha256,
          character_profile_path: "character-profile.json",
          character_profile_sha256: sha256(characterProfileBytes),
          character_profile_provenance_path: "character-profile.json.meta.json",
          character_profile_provenance_sha256: sha256(characterProfileProvenance),
        },
        schema: {
          $defs: {
            scene_plan: {
              additionalProperties: false,
              properties: {
                scene_label: { type: "string", minLength: 1, maxLength: 80 },
              },
              required: ["scene_label"],
              type: "object",
            },
          },
          $ref: "#/$defs/scene_plan",
        },
      },
    }),
  );
  const attempts = Buffer.from(
    JSON.stringify({
      schema_version: 2,
      kind: "dialogue-attempt-ledger-v2",
      attempts: [],
    }),
  );
  await writeFile(path.join(bundleDirectory, "request.json"), request);
  await writeFile(
    path.join(bundleDirectory, "request.json.meta.json"),
    requestProvenance,
  );
  await writeFile(path.join(bundleDirectory, "plan.json"), plan);
  await writeFile(
    path.join(bundleDirectory, "plan.json.meta.json"),
    planProvenance,
  );
  await writeFile(
    path.join(bundleDirectory, "style-anchor.json"),
    styleAnchorBytes,
  );
  await writeFile(
    path.join(bundleDirectory, "style-anchor.json.meta.json"),
    styleAnchorProvenance,
  );
  await writeFile(
    path.join(bundleDirectory, "character-profile.json"),
    characterProfileBytes,
  );
  await writeFile(
    path.join(bundleDirectory, "character-profile.json.meta.json"),
    characterProfileProvenance,
  );
  await writeFile(path.join(bundleDirectory, "attempts.json"), attempts);

  const assetSpecs = [
    {
      id: "concept",
      role: "concept",
      state: null,
      width: 1024,
      height: 1536,
      colorType: 2,
      marker: 1,
    },
    {
      id: "background",
      role: "background",
      state: null,
      width: 1672,
      height: 941,
      colorType: 2,
      marker: 2,
    },
    {
      id: "expression-neutral",
      role: "expression",
      state: "neutral",
      width: 1024,
      height: 1536,
      colorType: 6,
      marker: 3,
    },
    {
      id: "expression-delighted",
      role: "expression",
      state: "delighted",
      width: 1024,
      height: 1536,
      colorType: 6,
      marker: 4,
    },
    {
      id: "expression-flustered",
      role: "expression",
      state: "flustered",
      width: 1024,
      height: 1536,
      colorType: 6,
      marker: 5,
    },
    {
      id: "expression-concerned",
      role: "expression",
      state: "concerned",
      width: 1024,
      height: 1536,
      colorType: 6,
      marker: 6,
    },
  ] as const;
  const assets = [];
  for (const spec of assetSpecs) {
    const bytes = makePng(spec.width, spec.height, spec.colorType, spec.marker);
    const assetPath = `assets/${spec.id}.png`;
    const provenancePath = `assets/${spec.id}.png.meta.json`;
    const provenance = Buffer.from(
      JSON.stringify({
        schema_version: 2,
        id: spec.id,
        selected_attempt: 0,
        artifact: { sha256: sha256(bytes) },
      }),
    );
    await writeFile(path.join(bundleDirectory, assetPath), bytes);
    await writeFile(path.join(bundleDirectory, provenancePath), provenance);
    assets.push({
      id: spec.id,
      role: spec.role,
      ...(spec.state === null ? {} : { state: spec.state }),
      path: assetPath,
      sha256: sha256(bytes),
      bytes: bytes.byteLength,
      media: {
        mime_type: "image/png",
        width: spec.width,
        height: spec.height,
        alpha: spec.colorType === 6,
      },
      provenance_path: provenancePath,
      provenance_sha256: sha256(provenance),
      selected_attempt: 0,
    });
  }

  const bundle = {
    schema_version: 4,
    kind: "dialogue-scene-bundle-v5",
    recipe: "dialogue-scene",
    recipe_version: "dialogue-scene-v6",
    tag: slug,
    game_id: "seminar_hall",
    run_identity_sha256: sha256(Buffer.from(`run:${slug}`)),
    request: {
      path: "request.json",
      sha256: sha256(request),
      provenance_path: "request.json.meta.json",
      provenance_sha256: sha256(requestProvenance),
    },
    plan: {
      path: "plan.json",
      sha256: sha256(plan),
      provenance_path: "plan.json.meta.json",
      provenance_sha256: sha256(planProvenance),
    },
    character_profile: {
      path: "character-profile.json",
      sha256: sha256(characterProfileBytes),
      provenance_path: "character-profile.json.meta.json",
      provenance_sha256: sha256(characterProfileProvenance),
    },
    character_profile_binding: profileBinding,
    character_profile_sha256: sha256(characterProfileBytes),
    identity_reference: {
      path: "assets/concept.png",
      sha256: identityReferenceSha256,
      provenance_path: "assets/concept.png.meta.json",
      provenance_sha256: "d".repeat(64),
    },
    identity_reference_source: identityReferenceSource,
    assets,
    scene_data: {
      scene_id: slug,
      title: titleCase(slug),
      scene_label: "Adult graduate study lounge after an evening seminar",
      concept_asset_id: "concept",
      background: {
        asset_id: "background",
        alt: "An adult university study lounge",
      },
      appearance: {
        id: "mio-amamiya",
        label: "Mio Amamiya",
        age: 23,
        role: "Graduate astronomy researcher",
        tagline: "A confident invitation after the seminar.",
        description:
          "An adult researcher meeting another adult after a seminar.",
        visual_identity: "Adult woman with an indigo bob and star hairpin",
        art_direction: "Polished 2D anime visual-novel character art",
      },
      placement: { slot: "right", framing_zoom: 70, source_framing_zoom: 70 },
      available_states: ["neutral", "delighted", "flustered", "concerned"],
      expression_variants: [
        {
          id: "mio-neutral",
          asset_id: "expression-neutral",
          appearance_id: "mio-amamiya",
          state: "neutral",
          label: "Composed",
          description: "composed and attentive",
          alt: "Mio looking composed",
          slot: "right",
        },
        {
          id: "mio-delighted",
          asset_id: "expression-delighted",
          appearance_id: "mio-amamiya",
          state: "delighted",
          label: "Delighted",
          description: "warm and delighted",
          alt: "Mio looking delighted",
          slot: "right",
        },
        {
          id: "mio-flustered",
          asset_id: "expression-flustered",
          appearance_id: "mio-amamiya",
          state: "flustered",
          label: "Flustered",
          description: "warmly flustered",
          alt: "Mio looking flustered",
          slot: "right",
        },
        {
          id: "mio-concerned",
          asset_id: "expression-concerned",
          appearance_id: "mio-amamiya",
          state: "concerned",
          label: "Concerned",
          description: "focused concern",
          alt: "Mio looking concerned",
          slot: "right",
        },
      ],
      dialogue: [
        {
          id: "opening",
          speaker: "Mio",
          text: "I hoped you would stay after the seminar.",
          expression_state: "neutral",
        },
      ],
    },
    attempt_ledger: { path: "attempts.json", sha256: sha256(attempts) },
    review: { status: "pending" },
    rights: {
      aggregate: "unreviewed",
      publication_authorized: false,
    },
  };
  const pendingBundleBytes = Buffer.from(JSON.stringify(bundle));
  await writeFile(
    path.join(bundleDirectory, "bundle.json"),
    pendingBundleBytes,
  );
  await writeFile(
    path.join(bundleDirectory, "bundle.json.meta.json"),
    JSON.stringify({
      schema_version: 2,
      artifact: { sha256: sha256(pendingBundleBytes) },
      refs: [
        "request.json",
        "plan.json",
        "attempts.json",
        "style-anchor.json",
        "style-anchor.json.meta.json",
        "character-profile.json",
        "character-profile.json.meta.json",
      ],
      params: {
        run_identity_sha256: bundle.run_identity_sha256,
        selected_assets: 6,
        ...styleBinding,
        character_profile_ref: profileBinding.ref,
        character_profile_source_sha256: profileBinding.source_sha256,
        character_profile_path: "character-profile.json",
        character_profile_sha256: sha256(characterProfileBytes),
        character_profile_provenance_path: "character-profile.json.meta.json",
        character_profile_provenance_sha256: sha256(characterProfileProvenance),
      },
    }),
  );
  let bundlePath = path.join(bundleDirectory, "bundle.json");
  if (eligibility !== "pending") {
    const status = eligibility === "failed-review" ? "fail" : "pass";
    const reviewBytes = Buffer.from(
      JSON.stringify({
        schema_version: 4,
        kind: "dialogue-scene-review-v5",
        status,
        usage: "local-demo",
        source_bundle_sha256: sha256(pendingBundleBytes),
        acceptance_spec_sha256: "a".repeat(64),
        character_profile_source_sha256: profileBinding.source_sha256,
        character_profile_sha256: sha256(characterProfileBytes),
        independent_reviewer: true,
        asset_sha256: assets.map((asset) => asset.sha256),
        publication_authorized: false,
        reviewed_at: "2026-08-20T12:00:00Z",
      }),
    );
    const reviewProvenance = Buffer.from(
      JSON.stringify({
        schema_version: 2,
        artifact: { sha256: sha256(reviewBytes) },
        refs: ["bundle.json", "character-profile.json"],
        params: {
          source_bundle_sha256: sha256(pendingBundleBytes),
          character_profile_ref: profileBinding.ref,
          character_profile_source_sha256: profileBinding.source_sha256,
          character_profile_sha256: sha256(characterProfileBytes),
        },
      }),
    );
    await writeFile(path.join(bundleDirectory, "review.json"), reviewBytes);
    await writeFile(
      path.join(bundleDirectory, "review.json.meta.json"),
      reviewProvenance,
    );
    const reviewedBundle = {
      ...bundle,
      review: {
        status,
        path: "review.json",
        sha256: sha256(reviewBytes),
        provenance_path: "review.json.meta.json",
        provenance_sha256: sha256(reviewProvenance),
      },
      rights: {
        aggregate:
          eligibility === "local" || eligibility === "failed-review"
            ? "restricted"
            : eligibility === "publication-authorized"
              ? "redistribution-approved"
              : "unreviewed",
        publication_authorized: eligibility === "publication-authorized",
      },
    };
    bundlePath = path.join(bundleDirectory, "bundle.reviewed.json");
    await writeFile(bundlePath, JSON.stringify(reviewedBundle));
  }
  return {
    root,
    bundleDirectory,
    bundlePath,
    backgroundSha256: assets[1].sha256,
    options: { stateRoot, publicRoot },
  };
}

async function rewriteBoundRecord(
  setup: {
    readonly bundleDirectory: string;
    readonly bundlePath: string;
  },
  kind: "request" | "plan",
  mutate: (record: Record<string, unknown>) => void,
): Promise<void> {
  if (path.basename(setup.bundlePath) !== "bundle.json") {
    throw new Error("rewriteBoundRecord requires a pending source bundle");
  }
  const recordPath = path.join(setup.bundleDirectory, `${kind}.json`);
  const record = JSON.parse(await readFile(recordPath, "utf8")) as Record<
    string,
    unknown
  >;
  mutate(record);
  const recordBytes = Buffer.from(JSON.stringify(record));
  await writeFile(recordPath, recordBytes);

  const provenancePath = `${recordPath}.meta.json`;
  const provenance = JSON.parse(
    await readFile(provenancePath, "utf8"),
  ) as Record<string, unknown>;
  (provenance.artifact as Record<string, unknown>).sha256 = sha256(recordBytes);
  const provenanceBytes = Buffer.from(JSON.stringify(provenance));
  await writeFile(provenancePath, provenanceBytes);

  const bundle = JSON.parse(
    await readFile(setup.bundlePath, "utf8"),
  ) as Record<string, unknown>;
  const binding = bundle[kind] as Record<string, unknown>;
  binding.sha256 = sha256(recordBytes);
  binding.provenance_sha256 = sha256(provenanceBytes);
  const bundleBytes = Buffer.from(JSON.stringify(bundle));
  await writeFile(setup.bundlePath, bundleBytes);

  const bundleProvenancePath = path.join(
    setup.bundleDirectory,
    "bundle.json.meta.json",
  );
  const bundleProvenance = JSON.parse(
    await readFile(bundleProvenancePath, "utf8"),
  ) as Record<string, unknown>;
  (bundleProvenance.artifact as Record<string, unknown>).sha256 =
    sha256(bundleBytes);
  await writeFile(bundleProvenancePath, JSON.stringify(bundleProvenance));
}

async function temporaryDirectory(): Promise<string> {
  const directory = await mkdtemp(
    path.join(tmpdir(), "stage-gen-dialogue-theme-"),
  );
  cleanupDirectories.push(directory);
  return directory;
}

function makePng(
  width: number,
  height: number,
  colorType: 2 | 6,
  marker: number,
  idatOverride?: Buffer,
): Buffer {
  const channels = colorType === 6 ? 4 : 3;
  const scanlines = Buffer.alloc((width * channels + 1) * height);
  scanlines[1] = marker;
  if (colorType === 6) scanlines[4] = 255;
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0);
  header.writeUInt32BE(height, 4);
  header[8] = 8;
  header[9] = colorType;
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    pngChunk("IHDR", header),
    pngChunk("IDAT", idatOverride ?? deflateSync(scanlines)),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
}

function pngChunk(type: string, data: Buffer): Buffer {
  const typeBytes = Buffer.from(type, "ascii");
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.byteLength);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([typeBytes, data])));
  return Buffer.concat([length, typeBytes, data, crc]);
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

function sha256(bytes: Buffer): string {
  return createHash("sha256").update(bytes).digest("hex");
}

function canonicalSha256(value: unknown): string {
  return sha256(Buffer.from(JSON.stringify(sortJson(value))));
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

function titleCase(value: string): string {
  return value
    .split("-")
    .map((part) => `${part[0].toUpperCase()}${part.slice(1)}`)
    .join(" ");
}

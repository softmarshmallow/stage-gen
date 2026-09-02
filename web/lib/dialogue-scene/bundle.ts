// Read one run's `bundle.json` and project it into the fixture a scene plays.
//
// This is the whole consumer side of `dialogue-scene-bundle-v7`. It replaces the
// bundle reader that used to live inside the theme installer: that module existed
// to copy a reviewed bundle into a public directory for a DOM preview route, and
// both the route and the directory are gone. What survives is the part that was
// never about installing anything - turning a run into something playable.
//
// Strict on purpose. A bundle whose keys do not match is refused rather than
// read leniently, because the run it describes is digest-bound and a consumer
// that guessed would be guessing about bytes somebody signed for.

import {
  validateDialogueSceneFixture,
  type DialogueSceneFixture,
} from "./schema";
import type { UiAtlasRoleLayout, UiAtlasRoleName } from "@/lib/manifest/ui-atlas-layout";
import { parseUiAtlasRoleLayout } from "@/lib/manifest/ui-atlas-layout";
import type { UiIconSetLayout } from "@/lib/manifest/ui-icon-layout";
import { parseUiIconSetLayout } from "@/lib/manifest/ui-icon-layout";
import { serializeScenarioProgram, type ScenarioProgram } from "@/lib/scenario/program";
import { parseScenarioProgram } from "@/lib/scenario/program";

export const DIALOGUE_SCENE_BUNDLE_KIND = "dialogue-scene-bundle-v7" as const;
export const DIALOGUE_SCENE_RECIPE_VERSION = "dialogue-scene-v7" as const;

export interface DialogueSceneBundleAsset {
  readonly id: string;
  readonly role: "style" | "background" | "expression" | "track" | "ui";
  readonly actorId: string | null;
  readonly state: string | null;
  readonly trackId: string | null;
  readonly path: string;
  readonly sha256: string;
}

export interface DialogueSceneBundle {
  readonly tag: string;
  readonly gameId: string;
  readonly assets: readonly DialogueSceneBundleAsset[];
  readonly sceneData: SceneData;
}

/** One generated nine-slice role the scene draws its panels and buttons from. */
interface SceneUiRole extends UiAtlasRoleLayout {
  readonly asset_id: string;
}

interface SceneStage {
  readonly stage_id: string;
  readonly asset_id: string;
  readonly alt: string;
}

interface SceneExpressionVariant {
  readonly id: string;
  readonly asset_id: string;
  readonly state: string;
  readonly label: string;
  readonly description: string;
  readonly alt: string;
}

interface SceneActor {
  readonly actor_id: string;
  readonly appearance: {
    readonly id: string;
    readonly label: string;
    readonly age: number;
    readonly role: string;
    readonly description: string;
    readonly visual_identity: string;
    readonly art_direction: string;
  };
  readonly expression_variants: readonly SceneExpressionVariant[];
}

interface SceneTrack {
  readonly track_id: string;
  readonly asset_id: string;
}

interface SceneData {
  readonly scene_id: string;
  readonly title: string;
  readonly scene_label: string;
  readonly style_asset_id: string;
  readonly stages: readonly SceneStage[];
  readonly tracks: readonly SceneTrack[];
  readonly actors: readonly SceneActor[];
  readonly placement: {
    readonly framing_zoom: number;
    readonly source_framing_zoom: number;
  };
  /** The screen-fixed interface: measured geometry per role, and the sheet it is drawn from. */
  readonly ui: SceneUi;
  readonly scenario: ScenarioProgram;
}

export type SceneUiIconSet = UiIconSetLayout & Readonly<{ asset_id: string }>;

export type SceneUi = Readonly<
  Record<UiAtlasRoleName, SceneUiRole> & { preview_icons: SceneUiIconSet }
>;

function uiRoles(source: Record<string, unknown>): SceneUi {
  const role = (name: UiAtlasRoleName): SceneUiRole => {
    const raw = record(source[name], `scene_data.ui.${name}`);
    return Object.freeze({
      ...parseUiAtlasRoleLayout(raw, name, `scene_data.ui.${name}`),
      asset_id: text(raw.asset_id, `scene_data.ui.${name}.asset_id`),
    });
  };
  const rawIcons = record(source.preview_icons, "scene_data.ui.preview_icons");
  const previewIcons: SceneUiIconSet = Object.freeze({
    ...parseUiIconSetLayout(rawIcons, "scene_data.ui.preview_icons"),
    asset_id: text(rawIcons.asset_id, "scene_data.ui.preview_icons.asset_id"),
  });
  return Object.freeze({
    panel_frame: role("panel_frame"),
    button_rect: role("button_rect"),
    preview_icons: previewIcons,
  });
}

export function parseDialogueSceneBundle(value: unknown): DialogueSceneBundle {
  const root = record(value, "bundle");
  exact(root.kind, DIALOGUE_SCENE_BUNDLE_KIND, "bundle.kind");
  exact(root.schema_version, 7, "bundle.schema_version");
  exact(root.recipe, "dialogue-scene", "bundle.recipe");
  exact(root.recipe_version, DIALOGUE_SCENE_RECIPE_VERSION, "bundle.recipe_version");

  const assets = array(root.assets, "bundle.assets").map((entry, index) => {
    const asset = record(entry, `bundle.assets[${index}]`);
    const role = asset.role;
    if (
      role !== "style" &&
      role !== "background" &&
      role !== "expression" &&
      role !== "track" &&
      role !== "ui"
    ) {
      throw new Error(`bundle.assets[${index}].role is not a known role`);
    }
    return Object.freeze({
      id: text(asset.id, `bundle.assets[${index}].id`),
      role,
      // The producer's canonical form omits nulls, so an asset with no actor or
      // no expression state simply has no key. Absent and null mean the same
      // thing here, and reading only one of the two is how a style plate ends up
      // failing validation for not being an expression.
      actorId: optional(asset.actor_id, "asset actor_id"),
      state: optional(asset.state, "asset state"),
      trackId: optional(asset.track_id, "asset track_id"),
      path: text(asset.path, `bundle.assets[${index}].path`),
      sha256: text(asset.sha256, `bundle.assets[${index}].sha256`),
    });
  });

  const sceneRaw = record(root.scene_data, "bundle.scene_data");
  const sceneData: SceneData = {
    scene_id: text(sceneRaw.scene_id, "scene_data.scene_id"),
    title: text(sceneRaw.title, "scene_data.title"),
    scene_label: text(sceneRaw.scene_label, "scene_data.scene_label"),
    style_asset_id: text(sceneRaw.style_asset_id, "scene_data.style_asset_id"),
    tracks: array(sceneRaw.tracks ?? [], "scene_data.tracks").map((entry, index) => {
      const track = record(entry, `scene_data.tracks[${index}]`);
      return Object.freeze({
        track_id: text(track.track_id, `scene_data.tracks[${index}].track_id`),
        asset_id: text(track.asset_id, `scene_data.tracks[${index}].asset_id`),
      });
    }),
    stages: array(sceneRaw.stages, "scene_data.stages").map((entry, index) => {
      const stage = record(entry, `scene_data.stages[${index}]`);
      return Object.freeze({
        stage_id: text(stage.stage_id, "stage_id"),
        asset_id: text(stage.asset_id, "stage asset_id"),
        alt: text(stage.alt, "stage alt"),
      });
    }),
    actors: array(sceneRaw.actors, "scene_data.actors").map((entry, index) => {
      const actor = record(entry, `scene_data.actors[${index}]`);
      const appearance = record(actor.appearance, `scene_data.actors[${index}].appearance`);
      return Object.freeze({
        actor_id: text(actor.actor_id, "actor_id"),
        appearance: Object.freeze({
          id: text(appearance.id, "appearance.id"),
          label: text(appearance.label, "appearance.label"),
          age: integer(appearance.age, "appearance.age"),
          role: text(appearance.role, "appearance.role"),
          description: text(appearance.description, "appearance.description"),
          visual_identity: text(appearance.visual_identity, "appearance.visual_identity"),
          art_direction: text(appearance.art_direction, "appearance.art_direction"),
        }),
        expression_variants: array(
          actor.expression_variants,
          `scene_data.actors[${index}].expression_variants`,
        ).map((variantValue, at) => {
          const variant = record(variantValue, `expression_variants[${at}]`);
          return Object.freeze({
            id: text(variant.id, "variant.id"),
            asset_id: text(variant.asset_id, "variant.asset_id"),
            state: text(variant.state, "variant.state"),
            label: text(variant.label, "variant.label"),
            description: text(variant.description, "variant.description"),
            alt: text(variant.alt, "variant.alt"),
          });
        }),
      });
    }),
    placement: Object.freeze({
      framing_zoom: integer(
        record(sceneRaw.placement, "scene_data.placement").framing_zoom,
        "placement.framing_zoom",
      ),
      source_framing_zoom: integer(
        record(sceneRaw.placement, "scene_data.placement").source_framing_zoom,
        "placement.source_framing_zoom",
      ),
    }),
    ui: uiRoles(record(sceneRaw.ui, "scene_data.ui")),
    scenario: parseScenarioProgram(sceneRaw.scenario),
  };

  return Object.freeze({
    tag: text(root.tag, "bundle.tag"),
    gameId: text(root.game_id, "bundle.game_id"),
    assets: Object.freeze(assets),
    sceneData,
  });
}

/**
 * Turn one bundle into the fixture the scene plays.
 *
 * `assetUrl` is the seam: a run streams through the per-tag asset API, and an
 * installed bundle would stream from its own digest-addressed directory. Nothing
 * else about the projection differs, which is why the caller supplies it.
 */
export function projectDialogueSceneFixture(
  bundle: DialogueSceneBundle,
  assetUrl: (asset: DialogueSceneBundleAsset) => string,
): DialogueSceneFixture {
  const byId = new Map(bundle.assets.map((asset) => [asset.id, asset]));
  const require = (id: string): DialogueSceneBundleAsset => {
    const asset = byId.get(id);
    if (asset === undefined) {
      throw new Error(`bundle names asset ${id} that its inventory does not carry`);
    }
    return asset;
  };
  const scene = bundle.sceneData;
  return validateDialogueSceneFixture({
    schemaVersion: 1,
    fixtureId: scene.scene_id,
    title: scene.title,
    sceneLabel: scene.scene_label,
    presentation: {
      framingZoom: scene.placement.framing_zoom,
      sourceFramingZoom: scene.placement.source_framing_zoom,
    },
    styleSrc: assetUrl(require(scene.style_asset_id)),
    stages: scene.stages.map((stage) => ({
      stageId: stage.stage_id,
      id: stage.asset_id,
      src: assetUrl(require(stage.asset_id)),
      alt: stage.alt,
    })),
    tracks: scene.tracks.map((track) => ({
      trackId: track.track_id,
      id: track.asset_id,
      src: assetUrl(require(track.asset_id)),
    })),
    actors: scene.actors.map((actor) => ({
      actorId: actor.actor_id,
      appearance: {
        id: actor.appearance.id,
        label: actor.appearance.label,
        age: actor.appearance.age,
        role: actor.appearance.role,
        description: actor.appearance.description,
        visualIdentity: actor.appearance.visual_identity,
        artDirection: actor.appearance.art_direction,
      },
      expressions: actor.expression_variants.map((variant) => ({
        id: variant.id,
        src: assetUrl(require(variant.asset_id)),
        alt: variant.alt,
        state: variant.state,
        label: variant.label,
        description: variant.description,
      })),
    })),
    ui: {
      panelFrame: {
        layout: scene.ui.panel_frame,
        src: assetUrl(require(scene.ui.panel_frame.asset_id)),
      },
      buttonRect: {
        layout: scene.ui.button_rect,
        src: assetUrl(require(scene.ui.button_rect.asset_id)),
      },
      previewIcons: {
        layout: scene.ui.preview_icons,
        src: assetUrl(require(scene.ui.preview_icons.asset_id)),
      },
    },
    scenario: serializeScenarioProgram(scene.scenario),
  });
}

function record(value: unknown, label: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function array(value: unknown, label: string): readonly unknown[] {
  if (!Array.isArray(value)) throw new Error(`${label} must be an array`);
  return value;
}

function optional(value: unknown, label: string): string | null {
  return value === null || value === undefined ? null : text(value, label);
}

function text(value: unknown, label: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`${label} must be a non-empty string`);
  }
  return value;
}

function integer(value: unknown, label: string): number {
  if (!Number.isSafeInteger(value)) throw new Error(`${label} must be an integer`);
  return value as number;
}

function exact<ValueT>(value: unknown, expected: ValueT, label: string): void {
  if (value !== expected) throw new Error(`${label} must be ${JSON.stringify(expected)}`);
}

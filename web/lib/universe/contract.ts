/**
 * The universe gallery contracts the viewer reads: `universe-gallery-manifest-v1`,
 * the admitted universe it names (`universe-admitted-v1`), and the per-entity
 * record (`universe-entity-record-v1`).
 *
 * Strict, hand-written validating parsers in the house style: an unknown kind
 * is refused with a re-generate hint, shapes are checked field by field, and
 * wire `lower_snake_case` is translated to runtime camelCase here — this module
 * is the boundary, so nothing downstream spells a field two ways.
 *
 * The viewer reads three documents and never the graph: a gallery is finished
 * work, and the run view at /runs/<tag> already owns how it was produced.
 */

export const GALLERY_MANIFEST_KIND = "universe-gallery-manifest-v1";
export const ADMITTED_UNIVERSE_KIND = "universe-admitted-v1";
export const ENTITY_RECORD_KIND = "universe-entity-record-v1";
export const UNIVERSE_SCHEMA_VERSION = 1;

export const UNIVERSE_REFUSAL =
  "unsupported universe gallery run; regenerate it with a current stage-gen " +
  "(stage-gen universe gallery)";

/** How a branch can end. `admitted` and `rejected` are review outcomes; the rest name a stage. */
export const ENTITY_STATUSES = [
  "admitted",
  "rejected",
  "direction_failed",
  "generation_failed",
  "review_failed",
  "unknown",
] as const;
export type EntityStatus = (typeof ENTITY_STATUSES)[number];

/** The eight classes an entity can hold, in the order the gallery presents them. */
export const CLASS_ORDER = [
  "actor",
  "collective",
  "place",
  "thing",
  "kind",
  "system",
  "event",
  "idea",
] as const;
export type EntityClass = (typeof CLASS_ORDER)[number];

/**
 * The named checks one image review returns, in reading order rather than the
 * producer's alphabetical serialization: what it is, what it is doing, whether
 * the sealed register held, then the medium and the two form refusals.
 */
export const REVIEW_CHECKS = [
  "entity_identity",
  "action_legibility",
  "register_fidelity",
  "medium_fidelity",
  "explanatory_form_absent",
  "readable_text_absent",
  "technical_quality",
] as const;
export type ReviewCheck = (typeof REVIEW_CHECKS)[number];

/** Short labels for the check matrix; the wire names are too wide for a column head. */
export const REVIEW_CHECK_LABELS: Readonly<Record<ReviewCheck, string>> = {
  entity_identity: "identity",
  action_legibility: "action",
  register_fidelity: "register",
  medium_fidelity: "medium",
  explanatory_form_absent: "no diagram",
  readable_text_absent: "no text",
  technical_quality: "technical",
};

export interface GalleryEntityEntry {
  readonly entityId: string;
  readonly displayName: string;
  readonly primaryClass: string;
  readonly status: EntityStatus;
  /** Why a branch ended where it did. Empty for a terminal review outcome. */
  readonly reason: string;
  /** Run-relative refs, null when the branch never produced that artifact. */
  readonly image: string | null;
  readonly record: string | null;
  readonly review: string | null;
}

export interface GalleryManifest {
  readonly universeId: string;
  readonly title: string;
  readonly mediumId: string;
  readonly graphSha256: string;
  readonly invocationId: string;
  readonly closedInGraph: boolean;
  /** Run-relative, because the run carries the bytes its manifest names. */
  readonly inputs: {
    readonly universePath: string;
    readonly universeSha256: string;
    readonly posterProxyPath: string;
  };
  readonly counts: Readonly<Record<string, number>>;
  readonly entityCount: number;
  readonly entities: readonly GalleryEntityEntry[];
  readonly durationMs: number | null;
  readonly knownCostUsd: number | null;
  readonly publicationAuthorized: boolean;
  readonly publicationGate: string;
}

/** A sourced claim: what is asserted, and where the pipeline says it came from. */
export interface SourcedClaim {
  readonly claim: string;
  readonly lineage: string;
}

export interface UniverseEntity {
  readonly entityId: string;
  readonly displayName: string;
  readonly entityKind: string;
  readonly primaryClass: string;
  readonly facets: readonly string[];
  readonly summary: string;
  readonly howItWorksOrLives: string;
  readonly presentTension: string;
  readonly facts: readonly SourcedClaim[];
}

export interface UniverseRelationship {
  readonly relationshipId: string;
  readonly kind: string;
  readonly family: string;
  readonly sourceEntityId: string;
  readonly targetEntityId: string;
  readonly summary: string;
  readonly perspective: string;
  readonly temporalScope: string;
}

export interface IdentityMarker {
  readonly markerId: string;
  readonly ownerEntityId: string;
  readonly form: string;
  readonly meaning: string;
  readonly materials: string;
  readonly appliedUse: string;
  readonly limits: string;
}

export interface Viewpoint {
  readonly viewpointId: string;
  readonly displayName: string;
  readonly summary: string;
  readonly entryQuestion: string;
  readonly initiallyKnown: string;
  readonly anchorEntityIds: readonly string[];
}

export interface InstitutionalTension {
  readonly tensionId: string;
  readonly summary: string;
  readonly materialStakes: string;
  readonly competingLegitimateNeeds: string;
  readonly participantEntityIds: readonly string[];
}

/** The sealed scene facts one image was planned against. Weather is scene-local. */
export interface SceneRegister {
  readonly scale: string;
  readonly timeOfDay: string;
  readonly weather: string;
  readonly setting: string;
  readonly population: string;
  readonly energy: string;
}

/**
 * The composition in three strokes, and the axis the planner spreads a gallery
 * along: no (verb, prop) pair may repeat, and no vantage may cover more than
 * half the set. Reading them together is how redundancy becomes visible.
 */
export interface SignatureMotif {
  readonly actionVerb: string;
  readonly dominantProp: string;
  readonly vantage: string;
}

export interface EntityPlan {
  readonly entityId: string;
  readonly primaryPurpose: string;
  readonly audienceQuestion: string;
  readonly scenePremise: string;
  readonly inFrameContrast: string;
  readonly conceptMode: string;
  readonly signatureMotif: SignatureMotif | null;
  readonly sceneRegister: SceneRegister;
}

export interface AdmittedUniverse {
  readonly universeId: string;
  readonly title: string;
  readonly mediumId: string;
  readonly premise: SourcedClaim;
  readonly presentState: SourcedClaim;
  readonly entities: readonly UniverseEntity[];
  readonly relationships: readonly UniverseRelationship[];
  readonly identityMarkers: readonly IdentityMarker[];
  readonly viewpoints: readonly Viewpoint[];
  readonly institutionalTensions: readonly InstitutionalTension[];
  readonly physicalEcologicalRules: readonly SourcedClaim[];
  readonly unresolvedQuestions: readonly string[];
  readonly plans: readonly EntityPlan[];
}

export interface ImageReview {
  readonly verdict: string;
  readonly whatTheImageTeaches: string;
  readonly blockingFindings: readonly string[];
  readonly advisoryFindings: readonly string[];
  /** Every named check, `pass` or `fail` as the reviewer returned it. */
  readonly checks: Readonly<Record<ReviewCheck, string>>;
}

/** What the primary subject is visibly doing, as the direction compiler sealed it. */
export interface ActionBeat {
  readonly agent: string;
  readonly goal: string;
  readonly obstacle: string;
  readonly intervention: string;
  readonly visibleStateChange: string;
}

/** How the subject must look, so the same entity stays the same entity. */
export interface VisualIdentity {
  readonly silhouette: string;
  readonly proportions: string;
  readonly constructionLogic: string;
  readonly materials: string;
  readonly colorPlacement: string;
  readonly scaleAnchor: string;
  readonly wearAndHistory: string;
  readonly characteristicMotionOrUse: string;
  readonly forbiddenSubstitutions: readonly string[];
}

/**
 * The compiled direction the image was drawn from, as the record keeps it.
 *
 * This is what a rejection is judged against: the reviewer's finding only
 * means something beside the beat the image was supposed to show.
 */
export interface DirectionSummary {
  readonly primarySubject: string;
  readonly actionBeat: ActionBeat;
  readonly visualIdentity: VisualIdentity;
}

export interface EntityRecord {
  readonly entityId: string;
  readonly status: EntityStatus;
  readonly direction: DirectionSummary | null;
  readonly review: ImageReview;
  readonly image: { readonly width: number; readonly height: number } | null;
}

function record(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function text(value: unknown, label: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`${label} must be a non-empty string`);
  }
  return value;
}

/** A field the producer writes but may legitimately leave empty. */
function optionalText(value: unknown, label: string): string {
  if (value === undefined || value === null) return "";
  if (typeof value !== "string") throw new Error(`${label} must be a string`);
  return value;
}

function integer(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isInteger(value)) {
    throw new Error(`${label} must be an integer`);
  }
  return value;
}

function optionalNumber(value: unknown, label: string): number | null {
  if (value === undefined || value === null) return null;
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`${label} must be a finite number`);
  }
  return value;
}

function array(value: unknown, label: string): readonly unknown[] {
  if (!Array.isArray(value)) throw new Error(`${label} must be an array`);
  return value;
}

function strings(value: unknown, label: string): readonly string[] {
  return array(value, label).map((entry, index) =>
    text(entry, `${label}[${index}]`),
  );
}

function status(value: unknown, label: string): EntityStatus {
  if (
    typeof value !== "string" ||
    !(ENTITY_STATUSES as readonly string[]).includes(value)
  ) {
    throw new Error(`${label} must be one of ${ENTITY_STATUSES.join(", ")}`);
  }
  return value as EntityStatus;
}

/**
 * A run-relative artifact ref, or null when the branch produced none.
 *
 * Segments are checked here as well as in the asset route, because this ref
 * reaches the browser as an image URL: a manifest is data the viewer is
 * handed, not a licence to address whatever it names.
 */
function artifactRef(value: unknown, label: string): string | null {
  if (value === undefined || value === null) return null;
  const ref = text(value, label);
  const segments = ref.split("/");
  if (
    segments.some(
      (segment) => segment === "" || segment === "." || segment === "..",
    )
  ) {
    throw new Error(`${label} must be a run-relative path`);
  }
  return ref;
}

function claim(value: unknown, label: string): SourcedClaim {
  const raw = record(value, label);
  return {
    claim: text(raw.claim, `${label}.claim`),
    lineage: optionalText(raw.lineage, `${label}.lineage`),
  };
}

function assertKind(raw: Record<string, unknown>, kind: string): void {
  if (raw.kind !== kind || raw.schema_version !== UNIVERSE_SCHEMA_VERSION) {
    throw new Error(UNIVERSE_REFUSAL);
  }
}

export function parseGalleryManifest(value: unknown): GalleryManifest {
  const raw = record(value, "gallery manifest");
  assertKind(raw, GALLERY_MANIFEST_KIND);

  const inputs = record(raw.inputs, "inputs");
  const counts = record(raw.counts, "counts");
  const entities = array(raw.entities, "entities").map(
    (entry, index): GalleryEntityEntry => {
      const item = record(entry, `entities[${index}]`);
      return {
        entityId: text(item.entity_id, `entities[${index}].entity_id`),
        displayName: text(item.display_name, `entities[${index}].display_name`),
        primaryClass: text(
          item.primary_class,
          `entities[${index}].primary_class`,
        ),
        status: status(item.status, `entities[${index}].status`),
        reason: optionalText(item.reason, `entities[${index}].reason`),
        image: artifactRef(item.image, `entities[${index}].image`),
        record: artifactRef(item.record, `entities[${index}].record`),
        review: artifactRef(item.review, `entities[${index}].review`),
      };
    },
  );

  const entityCount = integer(raw.entity_count, "entity_count");
  if (entityCount !== entities.length) {
    throw new Error("entity_count must match the number of entities listed");
  }

  return {
    universeId: text(raw.universe_id, "universe_id"),
    title: text(raw.title, "title"),
    mediumId: text(raw.medium_id, "medium_id"),
    graphSha256: text(raw.graph_sha256, "graph_sha256"),
    invocationId: text(raw.invocation_id, "invocation_id"),
    closedInGraph: raw.closed_in_graph === true,
    inputs: {
      universePath: text(inputs.universe_path, "inputs.universe_path"),
      universeSha256: text(inputs.universe_sha256, "inputs.universe_sha256"),
      posterProxyPath: text(
        inputs.poster_proxy_path,
        "inputs.poster_proxy_path",
      ),
    },
    counts: Object.fromEntries(
      Object.entries(counts).map(([key, count]) => [
        key,
        integer(count, `counts.${key}`),
      ]),
    ),
    entityCount,
    entities,
    durationMs: optionalNumber(raw.duration_ms, "duration_ms"),
    knownCostUsd: optionalNumber(raw.known_cost_usd, "known_cost_usd"),
    // A gallery is unpublished until a separate human gate says otherwise, so
    // the viewer trusts an explicit true and nothing else.
    publicationAuthorized: raw.publication_authorized === true,
    publicationGate: optionalText(raw.publication_gate, "publication_gate"),
  };
}

export function parseAdmittedUniverse(value: unknown): AdmittedUniverse {
  const raw = record(value, "admitted universe");
  assertKind(raw, ADMITTED_UNIVERSE_KIND);

  const proposal = record(raw.proposal, "proposal");
  const plan = record(raw.plan, "plan");

  const entities = array(proposal.entities, "proposal.entities").map(
    (entry, index): UniverseEntity => {
      const item = record(entry, `proposal.entities[${index}]`);
      const at = `proposal.entities[${index}]`;
      return {
        entityId: text(item.entity_id, `${at}.entity_id`),
        displayName: text(item.display_name, `${at}.display_name`),
        entityKind: optionalText(item.entity_kind, `${at}.entity_kind`),
        primaryClass: text(item.primary_class, `${at}.primary_class`),
        facets: strings(item.facets ?? [], `${at}.facets`),
        summary: optionalText(item.summary, `${at}.summary`),
        howItWorksOrLives: optionalText(
          item.how_it_works_or_lives,
          `${at}.how_it_works_or_lives`,
        ),
        presentTension: optionalText(
          item.present_tension,
          `${at}.present_tension`,
        ),
        facts: array(item.facts ?? [], `${at}.facts`).map((fact, at2) =>
          claim(fact, `${at}.facts[${at2}]`),
        ),
      };
    },
  );

  const relationships = array(
    proposal.relationships,
    "proposal.relationships",
  ).map((entry, index): UniverseRelationship => {
    const at = `proposal.relationships[${index}]`;
    const item = record(entry, at);
    return {
      relationshipId: text(item.relationship_id, `${at}.relationship_id`),
      kind: text(item.relationship_kind, `${at}.relationship_kind`),
      family: optionalText(
        item.relationship_family,
        `${at}.relationship_family`,
      ),
      sourceEntityId: text(item.source_entity_id, `${at}.source_entity_id`),
      targetEntityId: text(item.target_entity_id, `${at}.target_entity_id`),
      summary: optionalText(item.summary, `${at}.summary`),
      perspective: optionalText(item.perspective, `${at}.perspective`),
      temporalScope: optionalText(item.temporal_scope, `${at}.temporal_scope`),
    };
  });

  const identityMarkers = array(
    proposal.identity_markers ?? [],
    "proposal.identity_markers",
  ).map((entry, index): IdentityMarker => {
    const at = `proposal.identity_markers[${index}]`;
    const item = record(entry, at);
    return {
      markerId: text(item.marker_id, `${at}.marker_id`),
      ownerEntityId: text(item.owner_entity_id, `${at}.owner_entity_id`),
      form: optionalText(item.form, `${at}.form`),
      meaning: optionalText(item.meaning, `${at}.meaning`),
      materials: optionalText(item.materials, `${at}.materials`),
      appliedUse: optionalText(item.applied_use, `${at}.applied_use`),
      limits: optionalText(item.limits, `${at}.limits`),
    };
  });

  const viewpoints = array(
    proposal.viewpoints ?? [],
    "proposal.viewpoints",
  ).map((entry, index): Viewpoint => {
    const at = `proposal.viewpoints[${index}]`;
    const item = record(entry, at);
    return {
      viewpointId: text(item.viewpoint_id, `${at}.viewpoint_id`),
      displayName: text(item.display_name, `${at}.display_name`),
      summary: optionalText(item.summary, `${at}.summary`),
      entryQuestion: optionalText(item.entry_question, `${at}.entry_question`),
      initiallyKnown: optionalText(
        item.initially_known,
        `${at}.initially_known`,
      ),
      anchorEntityIds: strings(
        item.anchor_entity_ids ?? [],
        `${at}.anchor_entity_ids`,
      ),
    };
  });

  const institutionalTensions = array(
    proposal.institutional_tensions ?? [],
    "proposal.institutional_tensions",
  ).map((entry, index): InstitutionalTension => {
    const at = `proposal.institutional_tensions[${index}]`;
    const item = record(entry, at);
    return {
      tensionId: text(item.tension_id, `${at}.tension_id`),
      summary: optionalText(item.summary, `${at}.summary`),
      materialStakes: optionalText(
        item.material_stakes,
        `${at}.material_stakes`,
      ),
      competingLegitimateNeeds: optionalText(
        item.competing_legitimate_needs,
        `${at}.competing_legitimate_needs`,
      ),
      participantEntityIds: strings(
        item.participant_entity_ids ?? [],
        `${at}.participant_entity_ids`,
      ),
    };
  });

  const plans = array(plan.plans, "plan.plans").map(
    (entry, index): EntityPlan => {
      const at = `plan.plans[${index}]`;
      const item = record(entry, at);
      const register = record(item.scene_register, `${at}.scene_register`);
      const motif =
        item.signature_motif === undefined || item.signature_motif === null
          ? null
          : record(item.signature_motif, `${at}.signature_motif`);
      return {
        entityId: text(item.entity_id, `${at}.entity_id`),
        primaryPurpose: optionalText(
          item.primary_purpose,
          `${at}.primary_purpose`,
        ),
        audienceQuestion: optionalText(
          item.audience_question,
          `${at}.audience_question`,
        ),
        scenePremise: optionalText(item.scene_premise, `${at}.scene_premise`),
        inFrameContrast: optionalText(
          item.in_frame_contrast,
          `${at}.in_frame_contrast`,
        ),
        conceptMode: optionalText(item.concept_mode, `${at}.concept_mode`),
        signatureMotif:
          motif === null
            ? null
            : {
                actionVerb: optionalText(
                  motif.action_verb,
                  `${at}.signature_motif.action_verb`,
                ),
                dominantProp: optionalText(
                  motif.dominant_prop,
                  `${at}.signature_motif.dominant_prop`,
                ),
                vantage: optionalText(
                  motif.vantage,
                  `${at}.signature_motif.vantage`,
                ),
              },
        sceneRegister: {
          scale: optionalText(register.scale, `${at}.scene_register.scale`),
          timeOfDay: optionalText(
            register.time_of_day,
            `${at}.scene_register.time_of_day`,
          ),
          weather: optionalText(
            register.weather,
            `${at}.scene_register.weather`,
          ),
          setting: optionalText(
            register.setting,
            `${at}.scene_register.setting`,
          ),
          population: optionalText(
            register.population,
            `${at}.scene_register.population`,
          ),
          energy: optionalText(register.energy, `${at}.scene_register.energy`),
        },
      };
    },
  );

  return {
    universeId: text(raw.universe_id, "universe_id"),
    title: text(raw.title, "title"),
    mediumId: text(raw.medium_id, "medium_id"),
    premise: claim(proposal.premise, "proposal.premise"),
    presentState: claim(proposal.present_state, "proposal.present_state"),
    entities,
    relationships,
    identityMarkers,
    viewpoints,
    institutionalTensions,
    physicalEcologicalRules: array(
      proposal.physical_ecological_rules ?? [],
      "proposal.physical_ecological_rules",
    ).map((rule, index) =>
      claim(rule, `proposal.physical_ecological_rules[${index}]`),
    ),
    unresolvedQuestions: strings(
      proposal.unresolved_questions ?? [],
      "proposal.unresolved_questions",
    ),
    plans,
  };
}

function directionSummary(value: unknown): DirectionSummary | null {
  if (value === undefined || value === null) return null;
  const raw = record(value, "direction_summary");
  const beat = record(raw.action_beat, "direction_summary.action_beat");
  const identity = record(
    raw.visual_identity,
    "direction_summary.visual_identity",
  );
  const at = "direction_summary.visual_identity";
  return {
    primarySubject: optionalText(
      raw.primary_subject,
      "direction_summary.primary_subject",
    ),
    actionBeat: {
      agent: optionalText(beat.agent, "direction_summary.action_beat.agent"),
      goal: optionalText(beat.goal, "direction_summary.action_beat.goal"),
      obstacle: optionalText(
        beat.obstacle,
        "direction_summary.action_beat.obstacle",
      ),
      intervention: optionalText(
        beat.intervention,
        "direction_summary.action_beat.intervention",
      ),
      visibleStateChange: optionalText(
        beat.visible_state_change,
        "direction_summary.action_beat.visible_state_change",
      ),
    },
    visualIdentity: {
      silhouette: optionalText(identity.silhouette, `${at}.silhouette`),
      proportions: optionalText(identity.proportions, `${at}.proportions`),
      constructionLogic: optionalText(
        identity.construction_logic,
        `${at}.construction_logic`,
      ),
      materials: optionalText(identity.materials, `${at}.materials`),
      colorPlacement: optionalText(
        identity.color_placement,
        `${at}.color_placement`,
      ),
      scaleAnchor: optionalText(identity.scale_anchor, `${at}.scale_anchor`),
      wearAndHistory: optionalText(
        identity.wear_and_history,
        `${at}.wear_and_history`,
      ),
      characteristicMotionOrUse: optionalText(
        identity.characteristic_motion_or_use,
        `${at}.characteristic_motion_or_use`,
      ),
      forbiddenSubstitutions: strings(
        identity.forbidden_substitutions ?? [],
        `${at}.forbidden_substitutions`,
      ),
    },
  };
}

export function parseEntityRecord(value: unknown): EntityRecord {
  const raw = record(value, "entity record");
  assertKind(raw, ENTITY_RECORD_KIND);

  const review = record(raw.review, "review");
  const checks = Object.fromEntries(
    REVIEW_CHECKS.map((check) => [
      check,
      optionalText(review[check], `review.${check}`),
    ]),
  ) as Record<ReviewCheck, string>;

  const image =
    raw.image === undefined || raw.image === null
      ? null
      : record(raw.image, "image");

  return {
    entityId: text(review.entity_id, "review.entity_id"),
    status: status(raw.status, "status"),
    direction: directionSummary(raw.direction_summary),
    review: {
      verdict: optionalText(review.verdict, "review.verdict"),
      whatTheImageTeaches: optionalText(
        review.what_the_image_teaches,
        "review.what_the_image_teaches",
      ),
      blockingFindings: strings(
        review.blocking_findings ?? [],
        "review.blocking_findings",
      ),
      advisoryFindings: strings(
        review.advisory_findings ?? [],
        "review.advisory_findings",
      ),
      checks,
    },
    image:
      image === null
        ? null
        : {
            width: integer(image.width, "image.width"),
            height: integer(image.height, "image.height"),
          },
  };
}

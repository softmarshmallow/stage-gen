/**
 * Derivation for the universe viewer: the joins and tallies the page needs,
 * as pure functions over the parsed contracts.
 *
 * The server does every join once and hands the client one flat array, so the
 * browser holds no index and no lookup: filtering a card is reading two of its
 * own fields. Keeping it here rather than in the component also means the
 * arithmetic that decides what the gallery *says* — which checks failed, and
 * how often — is testable without rendering anything.
 */

import {
  type AdmittedUniverse,
  CLASS_ORDER,
  type DirectionSummary,
  type EntityPlan,
  type EntityRecord,
  type EntityStatus,
  type GalleryManifest,
  type IdentityMarker,
  type ImageReview,
  type ReviewCheck,
  REVIEW_CHECKS,
  type SourcedClaim,
} from "./contract";

/** One end of a relationship, seen from the entity whose card it appears on. */
export interface IncidentRelationship {
  readonly kind: string;
  readonly otherEntityId: string;
  readonly otherDisplayName: string;
  readonly summary: string;
  /** True when this entity is the source; the card draws → rather than ←. */
  readonly outgoing: boolean;
}

/** Everything one entity card renders, joined server-side. */
export interface EntityCard {
  readonly entityId: string;
  readonly displayName: string;
  readonly entityKind: string;
  readonly primaryClass: string;
  readonly facets: readonly string[];
  readonly summary: string;
  readonly howItWorksOrLives: string;
  readonly presentTension: string;
  readonly facts: readonly SourcedClaim[];
  readonly status: EntityStatus;
  /** Why a branch ended where it did; empty for a terminal review outcome. */
  readonly reason: string;
  /** Run-relative image ref, or null when no image was produced. */
  readonly image: string | null;
  readonly imageWidth: number | null;
  readonly imageHeight: number | null;
  readonly plan: EntityPlan | null;
  /** The compiled direction the image was drawn from, when a record kept it. */
  readonly direction: DirectionSummary | null;
  readonly review: ImageReview | null;
  readonly relationships: readonly IncidentRelationship[];
  readonly markers: readonly IdentityMarker[];
}

function classRank(primaryClass: string): number {
  const index = (CLASS_ORDER as readonly string[]).indexOf(primaryClass);
  // A class this build does not know sorts last rather than first, so an
  // added class never silently takes over the top of the grid.
  return index === -1 ? CLASS_ORDER.length : index;
}

/**
 * Join the manifest, the admitted universe, and the records into ordered cards.
 *
 * The manifest is the authority on which entities exist and how each branch
 * ended, so it drives the iteration; an entity it names that the proposal does
 * not describe is skipped rather than rendered half-empty.
 */
export function buildEntityCards(
  manifest: GalleryManifest,
  universe: AdmittedUniverse,
  records: Readonly<Record<string, EntityRecord>>,
): readonly EntityCard[] {
  const entities = new Map(
    universe.entities.map((entity) => [entity.entityId, entity]),
  );
  const plans = new Map(universe.plans.map((plan) => [plan.entityId, plan]));
  const names = new Map(
    universe.entities.map((entity) => [entity.entityId, entity.displayName]),
  );

  const markers = new Map<string, IdentityMarker[]>();
  for (const marker of universe.identityMarkers) {
    const owned = markers.get(marker.ownerEntityId);
    if (owned) owned.push(marker);
    else markers.set(marker.ownerEntityId, [marker]);
  }

  const incident = new Map<string, IncidentRelationship[]>();
  for (const relationship of universe.relationships) {
    const ends: readonly (readonly [string, string, boolean])[] = [
      [relationship.sourceEntityId, relationship.targetEntityId, true],
      [relationship.targetEntityId, relationship.sourceEntityId, false],
    ];
    for (const [self, other, outgoing] of ends) {
      if (!entities.has(self)) continue;
      const edge: IncidentRelationship = {
        kind: relationship.kind,
        otherEntityId: other,
        otherDisplayName: names.get(other) ?? other,
        summary: relationship.summary,
        outgoing,
      };
      const held = incident.get(self);
      if (held) held.push(edge);
      else incident.set(self, [edge]);
    }
  }

  const cards: EntityCard[] = [];
  for (const entry of manifest.entities) {
    const entity = entities.get(entry.entityId);
    if (!entity) continue;
    const held = records[entry.entityId] ?? null;
    cards.push({
      entityId: entity.entityId,
      displayName: entity.displayName,
      entityKind: entity.entityKind,
      primaryClass: entity.primaryClass,
      facets: entity.facets,
      summary: entity.summary,
      howItWorksOrLives: entity.howItWorksOrLives,
      presentTension: entity.presentTension,
      facts: entity.facts,
      status: entry.status,
      reason: entry.reason,
      image: entry.image,
      imageWidth: held?.image?.width ?? null,
      imageHeight: held?.image?.height ?? null,
      plan: plans.get(entry.entityId) ?? null,
      direction: held?.direction ?? null,
      review: held?.review ?? null,
      relationships: incident.get(entry.entityId) ?? [],
      markers: markers.get(entry.entityId) ?? [],
    });
  }

  cards.sort(
    (a, b) =>
      classRank(a.primaryClass) - classRank(b.primaryClass) ||
      a.displayName.localeCompare(b.displayName),
  );
  return cards;
}

/** How one named check fared across every entity that was actually reviewed. */
export interface CheckTally {
  readonly check: ReviewCheck;
  readonly passed: number;
  readonly failed: number;
  /** Reviewed entities whose value for this check was neither pass nor fail. */
  readonly other: number;
}

/**
 * Tally the named checks across a gallery, worst first.
 *
 * This is the reading the per-entity cards cannot give: one rejection tells
 * you an image was wrong, and thirty-six of them together tell you which way
 * the recipe leans. Ties keep the reviewer's own reading order so the table
 * does not reshuffle between two runs that failed equally.
 */
export function tallyReviewChecks(
  cards: readonly EntityCard[],
): readonly CheckTally[] {
  const reviewed = cards.filter((card) => card.review !== null);
  return REVIEW_CHECKS.map((check, index) => {
    let passed = 0;
    let failed = 0;
    let other = 0;
    for (const card of reviewed) {
      const value = card.review?.checks[check];
      if (value === "pass") passed += 1;
      else if (value === "fail") failed += 1;
      else other += 1;
    }
    return { check, passed, failed, other, index };
  })
    .sort((a, b) => b.failed - a.failed || a.index - b.index)
    .map(({ check, passed, failed, other }) => ({
      check,
      passed,
      failed,
      other,
    }));
}

/** The classes present in this gallery, in presentation order. */
export function presentClasses(
  cards: readonly EntityCard[],
): readonly string[] {
  const seen = new Set(cards.map((card) => card.primaryClass));
  return [...seen].sort(
    (a, b) => classRank(a) - classRank(b) || a.localeCompare(b),
  );
}

import type { PortalEndpointPlacement } from "./portal";
import type { PreparedGameplayContract } from "./prepared-gameplay";
import type { PreparedMap } from "@/lib/manifest/prepared-manifest";

/** Resolve map-owned portal anchors against separately authored gameplay transitions. */
export function preparedPortalEndpointPlacements(input: Readonly<{
  map: PreparedMap;
  maps: readonly PreparedMap[];
  transitions: PreparedGameplayContract["transitions"];
  worldWidth: number;
  portalKey: string;
}>): readonly PortalEndpointPlacement[] {
  if (!input.map.portal) return Object.freeze([]);
  if (!Number.isFinite(input.worldWidth) || input.worldWidth <= 0) {
    throw new Error("prepared portal world width must be positive");
  }
  return Object.freeze(
    input.map.portal.endpoints.map((endpoint) => {
      const transitions = input.transitions.filter(
        (candidate) =>
          candidate.from_map_id === input.map.map_id &&
          candidate.from_anchor === endpoint.anchor,
      );
      if (transitions.length > 1) {
        throw new Error(
          `prepared portal ${endpoint.anchor} has more than one transition`,
        );
      }
      const transition = transitions[0];
      const destinationIndex = transition
        ? input.maps.findIndex(
            (candidate) => candidate.map_id === transition.to_map_id,
          )
        : -1;
      if (transition && destinationIndex < 0) {
        throw new Error(
          `prepared portal ${endpoint.anchor} names an unknown destination map`,
        );
      }
      return Object.freeze({
        portalId: endpoint.anchor,
        kind: endpoint.role,
        x: endpoint.normalized_x * input.worldWidth,
        portalKey: input.portalKey,
        sourceFrame: endpoint.role,
        destinationIndex: destinationIndex < 0 ? null : destinationIndex,
      });
    }),
  );
}

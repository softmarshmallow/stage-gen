import { describe, expect, test } from "bun:test";
import type { PreparedGameplayContract } from "./prepared-gameplay";
import type { PreparedMap } from "@/lib/manifest/prepared-manifest";
import { preparedPortalEndpointPlacements } from "./prepared-portals";

function map(
  mapId: string,
  endpoints: PreparedMap["portal"] extends infer _T
    ? readonly Readonly<{
        anchor: string;
        normalized_x: number;
        role: "entry" | "exit";
      }>[]
    : never,
): PreparedMap {
  return {
    map_id: mapId,
    revision: 1,
    display_name: mapId,
    role: "scrolling_hunting_route",
    camera: { mode: "player_follow", follow_axes: ["x"] },
    hostile_population_enabled: true,
    track_ids: [],
    layers: [],
    ground: {
      mode: "terrain-atlas-3x3-minimal-v1",
      occupancy: ["1111111111"],
      vertical_fit: "floor_to_screen_bottom" as const,
      walk_surface_row: 0,
      asset: {
        path: `maps/${mapId}/ground.png`,
        sha256: "a".repeat(64),
        bytes: 1,
        media_type: "image/png",
        role: "asset" as const,
      },
    },
    portal: {
      mode: "portal-pair-1x2-v1",
      endpoints,
      asset: {
        path: `maps/${mapId}/portal.png`,
        sha256: "b".repeat(64),
        bytes: 1,
        media_type: "image/png",
        role: "asset" as const,
      },
    },
  };
}

describe("prepared portal adapter", () => {
  test("uses explicit role and anchor instead of inferring either from x", () => {
    const source = map("source", [
      { anchor: "east_arrival", normalized_x: 0.9, role: "entry" },
      { anchor: "west_departure", normalized_x: 0.1, role: "exit" },
    ]);
    const destination = map("destination", []);
    const transitions = [
      {
        transition_id: "travel",
        from_map_id: "source",
        from_anchor: "west_departure",
        to_map_id: "destination",
        to_spawn_id: "arrival",
      },
    ] as PreparedGameplayContract["transitions"];
    const placements = preparedPortalEndpointPlacements({
      map: source,
      maps: [source, destination],
      transitions,
      worldWidth: 640,
      portalKey: "prepared_portal_source",
    });

    expect(placements).toEqual([
      {
        portalId: "east_arrival",
        kind: "entry",
        x: 576,
        portalKey: "prepared_portal_source",
        sourceFrame: "entry",
        destinationIndex: null,
      },
      {
        portalId: "west_departure",
        kind: "exit",
        x: 64,
        portalKey: "prepared_portal_source",
        sourceFrame: "exit",
        destinationIndex: 1,
      },
    ]);
  });

  test("rejects ambiguous gameplay wiring for one map anchor", () => {
    const source = map("source", [
      { anchor: "gate", normalized_x: 0.5, role: "exit" },
    ]);
    const destination = map("destination", []);
    const transition = {
      transition_id: "travel_a",
      from_map_id: "source",
      from_anchor: "gate",
      to_map_id: "destination",
      to_spawn_id: "arrival",
    };
    expect(() =>
      preparedPortalEndpointPlacements({
        map: source,
        maps: [source, destination],
        transitions: [
          transition,
          { ...transition, transition_id: "travel_b" },
        ],
        worldWidth: 640,
        portalKey: "prepared_portal_source",
      }),
    ).toThrow("more than one transition");
  });
});

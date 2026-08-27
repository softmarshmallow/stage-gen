import { describe, expect, test } from "bun:test";
import {
  bottomContiguousOccupancy,
  parseTerrainOccupancy,
  terrainAtlasLookupEntries,
  terrainAtlasPlan,
  terrainPeeringMask,
} from "./terrain-atlas";

describe("47-mask terrain atlas consumer", () => {
  test("all masks and coordinates are unique and reachable", () => {
    const entries = terrainAtlasLookupEntries();
    expect(entries).toHaveLength(47);
    expect(new Set(entries.map((entry) => entry.mask)).size).toBe(47);
    expect(
      new Set(entries.map((entry) => `${entry.coordinate.column},${entry.coordinate.row}`)).size,
    ).toBe(47);
    for (const { mask } of entries) {
      const bits = [...mask].map(Number);
      const occupied = [
        [Boolean(bits[0]), Boolean(bits[1]), Boolean(bits[2])],
        [Boolean(bits[3]), true, Boolean(bits[5])],
        [Boolean(bits[6]), Boolean(bits[7]), Boolean(bits[8])],
      ];
      expect(terrainPeeringMask(occupied, 1, 1)).toBe(mask);
    }
  });

  test.each([
    ["solid", ["000000", "111111", "111111"]],
    ["one-cell-floating", ["000000", "011110", "000000"]],
    ["stairs", ["000011", "001111", "011111", "111111"]],
    ["concavity-and-hole", ["111111", "110011", "110101", "111111"]],
  ])("plans %s from all eight neighbors", (_name, rows) => {
    const occupied = parseTerrainOccupancy(rows);
    const plan = terrainAtlasPlan(occupied);
    expect(plan).toHaveLength(rows.reduce((count, row) => count + row.replaceAll("0", "").length, 0));
    expect(plan.every((cell) => cell.collision === "solid-cell")).toBeTrue();
  });

  test("projects bottom-contiguous heightfields without inventing slopes", () => {
    const occupied = bottomContiguousOccupancy([1, 2, 3, 2, 1]);
    expect(occupied.map((row) => row.map(Number).join(""))).toEqual([
      "00100",
      "01110",
      "11111",
    ]);
    expect(terrainAtlasPlan(occupied)).toHaveLength(9);
  });

  test("invalid binary maps fail closed", () => {
    expect(() => parseTerrainOccupancy([])).toThrow("nonempty");
    expect(() => parseTerrainOccupancy(["10", "1"])).toThrow("rectangle");
    expect(() => parseTerrainOccupancy(["1x"])).toThrow("zero-one");
  });
});

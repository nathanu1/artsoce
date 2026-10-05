import { describe, expect, it } from "vitest";
import { addressAt, decodeMap, entrances, KIND, rleDecode, tileHash } from "../src/lib/map";
import type { MapPayload } from "../src/types";

// 12 x 7 town: a house (sector 1) top left, a garden (sector 2, outdoor) top right, street elsewhere.
const W = 12;
const H = 7;
const grid = (f: (x: number, y: number) => number) => Array.from({ length: H }, (_, y) => Array.from({ length: W }, (_, x) => f(x, y)));
const rle = (rows: number[][]): [number, number][] => {
  const out: [number, number][] = [];
  for (const v of rows.flat()) {
    const last = out[out.length - 1];
    if (last && last[0] === v) last[1]++;
    else out.push([v, 1]);
  }
  return out;
};
const inHouse = (x: number, y: number) => x >= 1 && x <= 3 && y >= 1 && y <= 2;
const inGarden = (x: number, y: number) => x >= 8 && x <= 10 && y >= 1 && y <= 2;

const payload: MapPayload = {
  world: "the Ville",
  width: W,
  height: H,
  legend: { sector: ["", "House", "Rose Garden"], arena: ["", "kitchen", "yard"], object: ["", "stove", "garden"] },
  layers: {
    collision: rle(grid((x, y) => ((x === 3 && y === 1) || (x === 11 && y === 6) ? 1 : 0))),
    sector: rle(grid((x, y) => (inHouse(x, y) ? 1 : inGarden(x, y) ? 2 : 0))),
    arena: rle(grid((x, y) => (inHouse(x, y) ? 1 : inGarden(x, y) ? 2 : 0))),
    object: rle(grid((x, y) => (x === 1 && y === 1 ? 1 : x === 9 && y === 2 ? 2 : 0))),
  },
  outdoor_arenas: ["the Ville:Rose Garden:yard"],
  ground_objects: ["the Ville:Rose Garden:yard:garden"],
  objects: [],
};

describe("map decoding", () => {
  const m = decodeMap(payload);
  const kind = (x: number, y: number) => m.kind[y * W + x];

  it("rejects layers of the wrong size", () => {
    expect(() => rleDecode([[0, 3]], 4)).toThrow(/3 tiles, expected 4/);
  });

  it("resolves addresses at each level", () => {
    expect(addressAt(m, 1, 1)).toBe("the Ville:House:kitchen:stove");
    expect(addressAt(m, 2, 2, "arena")).toBe("the Ville:House:kitchen");
    expect(addressAt(m, 2, 2, "sector")).toBe("the Ville:House");
    expect(addressAt(m, 6, 5)).toBeNull();
    expect(m.objects.get("the Ville:House:kitchen:stove")).toEqual([[1, 1]]);
  });

  it("classifies ground: walls, nature, floors, lawn and flower beds", () => {
    expect(kind(3, 1)).toBe(KIND.WALL);
    expect(kind(11, 6)).toBe(KIND.NATURE);
    expect(kind(2, 2)).toBe(KIND.FLOOR);
    expect(kind(8, 1)).toBe(KIND.LAWN);
    expect(kind(9, 2)).toBe(KIND.BED);
    expect(kind(6, 5)).toBe(KIND.GRASS);
  });

  it("puts front doors on the street next to each building's middle", () => {
    const doors = entrances(m);
    expect(doors.get(1)).toEqual([2, 0]);
    expect(doors.get(2)).toEqual([9, 0]);
  });

  it("joins the front doors with a connected road", () => {
    const road = new Set<number>();
    for (let i = 0; i < W * H; i++) if (m.kind[i] === KIND.ROAD) road.add(i);
    expect(road.has(0 * W + 2) && road.has(0 * W + 9)).toBe(true);
    // flood fill over road tiles from one door reaches the other
    const seen = new Set([2]);
    const queue = [2];
    while (queue.length) {
      const i = queue.pop()!;
      for (const j of [i - 1, i + 1, i - W, i + W]) {
        if (j < 0 || j >= W * H || seen.has(j) || !road.has(j)) continue;
        if (Math.abs((j % W) - (i % W)) > 1) continue;
        seen.add(j);
        queue.push(j);
      }
    }
    expect(seen.has(9)).toBe(true);
  });

  it("hashes tiles deterministically into [0, 1]", () => {
    expect(tileHash(3, 4)).toBe(tileHash(3, 4));
    expect(tileHash(3, 4)).not.toBe(tileHash(4, 3));
    for (let i = 0; i < 50; i++) {
      const h = tileHash(i, i * 7, 2);
      expect(h).toBeGreaterThanOrEqual(0);
      expect(h).toBeLessThanOrEqual(1);
    }
  });
});

import { describe, expect, it } from "vitest";
import { draftCost, dropPlacement, emptyDraft, footprint, push, redo, replace, shownItems, size, templateOps, undo } from "../src/lib/build";
import type { BuildOp, CatalogItem, PlacedItem } from "../src/types";

const bench = { footprint: [2, 1] as [number, number] };
const place = (x: number, y: number, id = "bench"): BuildOp => ({ op: "place", catalog_id: id, x, y, rot: 0, paint: null });

describe("draft history", () => {
  it("undoes and redoes whole steps, and a new step clears redo", () => {
    let d = push(emptyDraft(), [place(1, 1)]);
    d = push(d, [place(2, 2), place(3, 3)]);
    expect(d.ops).toHaveLength(3);
    d = undo(d);
    expect(d.ops).toHaveLength(1);
    d = redo(d);
    expect(d.ops).toHaveLength(3);
    d = undo(undo(d));
    expect(d.ops).toHaveLength(0);
    d = push(d, [place(5, 5)]);
    expect(d.redo).toHaveLength(0);
    expect(redo(d)).toBe(d);
  });

  it("ignores empty pushes and undo past the start", () => {
    const d = emptyDraft();
    expect(push(d, [])).toBe(d);
    expect(undo(d)).toBe(d);
  });

  it("replace is undoable", () => {
    const d = replace(push(emptyDraft(), [place(1, 1)]), []);
    expect(d.ops).toEqual([]);
    expect(undo(d).ops).toHaveLength(1);
  });
});

describe("footprints", () => {
  it("swap width and height on quarter turns", () => {
    expect(size(bench, 0)).toEqual([2, 1]);
    expect(size(bench, 1)).toEqual([1, 2]);
    expect(size(bench, 2)).toEqual([2, 1]);
    expect(footprint(bench, 4, 5, 1)).toEqual([
      [4, 5],
      [4, 6],
    ]);
  });
});

describe("shownItems", () => {
  const items: PlacedItem[] = [{ id: "i1", catalog_id: "bench", x: 1, y: 1, rot: 0, paint: null } as PlacedItem, { id: "i2", catalog_id: "lamp", x: 5, y: 5, rot: 0, paint: null } as PlacedItem];

  it("applies place, move, paint and remove on top of committed items", () => {
    const ops: BuildOp[] = [place(8, 8, "mailbox"), { op: "move", item_id: "i1", x: 2, y: 3, rot: 1 }, { op: "paint", item_id: "i2", paint: "mint" }, { op: "remove", item_id: "i2" }];
    const shown = shownItems(items, ops);
    expect(shown.map((s) => s.key).sort()).toEqual(["draft:0", "i1"]);
    const moved = shown.find((s) => s.key === "i1")!;
    expect([moved.x, moved.y, moved.rot, moved.draft, moved.committedId, moved.opIndex]).toEqual([2, 3, 1, true, "i1", 1]);
    const placed = shown.find((s) => s.key === "draft:0")!;
    expect([placed.catalog_id, placed.committedId, placed.opIndex]).toEqual(["mailbox", null, 0]);
  });

  it("ignores operations on unknown items", () => {
    expect(shownItems(items, [{ op: "remove", item_id: "nope" }])).toHaveLength(2);
  });

  it("dropPlacement removes only that operation", () => {
    expect(dropPlacement([place(1, 1), place(2, 2), place(3, 3)], 1).map((o) => o.x)).toEqual([1, 3]);
  });
});

describe("templates and cost", () => {
  it("offsets template parts from the anchor tile", () => {
    const ops = templateOps({ id: "t", name: "Nook", parts: [{ item: "bench", dx: 0, dy: 0 }, { item: "lamp", dx: 2, dy: 1, rot: 3, paint: "mint" }] } as never, 10, 20);
    expect(ops).toEqual([
      { op: "place", catalog_id: "bench", x: 10, y: 20, rot: 0, paint: null },
      { op: "place", catalog_id: "lamp", x: 12, y: 21, rot: 3, paint: "mint" },
    ]);
  });

  it("sums motif costs of new items per theme", () => {
    const catalog = new Map<string, CatalogItem>([
      ["bench", { id: "bench", cost: { kin: 1, bloom: 1 } } as unknown as CatalogItem],
      ["lamp", { id: "lamp", cost: { kin: 2 } } as unknown as CatalogItem],
    ]);
    const ops: BuildOp[] = [place(1, 1), place(2, 2, "lamp"), { op: "move", item_id: "i1", x: 0, y: 0 }, place(3, 3, "unknown")];
    expect(draftCost(ops, catalog)).toEqual({ kin: 3, bloom: 1 });
  });
});

import type { BuildOp, CatalogItem, PlacedItem, Template, Tile } from "../types";

/** A build session: operations not yet sent, with undo and redo. */
export interface Draft {
  ops: BuildOp[];
  undo: BuildOp[][];
  redo: BuildOp[][];
}

export const emptyDraft = (): Draft => ({ ops: [], undo: [], redo: [] });

export function push(d: Draft, ops: BuildOp[]): Draft {
  if (!ops.length) return d;
  return { ops: [...d.ops, ...ops], undo: [...d.undo, d.ops], redo: [] };
}

export function replace(d: Draft, ops: BuildOp[]): Draft {
  return { ops, undo: [...d.undo, d.ops], redo: [] };
}

export function undo(d: Draft): Draft {
  if (!d.undo.length) return d;
  const prev = d.undo[d.undo.length - 1];
  return { ops: prev, undo: d.undo.slice(0, -1), redo: [...d.redo, d.ops] };
}

export function redo(d: Draft): Draft {
  if (!d.redo.length) return d;
  const next = d.redo[d.redo.length - 1];
  return { ops: next, undo: [...d.undo, d.ops], redo: d.redo.slice(0, -1) };
}

export function size(item: Pick<CatalogItem, "footprint">, rot: number): [number, number] {
  const [w, h] = item.footprint;
  return rot % 2 ? [h, w] : [w, h];
}

export function footprint(item: Pick<CatalogItem, "footprint">, x: number, y: number, rot: number): Tile[] {
  const [w, h] = size(item, rot);
  const out: Tile[] = [];
  for (let dy = 0; dy < h; dy++) for (let dx = 0; dx < w; dx++) out.push([x + dx, y + dy]);
  return out;
}

export interface ShownItem {
  key: string; // committed id, or "draft:<op index>"
  catalog_id: string;
  x: number;
  y: number;
  rot: number;
  paint: string | null;
  draft: boolean;
  committedId: string | null;
  opIndex: number | null;
}

/** What the town shows while building: committed items with the draft applied on top. */
export function shownItems(items: PlacedItem[], ops: BuildOp[]): ShownItem[] {
  const out = new Map<string, ShownItem>();
  for (const it of items) {
    out.set(it.id, { key: it.id, catalog_id: it.catalog_id, x: it.x, y: it.y, rot: it.rot, paint: it.paint, draft: false, committedId: it.id, opIndex: null });
  }
  ops.forEach((op, i) => {
    if (op.op === "place" && op.catalog_id !== undefined) {
      out.set(`draft:${i}`, {
        key: `draft:${i}`,
        catalog_id: op.catalog_id,
        x: op.x ?? 0,
        y: op.y ?? 0,
        rot: op.rot ?? 0,
        paint: op.paint ?? null,
        draft: true,
        committedId: null,
        opIndex: i,
      });
      return;
    }
    const target = op.item_id ? out.get(op.item_id) : undefined;
    if (!target) return;
    if (op.op === "remove") out.delete(op.item_id!);
    else if (op.op === "move") out.set(target.key, { ...target, x: op.x ?? target.x, y: op.y ?? target.y, rot: op.rot ?? target.rot, draft: true, opIndex: i });
    else if (op.op === "paint") out.set(target.key, { ...target, paint: op.paint ?? null, draft: true, opIndex: i });
  });
  return [...out.values()];
}

/** Drop a draft-placed item (its place op) from the draft. */
export function dropPlacement(ops: BuildOp[], opIndex: number): BuildOp[] {
  return ops.filter((_, i) => i !== opIndex);
}

export function templateOps(t: Template, x: number, y: number): BuildOp[] {
  return t.parts.map((p) => ({ op: "place", catalog_id: p.item, x: x + p.dx, y: y + p.dy, rot: p.rot ?? 0, paint: p.paint ?? null }));
}

/** Total motif cost of the draft's new items, per theme (refunds are computed by the server). */
export function draftCost(ops: BuildOp[], catalog: Map<string, CatalogItem>): Record<string, number> {
  const out: Record<string, number> = {};
  for (const op of ops) {
    if (op.op !== "place" || !op.catalog_id) continue;
    const item = catalog.get(op.catalog_id);
    if (!item) continue;
    for (const [t, n] of Object.entries(item.cost)) out[t] = (out[t] ?? 0) + n;
  }
  return out;
}

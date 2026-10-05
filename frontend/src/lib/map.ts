import type { MapPayload, Tile } from "../types";

export const KIND = {
  GRASS: 0,
  ROAD: 1,
  PLAZA: 2,
  FLOOR: 3,
  BATH: 4,
  LAWN: 5,
  BED: 6, // flower bed (garden ground cover)
  WALL: 7,
  NATURE: 8,
} as const;

export interface Building {
  index: number;
  name: string;
  tiles: number;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  entrance: Tile | null;
}

export interface TownMap {
  width: number;
  height: number;
  world: string;
  collision: Uint8Array;
  sector: Int32Array;
  arena: Int32Array;
  object: Int32Array;
  legend: MapPayload["legend"];
  kind: Uint8Array;
  plazaSector: number;
  outdoorArenas: Set<string>;
  groundObjects: Set<string>;
  objects: Map<string, Tile[]>;
  buildings: Map<number, Building>;
}

export function rleDecode(rle: [number, number][], size: number): Int32Array {
  const out = new Int32Array(size);
  let i = 0;
  for (const [value, count] of rle) {
    out.fill(value, i, i + count);
    i += count;
  }
  if (i !== size) throw new Error(`layer has ${i} tiles, expected ${size}`);
  return out;
}

export function addressAt(m: TownMap, x: number, y: number, level: "sector" | "arena" | "object" = "object"): string | null {
  const i = y * m.width + x;
  const s = m.legend.sector[m.sector[i]];
  if (!s) return null;
  if (level === "sector") return `${m.world}:${s}`;
  const a = m.legend.arena[m.arena[i]];
  if (!a) return level === "arena" ? null : `${m.world}:${s}`;
  if (level === "arena") return `${m.world}:${s}:${a}`;
  const o = m.legend.object[m.object[i]];
  return o ? `${m.world}:${s}:${a}:${o}` : `${m.world}:${s}:${a}`;
}

export function decodeMap(p: MapPayload): TownMap {
  const size = p.width * p.height;
  const collision = Uint8Array.from(rleDecode(p.layers.collision, size));
  const m: TownMap = {
    width: p.width,
    height: p.height,
    world: p.world,
    collision,
    sector: rleDecode(p.layers.sector, size),
    arena: rleDecode(p.layers.arena, size),
    object: rleDecode(p.layers.object, size),
    legend: p.legend,
    kind: new Uint8Array(size),
    plazaSector: p.legend.sector.indexOf("Town Square"),
    outdoorArenas: new Set(p.outdoor_arenas),
    groundObjects: new Set(p.ground_objects),
    objects: new Map(),
    buildings: new Map(),
  };
  for (let y = 0; y < p.height; y++) {
    for (let x = 0; x < p.width; x++) {
      const i = y * p.width + x;
      const s = m.sector[i];
      if (s > 0) {
        let b = m.buildings.get(s);
        if (!b) {
          b = { index: s, name: p.legend.sector[s], tiles: 0, x0: x, y0: y, x1: x, y1: y, entrance: null };
          m.buildings.set(s, b);
        }
        b.tiles++;
        b.x0 = Math.min(b.x0, x);
        b.y0 = Math.min(b.y0, y);
        b.x1 = Math.max(b.x1, x);
        b.y1 = Math.max(b.y1, y);
      }
      if (m.object[i] > 0 && s > 0) {
        const addr = addressAt(m, x, y);
        if (addr && addr.split(":").length === 4) {
          const list = m.objects.get(addr) ?? [];
          list.push([x, y]);
          m.objects.set(addr, list);
        }
      }
    }
  }
  classify(m);
  return m;
}

function classify(m: TownMap) {
  const { width: w, height: h } = m;
  for (let i = 0; i < w * h; i++) {
    const x = i % w;
    const y = (i / w) | 0;
    const s = m.sector[i];
    if (m.collision[i]) {
      m.kind[i] = s > 0 ? KIND.WALL : KIND.NATURE;
    } else if (s === 0) {
      m.kind[i] = KIND.GRASS;
    } else if (s === m.plazaSector) {
      m.kind[i] = KIND.PLAZA;
    } else {
      const arena = addressAt(m, x, y, "arena");
      const obj = addressAt(m, x, y, "object");
      if (arena && m.outdoorArenas.has(arena)) {
        m.kind[i] = obj && m.groundObjects.has(obj) ? KIND.BED : KIND.LAWN;
      } else if (arena && /bathroom/i.test(arena)) {
        m.kind[i] = KIND.BATH;
      } else {
        m.kind[i] = KIND.FLOOR;
      }
    }
  }
  for (const tile of roadNetwork(m)) m.kind[tile[1] * w + tile[0]] = KIND.ROAD;
}

const DIRS: Tile[] = [
  [1, 0],
  [0, 1],
  [-1, 0],
  [0, -1],
];

function isStreet(m: TownMap, i: number): boolean {
  return !m.collision[i] && (m.sector[i] === 0 || m.sector[i] === m.plazaSector);
}

/** Front doors: the street tile next to each building closest to its middle. */
export function entrances(m: TownMap): Map<number, Tile> {
  const out = new Map<number, Tile>();
  const best = new Map<number, number>();
  const { width: w, height: h } = m;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = y * w + x;
      if (!isStreet(m, i) || m.sector[i] === m.plazaSector) continue;
      for (const [dx, dy] of DIRS) {
        const nx = x + dx;
        const ny = y + dy;
        if (nx < 0 || ny < 0 || nx >= w || ny >= h) continue;
        const j = ny * w + nx;
        const s = m.sector[j];
        if (s <= 0 || s === m.plazaSector || m.collision[j]) continue;
        const b = m.buildings.get(s)!;
        const d = Math.abs(x - (b.x0 + b.x1) / 2) + Math.abs(y - (b.y0 + b.y1) / 2);
        if (d < (best.get(s) ?? Infinity)) {
          best.set(s, d);
          out.set(s, [x, y]);
        }
      }
    }
  }
  for (const [s, t] of out) m.buildings.get(s)!.entrance = t;
  return out;
}

function bfs(m: TownMap, start: Tile): Int32Array {
  const { width: w, height: h } = m;
  const dist = new Int32Array(w * h).fill(-1);
  const queue = new Int32Array(w * h);
  let head = 0;
  let tail = 0;
  const s = start[1] * w + start[0];
  dist[s] = 0;
  queue[tail++] = s;
  while (head < tail) {
    const i = queue[head++];
    const x = i % w;
    const y = (i / w) | 0;
    for (const [dx, dy] of DIRS) {
      const nx = x + dx;
      const ny = y + dy;
      if (nx < 0 || ny < 0 || nx >= w || ny >= h) continue;
      const j = ny * w + nx;
      if (dist[j] < 0 && isStreet(m, j)) {
        dist[j] = dist[i] + 1;
        queue[tail++] = j;
      }
    }
  }
  return dist;
}

/** Shortest street path from a to b that prefers going straight (fewer turns). */
function straightPath(m: TownMap, a: Tile, b: Tile): Tile[] {
  const { width: w, height: h } = m;
  const n = w * h * 4;
  const cost = new Float64Array(n).fill(Infinity);
  const prev = new Int32Array(n).fill(-1);
  const heap: [number, number][] = [];
  const push = (c: number, s: number) => {
    heap.push([c, s]);
    let k = heap.length - 1;
    while (k > 0) {
      const p = (k - 1) >> 1;
      if (heap[p][0] <= heap[k][0]) break;
      [heap[p], heap[k]] = [heap[k], heap[p]];
      k = p;
    }
  };
  const pop = (): [number, number] => {
    const top = heap[0];
    const last = heap.pop()!;
    if (heap.length) {
      heap[0] = last;
      let k = 0;
      for (;;) {
        const l = 2 * k + 1;
        const r = l + 1;
        let s = k;
        if (l < heap.length && heap[l][0] < heap[s][0]) s = l;
        if (r < heap.length && heap[r][0] < heap[s][0]) s = r;
        if (s === k) break;
        [heap[s], heap[k]] = [heap[k], heap[s]];
        k = s;
      }
    }
    return top;
  };
  const start = a[1] * w + a[0];
  for (let d = 0; d < 4; d++) {
    cost[start * 4 + d] = 0;
    push(0, start * 4 + d);
  }
  const goal = b[1] * w + b[0];
  let end = -1;
  while (heap.length) {
    const [c, state] = pop();
    if (c > cost[state]) continue;
    const i = state >> 2;
    const dir = state & 3;
    if (i === goal) {
      end = state;
      break;
    }
    const x = i % w;
    const y = (i / w) | 0;
    for (let nd = 0; nd < 4; nd++) {
      const nx = x + DIRS[nd][0];
      const ny = y + DIRS[nd][1];
      if (nx < 0 || ny < 0 || nx >= w || ny >= h) continue;
      const j = ny * w + nx;
      if (!isStreet(m, j)) continue;
      const nc = c + 1 + (nd === dir ? 0 : 0.75);
      const ns = j * 4 + nd;
      if (nc < cost[ns]) {
        cost[ns] = nc;
        prev[ns] = state;
        push(nc, ns);
      }
    }
  }
  const path: Tile[] = [];
  for (let s = end; s >= 0; s = prev[s]) {
    const i = s >> 2;
    path.push([i % w, (i / w) | 0]);
  }
  return path.reverse();
}

/** Roads: a minimum spanning tree over the front doors (and the town square), two tiles wide. */
export function roadNetwork(m: TownMap): Tile[] {
  const doors = [...entrances(m).values()];
  if (m.plazaSector > 0) {
    const plaza = m.buildings.get(m.plazaSector);
    if (plaza) {
      const cx = Math.round((plaza.x0 + plaza.x1) / 2);
      const cy = Math.round((plaza.y0 + plaza.y1) / 2);
      if (isStreet(m, cy * m.width + cx)) doors.push([cx, cy]);
    }
  }
  if (doors.length < 2) return [];
  const dists = doors.map((d) => bfs(m, d));
  const inTree = new Set<number>([0]);
  const edges: [number, number][] = [];
  while (inTree.size < doors.length) {
    let best: [number, number, number] | null = null;
    for (const a of inTree) {
      for (let b = 0; b < doors.length; b++) {
        if (inTree.has(b)) continue;
        const d = dists[a][doors[b][1] * m.width + doors[b][0]];
        if (d >= 0 && (!best || d < best[2])) best = [a, b, d];
      }
    }
    if (!best) break; // some doors are unreachable from the rest
    inTree.add(best[1]);
    edges.push([best[0], best[1]]);
  }
  const road = new Set<number>();
  const w = m.width;
  for (const [a, b] of edges) {
    const path = straightPath(m, doors[a], doors[b]);
    for (let k = 0; k < path.length; k++) {
      const [x, y] = path[k];
      road.add(y * w + x);
      const next = path[k + 1] ?? path[k - 1];
      if (!next) continue;
      // widen to two tiles: the tile below a horizontal stretch, right of a vertical one
      const horizontal = next[1] === y;
      const side = horizontal ? (y + 1 < m.height ? (y + 1) * w + x : -1) : x + 1 < w ? y * w + x + 1 : -1;
      if (side >= 0 && isStreet(m, side)) road.add(side);
    }
  }
  const out: Tile[] = [];
  for (const i of road) if (m.sector[i] === 0) out.push([i % w, (i / w) | 0]);
  return out;
}

export function tileHash(x: number, y: number, salt = 0): number {
  let h = (x * 374761393 + y * 668265263 + salt * 2246822519) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
}

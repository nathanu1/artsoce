import type { Api } from "../api";
import { ApiError } from "../apiError";
import type { BuildCheck, Info, MapPayload, Poll, ResidentDetail } from "../types";
import { Player, type Timeline } from "./player";

// The demo build reads the files `ga export-demo` writes next to the page.
const BASE = "./demo/";
const files = new Map<string, Promise<unknown>>();

function load<T>(name: string): Promise<T> {
  let p = files.get(name);
  if (!p) {
    p = fetch(BASE + name).then((r) => {
      if (!r.ok) throw new ApiError(r.status, `the recording is missing ${name}`);
      return r.json();
    });
    p.catch(() => files.delete(name)); // let a later call retry
    files.set(name, p);
  }
  return p as Promise<T>;
}

const READ_ONLY = "this is a recording, so nothing in it can change. Run ga play to play the town yourself";

/** Where the recording opens: shortly before the first thing the player does. */
const OPEN_AT = 300;

let player: Promise<Player> | null = null;
/** The one player for the page (concurrent first calls share it). */
export function demoPlayer(): Promise<Player> {
  if (!player) {
    player = load<Timeline>("timeline.json").then((tl) => new Player(tl, OPEN_AT));
    player.catch(() => (player = null));
  }
  return player;
}

/** Memories are exported once per resident; the inspector's filters run here. */
function memories(rows: Record<string, unknown>[], query: URLSearchParams): Record<string, unknown>[] {
  const kind = query.get("kind");
  const q = query.get("q")?.toLowerCase();
  const limit = Number(query.get("limit") ?? 60);
  return rows.filter((m) => (!kind || m.kind === kind) && (!q || String(m.description ?? "").toLowerCase().includes(q))).slice(0, limit);
}

async function research<T>(path: string): Promise<T> {
  const data = await load<Record<string, unknown>>("research.json");
  const [route, search = ""] = path.split("?");
  const parts = route.split("/").map(decodeURIComponent);
  if (parts[0] === "agent" && parts[2] === "memories") {
    const rows = data[`agent/${parts[1]}/memories`] as Record<string, unknown>[] | undefined;
    if (!rows) throw new ApiError(404, "this resident is not in the recording");
    return memories(rows, new URLSearchParams(search)) as T;
  }
  const key = parts.join("/") + (search ? `?${search}` : "");
  if (!(key in data)) throw new ApiError(404, "this part of the run was not included in the recording");
  return data[key] as T;
}

export const demoApi: Api = {
  info: () => load<Info>("info.json"),
  map: () => load<MapPayload>("map.json"),
  poll: async (sinceStep: number, sinceFeed: number): Promise<Poll> => (await demoPlayer()).poll(sinceStep, sinceFeed),
  action: async () => {
    throw new ApiError(403, READ_ONLY);
  },
  validateBuild: async (): Promise<BuildCheck> => {
    throw new ApiError(403, READ_ONLY);
  },
  control: async (action, speed) => (await demoPlayer()).control(action, speed),
  resident: async (id: string): Promise<ResidentDetail> => ({ id, exchanges: [], conversations: [] }),
  object: async (address: string) => {
    const themes = await load<Record<string, string | null>>("objects.json");
    return { address, name: address.split(":").pop() ?? "", place: address.split(":").slice(1, 3), search_theme: themes[address] ?? null };
  },
  research,
};

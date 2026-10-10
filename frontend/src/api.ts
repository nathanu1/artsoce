import { ApiError } from "./apiError";
import { demoApi } from "./demo/api";
import { DEMO } from "./demo/flag";
import type { BuildCheck, BuildOp, Info, MapPayload, Poll, ResidentDetail } from "./types";

export { ApiError };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  } catch {
    throw new ApiError(0, "The town server is not answering.");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* keep the status text */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

const post = <T>(path: string, body: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(body) });

const liveApi = {
  info: () => request<Info>("/api/game/info"),
  map: () => request<MapPayload>("/api/game/map"),
  poll: (sinceStep: number, sinceFeed: number) => request<Poll>(`/api/game/poll?since_step=${sinceStep}&since_feed=${sinceFeed}`),
  action: (kind: string, payload: Record<string, unknown>) => post<{ seq: number; step: number }>("/api/game/action", { kind, payload }),
  validateBuild: (ops: BuildOp[]) => post<BuildCheck>("/api/game/validate-build", { ops }),
  control: (action: "pause" | "resume" | "speed" | "retry", speed?: string) => post<{ paused: boolean; speed: string; status: string }>("/api/game/control", { action, speed }),
  resident: (id: string) => request<ResidentDetail>(`/api/game/resident/${encodeURIComponent(id)}`),
  object: (address: string) => request<{ address: string; name: string; place: string[]; search_theme: string | null }>(`/api/game/object?address=${encodeURIComponent(address)}`),
  research: <T>(path: string) => request<T>(`/research/api/${path}`),
};

export type Api = typeof liveApi;

/** The town's server, or (in the demo build) a recording played back in the browser. */
export const api: Api = DEMO ? demoApi : liveApi;

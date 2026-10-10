import type { AgentFrame, FeedEvent, Frame, GameState, Poll, Schedule } from "../types";

/** What `ga export-demo` writes to demo/timeline.json. */
export interface Timeline {
  start: string;
  end: string;
  seconds_per_step: number;
  agents: string[];
  fields: string[];
  strings: string[];
  frames: [number, ...unknown[][]][];
  states: ({ step: number } & Partial<{ game: GameState; schedules: Record<string, Schedule>; objects: Poll["objects"] }>)[];
  feed: (FeedEvent & { step: number })[];
}

type Speed = "slow" | "normal" | "fast";
const RATES: Record<Speed, number> = { slow: 2, normal: 6, fast: 30 }; // steps per second, as in `ga play`
const TABLED = new Set(["activity", "kind", "address", "conversation", "partner"]);
const TALK_WINDOW = 360 * 3; // after a jump, Town Talk shows the last three game hours

/** Latest entry at or before `step` in a list sorted by step. */
function latest<T extends { step: number }>(list: T[], step: number): T | undefined {
  let lo = 0;
  let hi = list.length - 1;
  let found: T | undefined;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (list[mid].step <= step) {
      found = list[mid];
      lo = mid + 1;
    } else hi = mid - 1;
  }
  return found;
}

/**
 * Plays a recorded town in the browser: the same answers `ga play --replay` would give to the
 * interface, computed from the exported timeline. Time runs while playing; seeking jumps.
 */
export class Player {
  readonly first: number;
  readonly last: number;
  private t: number;
  private playing = true;
  private speed: Speed = "normal";
  private epoch = 0;
  private served = -1;
  private tick = 0;
  private readonly startMs: number;
  private readonly states: Record<"game" | "schedules" | "objects", { step: number; value: unknown }[]>;
  private readonly frameSteps: { step: number; i: number }[];

  constructor(
    private readonly tl: Timeline,
    startAt?: number,
    private readonly now: () => number = () => performance.now(),
  ) {
    this.first = tl.frames[0][0];
    this.last = tl.frames[tl.frames.length - 1][0];
    this.t = Math.min(this.last, Math.max(this.first, startAt ?? this.first));
    this.startMs = Date.parse(`${tl.start}Z`);
    this.frameSteps = tl.frames.map((f, i) => ({ step: f[0], i }));
    this.states = { game: [], schedules: [], objects: [] };
    for (const s of tl.states) for (const k of ["game", "schedules", "objects"] as const) if (k in s) this.states[k].push({ step: s.step, value: s[k] });
    this.tick = this.now();
  }

  timeAt(step: number): string {
    return new Date(this.startMs + Math.max(0, step) * this.tl.seconds_per_step * 1000).toISOString().slice(0, 19);
  }

  get step(): number {
    return Math.floor(this.t);
  }

  /** Everything that happened in the recording, in order (for the timeline's moments). */
  get events(): readonly (FeedEvent & { step: number })[] {
    return this.tl.feed;
  }

  private advance(): void {
    const at = this.now();
    const dt = Math.min(1, (at - this.tick) / 1000); // a hidden tab does not fast-forward
    this.tick = at;
    if (!this.playing) return;
    this.t = Math.min(this.last, this.t + dt * RATES[this.speed]);
    if (this.t >= this.last) this.playing = false;
  }

  private frame(step: number): Frame {
    const row = this.tl.frames[(latest(this.frameSteps, step) ?? this.frameSteps[0]).i];
    const agents: Record<string, AgentFrame> = {};
    this.tl.agents.forEach((aid, k) => {
      const cells = row[k + 1] as unknown[];
      const a: Record<string, unknown> = {};
      this.tl.fields.forEach((f, j) => {
        const v = cells[j];
        a[f] = TABLED.has(f) ? (typeof v === "number" && v >= 0 ? this.tl.strings[v] : null) : v;
      });
      agents[aid] = a as unknown as AgentFrame;
    });
    return { step: row[0], time: this.timeAt(row[0]), agents };
  }

  control(action: string, speed?: string): { paused: boolean; speed: string; status: string } {
    this.advance();
    if (action === "pause") this.playing = false;
    else if (action === "resume") {
      if (this.t >= this.last) this.seek(this.first); // play the recording again
      this.playing = true;
    } else if (action === "speed" && speed && speed in RATES) this.speed = speed as Speed;
    return { paused: !this.playing, speed: this.speed, status: this.status };
  }

  seek(step: number): void {
    this.t = Math.min(this.last, Math.max(this.first, step));
    this.epoch += 1; // the interface starts over from here
    this.tick = this.now();
  }

  private get status(): string {
    return this.t >= this.last ? "finished" : this.playing ? "running" : "paused";
  }

  poll(sinceStep: number, sinceFeed: number): Poll {
    this.advance();
    const cur = this.step;
    const fresh = this.served !== this.epoch;
    this.served = this.epoch;
    const frame = this.frame(cur);
    const upTo = this.tl.feed.filter((e) => e.step <= cur);
    const feedSeq = upTo.length ? upTo[upTo.length - 1].seq : 0;
    // after a jump only the recent conversations come back (for Town Talk), never old toasts
    const feed = fresh ? upTo.filter((e) => e.kind === "conversation" && e.step > cur - TALK_WINDOW) : upTo.filter((e) => e.seq > sinceFeed);
    const pick = <T,>(k: "game" | "schedules" | "objects") => (latest(this.states[k], cur)?.value ?? null) as T;
    return {
      epoch: this.epoch,
      status: this.status,
      paused: !this.playing,
      speed: this.speed,
      replay: true,
      error: null,
      thinking: {},
      clock: { step: cur, time: this.timeAt(cur), end: this.tl.end },
      frames: fresh || frame.step > sinceStep ? [frame] : [],
      feed,
      feed_seq: feedSeq,
      game: pick<GameState | null>("game"),
      schedules: pick<Record<string, Schedule> | null>("schedules"),
      objects: pick<Poll["objects"]>("objects"),
      ledger: null,
    };
  }
}

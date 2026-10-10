import { describe, expect, it } from "vitest";
import { Player, type Timeline } from "../src/demo/player";

function timeline(): Timeline {
  const fields = ["x", "y", "activity", "kind", "address", "sleeping", "conversation", "partner", "path_left"];
  const frames = Array.from({ length: 100 }, (_, i) => [i, [i, 5, 0, 1, -1, false, -1, -1, 0]] as [number, unknown[]]);
  return {
    start: "2023-02-13T07:00:00",
    end: "2023-02-13T07:16:30",
    seconds_per_step: 10,
    agents: ["klaus_mueller"],
    fields,
    strings: ["reading", "move"],
    frames,
    states: [
      { step: 0, game: { pulse: { points: 0 } } as never, schedules: {}, objects: {} },
      { step: 50, game: { pulse: { points: 9 } } as never },
    ],
    feed: [
      { seq: 1, step: 0, kind: "welcome" },
      { seq: 2, step: 20, kind: "conversation", participants: ["a", "b"] },
      { seq: 3, step: 40, kind: "chat", agent_id: "klaus_mueller" },
    ] as never,
  };
}

describe("the demo player", () => {
  it("plays at the chosen speed and stops at the end", () => {
    let ms = 0;
    const p = new Player(timeline(), 0, () => ms);
    expect(p.poll(-2, 0).clock?.step).toBe(0);
    ms += 1000; // normal speed: 6 steps a second
    const a = p.poll(0, 0);
    expect(a.clock?.step).toBe(6);
    expect(a.frames[0].agents.klaus_mueller).toMatchObject({ x: 6, activity: "reading", kind: "move", address: null });
    p.control("speed", "fast");
    ms += 5000; // 30 steps a second, capped at a second per tick
    expect(p.poll(6, 0).clock?.step).toBe(36);
    for (let i = 0; i < 5; i++) {
      ms += 1000;
      p.poll(0, 0);
    }
    const end = p.poll(0, 0);
    expect(end.clock?.step).toBe(99);
    expect(end.status).toBe("finished");
    expect(end.paused).toBe(true);
    p.control("resume"); // plays again from the start
    expect(p.poll(0, 3).clock?.step).toBe(0);
  });

  it("delivers events once, in order, and only up to the current step", () => {
    let ms = 0;
    const p = new Player(timeline(), 0, () => ms);
    p.poll(-2, 0);
    ms += 5000;
    p.control("speed", "fast"); // the tick above was at normal speed: 6 steps
    ms += 1000;
    const r = p.poll(0, 1);
    expect(r.clock?.step).toBe(36);
    expect(r.feed.map((e) => e.seq)).toEqual([2]);
    expect(r.feed_seq).toBe(2);
  });

  it("jumps: a new epoch, the state of that moment and recent talk only", () => {
    let ms = 0;
    const p = new Player(timeline(), 0, () => ms);
    p.poll(-2, 0);
    p.seek(60);
    const r = p.poll(0, 1);
    expect(r.epoch).toBe(1);
    expect(r.clock?.step).toBe(60);
    expect(r.frames[0].step).toBe(60);
    expect((r.game as unknown as { pulse: { points: number } }).pulse.points).toBe(9);
    expect(r.feed.map((e) => e.kind)).toEqual(["conversation"]); // no toast for the old chat
    expect(r.feed_seq).toBe(3);
    const next = p.poll(60, 3);
    expect(next.epoch).toBe(1);
    expect(next.feed).toEqual([]);
  });
});

import { FilmStrip } from "@phosphor-icons/react";
import { useEffect, useMemo, useState } from "react";
import { formatTime } from "../lib/time";
import { useTown } from "../store";
import { demoPlayer } from "./api";
import type { Player } from "./player";

/** Jumps land three game minutes early (three seconds at normal speed) so the moment plays out. */
const LEAD = 18;

interface Moment {
  step: number;
  label: string;
}

/** The recording's timeline: drag to any time, or jump to a moment worth seeing. */
export function DemoBar() {
  const info = useTown((s) => s.info)!;
  const clock = useTown((s) => s.poll?.clock);
  const [player, setPlayer] = useState<Player | null>(null);
  useEffect(() => {
    let alive = true;
    void demoPlayer().then((p) => alive && setPlayer(p));
    return () => {
      alive = false;
    };
  }, []);

  const moments = useMemo<Moment[]>(() => {
    if (!player) return [];
    const name = (id: unknown) => info.residents.find((r) => r.id === id)?.first_name ?? "someone";
    const out: Moment[] = [];
    for (const e of player.events) {
      const kind = e.kind;
      const label =
        kind === "chat"
          ? `You chat with ${name(e.agent_id)}`
          : kind === "gift"
            ? `A gift for ${name(e.agent_id)}`
            : kind === "request"
              ? "Residents make wishes"
              : kind === "build"
                ? "You build"
                : kind === "delivered"
                  ? `${name(e.agent_id)}’s wish comes true`
                  : kind === "level_up"
                    ? `Town Pulse: ${String(e.name ?? "level up")}`
                    : kind === "conversation"
                      ? `${((e.participants as string[]) ?? []).map(name).join(" and ")} talk`
                      : kind === "whisper"
                        ? `Inner voice for ${name(e.agent_id)}`
                        : null;
      if (!label) continue;
      if (out.length && out[out.length - 1].label === label && e.step - out[out.length - 1].step < 30) continue; // one chip per burst
      out.push({ step: e.step, label });
    }
    return out;
  }, [player, info]);

  if (!player || !clock) return null;
  const jump = (step: number) => player.seek(step);
  return (
    <div className="pointer-events-auto panel flex w-[min(92vw,520px)] flex-col gap-1.5 px-3 py-2">
      <div className="flex items-center gap-2">
        <FilmStrip size={16} weight="fill" color="#e2629b" aria-hidden="true" />
        <span className="font-display text-sm font-bold">Recording</span>
        <span className="min-w-0 truncate text-xs text-[var(--muted)]">mock model, so residents’ words are placeholders</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="tabular text-[11px] font-bold text-[var(--muted)]">{formatTime(player.timeAt(player.first))}</span>
        <label htmlFor="demo-time" className="sr-only">
          Time in the recording
        </label>
        <input
          id="demo-time"
          name="time"
          type="range"
          min={player.first}
          max={player.last}
          step={6}
          value={Math.max(player.first, clock.step)}
          aria-valuetext={formatTime(clock.time)}
          onChange={(e) => jump(Number(e.target.value))}
          className="h-2 min-w-0 flex-1 cursor-pointer accent-[var(--color-sun)]"
        />
        <span className="tabular text-[11px] font-bold text-[var(--muted)]">{formatTime(player.timeAt(player.last))}</span>
      </div>
      {moments.length ? (
        <div className="scroll-thin -mx-1 flex gap-1 overflow-x-auto px-1 py-0.5" role="group" aria-label="Moments in the recording">
          {moments.map((m) => (
            <button
              key={`${m.step}-${m.label}`}
              type="button"
              onClick={() => jump(Math.max(player.first, m.step - LEAD))}
              className={`shrink-0 whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-bold transition-colors ${clock.step >= m.step ? "bg-sun/25" : "bg-[var(--panel-2)] hover:bg-[var(--panel-hover)]"}`}
              title={`Jump to just before ${formatTime(player.timeAt(m.step))}`}
            >
              <span className="tabular">{formatTime(player.timeAt(m.step))}</span> {m.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

import { ArrowClockwise, ArrowCounterClockwise, CloudMoon, FastForward, Flask, Hammer, Minus, Notebook, Pause, Play, Plus, Sun, SunHorizon, Warning } from "@phosphor-icons/react";
import { api } from "../api";
import { formatDay, formatNumber, formatTime, hourOf } from "../lib/time";
import { useTown } from "../store";
import { Button, IconButton, MotifCount } from "./ui";

function scene() {
  return (window as unknown as { __town?: { rotate: (d: 1 | -1) => void; zoomBy: (f: number) => void } }).__town;
}

export function Hud() {
  const info = useTown((s) => s.info)!;
  const poll = useTown((s) => s.poll);
  const mode = useTown((s) => s.mode);
  const setMode = useTown((s) => s.setMode);
  const openNotebook = useTown((s) => s.openNotebook);
  const toast = useTown((s) => s.toast);
  const game = poll?.game;
  const pulse = game?.pulse;
  const clock = poll?.clock;
  const hour = clock ? hourOf(clock.time) : 9;
  const TimeIcon = hour >= 6 && hour < 17.5 ? Sun : hour >= 17.5 && hour < 20 ? SunHorizon : CloudMoon;
  const thinking = Object.keys(poll?.thinking ?? {});
  const nextLevel = pulse ? info.content.levels.find((l) => l.level === pulse.level + 1) : undefined;
  const progress = pulse ? (pulse.next_at ? (pulse.points - (info.content.levels.find((l) => l.level === pulse.level)?.points ?? 0)) / Math.max(1, pulse.next_at - (info.content.levels.find((l) => l.level === pulse.level)?.points ?? 0)) : 1) : 0;

  const control = async (action: "pause" | "resume" | "speed" | "retry", speed?: string) => {
    try {
      await api.control(action, speed);
    } catch (e) {
      toast({ tone: "warn", title: "The clock did not change", body: (e as Error).message });
    }
  };

  return (
    <>
      {/* town badge */}
      <header className="pointer-events-auto panel absolute left-3 top-3 flex max-w-[calc(100vw-196px)] items-center gap-3 px-3 py-2 sm:left-4 sm:top-4 sm:max-w-none">
        <div className="flex size-11 items-center justify-center rounded-full bg-sun font-display text-xl font-bold text-[#2a2838]" aria-label={`Town Pulse level ${pulse?.level ?? 1}`}>
          {pulse?.level ?? 1}
        </div>
        <div className="min-w-0">
          <h1 className="font-display text-lg font-bold leading-tight">Smallville</h1>
          <div className="flex min-w-0 items-center gap-2">
            <span className="truncate text-xs font-bold text-[var(--muted)]">{pulse?.name ?? "Sleepy Hamlet"}</span>
            <span className="relative hidden h-2 w-20 shrink-0 overflow-hidden rounded-full bg-[var(--panel-2)] sm:block" role="meter" aria-label="Town Pulse progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress * 100)}>
              <span className="absolute inset-y-0 left-0 rounded-full bg-[linear-gradient(90deg,#e2629b,#f2792b)]" style={{ width: `${Math.round(progress * 100)}%` }} />
            </span>
            <span className="tabular hidden text-xs font-bold text-[var(--muted)] sm:inline" title={nextLevel ? `${formatNumber(pulse?.points ?? 0)} of ${formatNumber(pulse?.next_at ?? 0)} Pulse points to ${nextLevel.name}` : "Highest level reached"}>
              {formatNumber(pulse?.points ?? 0)}
              {pulse?.next_at ? <span className="font-semibold">/{formatNumber(pulse.next_at)}</span> : null}
            </span>
          </div>
        </div>
      </header>

      {/* clock and speed */}
      <div className="pointer-events-auto panel absolute left-3 top-[76px] flex items-center gap-2 px-2 py-1.5 md:left-1/2 md:top-4 md:-translate-x-1/2">
        <TimeIcon size={22} weight="fill" color={hour >= 6 && hour < 20 ? "#f2a33a" : "#8ea6ff"} aria-hidden="true" />
        <div className="px-1 text-center">
          <div className="font-display text-base font-bold leading-tight tabular">{clock ? formatTime(clock.time) : "…"}</div>
          <div className="text-[11px] font-bold text-[var(--muted)]">{clock ? formatDay(clock.time) : "Waking up…"}</div>
        </div>
        {poll?.replay ? null : (
          <>
            <IconButton label={poll?.paused ? "Play" : "Pause"} icon={poll?.paused ? Play : Pause} onClick={() => control(poll?.paused ? "resume" : "pause")} disabled={!poll || poll.status === "finished" || !!poll.error} />
            <div className="flex rounded-full bg-[var(--panel-2)] p-1" role="group" aria-label="Speed">
              {(["slow", "normal", "fast"] as const).map((s) => (
                <button
                  key={s}
                  type="button"
                  aria-pressed={poll?.speed === s}
                  aria-label={s === "fast" ? "Fast" : undefined}
                  title={s === "fast" ? "Fast" : undefined}
                  onClick={() => control("speed", s)}
                  className={`rounded-full px-2.5 py-1 font-display text-xs font-semibold capitalize transition-colors ${poll?.speed === s ? "bg-sun text-[#2a2838]" : "hover:bg-[var(--panel-3)]"}`}
                >
                  {s === "fast" ? <FastForward size={14} weight="fill" aria-hidden="true" /> : s}
                </button>
              ))}
            </div>
          </>
        )}
        {poll?.replay ? (
          <IconButton label={poll?.paused ? "Play the replay" : "Pause the replay"} icon={poll?.paused ? Play : Pause} onClick={() => control(poll?.paused ? "resume" : "pause")} />
        ) : null}
      </div>

      {/* right controls */}
      <nav className="pointer-events-auto panel absolute right-3 top-3 flex items-center gap-1.5 p-1.5 sm:right-4 sm:top-4" aria-label="Town tools">
        <IconButton label="Notebook (N)" icon={Notebook} onClick={() => openNotebook()} />
        {poll?.replay ? null : <IconButton label={mode === "build" ? "Leave build mode (B)" : "Build and decorate (B)"} icon={Hammer} active={mode === "build"} onClick={() => setMode(mode === "build" ? "play" : "build")} />}
        <a href="/inspector" target="_blank" rel="noreferrer" aria-label="Research inspector (opens a new tab)" title="Research inspector" className="inline-flex size-11 items-center justify-center rounded-full bg-[var(--panel-2)] text-[var(--text)] hover:bg-[var(--panel-3)]">
          <Flask size={21} weight="bold" aria-hidden="true" />
        </a>
      </nav>

      {/* camera */}
      <div className="pointer-events-auto absolute bottom-24 right-3 flex flex-col gap-1.5 sm:bottom-6 sm:right-4" role="group" aria-label="Camera">
        <IconButton label="Zoom in (+)" icon={Plus} onClick={() => scene()?.zoomBy(1.25)} className="shadow-md" />
        <IconButton label="Zoom out (-)" icon={Minus} onClick={() => scene()?.zoomBy(0.8)} className="shadow-md" />
        <IconButton label="Turn left (Q)" icon={ArrowCounterClockwise} onClick={() => scene()?.rotate(-1)} className="shadow-md" />
        <IconButton label="Turn right (E)" icon={ArrowClockwise} onClick={() => scene()?.rotate(1)} className="shadow-md" />
      </div>

      {/* motif pouch */}
      {mode === "play" && game ? (
        <button type="button" onClick={() => openNotebook("collections")} className="pointer-events-auto panel absolute bottom-3 left-3 hidden flex-wrap items-center gap-1 p-1.5 sm:bottom-4 sm:left-4 lg:flex" aria-label="Your motifs, open the collection">
          {info.content.themes.map((t) => (
            <MotifCount key={t.id} theme={t} count={game.theme_counts[t.id] ?? 0} />
          ))}
        </button>
      ) : null}

      {/* status */}
      <div className="pointer-events-none absolute inset-x-3 top-[140px] flex flex-col items-center gap-2 md:inset-x-auto md:left-1/2 md:top-[84px] md:-translate-x-1/2" aria-live="polite">
        {info.mode === "mock" ? <span className="rounded-full bg-[var(--panel)]/90 px-3 py-1 text-xs font-bold text-[var(--muted)] shadow">MOCK model: residents' words are placeholders</span> : null}
        {poll?.replay ? <span className="rounded-full bg-[var(--panel)]/90 px-3 py-1 text-xs font-bold text-[var(--muted)] shadow">Replay: no model calls, view only</span> : null}
        {thinking.length && info.mode === "live" ? (
          <span className="rounded-full bg-[var(--panel)]/90 px-3 py-1 text-xs font-bold text-[var(--muted)] shadow">
            {info.llm.model} is thinking for {thinking.map((id) => info.residents.find((r) => r.id === id)?.first_name ?? "the town").join(", ")}…
          </span>
        ) : null}
        {poll?.error ? (
          <div className="pointer-events-auto panel flex max-w-[min(92vw,560px)] items-start gap-3 px-4 py-3">
            <Warning size={22} weight="fill" color="#d9534f" aria-hidden="true" className="mt-0.5 shrink-0" />
            <div className="min-w-0">
              <p className="font-display font-bold">The town paused at its last save</p>
              <p className="break-words text-sm text-[var(--muted)]">{poll.error.split("\n")[0]}</p>
              {info.llm.kind === "ollama" ? <p className="mt-1 text-sm text-[var(--muted)]">Start Ollama (`ollama serve`) and check the model is pulled, then retry.</p> : null}
            </div>
            {poll.replay ? null : (
              <Button tone="primary" onClick={() => control("retry")}>
                Retry
              </Button>
            )}
          </div>
        ) : null}
      </div>
    </>
  );
}

import { AnimatePresence } from "motion/react";
import { useEffect } from "react";
import { api } from "./api";
import { BuildPanel } from "./components/BuildPanel";
import { Hud } from "./components/Hud";
import { Inspector } from "./components/Inspector";
import { Notebook } from "./components/Notebook";
import { ObjectCard } from "./components/ObjectCard";
import { ChatSheet, ResidentCard } from "./components/ResidentCard";
import { Toasts, TownTalk } from "./components/Toasts";
import { TownView } from "./components/TownView";
import { decodeMap } from "./lib/map";
import { hourOf } from "./lib/time";
import { useTown } from "./store";

function scene() {
  return (window as unknown as { __town?: { rotate: (d: 1 | -1) => void; zoomBy: (f: number) => void; panPixels: (x: number, y: number) => void } }).__town;
}

function usePolling(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    let timer = 0;
    let failures = 0;
    const tick = async () => {
      const st = useTown.getState();
      try {
        const p = await api.poll(st.epoch === useTown.getState().poll?.epoch ? st.sinceStep : -2, st.sinceFeed);
        if (!alive) return;
        useTown.getState().ingest(p);
        failures = 0;
        timer = window.setTimeout(tick, p.paused || p.error ? 600 : 220);
      } catch {
        failures++;
        if (failures === 3) useTown.getState().toast({ tone: "warn", title: "Lost the town server", body: "Is `ga play` still running? Retrying…" });
        timer = window.setTimeout(tick, Math.min(5000, 500 * failures));
      }
    };
    void tick();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [enabled]);
}

function useShortcuts() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.closest("input, textarea, select, [role=dialog]")) return;
      const st = useTown.getState();
      const k = e.key.toLowerCase();
      if (st.mode === "build" && ["r", "d", "delete", "backspace"].includes(k)) return; // build panel handles these
      if (k === "n") st.notebook.open ? st.closeNotebook() : st.openNotebook();
      else if (k === "b" && !st.poll?.replay) st.setMode(st.mode === "build" ? "play" : "build");
      else if (k === "q") scene()?.rotate(-1);
      else if (k === "e") scene()?.rotate(1);
      else if (k === "+" || k === "=") scene()?.zoomBy(1.2);
      else if (k === "-") scene()?.zoomBy(0.83);
      else if (k === "w" || k === "arrowup") scene()?.panPixels(0, 60);
      else if (k === "s" || k === "arrowdown") scene()?.panPixels(0, -60);
      else if (k === "a" || k === "arrowleft") scene()?.panPixels(60, 0);
      else if (k === "d" || k === "arrowright") scene()?.panPixels(-60, 0);
      else if (k === " ") {
        e.preventDefault();
        if (st.poll && !st.poll.error) void api.control(st.poll.paused ? "resume" : "pause").catch(() => undefined);
      } else if (k === "escape") {
        st.select(null);
        st.setFollow(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}

function Loading({ error }: { error: string | null }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 bg-[linear-gradient(180deg,var(--sky-top),var(--sky-bottom))] p-6 text-center">
      <div className="panel flex max-w-md flex-col items-center gap-3 px-8 py-7">
        <span className="flex size-16 items-center justify-center rounded-full bg-sun font-display text-3xl font-bold text-[#2a2838]" aria-hidden="true">
          S
        </span>
        <h1 className="font-display text-2xl font-bold">Smallville Lab</h1>
        {error ? (
          <>
            <p className="text-[var(--muted)]">{error}</p>
            <p className="text-sm text-[var(--muted)]">
              Start the town with <code className="rounded bg-[var(--panel-2)] px-1.5">ga play --config configs/town_ollama.yaml</code>, then reload this page.
            </p>
          </>
        ) : (
          <>
            <p className="text-[var(--muted)]" aria-live="polite">
              Waking up the town…
            </p>
            <div className="h-2 w-48 overflow-hidden rounded-full bg-[var(--panel-2)]">
              <div className="h-full w-1/3 animate-pulse rounded-full bg-sun" />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Town() {
  const info = useTown((s) => s.info);
  const map = useTown((s) => s.map);
  const bootError = useTown((s) => s.bootError);
  const selection = useTown((s) => s.selection);
  const chatWith = useTown((s) => s.chatWith);
  const mode = useTown((s) => s.mode);
  const notebookOpen = useTown((s) => s.notebook.open);
  const clock = useTown((s) => s.poll?.clock);

  useEffect(() => {
    let alive = true;
    Promise.all([api.info(), api.map()])
      .then(([info, payload]) => alive && useTown.getState().boot(info, decodeMap(payload)))
      .catch((e) => alive && useTown.getState().bootFailed((e as Error).message));
    return () => {
      alive = false;
    };
  }, []);
  usePolling(!!info);
  useShortcuts();

  // sky follows the town's clock
  useEffect(() => {
    if (!clock) return;
    const h = hourOf(clock.time);
    const night = h < 5.5 || h >= 20;
    const dusk = (h >= 17.5 && h < 20) || (h >= 5.5 && h < 7);
    const root = document.documentElement.style;
    root.setProperty("--sky-top", night ? "#1c2a4f" : dusk ? "#f3a37f" : "#8fd0f2");
    root.setProperty("--sky-bottom", night ? "#3a4d78" : dusk ? "#ffd9a8" : "#e6f6fd");
  }, [clock]);

  if (!info || !map) return <Loading error={bootError} />;
  return (
    <div className="relative h-full overflow-hidden bg-[linear-gradient(180deg,var(--sky-top),var(--sky-bottom))] transition-[background] duration-1000">
      <TownView />
      <div className="pointer-events-none absolute inset-0 z-10">
        {mode === "build" ? <BuildPanel /> : <Hud />}
        {mode === "play" ? <TownTalk /> : null}
        <AnimatePresence>
          {mode === "play" && selection?.kind === "resident" ? <ResidentCard key={selection.id} id={selection.id} /> : null}
          {mode === "play" && selection?.kind === "object" ? <ObjectCard key={selection.address} address={selection.address} /> : null}
          {mode === "play" && selection?.kind === "item" ? <ObjectCard key={selection.id} itemId={selection.id} /> : null}
          {mode === "play" && chatWith ? <ChatSheet key={`chat-${chatWith}`} id={chatWith} /> : null}
        </AnimatePresence>
      </div>
      {notebookOpen ? <Notebook /> : null}
      <Toasts />
    </div>
  );
}

export default function App() {
  return window.location.pathname.startsWith("/inspector") ? <Inspector /> : <Town />;
}

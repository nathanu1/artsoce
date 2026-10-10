import { AnimatePresence } from "motion/react";
import { useEffect } from "react";
import { api } from "./api";
import { BuildPanel } from "./components/BuildPanel";
import { Hud } from "./components/Hud";
import { Inspector } from "./components/Inspector";
import { Notebook } from "./components/Notebook";
import { ObjectCard } from "./components/ObjectCard";
import { ResidentCard } from "./components/ResidentCard";
import { Toasts, TownTalk } from "./components/Toasts";
import { TownView } from "./components/TownView";
import { decodeMap } from "./lib/map";
import { DEMO } from "./demo/flag";
import { Welcome } from "./demo/Welcome";
import { replaceQuery, useView } from "./lib/route";
import { hourOf } from "./lib/time";
import { useTown, type NotebookTab } from "./store";

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
        if (failures === 3) useTown.getState().toast({ tone: "warn", title: "Lost the town server", body: "Check that \u201Cga play\u201D is still running. Retrying…" });
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
      if (e.metaKey || e.ctrlKey || e.altKey) return; // leave browser and system shortcuts alone
      const target = e.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [role=dialog]")) return;
      const st = useTown.getState();
      const k = e.key.toLowerCase();
      // Space belongs to whatever control has focus; only the town itself pauses on Space
      const onControl = !!target?.closest("button, a, [role=tab], [tabindex]");
      if (st.mode === "build" && ["r", "d", "p", "enter", "delete", "backspace"].includes(k)) return; // the build panel handles these
      const placing = st.mode === "build" && ((st.tool === "place" && !!st.catalogId) || (st.tool === "template" && !!st.templateId));
      if (placing && k.startsWith("arrow")) return; // arrows move the placement cursor instead of the view
      if (k === "n") st.notebook.open ? st.closeNotebook() : st.openNotebook();
      else if (k === "l" && st.mode === "play") st.setLook(!st.look);
      else if (k === "b" && !st.poll?.replay) st.setMode(st.mode === "build" ? "play" : "build");
      else if (k === "q") scene()?.rotate(-1);
      else if (k === "e") scene()?.rotate(1);
      else if (k === "+" || k === "=") scene()?.zoomBy(1.2);
      else if (k === "-") scene()?.zoomBy(0.83);
      else if (k === "w" || k === "arrowup") scene()?.panPixels(0, 60);
      else if (k === "s" || k === "arrowdown") scene()?.panPixels(0, -60);
      else if (k === "a" || k === "arrowleft") scene()?.panPixels(60, 0);
      else if (k === "d" || k === "arrowright") scene()?.panPixels(-60, 0);
      else if (k === " " && !onControl) {
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
        <h1 className="font-display text-2xl font-bold" translate="no">
          Smallville Lab
        </h1>
        <div aria-live="polite" className="flex flex-col items-center gap-3">
          {error ? (
            <>
              <p className="text-[var(--muted)]">{error}</p>
              <p className="text-sm text-[var(--muted)]">
                Start the town with{" "}
                <code className="rounded bg-[var(--panel-2)] px-1.5" translate="no">
                  ga play --config configs/town_ollama.yaml
                </code>
                , then reload this page.
              </p>
            </>
          ) : (
            <p className="text-[var(--muted)]">Waking up the town…</p>
          )}
        </div>
        {error ? null : (
          <div className="h-2 w-48 overflow-hidden rounded-full bg-[var(--panel-2)]" aria-hidden="true">
            <div className="h-full w-1/3 animate-pulse rounded-full bg-sun" />
          </div>
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

  // sky follows the town's clock (and stays dim in dark mode); the browser chrome follows the sky
  const hour = clock ? Math.floor(hourOf(clock.time) * 4) / 4 : null;
  useEffect(() => {
    if (hour === null) return;
    const forced = document.documentElement.dataset.theme;
    const dark = forced === "dark" || (forced !== "light" && (window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false));
    const night = hour < 5.5 || hour >= 20;
    const dusk = (hour >= 17.5 && hour < 20) || (hour >= 5.5 && hour < 7);
    const [top, bottom] = night ? ["#1c2a4f", "#3a4d78"] : dusk ? (dark ? ["#5a3b4a", "#7a5560"] : ["#f3a37f", "#ffd9a8"]) : dark ? ["#1d2a4a", "#3b4f74"] : ["#8fd0f2", "#e6f6fd"];
    const root = document.documentElement.style;
    root.setProperty("--sky-top", top);
    root.setProperty("--sky-bottom", bottom);
    for (const meta of document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')) meta.content = top;
  }, [hour]);

  // the notebook's page lives in the URL (?notebook=collections), so it can be linked and reloaded
  const notebookTab = useTown((s) => s.notebook.tab);
  useEffect(() => {
    const tab = new URLSearchParams(window.location.search).get("notebook");
    if (tab && ["requests", "collections", "residents", "town"].includes(tab)) useTown.getState().openNotebook(tab as NotebookTab);
  }, []);
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (notebookOpen) q.set("notebook", notebookTab);
    else q.delete("notebook");
    replaceQuery(q);
  }, [notebookOpen, notebookTab]);

  if (!info || !map) return <Loading error={bootError} />;
  return (
    <div className="relative h-full overflow-hidden bg-[linear-gradient(180deg,var(--sky-top),var(--sky-bottom))]">
      <main className="absolute inset-0" inert={notebookOpen || undefined}>
        <TownView />
        <div className="pointer-events-none absolute inset-0 z-10">
          {mode === "build" ? <BuildPanel /> : <Hud />}
          {mode === "play" && !selection ? <TownTalk /> : null}
          {DEMO && !selection ? <Welcome /> : null}
          <AnimatePresence>
            {mode === "play" && selection?.kind === "resident" ? <ResidentCard key={selection.id} id={selection.id} /> : null}
            {mode === "play" && selection?.kind === "object" ? <ObjectCard key={selection.address} address={selection.address} /> : null}
            {mode === "play" && selection?.kind === "item" ? <ObjectCard key={selection.id} itemId={selection.id} /> : null}
          </AnimatePresence>
        </div>
      </main>
      {notebookOpen ? <Notebook /> : null}
      <Toasts />
    </div>
  );
}

export default function App() {
  return useView() === "inspector" ? <Inspector /> : <Town />;
}

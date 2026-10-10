import { Check, ExclamationMark, MoonStars } from "@phosphor-icons/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { footprint, push, shownItems, templateOps } from "../lib/build";
import { activityIcon, activityLabel } from "../lib/icons";
import { failureBody } from "../lib/text";
import { isBefore, minutesBetween } from "../lib/time";
import { themePaints, TownScene, type GhostPart, type OverlayLabel, type OverlayPoint } from "../scene/TownScene";
import { useTown } from "../store";
import type { BuildOp, Poll, Tile } from "../types";

// stable fallbacks: a selector that returns a fresh {} or [] makes React re-render forever
const NO_THINKING: Poll["thinking"] = {};

const prefersReduced = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

/** Which line of a conversation is being said at sim time `now`. */
function currentLine(c: { lines: { speaker: string; text: string }[]; startedAt: string; endedAt: string }, now: string) {
  if (!c.lines.length || isBefore(now, c.startedAt) || !isBefore(now, c.endedAt)) return null;
  const total = Math.max(0.5, minutesBetween(c.startedAt, c.endedAt));
  const idx = Math.min(c.lines.length - 1, Math.floor((minutesBetween(c.startedAt, now) / total) * c.lines.length));
  return c.lines[idx];
}

export function TownView() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<TownScene | null>(null);
  const bubbleRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const labelLayer = useRef<HTMLDivElement>(null);
  const info = useTown((s) => s.info)!;
  const map = useTown((s) => s.map)!;
  const frame = useTown((s) => s.frame);
  const game = useTown((s) => s.poll?.game ?? null);
  const clock = useTown((s) => s.poll?.clock ?? null);
  const thinking = useTown((s) => s.poll?.thinking ?? NO_THINKING);
  const bubbles = useTown((s) => s.bubbles);
  const conversations = useTown((s) => s.conversations);
  const selection = useTown((s) => s.selection);
  const mode = useTown((s) => s.mode);
  const focus = useTown((s) => s.focus);
  const follow = useTown((s) => s.follow);
  const draft = useTown((s) => s.draft);
  const tool = useTown((s) => s.tool);
  const catalogId = useTown((s) => s.catalogId);
  const templateId = useTown((s) => s.templateId);
  const rot = useTown((s) => s.rot);
  const paint = useTown((s) => s.paint);
  const hover = useTown((s) => s.hover);
  const check = useTown((s) => s.check);
  const picked = useTown((s) => s.picked);
  const paints = useMemo(() => themePaints(info), [info]);
  const catalog = useMemo(() => new Map(info.content.items.map((i) => [i.id, i])), [info]);
  const [, setTick] = useState(0);

  // ---------------------------------------------------------------- scene lifecycle
  useEffect(() => {
    const canvas = canvasRef.current!;
    const scene = new TownScene(canvas, map, info, {
      reducedMotion: prefersReduced(),
      onFrame: (pts: Record<string, OverlayPoint>, labels: OverlayLabel[]) => {
        for (const [id, p] of Object.entries(pts)) {
          const el = bubbleRefs.current[id];
          if (!el) continue;
          el.style.transform = `translate3d(${p.x}px, ${p.y}px, 0) translate(-50%, -100%)`;
          el.style.visibility = p.visible ? "visible" : "hidden";
        }
        const layer = labelLayer.current;
        if (layer) {
          const keep = new Set(labels.map((l) => l.key));
          for (const child of [...layer.children] as HTMLElement[]) if (!keep.has(child.dataset.key ?? "")) child.remove();
          for (const l of labels) {
            let el = layer.querySelector<HTMLElement>(`[data-key="${l.key}"]`);
            if (!el) {
              el = document.createElement("div");
              el.dataset.key = l.key;
              el.className = "pointer-events-none absolute left-0 top-0 whitespace-nowrap rounded-full bg-[var(--panel)]/85 px-2.5 py-0.5 font-display text-xs font-semibold text-[var(--text)] shadow-sm";
              el.textContent = l.text;
              layer.appendChild(el);
            }
            el.style.transform = `translate3d(${l.x}px, ${l.y}px, 0) translate(-50%, -50%)`;
          }
        }
      },
    });
    sceneRef.current = scene;
    const ro = new ResizeObserver(() => {
      const r = wrapRef.current!.getBoundingClientRect();
      scene.resize(r.width, r.height);
    });
    ro.observe(wrapRef.current!);
    (window as unknown as { __town?: TownScene }).__town = scene;
    return () => {
      ro.disconnect();
      scene.dispose();
      sceneRef.current = null;
    };
  }, [info, map]);

  // bubbles refresh a few times a second (sim time advances via polling)
  useEffect(() => {
    const id = window.setInterval(() => setTick((t) => t + 1), 500);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => sceneRef.current?.updateFrame(frame), [frame]);
  useEffect(() => {
    if (clock) sceneRef.current?.setHour(new Date(`${clock.time}Z`).getUTCHours() + new Date(`${clock.time}Z`).getUTCMinutes() / 60);
  }, [clock]);
  useEffect(() => {
    const items = game?.items ?? [];
    sceneRef.current?.setItems(mode === "build" ? shownItems(items, draft.ops) : shownItems(items, []), paints);
  }, [game?.items, draft.ops, mode, paints]);
  useEffect(() => {
    const color = (t: string) => info.content.themes.find((x) => x.id === t)?.color ?? "#ffd166";
    sceneRef.current?.setSparkles(game?.sparkles ?? [], color);
  }, [game?.sparkles, info]);
  useEffect(() => {
    sceneRef.current?.select(selection?.kind === "resident" ? selection.id : null);
  }, [selection]);
  useEffect(() => {
    if (focus) sceneRef.current?.focus(focus.tile);
  }, [focus]);
  useEffect(() => sceneRef.current?.setFollow(follow), [follow]);

  // ---------------------------------------------------------------- build ghost
  const ghostOps: BuildOp[] = useMemo(() => {
    if (mode !== "build" || !hover) return [];
    if (tool === "place" && catalogId) return [{ op: "place", catalog_id: catalogId, x: hover[0], y: hover[1], rot, paint }];
    if (tool === "template" && templateId) {
      const t = [...info.content.templates, ...(game?.user_templates ?? [])].find((x) => x.id === templateId);
      return t ? templateOps(t, hover[0], hover[1]) : [];
    }
    return [];
  }, [mode, hover, tool, catalogId, templateId, rot, paint, info, game?.user_templates]);

  // tiles of the item picked for moving, highlighted while no ghost is shown
  const pickedTiles: Tile[] = useMemo(() => {
    if (mode !== "build" || !picked) return [];
    const shown = shownItems(game?.items ?? [], draft.ops).find((i) => i.key === picked);
    const cat = shown ? catalog.get(shown.catalog_id) : undefined;
    return shown && cat ? footprint(cat, shown.x, shown.y, shown.rot) : [];
  }, [mode, picked, game?.items, draft.ops, catalog]);

  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;
    if (!ghostOps.length) {
      scene.setGhost([], paints, pickedTiles);
      return;
    }
    const verdicts = check?.verdicts.slice(-ghostOps.length) ?? [];
    const parts: GhostPart[] = ghostOps.map((op, i) => ({ catalogId: op.catalog_id!, x: op.x!, y: op.y!, rot: op.rot ?? 0, paint: op.paint ?? null, ok: verdicts[i]?.ok ?? false }));
    scene.setGhost(parts, paints);
  }, [ghostOps, check, paints, pickedTiles]);

  // validate the draft plus the ghost against the server's last snapshot (debounced)
  useEffect(() => {
    if (mode !== "build") return;
    const ops = [...draft.ops, ...ghostOps];
    if (!ops.length) {
      useTown.getState().setBuild({ check: null });
      return;
    }
    const id = window.setTimeout(async () => {
      try {
        const res = await api.validateBuild(ops);
        useTown.getState().setBuild({ check: res });
      } catch {
        /* the build panel shows connection problems */
      }
    }, 90);
    return () => window.clearTimeout(id);
  }, [mode, draft.ops, ghostOps]);

  // ---------------------------------------------------------------- input
  useEffect(() => {
    const canvas = canvasRef.current!;
    let down: { x: number; y: number; moved: boolean } | null = null;
    const pointers = new Map<number, { x: number; y: number }>();
    let pinch = 0;
    const local = (e: PointerEvent | WheelEvent) => {
      const r = canvas.getBoundingClientRect();
      return { x: e.clientX - r.left, y: e.clientY - r.top };
    };
    const onDown = (e: PointerEvent) => {
      canvas.setPointerCapture(e.pointerId);
      pointers.set(e.pointerId, local(e));
      down = { ...local(e), moved: false };
      if (pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        pinch = Math.hypot(a.x - b.x, a.y - b.y);
      }
    };
    const onMove = (e: PointerEvent) => {
      const p = local(e);
      const scene = sceneRef.current;
      if (!scene) return;
      if (pointers.has(e.pointerId)) {
        const prev = pointers.get(e.pointerId)!;
        pointers.set(e.pointerId, p);
        if (pointers.size === 2) {
          const [a, b] = [...pointers.values()];
          const d = Math.hypot(a.x - b.x, a.y - b.y);
          if (pinch > 0) scene.zoomBy(d / pinch);
          pinch = d;
          return;
        }
        if (down && (down.moved || Math.hypot(p.x - down.x, p.y - down.y) > 5)) {
          down.moved = true;
          scene.panPixels(p.x - prev.x, p.y - prev.y);
          return;
        }
      }
      const st = useTown.getState();
      if (st.mode === "build") {
        const t = scene.tileAt(p.x, p.y);
        const h = st.hover;
        if (!t) st.setBuild({ hover: null });
        else if (!h || h[0] !== t[0] || h[1] !== t[1]) st.setBuild({ hover: t });
      }
    };
    const onUp = (e: PointerEvent) => {
      pointers.delete(e.pointerId);
      if (pointers.size < 2) pinch = 0;
      const wasClick = down && !down.moved;
      down = null;
      if (!wasClick) return;
      const p = local(e);
      handleClick(p.x, p.y);
    };
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      sceneRef.current?.zoomBy(e.deltaY > 0 ? 0.88 : 1.14);
    };
    canvas.addEventListener("pointerdown", onDown);
    canvas.addEventListener("pointermove", onMove);
    canvas.addEventListener("pointerup", onUp);
    canvas.addEventListener("pointercancel", onUp);
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      canvas.removeEventListener("pointerdown", onDown);
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerup", onUp);
      canvas.removeEventListener("pointercancel", onUp);
      canvas.removeEventListener("wheel", onWheel);
    };
  }, []);

  function handleClick(x: number, y: number) {
    const scene = sceneRef.current;
    const st = useTown.getState();
    if (!scene) return;
    if (st.mode === "build") {
      const t = scene.tileAt(x, y);
      if (st.tool === "place" && st.catalogId && t) {
        st.setBuild({ draft: push(st.draft, [{ op: "place", catalog_id: st.catalogId, x: t[0], y: t[1], rot: st.rot, paint: st.paint }]) });
        return;
      }
      if (st.tool === "template" && st.templateId && t) {
        const tpl = [...st.info!.content.templates, ...(st.poll?.game?.user_templates ?? [])].find((q) => q.id === st.templateId);
        if (tpl) st.setBuild({ draft: push(st.draft, templateOps(tpl, t[0], t[1])) });
        return;
      }
      const hit = scene.pick(x, y, { residents: false });
      if (hit?.kind === "item") st.setBuild({ picked: hit.key });
      else if (st.picked && t) {
        // move the picked item here
        const shown = shownItems(st.poll?.game?.items ?? [], st.draft.ops).find((i) => i.key === st.picked);
        if (shown?.committedId) st.setBuild({ draft: push(st.draft, [{ op: "move", item_id: shown.committedId, x: t[0], y: t[1], rot: shown.rot }]) });
        else if (shown?.opIndex !== null && shown?.opIndex !== undefined) {
          const ops = st.draft.ops.map((op, i) => (i === shown.opIndex ? { ...op, x: t[0], y: t[1] } : op));
          st.setBuild({ draft: { ops, undo: [...st.draft.undo, st.draft.ops], redo: [] } });
        }
      } else st.setBuild({ picked: null });
      return;
    }
    const hit = scene.pick(x, y);
    if (!hit) return st.select(null);
    switch (hit.kind) {
      case "resident":
        st.select({ kind: "resident", id: hit.id });
        break;
      case "sparkle":
        if (st.poll?.replay) {
          st.toast({ tone: "info", title: "A sparkle from a conversation", body: "Two residents left it behind. In a live town you can collect it as a motif." });
          break;
        }
        void api
          .action("collect_sparkle", { sparkle: hit.id })
          .then((r) => st.addPending(r.seq, "collect"))
          .catch((e) => st.toast({ tone: "warn", title: "Could not collect the sparkle", body: failureBody(e) }));
        break;
      case "item": {
        const item = st.poll?.game?.items.find((i) => i.id === hit.key);
        st.select(item ? { kind: "item", id: item.id } : null);
        break;
      }
      case "object":
        st.select({ kind: "object", address: hit.address });
        break;
      default:
        st.select(null);
    }
  }

  // ---------------------------------------------------------------- overlay content
  const now = clock?.time ?? info.start;
  const residents = info.residents;
  const nameToId = useMemo(() => new Map(residents.map((r) => [r.id, r.first_name])), [residents]);
  return (
    <div ref={wrapRef} className="absolute inset-0">
      <canvas
        ref={canvasRef}
        role="img"
        className={`block size-full touch-none ${mode === "build" ? "cursor-crosshair" : "cursor-pointer"}`}
        aria-label="The town, seen from above. With the keyboard, find residents in the notebook (N) and nearby things with Look Around (L)."
      />
      <div ref={labelLayer} className="pointer-events-none absolute inset-0 overflow-hidden" />
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        {residents.map((r) => {
          const a = frame?.agents[r.id];
          const said = bubbles[r.id];
          const conv = conversations.find((c) => c.participants.includes(r.id) && currentLine(c, now)?.speaker === r.id);
          const line = conv ? currentLine(conv, now) : null;
          const think = thinking[r.id];
          const req = game?.requests.find((q) => q.agent_id === r.id && q.status !== "fulfilled");
          const text = said?.text ?? line?.text ?? null;
          const Icon = activityIcon(a?.activity ?? "");
          return (
            <div key={r.id} ref={(el) => void (bubbleRefs.current[r.id] = el)} className="absolute left-0 top-0 flex flex-col items-center gap-1" style={{ visibility: "hidden" }}>
              {text ? (
                <div className="max-w-[240px] rounded-2xl bg-[var(--panel)] px-3 py-1.5 text-center text-[13px] font-semibold leading-snug text-[var(--text)] shadow-md">
                  <span className="sr-only">{nameToId.get(r.id)} says: </span>
                  <span className="line-clamp-3">{text}</span>
                </div>
              ) : null}
              <div className="flex items-center gap-1">
                {req ? (
                  <span className={`flex size-6 items-center justify-center rounded-full shadow ${req.status === "ready" ? "bg-[#58b368]" : "bg-sun"}`} title={req.wish}>
                    {req.status === "ready" ? <Check size={14} weight="bold" color="#ffffff" aria-hidden="true" /> : <ExclamationMark size={14} weight="bold" color="#2a2838" aria-hidden="true" />}
                    <span className="sr-only">{req.status === "ready" ? "Request ready to deliver" : "Has a request"}</span>
                  </span>
                ) : null}
                <span className="flex h-7 items-center gap-1 rounded-full bg-[var(--panel)] px-2 shadow-md" title={activityLabel(a?.activity ?? "")}>
                  {think ? (
                    <span className="flex gap-0.5">
                      {[0, 1, 2].map((i) => (
                        <span key={i} aria-hidden="true" className="size-1.5 animate-bounce rounded-full bg-[var(--muted)]" style={{ animationDelay: `${i * 120}ms` }} />
                      ))}
                      <span className="sr-only">thinking</span>
                    </span>
                  ) : a?.sleeping ? (
                    <>
                      <MoonStars size={15} weight="fill" color="#6b6fa8" aria-hidden="true" />
                      <span className="sr-only">asleep</span>
                    </>
                  ) : (
                    <Icon size={15} weight="fill" aria-hidden="true" />
                  )}
                  <span className="font-display text-xs font-semibold">{r.first_name}</span>
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

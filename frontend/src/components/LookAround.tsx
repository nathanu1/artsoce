import { Binoculars, Cube, Sparkle, X } from "@phosphor-icons/react";
import { motion, useReducedMotion } from "motion/react";
import { useEffect, useMemo, useRef } from "react";
import { api } from "../api";
import { iconByName } from "../lib/icons";
import { objectName, placeOfAddress } from "../lib/places";
import { failureBody } from "../lib/text";
import { useTown } from "../store";
import type { Tile } from "../types";
import { IconButton } from "./ui";

type SceneLike = { viewCenter: () => Tile };
const scene = () => (window as unknown as { __town?: SceneLike }).__town;
const dist = (a: Tile, b: Tile) => Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]);

/**
 * Everything near the middle of the view as a list: sparkles to collect, things you placed and
 * objects to search or change. The keyboard route to what is otherwise clicked in the town.
 */
export function LookAround() {
  const map = useTown((s) => s.map)!;
  const info = useTown((s) => s.info)!;
  const game = useTown((s) => s.poll?.game);
  const setLook = useTown((s) => s.setLook);
  const reduce = useReducedMotion();
  const first = useRef<HTMLButtonElement>(null);
  const opener = useRef<Element | null>(null);

  const center: Tile = useMemo(() => scene()?.viewCenter() ?? [70, 50], []);
  const near = useMemo(() => {
    const sparkles = (game?.sparkles ?? [])
      .filter((s) => s.tile && dist(s.tile, center) <= 24)
      .sort((a, b) => dist(a.tile!, center) - dist(b.tile!, center))
      .slice(0, 6);
    const items = (game?.items ?? [])
      .map((i) => ({ item: i, d: dist([i.x, i.y], center) }))
      .filter((x) => x.d <= 20)
      .sort((a, b) => a.d - b.d)
      .slice(0, 6)
      .map((x) => x.item);
    const placed = new Set((game?.items ?? []).map((i) => i.address));
    const objects = [...map.objects.entries()]
      .filter(([address]) => !placed.has(address) && !map.groundObjects.has(address))
      .map(([address, tiles]) => ({ address, tile: tiles[0], d: Math.min(...tiles.map((t) => dist(t, center))) }))
      .filter((o) => o.d <= 14)
      .sort((a, b) => a.d - b.d)
      .slice(0, 10);
    return { sparkles, items, objects };
  }, [game?.sparkles, game?.items, map, center]);

  const close = () => {
    setLook(false);
    if (opener.current instanceof HTMLElement && opener.current.isConnected) opener.current.focus();
  };

  useEffect(() => {
    opener.current = document.activeElement;
    first.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []); // once, when the list opens

  const open = (sel: { kind: "object"; address: string } | { kind: "item"; id: string }, tile: Tile) => {
    const st = useTown.getState();
    st.focusOn(tile);
    st.select(sel);
    setLook(false);
  };

  const collect = async (id: string) => {
    const st = useTown.getState();
    try {
      const ack = await api.action("collect_sparkle", { sparkle: id });
      st.addPending(ack.seq, "collect");
    } catch (e) {
      st.toast({ tone: "warn", title: "Could not collect the sparkle", body: failureBody(e) });
    }
  };

  const themeOf = (id: string) => info.content.themes.find((t) => t.id === id);
  const catalog = new Map(info.content.items.map((i) => [i.id, i]));
  const empty = !near.sparkles.length && !near.items.length && !near.objects.length;
  let firstUsed = false;
  const firstRef = () => {
    if (firstUsed) return undefined;
    firstUsed = true;
    return first;
  };
  const row = "flex w-full items-center gap-2.5 rounded-2xl px-2.5 py-2 text-left hover:bg-[var(--panel-hover)]";

  return (
    <motion.div
      role="dialog"
      aria-labelledby="look-title"
      initial={reduce ? false : { y: -10, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      className="pointer-events-auto panel absolute right-3 top-[76px] z-20 flex max-h-[min(70dvh,560px)] w-[min(92vw,340px)] flex-col overflow-hidden sm:right-4 sm:top-[88px]"
    >
      <div className="flex items-center gap-2 border-b-2 border-[var(--line)] px-3 py-2">
        <Binoculars size={20} weight="fill" color="#2a9d96" aria-hidden="true" />
        <h2 id="look-title" className="flex-1 font-display text-lg font-bold">
          Look Around
        </h2>
        <IconButton label="Close (Esc)" icon={X} onClick={close} />
      </div>
      <div className="scroll-thin flex-1 overflow-y-auto overscroll-contain p-2">
        {empty ? <p className="p-2 text-sm text-[var(--muted)]">Nothing to look at here. Move the view closer to a building or a park, then look again.</p> : null}
        {near.sparkles.length ? (
          <section className="mb-2">
            <h3 className="px-2.5 py-1 text-xs font-bold uppercase tracking-wide text-[var(--muted)]">Sparkles</h3>
            {near.sparkles.map((s) => {
              const t = themeOf(s.theme);
              return (
                <button key={s.id} ref={firstRef()} type="button" className={row} onClick={() => void collect(s.id)}>
                  <Sparkle size={20} weight="fill" color={t?.color} aria-hidden="true" />
                  <span className="min-w-0 flex-1 truncate font-semibold">Collect a {t?.name ?? ""} sparkle</span>
                </button>
              );
            })}
          </section>
        ) : null}
        {near.items.length ? (
          <section className="mb-2">
            <h3 className="px-2.5 py-1 text-xs font-bold uppercase tracking-wide text-[var(--muted)]">Things You Placed</h3>
            {near.items.map((i) => {
              const cat = catalog.get(i.catalog_id);
              const Icon = iconByName(themeOf(cat?.theme ?? "")?.icon);
              return (
                <button key={i.id} ref={firstRef()} type="button" className={row} onClick={() => open({ kind: "item", id: i.id }, [i.x, i.y])}>
                  <Icon size={20} weight="fill" color={themeOf(cat?.theme ?? "")?.color} aria-hidden="true" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-semibold capitalize">{i.name || cat?.name || i.catalog_id}</span>
                    <span className="block truncate text-xs text-[var(--muted)]">{placeOfAddress(i.address)}</span>
                  </span>
                </button>
              );
            })}
          </section>
        ) : null}
        {near.objects.length ? (
          <section>
            <h3 className="px-2.5 py-1 text-xs font-bold uppercase tracking-wide text-[var(--muted)]">Objects</h3>
            {near.objects.map((o) => (
              <button key={o.address} ref={firstRef()} type="button" className={row} onClick={() => open({ kind: "object", address: o.address }, o.tile)}>
                <Cube size={20} weight="fill" color="#8a7bb8" aria-hidden="true" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-semibold capitalize">{objectName(o.address)}</span>
                  <span className="block truncate text-xs text-[var(--muted)]">{placeOfAddress(o.address)}</span>
                </span>
              </button>
            ))}
          </section>
        ) : null}
      </div>
    </motion.div>
  );
}
